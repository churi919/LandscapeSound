"""New scene classes stay independent and never borrow another category's WAV."""
import copy
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
from audio_layers import plan_audio_layers
from scene_audio_runtime import _validate


ROOT = Path(__file__).resolve().parents[1]


def wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000)
        output.writeframes(struct.pack('<h', 1200)*8000)


def generated(folder, categories):
    items=[]
    for category in categories:
        path=folder/'generated'/(category+'.wav'); wav(path)
        items.append({'category':category,'file':str(path),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'prompt':'Temporary test fixture, not production AI audio', 'seed':123})
    (folder/'generated'/'manifest.json').write_text(json.dumps({'ai_generated':True,
        'model':{'id':'temporary-test-model'},'items':items}),encoding='utf-8')


def source(category, **extra):
    return {'id':category, 'category':category,'label':category,'azimuth':20,
        'virtual_radius':4.8,'area_fraction':1,'enabled':True, **extra}


def payload(result):
    return json.loads(re.search(r'const CONFIG=(.*?);</script>',result,re.S).group(1))


class ExtendedSceneAudioTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
    def tearDown(self):self.temporary.cleanup()

    def test_each_new_category_has_its_own_generated_only_profile_and_control(self):
        for category,label in [('surf','海浪'),('stream','流水'),('traffic','道路背景'),('wind','风声')]:
            folder=self.root/category;generated(folder,[category])
            page=render_audio([source(category)],'test',folder)
            config=payload(page)
            self.assertEqual(config['default_preset'],'generated')
            self.assertEqual(config['available_presets'],['generated'])
            self.assertEqual(set(config['audio']),{'generated_'+category})
            self.assertEqual(config['layers'][0]['category'],category)
            self.assertEqual(config['profiles']['generated']['categories'][category]['kind'],'ai_generated')
            self.assertIn('id="'+category+'-level"',page)
            self.assertIn(label,page)
            select=re.search(r'<select id="version">(.*?)</select>',page,re.S).group(1)
            self.assertNotIn('value="natural"',select)
            self.assertNotIn('value="legacy"',select)

    def test_missing_new_category_never_substitutes_water_or_trees(self):
        generated(self.root,['water'])
        wav(self.root/'legacy'/'water.wav');wav(self.root/'natural'/'water.wav')
        with self.assertRaisesRegex(FileNotFoundError,'surf'):
            render_audio([source('surf')],'test',self.root)

    def test_gpt_relative_level_and_explicit_spread_reach_render_settings(self):
        generated(self.root,['surf','wind'])
        config=payload(render_audio([source('surf',relative_level=.9,spread_degrees=38),
            source('wind',relative_level=.25,spread_degrees=15)],'test',self.root))
        self.assertEqual(config['category_levels'],{'surf':.9,'wind':.25})
        layers={x['category']:x for x in config['layers']}
        self.assertEqual(layers['surf']['spread_degrees'],38)
        self.assertEqual(layers['wind']['spread_degrees'],15)

    def test_unsupported_categories_are_still_not_inferred_or_played(self):
        self.assertEqual(plan_audio_layers([source('music')]),[])
        self.assertEqual(plan_audio_layers([source('traffic',enabled=False)]),[])

    def test_runtime_accepts_three_distinct_extended_stems_but_rejects_four(self):
        plan={'cache_key':'a'*64,'image_sha256_rgb':'b'*64,
            'stems':[{'category':x,'prompt':'Fixture only','seed':1,'seconds':30} for x in ['surf','wind','traffic']]}
        _validate(plan,self.root)
        changed=copy.deepcopy(plan);changed['stems'].append({'category':'stream','prompt':'Fixture only','seed':2})
        with self.assertRaisesRegex(ValueError,'three'):_validate(changed,self.root)

    @unittest.skipUnless(shutil.which('node'),'Node runtime required')
    def test_browser_availability_skips_missing_reference_profiles(self):
        generated(self.root,['surf'])
        config=payload(render_audio([source('surf'),source('wind',enabled=False)],'test',self.root))
        path=self.root/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
        script=self.root/'check.js';script.write_text(NODE_CHECK,encoding='utf-8')
        result=subprocess.run([shutil.which('node'),str(script),str(path),str(ROOT/'audio_player.js')],
            capture_output=True,text=True,check=True)
        values=json.loads(result.stdout)
        self.assertEqual(values['initial'],['generated'])
        self.assertEqual(values['unavailable'],[])
        self.assertEqual(values['layers'][0]['category'],'surf')


NODE_CHECK=r'''
const fs=require('fs'),vm=require('vm');const CONFIG=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const elements=new Map();function element(id){if(!elements.has(id))elements.set(id,{value:'0.5',disabled:false,textContent:'',children:[],append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x},addEventListener(){},setAttribute(){},click(){}});return elements.get(id);}
element('version').value=CONFIG.default_preset;for(const [c,v] of Object.entries(CONFIG.category_levels))element(c+'-level').value=String(v);
const document={getElementById:element,createElement:()=>({value:'',textContent:'',append(){},setAttribute(){},addEventListener(){}}),querySelectorAll:()=>[]};
const window={addEventListener(){}};const sandbox={CONFIG,document,window,console,setTimeout(){},clearTimeout(){},Map,Math,JSON,Number,Blob,URL};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),sandbox);
const initial=vm.runInContext('availableVersions()',sandbox),layers=vm.runInContext('planLayers()',sandbox);CONFIG.sources[1].enabled=true;const unavailable=vm.runInContext('availableVersions()',sandbox);console.log(JSON.stringify({initial,unavailable,layers}));
'''


if __name__=='__main__':unittest.main()
