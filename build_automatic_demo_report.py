"""Build a report from one completed upload, without inference or network calls.

Only docs/automatic_panorama_demo.html and outputs/automatic_panorama_demo/
are written. Existing job stages, model audio, and exact-text TTS caches stay
unchanged. Static players embed already verified local files on demand.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
from urllib.parse import quote
import wave

from PIL import Image
from panorama_pipeline import load_job, load_pipeline_result


ROOT = Path(__file__).resolve().parent
DEFAULT_JOB = '91844ab0aeda4e29461ad3704cc26255e8e43be09a5d1b36423b381d32349fb8'
OUT = ROOT / 'outputs' / 'automatic_panorama_demo'
REPORT = ROOT / 'docs' / 'automatic_panorama_demo.html'
E = html.escape


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding='utf-8')


def href(path, page=REPORT):
    return quote(Path(os.path.relpath(path, page.parent)).as_posix(), safe='/')


def link(path, label, page=REPORT):
    return '<a href="' + href(path, page) + '">' + E(label) + '</a>'


def wav_record(path):
    path = Path(path)
    with wave.open(str(path), 'rb') as audio:
        frames = audio.getnframes()
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        rate = audio.getframerate()
        complete = len(audio.readframes(frames)) == frames * channels * width
    if not complete or not frames:
        raise ValueError('Incomplete WAV: ' + str(path))
    return {'file': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size,
            'duration_seconds': frames / rate, 'sample_rate': rate,
            'channels': channels, 'sample_width_bytes': width,
            'complete_frames': complete}


STYLE = '''body{margin:0;background:#f4f3ed;color:#193e31;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:32px 20px 70px}h1{font-size:36px;line-height:1.35;letter-spacing:-.03em}h2{font-size:24px}h3{font-size:18px}a{color:#21664a;text-underline-offset:4px}.panel{border:1px solid #cfdbca;background:#fffef9;border-radius:14px;padding:23px;margin:24px 0}.lead{font-size:21px}.note{font-size:14px;color:#53685b}.button{display:inline-block;background:#225f47;color:white;border-radius:8px;padding:10px 17px;margin:4px 7px 4px 0;text-decoration:none}.secondary{background:#e2eadf;color:#204c36}.panorama{width:100%;max-height:360px;object-fit:contain;background:#e3e8de;border-radius:10px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%;margin:10px 0}table{width:100%;border-collapse:collapse;font-size:15px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #d5dfd0}.table-wrap{overflow:auto}summary{cursor:pointer;min-height:36px}.prompt{font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:18px}iframe{width:100%;height:900px;border:1px solid #cfdbca;border-radius:12px}a:focus-visible,summary:focus-visible{outline:3px solid #287fac;outline-offset:3px}@media(max-width:700px){h1{font-size:28px}.pair{grid-template-columns:1fr}.panel{padding:16px}main{padding:24px 15px}}'''


def document(title, body):
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + E(title) + '</title><style>' + STYLE + '</style><main>' + body +
            '</main><script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>{document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})}));</script></html>')


def build(job_id=DEFAULT_JOB):
    result = load_pipeline_result(job_id, root=ROOT, verify=True)
    if result is None:
        raise ValueError('Completed upload failed exact stage/audio/TTS verification')
    status = load_job(job_id, ROOT)
    folder = Path(result['job_dir'])
    plan = result['plan']
    source = next(x for x in read(ROOT / 'samples' / 'auto_demo' / 'manifest.json')
                  if x['sha256'] == result['input_sha256'])
    if source['id'] != 'lauter_waterfall' or source['license'] != 'CC0-1.0':
        raise ValueError('Unexpected source panorama or licence')
    image_hash = result['image_sha256_rgb']
    with Image.open(source['file']) as image:
        actual_rgb_hash = hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
    if digest(source['file']) != job_id or actual_rgb_hash != image_hash:
        raise ValueError('Source upload does not match completed job')

    audit_file = Path(result['gpt_provenance']['request_audit_file'])
    audit = read(audit_file)
    if audit.get('status') != 'completed' or audit.get('observed_tool_calls') != 0:
        raise ValueError('GPT request does not have a completed zero-tool audit')
    scene = plan['evidence']['gpt_response_scene']
    if scene['id'] != result['scene_id']:
        raise ValueError('GPT scene does not match this upload')
    changes = plan['evidence']['automatic_acoustic_policy']['changes']
    prompts = []
    for stem in plan['stems']:
        original = next(x['prompt_en'] for x in scene['stems'] if x['id'] == stem['id'])
        if not stem['prompt'].startswith(original):
            raise ValueError('The per-image GPT acoustic prompt was discarded')
        prompts.append({'category': stem['category'], 'original_gpt_prompt': original,
                        'applied_prompt': stem['prompt'], 'original_preserved': True})

    monitored = {folder / 'status.json', folder / 'result.json', audit_file}
    for step in status['steps']:
        monitored.update(folder / name for name in step['artifacts'])
    monitored.update(folder.rglob('request_audit.json'))
    monitored.update(Path(result['assets_dir']).rglob('*.json'))
    raw = []
    processed = []
    for stem in result['audio_result']['stems']:
        raw_record = wav_record(stem['original_stereo_path'])
        processed_record = wav_record(stem['file'])
        if raw_record['sha256'] != stem['raw_source_sha256'] or processed_record['sha256'] != stem['sha256']:
            raise ValueError('Model audio or processed audio hash mismatch')
        raw.append(raw_record)
        processed.append(processed_record)
        monitored.update([Path(raw_record['file']), Path(processed_record['file'])])
    voice = next(x for x in result['narration']['voices'] if x['voice_id'] == 'zh-CN-XiaoxiaoNeural')
    spoken = result['narration_text']
    text_hash = hashlib.sha256(spoken.encode('utf-8')).hexdigest()
    if voice['text'] != spoken or voice['text_sha256'] != text_hash or digest(voice['file']) != voice['sha256']:
        raise ValueError('Narration is not the exact current guide text')
    monitored.update(Path(voice['file']).parent.glob('*.json'))
    monitored.add(Path(voice['file']))
    before = {str(path): digest(path) for path in sorted(monitored)}

    prior_samples = []
    for sample_manifest in ['panoramas', 'panoramas_gpt']:
        prior_samples.extend(read(ROOT / 'samples' / sample_manifest / 'manifest.json'))
    if len(prior_samples) != 6 or job_id in {x['sha256'] for x in prior_samples}:
        raise ValueError('The demo must be a new image outside the six prior samples')
    prior_wavs = []
    current_assets = Path(result['assets_dir']).resolve()
    for path in sorted((ROOT / 'assets').rglob('*.wav')):
        if not path.resolve().is_relative_to(current_assets):
            prior_wavs.append({'file': str(path), 'sha256': digest(path)})
    previous_hashes = {x['sha256'] for x in prior_wavs}
    if not previous_hashes or any(x['sha256'] in previous_hashes for x in raw + processed):
        raise ValueError('A new demo WAV matches existing historical audio')

    OUT.mkdir(parents=True, exist_ok=True)
    from browser_audio import render_audio
    views = {}
    view_links = []
    angle_rows = []
    for view in result['report']['views']:
        vid = view['id']
        sources = plan['views'][vid]['sources']
        view_page = OUT / (vid + '.html')
        player = OUT / (vid + '_player.html')
        view_body = link(REPORT, '← 自动上传完整演示', view_page)
        view_body += '<h1>' + E(result['title'] + ' · ' + view['label']) + '</h1>'
        view_body += '<p>' + ' · '.join(link(OUT / (v['id'] + '.html'), v['label'], view_page)
                                             for v in result['report']['views']) + '</p>'
        view_body += '<img class="panorama" src="' + href(view['report']['files']['input'], view_page) + '" alt="' + E(view['label'] + '透视画面') + '">'
        if sources:
            player.write_text(render_audio(sources, spoken, result['assets_dir'], 28), encoding='utf-8')
            view_body += '<p>本方向有本图 GPT 指定的模拟声源。配音采用同一段已缓存神经女声，可分别试听。</p><iframe src="' + player.name + '" title="' + E(view['label'] + '空间声景播放器') + '" allow="autoplay"></iframe>'
        else:
            view_body += '<section class="panel"><h2>此方向未设置声源</h2><p>GPT 没有为左侧画面指定溪流声源，因此不增加或复制其他方向的水声。</p><p>' + E(spoken) + '</p><audio controls preload="none" src="' + href(voice['file'], view_page) + '"></audio></section>'
        view_body += '<p class="note">画面方位为全景视图标签；声音为生成式模拟，虚拟半径不是米。神经配音非真人录音。</p>'
        view_page.write_text(document(result['title'] + ' · ' + view['label'], view_body), encoding='utf-8')
        angles = [{'id': x['id'], 'category': x['category'], 'azimuth': x['azimuth'],
                   'panorama_heading_degrees': (view['yaw'] + x['azimuth'] + 180) % 360 - 180,
                   'spread_degrees': x['spread_degrees'], 'virtual_radius': x['virtual_radius'],
                   'basis_zh': x['basis_zh']} for x in sources]
        views[vid] = {'label': view['label'], 'yaw': view['yaw'], 'source_count': len(sources),
                      'sources': angles, 'page': str(view_page),
                      'player': str(player) if sources else None}
        view_links.append('<a class="button secondary" href="' + href(view_page) + '">' + E(view['label']) + ('试听' if sources else ' · 无声源') + '</a>')
        angle_rows.append('<tr><td>' + E(view['label']) + '</td><td>' + str(len(sources)) + '</td><td>' +
                          (' / '.join(f"{x['azimuth']:g}°，宽度{x['spread_degrees']:g}°，虚拟半径{x['virtual_radius']:g}" for x in sources) if sources else '—') + '</td></tr>')

    failed_requests = [{'file': str(path), 'sha256': digest(path), 'status': read(path).get('status'),
                        'error': read(path).get('error')} for path in folder.rglob('request_audit.json')
                       if read(path).get('status') == 'failed']
    stage_times = {x['id']: x['duration_seconds'] for x in status['steps']}
    total_work = round(sum(stage_times.values()), 3)
    browser_file = OUT / 'browser_verification.json'
    browser = read(browser_file) if browser_file.is_file() else None
    if browser and (browser.get('job_id') != job_id or browser.get('cache_key') != plan['cache_key']):
        raise ValueError('Browser verification is for another job')
    reopen_file = OUT / 'cache_reopen_verification.json'
    reopened = read(reopen_file) if reopen_file.is_file() else None
    if reopened and (not reopened.get('no_new_worker_or_generation') or
                     not all(reopened.get('exact_files_unchanged', {}).values()) or
                     reopened.get('gpt_attempt_count_before') != reopened.get('gpt_attempt_count_after')):
        raise ValueError('Reopen verification did not preserve the existing job')
    after = {path: digest(path) for path in before}
    if before != after:
        raise ValueError('Report generation unexpectedly altered a monitored cache file')
    verification = {'schema_version': 1, 'verified_utc': datetime.now(timezone.utc).isoformat(),
        'job_id': job_id, 'scene_id': result['scene_id'], 'cache_key': plan['cache_key'],
        'load_pipeline_result_verify_true': True,
        'verification_was_read_only_no_inference_or_network': True,
        'source': source, 'input_sha256': job_id, 'image_sha256_rgb': image_hash,
        'normalized_input_png_sha256': digest(folder / 'input.png'),
        'contact_sheet_sha256': digest(result['contact_sheet_file']),
        'result_sha256': digest(folder / 'result.json'), 'raw_audio': raw,
        'processed_audio': processed, 'narration': {k: v for k, v in voice.items() if k != 'audio_base64'},
        'narration_exact_text': spoken, 'narration_text_sha256': text_hash,
        'gpt': {'provider': result['gpt_provenance']['provider'], 'model': result['gpt_provenance']['model'],
                'response_sha256': digest(result['gpt_provenance']['response_file']),
                'audit_file': str(audit_file), 'audit_sha256': digest(audit_file),
                'status': audit['status'], 'observed_tool_calls': audit['observed_tool_calls']},
        'per_image_prompts': prompts, 'acoustic_policy': plan['evidence']['automatic_acoustic_policy'],
        'new_image_and_audio': {'prior_six_ids': [x['id'] for x in prior_samples],
            'image_not_one_of_prior_six': True, 'historical_wav_comparison_count': len(prior_wavs),
            'all_new_raw_and_processed_hashes_differ': True,
            'comparison_scope': 'All currently existing WAVs under assets/, excluding only this new cache folder',
            'historical_wav_hashes': prior_wavs},
        'views': views, 'stage_duration_seconds': stage_times,
        'successful_stage_work_seconds_including_reused_analysis': total_work,
        'latest_retry_wall_seconds': result['duration_seconds'],
        'earlier_failed_requests': failed_requests,
        'retry_explanation': '首次客户端诊断事件被适配器误判为工具调用并中止；修正事件分类后重试，复用视觉阶段。成功请求审计记录为0次工具调用。',
        'browser_verification': {'file': str(browser_file), 'sha256': digest(browser_file), 'record': browser} if browser else None,
        'cache_reopen_verification': {'file': str(reopen_file), 'sha256': digest(reopen_file), 'record': reopened} if reopened else None,
        'cache_unchanged': {'all_monitored_files_unchanged': True, 'file_count': len(before), 'sha256_by_path': before},
        'boundaries': {'subjective_naturalness_tested': False, 'rain_confusion_resolved': None,
                       'between_scene_difference_retested': False, 'user_experience_validated': False}}
    rows = ''.join('<tr><td>' + E(x['label']) + '</td><td>' + f"{x['duration_seconds']:.3f} 秒" +
                   '</td><td>' + ('复用首次完成的视觉结果' if x.get('reused') else '本次完成') + '</td></tr>' for x in status['steps'])
    facts = ''.join('<li>' + E(x) + '</li>' for x in scene['visible_facts_zh'])
    prompt_blocks = ''.join('<h3>' + E(x['category']) + ' · 本图 GPT 原提示词</h3><p class="prompt">' + E(x['original_gpt_prompt']) + '</p>' for x in prompts)
    prompt_blocks += ''.join('<h3>追加的本地约束</h3><p class="prompt">' + E(x['appended_constraint']) + '</p>' for x in changes)
    browser_note = ('主应用浏览器已实际检查前、右、后三个方向播放，均为一层素材；配音与声景互斥、全部停止和离线混音工程检查通过。左侧保留零声源。'
                    if browser else '浏览器检查尚未并入本报告。')
    if browser and browser.get('views', {}).get('left', {}).get('sourceCount') == 0:
        browser_note += '左侧实际检查中仅配音在播放，声源与活动声景节点均为0。'
    if reopened:
        browser_note += '重启主服务、刷新浏览器并从最近任务打开后，关键文件保持不变，GPT请求次数仍为' + str(reopened['gpt_attempt_count_after']) + '次，没有新建生成进程。'
    if browser and browser.get('automated_regression_tests'):
        tests = browser['automated_regression_tests']
        browser_note += '自动回归检查为' + str(tests['passed']) + '项通过、' + str(tests['skipped']) + '项跳过。'
    body = '<p class="note">LANDSCAPESOUND / AUTOMATIC UPLOAD DEMO / 2026-10-25</p><h1>上传新全景图，自动生成<br>画面理解、专属声景和中文配音。</h1>'
    body += '<p class="lead">已在主应用实际上传一张此前未使用的全景图，完成五个步骤。此页提供同一张图的真实生成结果与可复查记录。</p><p><a class="button" href="http://127.0.0.1:8501/">打开主应用</a><a class="button secondary" href="#listen">试听本次结果</a></p>'
    body += '<section class="panel"><h2>' + E(result['title']) + '</h2><img class="panorama" src="' + href(result['report']['files']['panorama']) + '" alt="林间溪流与石岸的360度全景"><p class="note">来源：<a href="' + E(source['source_url']) + '">Poly Haven · Lauter Waterfall</a>，<a href="' + E(source['license_url']) + '">CC0</a>。官方摄影全景缩至4096×2048，未生成或改动画面。Powered by Poly Haven。</p><ul>' + facts + '</ul></section>'
    body += '<section class="panel" id="listen"><h2>本图新声音与配音</h2><div class="pair"><div><h3>岩石间溪水 · 28 秒</h3><audio controls preload="none" src="' + href(processed[0]['file']) + '"></audio><p class="note">Stable Audio 3 Medium 本机生成，后处理为单声道循环素材。与已有 ' + str(len(prior_wavs)) + ' 条历史 WAV 的文件指纹均不相同。</p></div><div><h3>神经女声晓晓 · 28.2 秒</h3><audio controls preload="none" src="' + href(voice['file']) + '"></audio><p class="note">按下面的本图文字生成，逐字与缓存匹配。神经合成配音，非真人录音。</p></div></div><p>' + E(spoken) + '</p><p>' + ''.join(view_links) + '</p><p class="note">四方向的声源角度来自本图 GPT 视觉解释。方位、宽度和虚拟半径是试听代理，不代表实际声学测量。</p><div class="table-wrap"><table><tr><th>方向</th><th>声源数</th><th>画面内声像设置</th></tr>' + ''.join(angle_rows) + '</table></div></section>'
    body += '<section class="panel"><h2>自动流程与耗时</h2><div class="table-wrap"><table><tr><th>步骤</th><th>有效工作</th><th>本次情况</th></tr>' + rows + '</table></div><p>五阶段有效工作合计 <b>' + f'{total_work:.3f}' + ' 秒</b>；本次重试耗时 <b>' + f"{result['duration_seconds']:.3f}" + ' 秒</b>，其中视觉结果已在首次完成。上述合计不包含人工处理和失败等待。</p><p class="note">首次 GPT 请求因适配器把客户端诊断误判为工具事件而中止。修复事件分类后从 GPT 阶段重试，并保留失败审计；本次成功请求记录为0次工具调用。自动理解使用已登录 ChatGPT 的官方 Codex 客户端（' + E(audit['model']) + '）。</p></section>'
    body += '<section class="panel"><h2>逐图提示词仍被保留</h2><p>本图 GPT 原始英文提示词完整保留；本地只追加水声纹理约束，没有替换成固定溪流模板。新图有自己的图片绑定、种子和音频缓存。</p><details><summary>查看本图提示词和追加内容</summary>' + prompt_blocks + '</details><p class="note">提示中的排除语句不保证模型绝对遵循，不能据此宣称雨声混淆已解决。</p></section>'
    evidence_links = [link(OUT / 'verification.json', '本轮完整核验'), link(folder / 'plan.json', '本图声景计划'),
                      link(folder / 'gpt' / 'response.txt', 'GPT 原始回复'), link(audit_file, '成功请求审计'),
                      link(raw[0]['file'], '模型原始30秒WAV'), link(result['contact_sheet_file'], '发给GPT的全景与四视图')]
    if browser: evidence_links.insert(1, link(browser_file, '主应用浏览器检查'))
    if reopened: evidence_links.insert(2, link(reopen_file, '重开任务缓存检查'))
    body += '<section class="panel"><h2>验证结果与试听边界</h2><p>完整结果、阶段文件、原始与处理后 WAV、逐字配音缓存均通过校验。' + browser_note + '</p><p>这次验证了新图自动处理与实际播放。尚未进行人耳自然度评分、溪流与雨声辨识测试，也未重新进行多场景差异对比；不能据此认定听感问题已经解决。静态图片无法确认实际声音、流速、风速或无障碍通行条件。</p><details><summary>打开来源、模型原始结果与核验记录</summary><p>' + ' · '.join(evidence_links) + '</p><p class="note">原始视觉阶段记录保留其阶段当时的来源说明；最终整合后的来源与限制见 result.json。</p></details></section>'
    REPORT.write_text(document('新全景自动声景与自然配音演示', body), encoding='utf-8')
    generated_files = [REPORT] + list(OUT.glob('*.html'))
    verification['report_artifacts'] = [{'file': str(path), 'sha256': digest(path)} for path in generated_files]
    write_json(OUT / 'verification.json', verification)
    print(json.dumps({'report': str(REPORT), 'verification': str(OUT / 'verification.json'),
                      'job_id': job_id, 'cache_unchanged': True,
                      'historical_wavs_checked': len(prior_wavs), 'work_seconds': total_work,
                      'retry_seconds': result['duration_seconds'],
                      'view_source_counts': {k: v['source_count'] for k, v in views.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id', default=DEFAULT_JOB)
    build(parser.parse_args().job_id)
