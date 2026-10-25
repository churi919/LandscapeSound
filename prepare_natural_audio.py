"""Prepare long, level-controlled illustrative loops from licensed public previews."""
import json
import math
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
from local_config import ROOT


def read_mono(path):
    sr,pcm=wavfile.read(path)
    x=pcm.astype(np.float64)
    if pcm.dtype.kind in 'iu':x/=float(max(abs(np.iinfo(pcm.dtype).min),np.iinfo(pcm.dtype).max))
    if x.ndim==2:x=x.mean(axis=1)
    return sr,x


def prepare(item,output,sr=32000):
    old_sr,x=read_mono(item['decoded_wav'])
    x-=np.mean(x)
    x=signal.sosfiltfilt(signal.butter(2,55,btype='highpass',fs=old_sr,output='sos'),x)
    divisor=math.gcd(sr,old_sr)
    x=signal.resample_poly(x,sr//divisor,old_sr//divisor)
    length=60*sr
    candidates=[]
    for start in range(0,len(x)-length+1,5*sr):
        chunk=x[start:start+length];rms=float(np.sqrt(np.mean(chunk**2)))
        if rms<1e-9:continue
        score=float(np.quantile(abs(chunk),.999))/rms+.1*float(np.max(abs(chunk)))/rms
        candidates.append((score,start))
    if not candidates:raise ValueError('A 60-second source recording is required')
    _,start=min(candidates)
    x=x[start:start+length].copy()
    cross=2*sr;angle=np.linspace(0,np.pi/2,cross)
    blend=x[-cross:]*np.cos(angle)+x[:cross]*np.sin(angle)
    x=np.concatenate([x[cross:-cross],blend])
    gain=.08/max(float(np.sqrt(np.mean(x*x))),1e-9)
    gain=min(gain,.65/max(float(np.max(abs(x))),1e-9));x*=gain
    pcm=np.round(np.clip(x,-1,1)*32767).astype(np.int16)
    wavfile.write(output,sr,pcm)
    step=float(abs(x[-1]-x[0]));diff_rms=float(np.sqrt(np.mean(np.diff(x)**2)))
    return {'file':str(output),'source_id':item['id'],'source_url':item['source_url'],
            'author':item['author'],'license':item['license'],
            'download_kind':item['download_kind'],'sample_rate':sr,'channels':1,
            'duration_seconds':len(x)/sr,'source_excerpt_start_seconds':start/sr,
            'processing':'DC removal, 55Hz high-pass, deterministic low-crest 60s excerpt, resample32kHz, 2s equal-power circular crossfade, RMS/peak gain control; not denoised or AI generated.',
            'rms':float(np.sqrt(np.mean(x*x))),'peak':float(np.max(abs(x))),
            'loop_boundary_step':step,'ordinary_sample_difference_rms':diff_rms,
            'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'depicted_site_recording':False,'subjectively_auditioned':False}


def main():
    raw=json.loads((ROOT/'assets'/'recorded_raw'/'manifest.json').read_text(encoding='utf-8'))
    folder=ROOT/'assets'/'natural';folder.mkdir(parents=True,exist_ok=True)
    mapping={'trees_wind':'trees.wav','water_lake':'water.wav','water_brook':'brook.wav'}
    records=[prepare(x,folder/mapping[x['id']]) for x in raw['items'] if x['id'] in mapping]
    result={'version':2,'material_kind':'licensed field-recording textures from official public HQ MP3 previews',
            'not_pictured_site_recording':True,'not_ai_generated':True,'items':records,
            'bird':'Manual bird demonstration, if enabled, still uses the original procedural asset.',
            'limits':'No subjective listening or assurance about incidental background events. Water texture is lake lapping; not a confirmation that the pictured water makes this sound.'}
    (folder/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'file':Path(x['file']).name,'duration':x['duration_seconds'],'rms':x['rms'],'peak':x['peak']} for x in records]))

if __name__=='__main__':main()
