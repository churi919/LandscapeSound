"""Report the panorama-specific generation runs without implying real-site audio."""
from pathlib import Path
import html
import json
from local_config import ROOT


def main():
    batch=json.loads((ROOT/'outputs'/'scene_audio_demo'/'batch_results.json').read_text(encoding='utf-8'))
    qa_path=ROOT/'outputs'/'scene_audio_qa'/'evaluation.json'
    qa=json.loads(qa_path.read_text(encoding='utf-8')) if qa_path.is_file() else None
    if qa and {x['scene_id']:x['cache_key'] for x in qa.get('scenes',[])} != {x['id']:x['cache_key'] for x in batch}:
        qa = None
    esc=html.escape;cards=[]
    recommended={'lakes':'back','autumn_forest_01':'front','suburban_garden':'back'}
    notes={
        'lakes':'开阔水面与岸边植被：分别生成湖岸轻微拍水、开阔岸边叶片纹理，再按各方向的画面安排声音。',
        'autumn_forest_01':'树干、林冠与落叶地面：生成较细碎的秋林叶片声。干叶、林下等细节来自本次人工看图核对；轻风属于模拟设定。',
        'suburban_garden':'草地、庭院树木和灌木：生成低强度庭院叶丛纹理。可见静止泳池被分割模型漏识别，本次不擅自添加泵或流水声。'}
    for record in batch:
        sid=record['id'];folder=ROOT/'outputs'/'scene_audio_demo'/sid
        plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
        manifest=json.loads(Path(record['manifest_path']).read_text(encoding='utf-8'))
        if manifest.get('cache_key') != plan['cache_key'] or plan['cache_key'] != record['cache_key']:
            raise ValueError('Scene plan and generated batch must match before publishing')
        stems=[];rows=[]
        for item in manifest['items']:
            category=item['category'];label='风叶' if category=='trees' else '湖岸水声'
            wav=Path(item['file']).relative_to(ROOT).as_posix()
            raw=Path(item['original_stereo_path']).relative_to(ROOT).as_posix()
            g=item['generation'];d=item.get('dynamics') or {}
            stems.append('<div class="stem"><b>'+label+' · 本图生成处理版</b><audio controls preload="none" src="../'+esc(wav)+'"></audio><details><summary>提示词、原始音频和处理记录</summary><p class="prompt">'+esc(g['prompt'])+'</p><p>种子 '+str(g['seed'])+' · 原始30秒立体声 · 处理后28秒单声道</p><audio controls preload="none" src="../'+esc(raw)+'"></audio><p class="note">原始音量未匹配；不要用大小声判断质量。最大动态衰减 '+f'{d.get("maximum_gain_reduction_db",0):.2f}'+' dB；P95 '+f'{d.get("p95_gain_reduction_db",0):.2f}'+' dB。</p></details></div>')
            seconds=g.get('official_cli_wall_seconds',g.get('wall_seconds_including_process_start'))
            rows.append('<tr><td>'+label+'</td><td>'+str(round(seconds,2))+'秒</td><td>'+f'{item["integrated_lufs"]:.2f}'+'</td><td>'+f'{item["true_peak_4x_dbtp"]:.2f}'+'</td><td><code>'+item['sha256'][:12]+'</code></td></tr>')
        recommended_view=recommended.get(sid,'front')
        viewlinks=' · '.join('<a href="../outputs/scene_audio_demo/'+sid+'/'+vid+'.html">'+label+'</a>' for vid,label in [('front','前'),('right','右'),('back','后'),('left','左')] if vid in record['view_pages'])
        cards.append('<section class="panel"><h2>'+esc(record['title'])+'</h2><img class="panorama" src="../outputs/panorama/'+sid+'/panorama.jpg" alt="'+esc(record['title'])+'全景"><p>'+notes.get(sid,'根据画面可见内容编写声音提示词。')+'</p><p><a class="button" href="../outputs/scene_audio_demo/'+sid+'/'+recommended_view+'.html">打开本图空间声景</a> <span>'+viewlinks+'</span></p>'+''.join(stems)+'<div class="table-wrap"><table><tr><th>类型</th><th>本机CLI生成</th><th>最终LUFS</th><th>4×峰值dBTP估计</th><th>处理文件指纹</th></tr>'+''.join(rows)+'</table></div><p class="note">图片指纹 '+esc(plan['image_sha256_rgb'][:16])+' · 本图缓存 '+esc(plan['cache_key'][:16])+' · <a href="../outputs/scene_audio_demo/'+sid+'/plan.json">完整画面依据与声音计划</a></p></section>')
    qa_text='<p>音频独立性、实际响度、峰值与内容匹配记录正在检查。</p>'
    if qa is not None:
        labels={'tree_leaves_light_breeze':'轻风叶声','small_lake_ripples':'湖岸微浪','birds':'鸟鸣','waterfall':'瀑布',
            'rain':'雨声','insects':'虫声','isolated_water_drops':'滴水','running_stream':'溪流',
            'strong_water_splashes':'明显溅水','breaking_ocean_surf':'海浪','strong_wind':'强风',
            'mechanical_hiss':'机械嘶声','gentle_outdoor_wind':'轻风','human_speech':'人声','music':'音乐','abrupt_impacts':'撞击'}
        names={r['id']:r['title'] for r in batch}; qrows=[]
        for entry in qa.get('clap',{}).get('files',[]):
            if entry.get('kind') != 'scene_generated_processed':continue
            sid=next((x for x in names if entry['id']==x+'_'+entry['category']),None)
            if sid is None:continue
            label='叶片' if entry['category']=='trees' else '水声'
            near='、'.join(labels.get(x,x) for x in entry['ranking'][1:3])
            qrows.append('<tr><td>'+esc(names[sid]+' · '+label)+'</td><td>'+f'{entry["target_mean_cosine"]:.4f}'+'</td><td>'+str(entry['target_rank'])+'</td><td>'+esc(near)+'</td></tr>')
        qa_text='<p>独立文件、图片绑定、时长、电平和无样本削波检查通过。下面是对处理版音频的16类文本内容匹配，目标排名不是音质分数。</p><div class="table-wrap"><table><tr><th>音轨</th><th>目标cosine</th><th>目标排名</th><th>随后两种接近标签</th></tr>'+''.join(qrows)+'</table></div><p>秋林和庭院叶声匹配目标类别。湖岸叶声首次更接近雨声／瀑布，简化为独立短促叶片声后，雨声相似度由0.5119降至0.0970；叶片目标排名由第3升至第1，但目标绝对相似度也由0.3183降至0.2942。这里只能说明这组标签中的分离改善，不能称音质评分提升。</p><p>新湖岸水声的目标相似度0.3869，未超过旧通用水声的0.3975。每图生成提供独立、可调的场景表达，不保证每条声音都更好。动态处理幅度仍较大，湖岸叶声最大衰减14.81dB、P95为5.34dB。</p><p class="note">相似度不是事件概率，不能据标签断定出现鸟／虫／雨或保证其不存在。不同文件与音频表征也不证明人耳能准确区分秋林和庭院。本轮尚未进行主观听辨。</p><p><a href="../outputs/scene_audio_qa/evaluation.json">完整核验与内容匹配</a> · <a href="../outputs/scene_audio_qa/retry_comparison.json">湖岸叶声两次尝试</a> · <a href="../outputs/scene_audio_demo/attempts/initial/lakes_result.json">保留的初次生成记录</a> · <a href="../outputs/scene_audio_demo/app_verification.json">12个方向界面与未缓存图片检查</a></p>'
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>每张全景独立生成声音 · 三图demo</title><style>body{margin:0;background:#f5f4ee;color:#193e31;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:36px 20px 70px}h1{font-size:36px;line-height:1.35;letter-spacing:-.025em}h2{font-size:26px}a{color:#216b4d;text-underline-offset:4px}.panel{border:1px solid #d0dccb;background:#fffef8;border-radius:14px;padding:24px;margin:28px 0}.lead{font-size:21px}.note{font-size:14px;color:#566b5b}.panorama{width:100%;max-height:350px;object-fit:contain;background:#e5e8df;border-radius:9px}.button{display:inline-block;background:#225f47;color:white;text-decoration:none;border-radius:8px;padding:10px 18px;margin:0 12px 8px 0}.stem{border-top:1px solid #d7dfd1;padding:16px 0}audio{display:block;width:100%;max-width:640px;margin:12px 0}summary{cursor:pointer;font-size:14px;min-height:36px}.prompt{font-size:14px;white-space:pre-wrap}.table-wrap{overflow:auto}table{font-size:14px;width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-bottom:1px solid #d6dfd1}a:focus-visible,summary:focus-visible{outline:3px solid #287baa;outline-offset:3px}@media(max-width:650px){h1{font-size:28px}.panel{padding:16px}}</style><main><p class="note">LANDSCAPESOUND / SCENE-CONDITIONED AUDIO / 2026-10-25</p><h1>每张全景用自己的提示词，<br>生成自己的声音。</h1><p class="lead">湖岸、秋林、庭院已分别运行 Stable Audio 3 Medium。下方可直接听本图生成的风叶／水声，也可打开四个朝向的空间混音。</p><p><a href="http://127.0.0.1:8501">打开应用 → 360° 全景测试</a></p><section class="panel"><h2>现在怎样生成</h2><p>全景四视角的分割与声源结果 → 本图内容依据和声音设定 → 分类英文提示词 → 本地音频生成 → 保留原始音频、处理为循环素材 → 按所选视角安排左右和相对远近。</p><p>模型仍通过文字提示词生成音频，没有直接把图像像素送进音频模型。本次三张示例加入了明确记录的人工看图核对；新上传全景默认使用自动识别内容。相同图片与相同计划可复用本图缓存，不会套用其他图片的生成文件。</p><p class="note">同一全景四个朝向共用本图的分类音频，方向差别来自图像中的声源位置，并非每个朝向独立生成。风和水的动态强度属于模拟设定；静态图像不能恢复现场真实声景。当前只自动配置树木与水体。</p></section>__CARDS__<section class="panel"><h2>这轮能确认与仍待判断的效果</h2>__QA__<p>可以确认三张图使用不同内容提示词与独立生成文件，并且能在网页中按方向播放。音频进行了响度和峰值处理，不同图的处理强度可能不同。</p><p>是否更自然、是否准确表达了秋林和庭院的区别，以及是否帮助视障用户理解空间，仍需要耳机听辨和用户实验。图像识别漏项也会传递到声音计划，庭院泳池就是本轮暴露的例子。</p><p class="note">每个处理片段为28秒；播放器通常播放20秒，短片段和空间混音后的响度不保证完全相同。自然录音／程序选项属于通用对照，未按本轮生成素材匹配响度。</p><p><a href="../outputs/scene_audio_demo/batch_results.json">批次运行记录</a> · <a href="../outputs/scene_audio_demo/ui_verification.json">界面与播放检查</a></p></section></main></html>'''
    target=ROOT/'docs'/'scene_audio_evaluation.html'
    target.write_text(doc.replace('__CARDS__',''.join(cards)).replace('__QA__',qa_text),encoding='utf-8')
    print(target)


if __name__=='__main__':main()
