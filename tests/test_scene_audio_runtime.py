"""Exercise cache identity and actual postprocessing without model inference."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

from scene_audio_runtime import (_scene_lock, _validate, _json_hash,
    _prepare_materials, load_scene_audio, ensure_scene_audio)


def plan():
    return {'cache_key': 'a'*64, 'image_sha256_rgb': 'b'*64,
        'stems': [{'category': 'trees', 'prompt': 'Temporary test waveform, not an AI demo',
            'seed': 12, 'seconds': 30}]}


class SceneAudioRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_empty_plan_never_starts_a_worker_or_returns_generic_audio(self):
        value = plan(); value['stems'] = []
        result = ensure_scene_audio(value, self.root)
        self.assertEqual(result['status'], 'empty')
        self.assertIsNone(result['assets_dir'])
        self.assertFalse((self.root/'assets').exists())

    def test_cache_key_cannot_escape_its_directory(self):
        value = plan(); value['cache_key'] = '../generic'
        with self.assertRaises(ValueError): _validate(value, self.root)

    def test_changed_model_revision_is_not_silently_ignored(self):
        value = plan(); value['model'] = {'revision': 'other', 'seconds': 30, 'steps': 8, 'cfg': 1}
        with self.assertRaisesRegex(ValueError, 'configuration'):
            _validate(value, self.root)

    def test_scene_lock_excludes_concurrent_generation_and_releases(self):
        folder = self.root/'scene'
        with _scene_lock(folder):
            with self.assertRaisesRegex(RuntimeError, '正在生成'):
                with _scene_lock(folder): pass
        self.assertFalse((folder/'.generation.lock').exists())

    def test_real_processing_cache_and_tamper_detection(self):
        value = plan(); root, folder = _validate(value, self.root)
        raw_folder = folder/'raw'; raw_folder.mkdir(parents=True)
        sample_rate = 44100; t = np.arange(30*sample_rate)/sample_rate
        # A synthetic fixture only. No generated production asset is fabricated.
        mono = (.04+.02*np.sin(2*np.pi*.4*t))*np.sin(2*np.pi*600*t)
        pcm = np.round(np.column_stack([mono, mono*.9])*32767).astype(np.int16)
        path = raw_folder/'trees.wav'; wavfile.write(path, sample_rate, pcm)
        raw = {'category': 'trees', 'prompt': value['stems'][0]['prompt'],
            'seed': value['stems'][0]['seed'],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'wav': str(path),
            'fixture_only': True}
        raw_manifest = {'model_repo': 'fixture', 'model_revision': 'fixture', 'items': [raw]}
        (raw_folder/'manifest.json').write_text(json.dumps(raw_manifest), encoding='utf-8')
        # A fresh installation may have procedural controls but no licensed
        # natural-reference download. Missing optional media must not abort it.
        for profile in ['legacy']:
            source = root/'assets'/profile; source.mkdir(parents=True)
            wavfile.write(source/'trees.wav', sample_rate, pcm[:100])
        metadata = _prepare_materials(value, folder, root, raw_manifest)
        item = metadata['items'][0]
        self.assertTrue((folder/'legacy'/'trees.wav').is_file())
        self.assertFalse((folder/'natural'/'trees.wav').exists())
        self.assertEqual(item['duration_seconds'], 28)
        self.assertLessEqual(item['true_peak_4x_dbtp'], -1.45)
        self.assertAlmostEqual(item['integrated_lufs'], -23, places=2)
        self.assertTrue(item['dynamics']['changes_dynamic_range'])
        self.assertTrue(load_scene_audio(value, root)['reused'])
        changed = copy.deepcopy(value); changed['stems'][0]['prompt'] += ' different scene'
        self.assertIsNone(load_scene_audio(changed, root))
        changed = copy.deepcopy(value); changed['image_sha256_rgb'] = 'c'*64
        self.assertIsNone(load_scene_audio(changed, root))
        with (folder/'generated'/'trees.wav').open('ab') as output: output.write(b'tampered')
        self.assertIsNone(load_scene_audio(value, root))

    def test_missing_environment_fails_without_a_ready_manifest(self):
        value = plan()
        with self.assertRaisesRegex(RuntimeError, '尚未安装'):
            ensure_scene_audio(value, self.root)
        folder = self.root/'assets'/'scene_generated'/value['cache_key']
        self.assertFalse((folder/'generated'/'manifest.json').exists())
        self.assertFalse((folder/'.generation.lock').exists())

    def test_items_alias_has_same_empty_behavior(self):
        value = plan(); value['items'] = value.pop('stems'); value['items'] = []
        self.assertEqual(ensure_scene_audio(value, self.root)['status'], 'empty')


if __name__ == '__main__': unittest.main()
