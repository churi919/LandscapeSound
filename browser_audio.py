"""Public API for the current player and a reproducible legacy renderer."""
from pathlib import Path
from audio_player_v2 import render_audio
from browser_audio_legacy import render_audio as render_audio_legacy


def write_preview(path=None):
    root=Path(__file__).resolve().parent
    sources=[{'id':'tree-left','category':'trees','label':'左侧风叶（手动预览）','enabled':True,
              'azimuth':-30,'virtual_radius':2.7,'near_score':.85,'area_fraction':.3},
             {'id':'water-right','category':'water','label':'右侧水面（手动预览）','enabled':True,
              'azimuth':30,'virtual_radius':5.7,'near_score':.35,'area_fraction':.2},
             {'id':'bird-manual','category':'bird','label':'鸟鸣（人工示例，默认关闭）','enabled':False,
              'azimuth':0,'virtual_radius':4.8,'near_score':None,'area_fraction':.01}]
    target=Path(path) if path else root/'audio_component_preview.html'
    target.write_text(render_audio(sources,'手动预览：左前方为风叶，右前方为水声。声音和位置均为模拟设定。',root/'assets',20),encoding='utf-8')
    return target

if __name__=='__main__':print(write_preview())
