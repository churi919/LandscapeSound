"""Build the four-scene listening report from already completed evaluations."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import itertools
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote

from evaluate_multiscene_automatic import ROOT, OUT, read, write, digest


REPORT = ROOT / 'docs' / 'multiscene_automatic_evaluation.html'
E = html.escape
LABELS = {'stream': '溪流', 'surf': '海边', 'traffic': '街道'}
TAG_LABELS = {'rocky_stream_cascade': '石间溪流', 'steady_rain': '持续降雨',
              'coastal_surf': '海岸浪声', 'road_vehicle_ambience': '道路车声',
              'large_waterfall': '大型瀑布', 'mechanical_hiss': '机械嘶声',
              'isolated_drips': '孤立滴水', 'tree_leaf_rustling': '树叶摩擦',
              'gentle_wind': '轻风', 'strong_windstorm': '强风', 'birds': '鸟鸣',
              'insects': '虫鸣', 'human_speech': '人声', 'music': '音乐',
              'abrupt_impacts': '突发撞击', 'horns_sirens': '鸣笛/警笛',
              'quiet_lake_ripples': '湖岸微浪'}


def scene_label(row):
    return '岩壁瀑布' if row.get('target_label') == 'large_waterfall' else LABELS[row['scene_group']]


def href(path, page=REPORT):
    return quote(Path(os.path.relpath(path, page.parent)).as_posix(), safe='/')


def link(path, label, page=REPORT, cls=''):
    return '<a class="' + cls + '" href="' + href(path, page) + '">' + E(label) + '</a>'


STYLE = '''
:root{color-scheme:light;--ink:#14283b;--muted:#536575;--line:#d9e2e6;--mint:#236c67;--navy:#102d43;--warm:#f8eedc}
*{box-sizing:border-box}body{margin:0;background:#f4f6f7;color:var(--ink);font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:auto;padding:32px 22px 76px}h1{font-size:42px;line-height:1.25;letter-spacing:-.04em;max-width:880px;margin:14px 0 20px}h2{font-size:27px;letter-spacing:-.025em;margin:8px 0 17px}h3{font-size:20px;margin:8px 0}a{color:#1c656c;text-underline-offset:4px}p{margin:12px 0}button,select,input{font:inherit}button,select,.button{min-height:46px;border-radius:10px;border:1px solid #abc1c7;padding:10px 16px}button{cursor:pointer;background:var(--navy);color:#fff}.button{display:inline-flex;align-items:center;text-decoration:none;background:var(--navy);color:#fff;margin:4px 8px 4px 0}.secondary{background:#e3eeec;color:#184e4c}button:active,.button:active{transform:scale(.98)}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #c27c24;outline-offset:4px}select{width:100%;background:#fff;color:var(--ink)}.hero{padding:35px;background:var(--navy);color:#f7fbfc;border-radius:22px}.eyebrow{font-size:12px;letter-spacing:.14em;font-weight:650;color:#a7d1cf}.hero p{color:#d0e1e7;max-width:830px}.panel{background:white;border:1px solid var(--line);border-radius:18px;padding:26px;margin:26px 0}.callout{background:var(--warm);border:1px solid #e5d7b9;border-radius:12px;padding:16px 19px}.note{color:var(--muted);font-size:14px}.pair,.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px}.sound-panel{background:#f2f6f6;border-radius:12px;padding:18px}audio{display:block;width:100%;margin:14px 0}.reveal-toggle{display:flex;align-items:center;gap:10px;min-height:48px;font-weight:650}.reveal-toggle input{width:21px;height:21px;accent-color:var(--mint)}.scene-card{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}.scene-card img{display:block;width:100%;aspect-ratio:2;object-fit:cover}.scene-card .inside{padding:20px}.tag{display:inline-block;font-size:12px;padding:4px 10px;background:#e1eeeb;color:#1c5856;border-radius:99px}.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.view img{width:100%;display:block;border-radius:9px}.view p{font-size:13px;line-height:1.6}.table-wrap{overflow-x:auto}table{border-collapse:collapse;min-width:650px;width:100%;font-size:15px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:12px 10px}th{font-weight:650;color:#345368}td.number{font-variant-numeric:tabular-nums}.positive{color:#216f64;font-weight:650}.mixed{color:#895e24;font-weight:650}details{margin-top:16px}summary{cursor:pointer;min-height:42px;line-height:1.6;font-weight:600}pre{font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f5;padding:15px;border-radius:10px}.blind .reveal-only{display:none}.blind .reveal-caption::after{content:'先按 A–F 试听，再揭晓图片与结果。'}@media(max-width:750px){main{padding:16px 14px 50px}h1{font-size:30px}.hero{padding:25px}.pair,.cards{grid-template-columns:1fr}.grid4{grid-template-columns:1fr 1fr}.panel{padding:19px}h2{font-size:23px}}@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}button:active,.button:active{transform:none}}'''


SCRIPT = '''
const sounds=Array.from(document.querySelectorAll('audio'));
sounds.forEach(a=>a.addEventListener('play',()=>sounds.forEach(b=>{if(a!==b)b.pause()})));
const reveal=document.getElementById('reveal');if(reveal)reveal.addEventListener('change',()=>{document.body.classList.toggle('blind',!reveal.checked)});
const clips=CLIPS;
for(const side of ['a','b']){const select=document.getElementById('select-'+side),audio=document.getElementById('audio-'+side);if(select&&audio){select.addEventListener('change',()=>{sounds.forEach(a=>a.pause());audio.src=clips[Number(select.value)].url;audio.load()})}}
'''


def document(title, body, *, clips=None, blind=False):
    script = SCRIPT.replace('CLIPS', json.dumps(clips or [], ensure_ascii=False).replace('<', '\\u003c'))
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + E(title) + '</title><style>' + STYLE + '</style><body' +
            (' class="blind"' if blind else '') + '><main>' + body +
            '</main><script>' + script + '</script></body></html>')


def audio(path, page=REPORT):
    return '<audio controls preload="metadata" src="' + href(path, page) + '"></audio>'


def voice_line(row, page):
    n = row['narration']
    return ('<h3>本图自然配音 · 晓晓</h3>' + audio(n['file'], page) +
            '<p>' + E(row['narration_text']) + '</p><p class="note">' +
            f"{n['duration_seconds']:.1f}秒 · 同一自然女声 · 逐字缓存核验通过 · " +
            '神经合成，并非真人录音。语速数值不代表自然度评分。</p>')


def scene_page(row):
    page = OUT / 'scenes' / (row['id'] + '.html'); page.parent.mkdir(parents=True, exist_ok=True)
    body = link(REPORT, '← 返回四场景对比', page, 'button secondary')
    body += '<h1>' + E(row['title']) + '</h1><span class="tag">' + scene_label(row) + ' · 主应用真实上传</span>'
    body += '<section class="panel"><img style="width:100%;border-radius:12px" src="' + href(row['source']['file'], page) + '" alt="' + E(row['title'] + '完整等距柱状全景') + '">'
    author = row['source'].get('author', '')
    if isinstance(author, dict): author = '、'.join(author)
    body += '<p class="note">来源：<a href="' + E(row['source']['source_url']) + '">Poly Haven</a> · ' + E(str(author)) + ' · ' + E(row['source'].get('license', '许可见来源')) + '。图像仅缩放，声音为模拟。</p></section>'
    body += '<section class="panel"><h2>这张图的声音与导览</h2><p>固定起点、单声道、全局等响度的声音内容对照。主应用仍提供各方向的空间试听。</p><h3>本图生成音轨</h3>' + audio(row['matched_mix']['file'], page)
    body += '<p class="note">' + '、'.join(E(stem['label_zh'] or stem['category']) for stem in row['stems']) + '；多轨时按本图设定权重相加，不按四方向重复叠加。</p>'
    body += voice_line(row, page) + '</section>'
    body += '<section class="panel"><h2>四方向画面与声源代理</h2><div class="grid4">'
    for vid, view in row['views'].items():
        proxies = '；'.join(f"{source['category']}：{source['azimuth']:g}°，虚拟半径{source['virtual_radius']:g}" for source in view['sources']) or '没有配置视觉代理声源'
        body += '<div class="view"><img src="' + href(view['files']['input'], page) + '" alt="' + E(view['label'] + '透视画面') + '"><h3>' + E(view['label']) + '</h3><p>' + E(proxies) + '</p></div>'
    body += '</div><p class="note">这些角度和虚拟远近来自 GPT 的图片解释，并非实际声源测量。没有代理源也不等于真实世界这个方向绝对无声。</p></section>'
    body += '<section class="panel"><h2>GPT 看到的内容</h2><ul>' + ''.join('<li>' + E(fact) + '</li>' for fact in row['visible_facts_zh']) + '</ul><details><summary>不确定性、提示词和耗时</summary><ul>'
    body += ''.join('<li>' + E(item) + '</li>' for item in row['uncertainties_zh']) + '</ul>'
    for stem in row['stems']:
        body += '<h3>' + E(stem['label_zh'] or stem['category']) + '</h3><pre>' + E(stem['prompt']) + '</pre>'
    body += '<pre>' + E(json.dumps({'stage_duration_seconds': row['stage_duration_seconds'], 'job_id': row['job_id'], 'cache_key': row['cache_key'], 'narration_sha256': row['narration']['sha256']}, ensure_ascii=False, indent=2)) + '</pre></details></section>'
    review_file = OUT / 'visual_review.json'
    if review_file.is_file():
        review = next((item for item in read(review_file)['items'] if item['id'] == row['id'] and item['job_id'] == row['job_id']), None)
        if review:
            body += '<section class="panel"><h2>画面与文字复核</h2><p>' + E(review['notes_zh']) + '</p><p class="note">由助理对保存的四方向拼图与文字逐项查看；不是标注数据集准确率，也不是人耳听感评分。</p></section>'
    body += '<p><a class="button" href="http://127.0.0.1:8501/">回到主应用试听空间方位</a></p>'
    page.write_text(document(row['title'] + ' · 自动声景与自然配音', body), encoding='utf-8')
    return page


def build():
    data = read(OUT / 'evaluation.json'); rows = data['rows']
    fresh = [row for row in rows if row['kind'] == 'new_main_application_upload']
    if len(fresh) != 4 or not data.get('source_caches_unchanged'):
        raise ValueError('Completed four-scene evaluation is required')
    for row in rows:
        if digest(row['matched_mix']['file']) != row['matched_mix']['sha256']:
            raise ValueError('Matched comparison clip was modified')
    browser_file = OUT / 'browser_verification.json'
    browser = read(browser_file) if browser_file.is_file() else None
    browser_checks = {}
    if browser:
        observed = {item['id']: item for item in browser['items']}
        for row in fresh:
            actual = observed.get(row['id'], {})
            browser_checks[row['id']] = (actual.get('job_id') == row['job_id']
                and actual.get('cache_key') == row['cache_key']
                and actual.get('image_sha256_rgb') == row['image_sha256_rgb']
                and actual.get('narration_sha256') == row['narration']['sha256'])
        for key in ['sound_playing', 'narration_playing', 'sound_stopped_for_narration', 'stop_all']:
            browser_checks[key] = browser['shared_observations_for_each_image'].get(key) is True
        if not all(browser_checks.values()):
            raise ValueError('Actual main-application browser verification does not match evaluated files')
    pages = {row['id']: scene_page(row) for row in fresh}
    # This fixed order is an unlabelled listening aid, not a randomized trial.
    order = [2, 0, 3, 1, 5, 4]
    clips = [{'code': chr(65 + i), 'id': rows[index]['id'], 'url': href(rows[index]['matched_mix']['file'])}
             for i, index in enumerate(order)]
    codes = {item['id']: item['code'] for item in clips}
    options = ''.join('<option value="' + str(i) + '">样本 ' + item['code'] + '</option>' for i, item in enumerate(clips))
    body = '<header class="hero"><div class="eyebrow">LANDSCAPESOUND / LISTENING REVIEW</div><h1>四张新全景，<br>听见不同的场景。</h1><p>一处石间溪流、一处岩壁瀑布、一处海边、一条街道，均从主应用上传并自动完成 GPT 理解、独立声景生成和自然女声导览。这一轮重点听：流水还是雨？</p><a class="button secondary" href="http://127.0.0.1:8501/">打开主应用</a></header>'
    body += '<section class="panel"><h2>先听，再揭晓</h2><div class="callout">建议戴耳机，从较低音量开始。比较水声是否有连续水路与起伏，海浪是否有涌退，街道是否有分开的机械通过声。所有音频切换时自动互停。</div>'
    body += '<p class="note">A–D是本轮新图，E–F是明确保留的旧溪流参照；代码本身不说明场景。这是自助听辨工具，未记录任何人的辨识率。</p><div class="pair">'
    for side, index in [('a', 0), ('b', 1)]:
        opts = options.replace('value="' + str(index) + '"', 'value="' + str(index) + '" selected', 1)
        body += '<div class="sound-panel"><label for="select-' + side + '">试听槽 ' + side.upper() + '</label><select id="select-' + side + '">' + opts + '</select><audio id="audio-' + side + '" controls preload="metadata" src="' + clips[index]['url'] + '"></audio></div>'
    body += '</div><label class="reveal-toggle"><input id="reveal" type="checkbox">揭晓场景、图片与评价</label><p class="note reveal-caption"></p>'
    body += '<div class="reveal-only table-wrap"><table><thead><tr><th>代码</th><th>场景</th><th>来源</th></tr></thead><tbody>'
    for clip in clips:
        row = next(row for row in rows if row['id'] == clip['id'])
        body += '<tr><td>' + clip['code'] + '</td><td>' + E(row['title']) + '</td><td>' + ('本轮主应用新生成' if row['kind'] == 'new_main_application_upload' else '旧溪流参照') + '</td></tr>'
    body += '</tbody></table></div></section>'

    body += '<section class="panel reveal-only"><h2>流水与雨声：本轮结果</h2><p>下表比较同一组文字标签与音频的 CLAP 表征接近度。石间溪流以“溪流”为预定目标，较高岩壁瀑布以“瀑布”为预定目标；同时保留溪流、瀑布、雨三项。正的“目标−雨”差值只表示更接近目标文字，不能证明没有雨感。</p><div class="table-wrap"><table><thead><tr><th>样本</th><th>预定目标</th><th>溪流</th><th>瀑布</th><th>降雨</th><th>目标−雨</th><th>最接近的三类文字</th></tr></thead><tbody>'
    for value in data['summary']['stream_rain_comparison']:
        css = 'positive' if value['target_minus_rain'] > 0 else 'mixed'
        body += '<tr><td>' + codes[value['id']] + ' · ' + E(value['title']) + '</td><td>' + TAG_LABELS[value['target_label']] + '</td><td class="number">' + f"{value['stream_cosine']:.3f}" + '</td><td class="number">' + f"{value['waterfall_cosine']:.3f}" + '</td><td class="number">' + f"{value['rain_cosine']:.3f}" + '</td><td class="number ' + css + '">' + f"{value['target_minus_rain']:+.3f}" + '</td><td>' + '、'.join(TAG_LABELS.get(label, label) for label in value['top3']) + '</td></tr>'
    body += '</tbody></table></div>'
    isolated = data['summary'].get('isolated_water_stem_diagnostics', [])
    if isolated:
        body += '<details><summary>多音轨水景：单独检查水声音轨</summary><p class="note">主表与试听槽使用本图完整混音。若图中还有叶片等音轨，这里只评价实际水声文件，避免把其他层的雨感归到水声。</p><ul>'
        for value in isolated:
            body += '<li>' + E(value['title']) + '：溪流 ' + f"{value['stream_cosine']:.3f}" + '，瀑布 ' + f"{value['waterfall_cosine']:.3f}" + '，雨 ' + f"{value['rain_cosine']:.3f}" + '；目标−雨 ' + f"{value['target_minus_rain']:+.3f}" + '。</li>'
        body += '</ul></details>'
    negative = [value for value in data['summary']['stream_rain_comparison'] if value['kind'] == 'new_main_application_upload' and value['best_water_minus_rain'] <= 0]
    if negative:
        conclusion = '本轮仍有新水景样本在这组标签中更接近降雨；自动内容诊断没有支持“流水雨感已解决”。建议优先试听这些样本：' + '、'.join(codes[value['id']] for value in negative) + '。'
    else:
        conclusion = '两张新水景在溪流/瀑布两类中至少有一项比降雨更接近；这是积极的内容诊断信号，雨感与自然度仍以实际试听为准。瀑布若更接近细溪，应另看水势尺度表达是否不足。'
    body += '<div class="callout">' + E(conclusion) + '</div>'
    for value in data['summary']['stream_rain_comparison']:
        if value['kind'] == 'new_main_application_upload' and value['target_label'] == 'large_waterfall' and value['closest_water_label'] == 'rocky_stream_cascade':
            body += '<p>样本 ' + codes[value['id']] + ' 的表征更接近细溪，溪流相对雨声只高 ' + f"{value['stream_minus_rain']:.3f}" + '；瀑布类别更低，说明还需要听水势尺度是否被弱化，不能只看到“溪流排第一”就认定已经改善。</p>'
    body += '<p class="note">旧溪流与新图的场景不同，数值变化不能单独归因于提示词改善。本轮没有以评价结果挑选或替换新图的音轨。</p></section>'

    body += '<section class="reveal-only"><h2>四个新场景与自然配音</h2><div class="cards">'
    for row in fresh:
        body += '<article class="scene-card"><img loading="lazy" src="' + href(row['source']['file']) + '" alt="' + E(row['title'] + '完整全景') + '"><div class="inside"><span class="tag">样本 ' + codes[row['id']] + ' · ' + scene_label(row) + '</span><h3>' + E(row['title']) + '</h3>'
        body += audio(row['matched_mix']['file']) + '<p>' + E('；'.join(row['visible_facts_zh'][:2])) + '</p>'
        body += '<details><summary>听本图的自然女声导览</summary>' + voice_line(row, REPORT) + '</details>'
        body += link(pages[row['id']], '看四方向、提示词与完整记录', cls='button secondary') + '</div></article>'
    body += '</div></section>'

    body += '<section class="panel reveal-only"><h2>不同场景的声音差异</h2><p>数值越低，表示本模型的音频表征越分开。浅溪与岩壁瀑布是两种流水场景，应与“流水—海岸—街道”的跨类比较分开看；两种流水之间也需要保留各自的水势尺度。</p><div class="table-wrap"><table><thead><tr><th>场景配对</th><th>音频表征相似度</th><th>比较类型</th></tr></thead><tbody>'
    for pair in sorted(data['summary']['between_scene_pairs'], key=lambda p: p['audio_embedding_cosine'], reverse=True):
        body += '<tr><td>' + codes[pair['a']] + ' × ' + codes[pair['b']] + '</td><td class="number">' + f"{pair['audio_embedding_cosine']:.3f}" + '</td><td>' + ('两种流水场景' if pair['same_scene_group'] else '不同场景类别') + '</td></tr>'
    body += '</tbody></table></div><p class="note">新图之间的差异不是与上一轮同图同种子的受控实验；相似度更低也不等于人耳更容易辨别。</p></section>'

    body += '<section class="panel reveal-only"><h2>配音听起来怎样</h2><p>四图均使用晓晓神经女声，每段导览按本图可见内容独立编写。缓存文字、音频指纹与实际时长已核对；没有把语速或播放成功当成自然度评分。</p><p>可以重点听三个方面：句间停顿是否顺畅、景物名是否读清楚、语气是否适合温和导览。旧系统机器人声音没有同文录音，因此这里不冒称公平的新旧配音实验。</p><div class="table-wrap"><table><thead><tr><th>样本</th><th>配音长度</th><th>非空白文字/秒</th><th>检查</th></tr></thead><tbody>'
    for row in fresh:
        n = row['narration']
        body += '<tr><td>' + codes[row['id']] + ' · ' + E(row['title']) + '</td><td>' + f"{n['duration_seconds']:.1f}秒" + '</td><td>' + f"{n['characters_per_second']:.2f}" + '</td><td>本图精确文本与MP3匹配</td></tr>'
    body += '</tbody></table></div></section>'

    body += '<section class="panel reveal-only"><details><summary>本轮自动运行与恢复记录</summary><p>四图经主应用上传后自动完成理解、音效和配音；运行中遇到的问题与恢复过程保留在各任务日志，未把失败隐藏成成功。下表列各阶段记录的有效工作耗时，缓存恢复的阶段沿用原记录，不等于从首次点击到结束的总等待时间。</p>'
    if browser:
        body += '<p>主应用浏览器已实际验证4张新图的声景、自然女声、播放互停与全部停止；每图一个素材层，没有重复堆叠。浏览器观察中的图片、音轨计划和配音指纹与本页逐项一致。</p>'
    body += '<div class="table-wrap"><table><thead><tr><th>样本</th><th>图像</th><th>GPT</th><th>音效</th><th>配音</th></tr></thead><tbody>'
    for row in fresh:
        durations = row['stage_duration_seconds']
        body += '<tr><td>' + codes[row['id']] + '</td>' + ''.join('<td>' + f"{durations[key]:.1f}秒" + '</td>' for key in ['analysis', 'gpt', 'audio', 'narration']) + '</tr>'
    body += '</tbody></table></div><ul>'
    for row in fresh:
        for incident in row.get('runtime_incidents', []):
            body += '<li>' + E(row['title'] + '：' + incident['note_zh']) + '</li>'
    body += '</ul><p class="note">原始图像、GPT回复、计划与生成音轨均独立保留；评价过程中这些源文件的指纹和修改时间没有变化。</p></details></section>'

    body += '<section class="panel reveal-only"><details><summary>查看比较方法、来源与核验</summary><p>本轮与旧参照均为28秒、32kHz单声道，从样本0开始；全组匹配至 ' + f"{data['global_target_lufs']:.3f}" + ' LUFS，组内误差小于0.01 LU，估计真峰值低于−1.5 dBTP。这里仅额外调增益，没有再做动态压缩。主应用空间方位与随机起点不参与本内容对照。</p><p>CLAP使用既有固定模型、17标签/34条文字、三个10秒窗口，全部本地读取；不是现场录音分析。</p><ul>'
    limits_zh = [
        '表征相似度、排名和差值属于内容诊断，不能当作自然度、真实事件概率或人耳辨识率。',
        '新图与旧溪流参照的场景不同，轮次差异不能单独归因于提示词或模型改善。',
        '这组固定文字曾参与前轮优化，本轮仍属于探索性比较，不是独立的用户验证。',
        '应用后处理可能对不同素材产生不同动态调整；本对照只额外匹配增益。',
        '自然配音是神经合成，逐字缓存与播放检查不评价发音准确性或语气自然度。',
        '某方向没有视觉代理源，不等于真实声音不会从其他方向传播过来。']
    body += ''.join('<li>' + E(limit) + '</li>' for limit in limits_zh) + '</ul>'
    body += '<p>原始与处理后音轨信号检查：' + ('全部通过。' if data['summary']['all_source_and_signal_checks_passed'] else '存在需查看的信号项，记录如下。') + '</p><pre>'
    body += E(json.dumps({row['title']: [{'category': stem['category'], 'raw_sample_clipping_count': stem['raw']['sample_clipping_count'], 'processed_sample_clipping_count': stem['processed']['sample_clipping_count'], 'checks': stem['checks']} for stem in row['stems']] for row in fresh}, ensure_ascii=False, indent=2)) + '</pre>'
    body += link(OUT / 'evaluation.json', '完整评价记录 JSON') + ' · ' + link(OUT / 'audio_embeddings.npz', '音频表征文件')
    if browser:
        body += ' · ' + link(browser_file, '主应用实际浏览器播放核验')
    ui_proof_file = ROOT / 'outputs' / 'ui_refinement' / 'browser_verification.json'
    if ui_proof_file.is_file():
        body += ' · ' + link(ui_proof_file, '主界面呈现、上传定位与焦点核验')
    for row in fresh:
        body += '<p>' + E(row['title']) + '：<a href="' + E(row['source']['source_url']) + '">原始全景来源</a> · ' + link(row['result_file'], '自动任务记录') + '</p>'
    body += '</details></section><p class="note reveal-only">生成时间：' + E(datetime.now(timezone.utc).isoformat()) + '。声音均为生成式景观模拟，配音为神经合成；图片不能确定实际响度、流速或通行条件。</p>'
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(document('四场景自动声景与自然配音比较', body, clips=clips, blind=True), encoding='utf-8')

    html_pages = [REPORT, *pages.values()]
    local_links = []
    for page in html_pages:
        for path in re.findall(r'(?:src|href)="([^"]+)"', page.read_text(encoding='utf-8')):
            if path.startswith(('http:', 'https:', '#', 'data:')):
                continue
            target = (page.parent / unquote(path.split('#')[0])).resolve()
            if not target.is_file():
                raise ValueError('Broken local report link: ' + str(target))
            local_links.append({'page': str(page), 'target': str(target)})
    verification = {'report': str(REPORT), 'html_pages': [str(page) for page in html_pages],
                    'all_local_links_exist': True, 'local_link_count': len(local_links),
                    'blind_sample_mapping': clips, 'all_audio_checks_passed': data['summary']['all_source_and_signal_checks_passed'],
                    'source_caches_unchanged_during_evaluation': data['source_caches_unchanged'],
                    'main_browser_checks': browser_checks,
                    'main_browser_proof_sha256': digest(browser_file) if browser else None,
                    'main_ui_proof_file': str(ui_proof_file) if ui_proof_file.is_file() else None,
                    'main_ui_proof_sha256': digest(ui_proof_file) if ui_proof_file.is_file() else None,
                    'new_scene_count': len(fresh), 'clap_is_not_human_listening_score': True}
    write(OUT / 'report_verification.json', verification)
    print(json.dumps(verification, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    build()
