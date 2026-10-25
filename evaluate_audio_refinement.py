"""Compare retained web-GPT output with local acoustic refinement candidates.

Selection is exploratory on the same explicit CLAP text set. Audio features
are not human hearing, naturalness, event probability, or user benefit scores.
This script never generates new model audio or changes old experiment files.
"""
from __future__ import annotations

import itertools
import argparse
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

import numpy as np
import local_config
from prepare_model_audio import measure, save_audio
import evaluate_gpt_audio_demo as base
from optimize_scene_audio import OUT, ROOT, read, write


SCENES=['fish_hoek_beach','xanderklinge','urban_street_04']


def _protocol(original,new):
    a=original['stems'];b=new['stems']
    return {
        'same_image':original['image_sha256_rgb']==new['image_sha256_rgb'],
        'same_seed':[x['seed'] for x in a]==[x['seed'] for x in b],
        'same_model':original['model']==new['model'],
        'same_categories':[x['category'] for x in a]==[x['category'] for x in b],
        'same_relative_levels':[x['relative_level'] for x in a]==[x['relative_level'] for x in b],
        'same_view_proxies':original['views']==new['views'],
        'same_original_web_reply':original['evidence']['gpt_provenance']==new['evidence']['gpt_provenance'],
        'changed_prompt':[x['prompt'] for x in a]!=[x['prompt'] for x in b],
        'local_edits_not_claimed_as_web_reply':all(x.get('prompt_source')=='local_acoustic_refinement_after_web_gpt' for x in b),
    }


def prepare_rows():
    samples={x['id']:x for x in read(ROOT/'samples'/'panoramas_gpt'/'manifest.json')}
    candidate_runs=read(OUT/'candidate_runs.json')
    if len(candidate_runs)!=6:raise ValueError('Complete all six planned candidates before final evaluation')
    originals={};candidates={sid:[] for sid in SCENES};all_rows=[]
    for sid in SCENES:
        old=base.condition_audio(ROOT/'outputs'/'gpt_audio_demo'/sid/'gpt_detailed',samples[sid])
        old.update(id=sid+'/previous_gpt',scene_id=sid,variant='previous_gpt',kind='previous_round_web_gpt',target_label=base.TARGETS[old['stems'][0]['category']])
        originals[sid]=old
    for record in candidate_runs:
        sid=record['scene_id'];folder=Path(record['plan_file']).parent
        value=base.condition_audio(folder,samples[sid])
        value.update(id=sid+'/'+record['variant'],scene_id=sid,variant=record['variant'],kind='new_local_refinement',target_label=base.TARGETS[value['stems'][0]['category']])
        value['refinement_protocol_checks']=_protocol(originals[sid]['_plan'],value['_plan'])
        value['all_passed']=value['all_passed'] and all(value['refinement_protocol_checks'].values())
        candidates[sid].append(value)
    # This is an old reference, retained and labelled as such, never passed off
    # as a newly generated refinement or used as a replacement raw candidate.
    reference=base.condition_audio(ROOT/'outputs'/'gpt_audio_demo'/'xanderklinge'/'category_only_control',samples['xanderklinge'])
    reference.update(id='xanderklinge/previous_short_reference',scene_id='xanderklinge',variant='previous_short_reference',kind='previous_round_short_reference',target_label='rocky_stream_cascade')
    for sid in SCENES:
        values=[originals[sid],*candidates[sid]]+([reference] if sid=='xanderklinge' else [])
        target=min([-23.]+[x['unmatched_dry_mix_measurement']['integrated_lufs']-1.55-x['unmatched_dry_mix_measurement']['true_peak_4x_dbtp'] for x in values])
        for row in values:
            folder=OUT/'comparison_audio'/sid/row['variant'];folder.mkdir(parents=True,exist_ok=True)
            level=save_audio(folder/'matched_mix.wav',row['_mix'],target)
            row['matched_mix']={**level,'shared_scene_target_lufs':target,'additional_dynamic_processing':False}
            row['checks']['matched_mix_28s']=level['duration_seconds']==28
            row['checks']['matched_mix_peak_headroom']=level['true_peak_4x_dbtp']<=-1.5
            row['all_passed']=row['all_passed'] and all(row['checks'].values())
            write(folder/'matched_mix.json',row['matched_mix'])
            all_rows.append(row)
        old_level=originals[sid]['matched_mix']['integrated_lufs']
        for row in values:
            row['old_new_loudness_difference_lu']=row['matched_mix']['integrated_lufs']-old_level
            row['all_passed']=row['all_passed'] and abs(row['old_new_loudness_difference_lu'])<.01
    if not all(x['all_passed'] for x in all_rows):
        write(OUT/'failed_signal_verification.json',[{k:v for k,v in x.items() if not k.startswith('_')} for x in all_rows])
        raise ValueError('Source, signal, protocol or loudness check failed; see failed_signal_verification.json')
    return all_rows,originals,candidates


def clap_rows(rows,save_embeddings=True):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
    import torch
    from transformers import ClapModel,ClapProcessor
    device='cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(min(8,torch.get_num_threads()));torch.manual_seed(20261025)
    processor=ClapProcessor.from_pretrained(base.CLAP_MODEL,revision=base.CLAP_REVISION,trust_remote_code=False,local_files_only=True)
    model=ClapModel.from_pretrained(base.CLAP_MODEL,revision=base.CLAP_REVISION,use_safetensors=False,trust_remote_code=False,local_files_only=True).eval().to(device)
    labels=list(base.TEXTS);texts=[t for pair in base.TEXTS.values() for t in pair]
    with torch.inference_mode():
        inputs=processor(text=texts,return_tensors='pt',padding=True)
        text_features=model.get_text_features(**{k:v.to(device) for k,v in inputs.items()})
        text_features=torch.nn.functional.normalize(text_features.float(),dim=-1)
    embeddings={}
    for row in rows:
        windows,meta=base._feature_windows(row['matched_mix']['file'])
        with torch.inference_mode():
            inputs=processor(audios=[x for x,_ in windows],sampling_rate=48000,return_tensors='pt',padding='repeatpad',truncation='rand_trunc')
            features=model.get_audio_features(**{k:v.to(device) for k,v in inputs.items()})
            features=torch.nn.functional.normalize(features.float(),dim=-1)
            cosines=(features@text_features.T).cpu().numpy()
            average=torch.nn.functional.normalize(features.mean(dim=0),dim=-1).cpu().numpy()
        embeddings[row['id']]=average
        records=[]
        for (_,window),scores in zip(windows,cosines):
            means={name:float(np.mean(scores[2*i:2*i+2])) for i,name in enumerate(labels)}
            records.append({**window,'label_mean_cosines':means})
        means={name:float(np.mean([x['label_mean_cosines'][name] for x in records])) for name in labels}
        ranking=sorted(means,key=means.get,reverse=True);target=row['target_label']
        row['clap']={'windows':records,'mean_label_cosines':means,'ranking':ranking,'target_label':target,
            'target_mean_cosine':means[target],'target_rank':ranking.index(target)+1,
            'rain_mean_cosine':means['steady_rain'],'target_minus_rain':means[target]-means['steady_rain'],
            'isolated_drips_mean_cosine':means['isolated_drips'],'target_minus_isolated_drips':means[target]-means['isolated_drips']}
        print(json.dumps({'id':row['id'],'target':round(means[target],4),'rain':round(means['steady_rain'],4),'rank':ranking.index(target)+1,'top3':ranking[:3]},ensure_ascii=False),flush=True)
    del model
    if device=='cuda':torch.cuda.empty_cache()
    if save_embeddings:
        np.savez_compressed(OUT/'audio_embeddings.npz',**{k.replace('/','__'):v for k,v in embeddings.items()})
    return embeddings,{'model':base.CLAP_MODEL,'revision':base.CLAP_REVISION,'device':device,
        'method':'Same explicit 17-label / 34-text set and three 10-second 48kHz RMS-scaled windows as previous round; no softmax.',
        'text_prompts':base.TEXTS,'offline':True}


def choose(rows,originals,candidates,embeddings):
    selections={};all_proposed={}
    for sid in SCENES:
        values=candidates[sid]
        if sid=='xanderklinge':
            qualified=[x for x in values if x['clap']['target_mean_cosine']>=.45 and x['clap']['target_rank']==1
                and x['clap']['rain_mean_cosine']<originals[sid]['clap']['rain_mean_cosine']
                and x['clap']['target_minus_rain']>0 and x['clap']['target_minus_isolated_drips']>0]
            pool=qualified or values
            chosen=max(pool,key=lambda x:(x['clap']['target_minus_rain'],x['clap']['target_mean_cosine']))
            gate=bool(qualified)
            all_proposed[sid]=chosen
            reference=next(x for x in rows if x['kind']=='previous_round_short_reference')
            reference_qualifies=(reference['clap']['target_mean_cosine']>=.45 and reference['clap']['target_rank']==1
                and reference['clap']['rain_mean_cosine']<originals[sid]['clap']['rain_mean_cosine']
                and reference['clap']['target_minus_rain']>0 and reference['clap']['target_minus_isolated_drips']>0)
            if reference_qualifies:
                recommended=max([*qualified,reference],key=lambda x:(x['clap']['target_minus_rain'],x['clap']['target_mean_cosine']))
                chosen=recommended;gate=True
                if chosen is reference:
                    chosen['retained_previous_reason']='The previous short stream reference has the largest qualified target-minus-rain margin; retained transparently rather than preferring a newer but more rain-confused output.'
        else:
            chosen=values[0];gate=chosen['clap']['target_rank']==1
            all_proposed[sid]=chosen
        if sid=='fish_hoek_beach':
            previous=originals[sid]
            if (chosen['clap']['target_mean_cosine'] < previous['clap']['target_mean_cosine']-.02
                    or chosen['clap']['rain_mean_cosine'] > previous['clap']['rain_mean_cosine']+.05):
                chosen=previous;gate=chosen['clap']['target_rank']==1
                chosen['retained_previous_reason']='New surf candidate lowered target similarity and increased rain confusion; retained original web-GPT surf without calling it newly generated.'
        chosen['selection_gate_passed']=gate
        selections[sid]=chosen
        selected=OUT/'selected'/sid
        write(selected/'plan.json',chosen['_plan'])
        original_result=read(chosen['_folder']/'result.json')
        write(selected/'result.json',original_result)
    diversity={}
    for label,values in [('previous_gpt',originals),('all_proposed',all_proposed),('selected_refinement',selections)]:
        pairs=[]
        for a,b in itertools.combinations(SCENES,2):
            cosine=float(np.dot(embeddings[values[a]['id']],embeddings[values[b]['id']]))
            pairs.append({'a':a,'b':b,'mean_audio_embedding_cosine':cosine})
        mean=float(np.mean([x['mean_audio_embedding_cosine'] for x in pairs]))
        diversity[label]={'mean_pairwise_cosine':mean,'mean_pairwise_distance':1-mean,'pairs':pairs}
    delta=diversity['selected_refinement']['mean_pairwise_cosine']-diversity['previous_gpt']['mean_pairwise_cosine']
    return selections,diversity,delta


def compact(row):
    c=row['clap']
    return {'id':row['id'],'scene_id':row['scene_id'],'variant':row['variant'],'kind':row['kind'],
        'cache_key':row['cache_key'],'target_mean_cosine':c['target_mean_cosine'],'target_rank':c['target_rank'],
        'rain_mean_cosine':c['rain_mean_cosine'],'target_minus_rain':c['target_minus_rain'],
        'isolated_drips_mean_cosine':c['isolated_drips_mean_cosine'],'top3':c['ranking'][:3],
        'matched_mix':row['matched_mix'],'all_checks_passed':row['all_passed'],
        'selection_gate_passed':row.get('selection_gate_passed')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-clap',action='store_true');args=parser.parse_args()
    started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
    rows,originals,candidates=prepare_rows()
    if args.reuse_clap:
        stored=read(OUT/'evaluation.json');previous={x['id']:x for x in stored['rows']}
        saved=np.load(OUT/'audio_embeddings.npz');embeddings={};need_features=[]
        for row in rows:
            prior=previous.get(row['id'])
            if prior is None or prior['matched_mix']['sha256']!=row['matched_mix']['sha256']:
                need_features.append(row)
            else:
                row['clap']=prior['clap'];embeddings[row['id']]=saved[row['id'].replace('/','__')]
        saved.close()
        method={**stored['clap_method'],'reused_verified_identical_audio_features':True}
        if need_features:
            fresh,new_method=clap_rows(need_features,save_embeddings=False);embeddings.update(fresh)
            method.update(incrementally_scored_changed_audio=[x['id'] for x in need_features])
            np.savez_compressed(OUT/'audio_embeddings.npz',**{k.replace('/','__'):v for k,v in embeddings.items()})
    else:
        embeddings,method=clap_rows(rows)
    selected,diversity,delta=choose(rows,originals,candidates,embeddings)
    selection={sid:{'selected_variant':value['variant'],'candidate_plan_file':str(value['_folder']/'plan.json'),
        'selected_plan_file':str(OUT/'selected'/sid/'plan.json'),'selected_result_file':str(OUT/'selected'/sid/'result.json'),
        'cache_key':value['cache_key'],'source_condition':({'previous_round_web_gpt':'retained_previous_web_gpt','previous_round_short_reference':'retained_previous_short_reference'}.get(value['kind'],'local_acoustic_refinement_after_web_gpt')),
        'selection_reason':value.get('retained_previous_reason','New locally edited candidate retained after the stated exploratory checks.'),
        'previous_matched_mix':originals[sid]['matched_mix'],'selected_matched_mix':value['matched_mix'],
        'metrics':compact(value),'selection_gate_passed':value['selection_gate_passed']} for sid,value in selected.items()}
    scene_conditions={sid:{'before_gpt':compact(originals[sid]),'optimized':compact(selected[sid])} for sid in SCENES}
    summary={'scene_count':3,'new_candidate_count':6,'selection_protocol':'Exploratory same-seed positive-prompt edits: four stream prompts (the fourth is one bounded follow-up), one surf and one traffic. Stream selection requires target >= .45, target rank 1, rain below previous GPT, positive margin over rain and isolated drips, then maximizes target-minus-rain. The previous short stream is a legal, clearly labelled candidate and is retained if it wins; newer audio is not preferred for its age. If no candidate qualifies, best-margin new candidate is retained but gate is false. The old surf is retained if its new candidate lowers target by more than .02 or increases rain by more than .05. These are exploratory decisions on this same metric, not a preregistered or held-out experiment. All proposed candidates are retained and reported.',
        'all_engineering_checks_passed':all(x['all_passed'] for x in rows),
        'all_stream_selection_gates_passed':selected['xanderklinge']['selection_gate_passed'],
        'selection':selection,'scene_conditions':scene_conditions,'candidate_metrics':[compact(x) for x in rows],
        'between_scene_comparison':diversity,'optimized_minus_previous_mean_cosine':delta,
        'selected_is_more_separated_in_clap':delta<0,
        'subjectively_auditioned':False,
        'limits':['All candidates were evaluated and selected with the same fixed CLAP text set; this is exploratory optimization, not independent validation.',
            'CLAP cosines, margins and ranks are not quality scores, probabilities or proof of actual extra events.',
            'Lower between-scene feature similarity is not proof of stronger human scene discrimination.',
            'Postprocessed application audio is compared; same processing algorithm does not imply equal dynamic alterations.',
            'Static-photo source motion, acoustic energy and virtual distance remain simulation assumptions.']}
    write(OUT/'selection.json',selection);write(OUT/'summary.json',summary)
    clean=[]
    for row in rows:
        clean.append({k:v for k,v in row.items() if not k.startswith('_')})
    write(OUT/'evaluation.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'clap_method':method,
        'rows':clean,'summary':summary,'wall_seconds':time.perf_counter()-started})
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
