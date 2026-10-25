import local_config
import importlib.metadata
import json
import shutil
import platform
import wave
import torch

def main():
    output={'python':platform.python_version(),'cuda':torch.cuda.is_available(),'torch':torch.__version__,
            'torch_cuda':torch.version.cuda,'project':str(local_config.ROOT),
            'disk_free_gb':round(shutil.disk_usage(local_config.ROOT).free/1024**3,2),
            'libraries':{n:importlib.metadata.version(n) for n in ['numpy','Pillow','scipy','transformers','streamlit']},
            'assets':{}}
    if torch.cuda.is_available():
        props=torch.cuda.get_device_properties(0)
        output.update(gpu=props.name,vram_mb=round(props.total_memory/1024**2))
    for name in ['trees','water','bird']:
        p=local_config.ROOT/'assets'/(name+'.wav')
        with wave.open(str(p),'rb') as w:
            output['assets'][name]={'channels':w.getnchannels(),'sample_rate':w.getframerate(),
                                    'duration':w.getnframes()/w.getframerate()}
    output['audio_renderer_version']=2
    output['natural_assets']={}
    for name in ['trees','water','brook']:
        p=local_config.ROOT/'assets'/'natural'/(name+'.wav')
        if p.is_file():
            with wave.open(str(p),'rb') as w:
                output['natural_assets'][name]={'channels':w.getnchannels(),'sample_rate':w.getframerate(),
                                                'duration':w.getnframes()/w.getframerate()}
    text=json.dumps(output,ensure_ascii=False,indent=2)
    print(text)
    (local_config.ROOT/'outputs'/'diagnostics.json').write_text(text,encoding='utf-8')

if __name__=='__main__': main()
