"""Durability and identity boundaries without calling a GPT/audio/TTS service."""
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

import panorama_pipeline as pipeline


def picture(color='green', size=(40, 20)):
    stream=io.BytesIO();Image.new('RGB',size,color).save(stream,format='PNG');return stream.getvalue()


class FixtureServices:
    def __init__(self):
        self.calls=dict(analysis=0,gpt=0,audio=0,narration=0)
        self.audio={};self.speech={};self.fail_narration=False;self.invalid_gpt=False

    def analyze(self,image,folder,title):
        self.calls['analysis']+=1;folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        views=[]
        for view_id,yaw in [('front',0),('right',90),('back',180),('left',-90)]:
            child=folder/'views'/view_id;child.mkdir(parents=True)
            files={}
            for name in ['input','segmentation','depth']:
                path=child/(name+'.png');image.save(path);files[name]=str(path)
            views.append({'id':view_id,'label':view_id,'yaw':yaw,'report':{'files':files,'scene':{'sources':[]}}})
        return {'title':title,'input':{'sha256_rgb':hashlib.sha256(image.tobytes()).hexdigest()},
            'views':views,'limitations':['No panoramic GPT description has been generated; the new views use local rules.',
                'Stereo HRTF and procedural illustrative sounds; no field recordings or user-perception validation.',
                'Depth is not metres.']}

    def vision(self,image_file,prompt,output_dir):
        self.calls['gpt']+=1
        if self.invalid_gpt:return {'response_text':'not a GPT JSON reply','provenance':{}}
        scene_id=re.search(r'scene id必须是 ([a-z0-9_]+)',prompt).group(1)
        value={'schema_version':1,'scenes':[{'id':scene_id,
            'visible_facts_zh':['右方可见一条岩石间的小溪，树木环绕两侧。'],
            'uncertainties_zh':['不能由静态照片确定水速、风速或声音响度。'],
            'narration_zh':'眼前是一处岩石和树木围合的小溪，右方的窄水流沿着岩面向下延伸。你可以在试听中留意水道的连续流动与石块间的轻微咕噜声，这些声音是根据图片设计的模拟。',
            'stems':[{'id':'stream_primary','category':'stream','label_zh':'岩石间小溪',
                'visual_evidence_zh':['右方画面有可见水线与岩石。'],
                'simulation_assumptions_zh':['低强度连续流水是模拟设定，不能当作现场实测。'],
                'prompt_en':'An intimate recording of a small stream running between stones. Rounded liquid gurgles and a narrow connected current vary naturally in a quiet outdoor space with short little splashes.',
                'relative_level':.7,'views':[{'view_id':'right','azimuth':-5,'spread_degrees':16,
                    'virtual_radius':3.2,'basis_zh':'依据右侧可见水线给出试听方位，距离不是米。'}]}]}]}
        return {'response_text':json.dumps(value,ensure_ascii=False),
                'provenance':{'provider':'web_chatgpt','conversation_url':'https://chatgpt.com/c/fixture-only-test',
                              'fixture_only':True}}

    def generate_audio(self,plan,root):
        self.calls['audio']+=1
        value={'assets_dir':str(Path(root)/'fixture_audio'/plan['cache_key']),
               'cache_key':plan['cache_key'],'generated':True,'reused':False,'stems':[],'fixture_only':True}
        self.audio[plan['cache_key']]=value;return copy.deepcopy(value)

    def load_audio(self,plan,root):return copy.deepcopy(self.audio.get(plan['cache_key']))

    def narrate(self,text,voices,root):
        self.calls['narration']+=1
        if self.fail_narration:raise RuntimeError('Temporary fixture speech failure')
        key=hashlib.sha256(text.encode()).hexdigest();existing=self.speech.get(key,{'voices':[]})
        records={x['voice_id']:x for x in existing['voices']}
        for voice in voices:records[voice]={'voice_id':voice,'audio_base64':'TEMPORARY_FIXTURE_NOT_AUDIO'}
        value={'text_sha256':key,'default_voice':pipeline.DEFAULT_VOICE,'voices':list(records.values()),'fixture_only':True}
        self.speech[key]=value;return copy.deepcopy(value)

    def load_narration(self,text,root):
        return copy.deepcopy(self.speech.get(hashlib.sha256(text.encode()).hexdigest(),{'voices':[]}))

    def mapping(self):return {name:getattr(self,name) for name in ['analyze','generate_audio','load_audio','narrate','load_narration']}


class PanoramaPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.services=FixtureServices();self.image=picture()
        self.sheet_patch=patch.object(pipeline,'_contact_sheet',side_effect=lambda image,sid,path:image.save(path,format='JPEG'))
        self.sheet_patch.start()

    def tearDown(self):self.sheet_patch.stop();self.temporary.cleanup()

    def run_job(self,**kwargs):
        return pipeline.run_pipeline(self.image,'Fixture panorama',root=self.root,
            vision_client=self.services.vision,services=self.services.mapping(),vision_identity={'fixture':'stable'},**kwargs)

    def test_fresh_run_binds_gpt_and_new_audio_and_does_not_alter_visual_report(self):
        events=[];result=self.run_job(progress=lambda x:events.append(x))
        self.assertEqual(result['status'],'complete')
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=1,narration=1))
        change=result['plan']['evidence']['automatic_acoustic_policy']['changes'][0]
        self.assertTrue(result['plan']['stems'][0]['prompt'].startswith(change['original_gpt_prompt']+' '))
        self.assertTrue(result['plan']['stems'][0]['prompt'].endswith(pipeline.STREAM_CONSTRAINT))
        self.assertEqual(result['plan']['stems'][0]['prompt_source'],'local_acoustic_policy_after_gpt')
        self.assertEqual(result['plan']['image_sha256_rgb'],result['image_sha256_rgb'])
        self.assertEqual(result['gpt_provenance']['response_sha256'],pipeline._digest(result['gpt_provenance']['response_file']))
        self.assertNotIn('audio_base64',result['narration']['voices'][0])
        self.assertTrue(result['narration_text'].startswith('眼前'))
        raw=json.loads(Path(result['report_path']).read_text(encoding='utf-8'))
        self.assertTrue(any('No panoramic GPT' in x for x in raw['limitations']))
        self.assertFalse(any('No panoramic GPT' in x for x in result['report']['limitations']))
        status=pipeline.load_job(result['job_id'],self.root)
        self.assertTrue(all(x['status']=='complete' for x in status['steps']))
        self.assertTrue(all(isinstance(x['duration_seconds'],float) for x in status['steps']))
        self.assertEqual(events[-1]['status'],'complete')

    def test_completed_retry_reuses_all_five_stages(self):
        first=self.run_job();second=self.run_job()
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=1,narration=1))
        self.assertEqual(second['plan']['cache_key'],first['plan']['cache_key'])
        self.assertEqual(set(second['reused_steps']),{x[0] for x in pipeline.STEPS})
        self.assertIsNotNone(pipeline.load_pipeline_result(second['job_id'],self.root,verify=False))

    def test_water_policy_preserves_each_gpt_scene_and_leaves_surf_unchanged(self):
        stream_a='A narrow shallow creek curls between close stones with uneven low bubbling and small spaced splashes.'
        stream_b='A high rocky waterfall falls in a broad resonant rush, with forceful liquid surges at its base.'
        surf='Slow ocean swells rise and retreat along a long sandy shore.'
        def plan(prompt,category):
            return {'stems':[{'category':category,'prompt':prompt,'prompt_source':'gpt', 'seed':17}],
                'evidence':{},'items':[],'cache_key':'before'}
        original_a=plan(stream_a,'stream')
        output_a=pipeline.apply_acoustic_policy(original_a)
        output_b=pipeline.apply_acoustic_policy(plan(stream_b,'stream'))
        output_surf=pipeline.apply_acoustic_policy(plan(surf,'surf'))
        for source,output in [(stream_a,output_a),(stream_b,output_b)]:
            self.assertEqual(output['stems'][0]['prompt'],source+' '+pipeline.STREAM_CONSTRAINT)
            change=output['evidence']['automatic_acoustic_policy']['changes'][0]
            self.assertEqual(change['original_gpt_prompt'],source)
            self.assertEqual(change['applied_prompt'],output['stems'][0]['prompt'])
            self.assertTrue(change['original_gpt_prompt_preserved'])
            self.assertEqual(output['items'],output['stems'])
        self.assertNotEqual(output_a['stems'][0]['prompt'],output_b['stems'][0]['prompt'])
        self.assertNotEqual(output_a['cache_key'],output_b['cache_key'])
        self.assertEqual(original_a['stems'][0]['prompt'],stream_a)
        self.assertEqual(output_surf['stems'][0]['prompt'],surf)
        self.assertEqual(output_surf['stems'][0]['prompt_source'],'gpt')
        self.assertEqual(output_surf['evidence']['automatic_acoustic_policy']['changes'],[])

    def test_traffic_policy_preserves_scene_rhythm_and_policy_version_invalidates_audio_only(self):
        original='A single distant bus engine passes slowly, followed by two short tire rolls with long quiet intervals.'
        plan={'stems':[{'category':'traffic','prompt':original,'prompt_source':'gpt'}],'items':[],'evidence':{}}
        adjusted=pipeline.apply_acoustic_policy(plan)
        self.assertEqual(adjusted['stems'][0]['prompt'],original+' '+pipeline.TRAFFIC_CONSTRAINT)
        self.run_job()
        with patch.object(pipeline,'ACOUSTIC_POLICY_VERSION','fixture-next-policy'):
            self.run_job()
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=2,narration=1))

    def test_failed_speech_resumes_without_repeating_analysis_gpt_or_audio(self):
        self.services.fail_narration=True
        with self.assertRaisesRegex(RuntimeError,'speech failure'):self.run_job()
        job=pipeline.load_job(pipeline.job_id_for(self.image),self.root)
        self.assertEqual(job['status'],'failed');self.assertEqual(job['current_step'],5)
        self.assertIsNone(pipeline.load_pipeline_result(job['job_id'],self.root))
        self.services.fail_narration=False;result=self.run_job()
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=1,narration=2))
        self.assertTrue(result['audio_result']['generated'])

    def test_invalid_gpt_never_generates_audio_or_speech_or_rule_fallback(self):
        self.services.invalid_gpt=True
        with self.assertRaisesRegex(ValueError,'Invalid GPT'):self.run_job()
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=0,narration=0))
        job=pipeline.load_job(pipeline.job_id_for(self.image),self.root)
        self.assertEqual(job['status'],'failed');self.assertEqual(job['current_step'],2)

    def test_changed_response_is_not_silently_reused(self):
        first=self.run_job();Path(first['gpt_provenance']['response_file']).write_text('altered',encoding='utf-8')
        self.run_job()
        self.assertEqual(self.services.calls['analysis'],1);self.assertEqual(self.services.calls['gpt'],2)

    def test_voice_addition_does_not_rerun_image_gpt_or_sound(self):
        self.run_job()
        result=self.run_job(narration_voices=[pipeline.DEFAULT_VOICE,'zh-CN-YunxiNeural'])
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=1,narration=2))
        self.assertEqual(len(result['narration']['voices']),2)

    def test_new_image_gets_separate_job_plan_and_gpt_request(self):
        first=self.run_job();self.image=picture('blue');second=self.run_job()
        self.assertNotEqual(first['job_id'],second['job_id'])
        self.assertNotEqual(first['plan']['cache_key'],second['plan']['cache_key'])
        self.assertEqual(self.services.calls['gpt'],2);self.assertEqual(self.services.calls['audio'],2)

    def test_cancellation_is_persisted_and_completed_steps_can_resume(self):
        def progress(state):
            if state['steps'][1]['status']=='complete':pipeline.request_cancel(state['job_id'],self.root)
        with self.assertRaises(pipeline.PipelineCancelled):self.run_job(progress=progress)
        job_id=pipeline.job_id_for(self.image)
        self.assertEqual(pipeline.load_job(job_id,self.root)['status'],'cancelled')
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=0,narration=0))
        pipeline.clear_cancellation(job_id,self.root);self.run_job()
        self.assertEqual(self.services.calls,dict(analysis=1,gpt=1,audio=1,narration=1))

    def test_invalid_geometry_and_job_paths_are_rejected(self):
        self.image=picture(size=(30,20))
        with self.assertRaisesRegex(ValueError,'2:1'):self.run_job()
        self.assertEqual(self.services.calls['analysis'],0)
        self.assertEqual(pipeline.load_job(pipeline.job_id_for(self.image),self.root)['status'],'failed')
        with self.assertRaises(ValueError):pipeline.job_dir('../outside',self.root)

    def test_active_job_lock_prevents_duplicate_workers(self):
        folder=pipeline.job_dir(pipeline.job_id_for(self.image),self.root);folder.mkdir(parents=True)
        with pipeline._lock(folder):
            with self.assertRaisesRegex(RuntimeError,'正在处理'):
                with pipeline._lock(folder):pass
        self.assertFalse((folder/'.job.lock').exists())

    def test_verified_read_checks_saved_stage_artifacts(self):
        result=self.run_job();job_id=result['job_id']
        with patch('scene_audio_runtime.load_scene_audio',side_effect=self.services.load_audio),patch('narration.get_narration_assets',side_effect=self.services.load_narration):
            self.assertIsNotNone(pipeline.load_pipeline_result(job_id,self.root))
            Path(result['plan_path']).write_text('{}',encoding='utf-8')
            self.assertIsNone(pipeline.load_pipeline_result(job_id,self.root))

    def test_default_analysis_uses_a_separate_child_before_audio_imports(self):
        output=self.root/'job'/'analysis';seen=[]
        def fake_child(command,**options):
            seen.append((command,options))
            output.mkdir(parents=True,exist_ok=True)
            (output/'report.json').write_text(json.dumps({'input':{'sha256_rgb':'fixture'},'fixture_only':True}),encoding='utf-8')
            return SimpleNamespace(returncode=0,stdout='Temporary child fixture only')
        with patch('subprocess.run',side_effect=fake_child):
            result=pipeline._default_services()['analyze'](Image.new('RGB',(40,20),'green'),output,'Fixture')
        self.assertTrue(result['fixture_only'])
        command,options=seen[0]
        self.assertIn('--analysis-only',command)
        self.assertIn('--analysis-output',command)
        self.assertTrue((output.parent/'input.png').is_file())
        self.assertNotIn('shell',options)
        if pipeline.os.name=='nt':self.assertEqual(options['creationflags'],pipeline.subprocess.CREATE_NO_WINDOW)


if __name__=='__main__':unittest.main()
