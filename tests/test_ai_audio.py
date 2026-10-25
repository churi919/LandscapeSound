"""Optional AI material readiness and shared rendering controls, using temporary fixtures."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave

from audio_player_v2 import render_audio

ROOT=Path(__file__).resolve().parents[1]


def region(category,enabled=True):
    return {'id':category,'category':category,'label':category,'enabled':enabled,
            'azimuth':0,'virtual_radius':4.8,'near_score':.5,'area_fraction':.2}


def write_wav(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
        wav.writeframes(struct.pack('<h',1200)*8000)


def fixture_assets(root,generated=('trees','water'),declared=True):
    for category in ('trees','water','bird'):
        write_wav(root/'legacy'/(category+'.wav'))
        write_wav(root/'natural'/(category+'.wav'))
    (root/'natural'/'manifest.json').write_text(json.dumps({'not_ai_generated':True,'not_pictured_site_recording':True,'items':[]}),encoding='utf-8')
    items=[]
    for category in generated:
        path=root/'generated'/(category+'.wav');write_wav(path)
        items.append({'category':category,'file':str(path),'seed':12,'prompt':'Temporary test fixture, not a real generated production asset',
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (root/'generated').mkdir(exist_ok=True)
    (root/'generated'/'manifest.json').write_text(json.dumps({'ai_generated':declared,'model':{'id':'temporary-test-model'},'items':items}),encoding='utf-8')


def get_payload(result):
    return json.loads(re.search(r'<script>const CONFIG=(.*?);</script>',result,re.S).group(1))


class OptionalAIPlayerTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)

    def tearDown(self):self.folder.cleanup()

    def test_complete_declared_wave_assets_enable_ai_by_default(self):
        fixture_assets(self.root)
        result=render_audio([region('trees'),region('water')],'test',self.root)
        payload=get_payload(result)
        self.assertTrue(payload['generated_available'])
        self.assertEqual(payload['default_preset'],'generated')
        select=re.search(r'<select id="version">(.*?)</select>',result,re.S).group(1)
        self.assertIn('value="generated" selected',select)
        self.assertEqual(payload['profiles']['generated']['categories']['trees']['kind'],'ai_generated')
        self.assertFalse(payload['comparison_fixed_offsets'])

    def test_model_name_and_explicit_comparison_policy_are_reflected_in_the_player(self):
        fixture_assets(self.root)
        path=self.root/'generated'/'manifest.json'
        metadata=json.loads(path.read_text(encoding='utf-8'))
        metadata.update(model={'id':'stable-audio-3','name':'Stable Audio 3 Medium'},comparison_fixed_offsets=True)
        path.write_text(json.dumps(metadata),encoding='utf-8')
        payload=get_payload(render_audio([region('trees'),region('water')],'test',self.root))
        self.assertTrue(payload['comparison_fixed_offsets'])
        self.assertEqual(payload['profiles']['generated']['label'],'AI生成：Stable Audio 3 Medium')

    def test_missing_one_enabled_material_does_not_offer_an_ai_preset(self):
        fixture_assets(self.root,generated=('trees',))
        result=render_audio([region('trees'),region('water')],'test',self.root)
        payload=get_payload(result)
        self.assertFalse(payload['generated_available'])
        select=re.search(r'<select id="version">(.*?)</select>',result,re.S).group(1)
        self.assertNotIn('value="generated"',select)
        self.assertEqual(payload['default_preset'],'natural')
        # Only an enabled category needs to be complete; disabled controls must
        # still be checked again by the browser when the user enables them.
        payload=get_payload(render_audio([region('trees'),region('water',False)],'test',self.root))
        self.assertTrue(payload['generated_available'])
        self.assertNotIn('generated_water',payload['audio'])

    def test_a_file_without_generation_evidence_or_with_wrong_hash_is_not_ai(self):
        fixture_assets(self.root,declared=False)
        payload=get_payload(render_audio([region('trees')],'test',self.root))
        self.assertFalse(payload['generated_available'])
        self.assertNotIn('generated',payload['profiles'])
        manifest=self.root/'generated'/'manifest.json'
        metadata=json.loads(manifest.read_text(encoding='utf-8'));metadata['ai_generated']=True
        metadata['items'][0]['sha256']='0'*64
        manifest.write_text(json.dumps(metadata),encoding='utf-8')
        self.assertFalse(get_payload(render_audio([region('trees')],'test',self.root))['generated_available'])

    def test_invalid_wave_cannot_silently_fall_back_under_an_ai_label(self):
        fixture_assets(self.root)
        (self.root/'generated'/'water.wav').write_bytes(b'not a wav')
        payload=get_payload(render_audio([region('water')],'test',self.root))
        self.assertFalse(payload['generated_available'])
        self.assertNotIn('generated_water',payload['audio'])

    def test_manual_bird_origin_stays_procedural_in_an_ai_scene(self):
        fixture_assets(self.root)
        payload=get_payload(render_audio([region('trees'),region('bird')],'test',self.root))
        self.assertTrue(payload['generated_available'])
        categories=payload['profiles']['generated']['categories']
        self.assertTrue(categories['trees']['ai_generated'])
        self.assertFalse(categories['bird']['ai_generated'])
        self.assertEqual(categories['bird']['kind'],'procedural')
        self.assertEqual(payload['audio']['generated_bird'],payload['audio']['legacy_bird'])

    @unittest.skipUnless(shutil.which('node'),'Node runtime required for rendering control checks')
    def test_browser_plan_offsets_and_spatial_parameters_match_across_continuous_materials(self):
        fixture_assets(self.root)
        sources=[dict(region('water'),id='water-left',azimuth=-30),
                 dict(region('water'),id='water-center'),
                 dict(region('water'),id='water-right',azimuth=30),region('bird')]
        payload=get_payload(render_audio(sources,'test',self.root))
        config=self.root/'config.json';config.write_text(json.dumps(payload),encoding='utf-8')
        harness=self.root/'check.js'
        harness.write_text(NODE_HARNESS,encoding='utf-8')
        process=subprocess.run([shutil.which('node'),str(harness),str(config),str(ROOT/'audio_player.js')],capture_output=True,text=True,check=True)
        result=json.loads(process.stdout)
        self.assertTrue(result['plans_equal'])
        self.assertTrue(result['voice_controls_equal'])
        self.assertEqual(result['preset'],'generated')
        self.assertFalse(result['provenance']['not_ai_generated'])
        self.assertFalse(result['provenance']['all_audible_materials_ai_generated'])
        self.assertTrue(result['provenance']['mixed_origins'])
        self.assertEqual(result['fixed_serials'],[1,1,1])
        self.assertEqual(result['normal_serials'],[1,2,3])


NODE_HARNESS=r'''
const fs=require('fs'),vm=require('vm');
const CONFIG=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.value='';this.disabled=false;this.style={};}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(){}click(){}}
const elements=new Map();const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
for(const [id,value] of Object.entries({version:CONFIG.default_preset,mode:'depth',volume:'0.25','trees-level':'0.8','water-level':'0.7'}))element(id).value=value;
const document={getElementById:element,createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
const sandbox={CONFIG,document,window:{addEventListener(){}},console,setTimeout,clearTimeout,atob:s=>Buffer.from(s,'base64').toString('binary'),URL:{createObjectURL:()=>'',revokeObjectURL(){}},Blob};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),sandbox);
class Param{constructor(value=0){this.value=value;}setValueAtTime(v){this.value=v;}linearRampToValueAtTime(v){this.value=v;}setTargetAtTime(v){this.value=v;}}
function node(extra={}){return {connect(){},disconnect(){},...extra};}
const ac={currentTime:0,decodeAudioData:async()=>({duration:30}),createBufferSource:()=>node({start(){},stop(){}}),createGain:()=>node({gain:new Param()}),createBiquadFilter:()=>node({frequency:new Param(),Q:new Param()}),createPanner:()=>node({positionX:new Param(),positionY:new Param(),positionZ:new Param()})};
sandbox.ac=ac;sandbox.destination=node();
(async()=>{const plans={};const controls={};for(const version of ['natural','generated']){plans[version]=vm.runInContext(`JSON.stringify(currentPlan('${version}'))`,sandbox);const voices=await vm.runInContext(`renderVoices(ac,'${version}',currentPlan('${version}'),destination,.1,7.7,1,true,true)`,sandbox);controls[version]=voices.map(v=>({offset:v.offset,azimuth:v.azimuth,base:v.base,cutoff:v.cutoff,panner:((p)=>({refDistance:p.refDistance,rolloff:p.rolloffFactor,model:p.panningModel}))(v.connected[2])}));}const normal_serials=vm.runInContext('[nextPlaybackSerial(),nextPlaybackSerial(),nextPlaybackSerial()]',sandbox);CONFIG.comparison_fixed_offsets=true;const fixed_serials=vm.runInContext('[nextPlaybackSerial(),nextPlaybackSerial(),nextPlaybackSerial()]',sandbox);console.log(JSON.stringify({plans_equal:plans.natural===plans.generated,voice_controls_equal:JSON.stringify(controls.natural)===JSON.stringify(controls.generated),preset:element('version').value,provenance:vm.runInContext("selectedProvenance('generated')",sandbox),normal_serials,fixed_serials}));})().catch(e=>{console.error(e);process.exit(1);});
'''

if __name__=='__main__':unittest.main()
