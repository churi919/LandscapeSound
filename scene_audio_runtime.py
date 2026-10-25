"""Run local scene-conditioned audio in its own environment and verify caches."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid


RUNTIME_VERSION = 'scene-audio-runtime-1'
MODEL_REVISION = '08b17423649b5714b22eab20f96bf00751f2358a'
GENERATED_CATEGORIES = frozenset({'trees', 'water', 'surf', 'stream', 'traffic', 'wind'})


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def _validate(plan, root=None):
    root = Path(root or Path(__file__).resolve().parent).resolve()
    if not isinstance(plan, dict):
        raise ValueError('Scene audio plan must be a dictionary')
    key = plan.get('cache_key', '')
    if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
        raise ValueError('Scene audio cache_key must be a 64-character SHA256 hex string')
    image_hash = plan.get('image_sha256_rgb', '')
    if not isinstance(image_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', image_hash):
        raise ValueError('Scene audio plan needs a valid image fingerprint')
    model = plan.get('model')
    if model is not None:
        if (not isinstance(model, dict) or model.get('revision') != MODEL_REVISION
                or model.get('seconds') != 30 or model.get('steps') != 8 or model.get('cfg') != 1
                or model.get('id') != 'stable-audio-3' or model.get('dit') != 'medium'
                or model.get('decoder') != 'same-l' or model.get('precision') != 'w8a8'):
            raise ValueError('Scene plan model configuration does not match the deployed Medium runtime')
    stems = plan.get('stems', plan.get('items', []))
    if not isinstance(stems, list) or len(stems) > 3:
        raise ValueError('At most three independently generated scene stems are supported')
    seen = set()
    for stem in stems:
        if not isinstance(stem, dict) or stem.get('category') not in GENERATED_CATEGORIES:
            raise ValueError('Unsupported scene stem')
        if stem['category'] in seen:
            raise ValueError('Duplicate scene stem category')
        seen.add(stem['category'])
        if not isinstance(stem.get('prompt'), str) or not stem['prompt'].strip():
            raise ValueError('A scene-specific generation prompt is required')
        if not isinstance(stem.get('seed'), int) or not 0 <= stem['seed'] <= 2**32-1:
            raise ValueError('Generation seed must be an unsigned 32-bit integer')
        if stem.get('seconds', 30) != 30:
            raise ValueError('This runtime currently generates 30-second raw candidates')
    return root, root/'assets'/'scene_generated'/key


def _stems(plan):
    return plan.get('stems', plan.get('items', []))


def _result(plan, folder, metadata, generated):
    return {'status': 'ready', 'assets_dir': str(folder),
        'manifest_path': str(folder/'generated'/'manifest.json'),
        'cache_key': plan['cache_key'], 'image_sha256_rgb': plan['image_sha256_rgb'],
        'generated': bool(generated), 'reused': not bool(generated),
        'stems': metadata['items'], 'manifest': metadata}


def load_scene_audio(plan, root=None):
    """Return an independently generated, checksum-verified cache, or None."""
    _, folder = _validate(plan, root)
    if not _stems(plan):
        return {'status': 'empty', 'assets_dir': None, 'manifest_path': None,
            'cache_key': plan['cache_key'], 'generated': False, 'reused': False, 'stems': []}
    try:
        metadata = json.loads((folder/'generated'/'manifest.json').read_text(encoding='utf-8'))
        if metadata.get('plan_sha256') != _json_hash(plan) or metadata.get('runtime_version') != RUNTIME_VERSION:
            return None
        if metadata.get('image_sha256_rgb') != plan['image_sha256_rgb'] or metadata.get('scene_specific') is not True:
            return None
        items = metadata['items']
        if {x['category'] for x in items} != {x['category'] for x in _stems(plan)}:
            return None
        planned = {x['category']: x for x in _stems(plan)}
        if len(items) != len(planned):
            return None
        for item in items:
            path = folder/'generated'/(item['category']+'.wav')
            raw_path = folder/'raw'/(item['category']+'.wav')
            expected = planned[item['category']]
            generation = item.get('generation', {})
            if generation.get('prompt') != expected['prompt'] or generation.get('seed') != expected['seed']:
                return None
            if _digest(path) != item['sha256'] or _digest(raw_path) != item['raw_source_sha256']:
                return None
            if item.get('duration_seconds') != 28 or item.get('ai_generated') is not True:
                return None
        return _result(plan, folder, metadata, False)
    except (OSError, ValueError, KeyError, TypeError):
        return None


@contextmanager
def _scene_lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder/'.generation.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError('这张全景的声音正在生成，请稍后再试。') from exc
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(json.dumps({'pid': os.getpid(), 'started_utc': datetime.now(timezone.utc).isoformat()}))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _prepare_materials(plan, folder, root, raw_manifest):
    # Importing this module also configures the main environment's D: cache.
    # The independent generator is never imported into the main process.
    from prepare_model_audio import texture, matched_dynamics, measure, save_audio
    generated = folder/'generated'; generated.mkdir(parents=True, exist_ok=True)
    items = []
    raw_by_category = {x['category']: x for x in raw_manifest['items']}
    for stem in _stems(plan):
        category = stem['category']; raw = raw_by_category[category]
        path = folder/'raw'/(category+'.wav')
        if _digest(path) != raw['sha256']:
            raise ValueError('Scene generation checksum mismatch before processing')
        audio, ratio = texture(path, highpass=True, seconds=30)
        processed, dynamics = matched_dynamics(audio, -23.)
        before = measure(processed)
        target = min(-23., before['integrated_lufs'] - 1.5 - before['true_peak_4x_dbtp'])
        item = save_audio(generated/(category+'.wav'), processed, target)
        if item['true_peak_4x_dbtp'] > -1.45:
            raise ValueError('Scene processed audio violates estimated peak headroom')
        item.update(category=category, generation=raw, raw_source_sha256=raw['sha256'],
            ai_generated=True, pictured_site_recording=False, mono_downmix_rms_ratio=ratio,
            original_stereo_path=str(path), dynamics=dynamics, target_lufs=target,
            subjectively_auditioned=False, scene_specific=True,
            processing='scene raw stereo retained; mono downmix, 55Hz high-pass, 32kHz resample, 2s circular crossfade, lookahead soft-knee dynamics, LUFS normalization with 4x-estimated peak headroom')
        items.append(item)
    # These are explicitly comparison assets. Generated materials never copy a
    # generic generated WAV, and no source category is substituted for another.
    for profile in ['legacy', 'natural']:
        target = folder/profile; target.mkdir(parents=True, exist_ok=True)
        references = root/'assets'/profile
        # A clean source checkout need not include optional reference media.
        # Its new-image generated track must still complete independently.
        if not references.is_dir():
            continue
        for source in references.iterdir():
            if source.is_file() and source.suffix.lower() in {'.wav', '.json'}:
                shutil.copy2(source, target/source.name)
    metadata = {'schema_version': 1, 'runtime_version': RUNTIME_VERSION,
        'scene_specific': True, 'ai_generated': True, 'not_ai_generated': False,
        'cache_key': plan['cache_key'], 'image_sha256_rgb': plan['image_sha256_rgb'],
        'plan_sha256': _json_hash(plan), 'plan': plan,
        'model': {'id': 'stable-audio-3', 'name': 'Stable Audio 3 Medium · 本全景专属',
            'checkpoint_repo': raw_manifest['model_repo'], 'revision': raw_manifest['model_revision']},
        'model_source': 'https://huggingface.co/stabilityai/stable-audio-3-optimized',
        'items': items, 'pictured_site_recording': False,
        'raw_manifest': str(folder/'raw'/'manifest.json'),
        'comparison_fixed_offsets': False,
        'comparison_materials': 'natural and legacy are shared comparison references, not scene-generated materials; no matched-loudness claim',
        'loudness_method': 'pyloudnorm K-weighted integrated loudness, 4x estimated true peak; not a certified meter',
        'subjective_quality': 'not measured; generated events may deviate from the picture or prompt',
        'created_utc': datetime.now(timezone.utc).isoformat()}
    _write_json(generated/'manifest.json', metadata)
    return metadata


def ensure_scene_audio(plan, root=None):
    """Generate missing scene stems locally, then postprocess and verify them.

    No model download is attempted here. A failed generation raises and leaves
    no ready manifest; a caller must explicitly label any generic fallback.
    """
    root, folder = _validate(plan, root)
    cached = load_scene_audio(plan, root)
    if cached is not None:
        return cached
    with _scene_lock(folder):
        cached = load_scene_audio(plan, root)
        if cached is not None:
            return cached
        _write_json(folder/'plan.json', plan)
        python = root/'audio_model'/'.venv'/'Scripts'/'python.exe'
        worker = root/'audio_model'/'generate_scene_audio.py'
        if not python.is_file() or not worker.is_file():
            raise RuntimeError('本机音频生成环境尚未安装，不能生成专属声音。')
        log = folder/'generation_worker.log'
        with log.open('w', encoding='utf-8') as stream:
            child = subprocess.Popen([str(python), str(worker), '--plan', str(folder/'plan.json'),
                '--output-dir', str(folder/'raw')], cwd=root, stdout=stream, stderr=subprocess.STDOUT)
            try:
                child.wait(timeout=600)
            except BaseException:
                # psutil stays inside the independent model environment. The
                # cleanup helper verifies this exact worker + plan before it
                # can terminate the worker's descendants or remove its lock.
                subprocess.run([str(python), str(worker), '--cleanup-pid', str(child.pid),
                    '--plan', str(folder/'plan.json')], cwd=root, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=30, check=False)
                raise
        if child.returncode:
            detail = log.read_text(encoding='utf-8', errors='replace')[-2000:]
            raise RuntimeError('本次全景声音生成未完成；未套用通用素材。\n'+detail)
        raw_manifest = json.loads((folder/'raw'/'manifest.json').read_text(encoding='utf-8'))
        if raw_manifest.get('plan_sha256') != _json_hash(plan):
            raise ValueError('Scene worker returned a mismatched plan')
        metadata = _prepare_materials(plan, folder, root, raw_manifest)
        verified = load_scene_audio(plan, root)
        if verified is None:
            raise ValueError('Generated scene cache failed final verification')
        return _result(plan, folder, metadata, True)
