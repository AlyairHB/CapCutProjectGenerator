"""Flujo compartido por la interfaz y las pruebas."""
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from engines import audio, capcut


@dataclass
class Options:
    mode: str = 'combined'
    document: str = ''
    narration: str = ''
    document2: str = ''
    narration2: str = ''
    output: str = ''
    name: str = 'Proyecto_CapCut'
    videos: tuple = ()
    audios: tuple = ()
    fmt: str = 'mp3'
    model: str = 'small'
    margin: float = 0.08
    videos_per_chapter: int = 4
    strict: bool = False
    trim: float = 0.5
    generic: dict = field(default_factory=dict)
    sticker_ids: tuple = ()
    sticker_interval: float = 10.0
    sticker_duration: float = 3.0


def sticker_settings(ids_value, interval_value=10.0, duration_value=3.0):
    return capcut.sticker_settings(ids_value, interval_value, duration_value)


def source_pairs(options):
    pairs = [(options.document, options.narration)]
    if options.document2 or options.narration2:
        pairs.append((options.document2, options.narration2))
    return pairs


def validate(options):
    if options.mode not in {'combined', 'split', 'capcut'}:
        raise ValueError('Modo de trabajo inválido.')
    name = options.name.strip()
    if not name or name in {'.', '..'} or any(c in name for c in '/\\<>:"|?*') or name.endswith('.'):
        raise ValueError('Escribe un nombre de proyecto válido, sin rutas ni caracteres especiales.')
    if not options.output.strip():
        raise ValueError('Selecciona una carpeta de salida.')
    if Path(options.output).exists() and not Path(options.output).is_dir():
        raise ValueError('La salida debe ser una carpeta.')
    if not math.isfinite(options.margin) or not 0 <= options.margin <= 2:
        raise ValueError('El margen debe estar entre 0 y 2 segundos.')
    if not math.isfinite(options.trim) or options.trim < 0:
        raise ValueError('El recorte inicial debe ser un número mayor o igual a cero.')
    if options.fmt not in {'mp3', 'wav'}:
        raise ValueError('Formato de audio inválido.')
    if options.mode != 'capcut':
        chapters = 0
        for index, (document, narration) in enumerate(source_pairs(options), 1):
            for label, value in [('documento', document), ('audio de narración', narration)]:
                if not value or not Path(value).is_file():
                    raise ValueError(f'Selecciona un {label} existente para la parte {index}.')
            count = len(audio.paragraphs_from_file(document))
            if not count:
                raise ValueError(f'El documento de la parte {index} no contiene párrafos.')
            chapters += count
    else:
        chapters = len(options.audios)
    if options.mode != 'split':
        if type(options.videos_per_chapter) is not int or options.videos_per_chapter < 1:
            raise ValueError('Videos por capítulo debe ser un entero mayor que cero.')
        if not chapters or len(options.videos) != chapters * options.videos_per_chapter:
            raise ValueError(f'Para {chapters} capítulos se necesitan {chapters * options.videos_per_chapter} videos; seleccionaste {len(options.videos)}.')
        if options.strict and chapters != 40:
            raise ValueError(f'Se exigen 40 capítulos; se encontraron {chapters}.')
        for paths, extensions in [(options.videos, capcut.VIDEO), (options.audios if options.mode == 'capcut' else (), capcut.AUDIO)]:
            if len(set(map(str, paths))) != len(paths):
                raise ValueError('La selección contiene archivos repetidos.')
            if any(not Path(p).is_file() or Path(p).suffix.lower() not in extensions for p in paths):
                raise ValueError('La selección contiene archivos inexistentes o de formato no admitido.')
        generic_blocks = (
            ('bloque tras el capítulo 7', ('generic_video', 'generic_audio')),
            ('bloque final', ('generic_end_video', 'generic_end_audio')),
        )
        for label, keys in generic_blocks:
            values = [options.generic.get(k) for k in keys]
            if any(values) and not all(values):
                raise ValueError(f'Selecciona el video y el audio del {label}, o deja ambos vacíos.')
            for key, value in zip(keys, values):
                if not value:
                    continue
                p = Path(value)
                if not p.is_file() or p.suffix.lower() not in (capcut.VIDEO if 'video' in key else capcut.AUDIO):
                    raise ValueError(f'Archivo genérico inválido: {p}')
        sticker_settings(options.sticker_ids, options.sticker_interval, options.sticker_duration)
    for tool in (('ffprobe',) if options.mode == 'capcut' else ('ffmpeg', 'ffprobe') if options.mode == 'combined' else ('ffmpeg',)):
        if not shutil.which(tool):
            raise ValueError(f'No se encontró {tool} en PATH. Instala FFmpeg.')
    dest = Path(options.output).expanduser().resolve() / name
    if dest.exists():
        raise FileExistsError(f'Ya existe {dest}. Elige otro nombre para no sobrescribir.')
    return dest, chapters


def run(options, emit=print):
    dest, chapters = validate(options)
    sticker_ids, sticker_interval, sticker_duration = sticker_settings(
        options.sticker_ids, options.sticker_interval, options.sticker_duration)
    # Carpeta exclusiva para cada ejecución: conserva los medios referenciados por CapCut.
    dest.mkdir(parents=True, exist_ok=False)
    audios = options.audios
    if options.mode != 'capcut':
        audio_dir = dest / 'audios'
        pairs = source_pairs(options)
        exported = []
        for index, (document, narration) in enumerate(pairs, 1):
            count = len(audio.paragraphs_from_file(document))
            # Cada alineación usa únicamente el documento correspondiente a su audio.
            part_dir = audio_dir if len(pairs) == 1 else audio_dir / f'parte_{index:03d}'
            part_dir.parent.mkdir(parents=True, exist_ok=True)
            emit(f'Paso 1: cortar parte {index}/{len(pairs)} ({count} capítulos).')
            audio.align_and_export(document, narration, part_dir,
                                   options.fmt, options.margin, options.model, emit)
            cuts = [part_dir / f'audio_{i:03d}.{options.fmt}' for i in range(1, count + 1)]
            if any(not p.is_file() for p in cuts):
                raise RuntimeError(f'El cortador no produjo todos los audios de la parte {index}. Se conserva la salida para revisión.')
            if len(pairs) > 1:
                # Numeración global para que el orden natural de CapCut respete ambas partes.
                for cut in cuts:
                    target = audio_dir / f'audio_{len(exported) + 1:03d}.{options.fmt}'
                    cut.rename(target)
                    exported.append(target)
            else:
                exported.extend(cuts)
        audios = tuple(exported)
    if options.mode != 'split':
        emit('Paso 2: generar borrador de CapCut.' if options.mode == 'combined' else 'Generando borrador de CapCut.')
        capcut.init_kind()
        result = capcut.generate('', '', dest, name='CapCut', strict=options.strict,
                                 progress=lambda done, total, msg: emit(f'{msg} ({done}/{total})'),
                                 selected_videos=options.videos, selected_audios=audios,
                                 trim_start=options.trim, videos_per_chapter=options.videos_per_chapter,
                                 sticker_ids=sticker_ids, sticker_interval=sticker_interval,
                                 sticker_duration=sticker_duration,
                                 **{k: v for k, v in options.generic.items() if v})
        emit(f'Borrador creado en: {result[0]}')
    emit(f'Proceso terminado: {dest}')
    return dest
