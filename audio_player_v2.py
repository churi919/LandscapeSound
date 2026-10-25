"""Long illustrative textures with per-category budgets and a preserved A/B mode."""
import base64
import html
import json
import hashlib
import math
import re
import wave
from pathlib import Path
from audio_layers import plan_audio_layers
from ui_i18n import get_language, normalize_language

ROOT=Path(__file__).resolve().parent
CATEGORY_LABELS={'trees':'风叶','water':'水声','bird':'鸟鸣（人工）',
                 'surf':'海浪','stream':'流水','traffic':'道路背景','wind':'风声'}
CATEGORY_LABELS_EN={'trees':'Leaves','water':'Water','bird':'Bird sound (manual example)',
                    'surf':'Surf','stream':'Stream','traffic':'Road ambience','wind':'Wind'}
GENERATED_CATEGORIES=frozenset(CATEGORY_LABELS)-{'bird'}
CATEGORY_LEVELS={'trees':.8,'water':.7,'bird':.5,'surf':.7,'stream':.7,'traffic':.55,'wind':.6}

_TEMPLATE_EN={
    'lang="zh-CN"':'lang="en"',
    '景观声音与描述播放器':'Soundscape audio and narration player',
    '连续声景试听':'Continuous soundscape preview',
    '同类区域整理成连续纹理，避免同一段声音同步堆叠。可用素材会在下方列出，均用于模拟预体验，并非照片现场录音。':
        'Regions of the same type form continuous textures, avoiding synchronized copies. Available audio is listed below. It is a simulation, not a recording of the photographed site.',
    '声音版本':'Audio version','空间方式':'Spatial mode',
    '深度驱动双耳声景':'Relative-depth binaural soundscape','普通混音对照':'Plain-mix comparison',
    '播放声景':'Play soundscape','停止全部声音':'Stop all audio',
    '左右耳校准':'Left/right headphone check','下载试听设置':'Download playback settings',
    '朗读配音':'Narration voice','朗读景观描述':'Read original guide',
    '朗读音量':'Narration volume','总音量':'Master volume',
    '尚未播放。建议佩戴立体声耳机。':'Not playing. Stereo headphones are recommended.',
    '调整图像区域的方位和远近':'Adjust region direction and virtual distance',
    '这里的修改仅用于试听。需要保存图像分析校正时，请使用应用中的校正表单。':
        'These changes affect this preview only. Use the application correction form to save changes to the image analysis.',
    '景观描述与素材来源':'Original guide and audio sources',
    '可选版本由当前已备齐的素材决定；有对应自然录音时才提供录音选项。各条件采用相同的连续混音、方位和距离规则，具体对照条件以评估页为准。当前试听尚不能代替主观听感实验；人工鸟鸣选项若存在，仍为程序示例。':
        'Available versions depend on verified audio files. A recorded-audio option appears only when matching recordings are available. Conditions share mixing, direction and distance rules; consult the evaluation page for the comparison protocol. This preview is not a subjective listening study. Any manual bird option remains a procedural example.',
    '播放状态与工程自检':'Playback status and engineering checks',
    '静音检验新版混音':'Run silent mix check',
}


def safe_json(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')


def original_text_language(text):
    """Choose a local system-voice family from content, never the UI locale.

    This lightweight hint only distinguishes the application's Chinese guides
    from its English previews. It does not translate or rewrite the text.
    """
    text=str(text)
    if re.search(r'[\u3400-\u9fff]',text):return 'zh-CN'
    if re.search(r'[A-Za-z]',text):return 'en'
    return 'und'


def _read_manifest(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}


def _ai_generation_declared(metadata):
    """A filename alone never upgrades ordinary recordings into AI materials."""
    if not (metadata.get('ai_generated') is True or metadata.get('not_ai_generated') is False):
        return False
    model=metadata.get('model',metadata.get('model_id'))
    if isinstance(model,dict):model=model.get('id',model.get('name',model.get('model_id')))
    return isinstance(model,str) and bool(model.strip())


def _generated_items(assets_dir,metadata):
    if not _ai_generation_declared(metadata):return {}
    result={}
    items=metadata.get('items',[])
    if not isinstance(items,list):return result
    for item in items:
        if not isinstance(item,dict):continue
        category=item.get('category')
        if category not in GENERATED_CATEGORIES:continue
        target=assets_dir/'generated'/(category+'.wav')
        declared=item.get('file')
        if declared is not None and Path(str(declared)).name!=target.name:continue
        try:
            with wave.open(str(target),'rb') as wav:
                frames=wav.getnframes()
                if frames<=0 or wav.getnchannels() not in (1,2) or wav.getframerate()<8000:continue
                if len(wav.readframes(frames))!=frames*wav.getnchannels()*wav.getsampwidth():continue
            expected=item.get('sha256',item.get('wav_sha256'))
            if expected and hashlib.sha256(target.read_bytes()).hexdigest()!=expected:continue
        except (OSError,EOFError,wave.Error):
            continue
        result[category]=(target,item)
    return result


def _narration_payload(description):
    """Embed only checksum-verified neural speech for this exact UTF-8 text."""
    digest=hashlib.sha256(description.encode('utf-8')).hexdigest()
    result={'text_sha256':digest,'default_voice':None,'voices':[],'available':False}
    try:
        from narration import get_narration_assets
        cached=get_narration_assets(description,root=ROOT)
    except (ImportError,OSError,ValueError,TypeError):
        return result
    if not isinstance(cached,dict) or cached.get('text_sha256')!=digest:
        return result
    for entry in cached.get('voices',[]):
        if not isinstance(entry,dict) or entry.get('neural') is not True:
            continue
        voice_id=entry.get('voice_id')
        if not isinstance(voice_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',voice_id):
            continue
        if entry.get('mime_type') not in {'audio/mpeg','audio/wav','audio/ogg'}:
            continue
        try:
            encoded=entry.get('audio_base64')
            if not isinstance(encoded,str):
                encoded=base64.b64encode(Path(entry['file']).read_bytes()).decode('ascii')
            raw=base64.b64decode(encoded,validate=True)
        except (OSError,KeyError,ValueError,TypeError):
            continue
        if not raw or hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):
            continue
        record={key:entry[key] for key in ['voice_id','label','provider','mime_type','sha256','duration_seconds','neural'] if key in entry}
        record.update(audio_base64=encoded,field_recording=False)
        result['voices'].append(record)
    ids={item['voice_id'] for item in result['voices']}
    if ids:
        result['available']=True
        preferred=cached.get('default_voice')
        result['default_voice']=preferred if preferred in ids else result['voices'][0]['voice_id']
    return result


def render_audio(sources,description,assets_dir,duration=20,language=None):
    language=normalize_language(language or get_language())
    translated=lambda chinese,english:english if language=='en' else chinese
    labels=CATEGORY_LABELS_EN if language=='en' else CATEGORY_LABELS
    assets_dir=Path(assets_dir)
    clean=[]
    for index,source in enumerate(sources):
        if source.get('category') not in CATEGORY_LABELS:continue
        a=float(source.get('azimuth',0));r=float(source.get('virtual_radius',4.8))
        if not math.isfinite(a) or not math.isfinite(r):raise ValueError('Audio positions must be finite')
        entry=dict(source);entry.update(id=str(source.get('id',f'source-{index}')),label=str(source.get('label',source['category'])),
                                     azimuth=max(-90,min(90,a)),virtual_radius=max(1.8,min(7.8,r)),enabled=bool(source.get('enabled',True)))
        near=source.get('near_score');entry['near_score']=float(near) if near is not None and math.isfinite(float(near)) else None
        area=source.get('area_fraction',1);entry['area_fraction']=float(area) if isinstance(area,(int,float)) and math.isfinite(area) and 0<area<=1 else 1.
        spread=source.get('spread_degrees',0)
        entry['spread_degrees']=max(0.,min(45.,float(spread))) if isinstance(spread,(int,float)) and math.isfinite(spread) else 0.
        relative=source.get('relative_level')
        if isinstance(relative,(int,float)) and math.isfinite(relative):entry['relative_level']=max(0.,min(1.,float(relative)))
        else:entry.pop('relative_level',None)
        clean.append(entry)
    categories={s['category'] for s in clean};audio={};natural_available=True
    metadata=_read_manifest(assets_dir/'natural'/'manifest.json')
    legacy_metadata=_read_manifest(assets_dir/'legacy'/'audio_manifest.json')
    generated_metadata=_read_manifest(assets_dir/'generated'/'manifest.json')
    generated_items=_generated_items(assets_dir,generated_metadata)
    origins={'natural':{},'legacy':{},'generated':{}}
    for category in sorted(categories):
        old=assets_dir/'legacy'/(category+'.wav')
        if not old.is_file():old=assets_dir/(category+'.wav')
        if old.is_file():
            audio['legacy_'+category]=base64.b64encode(old.read_bytes()).decode('ascii')
            origins['legacy'][category]={'kind':'procedural','ai_generated':False,'file':str(old),
                                         'pictured_site_recording':False}
        new=assets_dir/'natural'/(category+'.wav')
        if category=='bird':new=old
        if not new.is_file():
            natural_available=False
            # Historical tree/water controls may explicitly offer their same-
            # category procedural texture. Never borrow another sound class.
            new=old
        if new.is_file():
            audio['natural_'+category]=base64.b64encode(new.read_bytes()).decode('ascii')
            origins['natural'][category]={'kind':'procedural' if new==old else 'field_recording',
                'ai_generated':False,'file':str(new),'pictured_site_recording':False}
        if category=='bird' and 'legacy_bird' in audio:
            audio['generated_bird']=audio['legacy_bird']
            origins['generated'][category]=dict(origins['legacy'][category])
        elif category in generated_items:
            generated_path,item=generated_items[category]
            audio['generated_'+category]=base64.b64encode(generated_path.read_bytes()).decode('ascii')
            origins['generated'][category]={'kind':'ai_generated','ai_generated':True,
                'file':str(generated_path),'pictured_site_recording':False,'generation':item,
                'model':generated_metadata.get('model',generated_metadata.get('model_id'))}
    active={s['category'] for s in clean if s['enabled']}
    required=active-{'bird'}
    generated_available=bool(required) and required.issubset(generated_items) and active.issubset(origins['generated'])
    profiles={
        'natural':{'label':translated('自然录音：连续纹理','Recorded audio: continuous texture'),'provenance':metadata,'categories':origins['natural']},
        'legacy':{'label':translated('原版：程序点声源','Legacy: procedural point sources'),'provenance':legacy_metadata,'categories':origins['legacy']}}
    if generated_items:
        model_label=generated_metadata.get('model',generated_metadata.get('model_id'))
        if isinstance(model_label,dict):model_label=model_label.get('name',model_label.get('id'))
        model_label=model_label.strip() if isinstance(model_label,str) and model_label.strip() else 'Stable Audio 3'
        if language=='en':model_label=model_label.replace(' · 本全景专属',' · scene-specific')
        profiles['generated']={'label':translated('AI生成：','AI generated: ')+model_label,'provenance':generated_metadata,
                               'categories':origins['generated']}
    available_presets=(['generated'] if generated_available else [])+[key for key in ['natural','legacy'] if active.issubset(origins[key])]
    if not available_presets and active:
        raise FileNotFoundError('No complete material preset for enabled categories: '+', '.join(sorted(active)))
    default_preset=available_presets[0] if available_presets else 'natural'
    category_levels={}
    for category in sorted(categories):
        specified=[s for s in clean if s['category']==category and 'relative_level' in s]
        category_levels[category]=(sum(s['relative_level']*s['area_fraction'] for s in specified)/sum(s['area_fraction'] for s in specified)) if specified else CATEGORY_LEVELS[category]
    options=''.join('<option value="'+key+'"'+(' selected' if key==default_preset else '')+'>'+html.escape(profiles[key]['label'])+'</option>' for key in available_presets)
    payload={'sources':clean,'layers':plan_audio_layers(clean),'description':str(description),'language':language,
             'description_language':original_text_language(description),
             'duration':max(3,min(60,float(duration))),'audio':audio,'natural_available':natural_available,
             'provenance':metadata,'profiles':profiles,'generated_available':generated_available,
             'available_presets':available_presets,
             'category_labels':{category:labels[category] for category in sorted(categories)},
             'category_levels':category_levels,
             'default_preset':default_preset,
             'comparison_fixed_offsets':generated_metadata.get('comparison_fixed_offsets') is True,
             'narration':_narration_payload(str(description)),'version':2}
    template=(ROOT/'audio_player_template.html').read_text(encoding='utf-8')
    if language=='en':
        # Translate only the static template before inserting any user text,
        # provenance, payload or script. Original descriptions stay verbatim.
        for chinese,english in sorted(_TEMPLATE_EN.items(),key=lambda pair:len(pair[0]),reverse=True):
            template=template.replace(chinese,english)
    script=(ROOT/'audio_player.js').read_text(encoding='utf-8')
    controls=''.join('<label for="'+category+'-level">'+html.escape(labels[category])+
                     ' <input id="'+category+'-level" type="range" min="0" max="1" step="0.05" value="'+str(category_levels[category])+'"></label>'
                     for category in sorted(categories))
    substitutions={'__PAYLOAD__':safe_json(payload),'__SCRIPT__':script,'__DESCRIPTION__':html.escape(str(description)),
                   '__PRESET_OPTIONS__':options,'__CATEGORY_CONTROLS__':controls}
    return re.sub(r'__PAYLOAD__|__SCRIPT__|__DESCRIPTION__|__PRESET_OPTIONS__|__CATEGORY_CONTROLS__',lambda match:substitutions[match.group(0)],template)
