"""Audit detailed web-GPT versus short-category audio prompts on new panoramas.

This script never generates audio or downloads a model. It creates clearly
labelled dry comparison mixes only from the actual condition-specific stems,
matches the two conditions' integrated loudness with peak headroom, and can
then run an offline, fixed-text CLAP comparison. Cosines are not quality scores.
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
import platform
import sys
import time

import local_config
import numpy as np
from PIL import Image, ImageOps
from scipy import signal
from scipy.io import wavfile
from prepare_model_audio import SR, measure, save_audio
from gpt_scene_audio import parse_gpt_audio_response

ROOT = local_config.ROOT
OUT = ROOT/'outputs'/'gpt_audio_qa'
CONDITIONS = ('gpt_detailed', 'category_only_control')
CLAP_MODEL = 'laion/clap-htsat-unfused'
CLAP_REVISION = '8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a'
TEXTS = {
    'coastal_surf': [
        'Sea waves break at a sandy beach, then wash and recede along the shore.',
        'The sound of ocean surf, rhythmic swashing waves and receding water on a beach.'
    ],
    'rocky_stream_cascade': [
        'A rocky woodland stream flows and bubbles over stones with a small cascading waterfall.',
        'Continuous stream water, small falling cascades, liquid splashes and bubbling over rocks.'
    ],
    'road_vehicle_ambience': [
        'A quiet road ambience with occasional distant vehicle engines and tires passing on asphalt.',
        'Restrained urban traffic sound with low engine tones and soft passing tire noise.'
    ],
    'tree_leaf_rustling': [
        'The sound of leaves gently rustling in trees and shrubs.',
        'Small irregular leaf flutters and soft foliage brushing in a light breeze.'
    ],
    'gentle_wind': [
        'Soft outdoor wind and a faint airy breeze.',
        'A light wind blowing gently through an open outdoor area.'
    ],
    'strong_windstorm': [
        'A loud windstorm with strong roaring gusts.',
        'Powerful wind howling and roaring outside.'
    ],
    'steady_rain': [
        'Rain falling steadily outdoors with many pattering raindrops.',
        'Heavy continuous rainfall and wet rain noise.'
    ],
    'large_waterfall': [
        'A powerful large waterfall roaring with dense rushing water.',
        'The loud continuous roar of a large waterfall.'
    ],
    'quiet_lake_ripples': [
        'Small gentle ripples lap softly at the edge of a quiet lake.',
        'Soft inland lake water gently lapping against a still shore.'
    ],
    'isolated_drips': [
        'Individual isolated water drops drip slowly into water.',
        'Separate drops of water dripping with quiet gaps.'
    ],
    'birds': ['Bird calls and birds chirping outdoors.', 'Natural birdsong and short bird tweets.'],
    'insects': ['Insects buzzing and crickets chirping.', 'A continuous background of outdoor insect calls.'],
    'human_speech': ['People talking in a conversation.', 'A person speaking with an audible human voice.'],
    'music': ['Instrumental music playing.', 'Music with singing voices.'],
    'mechanical_hiss': ['An electric fan makes a steady mechanical hiss.', 'Broadband synthetic white noise.'],
    'abrupt_impacts': ['Sudden loud bangs and sharp repeated impacts.', 'Abrupt thuds and hard knocking sounds.'],
    'horns_sirens': ['Traffic horns honking and an emergency siren.', 'A loud vehicle horn followed by a siren.'],
}
TARGETS = {'surf': 'coastal_surf', 'stream': 'rocky_stream_cascade', 'traffic': 'road_vehicle_ambience'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def audio_signal(path):
    """Return mono float signal and actual PCM format without trusting a manifest."""
    path=Path(path); sr, pcm=wavfile.read(path); x=pcm.astype(np.float64)
    if pcm.dtype.kind == 'u':
        midpoint=(np.iinfo(pcm.dtype).max+1)/2; x=(x-midpoint)/midpoint
    elif pcm.dtype.kind == 'i':
        x/=float(max(abs(np.iinfo(pcm.dtype).min),np.iinfo(pcm.dtype).max))
    if x.ndim == 1:x=x[:,None]
    metadata={'file':str(path.resolve()), 'sha256':digest(path), 'sample_rate':int(sr),
        'channels':int(x.shape[1]), 'duration_seconds':len(x)/sr,
        'finite':bool(np.isfinite(x).all()), 'rms':float(np.sqrt(np.mean(x*x))),
        'peak_abs':float(np.max(np.abs(x))), 'sample_clipping_count':int(np.count_nonzero(np.abs(x)>=.9999))}
    return x.mean(axis=1), metadata


def _actual_rgb(path):
    with Image.open(path) as image:
        image=ImageOps.exif_transpose(image).convert('RGB')
        return hashlib.sha256(image.tobytes()).hexdigest()


def source_checks(plan, sample):
    provenance=plan.get('evidence',{}).get('gpt_provenance',{})
    response_path=Path(provenance.get('response_file',''))
    contact_path=Path(provenance.get('contact_sheet_file',sample['gpt_input_file']))
    response_hash=digest(response_path) if response_path.is_file() else None
    parsed_scene=None;parse_error=None
    if response_path.is_file():
        try:
            parsed=parse_gpt_audio_response(response_path.read_text(encoding='utf-8'))
            parsed_scene=next((x for x in parsed['scenes'] if x['id']==plan['scene_id']),None)
        except (ValueError,KeyError) as exc:parse_error=str(exc)
    expected_scene=plan.get('evidence',{}).get('gpt_response_scene')
    actual_rgb=_actual_rgb(sample['file'])
    visual_report_path=ROOT/'outputs'/'gpt_panorama'/plan['scene_id']/'report.json'
    visual_report=read_json(visual_report_path) if visual_report_path.is_file() else {}
    checks={
        'sample_file_hash_matches_manifest':digest(sample['file'])==sample['sha256'],
        'source_rgb_matches_sample_and_plan':actual_rgb==sample['sha256_rgb']==plan['image_sha256_rgb'],
        'source_rgb_matches_analyzed_panorama_report':visual_report.get('input',{}).get('sha256_rgb')==actual_rgb,
        'web_gpt_provider':provenance.get('provider')=='web_chatgpt',
        'gpt_image_hash_matches_plan':provenance.get('image_sha256_rgb')==plan['image_sha256_rgb'],
        'original_response_file_exists':response_path.is_file(),
        'original_response_sha256_matches':bool(response_hash and response_hash==provenance.get('response_sha256')),
        'original_response_scene_matches_plan_evidence':parsed_scene is not None and parsed_scene==expected_scene,
        'uploaded_contact_sheet_file_exists':contact_path.is_file(),
        'uploaded_contact_sheet_hash_matches':contact_path.is_file() and digest(contact_path)==provenance.get('contact_sheet_sha256')==sample['gpt_input_sha256'],
        'official_conversation_url':str(provenance.get('conversation_url','')).startswith(('https://chatgpt.com/c/','https://chat.openai.com/c/')),
    }
    return {'checks':checks,'all_passed':all(checks.values()),'source_rgb_sha256':actual_rgb,
        'original_response_file':str(response_path),'original_response_sha256':response_hash,
        'visual_report_file':str(visual_report_path),
        'response_parse_error':parse_error,'contact_sheet_file':str(contact_path),
        'provenance':provenance}


def condition_audio(folder, sample):
    plan=read_json(folder/'plan.json'); result=read_json(folder/'result.json')
    manifest_path=Path(result['manifest_path']); manifest=read_json(manifest_path)
    assets=Path(result['assets_dir']); planned={x['category']:x for x in plan['stems']}
    source=source_checks(plan,sample)
    checks={
        'condition_matches_folder':plan['condition']==folder.name,
        'scene_id_matches_folder':plan['scene_id']==folder.parent.name,
        'cache_key_matches_plan_contents':plan['cache_key']==json_hash({k:v for k,v in plan.items() if k!='cache_key'}),
        'result_and_manifest_cache_match':result['cache_key']==manifest['cache_key']==plan['cache_key'],
        'manifest_full_plan_hash_matches':manifest.get('plan_sha256')==json_hash(plan),
        'manifest_image_hash_matches':manifest.get('image_sha256_rgb')==plan['image_sha256_rgb'],
        'scene_specific_ai_materials':manifest.get('scene_specific') is True and manifest.get('ai_generated') is True,
        'generated_categories_match_plan':set(planned)=={x['category'] for x in manifest['items']},
        'original_source_checks_passed':source['all_passed'],
    }
    records=[];mix=np.zeros(28*SR,dtype=np.float64)
    response_stems={x['category']:x for x in plan['evidence']['gpt_response_scene']['stems'] if x.get('enabled',True)}
    for item in manifest['items']:
        category=item['category'];stem=planned[category]
        path=assets/'generated'/(category+'.wav');raw_path=assets/'raw'/(category+'.wav')
        audio, processed=audio_signal(path);_,raw=audio_signal(raw_path)
        generation=item['generation'];level=measure(audio)
        weight=stem.get('relative_level')
        weight_valid=isinstance(weight,(int,float)) and not isinstance(weight,bool) and math.isfinite(weight) and 0<weight<=1
        actual_model={k:generation.get(k) for k in ['model_revision','steps','cfg','dit_family','dit_precision','decoder']}
        item_checks={
            'processed_hash_matches_manifest':processed['sha256']==item['sha256'],
            'raw_hash_matches_manifest':raw['sha256']==item['raw_source_sha256']==generation['sha256'],
            'prompt_matches_plan':generation['prompt']==stem['prompt'],
            'seed_matches_plan':generation['seed']==stem['seed'],
            'raw_30s_stereo_44100':raw['duration_seconds']==30 and raw['channels']==2 and raw['sample_rate']==44100,
            'processed_28s_mono_32000':processed['duration_seconds']==28 and processed['channels']==1 and processed['sample_rate']==SR,
            'finite_and_non_silent':raw['finite'] and processed['finite'] and min(raw['rms'],processed['rms'])>1e-5,
            'no_sample_clipping':raw['sample_clipping_count']==processed['sample_clipping_count']==0,
            'peak_headroom':level['true_peak_4x_dbtp']<=-1.45,
            'declared_level_matches_actual':abs(level['integrated_lufs']-item['integrated_lufs'])<.02,
            'relative_level_is_valid':weight_valid,
            'model_revision_matches_plan':generation.get('model_revision')==plan['model']['revision'],
            'sampling_settings_match_plan':generation.get('steps')==plan['model']['steps'] and generation.get('cfg')==plan['model']['cfg'],
            'local_cache_folder_matches_key':assets.resolve()==(ROOT/'assets'/'scene_generated'/plan['cache_key']).resolve(),
        }
        if plan['condition']=='gpt_detailed':
            item_checks['detailed_prompt_is_unmodified_gpt_text']=stem['prompt']==response_stems[category]['prompt_en'].strip()
        if weight_valid and processed['sample_rate']==SR and len(audio)==len(mix):mix+=audio*float(weight)
        records.append({'category':category,'prompt':stem['prompt'],'seed':stem['seed'],'relative_level':weight,
            'raw':raw,'processed':processed,'measured_level':level,'dynamics':item.get('dynamics'),
            'generation_seconds':generation.get('official_cli_wall_seconds'),'actual_model':actual_model,
            'checks':item_checks,'all_passed':all(item_checks.values())})
    checks['all_stem_checks_passed']=all(x['all_passed'] for x in records)
    measured_mix=measure(mix)
    return {'condition':plan['condition'],'cache_key':plan['cache_key'],'image_sha256_rgb':plan['image_sha256_rgb'],
        'plan_file':str(folder/'plan.json'),'manifest_file':str(manifest_path),'manifest_sha256':digest(manifest_path),
        'source':source,'stems':records,'unmatched_dry_mix_measurement':measured_mix,
        'mix_protocol':'Sum actual processed mono stems at sample zero, weighted once by plan.stem.relative_level. No HRTF, panning, distance, offsets, normalization by source count, extra compressor, or old/reference audio.',
        'checks':checks,'all_passed':all(checks.values()),'_plan':plan,'_mix':mix,'_folder':folder}


def paired_scene(scene_folder,sample):
    values=[condition_audio(scene_folder/name,sample) for name in CONDITIONS]
    detailed,control=values;dp=detailed['_plan'];cp=control['_plan']
    ds={x['category']:x for x in dp['stems']};cs={x['category']:x for x in cp['stems']}
    protocol={
        'same_image':dp['image_sha256_rgb']==cp['image_sha256_rgb'],
        'same_model_settings':dp['model']==cp['model'],
        'same_categories':set(ds)==set(cs),
        'same_seed_per_stem':set(ds)==set(cs) and all(ds[k]['seed']==cs[k]['seed'] for k in ds),
        'same_relative_levels':set(ds)==set(cs) and all(ds[k]['relative_level']==cs[k]['relative_level'] for k in ds),
        'same_view_proxies':dp['views']==cp['views'],
        'same_original_web_gpt_source':dp['evidence']['gpt_provenance']==cp['evidence']['gpt_provenance'],
        'control_links_to_detailed_plan':cp.get('original_detailed_cache_key')==dp['cache_key'],
        'all_prompts_differ':set(ds)==set(cs) and all(ds[k]['prompt']!=cs[k]['prompt'] for k in ds),
        'all_actual_generated_stems_differ':all(next(x for x in detailed['stems'] if x['category']==k)['raw']['sha256']!=next(x for x in control['stems'] if x['category']==k)['raw']['sha256'] for k in ds),
    }
    # A small quantization margin ensures the re-read PCM stays below -1.5 dBTP.
    operational_ceiling=-1.55
    target=min([-23.]+[x['unmatched_dry_mix_measurement']['integrated_lufs']+operational_ceiling-x['unmatched_dry_mix_measurement']['true_peak_4x_dbtp'] for x in values])
    for value in values:
        output=value['_folder']/'matched_mix.wav'
        measurement=save_audio(output,value['_mix'],target)
        value['matched_mix']={**measurement,'paired_target_lufs':target,'requested_peak_ceiling_dbtp':-1.5,
            'operational_peak_ceiling_dbtp':operational_ceiling,'additional_dynamic_processing':False}
        write_json(value['_folder']/'matched_mix.json',value['matched_mix'])
        value['checks']['matched_mix_headroom']=measurement['true_peak_4x_dbtp']<=-1.5
        value['checks']['matched_mix_duration']=measurement['duration_seconds']==28
        value['all_passed']=all(value['checks'].values())
    difference=detailed['matched_mix']['integrated_lufs']-control['matched_mix']['integrated_lufs']
    protocol['matched_pair_loudness_within_0_01_lu']=abs(difference)<.01
    target_categories=[x for x in ds if x in TARGETS]
    if len(target_categories)!=1:raise ValueError('Exactly one primary surf/stream/traffic category is required per scene for fixed-label evaluation')
    for value in values:
        for key in ['_plan','_mix','_folder']:value.pop(key)
    return {'scene_id':scene_folder.name,'scene_title':dp.get('scene_title',scene_folder.name),
        'image_sha256_rgb':dp['image_sha256_rgb'],'target_label':TARGETS[target_categories[0]],
        'paired_target_lufs':target,'gpt_minus_control_loudness_lu':difference,
        'protocol_checks':protocol,'all_passed':all(protocol.values()) and all(x['all_passed'] for x in values),
        'conditions':{x['condition']:x for x in values}}


def _feature_windows(path):
    audio,meta=audio_signal(path);source_rate=meta['sample_rate']
    common=math.gcd(source_rate,48000);audio=signal.resample_poly(audio,48000//common,source_rate//common).astype(np.float32)
    result=[]
    for start in np.linspace(0,max(0,len(audio)/48000-10),3):
        clip=audio[round(start*48000):round(start*48000)+480000]
        if len(clip)<480000:clip=np.pad(clip,(0,480000-len(clip)))
        rms=float(np.sqrt(np.mean(clip*clip)));peak=float(np.max(np.abs(clip)))
        gain=min(.05/max(rms,1e-12),.95/max(peak,1e-12))
        result.append((clip*gain,{'start_seconds':float(start),'duration_seconds':10.,'feature_input_gain':gain,'original_window_rms':rms}))
    return result,meta


def run_clap(scenes):
    """Only called after generation, with explicitly local cached official weights."""
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
    import torch
    from transformers import ClapModel,ClapProcessor
    device='cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(min(8,torch.get_num_threads()));torch.manual_seed(20261025)
    processor=ClapProcessor.from_pretrained(CLAP_MODEL,revision=CLAP_REVISION,trust_remote_code=False,local_files_only=True)
    model=ClapModel.from_pretrained(CLAP_MODEL,revision=CLAP_REVISION,use_safetensors=False,
        trust_remote_code=False,local_files_only=True).eval().to(device)
    labels=list(TEXTS);texts=[text for pair in TEXTS.values() for text in pair]
    with torch.inference_mode():
        inputs=processor(text=texts,return_tensors='pt',padding=True)
        text_features=model.get_text_features(**{k:v.to(device) for k,v in inputs.items()})
        text_features=torch.nn.functional.normalize(text_features.float(),dim=-1)
    results=[];embeddings={}
    for scene in scenes:
        for condition in CONDITIONS:
            item=scene['conditions'][condition];path=item['matched_mix']['file'];windows,meta=_feature_windows(path)
            with torch.inference_mode():
                inputs=processor(audios=[x for x,_ in windows],sampling_rate=48000,return_tensors='pt',padding='repeatpad',truncation='rand_trunc')
                features=model.get_audio_features(**{k:v.to(device) for k,v in inputs.items()})
                features=torch.nn.functional.normalize(features.float(),dim=-1)
                cosines=(features@text_features.T).cpu().numpy()
                average=torch.nn.functional.normalize(features.mean(dim=0),dim=-1).cpu().numpy()
            identifier=scene['scene_id']+'/'+condition;embeddings[identifier]=average;window_results=[]
            for (_,window),scores in zip(windows,cosines):
                means={name:float(np.mean(scores[2*i:2*i+2])) for i,name in enumerate(labels)}
                window_results.append({**window,'label_mean_cosines':means})
            means={name:float(np.mean([x['label_mean_cosines'][name] for x in window_results])) for name in labels}
            ranking=sorted(means,key=means.get,reverse=True);target=scene['target_label']
            row={'id':identifier,'scene_id':scene['scene_id'],'condition':condition,'file':str(path),
                'audio_sha256':meta['sha256'],'windows':window_results,'mean_label_cosines':means,
                'ranking':ranking,'target_label':target,'target_rank':ranking.index(target)+1,'target_mean_cosine':means[target]}
            results.append(row)
            print(json.dumps({'id':identifier,'target_rank':row['target_rank'],'target_cosine':round(means[target],4),'top3':ranking[:3]},ensure_ascii=False),flush=True)
    pairs={};separation={}
    for condition in CONDITIONS:
        rows=[]
        for a,b in itertools.combinations(scenes,2):
            value=float(np.dot(embeddings[a['scene_id']+'/'+condition],embeddings[b['scene_id']+'/'+condition]))
            rows.append({'a':a['scene_id'],'b':b['scene_id'],'mean_audio_embedding_cosine':value})
        pairs[condition]=rows
        separation[condition]=float(np.mean([x['mean_audio_embedding_cosine'] for x in rows])) if rows else None
    delta=None
    if all(separation[x] is not None for x in CONDITIONS):delta=separation['gpt_detailed']-separation['category_only_control']
    within=[{'scene_id':x['scene_id'],'detailed_control_embedding_cosine':float(np.dot(embeddings[x['scene_id']+'/gpt_detailed'],embeddings[x['scene_id']+'/category_only_control']))} for x in scenes]
    del model
    if device=='cuda':torch.cuda.empty_cache()
    return {'status':'completed','model':CLAP_MODEL,'revision':CLAP_REVISION,'offline_local_cache_only':True,
        'device':device,'python':platform.python_version(),'torch':torch.__version__,
        'method':'Fixed 17-label/34-text cosine proximity, three evenly spaced 10-second 48kHz windows of each actual matched 28-second dry mix, no softmax.',
        'feature_preprocessing':'Each 48kHz window is RMS-scaled toward .05 with a .95 sample-peak cap; explicitly separate from the stored paired LUFS listening mixes.',
        'text_prompts':TEXTS,'files':results,'scene_embedding_pairs_by_condition':pairs,
        'mean_between_scene_embedding_cosine':separation,'detailed_minus_control_mean_between_scene_cosine':delta,
        'detailed_is_less_similar_between_scenes_in_this_representation':delta<0 if delta is not None else None,
        'within_scene_condition_embedding_cosine':within,
        'limits':['Lower between-scene embedding cosine means larger difference only in this feature representation, not better quality or human scene recognition.',
            'Cosines and ranks depend on this explicit text set; they are not calibrated event probabilities or quality scores.',
            'Does not prove the presence or absence of birds, insects, voices, horns, music or other unintended events.',
            'The short-category control still uses GPT-selected source categories, levels and positions, so this comparison isolates prompt detail within that design, not the whole effect of GPT versus no GPT.',
            'One seed per stem and scene gives a small illustrative comparison, not a replicated causal or statistical result.',
            'Postprocessed application stems are evaluated; generation and dynamics effects cannot be separated as original model quality.',
            'No subjective headset listening or target-user experiment was performed.']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--signal-only',action='store_true')
    parser.add_argument('--scene',action='append');args=parser.parse_args()
    started=time.perf_counter();sample_path=ROOT/'samples'/'panoramas_gpt'/'manifest.json'
    samples={x['id']:x for x in read_json(sample_path)}
    folders=sorted(x for x in (ROOT/'outputs'/'gpt_audio_demo').iterdir() if x.is_dir() and (x/'gpt_detailed'/'plan.json').is_file())
    if args.scene:folders=[x for x in folders if x.name in set(args.scene)]
    if not folders:raise RuntimeError('No paired GPT audio demo plans found; complete generation before running this check.')
    scenes=[paired_scene(folder,samples[folder.name]) for folder in folders]
    records=[stem for s in scenes for c in s['conditions'].values() for stem in c['stems']]
    checks={
        'all_scene_and_pair_checks_passed':all(x['all_passed'] for x in scenes),
        'different_scene_rgb_fingerprints':len({x['image_sha256_rgb'] for x in scenes})==len(scenes),
        'every_condition_has_independent_cache_key':len({c['cache_key'] for s in scenes for c in s['conditions'].values()})==len(scenes)*2,
        'all_generated_raw_wav_hashes_distinct':len({x['raw']['sha256'] for x in records})==len(records),
        'all_processed_stem_hashes_distinct':len({x['processed']['sha256'] for x in records})==len(records),
        'all_full_mix_pairs_matched_within_0_01_lu':all(abs(x['gpt_minus_control_loudness_lu'])<.01 for x in scenes),
    }
    engineering=all(checks.values())
    report={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
        'method':'Verify exact image, web reply and generated audio; sum only actual condition-specific stems, paired LUFS/peak matching, then optional offline fixed-label CLAP.',
        'scene_count':len(scenes),'condition_count':2,'generated_stem_count':len(records),
        'all_engineering_checks_passed':engineering,'independence_checks':checks,'scenes':scenes,
        'clap':{'status':'not_run','reason':'--signal-only requested' if args.signal_only else 'engineering checks failed'},
        'subjectively_auditioned':False,'no_dependencies_installed':True,
        'comparison_boundary':'The stored dry mixes omit direction and distance to isolate generated content; the spatial demo is a separate application preview.'}
    if engineering and not args.signal_only:report['clap']=run_clap(scenes)
    report['wall_seconds']=round(time.perf_counter()-started,3)
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/('signal_verification.json' if args.signal_only else 'evaluation.json');write_json(path,report)
    compact_clap={'status':report['clap']['status'],'conditions':{},'difference':{}}
    if report['clap']['status']=='completed':
        for condition in CONDITIONS:
            cosine=report['clap']['mean_between_scene_embedding_cosine'][condition]
            targets=[]
            for value in report['clap']['files']:
                if value['condition']!=condition:continue
                targets.append({'scene_id':value['scene_id'],'target_label':value['target_label'],
                    'target_mean_cosine':value['target_mean_cosine'],'target_rank':value['target_rank'],
                    'top_label':value['ranking'][0],'top_mean_cosine':value['mean_label_cosines'][value['ranking'][0]],
                    'top_confusions':[{'label':label,'mean_cosine':value['mean_label_cosines'][label]}
                                      for label in value['ranking'] if label!=value['target_label']][:3]})
            compact_clap['conditions'][condition]={'mean_pairwise_cosine':cosine,
                'mean_pairwise_distance':1-cosine if cosine is not None else None,
                'pairwise':report['clap']['scene_embedding_pairs_by_condition'][condition],
                'target_results':targets}
        delta=report['clap']['detailed_minus_control_mean_between_scene_cosine']
        compact_clap['difference']={'detailed_minus_control_mean_pairwise_cosine':delta,
            'detailed_minus_control_mean_pairwise_distance':-delta if delta is not None else None,
            'detailed_is_more_separated_in_this_representation':delta<0 if delta is not None else None,
            'boundary':'Cosine distance is 1-cosine. This is feature-space separation of three illustrative scenes, not human recognition, quality, probability, or a replicated experiment.'}
    brief={'scene_count':len(scenes),'condition_count':2,'generated_stem_count':len(records),'all_engineering_checks_passed':engineering,
        'independence_checks':checks,'paired_loudness':[{'scene_id':x['scene_id'],'target_lufs':x['paired_target_lufs'],'difference_lu':x['gpt_minus_control_loudness_lu']} for x in scenes],
        'clap_status':report['clap']['status'],'content_results':[{k:x[k] for k in ['id','target_label','target_rank','target_mean_cosine']} for x in report['clap'].get('files',[])],
        'mean_between_scene_embedding_cosine':report['clap'].get('mean_between_scene_embedding_cosine'),
        'detailed_minus_control_mean_between_scene_cosine':report['clap'].get('detailed_minus_control_mean_between_scene_cosine'),
        'clap':compact_clap,
        'subjectively_auditioned':False,'report_file':str(path)}
    write_json(OUT/('signal_summary.json' if args.signal_only else 'summary.json'),brief)
    print(json.dumps(brief,ensure_ascii=False,indent=2),flush=True)
    if not engineering:raise SystemExit('One or more image, reply, audio or paired-control checks failed; inspect the written verification report.')


if __name__=='__main__':main()
