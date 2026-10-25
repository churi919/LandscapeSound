"""Make traceable AI stems and equal-length, loudness-matched recording controls."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d
from scipy.io import wavfile
from local_config import ROOT

import pyloudnorm as pyln

SR=32000


def read_audio(path):
    sr,pcm=wavfile.read(path)
    x=pcm.astype(np.float64)
    if pcm.dtype.kind in 'iu':x/=float(max(abs(np.iinfo(pcm.dtype).min),np.iinfo(pcm.dtype).max))
    if not np.isfinite(x).all():raise ValueError('Non-finite audio')
    if x.ndim==2:
        rms_stereo=float(np.sqrt(np.mean(x*x)))
        mono=x.mean(axis=1)
        downmix_ratio=float(np.sqrt(np.mean(mono*mono))/max(rms_stereo,1e-12))
    else:mono=x;downmix_ratio=1.
    return sr,mono,downmix_ratio


def texture(path,highpass=True,seconds=30):
    sr,x,ratio=read_audio(path)
    if len(x)/sr<seconds-.01:raise ValueError('Selected formal clip must contain 30 seconds')
    if ratio<.35:raise ValueError('Strong mono downmix cancellation requires review')
    x=x[:round(seconds*sr)]-np.mean(x[:round(seconds*sr)])
    if highpass:x=signal.sosfiltfilt(signal.butter(2,55,btype='highpass',fs=sr,output='sos'),x)
    divisor=math.gcd(sr,SR);x=signal.resample_poly(x,SR//divisor,sr//divisor)
    cross=2*SR;angle=np.linspace(0,np.pi/2,cross)
    x=np.concatenate([x[cross:-cross],x[-cross:]*np.cos(angle)+x[:cross]*np.sin(angle)])
    return x,ratio


def measure(x):
    loudness=float(pyln.Meter(SR).integrated_loudness(x))
    if not math.isfinite(loudness):raise ValueError('Silent or invalid clip')
    true_peak=float(np.max(np.abs(signal.resample_poly(x,4,1))))
    return {'integrated_lufs':loudness,'sample_peak':float(np.max(np.abs(x))),
            'true_peak_4x_dbtp':20*math.log10(max(true_peak,1e-12)),
            'rms':float(np.sqrt(np.mean(x*x))), 'duration_seconds':len(x)/SR}


def matched_dynamics(x,reference_lufs=-23.):
    """Same lookahead soft-knee compressor for AI and recorded controls.

    This prevents one rare generated transient from forcing the entire matched
    comparison down to a barely audible level. Raw WAVs remain untouched.
    """
    original=measure(x)
    x=x*10**((reference_lufs-original['integrated_lufs'])/20)
    peak=maximum_filter1d(np.abs(x),size=321,mode='wrap')
    level=20*np.log10(np.maximum(peak,1e-12));over=level-(-10.)
    knee=6.;ratio=4.;factor=1.-1./ratio
    reduction=np.where(over<=-knee/2,0.,np.where(over>=knee/2,factor*over,
                         factor*(over+knee/2)**2/(2*knee)))
    attack=math.exp(-1/(SR*.001));release=math.exp(-1/(SR*.12))
    envelope=np.empty_like(reduction);previous=0.
    # Warm the circular envelope to avoid a different state at the loop seam.
    for desired in reduction[-SR:]:
        coefficient=attack if desired>previous else release
        previous=coefficient*previous+(1-coefficient)*desired
    for index,desired in enumerate(reduction):
        coefficient=attack if desired>previous else release
        previous=coefficient*previous+(1-coefficient)*desired;envelope[index]=previous
    y=x*10**(-envelope/20)
    return y,{'type':'shared lookahead soft-knee peak compressor','threshold_dbfs':-10.,
              'ratio':4.,'knee_db':6.,'lookahead_about_ms':5.,'attack_ms':1.,'release_ms':120.,
              'pre_normalization_lufs':reference_lufs,'maximum_gain_reduction_db':float(np.max(envelope)),
              'mean_gain_reduction_db':float(np.mean(envelope)),
              'p95_gain_reduction_db':float(np.quantile(envelope,.95)),
              'fraction_over_3db_reduction':float(np.mean(envelope>3.)),
              'raw_texture_measurement':original,'changes_dynamic_range':True}


def save_audio(path,x,target_lufs):
    before=measure(x);gain_db=target_lufs-before['integrated_lufs'];x=x*10**(gain_db/20)
    if np.max(np.abs(x))>=1:raise ValueError('Peak headroom violated')
    path.parent.mkdir(parents=True,exist_ok=True)
    pcm=np.round(x*32767).astype(np.int16);wavfile.write(path,SR,pcm)
    after=measure(pcm.astype(float)/32768)
    after.update(file=str(path.resolve()),channels=1,sample_rate=SR,
                 gain_db=gain_db,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 loop_boundary_step=float(abs(x[-1]-x[0])),
                 adjacent_difference_rms=float(np.sqrt(np.mean(np.diff(x)**2))))
    return after


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--trees-id',required=True);parser.add_argument('--water-id',required=True)
    parser.add_argument('--target-lufs',type=float,default=-23.)
    parser.add_argument('--peak-dbtp',type=float,default=-1.5)
    parser.add_argument('--dynamics',choices=['matched-soft','none'],default='matched-soft')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'assets'/'generated')
    parser.add_argument('--comparison-assets-dir',type=Path,default=ROOT/'outputs'/'audio_model_comparison'/'assets')
    args=parser.parse_args()
    raw_path=ROOT/'assets'/'generated_raw'/'manifest.json'
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    items={x['id']:x for x in raw['items']}
    natural_manifest=json.loads((ROOT/'assets'/'natural'/'manifest.json').read_text(encoding='utf-8'))
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    comparison=args.comparison_assets_dir.resolve()
    ai_items=[];ref_items=[];pairs=[]
    for category,item_id in [('trees',args.trees_id),('water',args.water_id)]:
        item=items[item_id]
        if item['category']!=category:raise ValueError('Mismatched category')
        if hashlib.sha256(Path(item['wav']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Raw generation checksum mismatch')
        ai,ratio=texture(item['wav'],highpass=True)
        reference,_=texture(ROOT/'assets'/'natural'/(category+'.wav'),highpass=False)
        dynamics={'ai':None,'recording':None}
        if args.dynamics=='matched-soft':
            ai,dynamics['ai']=matched_dynamics(ai,args.target_lufs)
            reference,dynamics['recording']=matched_dynamics(reference,args.target_lufs)
        ai_before=measure(ai);ref_before=measure(reference)
        target=min(args.target_lufs,
                   ai_before['integrated_lufs']+args.peak_dbtp-ai_before['true_peak_4x_dbtp'],
                   ref_before['integrated_lufs']+args.peak_dbtp-ref_before['true_peak_4x_dbtp'])
        processed=save_audio(out/(category+'.wav'),ai,target)
        ref=save_audio(comparison/'natural'/(category+'.wav'),reference,target)
        ai_copy=comparison/'generated'/(category+'.wav');ai_copy.parent.mkdir(parents=True,exist_ok=True)
        ai_copy.write_bytes((out/(category+'.wav')).read_bytes())
        processed.update(category=category,generation=item,raw_source_sha256=item['sha256'],
                         mono_downmix_rms_ratio=ratio,ai_generated=True,
                         original_stereo_path=item['wav'],subjectively_auditioned=False,
                         dynamics=dynamics['ai'],
                         processing='mono arithmetic downmix, DC removal, 55Hz high-pass, 32kHz resample, 2s circular equal-power crossfade, shared soft-knee dynamics when enabled, category-paired LUFS normalization with -1.5dBTP 4x-estimated headroom; original stereo retained')
        ai_items.append(processed)
        ref.update(category=category,source_file=str(ROOT/'assets'/'natural'/(category+'.wav')),
                   source_processing='Matched 30s excerpt and 2s circular crossfade from the existing 58s reference; already high-pass filtered once; same optional soft-knee dynamics and category loudness target as AI.',dynamics=dynamics['recording'],ai_generated=False)
        ref_items.append(ref)
        pairs.append({'category':category,'candidate_id':item_id,'target_lufs':target,
                      'ai_lufs':processed['integrated_lufs'],'recording_lufs':ref['integrated_lufs'],
                      'difference_lu':processed['integrated_lufs']-ref['integrated_lufs'],
                      'ai_before':ai_before,'recording_before':ref_before})
    selected_models={x['generation']['model'] for x in ai_items}
    snapshot=out/'generation_manifest_snapshot.json';snapshot.write_bytes(raw_path.read_bytes())
    metadata={'ai_generated':True,'not_ai_generated':False,'model':{'id':'stable-audio-3','name':' / '.join(sorted(selected_models)),
               'checkpoint_repo':'stabilityai/stable-audio-3-optimized'},
              'model_source':'https://huggingface.co/stabilityai/stable-audio-3-optimized',
              'local_date':'2026-10-25','items':ai_items,'pictured_site_recording':False,
              'generation_manifest':str(snapshot),'generation_manifest_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
              'original_generation_manifest':str(raw_path),'dynamics_mode':args.dynamics,
              'loudness_method':'pyloudnorm ITU-R BS.1770 K-weighted integrated loudness; paired by category, 4x oversampled peak estimate; not a certified true-peak meter',
              'pair_loudness':pairs,'subjective_quality':'not measured; candidate selection may use CLAP similarity and signal checks, which do not establish naturalness or absence of extra sound events.'}
    (out/'manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    copied_meta=json.loads(json.dumps(metadata))
    copied_meta['comparison_fixed_offsets']=True
    for x in copied_meta['items']:x['file']=str((comparison/'generated'/(x['category']+'.wav')).resolve())
    (comparison/'generated'/'manifest.json').write_text(json.dumps(copied_meta,ensure_ascii=False,indent=2),encoding='utf-8')
    refmeta={'not_ai_generated':True,'not_pictured_site_recording':True,
             'material_kind':'Loudness-matched excerpts of the existing licensed recording textures',
             'items':ref_items,'original_provenance':natural_manifest,'pair_loudness':pairs}
    (comparison/'natural'/'manifest.json').write_text(json.dumps(refmeta,ensure_ascii=False,indent=2),encoding='utf-8')
    legacy=comparison/'legacy';legacy.mkdir(parents=True,exist_ok=True)
    for name in ['trees.wav','water.wav','bird.wav','audio_manifest.json']:
        (legacy/name).write_bytes((ROOT/'assets'/'legacy'/name).read_bytes())
    summary=comparison.parent/('preparation.json' if comparison.name=='assets' else comparison.name+'_preparation.json')
    summary.write_text(json.dumps({'selected':{'trees':args.trees_id,'water':args.water_id},'pairs':pairs,
                                  'comparison_assets':str(comparison),'ai_manifest':str(out/'manifest.json')},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'comparison':str(comparison),'pairs':pairs},ensure_ascii=False))

if __name__=='__main__':main()
