"""Upload integration checks with all inference, network, and workers mocked."""
import hashlib
import base64
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage

import auto_pipeline_ui as ui
import panorama_pipeline as pipeline
import panorama_ui


def picture():
    stream=io.BytesIO();Image.new('RGB',(80,40),'green').save(stream,format='PNG')
    return stream.getvalue()


class Uploaded(io.BytesIO):
    name='a new panorama.png'


def completed_result(raw,root):
    image=Image.open(io.BytesIO(raw)).convert('RGB');rgb=hashlib.sha256(image.tobytes()).hexdigest()
    job_id=pipeline.job_id_for(raw);description='这是测试专用的一段独立中文导览，描述眼前石块间的水道。'
    sources=[{'id':'stream_right','category':'stream','azimuth':8,'radius':3.2,'gain':.7}]
    report={'title':'全新上传测试','input':{'sha256_rgb':rgb},'views':[
        {'id':key,'label':key,'yaw':yaw,'report':{'scene':{'description':'旧规则文字不能代替本图导览','sources':[{'category':'trees'}]},'files':{}}}
        for key,yaw in [('front',0),('right',90),('back',180),('left',-90)]]}
    provenance={'provider':'codex_cli','image_sha256_rgb':rgb,'fixture_only':True}
    plan={'cache_key':'c'*64,'image_sha256_rgb':rgb,'condition':'automatic_gpt_with_acoustic_policy',
        'evidence':{'gpt_provenance':provenance,'visible_facts_zh':['石块之间有一条水道。'],'uncertainties_zh':['动态声音是模拟。']},
        'stems':[{'category':'stream','label_zh':'流水','visual_facts':['可见石间水道'],
                  'sound_assumptions':['模拟连续水流'],'prompt':'A flowing stream with gently bubbling and splashing water.'}],
        'views':{key:{'sources':sources if key=='right' else []} for key in ['front','right','back','left']}}
    return {'job_id':job_id,'status':'complete','report':report,'plan':plan,'image_sha256_rgb':rgb,
        'audio_result':{'assets_dir':str(root/'fixture_audio'),'manifest_path':str(root/'fixture_audio'/'manifest.json')},
        'narration_text':description,'narration_guide':{'text':description,'provenance':{'fixture_only':True}},
        'narration':{'voices':[{'voice_id':'zh-CN-XiaoxiaoNeural'}]},'requested_voice_ids':['zh-CN-XiaoxiaoNeural']}


class WorkerLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.raw=picture()
        (self.root/'.venv'/'Scripts').mkdir(parents=True);(self.root/'.venv'/'Scripts'/'python.exe').touch()
        (self.root/'panorama_pipeline.py').touch()

    def tearDown(self):self.temp.cleanup()

    def test_exact_raw_bytes_saved_and_live_worker_not_duplicated(self):
        title='测试图 " & harmless literal $(text)'
        with patch.object(ui.subprocess,'Popen',return_value=Mock(pid=42424)) as popen, \
             patch.object(ui,'_process_alive',side_effect=lambda pid:pid==42424):
            first=ui.launch_pipeline_worker(self.raw,title,self.root)
            second=ui.launch_pipeline_worker(self.raw,title,self.root)
            self.assertTrue(first['started']);self.assertFalse(second['started']);self.assertEqual(popen.call_count,1)
            args,kwargs=popen.call_args;command=args[0]
            self.assertIsInstance(command,list);self.assertFalse(kwargs['shell'])
            self.assertEqual(command[command.index('--title')+1],title)
            self.assertEqual(command[command.index('--input')+1],str(pipeline.job_dir(first['job_id'],self.root)/'uploaded_input.bin'))
            self.assertEqual(Path(command[command.index('--input')+1]).read_bytes(),self.raw)
            self.assertEqual(first['job_id'],hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(kwargs['creationflags'],0x08000000 if os.name=='nt' else 0)

    def test_failed_task_requires_explicit_retry_and_retains_artifacts(self):
        identifier,target=ui.save_uploaded_input(self.raw,'测试',self.root)
        folder=pipeline.job_dir(identifier,self.root);marker=folder/'kept.txt';marker.write_text('completed stage')
        pipeline.request_cancel(identifier,self.root)
        ui._write_json(folder/'status.json',{'status':'failed','steps':[{'id':'analysis','status':'complete'}]})
        with patch.object(ui.subprocess,'Popen',return_value=Mock(pid=42424)) as popen,patch.object(ui,'_process_alive',return_value=False):
            first=ui.launch_pipeline_worker(self.raw,'测试',self.root)
            self.assertFalse(first['started']);popen.assert_not_called()
            self.assertTrue(ui.launch_pipeline_worker(self.raw,'测试',self.root,retry=True)['started'])
            self.assertFalse((folder/'cancel.request').exists());self.assertEqual(marker.read_text(),'completed stage')
            self.assertEqual(target.read_bytes(),self.raw)

    def test_this_pipeline_plan_precedes_every_legacy_scene_plan(self):
        result=completed_result(self.raw,self.root)
        with patch('optimize_scene_audio.load_optimized_plan',side_effect=AssertionError('old plan used')):
            self.assertIs(panorama_ui._audio_plan(result['report'],self.root,'fish_hoek_beach',result),result['plan'])
            result['image_sha256_rgb']='e'*64
            with self.assertRaises(ValueError):panorama_ui._audio_plan(result['report'],self.root,'fish_hoek_beach',result)

    def test_recent_uploads_are_limited_and_selected_original_is_hash_checked(self):
        saved=[]
        for index in range(7):
            raw=self.raw+bytes([index]);identifier,target=ui.save_uploaded_input(raw,'任务'+str(index),self.root)
            request=target.parent/'ui_request.json';os.utime(request,(100+index,100+index));saved.append((identifier,raw))
        recent=ui.recent_upload_requests(self.root,limit=50)
        self.assertEqual(len(recent),5);self.assertEqual(recent[0]['job_id'],saved[-1][0])
        self.assertEqual(ui.load_saved_upload(saved[-1][0],self.root)['raw'],saved[-1][1])
        selected=pipeline.job_dir(saved[-1][0],self.root)/'uploaded_input.bin';selected.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'指纹不一致'):ui.load_saved_upload(saved[-1][0],self.root)

    def test_recent_upload_paths_cannot_escape_the_job_directory(self):
        identifier,target=ui.save_uploaded_input(self.raw,'任务',self.root)
        outside=self.root/'outside.png';outside.write_bytes(self.raw)
        request=target.parent/'ui_request.json';value=ui._read_json(request);value['input_file']=str(outside);ui._write_json(request,value)
        self.assertEqual(ui.recent_upload_requests(self.root),[])
        with self.assertRaises(ValueError):ui.load_saved_upload(identifier,self.root)
        with self.assertRaises(ValueError):ui.load_saved_upload('../outside',self.root)


class UploadAppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.raw=picture()
        self.job_id=pipeline.job_id_for(self.raw);self.asset_id='upload_'+self.job_id[:12]
        self.script='from pathlib import Path\nfrom panorama_ui import render_panorama_ui\nrender_panorama_ui(Path('+repr(str(self.root))+'))\n'

    def tearDown(self):self.temp.cleanup()

    def prepare(self):
        app=AppTest.from_string(self.script,default_timeout=15).run()
        app.radio(key='panorama_source_kind').set_value('上传我的全景图').run()
        self.assertFalse(app.exception)
        return app

    def test_confirmation_starts_automatically_once_and_pending_has_no_old_audio(self):
        status={'status':'running','message':'正在让 GPT 理解这张全景…','current_step':2,
            'steps':[{'id':'analysis','label':'分析全景与四个方向','status':'complete'},
                     {'id':'gpt','label':'GPT 理解画面','status':'running'}]}
        with patch('streamlit.file_uploader',side_effect=lambda *a,**k:Uploaded(self.raw)), \
             patch.object(pipeline,'load_job',return_value=status), \
             patch.object(ui,'launch_pipeline_worker',return_value={'started':True}) as launch, \
             patch.object(ui,'worker_is_running',return_value=True), \
             patch('panorama_ui._audio_plan',side_effect=AssertionError('pending must not play legacy audio')):
            app=self.prepare();launch.assert_not_called()
            app.checkbox(key='panorama_confirm_'+self.asset_id).check().run()
            self.assertFalse(app.exception);launch.assert_called_once()
            self.assertEqual(len(app.get('iframe')),0)
            self.assertFalse(any(button.label=='分析上传全景并生成声音' for button in app.button))
            self.assertTrue(any('发送给 GPT' in element.value and 'Microsoft' in element.value for element in app.caption))
            self.assertTrue(any('正在让 GPT' in element.proto.text for element in app.get('progress')))

    def test_complete_upload_uses_own_plan_audio_and_exact_narration_for_all_views(self):
        result=completed_result(self.raw,self.root);calls=[];storages=[]
        def storage(*args,**kwargs):
            value=MemoryMediaFileStorage(*args,**kwargs);storages.append(value);return value
        def exported(app):
            download=app.get('download_button')[0].proto.url.rsplit('/',1)[-1]
            return json.loads(storages[-1].get_file(download).content.decode('utf-8'))
        def render(sources,text,assets,duration):
            calls.append((sources,text,str(assets)))
            return '<script>const CONFIG='+json.dumps({'description':text,'sources':sources},ensure_ascii=False)+';</script>'
        def narration(text,root,key):
            self.assertEqual(text,result['narration_text'])
            return {'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'available_voice_ids':['zh-CN-XiaoxiaoNeural']}
        with patch('streamlit.file_uploader',side_effect=lambda *a,**k:Uploaded(self.raw)), \
             patch('streamlit.testing.v1.app_test.MemoryMediaFileStorage',side_effect=storage), \
             patch.object(pipeline,'load_job',return_value={'status':'complete'}), \
             patch.object(pipeline,'load_pipeline_result',return_value=result) as load, \
             patch.object(ui,'launch_pipeline_worker',side_effect=AssertionError('cached read spawned worker')), \
             patch('scene_audio_runtime.load_scene_audio',side_effect=AssertionError('must use verified pipeline audio result')), \
             patch('optimize_scene_audio.load_optimized_plan',side_effect=AssertionError('legacy plan used')), \
             patch('narration_ui.scene_narration_guide',side_effect=AssertionError('old narration used')), \
             patch('narration_ui.render_narration_controls',side_effect=narration), \
             patch('browser_audio.render_audio',side_effect=render), \
             patch('narration.ensure_narration',side_effect=AssertionError('online speech called')), \
             patch('scene_audio_runtime.ensure_scene_audio',side_effect=AssertionError('model called')):
            app=self.prepare();app.checkbox(key='panorama_confirm_'+self.asset_id).check().run()
            self.assertFalse(app.exception);self.assertEqual(len(app.get('iframe')),1)
            load.assert_called_with(self.job_id,root=self.root,verify=True)
            for view_id in ['right','back','left','front']:
                app.radio(key='panorama_view_'+self.asset_id).set_value(view_id).run()
                self.assertFalse(app.exception)
                self.assertEqual(len(app.get('iframe')),1)
                saved=exported(app)
                self.assertEqual(saved['scene_audio_plan'],result['plan'])
                self.assertEqual(saved['automatic_pipeline']['job_id'],self.job_id)
                self.assertEqual(saved['narration']['text'],result['narration_text'])
                self.assertEqual(saved['scene_audio_materials']['view_sources'],result['plan']['views'][view_id]['sources'])
            self.assertEqual(len(calls),5)
            for call,view_id in zip(calls,['front','right','back','left','front']):
                self.assertEqual(call,(result['plan']['views'][view_id]['sources'],result['narration_text'],result['audio_result']['assets_dir']))
            self.assertTrue(any('官方 GPT 入口自动理解' in element.value for element in app.info))

    def test_direction_without_scene_sources_still_embeds_exact_neural_guide(self):
        result=completed_result(self.raw,self.root);text=result['narration_text'];speech=b'temporary fixture narration bytes'
        cached={'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'provider':'fixture','default_voice':'zh-CN-XiaoxiaoNeural',
            'voices':[{'voice_id':'zh-CN-XiaoxiaoNeural','label':'自然女声 · 晓晓','provider':'fixture','neural':True,
                       'mime_type':'audio/mpeg','audio_base64':base64.b64encode(speech).decode(),'sha256':hashlib.sha256(speech).hexdigest()}]}
        with patch('streamlit.file_uploader',side_effect=lambda *a,**k:Uploaded(self.raw)), \
             patch.object(pipeline,'load_job',return_value={'status':'complete'}), \
             patch.object(pipeline,'load_pipeline_result',return_value=result), \
             patch.object(ui,'launch_pipeline_worker',side_effect=AssertionError('cached view spawned worker')), \
             patch('narration.get_narration_assets',return_value=cached), \
             patch('narration.ensure_narration',side_effect=AssertionError('online speech called')), \
             patch('scene_audio_runtime.ensure_scene_audio',side_effect=AssertionError('model called')):
            app=self.prepare();app.checkbox(key='panorama_confirm_'+self.asset_id).check().run()
            app.radio(key='panorama_view_'+self.asset_id).set_value('left').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('声景保持无声；仍可朗读' in element.value for element in app.info))
            player=app.get('iframe')[0].proto.srcdoc
            payload=json.loads(re.search(r'const CONFIG=(.*?);</script>',player,re.S).group(1))
            self.assertEqual(payload['sources'],[]);self.assertEqual(payload['layers'],[])
            self.assertEqual(payload['audio'],{})
            self.assertTrue(payload['narration']['available'])
            self.assertEqual(payload['description'],text)
            self.assertEqual(payload['narration']['default_voice'],'zh-CN-XiaoxiaoNeural')
            self.assertEqual(payload['narration']['text_sha256'],hashlib.sha256(text.encode()).hexdigest())
            self.assertIn('id="speak"',player)
            self.assertIn('id="narration-only-intro"',player)
            self.assertIn('此方向没有配置声源，声景保持无声。',player)
            self.assertIn('<button id="stop" class="stop">停止朗读</button>',player)
            style=re.search(r'<style id="narration-only-style">(.*?)</style>',player,re.S).group(1)
            self.assertIn('main > .toolbar:first-of-type',style)
            self.assertIn('#play, #calibrate, #export',style)
            self.assertIn('main > details',style)
            self.assertIn('main > p:not(#voice-status)',style)
            self.assertIn('{display:none!important}',style)

    def test_sound_source_direction_keeps_the_full_player(self):
        result=completed_result(self.raw,self.root)
        def render(sources,*args):
            return '<style></style><main aria-label="景观声音与描述播放器"><h2>连续声景试听</h2></main>'
        with patch('streamlit.file_uploader',side_effect=lambda *a,**k:Uploaded(self.raw)), \
             patch.object(pipeline,'load_job',return_value={'status':'complete'}), \
             patch.object(pipeline,'load_pipeline_result',return_value=result), \
             patch.object(ui,'launch_pipeline_worker',side_effect=AssertionError('cached read spawned worker')), \
             patch('narration_ui.render_narration_controls',return_value={}), \
             patch('browser_audio.render_audio',side_effect=render):
            app=self.prepare();app.checkbox(key='panorama_confirm_'+self.asset_id).check().run()
            app.radio(key='panorama_view_'+self.asset_id).set_value('right').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.get('iframe')[0].proto.srcdoc,render(result['plan']['views']['right']['sources']))

    def test_empty_uploader_recovers_selected_completed_task_without_generation(self):
        ui.save_uploaded_input(self.raw,'上次的全景',self.root)
        ui._write_json(pipeline.job_dir(self.job_id,self.root)/'status.json',{'status':'complete'})
        result=completed_result(self.raw,self.root)
        with patch('streamlit.file_uploader',return_value=None), \
             patch.object(pipeline,'load_job',return_value={'status':'complete'}), \
             patch.object(pipeline,'load_pipeline_result',return_value=result) as load, \
             patch.object(ui,'launch_pipeline_worker',side_effect=AssertionError('recovery started generation')), \
             patch('scene_audio_runtime.ensure_scene_audio',side_effect=AssertionError('model called')), \
             patch('narration.ensure_narration',side_effect=AssertionError('network speech called')), \
             patch('narration_ui.render_narration_controls',return_value={'fixture_only':True}), \
             patch('narration_ui.scene_narration_guide',side_effect=AssertionError('old guide used')):
            app=self.prepare()
            recent=app.selectbox(key='recent_auto_upload_job')
            self.assertIn('上次的全景 · 已完成',recent.options)
            self.assertFalse(app.get('download_button'))
            recent.set_value(self.job_id).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('download_button')),1)
            load.assert_called_with(self.job_id,root=self.root,verify=True)
            self.assertEqual(app.radio(key='panorama_view_'+self.asset_id).value,'front')
            app.run();self.assertFalse(app.exception)
            self.assertEqual(len(app.get('download_button')),1)


if __name__=='__main__':unittest.main()
