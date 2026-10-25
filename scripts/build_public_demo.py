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


def render(data):
    esc = html.escape
    cards = []
    for item in data['scenes']:
        source = item['image']
        authors = '、'.join(source['authors'])
        prompts = ''.join('<p><strong>'+esc(p['category'])+'</strong></p><pre>'+esc(p['prompt'])+'</pre>'
                          for p in item['sound_prompts'])
        cards.append('<article><img src="'+source['file']+'" alt="'+esc(item['title'])+'完整全景">'
            '<div class="content"><span class="tag">'+esc(item['group'])+'</span><h2>'+esc(item['title'])+'</h2>'
            '<p>'+esc('；'.join(item['visible_facts_zh'][:2]))+'</p>'
            '<label>本图模拟声景 · 28 秒（OGG 有损试听副本）</label><audio controls preload="metadata" src="'+item['audio']['file']+'"></audio>'
            '<label>本图自然中文导览 · 晓晓神经女声</label><audio controls preload="metadata" src="'+item['narration']['file']+'"></audio>'
            '<details><summary>导览文字与声音提示词</summary><p>'+esc(item['narration']['text'])+'</p>'+prompts+'</details>'
            '<p class="credit"><a href="'+source['source_url']+'">'+esc(source['source_title'])+'</a> · '+esc(authors)+
            ' · <a href="https://polyhaven.com/license">摄影 CC0</a> · Powered by Poly Haven</p></div></article>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LandscapeSound · 四场景试听</title><style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#18313e;background:#f3f6f7}*{box-sizing:border-box}body{margin:0}main{max-width:1140px;margin:auto;padding:32px 20px 60px}header{padding:36px;background:#112e40;color:#fff;border-radius:24px}h1{font-size:clamp(28px,4vw,44px);line-height:1.25;margin:12px 0}header p{color:#d7e8e9}h2{font-size:23px;margin:10px 0}p{line-height:1.8}a{color:#176562}.eyebrow{font-size:12px;letter-spacing:.14em;color:#baf0df}.note{background:#fff2d8;border:1px solid #e3d3ad;border-radius:16px;padding:18px 22px;margin:22px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:24px}article{border:1px solid #d4e0e4;background:#fff;border-radius:19px;overflow:hidden}article img{display:block;width:100%;aspect-ratio:2;object-fit:cover}.content{padding:22px}.tag{font-size:12px;color:#176562;font-weight:700;letter-spacing:.08em}label{display:block;font-size:14px;font-weight:600;margin:20px 0 8px}audio{display:block;width:100%;min-height:44px}details{margin-top:18px}summary{cursor:pointer;min-height:44px;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.6;background:#f0f5f5;padding:12px;border-radius:10px}.credit{font-size:12px;color:#4c6370;margin-bottom:0}table{width:100%;border-collapse:collapse;font-size:14px;margin:16px 0}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #d7e1e5}section{background:white;border:1px solid #d7e1e5;border-radius:18px;padding:22px;margin-top:24px}a:focus-visible,summary:focus-visible,audio:focus-visible{outline:3px solid #157eac;outline-offset:3px}footer{color:#506673;font-size:13px;margin-top:24px}@media(max-width:720px){main{padding:16px 12px 40px}header{padding:25px}.grid{grid-template-columns:1fr}.content{padding:18px}table{font-size:12px}th,td{padding:8px 5px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style><main><header><div class="eyebrow">LANDSCAPESOUND · PUBLIC DEMO</div><h1>一幅风景，一段声景。</h1><p>四张全新摄影全景，经主应用自动完成 GPT 理解、本机音效生成和中文导览。每张图都有独立音轨；这些声音是模拟，配音是神经合成，并非地点实录或真人录音。</p></header>
<aside class="note"><strong>先从舒适的音量开始。</strong><br>建议戴耳机。播放任意一段声音会停止页面内其他声音；你可以随时暂停。页面不调用 GPT、模型或在线语音服务，所有试听文件都在此包内。</aside>
<section><h2>溪流还是雨：问题仍然存在</h2><p>本轮自动内容诊断没有支持“流水雨感已解决”。浅溪仍更接近降雨标签，岩壁瀑布的水势也被弱化；街道与水景较容易分开。这些是 CLAP 表征接近度，不是人耳辨识率或自然度评分。</p>
<table><thead><tr><th>场景</th><th>溪流</th><th>降雨</th><th>瀑布</th><th>观察</th></tr></thead><tbody><tr><td>浅溪低跌水</td><td>0.535</td><td>0.620</td><td>0.376</td><td>仍有雨声混淆信号</td></tr><tr><td>岩壁瀑布</td><td>0.638</td><td>0.619</td><td>0.463</td><td>更像细溪，水势表达不足</td></tr></tbody></table>
<p>两种流水的音频表征相似度为0.861；街道与三水景约0.200–0.263，差别较清楚。海边与流水也偏相近。所有四条新结果均保留；没有按分数换成旧素材。</p>
<p class="credit">内容指标基于统一28秒、约−23 LUFS的未压缩对照WAV。下方OGG是有损试听副本，未对OGG重新评分。四段配音约25.7–27.8秒，精确文字缓存已核验，未进行人耳自然度评分。</p></section>
<div class="grid">''' + ''.join(cards) + '''</div><footer><p>图像方位、虚拟远近和动态声音均为模拟设定；静态图片不能确认现场响度、流速、通行或避障条件。</p><p><a href="metadata.json">来源、提示词、文件指纹与公开元数据</a> · <a href="../THIRD_PARTY_NOTICES.md">第三方来源与许可</a></p><p>仅公开演示所需的白名单字段；模型、环境、原始日志与登录资料不在此包内。</p></footer></main><script>document.querySelectorAll('audio').forEach(audio=>audio.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause();});}));</script></html>'''


def validate():
    data = read(OUTPUT/'metadata.json')
    assert_safe(data)
    text_files = [OUTPUT/'metadata.json', OUTPUT/'index.html']
    for path in text_files:
        text = path.read_text(encoding='utf-8')
        if any(re.search(pattern, text) for pattern in FORBIDDEN_TEXT):
            raise ValueError('Private text pattern detected in '+path.name)
    for scene in data['scenes']:
        for kind in ('image', 'audio', 'narration'):
            artifact = scene[kind]
            path = (OUTPUT/artifact['file']).resolve()
            if not path.is_relative_to(OUTPUT.resolve()) or digest(path) != artifact['sha256']:
                raise ValueError('Invalid public artifact identity')
    local_links = []
    for link in re.findall(r'(?:src|href)="([^"]+)"', (OUTPUT/'index.html').read_text(encoding='utf-8')):
        if urlparse(link).scheme or link.startswith('#'):
            continue
        target = (OUTPUT/unquote(link.split('#',1)[0])).resolve()
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


def build():
    evaluation = read(ROOT/'outputs/multiscene_automatic_evaluation/evaluation.json')
    assets = {item['id']:item for item in read(ROOT/'samples/multiscene_auto_20261025/manifest.json')}
    rows = {row['id']:row for row in evaluation['rows'] if row['id'] in IDS}
    if set(rows) != set(IDS):
        raise ValueError('All four local UI-generated evaluations are required')
    for subfolder in ('images', 'audio', 'narration'):
        (OUTPUT/subfolder).mkdir(parents=True, exist_ok=True)
    python = codec_python()
    scenes = [public_item(assets[identifier], rows[identifier], python) for identifier in IDS]
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
    (OUTPUT/'index.html').write_text(render(data), encoding='utf-8')
    return validate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(validate() if args.validate_only else build(), ensure_ascii=False))
