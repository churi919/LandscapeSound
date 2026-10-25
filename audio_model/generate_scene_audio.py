"""Generate separate Medium stems from a fingerprinted scene plan; no app imports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
for key, value in {'HF_HOME': BASE/'hf_cache', 'HF_HUB_CACHE': BASE/'hf_cache'/'hub',
    'TEMP': BASE/'.cache'/'tmp', 'TMP': BASE/'.cache'/'tmp'}.items():
    Path(value).mkdir(parents=True, exist_ok=True); os.environ[key] = str(value)
os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1',
    HF_HUB_OFFLINE='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')

import numpy as np
import psutil
import soundfile as sf
from memory_budget import START_AVAILABLE_GIB, RUNTIME_RESERVE_GIB, memory_budget

MODEL_REVISION = '08b17423649b5714b22eab20f96bf00751f2358a'
CODE_REVISION = '77e0398c26f7d22d801ec1bb036307e8b231f741'
GENERATED_CATEGORIES = frozenset({'trees', 'water', 'surf', 'stream', 'traffic', 'wind'})
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def stop_own_process(process):
    try:
        for child in reversed(process.children(recursive=True)):
            try: child.terminate()
            except psutil.NoSuchProcess: pass
        process.terminate()
    except psutil.NoSuchProcess:
        pass


def run_stem(stem, plan, folder):
    category = stem['category']; output = folder/(category+'.wav')
    record = folder/(category+'.json'); log = folder/(category+'.log')
    if record.is_file() and output.is_file():
        existing = json.loads(record.read_text(encoding='utf-8'))
        if (existing.get('plan_sha256') == plan_hash(plan)
                and existing.get('prompt') == stem['prompt']
                and existing.get('seed') == stem['seed']
                and existing.get('sha256') == digest(output)):
            return existing
    preflight = memory_budget(psutil.virtual_memory().available)
    if not preflight['can_start']:
        raise RuntimeError(f"Medium needs {START_AVAILABLE_GIB:g} GiB available RAM; "
            f"currently {preflight['available_gib']:.2f} GiB. No generation started; completed stages are retained.")
    command = [str(BASE/'.venv'/'Scripts'/'python.exe'),
        str(BASE/'stable-audio-3'/'optimized'/'tflite'/'scripts'/'sa3_tflite.py'),
        '--dit', 'medium', '--decoder', 'same-l', '--dit-precision', 'w8a8',
        '--decoder-precision', 'w8a8', '--seconds', '30', '--steps', '8',
        '--seed', str(stem['seed']), '--cfg', '1', '--threads', '8',
        '--prompt', stem['prompt'], '--out', str(output)]
    start = time.perf_counter(); peak_rss = 0; low_samples = 0
    minimum_available = psutil.virtual_memory().available
    print('Generating scene '+plan['cache_key'][:12]+' / '+category, flush=True)
    with log.open('w', encoding='utf-8') as stream:
        child = subprocess.Popen(command, cwd=BASE/'stable-audio-3'/'optimized'/'tflite',
            stdout=stream, stderr=subprocess.STDOUT, env=os.environ.copy())
        process = psutil.Process(child.pid)
        try:
            while child.poll() is None:
                try:
                    family = [process]+process.children(recursive=True)
                    peak_rss = max(peak_rss, sum(p.memory_info().rss for p in family if p.is_running()))
                    available = psutil.virtual_memory().available
                    minimum_available = min(minimum_available, available)
                    low_samples = low_samples+1 if available < RUNTIME_RESERVE_GIB*1024**3 else 0
                    if low_samples >= 5 or time.perf_counter()-start > 240:
                        stop_own_process(process)
                        raise RuntimeError('Stopped own generator to preserve system memory or timeout.')
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(.2)
        except BaseException:
            stop_own_process(process)
            child.wait(timeout=15)
            raise
    if child.returncode:
        raise RuntimeError('Scene generation failed: '+log.read_text(encoding='utf-8', errors='replace')[-2000:])
    audio, sr = sf.read(output, always_2d=True)
    if sr != 44100 or audio.shape != (30*sr, 2) or not np.isfinite(audio).all():
        raise ValueError('Invalid generated scene waveform')
    rms = float(np.sqrt(np.mean(audio**2))); peak = float(np.max(np.abs(audio)))
    if rms < 1e-5 or peak >= .9999:
        raise ValueError('Generated scene audio is silent or has clipped samples')
    text = log.read_text(encoding='utf-8', errors='replace')
    cli_time = re.search(r'done\s+(\d+(?:\.\d+)?)s wall', text)
    result = {**stem, 'id': plan['cache_key']+'_'+category,
        'cache_key': plan['cache_key'], 'image_sha256_rgb': plan['image_sha256_rgb'],
        'plan_sha256': plan_hash(plan), 'scene_specific': True,
        'model': 'Stable Audio 3 Medium', 'model_repo': 'stabilityai/stable-audio-3-optimized',
        'model_revision': MODEL_REVISION, 'code_repository': 'https://github.com/Stability-AI/stable-audio-3',
        'code_revision': CODE_REVISION, 'runtime': 'official native Windows LiteRT/TFLite CPU',
        'device': 'CPU / XNNPACK, Intel i9-14900HX', 'threads': 8,
        'dit_family': 'medium', 'dit_precision': 'w8a8', 'decoder': 'SAME-L w8a8',
        'steps': 8, 'cfg': 1., 'negative_prompt_requested': stem.get('negative_prompt'),
        'negative_prompt': None, 'negative_prompt_note': 'CFG=1 does not use a negative branch; exclusions in positive prompt are not a guarantee.',
        'wav': str(output), 'actual_duration_seconds': len(audio)/sr,
        'sample_rate': sr, 'channels': 2, 'rms': rms, 'peak': peak,
        'clipped_sample_count': int((np.abs(audio)>=.9999).sum()), 'sha256': digest(output),
        'wall_seconds_including_process_start': round(time.perf_counter()-start, 3),
        'official_cli_wall_seconds': float(cli_time.group(1)) if cli_time else None,
        'peak_process_tree_rss_mb': round(peak_rss/1024**2, 1),
        'memory_preflight': preflight,
        'minimum_system_available_gib': round(minimum_available/1024**3, 3),
        'runtime_reserve_gib': RUNTIME_RESERVE_GIB,
        'globally_serialized_model_worker': True, 'log': str(log),
        'ai_generated': True, 'pictured_site_recording': False, 'subjectively_auditioned': False,
        'all_inference_local': True, 'model_license': 'Stable Audio Community License; includes Gemma components',
        'created_utc': datetime.now(timezone.utc).isoformat()}
    write_json(record, result)
    print(json.dumps({'category': category, 'seconds': result['wall_seconds_including_process_start'],
        'sha256': result['sha256']}, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path); parser.add_argument('--cleanup-pid', type=int)
    args = parser.parse_args()
    if args.cleanup_pid is not None:
        try:
            process = psutil.Process(args.cleanup_pid)
            command = process.cmdline()
            if str(Path(__file__).resolve()) not in command or str(args.plan.resolve()) not in command:
                raise RuntimeError('Cleanup refused: worker command/plan does not match.')
            stop_own_process(process)
            try: process.wait(timeout=10)
            except psutil.TimeoutExpired: process.kill()
        except psutil.NoSuchProcess:
            pass
        lock = BASE/'.scene_generator.lock'
        try:
            owner = json.loads(lock.read_text(encoding='utf-8'))
            if owner.get('pid') == args.cleanup_pid: lock.unlink(missing_ok=True)
        except (OSError, ValueError): pass
        return
    if args.output_dir is None:
        parser.error('--output-dir is required for generation')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if not re.fullmatch(r'[a-f0-9]{64}', plan.get('cache_key', '')):
        raise ValueError('Invalid scene cache key')
    model = plan.get('model')
    if model is not None and (model.get('revision') != MODEL_REVISION or model.get('seconds') != 30
            or model.get('steps') != 8 or model.get('cfg') != 1 or model.get('id') != 'stable-audio-3'
            or model.get('dit') != 'medium' or model.get('decoder') != 'same-l' or model.get('precision') != 'w8a8'):
        raise ValueError('Plan/model runtime mismatch')
    weights = json.loads((BASE/'weights_manifest.json').read_text(encoding='utf-8'))
    if weights.get('revision') != MODEL_REVISION or weights.get('repo_id') != 'stabilityai/stable-audio-3-optimized':
        raise ValueError('Deployed weights differ from the fixed runtime revision')
    folder = args.output_dir.resolve()
    expected = (ROOT/'assets'/'scene_generated'/plan['cache_key']/'raw').resolve()
    if folder != expected:
        raise ValueError('Output must remain in this scene cache raw directory')
    stems = plan.get('stems', plan.get('items', []))
    if not stems or len(stems)>3 or any(x.get('category') not in GENERATED_CATEGORIES for x in stems):
        raise ValueError('No supported scene stems')
    folder.mkdir(parents=True, exist_ok=True)
    # Serialize all Medium CLI jobs across scenes to avoid multiplying RAM use.
    lock = BASE/'.scene_generator.lock'
    try:
        fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError('Another scene generator is running; retry after it finishes.') from exc
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps({'pid': os.getpid(), 'started_utc': datetime.now(timezone.utc).isoformat()}))
        items = [run_stem(stem, plan, folder) for stem in stems]
        write_json(folder/'manifest.json', {'schema_version': 1, 'scene_specific': True,
            'cache_key': plan['cache_key'], 'image_sha256_rgb': plan['image_sha256_rgb'],
            'plan_sha256': plan_hash(plan), 'model_repo': 'stabilityai/stable-audio-3-optimized',
            'model_revision': MODEL_REVISION, 'items': items})
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
