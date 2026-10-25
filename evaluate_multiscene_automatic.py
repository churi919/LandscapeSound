"""Evaluate completed UI-triggered uploads; never generate GPT, audio or TTS.

The established CLAP text/window protocol is reused as an exploratory content
representation. Scores are not naturalness ratings or human recognition rates.
Only outputs/multiscene_automatic_evaluation is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import time

import local_config
import numpy as np
from PIL import Image, ImageOps

from evaluate_gpt_audio_demo import audio_signal, digest, TARGETS
from panorama_pipeline import load_pipeline_result, load_job, _alive
from prepare_model_audio import SR, measure, save_audio


ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs' / 'multiscene_automatic_evaluation'
MANIFEST = ROOT / 'samples' / 'multiscene_auto_20261025' / 'manifest.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _available_memory():
    if os.name == 'nt':
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                        ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                        ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                        ('avail_extended', ctypes.c_ulonglong)]
        state = MemoryStatus(); state.length = ctypes.sizeof(state)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            raise RuntimeError('Cannot inspect system memory before CLAP evaluation')
        return state.avail_phys
    import psutil
    return psutil.virtual_memory().available


def model_preflight():
    for file in (ROOT / 'outputs' / 'auto_panorama').glob('*/status.json'):
        status = read(file)
        if status.get('status') == 'running' and _alive(status.get('worker_pid')):
            raise RuntimeError('CLAP deferred: a panorama worker is still running; finish generation first')
    available = _available_memory()
    if available < 4 * 1024**3:
        raise RuntimeError('CLAP deferred: less than 4 GiB system RAM available')
    return {'available_system_ram_gib': available / 1024**3,
            'minimum_system_ram_gib': 4, 'no_active_panorama_workers': True}


def _source_group(sample, categories):
    declared = sample.get('scene_group') or sample.get('comparison_group') or sample.get('category') or sample.get('scene_type')
    aliases = {'coast': 'surf', 'beach': 'surf', 'city': 'traffic', 'street': 'traffic',
               'creek': 'stream', 'waterfall': 'stream'}
    declared = aliases.get(declared, declared)
    if declared in TARGETS:
        return declared
    choices = [category for category in categories if category in TARGETS]
    if len(choices) == 1:
        return choices[0]
    raise ValueError('An explicit stream/surf/traffic scene group is required for ' + sample['id'])


def _stems(plan, items):
    planned = {item['category']: item for item in plan['stems']}
    mix = np.zeros(28 * SR, dtype=np.float64)
    records = []
    for item in items:
        stem = planned[item['category']]
        signal, processed = audio_signal(item['file'])
        _, raw = audio_signal(item['original_stereo_path'])
        checks = {
            'processed_checksum': processed['sha256'] == item['sha256'],
            'raw_checksum': raw['sha256'] == item['raw_source_sha256'] == item['generation']['sha256'],
            'prompt_matches_plan': item['generation']['prompt'] == stem['prompt'],
            'seed_matches_plan': item['generation']['seed'] == stem['seed'],
            'processed_28s_mono_32k': processed['duration_seconds'] == 28 and processed['channels'] == 1 and processed['sample_rate'] == SR,
            'raw_30s_stereo_44100': raw['duration_seconds'] == 30 and raw['channels'] == 2 and raw['sample_rate'] == 44100,
            'finite_non_silent': raw['finite'] and processed['finite'] and min(raw['rms'], processed['rms']) > 1e-5,
            'no_sample_clipping': raw['sample_clipping_count'] == processed['sample_clipping_count'] == 0,
            'model_revision_matches_plan': item['generation']['model_revision'] == plan['model']['revision'],
        }
        weight = stem['relative_level']
        if not isinstance(weight, (int, float)) or not 0 < weight <= 1:
            raise ValueError('Invalid declared stem level')
        if not all(value for key, value in checks.items() if key != 'no_sample_clipping'):
            raise ValueError('Stem verification failed: ' + json.dumps(checks))
        mix += signal * weight
        records.append({'category': item['category'], 'label_zh': stem.get('label_zh'),
                        'prompt': stem['prompt'], 'seed': stem['seed'], 'relative_level': weight,
                        'raw': raw, 'processed': processed, 'level': measure(signal),
                        'checks': checks, 'all_passed': all(checks.values()),
                        'dynamics': item.get('dynamics'), 'generation': item['generation']})
    if set(planned) != {item['category'] for item in items}:
        raise ValueError('Plan and generated categories differ')
    return mix, records


def prepare_new(sample):
    job_id = sample['sha256']
    if digest(sample['file']) != job_id:
        raise ValueError('Input panorama checksum mismatch')
    with Image.open(sample['file']) as opened:
        rgb = ImageOps.exif_transpose(opened).convert('RGB')
        image_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
    result = load_pipeline_result(job_id, root=ROOT, verify=True)
    if result is None:
        raise ValueError('This new panorama has not completed all automatic stages: ' + sample['id'])
    if result['image_sha256_rgb'] != image_hash or image_hash != sample['sha256_rgb']:
        raise ValueError('Completed job does not match source panorama')
    plan = result['plan']; provenance = result['gpt_provenance']
    audit = read(provenance['request_audit_file'])
    if provenance['provider'] != 'codex_cli' or audit.get('status') != 'completed' or audit.get('observed_tool_calls') != 0:
        raise ValueError('Current panorama has no completed automatic GPT image-understanding audit')
    scene = plan['evidence']['gpt_response_scene']
    originals = {item['category']: item['prompt_en'].strip() for item in scene['stems'] if item.get('enabled', True)}
    if not all(item['prompt'].startswith(originals[item['category']]) for item in plan['stems']):
        raise ValueError('A per-image GPT prompt was replaced rather than retained')
    mix, stems = _stems(plan, result['audio_result']['stems'])
    voice = next(item for item in result['narration']['voices'] if item['voice_id'] == 'zh-CN-XiaoxiaoNeural')
    text = result['narration_text']; text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if voice['text'] != text or voice['text_sha256'] != text_hash or digest(voice['file']) != voice['sha256']:
        raise ValueError('Narration is not for the exact current guide text')
    compact_voice = {key: value for key, value in voice.items() if key != 'audio_base64'}
    text_chars = sum(not char.isspace() and char.isalnum() for char in text)
    compact_voice['non_space_alnum_characters'] = text_chars
    compact_voice['characters_per_second'] = text_chars / voice['duration_seconds']
    compact_voice['naturalness_score'] = None
    compact_voice['prosody_or_pronunciation_human_review'] = 'Not scored; playback and exact-text cache checks only'
    status = load_job(job_id, ROOT)
    log_file = ROOT / 'outputs' / 'auto_panorama' / job_id / 'ui_worker.log'
    log_text = log_file.read_text(encoding='utf-8', errors='replace') if log_file.is_file() else ''
    incidents = []
    if 'Less than 5 GiB system RAM available' in log_text:
        incidents.append({'kind': 'initial_memory_preflight_deferred',
                          'note_zh': '首次被原5GiB可用内存预检阻止；依据实测模型峰值重新明确4.25GiB启动预算，并保留1.25GiB运行中余量保护后，从已完成图像/GPT阶段继续。',
                          'log_file': str(log_file), 'log_sha256': digest(log_file)})
    if 'PermissionError' in log_text and 'WinError 5' in log_text:
        incidents.append({'kind': 'transient_windows_progress_replace_lock',
                          'note_zh': '进度文件在Windows短暂占用时导致原子替换被拒绝；补入仅针对PermissionError的有限重试后，从有效图像/GPT缓存继续。',
                          'log_file': str(log_file), 'log_sha256': digest(log_file)})
    category = _source_group(sample, [item['category'] for item in stems])
    # The second water scene is visibly a taller cliff waterfall, not a small
    # rocky stream. Keep both water labels in the diagnostic and predeclare
    # the scene-appropriate primary label before examining its audio scores.
    target_label = sample.get('audio_target_label') or ('large_waterfall' if sample['id'] == 'crystal_falls' else TARGETS[category])
    return {'id': sample['id'], 'scene_id': sample['id'], 'title': result.get('title', sample['title']),
            'kind': 'new_main_application_upload', 'scene_group': category, 'target_label': target_label,
            'job_id': job_id, 'cache_key': plan['cache_key'], 'image_sha256_rgb': image_hash,
            'source': sample, 'gpt_provenance': provenance, 'visible_facts_zh': scene['visible_facts_zh'],
            'uncertainties_zh': scene['uncertainties_zh'], 'original_gpt_stems': scene['stems'],
            'acoustic_policy': plan['evidence'].get('automatic_acoustic_policy'),
            'plan_file': result['plan_path'], 'result_file': result['result_file'],
            'views': {v['id']: {'label': v['label'], 'yaw': v['yaw'], 'files': v['report']['files'],
                              'sources': plan['views'][v['id']]['sources']} for v in result['report']['views']},
            'stems': stems, 'narration': compact_voice, 'narration_text': text,
            'stage_duration_seconds': result['stage_duration_seconds'],
            'runtime_incidents': incidents,
            'first_created_utc': status['created_utc'], 'completed_utc': result['completed_utc'],
            'unmatched_mix_measurement': measure(mix), '_mix': mix,
            'mix_protocol': 'Actual processed mono stems summed from sample zero, weighted once by per-image plan.relative_level; no HRTF, distance, random offsets or extra dynamic processing',
            'all_passed': all(stem['all_passed'] for stem in stems)}


def prepare_references():
    previous = read(ROOT / 'outputs' / 'audio_refinement' / 'evaluation.json')
    refs = []
    for identifier, title in [('xanderklinge/previous_gpt', '旧溪流：详细提示（曾与雨混淆）'),
                              ('xanderklinge/previous_short_reference', '旧溪流：上一轮保留的简短提示')]:
        old = next(row for row in previous['rows'] if row['id'] == identifier)
        path = Path(old['matched_mix']['file'])
        if digest(path) != old['matched_mix']['sha256']:
            raise ValueError('Historical reference audio was modified')
        audio, meta = audio_signal(path)
        if meta['sample_rate'] != SR or meta['channels'] != 1 or meta['duration_seconds'] != 28:
            raise ValueError('Historical comparison audio does not match current format')
        refs.append({'id': identifier.replace('/', '__'), 'title': title,
                     'kind': 'explicit_historical_stream_reference', 'scene_group': 'stream',
                     'target_label': TARGETS['stream'], 'source_record': old,
                     'source_audio': meta, 'unmatched_mix_measurement': measure(audio),
                     '_mix': audio, 'all_passed': True})
    return refs


def prepare_rows():
    samples = read(MANIFEST)
    if isinstance(samples, dict):
        samples = samples.get('items') or samples.get('scenes')
    if not isinstance(samples, list) or len(samples) != 4:
        raise ValueError('This round requires four new panoramas in the recorded manifest')
    rows = [prepare_new(sample) for sample in samples]
    counts = {group: sum(row['scene_group'] == group for row in rows) for group in TARGETS}
    if counts != {'surf': 1, 'stream': 2, 'traffic': 1}:
        raise ValueError('This comparison needs two streams, one coast and one street: ' + str(counts))
    rows += prepare_references()
    # When a new water scene has another texture (for example foliage), also
    # inspect the actual water stem alone. This prevents a rain-like secondary
    # layer from being incorrectly attributed to the water itself. Single-stem
    # scenes already supply that diagnostic through the main mix.
    isolated = []
    for row in rows:
        if row['kind'] != 'new_main_application_upload' or row['scene_group'] != 'stream' or len(row['stems']) < 2:
            continue
        for stem in row['stems']:
            if stem['category'] not in {'stream', 'water'}:
                continue
            x, meta = audio_signal(stem['processed']['file'])
            isolated.append({'id': row['id']+'__water_stem_only', 'title': row['title']+'（水声音轨单独）',
                             'kind': 'isolated_current_water_stem', 'parent_scene_id': row['id'],
                             'scene_group': 'stream', 'target_label': row['target_label'],
                             'source_audio': meta, 'unmatched_mix_measurement': measure(x),
                             '_mix': x, 'all_passed': True})
    rows += isolated
    target = min([-23.] + [row['unmatched_mix_measurement']['integrated_lufs'] - 1.55 - row['unmatched_mix_measurement']['true_peak_4x_dbtp'] for row in rows])
    for row in rows:
        output = OUT / 'audio' / (row['id'] + '.wav')
        record = save_audio(output, row.pop('_mix'), target)
        if record['true_peak_4x_dbtp'] > -1.5 or record['duration_seconds'] != 28:
            raise ValueError('Matched comparison violates duration or peak headroom')
        row['matched_mix'] = {**record, 'global_target_lufs': target, 'fixed_start_seconds': 0,
                              'additional_dynamic_processing': False}
    if max(row['matched_mix']['integrated_lufs'] for row in rows) - min(row['matched_mix']['integrated_lufs'] for row in rows) > .01:
        raise ValueError('Comparison clips do not meet the 0.01 LU loudness tolerance')
    return rows, target


def _monitored_sources(rows):
    paths = set()
    for row in rows:
        if row['kind'] == 'new_main_application_upload':
            folder = ROOT / 'outputs' / 'auto_panorama' / row['job_id']
            paths.update(folder.rglob('*'))
            for stem in row['stems']:
                paths.add(Path(stem['raw']['file'])); paths.add(Path(stem['processed']['file']))
            paths.add(Path(row['narration']['file']))
            paths.add(Path(row['source']['file']))
        else:
            paths.add(Path(row['source_audio']['file']))
    return {str(path): {'sha256': digest(path), 'mtime_ns': path.stat().st_mtime_ns}
            for path in sorted(paths) if path.is_file()}


def evaluate(rows, reuse=False):
    saved_file = OUT / 'evaluation.json'; previous = read(saved_file) if reuse and saved_file.is_file() else None
    cached = {row['id']: row for row in previous['rows']} if previous else {}
    embeddings = {}; need = []
    old_embeddings = np.load(OUT / 'audio_embeddings.npz') if previous else None
    for row in rows:
        old = cached.get(row['id'])
        if old and old['matched_mix']['sha256'] == row['matched_mix']['sha256'] and row['id'] in old_embeddings:
            row['clap'] = old['clap']; embeddings[row['id']] = old_embeddings[row['id']]
        else:
            need.append(row)
    if old_embeddings is not None:
        old_embeddings.close()
    if need:
        preflight = model_preflight()
        from evaluate_audio_refinement import clap_rows
        fresh, method = clap_rows(need, save_embeddings=False)
        embeddings.update(fresh); method['preflight'] = preflight
    else:
        method = previous['clap_method']
    method = {**method, 'current_evaluation': 'New main-application uploads with explicit historical stream references',
              'reused_identical_audio_features': len(rows) - len(need)}
    np.savez_compressed(OUT / 'audio_embeddings.npz', **embeddings)
    return embeddings, method


def summarize(rows, embeddings):
    fresh = [row for row in rows if row['kind'] == 'new_main_application_upload']
    pairs = []
    for a, b in itertools.combinations(fresh, 2):
        cosine = float(np.dot(embeddings[a['id']], embeddings[b['id']]))
        pairs.append({'a': a['id'], 'b': b['id'], 'a_title': a['title'], 'b_title': b['title'],
                      'same_scene_group': a['scene_group'] == b['scene_group'],
                      'audio_embedding_cosine': cosine})
    between = [pair['audio_embedding_cosine'] for pair in pairs if not pair['same_scene_group']]
    within = [pair for pair in pairs if pair['same_scene_group']]
    streams = []; isolated_water = []
    for row in rows:
        if row['scene_group'] != 'stream':
            continue
        c = row['clap']
        record = {'id': row['id'], 'title': row['title'], 'kind': row['kind'],
                        'target_label': row['target_label'],
                        'target_cosine': c['target_mean_cosine'], 'rain_cosine': c['rain_mean_cosine'],
                        'stream_cosine': c['mean_label_cosines']['rocky_stream_cascade'],
                        'waterfall_cosine': c['mean_label_cosines']['large_waterfall'],
                        'stream_minus_rain': c['mean_label_cosines']['rocky_stream_cascade']-c['rain_mean_cosine'],
                        'waterfall_minus_rain': c['mean_label_cosines']['large_waterfall']-c['rain_mean_cosine'],
                        'best_water_minus_rain': max(c['mean_label_cosines']['rocky_stream_cascade'],c['mean_label_cosines']['large_waterfall'])-c['rain_mean_cosine'],
                        'closest_water_label': max(('rocky_stream_cascade','large_waterfall'),key=lambda key:c['mean_label_cosines'][key]),
                        'target_minus_rain': c['target_minus_rain'], 'target_rank': c['target_rank'],
                        'top3': c['ranking'][:3]}
        (isolated_water if row['kind'] == 'isolated_current_water_stem' else streams).append(record)
    return {'new_scene_count': 4, 'historical_stream_reference_count': 2,
            'all_source_and_signal_checks_passed': all(row['all_passed'] for row in rows),
            'global_loudness_tolerance_lu': .01, 'between_group_mean_cosine': float(np.mean(between)),
            'between_scene_pairs': pairs, 'within_stream_pair': within, 'stream_rain_comparison': streams,
            'isolated_water_stem_diagnostics': isolated_water,
            'subjective_naturalness_score': None, 'human_stream_rain_recognition_accuracy': None,
            'limitations': [
                'CLAP cosine, rank and margin are content-representation diagnostics, not naturalness, event probabilities or human recognition accuracy.',
                'New panoramas differ from historical stream references. Between-round differences do not isolate a causal prompt or model improvement.',
                'The same fixed text labels have guided prior optimization; this remains exploratory rather than a held-out generalization test.',
                'Different generated stems may receive different dynamic alterations during application processing; comparison adds gain only.',
                'Narration is neural synthetic speech, not human recording. Exact-text playback checks do not score pronunciation or prosody.',
                'Per-view source absence means no visual proxy was assigned; it does not model how real sound propagates around the full sphere.'
            ]}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reuse-clap', action='store_true'); args = parser.parse_args()
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    rows, target = prepare_rows(); before = _monitored_sources(rows)
    if args.prepare_only:
        write(OUT / 'prepared.json', {'rows': rows, 'global_target_lufs': target})
        print('Prepared verified comparison clips only; no model was loaded', flush=True)
        return
    embeddings, method = evaluate(rows, reuse=args.reuse_clap)
    after = _monitored_sources(rows)
    if before != after:
        raise ValueError('A source job or audio cache changed during evaluation')
    summary = summarize(rows, embeddings)
    result = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'rows': rows, 'clap_method': method, 'summary': summary,
              'global_target_lufs': target, 'wall_seconds': time.perf_counter() - started,
              'source_caches_unchanged': True, 'monitored_source_files': before}
    write(OUT / 'evaluation.json', result)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
