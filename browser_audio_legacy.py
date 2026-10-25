"""Self-contained Web Audio HRTF player and local-device Chinese speech synthesis.

Audio and text remain in the browser. Only local system Chinese voices are used;
if none exists, the description remains readable and no remote voice is selected.
"""
from __future__ import annotations

import base64
import html
import json
import math
from pathlib import Path


def _safe_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def render_audio(sources: list[dict], description: str, assets_dir: Path,
                 duration: float = 12.0) -> str:
    """Return standalone HTML suitable for streamlit.components.v1.html.

    Source positions are virtual audio coordinates, never measured metres.
    Unknown categories are excluded. Bird is accepted only when explicitly
    supplied/enabled by the calling UI; the vision pipeline must not infer birds.
    """
    clean = []
    for index, source in enumerate(sources):
        category = source.get('category')
        if category not in {'trees', 'water', 'bird'}:
            continue
        azimuth = float(source.get('azimuth', 0))
        radius = float(source.get('virtual_radius', 4.5))
        if not math.isfinite(azimuth) or not math.isfinite(radius):
            raise ValueError('Source azimuth and virtual_radius must be finite')
        near = source.get('near_score')
        if near is not None:
            near = float(near)
            near = max(0, min(1, near)) if math.isfinite(near) else None
        clean.append({'id': str(source.get('id', f'source-{index}')),
                      'category': category, 'label': str(source.get('label', category)),
                      'enabled': bool(source.get('enabled', True)),
                      'azimuth': max(-90, min(90, azimuth)),
                      'near_score': near,
                      'virtual_radius': max(1.8, min(7.8, radius))})
    payloads = {}
    for category in sorted({source['category'] for source in clean}):
        path = Path(assets_dir) / f'{category}.wav'
        if not path.is_file():
            raise FileNotFoundError(f'Missing sound asset {path}. Run generate_demo_audio.py first.')
        payloads[category] = base64.b64encode(path.read_bytes()).decode('ascii')
    return _TEMPLATE.replace('__PAYLOAD__', _safe_json({'sources': clean, 'audio': payloads,
        'description': str(description), 'duration': max(1, min(60, float(duration)))})).replace(
            '__DESCRIPTION__', html.escape(str(description)))


def write_preview(path: Path | None = None) -> Path:
    root = Path(__file__).resolve().parent
    path = Path(path) if path else root / 'audio_component_preview.html'
    sources = [
        {'id': 'tree-left', 'category': 'trees', 'label': '左前方树木（模拟设定）',
         'enabled': True, 'azimuth': -30, 'near_score': 0.85, 'virtual_radius': 2.7},
        {'id': 'water-right', 'category': 'water', 'label': '右前方水面（模拟设定）',
         'enabled': True, 'azimuth': 30, 'near_score': 0.35, 'virtual_radius': 5.7},
        {'id': 'bird-manual', 'category': 'bird', 'label': '人工鸟鸣示例（默认关闭）',
         'enabled': False, 'azimuth': 0, 'near_score': 0.1, 'virtual_radius': 7.2},
    ]
    path.write_text(render_audio(sources, '这是无模型声音预览。树声位于左前方较近处，水声位于右前方较远处。位置和声音均为模拟设定，不能用于判断真实场地。', root / 'assets'), encoding='utf-8')
    return path


_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LandscapeSound 双耳试听</title>
<style>
:root{color-scheme:light;font-family:system-ui,"Microsoft YaHei",sans-serif;color:#13392e;background:#f4f8f5}*{box-sizing:border-box}body{margin:0;padding:18px}main{max-width:1080px;margin:auto}.intro{font-size:14px;line-height:1.7;color:#465e54;margin:0 0 16px}.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}button,select{font:inherit;border-radius:9px;padding:11px 15px;border:1px solid #9eb7a9;background:white;color:#183e31;min-height:46px;cursor:pointer}button.primary{background:#1b5945;color:white;border-color:#1b5945}button.stop{border-color:#a54d35;color:#8a321b}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #ee9a32;outline-offset:3px}button:disabled{cursor:wait;opacity:.6}.volume{display:flex;gap:10px;align-items:center;margin:16px 0;font-size:14px}.volume input{width:180px}#status{background:#e4efe7;padding:10px 12px;border-radius:7px;min-height:40px;font-size:14px;line-height:1.5}#source-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:12px;margin:16px 0}.source{padding:13px 14px;border:1px solid #cedfd1;border-radius:10px;background:white}.source label{font-size:14px}.source h3{font-size:15px;margin:0 0 14px}.source .row{margin-top:9px}.source input[type=range]{display:block;width:100%;accent-color:#1b5945}.source input[type=checkbox]{width:18px;height:18px;vertical-align:middle;margin-right:8px;accent-color:#1b5945}.description{font-size:14px;line-height:1.8;margin:12px 0 0}details summary{cursor:pointer;min-height:30px}.foot{font-size:12px;color:#536a5e;line-height:1.6;margin:12px 0 0}.mode{display:flex;align-items:center;gap:9px;font-size:14px;margin:0 0 14px}h2{font-size:19px;margin:0 0 8px}
</style></head><body><main aria-label="景观声音与描述播放器">
<h2>听见画面的空间层次</h2>
<p class="intro">建议戴立体声耳机，从较低音量开始。所有声效为程序合成的示意素材；树木、水面可见，不代表现场一定发声。虚拟距离只控制听感。</p>
<div class="mode"><label for="mode">试听方式</label><select id="mode"><option value="depth">深度驱动双耳声景</option><option value="flat">普通混音（对照）</option></select></div>
<div class="actions"><button class="primary" id="play">播放双耳声景</button><button id="speak">朗读景观描述</button><button class="stop" id="stop">停止全部声音</button><button id="calibrate">左右耳校准</button></div>
<div class="volume"><label for="volume">声景音量</label><input aria-label="声景音量" id="volume" type="range" min="0" max="0.6" step="0.01" value="0.25"><output id="volume-value" for="volume">25%</output></div>
<div id="status" role="status" aria-live="polite" aria-atomic="true">尚未播放。点击按钮后声音才会开始。</div>
<div id="source-controls"></div>
<details><summary>查看景观描述</summary><p class="description">__DESCRIPTION__</p></details>
<p id="voice-status" class="foot">正在检查本机中文语音。</p>
<p class="foot">双耳定位使用浏览器 HRTF。左右校准是声道检查，不能证明个人方位识别有效。鸟鸣仅供人工确认后启用。</p>
</main><script>
'use strict';
const CONFIG = __PAYLOAD__;
const state = {playing:false,activeNodes:0,lastPositions:[],lastFilters:[],ttsVoiceCount:0,error:null,stopCount:0,mode:'depth',audioContextState:'not-created',speechActive:false,calibrating:false,events:[]};
window.landscapeAudioDebug=state;
let ctx=null, master=null, compressor=null, nodes=[], graph=[], autoStop=null, generation=0, voices=[], utterance=null;
const cache = new Map();
const $=id=>document.getElementById(id);
function status(text){$('status').textContent=text;state.events.push({time:Date.now(),text});state.events=state.events.slice(-30);}
function errorText(error){state.error=String(error && error.message || error);status('无法播放：'+state.error);}
function stopAudio(update=true){
  generation++;clearTimeout(autoStop);autoStop=null;
  for(const node of nodes){try{node.stop();}catch(_){}try{node.disconnect();}catch(_){}}
  for(const item of graph){for(const node of item.connected){try{node.disconnect();}catch(_){}}}
  nodes=[];graph=[];state.playing=false;state.activeNodes=0;state.calibrating=false;state.stopCount++;
  $('play').disabled=false;
  if(update)status('声景已停止。');
}
function stopAll(update=true){stopAudio(false);if('speechSynthesis' in window)speechSynthesis.cancel();utterance=null;state.speechActive=false;if(update)status('全部声音已停止。');}
async function audioContext(){
  if(!ctx){const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw Error('此浏览器不支持 Web Audio');ctx=new Audio({latencyHint:'interactive'});master=ctx.createGain();master.gain.value=Number($('volume').value);compressor=ctx.createDynamicsCompressor();compressor.threshold.value=-12;compressor.knee.value=18;compressor.ratio.value=6;compressor.attack.value=.005;compressor.release.value=.2;master.connect(compressor);compressor.connect(ctx.destination);}
  await ctx.resume();state.audioContextState=ctx.state;
  if(ctx.state!=='running')throw Error('浏览器尚未允许声音，请再次点击播放');
  return ctx;
}
async function buffer(category){
  if(cache.has(category))return cache.get(category);
  const data=atob(CONFIG.audio[category]);const bytes=new Uint8Array(data.length);for(let i=0;i<data.length;i++)bytes[i]=data.charCodeAt(i);
  const decoded=await ctx.decodeAudioData(bytes.buffer);cache.set(category,decoded);return decoded;
}
function applyPosition(item){
  const source=item.source;const r=source.virtual_radius;const angle=source.azimuth*Math.PI/180;
  const position={id:source.id,x:r*Math.sin(angle),y:0,z:-r*Math.cos(angle),azimuth:source.azimuth,virtual_radius:r,spatialized:!!item.panner};
  if(item.panner){item.panner.positionX.setTargetAtTime(position.x,ctx.currentTime,.03);item.panner.positionY.setTargetAtTime(0,ctx.currentTime,.03);item.panner.positionZ.setTargetAtTime(position.z,ctx.currentTime,.03);}
  const cutoff=9000*Math.pow(0.20,(r-1.8)/6);
  if(item.filter)item.filter.frequency.setTargetAtTime(cutoff,ctx.currentTime,.03);
  const posIndex=state.lastPositions.findIndex(p=>p.id===source.id);if(posIndex<0)state.lastPositions.push(position);else state.lastPositions[posIndex]=position;
  const filterInfo={id:source.id,frequency:item.filter?cutoff:22050,enabled:!!item.filter};
  const fIndex=state.lastFilters.findIndex(f=>f.id===source.id);if(fIndex<0)state.lastFilters.push(filterInfo);else state.lastFilters[fIndex]=filterInfo;
}
async function play(){
  stopAll(false);state.error=null;const token=generation;const selected=CONFIG.sources.filter(s=>s.enabled);
  if(!selected.length){status('没有启用的声源。可先勾选一个声源。');return;}
  $('play').disabled=true;status('正在准备本机音频…');
  try{
    await audioContext();const decoded=await Promise.all(selected.map(s=>buffer(s.category)));
    if(token!==generation)return;
    state.lastPositions=[];state.lastFilters=[];state.mode=$('mode').value;
    const start=ctx.currentTime+.08;
    selected.forEach((source,index)=>{
      const node=ctx.createBufferSource();node.buffer=decoded[index];node.loop=true;
      const gain=ctx.createGain();gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.9/Math.sqrt(selected.length),start+.12);
      gain.gain.setValueAtTime(.9/Math.sqrt(selected.length),start+CONFIG.duration-.15);gain.gain.linearRampToValueAtTime(0,start+CONFIG.duration);
      let filter=null,panner=null;const connected=[gain];
      if(state.mode==='depth'){
        filter=ctx.createBiquadFilter();filter.type='lowpass';filter.Q.value=.5;
        panner=ctx.createPanner();panner.panningModel='HRTF';panner.distanceModel='inverse';panner.refDistance=1;panner.maxDistance=25;panner.rolloffFactor=.32;
        panner.coneInnerAngle=360;panner.coneOuterAngle=360;panner.coneOuterGain=1;
        node.connect(filter);filter.connect(panner);panner.connect(gain);connected.push(filter,panner);
      }else node.connect(gain);
      gain.connect(master);const item={source,filter,panner,gain,connected};graph.push(item);applyPosition(item);nodes.push(node);node.start(start);node.stop(start+CONFIG.duration+.02);
    });
    state.playing=true;state.activeNodes=nodes.length;$('play').disabled=false;
    status((state.mode==='depth'?'正在播放深度驱动双耳声景':'正在播放普通混音对照')+'，'+selected.length+' 个模拟声源，'+CONFIG.duration+' 秒后停止。');
    autoStop=setTimeout(()=>{stopAudio(false);status('本轮试听已结束。');},(CONFIG.duration+.15)*1000);
  }catch(error){if(token===generation){stopAudio(false);errorText(error);}}
}
function loadVoices(){
  if(!('speechSynthesis' in window)){state.ttsVoiceCount=0;$('voice-status').textContent='此浏览器没有语音合成功能，可直接阅读描述。';return;}
  voices=speechSynthesis.getVoices().filter(v=>/^zh(?:-|_)/i.test(v.lang)&&v.localService);
  state.ttsVoiceCount=voices.length;
  $('voice-status').textContent=voices.length?'本机中文语音：'+voices.map(v=>v.name).join('、')+'。描述与声景分开播放。':'未找到本机中文语音；请在 Windows 安装中文语音后重开页面。描述仍可直接阅读。';
}
function speak(){
  stopAll(false);state.error=null;loadVoices();if(!voices.length){status('没有可用的本机中文语音，请阅读文字描述或安装中文语音。');return;}
  const token=generation;
  utterance=new SpeechSynthesisUtterance(CONFIG.description);utterance.voice=voices.find(v=>/^zh-CN$/i.test(v.lang))||voices[0];utterance.lang=utterance.voice.lang;utterance.rate=.92;utterance.volume=.8;
  utterance.onstart=()=>{if(token===generation){state.speechActive=true;status('正在朗读景观描述，声景已停止。');}};
  utterance.onend=()=>{if(token===generation){state.speechActive=false;status('景观描述朗读结束。');}};
  utterance.onerror=event=>{if(token===generation){state.speechActive=false;if(!['canceled','interrupted'].includes(event.error))errorText(event.error);}};
  speechSynthesis.speak(utterance);
}
async function calibrate(){
  stopAll(false);state.error=null;const token=generation;
  try{await audioContext();if(token!==generation)return;
    state.playing=true;state.calibrating=true;state.lastPositions=[];state.lastFilters=[];
    const t=ctx.currentTime+.08;
    [-1,1].forEach((pan,index)=>{const osc=ctx.createOscillator();osc.frequency.value=500+index*180;const p=ctx.createStereoPanner();p.pan.value=pan;const gain=ctx.createGain();const start=t+index*1.25;gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.45,start+.03);gain.gain.setValueAtTime(.45,start+.75);gain.gain.linearRampToValueAtTime(0,start+.82);osc.connect(p);p.connect(gain);gain.connect(master);nodes.push(osc);graph.push({connected:[p,gain]});osc.start(start);osc.stop(start+.85);});
    state.activeNodes=2;status('左右耳校准：先左耳低音，再右耳较高音。');
    autoStop=setTimeout(()=>{stopAudio(false);status('声道校准结束。若左右相反，请检查耳机佩戴方向。');},2400);
  }catch(error){if(token===generation){stopAudio(false);errorText(error);}}
}
function controls(){
  const container=$('source-controls');
  for(const [index,source] of CONFIG.sources.entries()){
    const card=document.createElement('section');card.className='source';
    const h=document.createElement('h3');const check=document.createElement('input');check.type='checkbox';check.id='enabled-'+index;check.checked=source.enabled;const label=document.createElement('label');label.htmlFor=check.id;label.textContent=source.label;h.append(check,label);card.append(h);
    const fields=[{name:'azimuth',label:'方位',min:-90,max:90,step:1,unit:'°'},{name:'virtual_radius',label:'虚拟距离',min:1.8,max:7.8,step:.1,unit:''}];
    for(const field of fields){const row=document.createElement('div');row.className='row';const l=document.createElement('label');const id=field.name+'-'+index;l.htmlFor=id;const output=document.createElement('output');output.htmlFor=id;output.textContent=Number(source[field.name]).toFixed(field.name==='azimuth'?0:1)+field.unit;l.append(document.createTextNode(field.label+'：'),output);const input=document.createElement('input');input.type='range';input.id=id;input.min=field.min;input.max=field.max;input.step=field.step;input.value=source[field.name];input.setAttribute('aria-label',source.label+' '+field.label);input.addEventListener('input',()=>{source[field.name]=Number(input.value);output.textContent=Number(input.value).toFixed(field.name==='azimuth'?0:1)+field.unit;const item=graph.find(i=>i.source===source);if(item)applyPosition(item);});row.append(l,input);card.append(row);}
    check.addEventListener('change',()=>{source.enabled=check.checked;if(state.playing)stopAudio();});container.append(card);
  }
  if(!CONFIG.sources.length)container.textContent='这张照片没有自动生成树木或水体声源。';
}
$('play').addEventListener('click',play);$('stop').addEventListener('click',()=>stopAll());$('speak').addEventListener('click',speak);$('calibrate').addEventListener('click',calibrate);
$('volume').addEventListener('input',event=>{const volume=Number(event.target.value);$('volume-value').value=Math.round(volume*100)+'%';if(master)master.gain.setTargetAtTime(volume,ctx.currentTime,.02);});
$('mode').addEventListener('change',()=>{stopAll(false);state.mode=$('mode').value;$('play').textContent=state.mode==='depth'?'播放双耳声景':'播放普通混音';status('试听方式已切换，点击播放开始。');});
window.addEventListener('pagehide',()=>stopAll(false));window.addEventListener('beforeunload',()=>stopAll(false));
if('speechSynthesis' in window)speechSynthesis.addEventListener('voiceschanged',loadVoices);
controls();loadVoices();
</script></body></html>'''


if __name__ == '__main__':
    print(write_preview())
