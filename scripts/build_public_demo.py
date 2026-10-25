"""Publish a small, explicitly whitelisted demo from existing local results.

No model inference, login, downloads or network requests are performed.
The original private experiment records are read, never copied wholesale.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlparse

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'demo_public'
IDS = ('monbachtal_riverbank', 'crystal_falls', 'secluded_beach', 'urban_street_03')
LABELS = {'monbachtal_riverbank': '苔岩浅溪与低跌水', 'crystal_falls': '岩壁瀑布与开阔水潭',
          'secluded_beach': '沙石海滩与近岸浪线', 'urban_street_03': '住宅街道与路边停车'}
GROUPS = {'monbachtal_riverbank': '浅溪', 'crystal_falls': '岩壁瀑布',
          'secluded_beach': '海边', 'urban_street_03': '街道'}
FORBIDDEN_KEYS = {'session_id', 'cli_executable', 'request_audit_file', 'response_file',
    'contact_sheet_file', 'request_file', 'source_file', 'result_file', 'plan_file',
    'api_key', 'access_token', 'refresh_token', 'cookies', 'email', 'worker_pid'}
FORBIDDEN_TEXT = [r'\b[A-Za-z]:[\\/]', r'chatgpt\.com/c/', r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
                  r'(?i)bearer\s+[A-Za-z0-9._-]+', r'\bsk-[A-Za-z0-9_-]{15,}']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False), encoding='utf-8')


def codec_python():
    if importlib.util.find_spec('soundfile'):
        return Path(sys.executable)
    for candidate in (ROOT/'audio_model/.venv/Scripts/python.exe',
                      ROOT/'audio_model/.venv/bin/python'):
        if candidate.is_file():
            return candidate
    raise RuntimeError('Install the independent audio environment with soundfile to encode the demo.')


ENCODE = r'''
import hashlib,json,sys
import numpy as np
import soundfile as sf
source,target=sys.argv[1:]
audio,rate=sf.read(source,always_2d=True)
if rate!=32000 or audio.shape!=(896000,1) or not np.isfinite(audio).all():
    raise ValueError('Expected the verified 28-second mono 32 kHz comparison WAV')
with sf.SoundFile(target,mode='w',samplerate=rate,channels=1,format='OGG',subtype='VORBIS') as stream:
    # Bounded writes avoid a large single-call Vorbis stack allocation on Windows.
    for start in range(0,len(audio),4096):
        stream.write(audio[start:start+4096])
decoded,sr=sf.read(target,always_2d=True)
if sr!=rate or decoded.shape!=audio.shape or not np.isfinite(decoded).all():
    raise ValueError('Invalid encoded listening copy')
print(json.dumps({'codec':'OGG Vorbis','lossy_listening_copy':True,
    'encoder':'soundfile '+sf.__version__+' / libsndfile '+sf.__libsndfile_version__,
    'encoding_quality':'libsndfile Vorbis default', 'duration_seconds':len(decoded)/sr,
    'sample_rate':sr,'channels':decoded.shape[1],
    'decoded_peak':float(np.max(np.abs(decoded))),
    'decoded_rms':float(np.sqrt(np.mean(decoded**2)))}))
'''


def assert_safe(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                raise ValueError('Private metadata key in public demo: '+key)
            assert_safe(item)
    elif isinstance(value, list):
        for item in value:
            assert_safe(item)
    elif isinstance(value, str):
        if any(re.search(pattern, value) for pattern in FORBIDDEN_TEXT):
            raise ValueError('Private content detected in public demo text')


def approved_source_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'polyhaven.com':
        raise ValueError('Unexpected panorama source URL')
    return url


def public_item(asset, row, python):
    identifier = asset['id']
    job = read(ROOT/'outputs/auto_panorama'/asset['sha256']/'result.json')
    if job['status'] != 'complete' or job['image_sha256_rgb'] != row['image_sha256_rgb']:
        raise ValueError('Incomplete or mismatched panorama result')
    source_image = ROOT/'samples/multiscene_auto_20261025'/(identifier+'.jpg')
    if digest(source_image) != asset['sha256']:
        raise ValueError('Panorama source checksum mismatch')
    image_path = OUTPUT/'images'/(identifier+'.jpg')
    with Image.open(source_image) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
        if image.width != 2*image.height:
            raise ValueError('Panorama is not full 2:1 ERP')
        image.resize((1024, 512), Image.Resampling.LANCZOS).save(
            image_path, quality=80, optimize=True)
    comparison = row['matched_mix']
    wav = ROOT/'outputs/multiscene_automatic_evaluation/audio'/(identifier+'.wav')
    if digest(wav) != comparison['sha256']:
        raise ValueError('Comparison WAV checksum mismatch')
    audio_path = OUTPUT/'audio'/(identifier+'.ogg')
    encoded = subprocess.run([str(python), '-c', ENCODE, str(wav), str(audio_path)],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=45)
    audio = json.loads(encoded.stdout)
    audio.update(file='audio/'+audio_path.name, sha256=digest(audio_path),
        source_comparison_wav_sha256=comparison['sha256'],
        source_comparison_target_lufs=comparison['global_target_lufs'],
        note='Lossy listening copy. Reported CLAP scores and exact loudness matching refer to the uncompressed comparison WAV, not a re-scoring of this OGG.')
    spoken = next(x for x in job['narration']['voices'] if x['voice_id']=='zh-CN-XiaoxiaoNeural')
    if hashlib.sha256(job['narration_text'].encode('utf-8')).hexdigest() != spoken['text_sha256']:
        raise ValueError('Narration text checksum mismatch')
    original_mp3 = Path(spoken['file'])
    if digest(original_mp3) != spoken['sha256']:
        raise ValueError('Narration audio checksum mismatch')
    narration_path = OUTPUT/'narration'/(identifier+'.mp3')
    shutil.copyfile(original_mp3, narration_path)
    # Construct all public fields explicitly. Never serialize source records.
    return {'id':identifier, 'title':LABELS[identifier], 'group':GROUPS[identifier],
        'image':{'file':'images/'+image_path.name, 'width':1024, 'height':512,
            'sha256':digest(image_path), 'source_image_sha256':asset['sha256'],
            'source_title':asset['source_title'], 'source_url':approved_source_url(asset['source_url']),
            'authors':asset['author'], 'license':'CC0-1.0', 'license_url':'https://polyhaven.com/license',
            'credit':'Powered by Poly Haven',
            'processing':'Complete ERP resized to 1024x512 JPEG quality80; no scene edits; no EXIF copied.'},
        'audio':audio,
        'narration':{'file':'narration/'+narration_path.name, 'sha256':digest(narration_path),
            'text':job['narration_text'], 'text_sha256':spoken['text_sha256'],
            'voice_id':spoken['voice_id'], 'duration_seconds':spoken['duration_seconds'],
            'provider':'Microsoft online neural TTS via edge-tts', 'neural':True,
            'human_recording':False},
        'gpt':{'provider':job['gpt_provenance']['provider'], 'model':job['gpt_provenance']['model']},
        'visible_facts_zh':job['plan']['evidence']['visible_facts_zh'],
        'sound_prompts':[{'category':x['category'], 'prompt':x['prompt'], 'seed':x['seed']}
                        for x in job['plan']['stems']],
        'view_sources':{key:[{k:s[k] for k in ('category','azimuth','virtual_radius','spread_degrees')}
                            for s in value.get('sources',[])]
                        for key,value in job['plan']['views'].items()},
        'clap_label_cosines':{key:float(value) for key,value in row['clap']['mean_label_cosines'].items()}}


EN_SCENES = {
    'monbachtal_riverbank': {
        'title': 'Mossy stream and small cascades', 'group': 'Shallow stream',
        'facts': [
            'Tall trees, exposed roots, fallen leaves and moss-covered rocks are visible in the woodland.',
            'A shallow stream, several small cascades and water between rocks are visible in front of layered rock faces.',
            'A dirt path and scattered stones are visible to the right, with a fallen trunk leaning across the rear view.'],
        'narration': 'In front of you is a shallow woodland stream surrounded by rocks, with several small cascades in the centre and stones scattered between the pools. Layered rock faces, partly covered in moss, rise to the left. To the right are a dirt slope with exposed roots and a path; looking back reveals a leaning fallen trunk. These are estimates from the image. The flowing-water sound is simulated, and access along the water remains uncertain.'},
    'crystal_falls': {
        'title': 'Rock-face waterfall and open pool', 'group': 'Rock-face waterfall',
        'facts': [
            'A white waterfall is visible against one side of the rock face, feeding a shallow pool and a channel between rocks.',
            'Rocks of different sizes lie in front, surrounded by trees, roots and dense foliage.',
            'Gravel, large rocks and objects placed beside a rock are visible to the right.',
            'The waterfall or its shallow downstream water is visible in both the rear and left views.'],
        'narration': 'The image suggests a position beside rocky shallow water surrounded by trees. Stones of different sizes lie ahead; to the right are gravel and large boulders. Turning towards the left rear reveals a white waterfall on the rock face and connected shallow water below. The sound is simulated. The photograph cannot establish the actual water force, distance or loudness, or whether the waterside is safe to access.'},
    'secluded_beach': {
        'title': 'Sandy, rocky beach and nearshore waves', 'group': 'Coast',
        'facts': [
            'A bay-like stretch of water lies ahead, with rounded rocks of different sizes in the water and along the shore.',
            'Pale sand borders the nearshore water, with dark strips and a longer brown strip scattered across it.',
            'Shrubs and trees are visible to the right, rear and left; some branches are bare.',
            'The sky is mostly blue with a few thin clouds, and bright reflections appear on the water to the front right.'],
        'narration': 'In front of you is a bay-like area of water enclosed by rocks, with pale sand extending along both sides and dark strips scattered across it. To the right, branches reach into the bright sky; behind you are denser shrubs and trees. The image suggests a small bay, but water depth, wave conditions and access cannot be confirmed. The waves in this preview are simulated.'},
    'urban_street_03': {
        'title': 'Residential street and parked cars', 'group': 'Street',
        'facts': [
            'The road extends forwards and backwards, with parked cars, kerbs and pavements on both sides.',
            'To the right is a row of multi-storey brick buildings with white window frames and arched entrances, fronted by shrubs and low walls.',
            'Homes, a brick wall, grey gates and tree crowns are visible to the left, with another broad tree behind.',
            'Grey-white cloud covers the sky, and white markings are visible on the road.'],
        'narration': 'A residential street stretches ahead, with cars parked along both sides beneath grey-white clouds. To the right, multi-storey brick buildings have white window frames, with shrubs and low walls in front. To the left are a brick wall, grey gates and tree crowns. Looking behind reveals the road and a broad tree. The photograph cannot confirm whether vehicles are moving. The sparse traffic sounds in the preview are simulated.'},
}


def render(data, language='zh-CN'):
    """Render both complete UI languages; a URL query selects the visible one.

    Each language uses only its own narration record. Missing English audio
    is shown explicitly and never replaced by the original Chinese recording.
    """
    esc = html.escape
    language = 'en' if language == 'en' else 'zh-CN'

    def page(lang):
        english = lang == 'en'
        def tr(zh, en):
            return en if english else zh
        cards = []
        for item in data['scenes']:
            translated = EN_SCENES[item['id']] if english else item
            title = translated['title']
            facts = translated['facts'] if english else item['visible_facts_zh']
            source = item['image']
            narration = item.get('narrations', {}).get(lang)
            if not english and narration is None:
                narration = item['narration']  # Schema-1 Chinese compatibility.
            authors = ', '.join(source['authors']) if english else '、'.join(source['authors'])
            prompts = ''.join('<p><strong>'+esc(p['category'])+'</strong></p><pre lang="en">'+esc(p['prompt'])+'</pre>'
                              for p in item['sound_prompts'])
            guide = '<p lang="'+lang+'">'+esc(narration['text'] if narration else translated['narration'])+'</p>'
            if narration:
                spoken = '<audio controls preload="metadata" lang="'+lang+'" aria-label="'+esc(title+tr('，中文神经导览', ', English neural narration'))+'" src="'+narration['file']+'"></audio>'
            else:
                spoken = '<p role="status" class="credit">'+tr('中文配音暂未就绪。', 'English narration is unavailable for this example. No Chinese audio is substituted.')+'</p>'
            cards.append(
                '<article><img src="'+source['file']+'" alt="'+esc(title+tr('，完整等距柱状全景', ', complete equirectangular panorama'))+'">'
                '<div class="content"><span class="tag">'+esc(translated['group'])+'</span><h2>'+esc(title)+'</h2>'
                '<p>'+esc((' ' if english else '；').join(facts[:2]))+'</p>'
                '<label>'+tr('本图模拟声景 · 28 秒（OGG 有损试听副本）',
                    'Scene-specific simulated soundscape · 28 s (lossy OGG listening copy)')+'</label>'
                '<audio controls preload="metadata" aria-label="'+esc(title+tr('，模拟声景', ', simulated soundscape'))+'" src="'+item['audio']['file']+'"></audio>'
                '<label>'+tr('本图自然中文导览 · 晓晓神经女声',
                    'English narration · Jenny neural female voice')+'</label>'+spoken+
                '<details><summary>'+tr('导览文字与声音提示词', 'Narration text and sound prompts')+'</summary>'
                '<h3>'+tr('中文导览原文', 'English narration text')+'</h3>'+guide+
                '<h3>'+tr('声音提示词（英文原文）', 'Sound prompts (original English)')+'</h3>'+prompts+'</details>'
                '<p class="credit"><span>'+tr('全景来源：', 'Panorama: ')+'</span><a href="'+source['source_url']+'">'+esc(source['source_title'])+'</a> · '+esc(authors)+
                ' · <a href="https://polyhaven.com/license">'+tr('摄影 CC0', 'Photography: CC0')+'</a> · Powered by Poly Haven</p></div></article>')
        notice = '../THIRD_PARTY_NOTICES.md' if english else '../THIRD_PARTY_NOTICES.zh-CN.md'
        return (
            '<div class="topbar"><a class="brand" data-app-view="home" href="http://127.0.0.1:8501/?lang='+lang+'">LandscapeSound</a>'
            '<nav aria-label="'+tr('页面导航', 'Page navigation')+'">'
            '<a data-app-view="demo" href="#scenes">'+tr('四场景试听', 'Listen to four scenes')+'</a>'
            '<a data-app-view="compare" href="#comparison">'+tr('品质比较', 'Quality comparison')+'</a>'
            '<a data-app-view="guide" href="http://127.0.0.1:8501/?lang='+lang+'&amp;view=guide">'+tr('使用指南', 'User guide')+'</a>'
            '<a data-app-view="notices" href="http://127.0.0.1:8501/?lang='+lang+'&amp;view=notices">'+tr('来源与许可', 'Sources and licences')+'</a></nav>'
            '<div class="languages" aria-label="'+tr('界面语言', 'Interface language')+'">'
            '<a data-language="zh-CN" lang="zh-CN" href="?lang=zh-CN"'+(' aria-current="true"' if not english else '')+'>中文</a>'
            '<a data-language="en" lang="en" href="?lang=en"'+(' aria-current="true"' if english else '')+'>English</a></div></div>'
            '<header><div class="eyebrow">LANDSCAPESOUND · '+tr('公开试听', 'PUBLIC DEMO')+'</div><h1>'+
            tr('一幅风景，一段声景。', 'A landscape, a soundscape.')+'</h1><p>'+
            tr('四张全新摄影全景，经主应用自动完成 GPT 理解、本机音效生成，并配有对应的中文和英文导览。每张图都有独立音轨；这些声音是模拟，配音是神经合成，并非地点实录或真人录音。',
               'Four new photographic panoramas from the main app’s automatic GPT scene understanding and local sound generation, with corresponding Chinese and English narration. Each image has its own audio. Soundscapes are simulated and narration is neural synthesis; neither is a recording of the pictured site or a human voice recording.')+'</p></header>'
            '<aside class="note"><strong>'+tr('先从舒适的音量开始。', 'Start at a comfortable volume.')+'</strong><p>'+
            tr('建议戴耳机。播放任意一段声音会停止页面内其他声音；你可以随时暂停。页面不调用 GPT、模型或在线语音服务，所有试听文件都在此包内。',
               'Headphones are recommended. Playing any clip pauses the other clips on this page, and you can pause at any time. This page makes no GPT, model or online speech-service calls; every listening file is included in this package.')+'</p>'
            '<button type="button" data-stop-audio>'+tr('暂停所有声音', 'Pause all audio')+'</button></aside>'
            '<section id="comparison"><h2>'+tr('溪流还是雨：问题仍然存在', 'Stream or rain: the problem remains')+'</h2><p>'+
            tr('本轮自动内容诊断没有支持“流水雨感已解决”。浅溪仍更接近降雨标签，岩壁瀑布的水势也被弱化；街道与水景较容易分开。这些是 CLAP 表征接近度，不是人耳辨识率或自然度评分。',
               'This round of automatic content diagnostics does not support the claim that rain-like flowing water has been resolved. The shallow stream remains closer to the rain label, and the rock-face waterfall sounds weaker than its setting suggests. Street and water scenes are easier to separate. These are CLAP representation similarities, not human recognition rates or naturalness scores.')+'</p>'
            '<div class="table-scroll"><table><thead><tr><th>'+tr('场景', 'Scene')+'</th><th>'+tr('溪流', 'Stream')+'</th><th>'+tr('降雨', 'Rain')+'</th><th>'+tr('瀑布', 'Waterfall')+'</th><th>'+tr('观察', 'Observation')+'</th></tr></thead><tbody>'
            '<tr><td>'+tr('浅溪低跌水', 'Shallow stream / small cascades')+'</td><td>0.535</td><td>0.620</td><td>0.376</td><td>'+tr('仍有雨声混淆信号', 'Rain confusion remains')+'</td></tr>'
            '<tr><td>'+tr('岩壁瀑布', 'Rock-face waterfall')+'</td><td>0.638</td><td>0.619</td><td>0.463</td><td>'+tr('更像细溪，水势表达不足', 'Closer to a small stream; insufficient force')+'</td></tr></tbody></table></div><p>'+
            tr('两种流水的音频表征相似度为0.861；街道与三水景约0.200–0.263，差别较清楚。海边与流水也偏相近。所有四条新结果均保留；没有按分数换成旧素材。',
               'The two flowing-water clips have an audio-representation similarity of 0.861. Street-to-water similarities are approximately 0.200–0.263, showing clearer separation. The coast is also relatively close to flowing water. All four new results are retained; none was replaced with an older clip to improve scores.')+'</p>'
            '<p class="credit">'+tr('内容指标基于统一28秒、约−23 LUFS的未压缩对照WAV。下方OGG是有损试听副本，未对OGG重新评分。原中文配音约25.7–27.8秒。中英文配音分别绑定各自文本和音频指纹，未进行人耳自然度评分。',
               'Content metrics use the uncompressed comparison WAVs, each 28 seconds and approximately −23 LUFS. The OGG files below are lossy listening copies and were not re-scored. The original Chinese narration clips last approximately 25.7–27.8 seconds. Each language’s narration is bound to its own exact text and audio fingerprint; human naturalness was not scored.')+'</p></section>'
            '<div id="scenes" class="grid">'+''.join(cards)+'</div><footer><p>'+
            tr('图像方位、虚拟远近和动态声音均为模拟设定；静态图片不能确认现场响度、流速、通行或避障条件。',
               'Image directions, virtual distances and dynamic sounds are simulated settings. A still image cannot establish actual loudness, flow speed, access or obstacle-avoidance conditions.')+'</p><p>'
            '<a href="metadata.json">'+tr('来源、提示词、文件指纹与公开元数据', 'Sources, prompts, file fingerprints and public metadata')+'</a> · '
            '<a data-app-view="notices" href="'+notice+'">'+tr('第三方来源与许可', 'Third-party sources and licences')+'</a></p><p>'+
            tr('仅公开演示所需的白名单字段；模型、环境、原始日志与登录资料不在此包内。',
               'Only the fields required for this public demo are included. Models, environments, original logs and sign-in information are excluded.')+'</p></footer>')

    config = json.dumps({'language': language, 'forced_language': False, 'embedded': False,
                         'current_view': 'demo', 'app_links': {}}, ensure_ascii=False)
    return '''<!doctype html><html lang="'''+language+'''"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script id="ls-demo-config" type="application/json">'''+config+'''</script>
<title>LandscapeSound</title><script>var demoConfig=JSON.parse(document.getElementById('ls-demo-config').textContent);var demoLanguage=demoConfig.forced_language?demoConfig.language:(new URLSearchParams(location.search).get('lang')||demoConfig.language);demoLanguage=demoLanguage==='en'?'en':'zh-CN';document.documentElement.lang=demoLanguage;document.title=demoLanguage==='en'?'LandscapeSound · Four-scene listening demo':'LandscapeSound · 四场景试听';</script><style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#18313e;background:#f3f6f7}*{box-sizing:border-box}body{margin:0}main{max-width:1140px;margin:auto;padding:24px 20px 60px}.topbar{display:flex;align-items:center;flex-wrap:wrap;gap:20px;margin-bottom:24px}.brand{font-weight:750;text-decoration:none;color:#18313e}nav{display:flex;flex-wrap:wrap;gap:16px;flex:1;font-size:13px}.languages{display:flex;gap:5px}.languages a{padding:7px 10px;border-radius:8px;text-decoration:none}.languages [aria-current]{background:#176562;color:white}header{padding:36px;background:#112e40;color:#fff;border-radius:24px}h1{font-size:clamp(28px,4vw,44px);line-height:1.25;margin:12px 0}header p{color:#d7e8e9}h2{font-size:23px;margin:10px 0}h3{font-size:16px;margin:20px 0 8px}p{line-height:1.8}a{color:#176562}.eyebrow{font-size:12px;letter-spacing:.14em;color:#baf0df}.note{background:#fff2d8;border:1px solid #e3d3ad;border-radius:16px;padding:18px 22px;margin:22px 0}.note p{margin:8px 0 12px}button{font:inherit;cursor:pointer;border:1px solid #176562;border-radius:10px;padding:10px 16px;background:#fff;color:#176562;min-height:44px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:24px}article{border:1px solid #d4e0e4;background:#fff;border-radius:19px;overflow:hidden}article img{display:block;width:100%;aspect-ratio:2;object-fit:cover}.content{padding:22px}.tag{font-size:12px;color:#176562;font-weight:700;letter-spacing:.08em}label{display:block;font-size:14px;font-weight:600;margin:20px 0 8px}audio{display:block;width:100%;min-height:44px}details{margin-top:18px}summary{cursor:pointer;min-height:44px;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.6;background:#f0f5f5;padding:12px;border-radius:10px}.credit{font-size:12px;color:#4c6370;margin-bottom:0}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;margin:16px 0}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #d7e1e5}section{background:white;border:1px solid #d7e1e5;border-radius:18px;padding:22px;margin-top:24px}a:focus-visible,summary:focus-visible,audio:focus-visible,button:focus-visible{outline:3px solid #157eac;outline-offset:3px}footer{color:#506673;font-size:13px;margin-top:24px}@media(max-width:720px){main{padding:16px 12px 40px}header{padding:25px}.grid{grid-template-columns:1fr}.content{padding:18px}table{font-size:12px}th,td{padding:8px 5px}.topbar{gap:12px}nav{order:3;flex-basis:100%}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head><body><main id="demo-root"></main><template id="demo-zh-CN">'''+page('zh-CN')+'''</template><template id="demo-en">'''+page('en')+'''</template><script>
(function(){
  var config=demoConfig,lang=demoLanguage,root=document.getElementById('demo-root');
  root.appendChild(document.getElementById('demo-'+lang).content.cloneNode(true));
  root.querySelectorAll('[data-app-view]').forEach(function(link){
    var view=link.dataset.appView;
    if(config.embedded){link.href=config.app_links[lang][view];link.target='_top';}
  });
  root.querySelectorAll('[data-language]').forEach(function(link){
    var next=link.dataset.language;
    link.href=config.embedded?config.app_links[next][config.current_view]:'?lang='+next+location.hash;
    if(config.embedded)link.target='_top';
  });
  var clips=root.querySelectorAll('audio');
  clips.forEach(function(audio){audio.addEventListener('play',function(){
    clips.forEach(function(other){if(other!==audio)other.pause();});
  });});
  root.querySelector('[data-stop-audio]').addEventListener('click',function(){clips.forEach(function(audio){audio.pause();});});
  var anchor=location.hash.slice(1)||(config.embedded&&config.current_view==='compare'?'comparison':'');
  if(anchor){var destination=document.getElementById(anchor);if(destination)destination.scrollIntoView();}
})();
</script></body></html>'''


def localized_narrations(scene):
    """Validate locale-to-file/text binding while retaining schema-1 Chinese."""
    records = scene.get('narrations', {})
    if not isinstance(records, dict) or set(records) - {'zh-CN', 'en'}:
        raise ValueError('Unsupported public narration locale')
    for language, record in records.items():
        suffix = '.en.mp3' if language == 'en' else '.mp3'
        if not isinstance(record, dict) or record.get('file') != 'narration/'+scene['id']+suffix:
            raise ValueError('Public narration file does not match its locale and scene')
        if language == 'en' and (record.get('language') != 'en' or record.get('voice_id') != 'en-US-JennyNeural'):
            raise ValueError('English public narration needs its declared English voice')
        if language == 'en' and (re.search(r'[\u3400-\u9fff]', record.get('text', ''))
                or record.get('source_text_sha256', scene['narration']['text_sha256']) != scene['narration']['text_sha256']):
            raise ValueError('English narration must match its language and source guide')
        if hashlib.sha256(record.get('text', '').encode('utf-8')).hexdigest() != record.get('text_sha256'):
            raise ValueError('Public narration text checksum mismatch')
        yield record


def validate():
    data = read(OUTPUT/'metadata.json')
    assert_safe(data)
    text_files = [OUTPUT/'metadata.json', OUTPUT/'index.html']
    for path in text_files:
        text = path.read_text(encoding='utf-8')
        if any(re.search(pattern, text) for pattern in FORBIDDEN_TEXT):
            raise ValueError('Private text pattern detected in '+path.name)
    for scene in data['scenes']:
        for artifact in [scene[kind] for kind in ('image', 'audio', 'narration')] + list(localized_narrations(scene)):
            path = (OUTPUT/artifact['file']).resolve()
            if not path.is_relative_to(OUTPUT.resolve()) or digest(path) != artifact['sha256']:
                raise ValueError('Invalid public artifact identity')
    local_links = []
    for link in re.findall(r'(?:src|href)="([^"]+)"', (OUTPUT/'index.html').read_text(encoding='utf-8')):
        if urlparse(link).scheme or link.startswith(('#', '?')):
            continue
        target = (OUTPUT/unquote(urlparse(link).path)).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            raise ValueError('Broken public demo link: '+link)
        local_links.append(link)
    files = [p for p in OUTPUT.rglob('*') if p.is_file()]
    if any(p.stat().st_size >= 500*1024 for p in files) or sum(p.stat().st_size for p in files) >= 3*1024**2:
        raise ValueError('Public demo exceeds lightweight publication budget')
    return {'public_demo':'demo_public/index.html', 'file_count':len(files),
        'total_bytes':sum(p.stat().st_size for p in files),
        'largest_file_bytes':max(p.stat().st_size for p in files),
        'local_links_verified':len(local_links), 'sensitive_text_scan_passed':True,
        'artifact_hashes_verified':True, 'all_files_below_500_kib':True}


def build_html_only(language='zh-CN'):
    """Rebuild only the page, retaining all published asset/metadata bytes."""
    data = read(OUTPUT/'metadata.json')
    assert_safe(data)
    (OUTPUT/'index.html').write_text(render(data, language), encoding='utf-8')
    return validate()


def add_english_narration():
    """Explicit online synthesis of only the four public English guide texts."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from narration import ensure_narration
    from narration_localization import store_reviewed_translation
    data = read(OUTPUT/'metadata.json')
    assert_safe(data)
    rows = []
    for scene in data['scenes']:
        text = EN_SCENES[scene['id']]['narration']
        store_reviewed_translation(source_text=scene['narration']['text'], translated_text=text,
            language='en', provenance={'method':'Reviewed public-demo English translation',
            'translated':True, 'scene_id':scene['id']}, root=ROOT)
        print('Creating English narration: '+scene['id'], file=sys.stderr, flush=True)
        result = ensure_narration(text, voices=['en-US-JennyNeural'], root=ROOT, language='en')
        voice = next(item for item in result['voices'] if item['voice_id'] == 'en-US-JennyNeural')
        source = Path(voice['file']).resolve()
        expected_text = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if (not source.is_relative_to((ROOT/'assets/narration').resolve())
                or voice['text'] != text or voice['text_sha256'] != expected_text
                or digest(source) != voice['sha256']):
            raise ValueError('English narration cache identity mismatch')
        destination = OUTPUT/'narration'/(scene['id']+'.en.mp3')
        shutil.copyfile(source, destination)
        record = {'file':destination.relative_to(OUTPUT).as_posix(),
            'sha256':digest(destination), 'text':text, 'text_sha256':expected_text,
            'source_text_sha256':scene['narration']['text_sha256'],
            'voice_id':voice['voice_id'], 'provider':voice['provider'], 'language':'en',
            'duration_seconds':voice['duration_seconds'], 'neural':True,
            'human_recording':False, 'synthesis_config':voice['synthesis_config'],
            'text_source':'English translation of the corresponding public Chinese guide, stored in EN_SCENES.'}
        scene['narrations'] = {'zh-CN':scene['narration'], 'en':record}
        rows.append({key:record[key] for key in ('file','voice_id','duration_seconds','sha256','text_sha256')})
    assert_safe(data)
    write(OUTPUT/'metadata.json', data)
    return {**build_html_only(), 'english_narrations':rows}


def build(language='zh-CN'):
    previous = read(OUTPUT/'metadata.json') if (OUTPUT/'metadata.json').is_file() else {}
    previous_scenes = {scene['id']:scene for scene in previous.get('scenes', [])}
    evaluation = read(ROOT/'outputs/multiscene_automatic_evaluation/evaluation.json')
    assets = {item['id']:item for item in read(ROOT/'samples/multiscene_auto_20261025/manifest.json')}
    rows = {row['id']:row for row in evaluation['rows'] if row['id'] in IDS}
    if set(rows) != set(IDS):
        raise ValueError('All four local UI-generated evaluations are required')
    for subfolder in ('images', 'audio', 'narration'):
        (OUTPUT/subfolder).mkdir(parents=True, exist_ok=True)
    python = codec_python()
    scenes = [public_item(assets[identifier], rows[identifier], python) for identifier in IDS]
    for scene in scenes:
        old = previous_scenes.get(scene['id'], {})
        preserved = old.get('narrations', {}).get('en')
        if preserved:
            # Never silently drop or regenerate the separately produced English guide.
            for record in localized_narrations(old):
                if digest(OUTPUT/record['file']) != record['sha256']:
                    raise ValueError('Existing localized narration has changed')
            scene['narrations'] = {'zh-CN':scene['narration'], 'en':preserved}
    data = {'schema_version':1, 'title':'LandscapeSound four-scene public demo',
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'scenes':scenes, 'pictured_site_recordings':False,
        'subjective_naturalness_score':None,
        'evaluation_method':{'model':'laion/clap-htsat-unfused',
            'measurement_source':'Uncompressed 28-second gain-matched comparison WAV, not the OGG copies',
            'interpretation':'Exploratory content cosine, not human recognition, naturalness or probabilities'},
        'pairwise_audio_cosines':[{k:p[k] for k in ('a','b','audio_embedding_cosine')}
            for p in evaluation['summary']['between_scene_pairs']]}
    assert_safe(data)
    write(OUTPUT/'metadata.json', data)
    (OUTPUT/'index.html').write_text(render(data, language), encoding='utf-8')
    return validate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--validate-only', action='store_true')
    modes.add_argument('--html-only', action='store_true', help='Rebuild the bilingual page without touching media or metadata.')
    modes.add_argument('--english-narration', action='store_true', help='Explicitly send the four public English guides to the online neural TTS service and publish their MP3s.')
    parser.add_argument('--language', choices=('zh-CN', 'en'), default='zh-CN', help='Default language; URL lang overrides it in the static page.')
    args = parser.parse_args()
    print(json.dumps(validate() if args.validate_only else add_english_narration() if args.english_narration else build_html_only(args.language) if args.html_only else build(args.language), ensure_ascii=False))
