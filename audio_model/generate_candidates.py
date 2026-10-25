"""Reproducible local SA3 Small-SFX/Medium generation and telemetry."""
from pathlib import Path
import os,json,time,hashlib,re,argparse,subprocess,sys,wave
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
os.environ['HF_HOME']=str(BASE/'hf_cache')
os.environ['HF_HUB_CACHE']=str(BASE/'hf_cache'/'hub')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TEMP']=str(BASE/'.cache'/'tmp')
os.environ['TMP']=str(BASE/'.cache'/'tmp')
os.environ['PYTHONIOENCODING']='utf-8'
os.environ['PYTHONUNBUFFERED']='1'
import psutil
import numpy as np
import soundfile as sf

TREE='A continuous close recording of a light breeze gently rustling broad green leaves in a tree canopy. Soft irregular leafy rustling and slow natural gusts, low intensity, detailed outdoor field-recording texture, steady without dramatic changes. No music or voices.'
WATER='Small gentle lake ripples lapping against a quiet shore. A continuous soft liquid wash with subtle irregular little laps, low energy, natural detailed outdoor recording, one clean water texture at a steady level. No music or voices.'
NEGATIVE='speech, voices, music, singing, birds, insects, traffic, rain, thunder, roaring wind, distortion, loud impacts, abrupt cuts, rhythmic pulses'
JOBS=[
 {'id':'smoke_trees_20s','category':'trees','seed':20261025,'seconds':20,'prompt':TREE,'role':'deployment_smoke'},
 {'id':'trees_soft_20261026','category':'trees','seed':20261026,'seconds':30,'prompt':TREE,'role':'candidate'},
 {'id':'water_ripples_20261028','category':'water','seed':20261028,'seconds':30,'prompt':WATER,'role':'candidate'},
 {'id':'trees_soft_20261027','category':'trees','seed':20261027,'seconds':30,'prompt':TREE,'role':'candidate'},
 {'id':'water_ripples_20261029','category':'water','seed':20261029,'seconds':30,'prompt':WATER,'role':'candidate'},
 {'id':'water_ripples_cfg2_20261028','category':'water','seed':20261028,'seconds':30,'prompt':WATER,'role':'cfg_comparison','cfg':2.,
  'negative_prompt':NEGATIVE+', waterfall, rushing river, crashing ocean surf, isolated dripping'},
 {'id':'trees_soft_cfg2_20261026','category':'trees','seed':20261026,'seconds':30,'prompt':TREE,'role':'cfg_comparison','cfg':2.,
  'negative_prompt':NEGATIVE},
 {'id':'medium_trees_20261026','category':'trees','seed':20261026,'seconds':30,'prompt':TREE,'role':'model_comparison',
  'dit':'medium','decoder':'same-l','model_label':'Stable Audio 3 Medium'},
 {'id':'medium_water_20261028','category':'water','seed':20261028,'seconds':30,'prompt':WATER,'role':'model_comparison',
  'dit':'medium','decoder':'same-l','model_label':'Stable Audio 3 Medium'},
]

def run(job):
    out=ROOT/'assets'/'generated_raw'/(job['id']+'.wav')
    record_path=ROOT/'outputs'/'audio_model_run'/(job['id']+'.json')
    if out.exists() and record_path.exists():
        print('Existing verified record:',record_path,flush=True);return json.loads(record_path.read_text(encoding='utf-8'))
    log=ROOT/'outputs'/'audio_model_run'/(job['id']+'.log')
    command=[str(BASE/'.venv'/'Scripts'/'python.exe'),str(BASE/'stable-audio-3'/'optimized'/'tflite'/'scripts'/'sa3_tflite.py'),
             '--dit',job.get('dit','sm-sfx'),'--decoder',job.get('decoder','same-s'),'--dit-precision','w8a8','--decoder-precision','w8a8',
             '--seconds',str(job['seconds']),'--steps','8','--seed',str(job['seed']),'--cfg',str(job.get('cfg',1)),'--threads','8',
             '--prompt',job['prompt'],'--out',str(out)]
    if job.get('negative_prompt'):command.extend(['--negative-prompt',job['negative_prompt']])
    recovered=out.exists() and log.exists() and 'saved' in log.read_text(encoding='utf-8',errors='replace')
    peak_rss=None;peak_system_used=None;elapsed=None
    if not recovered:
        if job.get('dit')=='medium' and psutil.virtual_memory().available<5*1024**3:
            raise RuntimeError('Medium deferred: less than 5 GiB system RAM available; no generation started.')
        started=time.perf_counter();peak_rss=0;peak_system_used=0
        low_memory_samples=0
        print('Starting '+job['id'],flush=True)
        with log.open('w',encoding='utf-8') as stream:
            child=subprocess.Popen(command,cwd=BASE/'stable-audio-3'/'optimized'/'tflite',stdout=stream,stderr=subprocess.STDOUT,env=os.environ.copy())
            process=psutil.Process(child.pid)
            while child.poll() is None:
                try:
                    family=[process]+process.children(recursive=True)
                    rss=sum(p.memory_info().rss for p in family if p.is_running())
                    memory=psutil.virtual_memory()
                    peak_rss=max(peak_rss,rss);peak_system_used=max(peak_system_used,memory.used)
                    low_memory_samples=low_memory_samples+1 if memory.available<1.25*1024**3 else 0
                    if job.get('dit')=='medium' and low_memory_samples>=5:
                        print('Stopping own Medium child to preserve system RAM headroom.',flush=True)
                        for own_child in reversed(process.children(recursive=True)):
                            try:own_child.terminate()
                            except psutil.NoSuchProcess:pass
                        process.terminate()
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                time.sleep(.2)
        elapsed=time.perf_counter()-started
        if child.returncode!=0:
            print(log.read_text(encoding='utf-8',errors='replace')[-8000:],flush=True)
            raise RuntimeError(f'Generation failed {job["id"]}: code {child.returncode}; log={log}')
    audio,sr=sf.read(out,always_2d=True)
    assert sr==44100 and audio.shape[1]==2 and len(audio)==job['seconds']*sr
    assert np.isfinite(audio).all() and np.sqrt(np.mean(audio**2))>1e-5
    text=log.read_text(encoding='utf-8',errors='replace')
    weights=json.loads((BASE/'weights_manifest.json').read_text(encoding='utf-8'))
    stages={}
    for pattern,key in [(r'T5Gemma \(tokenize \+ encode\).*?(\d+(?:\.\d+)?) ms','text_encoder_ms'),
                        (r'sample (\d+) ms','sampling_ms'),(r'decode rung.*? (\d+) ms','decode_ms')]:
        found=re.findall(pattern,text);stages[key]=float(found[-1]) if found else None
    result={**job,'model':job.get('model_label','Stable Audio 3 Small-SFX'),'model_repo':weights['repo_id'],'model_revision':weights['revision'],
            'code_repository':'https://github.com/Stability-AI/stable-audio-3','code_revision':'77e0398c26f7d22d801ec1bb036307e8b231f741',
            'runtime':'official native Windows LiteRT/TFLite CPU','device':'CPU / XNNPACK, Intel i9-14900HX',
            'threads':8,'dit_family':job.get('dit','sm-sfx'),'dit_precision':'w8a8',
            'decoder':('SAME-L w8a8' if job.get('decoder')=='same-l' else 'SAME-S w8a8'),'steps':8,'cfg':job.get('cfg',1.),'negative_prompt':job.get('negative_prompt'),
            'negative_prompt_note':('Explicit negative branch active; its presence does not prove all excluded events absent.' if job.get('cfg',1.)!=1 else 'CFG=1 baseline does not use a negative branch; no claim of absence of incidental events.'),
            'wav':str(out),'sample_rate':sr,'channels':audio.shape[1],'actual_duration_seconds':len(audio)/sr,
            'rms':float(np.sqrt(np.mean(audio**2))),'peak':float(np.max(abs(audio))),
            'clipped_sample_count':int((abs(audio)>=.9999).sum()),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
            'wall_seconds_including_process_start':round(elapsed,3) if elapsed is not None else None,
            'official_cli_wall_seconds':float(re.search(r'done\s+(\d+(?:\.\d+)?)s wall',text).group(1)),
            'peak_process_tree_rss_mb':round(peak_rss/1024**2,1) if peak_rss is not None else None,
            'peak_system_used_mb_during_run':round(peak_system_used/1024**2,1) if peak_system_used is not None else None,
            'recovered_after_log_decode_error_without_rerender':recovered,'stages':stages,'log':str(log),
            'generation_kind':'AI generated, not field recording','subjectively_auditioned':False,
            'model_license':'Stable Audio Community License; includes Gemma components; see model card.',
            'downloaded_anonymously':True,'all_inference_local':True}
    record_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_path=ROOT/'assets'/'generated_raw'/'manifest.json'
    existing=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'model':'Stable Audio 3 Small-SFX','items':[]}
    existing['items']=[x for x in existing['items'] if x['id']!=job['id']]+[result]
    existing['models']=sorted({x['model'] for x in existing['items']})
    if len(existing['models'])>1:existing['model']='Stable Audio 3 candidate collection; per-item model and decoder are recorded.'
    manifest_path.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',default='all');args=ap.parse_args()
    for job in JOBS:
        if args.only not in ['all',job['id'],job['category'],job['role']]:continue
        run(job)

if __name__=='__main__':main()
