"""Generate real, independent panorama audio and build inspectable listening pages."""
from pathlib import Path
import argparse
import html
import json
import time
from local_config import ROOT
from scene_audio_plan import build_panorama_audio_plan, load_demo_observations
from scene_audio_runtime import ensure_scene_audio
from browser_audio import render_audio


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', nargs='+', default=['lakes', 'autumn_forest_01', 'suburban_garden'])
    args = parser.parse_args()
    batch_path = ROOT/'outputs'/'scene_audio_demo'/'batch_results.json'
    results = json.loads(batch_path.read_text(encoding='utf-8')) if batch_path.is_file() else []
    for scene_id in args.ids:
        report = json.loads((ROOT/'outputs'/'panorama'/scene_id/'report.json').read_text(encoding='utf-8'))
        plan = build_panorama_audio_plan(report, load_demo_observations(report))
        folder = ROOT/'outputs'/'scene_audio_demo'/scene_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        print('START '+scene_id+' '+plan['cache_key'][:12], flush=True)
        start = time.perf_counter()
        result = ensure_scene_audio(plan, root=ROOT)
        result['wall_seconds_including_postprocessing'] = time.perf_counter()-start
        (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        pages = []
        for view in report['views']:
            view_id = view['id']; scene = view['report']['scene']
            sources = plan['views'][view_id]['sources']
            if result.get('assets_dir') and sources:
                player = render_audio(sources, scene.get('description', ''), result['assets_dir'], 20)
                (folder/(view_id+'_player.html')).write_text(player, encoding='utf-8')
                relative_image = Path(view['report']['files']['input']).relative_to(ROOT).as_posix()
                title = html.escape(plan['scene_title']+' · '+view.get('label', view_id))
                nav = ' · '.join('<a href="'+html.escape(v['id'])+'.html">'+html.escape(v.get('label',v['id']))+'</a>' for v in report['views'])
                page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__ · 本图专属声音</title><style>body{margin:0;background:#f5f4ee;color:#193e31;font:16px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1100px;margin:auto;padding:28px 18px}h1{font-size:28px;line-height:1.4}a{color:#246447}img{display:block;max-height:400px;max-width:100%;margin:20px auto;border-radius:12px}iframe{width:100%;height:850px;border:1px solid #cddcc9;border-radius:12px;background:#f5f7f1}.note{color:#516753;font-size:14px}</style><main><a href="../../../docs/scene_audio_evaluation.html">← 三张全景的生成试听与评估</a><h1>__TITLE__</h1><p>__NAV__</p><img src="../../../__IMAGE__" alt="当前透视视角"><p>本图独立生成的分类素材，结合当前朝向的方位与相对深度混音。风与水运动采用模拟设定；不是现场录音。</p><p class="note">四个朝向共用本图素材，不与其他全景复用。同播放器内的自然录音与原程序选项属于通用对照，未做等响度实验。</p><iframe src="__PLAYER__" title="__TITLE__ 专属声音播放器" allow="autoplay"></iframe></main></html>'''
                page = page.replace('__TITLE__', title).replace('__NAV__', nav).replace('__IMAGE__', html.escape(relative_image)).replace('__PLAYER__',view_id+'_player.html')
                (folder/(view_id+'.html')).write_text(page, encoding='utf-8')
                pages.append(view_id)
        entry = {'id':scene_id, 'title':plan['scene_title'], 'cache_key':plan['cache_key'],
            'image_sha256_rgb':plan['image_sha256_rgb'], 'generated':result['generated'],
            'reused':result['reused'], 'assets_dir':result['assets_dir'],
            'manifest_path':result['manifest_path'], 'stems':len(result['stems']), 'view_pages':pages,
            'wall_seconds_including_postprocessing':result['wall_seconds_including_postprocessing']}
        previous_index = next((i for i, value in enumerate(results) if value['id'] == scene_id), None)
        if previous_index is None:
            results.append(entry)
        else:
            results[previous_index] = entry
        print('DONE '+scene_id+' '+str(round(result['wall_seconds_including_postprocessing'],2))+'s',flush=True)
        (ROOT/'outputs'/'scene_audio_demo'/'batch_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('All requested scene demos complete.', flush=True)


if __name__ == '__main__':
    main()
