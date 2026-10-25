import json
import re
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from audio_player_v2 import render_audio
from ui_i18n import get_language, set_language

class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.assets=Path(self.temporary.name)
        for profile,value in [('natural',1200),('legacy',600)]:
            folder=self.assets/profile;folder.mkdir()
            with wave.open(str(folder/'trees.wav'),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000)
                output.writeframes(struct.pack('<h',value)*8000)
        # Synthetic byte fixtures only, not recordings or production AI audio.
        metadata={'not_ai_generated':True,'not_pictured_site_recording':True,
            'items':[{'category':'trees','fixture_only':True}]}
        (self.assets/'natural'/'manifest.json').write_text(json.dumps(metadata),encoding='utf-8')

    def test_description_cannot_break_the_embedded_payload_or_trigger_template_replacement(self):
        description='__SCRIPT__ __PAYLOAD__ __DESCRIPTION__ __PRESET_OPTIONS__ </script><img src=x onerror=1>'
        result=render_audio([],description,self.assets)
        payload=re.search(r'<script>const CONFIG=(.*?);</script>',result,re.S).group(1)
        self.assertEqual(json.loads(payload)['description'],description)
        self.assertNotIn('</script><img src=x onerror=1>',result)
        self.assertEqual(result.count("'use strict';"),1)

    def test_natural_materials_are_marked_recordings_and_disabled_birds_stay_disabled(self):
        source={'id':'tree','category':'trees','azimuth':-20,'virtual_radius':5,'enabled':True,'area_fraction':.2}
        result=render_audio([source,{'id':'bird','category':'bird','enabled':False}], 'test',self.assets)
        payload=json.loads(re.search(r'<script>const CONFIG=(.*?);</script>',result,re.S).group(1))
        self.assertEqual(payload['version'],2)
        self.assertTrue(payload['provenance']['not_pictured_site_recording'])
        self.assertTrue(payload['provenance']['not_ai_generated'])
        self.assertEqual(len(payload['layers']),1)
        self.assertNotEqual(payload['audio']['natural_trees'],payload['audio']['legacy_trees'])

    def test_english_controls_do_not_translate_original_content_or_change_audio_data(self):
        description='原始中文导览：播放声景 __DESCRIPTION__，用户文字不得替换。'
        sources=[{'id':'fixture','label':'用户自定义树木区域','category':'trees',
                  'azimuth':12,'virtual_radius':3.5,'enabled':True}]
        english=render_audio(sources,description,self.assets,language='en')
        chinese=render_audio(sources,description,self.assets,language='zh-CN')
        extract=lambda page:json.loads(re.search(r'<script>const CONFIG=(.*?);</script>',page,re.S).group(1))
        en,zh=extract(english),extract(chinese)
        self.assertEqual(en['language'],'en')
        self.assertEqual(en['description'],description)
        self.assertEqual(en['description_language'],'zh-CN')
        for key in ['sources','layers','audio','category_levels','duration','provenance']:
            self.assertEqual(en[key],zh[key],key)
        self.assertEqual(en['category_labels']['trees'],'Leaves')
        markup=english.split('<script>const CONFIG=')[0]
        for expected in ['lang="en"','id="landscape-player"','Play soundscape',
                         'Stop all audio','Narration voice','Read original guide',
                         'Original guide and audio sources','Playback status and engineering checks']:
            self.assertIn(expected,markup)
        self.assertIn(description,markup)
        self.assertNotIn('>朗读景观描述<',markup)
        self.assertEqual(en['profiles']['natural']['label'],'Recorded audio: continuous texture')

    def test_player_default_locale_uses_the_current_session_language(self):
        previous=get_language()
        try:
            set_language('en')
            rendered=render_audio([], '原始导览', self.assets)
            self.assertIn('<html lang="en">',rendered)
        finally:
            set_language(previous)

    def test_original_content_language_is_independent_of_interface_language(self):
        for language,text,expected in [('en','中文原文','zh-CN'),('zh-CN','English original','en'),('en','123…','und')]:
            with self.subTest(language=language,text=text):
                rendered=render_audio([],text,self.assets,language=language)
                payload=json.loads(re.search(r'<script>const CONFIG=(.*?);</script>',rendered,re.S).group(1))
                self.assertEqual(payload['description'],text)
                self.assertEqual(payload['description_language'],expected)
                if language!=expected:
                    self.assertFalse(payload['narration']['available'])
                    self.assertIn('<button id="speak" disabled>',rendered)
                    self.assertIn('English guide still preparing' if language=='en' else '中文导览仍在准备中',rendered)

if __name__=='__main__':unittest.main()
