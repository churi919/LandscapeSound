"""Automatic provenance checks using synthetic data, never saved GPT replies."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from gpt_scene_audio import build_gpt_panorama_audio_plan,load_gpt_panorama_audio_plan


class AutomaticGPTProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.report={'id':'synthetic_stream','title':'Synthetic provenance fixture',
            'input':{'sha256_rgb':'a'*64},'views':[
                {'id':key,'label':key,'yaw':yaw,'report':{'scene':{'sources':[]}}}
                for key,yaw in [('front',0),('right',90),('back',180),('left',-90)]]}
        self.scene={'id':'synthetic_stream','visible_facts_zh':['测试夹具设定：石间可见水道。'],
            'uncertainties_zh':['测试夹具不代表真实照片、现场声音或GPT输出。'],
            'stems':[{'id':'water','category':'stream','label_zh':'测试流水',
                'visual_evidence_zh':['仅为模式校验而构造的石间水道事实。'],
                'simulation_assumptions_zh':['测试声音计划不是实际生成结果。'],
                'prompt_en':('A synthetic test description of a connected rocky stream. '
                    'Rounded liquid movement gathers into a soft current, followed by '
                    'slower intervals and occasional separated swells. Maintain gentle '
                    'variation in the underlying continuous flow with low resonant details.'),
                'relative_level':.6,'views':[{'view_id':'front','azimuth':12,
                    'spread_degrees':20,'virtual_radius':3.5,'basis_zh':'合成测试方位。'}]}]}
        self.source={'provider':'codex_cli','model':'configured-test-model','cli_version':'test-client',
            'response_file':'temporary-test-response.json','response_sha256':'b'*64,
            'image_sha256_rgb':self.report['input']['sha256_rgb']}

    def test_automatic_source_stays_distinct_and_roundtrips(self):
        p=build_gpt_panorama_audio_plan(self.report,self.scene,self.source)
        self.assertEqual(p['planner_version'],'logged-in-gpt-panorama-audio-v1')
        self.assertEqual(p['evidence']['gpt_provenance']['provider'],'codex_cli')
        self.assertNotIn('conversation_url',p['evidence']['gpt_provenance'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'plan.json';path.write_text(json.dumps(p),encoding='utf-8')
            self.assertEqual(load_gpt_panorama_audio_plan(self.report,path),p)

    def test_credentials_and_fake_web_conversation_are_rejected(self):
        for key,value in [('access_token','test-not-real'),('conversation_url','https://chatgpt.com/c/test')]:
            source=copy.deepcopy(self.source);source[key]=value
            with self.assertRaises(ValueError):build_gpt_panorama_audio_plan(self.report,self.scene,source)

    def test_automatic_model_and_client_are_required(self):
        source=copy.deepcopy(self.source);source.pop('model')
        with self.assertRaises(ValueError):build_gpt_panorama_audio_plan(self.report,self.scene,source)
