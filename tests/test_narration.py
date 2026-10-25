"""Narration identity and checksum behavior; fixtures are not production TTS."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from narration import (get_narration_assets,text_sha256,VOICES,PROVIDER,NARRATION_VERSION,
                       SYNTHESIS_CONFIG,ensure_narration)


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.text='这是一段测试用的景观描述。'
    def tearDown(self):self.temporary.cleanup()
    def fixture(self,voice='zh-CN-XiaoxiaoNeural'):
        digest=text_sha256(self.text);folder=self.root/'assets'/'narration'/digest
        folder.mkdir(parents=True,exist_ok=True);path=folder/(voice+'.mp3')
        raw=b'ID3'+bytes(range(255))*8;path.write_bytes(raw)
        record={'version':NARRATION_VERSION,'text':self.text,'text_sha256':digest,'voice_id':voice,
            'neural':True,'provider':PROVIDER,'synthesis_config':dict(SYNTHESIS_CONFIG),
            'duration_seconds':4.,'sha256':hashlib.sha256(raw).hexdigest(),'fixture_only':True}
        (folder/(voice+'.json')).write_text(json.dumps(record),encoding='utf-8');return path
    def test_exact_text_hash_does_not_strip_or_normalize(self):
        self.assertNotEqual(text_sha256(self.text),text_sha256(self.text+' '))
    def test_missing_narration_returns_unavailable_without_network(self):
        result=get_narration_assets(self.text,self.root)
        self.assertFalse(result['available']);self.assertEqual(result['voices'],[])
    def test_empty_description_is_readable_but_not_synthesized(self):
        self.assertFalse(get_narration_assets('',self.root)['available'])
        with self.assertRaises(ValueError):ensure_narration('',root=self.root)
    def test_valid_record_has_base64_and_default_voice(self):
        path=self.fixture();result=get_narration_assets(self.text,self.root)
        self.assertTrue(result['available']);self.assertEqual(result['default_voice'],'zh-CN-XiaoxiaoNeural')
        self.assertEqual(base64.b64decode(result['voices'][0]['audio_base64']),path.read_bytes())
    def test_tampered_audio_is_not_used(self):
        path=self.fixture();path.write_bytes(path.read_bytes()+b'tamper')
        self.assertFalse(get_narration_assets(self.text,self.root)['available'])
    def test_changed_text_does_not_play_previous_cache(self):
        self.fixture();self.assertFalse(get_narration_assets(self.text+'新内容',self.root)['available'])
    def test_male_only_default_is_first_available_not_missing_female(self):
        self.fixture('zh-CN-YunxiNeural')
        self.assertEqual(get_narration_assets(self.text,self.root)['default_voice'],'zh-CN-YunxiNeural')
    def test_unconfigured_voices_and_missing_environment_fail_explicitly(self):
        with self.assertRaises(ValueError):ensure_narration(self.text,['unknown'],self.root)
        with self.assertRaisesRegex(RuntimeError,'未自动改用系统配音'):
            ensure_narration(self.text,root=self.root)


if __name__=='__main__':unittest.main()
