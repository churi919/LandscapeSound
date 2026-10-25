"""Narration identity and checksum behavior; fixtures are not production TTS."""
import base64
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from narration import (get_narration_assets,text_sha256,VOICES,PROVIDER,NARRATION_VERSION,
                       SYNTHESIS_CONFIG,ensure_narration,DEFAULT_VOICE,
                       default_voice_for_language,voices_for_language)


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.text='这是一段测试用的景观描述。'
    def tearDown(self):self.temporary.cleanup()
    def fixture(self,voice='zh-CN-XiaoxiaoNeural',text=None):
        text=self.text if text is None else text
        digest=text_sha256(text);folder=self.root/'assets'/'narration'/digest
        folder.mkdir(parents=True,exist_ok=True);path=folder/(voice+'.mp3')
        raw=b'ID3'+bytes(range(255))*8;path.write_bytes(raw)
        record={'version':NARRATION_VERSION,'text':text,'text_sha256':digest,'voice_id':voice,
            'neural':True,'provider':PROVIDER,'synthesis_config':dict(SYNTHESIS_CONFIG),
            'duration_seconds':4.,'sha256':hashlib.sha256(raw).hexdigest(),'fixture_only':True}
        if VOICES[voice]['language']=='en':record['language']='en'
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

    def test_locale_voice_defaults_and_voice_lists_are_isolated(self):
        self.assertEqual(DEFAULT_VOICE,'zh-CN-XiaoxiaoNeural')
        self.assertEqual(default_voice_for_language('en-US'),'en-US-JennyNeural')
        self.assertEqual(default_voice_for_language('zh-CN'),DEFAULT_VOICE)
        self.assertEqual(set(voices_for_language('en')),{'en-US-JennyNeural','en-US-GuyNeural'})
        self.assertEqual(set(voices_for_language('zh-CN')),{'zh-CN-XiaoxiaoNeural','zh-CN-YunxiNeural'})
        voices_for_language('en')['en-US-JennyNeural']['language']='changed fixture'
        self.assertEqual(VOICES['en-US-JennyNeural']['language'],'en')

    def test_english_cache_is_read_only_and_defaults_to_jenny(self):
        text='A quiet stream flows between the rocks.'
        self.fixture('en-US-GuyNeural',text);path=self.fixture('en-US-JennyNeural',text)
        before=path.read_bytes()
        with patch('narration.subprocess.run',side_effect=AssertionError('Cache reads must be offline')):
            result=get_narration_assets(text,self.root,language='en')
            reused=ensure_narration(text,root=self.root,language='en')
        self.assertEqual(result['default_voice'],'en-US-JennyNeural')
        self.assertEqual({item['language'] for item in result['voices']},{'en'})
        self.assertEqual(reused['default_voice'],'en-US-JennyNeural')
        self.assertEqual(path.read_bytes(),before)

    def test_cross_language_voice_and_text_are_never_exposed_or_synthesized(self):
        english='A path beside a stream.'
        self.fixture();self.fixture('en-US-JennyNeural',english)
        # Even a syntactically valid misfiled voice record cannot cross locales.
        self.fixture('en-US-JennyNeural',self.text)
        with patch('narration.subprocess.run',side_effect=AssertionError('No cross-language service call')):
            self.assertFalse(get_narration_assets(self.text,self.root,language='en')['available'])
            self.assertFalse(get_narration_assets(english,self.root,language='zh-CN')['available'])
            self.assertEqual({x['voice_id'] for x in get_narration_assets(self.text,self.root)['voices']},{DEFAULT_VOICE})
            for text,voice,language in [(self.text,'en-US-JennyNeural','en'),
                    (self.text,'en-US-JennyNeural','zh-CN'),(english,DEFAULT_VOICE,'en')]:
                with self.subTest(voice=voice,language=language),self.assertRaises(ValueError):
                    ensure_narration(text,[voice],self.root,language=language)

    def test_english_cache_requires_explicit_correct_language_metadata(self):
        text='An English guide.';path=self.fixture('en-US-JennyNeural',text)
        metadata_path=path.with_suffix('.json');record=json.loads(metadata_path.read_text(encoding='utf-8'))
        for incorrect in [None,'zh-CN']:
            with self.subTest(language=incorrect):
                altered=dict(record)
                if incorrect is None:altered.pop('language')
                else:altered['language']=incorrect
                metadata_path.write_text(json.dumps(altered),encoding='utf-8')
                self.assertFalse(get_narration_assets(text,self.root,language='en')['available'])

    def test_default_generation_requests_only_english_voices_with_locale_flag(self):
        text='An English-only fixture guide.'
        interpreter=self.root/'.venv_narration'/'Scripts'/'python.exe'
        interpreter.parent.mkdir(parents=True);interpreter.touch();(self.root/'synthesize_narration.py').touch()
        def fake_worker(command,**kwargs):
            voice=command[command.index('--voice')+1]
            self.assertEqual(command[command.index('--language')+1],'en')
            self.fixture(voice,text)
            return type('CompletedFixture',(),{'returncode':0})()
        with patch('narration.subprocess.run',side_effect=fake_worker) as worker:
            result=ensure_narration(text,root=self.root,language='en')
        requested={call.args[0][call.args[0].index('--voice')+1] for call in worker.call_args_list}
        self.assertEqual(requested,set(voices_for_language('en')))
        self.assertEqual(result['default_voice'],'en-US-JennyNeural')

    def test_invalid_existing_cache_is_preserved_instead_of_overwritten(self):
        path=self.fixture();path.write_bytes(b'corrupted fixture evidence');original=path.read_bytes()
        with patch('narration.subprocess.run',side_effect=AssertionError('Preserve existing cache')):
            with self.assertRaisesRegex(RuntimeError,'will not be overwritten'):
                ensure_narration(self.text,[DEFAULT_VOICE],self.root)
        self.assertEqual(path.read_bytes(),original)

    def test_direct_worker_rejects_cross_language_and_reuses_valid_cache_offline(self):
        from synthesize_narration import synthesize
        path=self.fixture();original=path.read_bytes()
        result=asyncio.run(synthesize(self.text,DEFAULT_VOICE,self.root,language='zh-CN'))
        self.assertTrue(result['reused']);self.assertEqual(path.read_bytes(),original)
        with self.assertRaises(ValueError):
            asyncio.run(synthesize(self.text,'en-US-JennyNeural',self.root,language='en'))

    def test_worker_writes_english_language_metadata_without_a_real_service(self):
        from synthesize_narration import synthesize
        text='A completely synthetic English fixture guide.';calls=[]
        class FixtureCommunicate:
            def __init__(self,requested_text,voice,**options):calls.append((requested_text,voice))
            async def save(self,path):Path(path).write_bytes(b'ID3'+bytes(range(255))*8)
        info=types.SimpleNamespace(length=4.,sample_rate=24000,channels=1,bitrate=48000)
        with patch.dict('sys.modules',{
                'edge_tts':types.SimpleNamespace(Communicate=FixtureCommunicate,__version__='fixture-only'),
                'mutagen.mp3':types.SimpleNamespace(MP3=lambda path:types.SimpleNamespace(info=info))}):
            result=asyncio.run(synthesize(text,'en-US-JennyNeural',self.root,language='en'))
            cached=asyncio.run(synthesize(text,'en-US-JennyNeural',self.root,language='en'))
        self.assertFalse(result['reused']);self.assertTrue(cached['reused'])
        self.assertEqual(calls,[(text,'en-US-JennyNeural')])
        record=json.loads(Path(result['file']).with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(record['language'],'en')
        self.assertEqual(record['text'],text)
        self.assertEqual(get_narration_assets(text,self.root,language='en')['default_voice'],'en-US-JennyNeural')


if __name__=='__main__':unittest.main()
