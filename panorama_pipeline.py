"""Durable upload → GPT vision → local sound → neural narration workflow.

Reading job state never calls a model or sends data. A run is explicit, each
completed stage is checksum-bound, and failed runs resume without substituting
local rules for a missing GPT reply. Distances remain visual rendering proxies.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
PIPELINE_VERSION = 'automatic-panorama-v1'
ACOUSTIC_POLICY_VERSION = 'image-specific-water-traffic-constraints-v2'
DEFAULT_VOICE = 'zh-CN-XiaoxiaoNeural'
STEPS = [('analysis', '分析全景与四个方向'), ('gpt', 'GPT 理解画面'),
         ('plan', '整理声景与中文导览'), ('audio', '生成本图声景'),
         ('narration', '生成自然配音')]
STREAM_CONSTRAINT = (
    'Keep the described water scale and rhythm: continuous irregular liquid movement, '
    'with falling water only where described; avoid rain-on-leaves ticks and a uniform '
    'broadband rain curtain.'
)
TRAFFIC_CONSTRAINT = (
    'Keep the described traffic rhythm and distance, with distinct engine and rolling-tire '
    'events separated in time rather than a generic broadband noise bed.'
)


class PipelineCancelled(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    try:
        # Windows briefly denies replacing a file held by a polling reader or
        # indexer. Keep the previous complete JSON readable and retry the same
        # atomic replacement; never expose a partially written status file.
        for attempt in range(20):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(min(.02 * (attempt + 1), .1))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except PermissionError:
            pass


def job_id_for(image_bytes):
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError('需要有效的全景图片文件。')
    return hashlib.sha256(image_bytes).hexdigest()


def job_dir(job_id, root=None):
    if not isinstance(job_id, str) or len(job_id) != 64 or any(c not in '0123456789abcdef' for c in job_id):
        raise ValueError('Invalid panorama job identity')
    return Path(root or ROOT).resolve() / 'outputs' / 'auto_panorama' / job_id


def load_job(job_id, root=None):
    """Read durable progress only; no inference, network, or browser operation."""
    return _read(job_dir(job_id, root) / 'status.json')


def request_cancel(job_id, root=None):
    folder = job_dir(job_id, root); folder.mkdir(parents=True, exist_ok=True)
    _write(folder / 'cancel.request', {'requested_utc': _now()})


def clear_cancellation(job_id, root=None):
    (job_dir(job_id, root) / 'cancel.request').unlink(missing_ok=True)


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) is not a safe process probe on Windows.
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # An inaccessible owner is not proven dead.
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def _lock(folder):
    path = folder / '.job.lock'
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        owner = _read(path)
        young = time.time() - path.stat().st_mtime < 10
        if (owner and _alive(owner.get('pid'))) or (not owner and young):
            raise RuntimeError('这张全景正在处理，请查看当前进度。')
        path.unlink(missing_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'started_utc': _now()}, stream)
        yield
    finally:
        owner = _read(path)
        if owner and owner.get('pid') == os.getpid():
            path.unlink(missing_ok=True)


def _decode(image_bytes):
    if len(image_bytes) > 45_000_000:
        raise ValueError('全景文件过大，请使用45MB以内的图片。')
    with Image.open(io.BytesIO(image_bytes)) as opened:
        if opened.width * opened.height > 50_000_000:
            raise ValueError('请将全景缩小至5000万像素以内。')
        image = ImageOps.exif_transpose(opened).convert('RGB')
    if abs(image.width / image.height - 2.) > .04:
        raise ValueError('需要完整的2:1等距柱状全景。普通宽幅照片不能只凭比例当作360°全景。')
    image.thumbnail((4096, 2048), Image.Resampling.LANCZOS)
    return image


def _contact_sheet(image, scene_id, destination):
    from panorama import perspective_view
    sheet = Image.new('RGB', (2048, 1600), '#f5f4ee')
    draw = ImageDraw.Draw(sheet)
    def font(size):
        try:return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
        except OSError:return ImageFont.load_default()
    draw.text((50, 12), scene_id + ' | full 360 x 180 ERP and four 90-degree views', fill='#193e31', font=font(27))
    preview = image.copy(); preview.thumbnail((1948, 974), Image.Resampling.LANCZOS)
    sheet.paste(preview, ((2048-preview.width)//2, 62))
    draw.text((50, 1030), 'ERP centre = front 0 deg; seam = back 180 deg. Not geographic north.', fill='#193e31', font=font(23))
    for index, (view_id, yaw) in enumerate([('front', 0), ('right', 90), ('back', 180), ('left', -90)]):
        x = index * 512
        draw.text((x + 7, 1065), f'{view_id} / yaw {yaw} deg', fill='#193e31', font=font(23))
        sheet.paste(perspective_view(image, yaw_degrees=yaw, pitch_degrees=0, hfov=90, size=500), (x+6, 1097))
    sheet.save(destination, quality=93)


def build_vision_prompt(scene_id):
    """One schema-bound request for the current upload; no old scene names."""
    return f'''请仅根据附图理解一张360°全景。scene id必须是 {scene_id}。上方是完整ERP，下方为front(0°)、right(90°)、back(180°)、left(-90°)四个90°透视图；以图上标签为准，不代表地理方向。
生成图像驱动景观预体验的声音计划。visible_facts_zh只写看得到的事实；uncertainties_zh写静态图片不能确认的事项。风、水动、车流、响度和实际声源距离均不能从静态图测得。停放车辆不证明有车流。任何动态声音都是simulation_assumptions_zh中的设计设想，不自动添加鸟、虫、讲话、雨、脚步、音乐、泵或不可见活动。
每图1到2条必要主音轨，category只允许surf（海浪）、stream（溪流/细小跌水）、traffic（明确假设性稀疏远处车辆）、wind（风）、trees（叶片）、water（微浪），同图类别不得重复。一条音轨只表达一个类别。prompt_en为30到90个英文词，正向写声学纹理、疏密、时间变化和间隙，不堆物体名或禁止事件。溪流强调连接的液体流动、低圆咕噜和石间水道，少用密集滴点、嘶嘶、细碎均匀拍打等容易像雨的措辞。海浪用慢涌起落和沙面退水；道路是稀疏引擎/轮胎通过并有长安静间隔，且承认只是模拟。
views仅列有对应视觉依据的方向。azimuth是各90°画面内-45..45度，spread_degrees为0..40，virtual_radius为1.8..7.8试听设定、不是米；basis_zh解释方位和不确定性。relative_level为0..1（主轨通常0.7），不是现场声压。narration_zh写约90–140汉字自然口语导览，只用可见事实，可简短提示声音是模拟，不朗读技术清单，不虚构地点身份和活动。
只返回完整JSON，不要Markdown、解释或代码。结构必须为：
{{"schema_version":1,"scenes":[{{"id":"{scene_id}","visible_facts_zh":["可见事实"],"uncertainties_zh":["不能确认的事项"],"narration_zh":"中文导览", "stems":[{{"id":"primary","category":"stream","label_zh":"岩石间流水","visual_evidence_zh":["图中证据"],"simulation_assumptions_zh":["低强度动态为模拟"],"prompt_en":"A detailed English audio prompt of thirty to ninety words.","relative_level":0.7,"views":[{{"view_id":"right","azimuth":0,"spread_degrees":16,"virtual_radius":3.5,"basis_zh":"依据与不确定性"}}]}}]}}]}}
不得输出种子、图片hash或声称已经生成/听过音频。'''


def _default_vision(image_file, prompt, output_dir):
    from gpt_cli_bridge import analyze_panorama_with_gpt
    return analyze_panorama_with_gpt(image_file, prompt, output_dir)


def _default_services():
    def analyze(image, output, title):
        # Let Torch/CUDA and its visual model objects disappear with a child
        # process before the CPU audio model checks its RAM headroom.
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        input_file=output.parent/'input.png'
        image.save(input_file)
        command=[sys.executable,str(Path(__file__).resolve()),'--input',str(input_file),
            '--title',title,'--analysis-only','--analysis-output',str(output)]
        options={'cwd':str(ROOT),'stdout':subprocess.PIPE,'stderr':subprocess.STDOUT,
                 'text':True,'encoding':'utf-8','errors':'replace','timeout':300,'check':False}
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
        completed=subprocess.run(command,**options)
        (output.parent/'analysis_worker.log').write_text(completed.stdout or '',encoding='utf-8')
        report=_read(output/'report.json')
        if completed.returncode or report is None:
            raise RuntimeError('全景视觉分析未完成。'+(completed.stdout or '')[-1500:])
        return report
    def generate(plan, root):
        from scene_audio_runtime import ensure_scene_audio
        return ensure_scene_audio(plan, root=root)
    def load_audio(plan, root):
        from scene_audio_runtime import load_scene_audio
        return load_scene_audio(plan, root=root)
    def narrate(text, voices, root):
        from narration import ensure_narration
        return ensure_narration(text, voices=voices, root=root)
    def load_narration(text, root):
        from narration import get_narration_assets
        return get_narration_assets(text, root=root)
    return dict(analyze=analyze, generate_audio=generate, load_audio=load_audio,
                narrate=narrate, load_narration=load_narration)


def _artifacts(folder, paths):
    result = {}
    for value in paths:
        path = Path(value).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise ValueError('Pipeline artifact is missing or outside this job')
        result[path.relative_to(folder).as_posix()] = _digest(path)
    return result


def _valid_stage(folder, record, signature):
    if not isinstance(record, dict) or record.get('status') != 'complete' or record.get('signature') != signature:
        return False
    try:
        for name, expected in record['artifacts'].items():
            path = (folder/name).resolve()
            if not path.is_relative_to(folder.resolve()) or _digest(path) != expected:return False
        return bool(record['artifacts'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _compact_narration(value):
    result = copy.deepcopy(value)
    for item in result.get('voices', []):item.pop('audio_base64', None)
    return result


def apply_acoustic_policy(plan):
    result = copy.deepcopy(plan); changes=[]
    for stem in result['stems']:
        category = stem['category']
        constraint = STREAM_CONSTRAINT if category == 'stream' else TRAFFIC_CONSTRAINT if category == 'traffic' else None
        if constraint is not None:
            original = stem['prompt']
            applied = original + ' ' + constraint
            changes.append({'category': category, 'original_gpt_prompt': original,
                'appended_constraint': constraint, 'applied_prompt': applied,
                'original_gpt_prompt_preserved': True})
            stem['prompt'] = applied
            stem['prompt_source'] = 'local_acoustic_policy_after_gpt'
            # A new upload keeps its own image-dependent seed and fresh cache;
            # policy reuse is text policy reuse, never a previous scene WAV.
    result['condition'] = 'automatic_gpt_with_acoustic_policy'
    result['evidence']['automatic_acoustic_policy'] = {'version': ACOUSTIC_POLICY_VERSION,
        'changes': changes, 'source': 'Image-specific GPT prompts with appended local acoustic constraints',
        'new_image_audio_generation': True, 'not_unmodified_gpt_prompt': bool(changes)}
    result['items'] = copy.deepcopy(result['stems'])
    result.pop('cache_key', None);result['cache_key'] = _hash(result)
    return result


def _guide(scene, image_hash):
    text = scene.get('narration_zh')
    generated = isinstance(text, str) and 40 <= len(text.strip()) <= 450
    if generated:
        text = text.strip()
    else:
        facts = scene['visible_facts_zh']
        text = ''.join(facts[:3])
        if len(text) > 300:text = ''.join(facts[:2])
        text += '这是依据全景图片设计的模拟声景。'
    return {'scene_id': scene['id'], 'image_sha256_rgb': image_hash, 'text': text,
        'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'provenance': {'method': 'GPT short spoken guide' if generated else 'Conservative concatenation of GPT visible facts',
                       'motion_and_sound_are_simulation_assumptions': True}}


def run_pipeline(image_bytes, title='我的全景图', root=None, vision_client=None,
                 progress=None, cancel=None, narration_voices=None, services=None, vision_identity=None):
    """Run or resume all five stages; tests may inject light, explicit services.

    ``vision_client(contact_sheet, prompt, job_gpt_dir)`` returns a dictionary
    with ``response_text`` and truthful ``provenance``. It must not return a
    synthetic local-rule fallback on a failed GPT request.
    """
    root = Path(root or ROOT).resolve(); identifier = job_id_for(image_bytes)
    folder = job_dir(identifier, root);folder.mkdir(parents=True, exist_ok=True)
    svc = _default_services();svc.update(services or {})
    voices = list(narration_voices or [DEFAULT_VOICE])
    vision = vision_client or _default_vision
    bridge_file = root/'gpt_cli_bridge.py'
    identity = vision_identity or {'adapter': vision.__module__+'.'+vision.__qualname__,
        'bridge_sha256': _digest(bridge_file) if bridge_file.is_file() and vision_client is None else None}
    with _lock(folder):
        run_started = time.perf_counter()
        old = load_job(identifier, root) or {}
        records = {x['id']: x for x in old.get('steps', []) if isinstance(x, dict) and x.get('id')}
        state = {'schema_version': 1, 'pipeline_version': PIPELINE_VERSION, 'job_id': identifier,
            'title': str(title), 'status': 'running', 'current_step': 1, 'message': '正在准备全景…',
            'created_utc': old.get('created_utc', _now()), 'started_utc': _now(), 'updated_utc': _now(),
            'worker_pid': os.getpid(), 'result_file': str(folder/'result.json'), 'steps': [], 'error': None}
        for sid, label in STEPS:
            state['steps'].append(records.get(sid, {'id': sid, 'label': label, 'status': 'pending'}))
        step_started = {}
        def publish():
            state['updated_utc'] = _now();_write(folder/'status.json', state)
            if progress:progress(copy.deepcopy(state))
        def cancelled():
            if (folder/'cancel.request').is_file() or (cancel is not None and cancel()):
                raise PipelineCancelled('处理已取消。已完成的步骤保留，可以重试继续。')
        def start(index, signature, message):
            cancelled();state['current_step'] = index+1;state['message'] = message
            step_started[index] = time.perf_counter()
            record = state['steps'][index]
            valid = _valid_stage(folder, record, signature)
            if not valid:
                record.update(status='running', signature=signature, started_utc=_now(), reused=False)
                record.pop('artifacts', None)
            else:record['reused'] = True
            publish();return valid
        def finish(index, signature, paths):
            state['steps'][index].update(status='complete', signature=signature,
                artifacts=_artifacts(folder, paths), completed_utc=_now(),
                duration_seconds=round(time.perf_counter()-step_started[index], 3))
            publish();cancelled()
        publish()
        try:
            image = _decode(image_bytes); image_hash = hashlib.sha256(image.tobytes()).hexdigest()
            scene_id = 'upload_'+identifier[:12]
            prepared = folder/'input.png';sheet = folder/'gpt_input.jpg';report_path = folder/'analysis'/'report.json'
            prepare_sig = _hash({'version': PIPELINE_VERSION, 'input_sha256': identifier,
                'image_sha256_rgb': image_hash, 'working_size': list(image.size), 'title': str(title)})
            if not start(0, prepare_sig, '正在分析全景与四个方向…'):
                (folder/'upload.bin').write_bytes(image_bytes)
                image.save(prepared)
                report = svc['analyze'](image.copy(), folder/'analysis', str(title))
                if report.get('input', {}).get('sha256_rgb') != image_hash:
                    raise ValueError('视觉分析与当前全景图片指纹不匹配。')
                _write(report_path, report)
                _contact_sheet(image, scene_id, sheet)
                paths = [prepared, sheet, report_path]
                for view in report.get('views', []):
                    paths.extend(view['report']['files'][x] for x in ('input', 'segmentation', 'depth'))
                finish(0, prepare_sig, paths)
            report = _read(report_path)
            if not report or report.get('input', {}).get('sha256_rgb') != image_hash:
                raise ValueError('已保存的视觉分析不属于这张图片。')
            prompt = build_vision_prompt(scene_id);gpt_folder = folder/'gpt';gpt_folder.mkdir(exist_ok=True)
            raw_path = gpt_folder/'response.txt';source_path = gpt_folder/'provenance.json';request_path = gpt_folder/'request.txt'
            vision_sig = _hash({'prepare': prepare_sig, 'report_sha256': _digest(report_path),
                'contact_sheet_sha256': _digest(sheet), 'request': prompt, 'adapter': identity})
            if not start(1, vision_sig, '正在让 GPT 理解这张全景…'):
                request_path.write_text(prompt, encoding='utf-8')
                answer = vision(sheet, prompt, gpt_folder)
                if not isinstance(answer, dict) or not isinstance(answer.get('response_text'), str):
                    raise ValueError('GPT入口没有返回完整文字回复，未改用本地规则。')
                raw_path.write_text(answer['response_text'], encoding='utf-8')
                provenance = copy.deepcopy(answer.get('provenance') or {})
                provenance.update(image_sha256_rgb=image_hash, response_file=str(raw_path),
                    response_sha256=_digest(raw_path), contact_sheet_file=str(sheet),
                    contact_sheet_sha256=_digest(sheet), request_file=str(request_path), request_sha256=_digest(request_path))
                from gpt_scene_audio import parse_gpt_audio_response
                parse_gpt_audio_response(answer['response_text'], expected_scene_ids=[scene_id])
                _write(source_path, provenance)
                finish(1, vision_sig, [raw_path, source_path, request_path])
            from gpt_scene_audio import parse_gpt_audio_response, build_gpt_panorama_audio_plan
            from scene_audio_plan import MODEL
            parsed = parse_gpt_audio_response(raw_path.read_text(encoding='utf-8'), expected_scene_ids=[scene_id])
            scene = parsed['scenes'][0];provenance = _read(source_path)
            plan_path = folder/'plan.json';guide_path = folder/'narration_guide.json'
            plan_sig = _hash({'response': _digest(raw_path), 'source': _digest(source_path),
                'model': MODEL, 'policy': ACOUSTIC_POLICY_VERSION})
            if not start(2, plan_sig, '正在整理声景提示与中文导览…'):
                plan = apply_acoustic_policy(build_gpt_panorama_audio_plan(report, scene, provenance))
                guide = _guide(scene, image_hash)
                _write(plan_path, plan);_write(guide_path, guide)
                finish(2, plan_sig, [plan_path, guide_path])
            plan = _read(plan_path);guide = _read(guide_path)
            audio_path = folder/'audio_result.json'
            audio_sig = _hash({'plan_sha256': _digest(plan_path), 'runtime': 'scene-audio-runtime-1'})
            audio_cache = svc['load_audio'](plan, root)
            audio_stage = start(3, audio_sig, '正在本机生成这张全景的声音…')
            if not audio_stage or audio_cache is None:
                state['steps'][3].update(reused=False, status='running')
                state['steps'][3].pop('artifacts', None);publish()
                audio_result = svc['generate_audio'](plan, root)
                if not audio_result or not audio_result.get('assets_dir'):
                    raise ValueError('专属声音未生成完成，未套用通用素材。')
                _write(audio_path, audio_result)
                finish(3, audio_sig, [audio_path])
            audio_result = _read(audio_path)
            narration_path = folder/'narration_result.json'
            narration_sig = _hash({'guide': _digest(guide_path), 'voices': voices,
                                  'version': 'microsoft-edge-neural-1', 'rate': '-3%', 'pitch': '+0Hz'})
            current_narration = svc['load_narration'](guide['text'], root)
            narration_stage = start(4, narration_sig, '正在生成自然中文配音…')
            ready = {x['voice_id'] for x in (current_narration or {}).get('voices', [])}
            if not narration_stage or not set(voices).issubset(ready):
                state['steps'][4].update(reused=False, status='running')
                state['steps'][4].pop('artifacts', None);publish()
                spoken = svc['narrate'](guide['text'], voices, root)
                if not set(voices).issubset({x['voice_id'] for x in (spoken or {}).get('voices', [])}):
                    raise ValueError('自然配音未生成完成，未改用系统旧声。')
                _write(narration_path, _compact_narration(spoken))
                finish(4, narration_sig, [narration_path])
            narration = _read(narration_path)
            cancelled()
            final_report = copy.deepcopy(report)
            final_report['original_visual_report_path'] = str(report_path)
            final_report['limitations'] = [x for x in report.get('limitations', [])
                if not x.startswith('No panoramic GPT description')
                and not x.startswith('Stereo HRTF and procedural illustrative')]
            final_report['limitations'].extend([
                'GPT image interpretation is recorded separately from the original local semantic/depth estimates.',
                'Sound is generated for this exact image and remains a simulation, not a recording of the pictured location.',
                'Chinese narration is cached neural speech, not a human field recording; no user-perception effectiveness is established.'])
            final_report['pipeline_completion'] = {'gpt_provider': provenance.get('provider'),
                'gpt_response_sha256': provenance['response_sha256'], 'plan_cache_key': plan['cache_key'],
                'neural_voice_ids': voices, 'local_visual_report_preserved': True}
            result = {'schema_version': 1, 'pipeline_version': PIPELINE_VERSION, 'job_id': identifier,
                'status': 'complete', 'title': str(title), 'scene_id': scene_id, 'image_sha256_rgb': image_hash,
                'input_sha256': identifier, 'report_path': str(report_path), 'report': final_report,
                'plan_path': str(plan_path), 'plan': plan, 'audio_result': audio_result,
                'assets_dir': audio_result['assets_dir'], 'gpt_provenance': provenance,
                'narration_text': guide['text'], 'narration_guide': guide, 'narration': narration,
                'requested_voice_ids': voices, 'job_dir': str(folder), 'contact_sheet_file': str(sheet),
                'result_file': str(folder/'result.json'), 'completed_utc': _now(),
                'duration_seconds': round(time.perf_counter()-run_started, 3),
                'stage_duration_seconds': {x['id']: x.get('duration_seconds') for x in state['steps']},
                'reused_steps': [x['id'] for x in state['steps'] if x.get('reused')],
                'boundaries': ['GPT image understanding is a separate recorded inference, never a local-rule fallback.',
                    'Sound dynamics and virtual acoustic positions are simulation assumptions, not field measurements.',
                    'Visual report is the original local model analysis; GPT-derived sources do not silently overwrite it.']}
            _write(folder/'result.json', result)
            state.update(status='complete', message='全景理解、专属声景和自然配音已完成。', error=None,
                         result_sha256=_digest(folder/'result.json'))
            publish();return result
        except BaseException as exc:
            state.update(status='cancelled' if isinstance(exc, PipelineCancelled) else 'failed',
                message=str(exc), error={'type': type(exc).__name__, 'message': str(exc)})
            if 1 <= state.get('current_step', 0) <= 5:
                record = state['steps'][state['current_step']-1]
                if record.get('status') != 'complete':record['status'] = state['status']
            publish();raise


def load_pipeline_result(job_id, root=None, verify=True):
    folder = job_dir(job_id, root);status = load_job(job_id, root)
    if not status or status.get('status') != 'complete':return None
    path = folder/'result.json';result = _read(path)
    if not result or result.get('job_id') != job_id or result.get('status') != 'complete':return None
    if not verify:return result
    try:
        if _digest(path) != status.get('result_sha256'):return None
        if not all(_valid_stage(folder, x, x.get('signature')) for x in status['steps']):return None
        from scene_audio_runtime import load_scene_audio
        from narration import get_narration_assets
        if load_scene_audio(result['plan'], root=root) is None:return None
        cached = get_narration_assets(result['narration_text'], root=root)
        if not set(result['requested_voice_ids']).issubset({x['voice_id'] for x in cached['voices']}):return None
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--title', default='我的全景图')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--voice', action='append', default=None)
    parser.add_argument('--analysis-only', action='store_true')
    parser.add_argument('--analysis-output', type=Path)
    args = parser.parse_args()
    image_bytes = args.input.read_bytes()
    if args.analysis_only:
        if args.analysis_output is None:parser.error('--analysis-output is required with --analysis-only')
        os.environ.setdefault('HF_HUB_OFFLINE','1')
        from analyze_panorama import analyze_panorama
        image=_decode(image_bytes)
        report=analyze_panorama(image,args.analysis_output,title=args.title)
        print(report['report_path'],flush=True)
        return
    def progress(state):
        print(json.dumps({'status': state['status'], 'current_step': state['current_step'],
            'message': state['message'], 'job_id': state['job_id']}, ensure_ascii=False), flush=True)
    run_pipeline(image_bytes, title=args.title, root=args.root,
                 progress=progress, narration_voices=args.voice)


if __name__ == '__main__':
    main()
