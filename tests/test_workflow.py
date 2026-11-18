import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from workflow import Options, run, sticker_settings, validate


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = self.root / 'texto.txt'
        self.doc.write_text('Primer párrafo.\n\nSegundo párrafo.', encoding='utf-8')
        self.source = self.root / 'narracion.wav'
        self.wav(self.source)
        self.videos = tuple(self.root / f'video_{i}.mp4' for i in range(1, 5))
        for video in self.videos:
            video.touch()
        self.options = Options(document=str(self.doc), narration=str(self.source),
                               output=str(self.root), videos=self.videos,
                               videos_per_chapter=2, fmt='wav')

    @staticmethod
    def wav(path):
        with wave.open(str(path), 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(b'\x00\x00' * 16000)

    def splitter(self, document, narration, output, fmt, margin, model, emit):
        output.mkdir()
        for i in (1, 2):
            self.wav(output / f'audio_{i:03d}.wav')
        (output / 'reporte.json').write_text('{}')

    def test_combined_passes_real_exported_audio_to_generator(self):
        from engines import capcut
        real_probe = capcut.probe
        def probe(path):
            if path.suffix == '.wav':
                return real_probe(path)
            return dict(duration=3_000_000, width=1920, height=1080, has_audio=False, codec='h264')
        with patch('workflow.audio.align_and_export', side_effect=self.splitter), patch('workflow.capcut.probe', side_effect=probe):
            dest = run(self.options, lambda _: None)
        content = json.loads((dest / 'CapCut/draft_content.json').read_text())
        materials = content['materials']['audios']
        self.assertEqual([Path(m['path']) for m in materials], [dest / 'audios/audio_001.wav', dest / 'audios/audio_002.wav'])
        self.assertEqual(content['duration'], 2_000_000)
        self.assertEqual(len(content['tracks'][0]['segments']), 4)
        self.assertEqual([track['type'] for track in content['tracks']], ['video', 'audio'])
        self.assertEqual(content['materials']['stickers'], [])
        self.assertTrue((dest / 'audios/reporte.json').exists())
        with self.assertRaises(FileExistsError):
            validate(self.options)

    def test_stickers_cycle_ids_every_interval(self):
        self.options.sticker_ids = ('1111111111111111111', '2222222222222222222')
        self.options.sticker_interval = 1.0
        self.options.sticker_duration = 0.5
        from engines import capcut
        real_probe = capcut.probe
        def probe(path):
            if path.suffix == '.wav':
                return real_probe(path)
            return dict(duration=3_000_000, width=1920, height=1080, has_audio=False, codec='h264')
        with patch('workflow.audio.align_and_export', side_effect=self.splitter), patch('workflow.capcut.probe', side_effect=probe):
            dest = run(self.options, lambda _: None)
        content = json.loads((dest / 'CapCut/draft_content.json').read_text())
        self.assertEqual([track['type'] for track in content['tracks']], ['video', 'sticker', 'audio'])
        segments = content['tracks'][1]['segments']
        self.assertEqual([segment['target_timerange'] for segment in segments],
                         [{'start': 0, 'duration': 500_000}, {'start': 1_000_000, 'duration': 500_000}])
        stickers = content['materials']['stickers']
        self.assertEqual([sticker['resource_id'] for sticker in stickers],
                         ['1111111111111111111', '2222222222222222222'])
        self.assertTrue(all(not sticker['path'] for sticker in stickers))

    def test_sticker_settings_accept_comma_separated_ids(self):
        ids, interval, duration = sticker_settings('111, 222;333', '5', '2')
        self.assertEqual(ids, ['111', '222', '333'])
        self.assertEqual((interval, duration), (5.0, 2.0))

    def test_sticker_duration_cannot_exceed_interval(self):
        self.options.sticker_ids = ('1234567890123456789',)
        self.options.sticker_interval = 1.0
        self.options.sticker_duration = 2.0
        with self.assertRaisesRegex(ValueError, 'no puede superar'):
            validate(self.options)

    def test_invalid_sticker_id_rejected(self):
        self.options.sticker_ids = ('no-es-un-id',)
        with self.assertRaisesRegex(ValueError, 'ID de sticker'):
            validate(self.options)

    def test_wrong_video_count_fails_before_splitting(self):
        self.options.videos = self.videos[:1]
        with patch('workflow.audio.align_and_export') as splitter:
            with self.assertRaises(ValueError):
                run(self.options)
            splitter.assert_not_called()
        self.assertFalse((self.root / self.options.name).exists())

    def test_split_mode_needs_no_videos(self):
        self.options.mode = 'split'
        self.options.videos = ()
        with patch('workflow.audio.align_and_export', side_effect=self.splitter), patch('workflow.capcut.generate') as generate:
            dest = run(self.options, lambda _: None)
            generate.assert_not_called()
        self.assertTrue((dest / 'audios/audio_002.wav').exists())

    def test_capcut_mode_does_not_transcribe(self):
        self.options.mode = 'capcut'
        self.options.audios = (self.source,)
        self.options.videos = self.videos[:2]
        with patch('workflow.audio.align_and_export') as splitter, patch('workflow.capcut.generate', return_value=(self.root, 2, 1, 1)) as generate:
            run(self.options, lambda _: None)
            splitter.assert_not_called()
            self.assertEqual(generate.call_args.kwargs['selected_audios'], (self.source,))

    def test_partial_generic_selection_rejected_before_transcription(self):
        self.options.generic = {'generic_video': str(self.videos[0])}
        with self.assertRaises(ValueError):
            validate(self.options)

    def test_partial_final_block_rejected_before_transcription(self):
        self.options.generic = {'generic_end_video': str(self.videos[0])}
        with patch('workflow.audio.align_and_export') as splitter:
            with self.assertRaisesRegex(ValueError, 'bloque final'):
                run(self.options)
            splitter.assert_not_called()

    def test_final_block_without_intermediate_is_allowed(self):
        generic_video = self.root / 'final.mp4'
        generic_video.touch()
        generic_audio = self.root / 'final.wav'
        self.wav(generic_audio)
        self.options.generic = {'generic_end_video': str(generic_video),
                                'generic_end_audio': str(generic_audio)}
        from engines import capcut
        real_probe = capcut.probe
        def probe(path):
            if path.suffix == '.wav':
                return real_probe(path)
            return dict(duration=3_000_000, width=1920, height=1080, has_audio=False, codec='h264')
        with patch('workflow.audio.align_and_export', side_effect=self.splitter), patch('workflow.capcut.probe', side_effect=probe):
            dest = run(self.options, lambda _: None)
        content = json.loads((dest / 'CapCut/draft_content.json').read_text())
        self.assertEqual(content['duration'], 9_000_000)
        self.assertEqual(len(content['tracks'][0]['segments']), 5)
        self.assertEqual(len(content['tracks'][1]['segments']), 3)
        self.assertEqual(content['tracks'][0]['segments'][-1]['target_timerange'],
                         {'start': 2_000_000, 'duration': 7_000_000})

    def test_intermediate_block_without_final_is_allowed(self):
        doc = self.root / 'ocho.txt'
        doc.write_text('\n\n'.join(f'Capítulo {i}.' for i in range(1, 9)), encoding='utf-8')
        videos = tuple(self.root / f'clip_{i}.mp4' for i in range(1, 9))
        for video in videos:
            video.touch()
        self.options.document = str(doc)
        self.options.videos = videos
        self.options.videos_per_chapter = 1
        generic_video = self.root / 'intermedio.mp4'
        generic_video.touch()
        generic_audio = self.root / 'intermedio.wav'
        self.wav(generic_audio)
        self.options.generic = {'generic_video': str(generic_video),
                                'generic_audio': str(generic_audio)}
        def split(document, narration, output, *args):
            output.mkdir()
            for i in range(1, 9):
                self.wav(output / f'audio_{i:03d}.wav')
            (output / 'reporte.json').write_text('{}')
        from engines import capcut
        real_probe = capcut.probe
        def probe(path):
            if path.suffix == '.wav':
                return real_probe(path)
            return dict(duration=3_000_000, width=1920, height=1080, has_audio=False, codec='h264')
        with patch('workflow.audio.align_and_export', side_effect=split), patch('workflow.capcut.probe', side_effect=probe):
            dest = run(self.options, lambda _: None)
        content = json.loads((dest / 'CapCut/draft_content.json').read_text())
        self.assertEqual(content['duration'], 15_000_000)
        self.assertEqual(len(content['tracks'][0]['segments']), 9)
        self.assertEqual(len(content['tracks'][1]['segments']), 9)
        self.assertEqual(content['tracks'][0]['segments'][7]['target_timerange'],
                         {'start': 7_000_000, 'duration': 7_000_000})
        self.assertEqual(content['tracks'][0]['segments'][-1]['target_timerange']['start'], 14_000_000)

    def test_missing_export_stops_generation(self):
        with patch('workflow.audio.align_and_export'), patch('workflow.capcut.generate') as generate:
            with self.assertRaises(RuntimeError):
                run(self.options, lambda _: None)
            generate.assert_not_called()

    def second_part(self):
        doc = self.root / 'segunda.txt'
        doc.write_text('Tercer capítulo.', encoding='utf-8')
        narration = self.root / 'segunda.wav'
        self.wav(narration)
        self.options.document2 = str(doc)
        self.options.narration2 = str(narration)
        extra = (self.root / 'video_5.mp4', self.root / 'video_6.mp4')
        for path in extra:
            path.touch()
        self.options.videos += extra

    def test_two_documents_produce_one_timeline_in_part_order(self):
        self.second_part()
        from engines import capcut
        real_probe = capcut.probe
        def probe(path):
            if path.suffix == '.wav':
                return real_probe(path)
            return dict(duration=3_000_000, width=1920, height=1080, has_audio=False, codec='h264')
        def split(document, narration, output, *args):
            output.mkdir()
            count = 2 if document == str(self.doc) else 1
            for i in range(1, count + 1):
                self.wav(output / f'audio_{i:03d}.wav')
            (output / 'reporte.json').write_text('{}')
        with patch('workflow.audio.align_and_export', side_effect=split) as splitter, patch('workflow.capcut.probe', side_effect=probe):
            dest = run(self.options, lambda _: None)
        self.assertEqual([(c.args[0], c.args[1]) for c in splitter.call_args_list],
                         [(str(self.doc), str(self.source)), (self.options.document2, self.options.narration2)])
        content = json.loads((dest / 'CapCut/draft_content.json').read_text())
        self.assertEqual([Path(m['path']).name for m in content['materials']['audios']],
                         ['audio_001.wav', 'audio_002.wav', 'audio_003.wav'])
        self.assertEqual(content['duration'], 3_000_000)
        self.assertEqual(len(content['tracks'][0]['segments']), 6)
        self.assertTrue((dest / 'audios/parte_001/reporte.json').exists())
        self.assertTrue((dest / 'audios/parte_002/reporte.json').exists())

    def test_incomplete_second_pair_fails_before_processing(self):
        self.options.document2 = str(self.doc)
        with patch('workflow.audio.align_and_export') as splitter:
            with self.assertRaisesRegex(ValueError, 'parte 2'):
                run(self.options)
            splitter.assert_not_called()

    def test_second_part_failure_does_not_generate_project(self):
        self.second_part()
        def split(*args):
            if args[0] == self.options.document2:
                raise RuntimeError('falló parte 2')
            self.splitter(*args)
        with patch('workflow.audio.align_and_export', side_effect=split), patch('workflow.capcut.generate') as generate:
            with self.assertRaisesRegex(RuntimeError, 'falló parte 2'):
                run(self.options, lambda _: None)
            generate.assert_not_called()

    def test_unsafe_name_rejected(self):
        self.options.name = '../otro'
        with self.assertRaises(ValueError):
            validate(self.options)


if __name__ == '__main__':
    unittest.main()
