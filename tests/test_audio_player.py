import json
import re
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from audio_player_v2 import render_audio

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

if __name__=='__main__':unittest.main()
