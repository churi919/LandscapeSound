"""Exploratory acoustic refinements of web-GPT scene plans.

The changed audio prompts are local edits, not new web-GPT output. Original
visual facts, image provenance, seeds and rendering proxies remain fixed.
All candidates and raw model output are retained for review.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

from local_config import ROOT
from scene_audio_runtime import ensure_scene_audio, load_scene_audio


OUT = ROOT/'outputs'/'audio_refinement'
PROMPTS = {
    'xanderklinge': {
        'refinement_stream_1': (
            "A close field recording of a small rocky woodland brook. A connected stream of water "
            "runs between uneven stones with a rounded, low liquid burble and clearly audible "
            "babbling currents. Little eddies fill rock hollows, release a hollow gloop, and join "
            "the main current again. A narrow short cascade adds occasional soft wet splashes "
            "in one localized place. The continuous moving-water body stays audible beneath "
            "the changing gurgles. Natural uneven phrasing, restrained volume, intimate detail, "
            "and gradual small variations throughout a thirty-second outdoor recording."
        ),
        'refinement_stream_2': (
            "A small forest stream pours over a low stone ledge into a shallow rock pool. "
            "Hear a narrow flowing ribbon, rounded bubbling, and a close irregular glug-glug "
            "as water swirls through pockets between stones. Soft connected liquid movement "
            "continues underneath several short, uneven splash clusters. The small falls occupy "
            "one nearby spot, while the brook carries a mellow flowing undercurrent onward. "
            "The texture is fluid and hollow, with changing resonant water cavities and gentle "
            "babbling energy, steady but naturally varied over thirty seconds."
        ),
        'refinement_stream_3': (
            "An intimate recording of babbling creek water flowing through a narrow rocky channel. "
            "The main texture is continuous rounded water chatter: little low gurgles, short "
            "bubbly rolls, and uneven hollow liquid notes created where the current meets stones. "
            "A short smooth spill occasionally gathers into a small localized splash, then "
            "returns to the softer burbling current. Keep the liquid body warm and close, "
            "with distinct connected flow, small shifting eddies, and relaxed irregular changes "
            "rather than a flat sustained wash. Thirty seconds of natural stream movement."
        ),
        'refinement_stream_4': (
            "A shallow woodland brook babbling through gaps between rounded stones. "
            "Close hollow gurgles and mellow bubbling pulses rise and sink with the connected "
            "current. Smooth localized liquid flow, soft resonant glugs and a few short "
            "little splashes. Calm natural variation."
        ),
    },
    'fish_hoek_beach': {
        'refinement_surf_1': (
            "A quiet sandy seashore with clearly shaped individual ocean swells. A low rounded "
            "surge builds slowly, opens into a short soft foamy swash, and drains away in a "
            "long fine sandy backwash. Several seconds of lighter water separate the next "
            "arrival. Each wave has a slightly different length and strength; a few overlap "
            "at the edge before the shore becomes quieter again. Broad open coastal space, "
            "gentle low-frequency swell beneath the brief brighter foam, slow irregular "
            "rise-and-fall contours over a continuous thirty-second recording."
        ),
    },
    'urban_street_04': {
        'refinement_traffic_1': (
            "A sparse distant urban road vehicle ambience. One restrained engine note and "
            "soft grainy tire roll approach gradually along asphalt, become modestly clearer, "
            "then recede with a falling engine tone. A long quiet interval follows before "
            "another distant vehicle passes at a different speed and pitch. Keep the individual "
            "motor and rolling-tire events distinct, with subtle low mechanical harmonics and "
            "gentle movement through space. Only a few unhurried vehicle passages over thirty "
            "seconds, a subdued background, and substantial calm gaps between passes."
        ),
    },
}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def json_hash(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def refined_plan(original,variant,prompt):
    if len(original['stems'])!=1:
        raise ValueError('This exploratory round holds one primary stem per scene')
    plan=copy.deepcopy(original)
    plan['condition']=variant
    plan['planner_version']='local-acoustic-refinement-after-web-gpt-v1'
    plan['original_detailed_cache_key']=original['cache_key']
    plan['evidence']['acoustic_refinement']={
        'prompt_author':'Local acoustic refinement after webGPT; not unmodified web-GPT output',
        'source_plan_cache_key':original['cache_key'],
        'changed':['positive audio prompt','prompt provenance and experiment condition'],
        'held_constant':['image','web-GPT visual facts','source categories','per-stem seed',
            'model and sampling settings','relative levels','per-view visual proxies','postprocessing algorithm'],
        'goal':'Reduce rain-like broadband/patter confusion while preserving connected rocky brook flow; separate surf swell and sparse engine event structures.',
        'exploratory_selection':'Three stream prompts, one surf and one traffic prompt, retained without hiding failed candidates. Selection uses explicit CLAP labels, not human listening.',
    }
    for stem in plan['stems']:
        stem['prompt']=prompt
        stem['prompt_source']='local_acoustic_refinement_after_web_gpt'
    plan['items']=copy.deepcopy(plan['stems'])
    plan.pop('cache_key',None);plan['cache_key']=json_hash(plan)
    return plan


def load_optimized_plan(report,scene_id,root=None):
    """Read a selected local refinement only for the exact original image."""
    root=Path(root or ROOT)
    path=root/'outputs'/'audio_refinement'/'selected'/scene_id/'plan.json'
    if not path.is_file():return None
    plan=read(path)
    if plan.get('image_sha256_rgb')!=report.get('input',{}).get('sha256_rgb'):return None
    if plan.get('cache_key')!=json_hash({k:v for k,v in plan.items() if k!='cache_key'}):
        raise ValueError('Selected acoustic plan has been changed without a new cache key')
    if plan.get('planner_version')=='local-acoustic-refinement-after-web-gpt-v1':
        if not all(x.get('prompt_source')=='local_acoustic_refinement_after_web_gpt' for x in plan['stems']):
            raise ValueError('Selected acoustic prompt provenance is incomplete')
    else:
        # A tested new prompt can regress. An unchanged previous plan may be
        # retained transparently; it is never relabelled as newly generated.
        selection_file=root/'outputs'/'audio_refinement'/'selection.json'
        selection=read(selection_file).get(scene_id,{}) if selection_file.is_file() else {}
        retained_kind=selection.get('source_condition')
        previous_condition='category_only_control' if retained_kind=='retained_previous_short_reference' else 'gpt_detailed'
        previous=root/'outputs'/'gpt_audio_demo'/scene_id/previous_condition/'plan.json'
        if (not previous.is_file() or plan!=read(previous)
                or retained_kind not in {'retained_previous_web_gpt','retained_previous_short_reference'}
                or selection.get('cache_key')!=plan['cache_key']):
            raise ValueError('Unexpected or unverified retained acoustic plan')
    if load_scene_audio(plan,root) is None:
        return None
    return plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--only',default='')
    args=parser.parse_args()
    batch_file=OUT/'candidate_runs.json'
    batch=read(batch_file) if batch_file.is_file() else []
    for scene_id,variants in PROMPTS.items():
        original=read(ROOT/'outputs'/'gpt_audio_demo'/scene_id/'gpt_detailed'/'plan.json')
        for variant,prompt in variants.items():
            if args.only and args.only not in {scene_id,variant}:continue
            folder=OUT/'candidates'/scene_id/variant
            plan=refined_plan(original,variant,prompt);write(folder/'plan.json',plan)
            print('START '+scene_id+' '+variant+' '+plan['cache_key'][:12],flush=True)
            started=time.perf_counter();result=ensure_scene_audio(plan,root=ROOT)
            result['wall_seconds_including_postprocessing']=time.perf_counter()-started
            write(folder/'result.json',result)
            row={'scene_id':scene_id,'variant':variant,'cache_key':plan['cache_key'],
                'plan_file':str(folder/'plan.json'),'result_file':str(folder/'result.json'),
                'assets_dir':result['assets_dir'],'manifest_path':result['manifest_path'],
                'generated':result['generated'],'reused':result['reused'],
                'wall_seconds_including_postprocessing':result['wall_seconds_including_postprocessing']}
            old=next((i for i,x in enumerate(batch) if x['scene_id']==scene_id and x['variant']==variant),None)
            if old is None:batch.append(row)
            else:batch[old]=row
            write(batch_file,batch)
            print('DONE '+scene_id+' '+variant+' '+str(round(result['wall_seconds_including_postprocessing'],2))+'s',flush=True)
    print('Requested exploratory candidates complete.',flush=True)


if __name__=='__main__':main()
