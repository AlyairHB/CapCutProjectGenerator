import gc
import json
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+', text, flags=re.UNICODE)


def paragraphs_from_file(path):
    path = Path(path)
    if path.suffix.lower() == '.docx':
        from docx import Document
        return [p.text.strip() for p in Document(path).paragraphs if p.text.strip()]
    raw = path.read_text(encoding='utf-8-sig')
    raw = re.sub(r'<[^>]*>', '', raw)
    return [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', raw) if p.strip()]


def run_ffmpeg(args):
    proc = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or 'FFmpeg falló')


def free_gpu():
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def align_and_export(document, audio, output, fmt, margin, model_name, emit):
    import torch
    import whisperx
    paragraphs = paragraphs_from_file(document)
    if not paragraphs:
        raise ValueError('El documento no contiene párrafos.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    emit(f'Se encontraron {len(paragraphs)} párrafos.')
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    compute_type = 'float16' if device == 'cuda' else 'int8'
    emit(f'Dispositivo: {device} ({compute_type}).')
    emit('Cargando modelo de transcripción (la primera ejecución puede descargarlo)...')
    model = whisperx.load_model(model_name, device=device, compute_type=compute_type, language='es')
    samples = whisperx.load_audio(str(audio))
    emit('Transcribiendo el audio...')
    transcription = model.transcribe(samples, batch_size=16 if device == 'cuda' else 4, language='es')
    del model
    free_gpu()
    emit('Alineando palabras...')
    align_model, metadata = whisperx.load_align_model(language_code='es', device=device)
    aligned = whisperx.align(transcription['segments'], align_model, metadata, samples, device, return_char_alignments=False)
    del align_model
    free_gpu()
    words = []
    for segment in aligned['segments']:
        for w in segment.get('words', []):
            if 'start' in w and 'end' in w:
                tokens = normalize(w.get('word', ''))
                for token in tokens:
                    words.append((token, float(w['start']), float(w['end'])))
    if not words:
        raise RuntimeError('No se obtuvieron palabras con marcas de tiempo.')
    reference = []
    paragraph_ends = []
    for p in paragraphs:
        reference.extend(normalize(p))
        paragraph_ends.append(len(reference))
    if not reference:
        raise ValueError('El documento no tiene palabras reconocibles.')
    recognized = [w[0] for w in words]
    matcher = SequenceMatcher(None, reference, recognized, autojunk=False)
    matching = {}
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(b-a):
                matching[a+k] = c+k
    emit(f'Coincidencia exacta de palabras: {len(matching)}/{len(reference)}.')
    # Derive boundaries from matched words near the end of each paragraph.
    boundaries = []
    report = []
    for i, end in enumerate(paragraph_ends[:-1]):
        near_left = [(idx, matching[idx]) for idx in range(max(0, end-12), end) if idx in matching]
        near_right = [(idx, matching[idx]) for idx in range(end, min(len(reference), end+12)) if idx in matching]
        if not near_left or not near_right:
            raise RuntimeError(f'No hay coincidencias suficientes alrededor del párrafo {i+1}; no se exportó para evitar cortes incorrectos.')
        left = near_left[-1][1]
        right = near_right[0][1]
        if right <= left:
            raise RuntimeError(f'Orden inconsistente alrededor del párrafo {i+1}.')
        # Use midpoint of the gap, without cutting into matched words.
        boundary = (words[left][2] + words[right][1]) / 2
        if words[right][1] < words[left][2]:
            boundary = words[left][2]
        boundaries.append(boundary)
        report.append({'paragraph': i+1, 'boundary_seconds': round(boundary, 3), 'left_word': words[left][0], 'right_word': words[right][0], 'unmatched_words_near_boundary': (end-1-near_left[-1][0]) + (near_right[0][0]-end)})
    duration = len(samples)/16000
    starts = [0.0] + boundaries
    ends = boundaries + [duration]
    if any(b <= a for a, b in zip(starts, ends)):
        raise RuntimeError('Se detectaron límites de tiempo inválidos.')
    for i, (start, end) in enumerate(zip(starts, ends), 1):
        # Apply padding only inside neighboring intervals to prevent overlap.
        left = max(0.0, start - margin if i > 1 else 0.0)
        right = min(duration, end + margin if i < len(paragraphs) else duration)
        target = output / f'audio_{i:03d}.{fmt}'
        args = ['-ss', f'{left:.4f}', '-i', str(audio), '-t', f'{right-left:.4f}', '-vn']
        if fmt == 'mp3':
            args += ['-codec:a', 'libmp3lame', '-q:a', '2']
        else:
            args += ['-codec:a', 'pcm_s16le']
        run_ffmpeg([*args, str(target)])
        emit(f'Exportado {i}/{len(paragraphs)}: {target.name}')
    (output / 'reporte.json').write_text(json.dumps({'paragraphs': len(paragraphs), 'recognized_words': len(words), 'reference_words': len(reference), 'exact_matched_words': len(matching), 'boundaries': report}, ensure_ascii=False, indent=2), encoding='utf-8')
    emit('¡Finalizado! Revisa los archivos y el reporte.json.')
