"""Exact-text speech embedding and narration transport/control regression checks."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from audio_player_v2 import _narration_payload, render_audio


ROOT=Path(__file__).resolve().parents[1]
TEXT='前方是一条岩石间流动的小溪。'


def fixture(text=TEXT):
    voices=[]
    english=not re.search(r'[\u3400-\u9fff]',text)
    configured=[('en-US-JennyNeural','Natural English female · Jenny'),('en-US-GuyNeural','Natural English male · Guy')] if english else [('zh-CN-XiaoxiaoNeural','自然女声 · 晓晓'),('zh-CN-YunxiNeural','自然男声 · 云希')]
    # Temporary byte fixtures exercise encoding/provenance only, never auditory QA.
    for voice_id,label in configured:
        raw=('temporary-narration-fixture-'+voice_id).encode()
        voices.append({'voice_id':voice_id,'label':label,'provider':'Temporary test provider',
            'mime_type':'audio/mpeg','sha256':hashlib.sha256(raw).hexdigest(),
            'audio_base64':base64.b64encode(raw).decode(),'neural':True,'duration_seconds':2.,'language':'en' if english else 'zh-CN',
            'credential_should_not_export':'test-fixture-secret'})
    return {'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'default_voice':configured[0][0],'voices':voices,'available':True}


class NarrationPlayerTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.assets=Path(folder.name)

    def mocked(self,value):
        return patch.dict(sys.modules,{'narration':types.SimpleNamespace(get_narration_assets=lambda *a,**k:value)})

    def test_exact_text_and_audio_checksum_are_required_before_embedding(self):
        valid=fixture()
        with self.mocked(valid):
            value=_narration_payload(TEXT)
        self.assertTrue(value['available'])
        self.assertEqual(value['default_voice'],'zh-CN-XiaoxiaoNeural')
        self.assertEqual(len(value['voices']),2)
        self.assertNotIn('credential_should_not_export',value['voices'][0])
        with self.mocked(valid):
            self.assertFalse(_narration_payload(TEXT+' 修改')['available'])
        valid['voices'][0]['sha256']='0'*64
        with self.mocked(valid):
            value=_narration_payload(TEXT)
        self.assertEqual([v['voice_id'] for v in value['voices']],['zh-CN-YunxiNeural'])

    def test_rendered_description_and_voice_controls_are_bound_to_current_text(self):
        with self.mocked(fixture()):
            rendered=render_audio([],TEXT,self.assets)
        payload=json.loads(re.search(r'const CONFIG=(.*?);</script>',rendered,re.S).group(1))
        self.assertEqual(payload['narration']['text_sha256'],hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(rendered.count('id="narration-voice"'),1)
        self.assertEqual(rendered.count('id="voice-status"'),1)
        self.assertIn('id="narration-volume"',rendered)

    def test_payload_isolates_english_voice_and_never_embeds_a_chinese_fallback(self):
        text='An English stream guide.';valid=fixture(text)
        valid['voices'].extend(fixture()['voices'])
        with self.mocked(valid):
            result=_narration_payload(text,language='en')
        self.assertEqual([entry['voice_id'] for entry in result['voices']],['en-US-JennyNeural','en-US-GuyNeural'])
        self.assertEqual(result['default_voice'],'en-US-JennyNeural')
        with self.mocked(fixture()):
            for description in [TEXT,'','123…']:
                with self.subTest(description=description):
                    result=_narration_payload(description,language='en')
                    self.assertFalse(result['available'])
                    self.assertFalse(result['language_matches_text'])

    @unittest.skipUnless(shutil.which('node'),'Node runtime required for narration control checks')
    def test_neural_play_stop_selection_race_and_explicit_system_controls(self):
        for language,text in [('zh-CN',TEXT),('en',TEXT),('zh-CN','Original English preview.'),('en','Original English preview.'),('en',''),('zh-CN','')]:
            with self.subTest(language=language,text=text),self.mocked(fixture(text)):
                rendered=render_audio([],text,self.assets,language=language)
                config=json.loads(re.search(r'const CONFIG=(.*?);</script>',rendered,re.S).group(1))
                with tempfile.TemporaryDirectory() as folder:
                    root=Path(folder);(root/'config.json').write_text(json.dumps(config),encoding='utf-8')
                    (root/'check.js').write_text(HARNESS,encoding='utf-8')
                    process=subprocess.run([shutil.which('node'),str(root/'check.js'),str(root/'config.json'),str(ROOT/'audio_player.js')],
                        capture_output=True,text=True,check=True)
                result=json.loads(process.stdout)
                self.assertTrue(all(result['checks'].values()),result)


HARNESS=r'''
const fs=require('fs'),vm=require('vm');
const CONFIG=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{constructor(){this.children=[];this.listeners={};this.value='';this.disabled=false;this.style={};}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(){}click(){}}
const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
for(const [id,value] of Object.entries({version:CONFIG.default_preset,mode:'depth',volume:'0.25','narration-volume':'0.8'}))el(id).value=value;
class FakeAudio{static made=[];static defer=false;constructor(src){this.src=src;this.paused=true;this.currentTime=0;FakeAudio.made.push(this);}play(){this.paused=false;this.onplaying?.();return FakeAudio.defer?new Promise(resolve=>this.resolve=resolve):Promise.resolve();}pause(){this.paused=true;}}
class Utterance{constructor(text){this.text=text;}}
let systemSpeakCount=0,capturedBlob,capturedSystemLanguage,capturedSystemText;
const speechSynthesis={getVoices:()=>[{lang:'en-US',localService:true,name:'Temporary English system voice'},{lang:'zh-CN',localService:true,name:'Temporary Chinese system voice'}],addEventListener(){},cancel(){},speak(utterance){systemSpeakCount++;capturedSystemLanguage=utterance.lang;capturedSystemText=utterance.text;utterance.onstart?.();}};
const sandbox={CONFIG,document:{getElementById:el,createElement:()=>new Element(),querySelectorAll:()=>[]},window:{addEventListener(){},speechSynthesis},speechSynthesis,SpeechSynthesisUtterance:Utterance,Audio:FakeAudio,console,setTimeout,clearTimeout,Blob,URL:{createObjectURL:b=>{capturedBlob=b;return 'temporary';},revokeObjectURL(){}},atob:s=>Buffer.from(s,'base64').toString('binary')};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),sandbox);
const state=()=>sandbox.window.landscapeAudioDebug;const checks={};
(async()=>{
 const english=CONFIG.language==='en',female=english?'en-US-JennyNeural':'zh-CN-XiaoxiaoNeural',male=english?'en-US-GuyNeural':'zh-CN-YunxiNeural';
 checks.locale_voice_options_only=el('narration-voice').children.filter(option=>option.value!=='system').every(option=>(english?/^en-/:/^zh-/).test(option.value));
 if(!CONFIG.description.trim()||CONFIG.description_language!==(english?'en':'zh-CN')){
   checks.reading_is_disabled=el('speak').disabled&&el('narration-voice').disabled;
   for(const forced of [female,male,'system',english?'zh-CN-XiaoxiaoNeural':'en-US-JennyNeural']){
     el('narration-voice').value=forced;await vm.runInContext('speak()',sandbox);
   }
   checks.no_cross_language_neural_or_system_transport=FakeAudio.made.length===0&&systemSpeakCount===0&&!state().speechActive;
   checks.preparing_message=el('status').textContent.includes(english?'English guide still preparing':'中文导览仍在准备中');
   console.log(JSON.stringify({checks}));return;
 }
 checks.default_neural_female=el('narration-voice').value===female;
 await vm.runInContext('speak()',sandbox);let audio=FakeAudio.made.at(-1);
 checks.actual_neural_transport=audio.src.startsWith('data:audio/mpeg;base64,')&&!audio.paused&&state().speechActive&&systemSpeakCount===0;
 checks.localized_reading_status=el('status').textContent.includes(CONFIG.language==='en'?'Reading the original guide':'朗读');
 checks.localized_voice_options=el('narration-voice').children.some(option=>option.textContent.includes(english?'Natural English female':'自然女声'));
 vm.runInContext('stopAll()',sandbox);
 checks.stop_all_stops_narration=audio.paused&&!state().speechActive&&state().activeNodes===0;
 el('narration-voice').value=male;el('narration-voice').listeners.change();
 await vm.runInContext('speak()',sandbox);
 checks.explicit_male_selection=state().last_narration.voice_id===male;
 vm.runInContext('download()',sandbox);const exported=JSON.parse(await capturedBlob.text());
 checks.export_source_exact=exported.narration.text_sha256===CONFIG.narration.text_sha256&&exported.narration.audio_sha256===CONFIG.narration.voices[1].sha256&&!JSON.stringify(exported).includes('audio_base64');
 audio=FakeAudio.made.at(-1);await vm.runInContext('play()',sandbox);
 checks.scene_play_stops_narration=audio.paused&&!state().speechActive;
 const beforeWrong=FakeAudio.made.length;
 CONFIG.narration.voices.push({...CONFIG.narration.voices[0],voice_id:english?'zh-CN-XiaoxiaoNeural':'en-US-JennyNeural',language:english?'zh-CN':'en'});
 el('narration-voice').value=CONFIG.narration.voices.at(-1).voice_id;await vm.runInContext('speak()',sandbox);
 checks.injected_opposite_voice_cannot_play=FakeAudio.made.length===beforeWrong&&systemSpeakCount===0;
 CONFIG.narration.voices.pop();el('narration-voice').value=male;
 FakeAudio.defer=true;const pending=vm.runInContext('speak()',sandbox);audio=FakeAudio.made.at(-1);
 vm.runInContext('stopAll()',sandbox);audio.resolve();await pending;
 checks.stale_async_completion_cannot_resume=audio.paused&&!state().speechActive;
 FakeAudio.defer=false;CONFIG.narration.voices=[];const before=systemSpeakCount;
 await vm.runInContext('speak()',sandbox);
 checks.no_silent_system_fallback=systemSpeakCount===before&&!state().speechActive&&el('status').textContent.includes(CONFIG.language==='en'?'not generated':'尚未生成');
 el('narration-voice').value='system';el('narration-voice').listeners.change();await vm.runInContext('speak()',sandbox);
 checks.explicit_system_selection=systemSpeakCount===before+1&&state().last_narration.voice_id==='system';
 checks.system_voice_follows_original_text=capturedSystemLanguage===(CONFIG.description_language==='en'?'en-US':'zh-CN')&&capturedSystemText===CONFIG.description;
 checks.system_option_language=el('narration-voice').children.at(-1).textContent.includes(CONFIG.description_language==='en'?(CONFIG.language==='en'?'English':'英文'):(CONFIG.language==='en'?'Chinese':'旧配音'));
 vm.runInContext('stopAll()',sandbox);
 console.log(JSON.stringify({checks}));
})().catch(error=>{console.error(error);process.exit(1);});
'''


if __name__=='__main__':unittest.main()
