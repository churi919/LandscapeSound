"""Publish the actual local model runs and a source-backed listening comparison."""
import html
import json
from pathlib import Path
from local_config import ROOT


def main():
    raw=json.loads((ROOT/'assets'/'generated_raw'/'manifest.json').read_text(encoding='utf-8'))
    qa=json.loads((ROOT/'outputs'/'audio_model_qa'/'clap_summary.json').read_text(encoding='utf-8'))
    selected=json.loads((ROOT/'assets'/'generated'/'manifest.json').read_text(encoding='utf-8'))
    reference=json.loads((ROOT/'outputs'/'audio_model_comparison'/'assets'/'natural'/'manifest.json').read_text(encoding='utf-8'))
    scores={x['id']:x for x in qa['results']};esc=html.escape
    candidates=[x for x in raw['items'] if x['role']!='deployment_smoke']
    rows=[];audio=[]
    for item in candidates:
        s=scores.get(item['id'],{});score=s.get('target_mean_cosine');rank=s.get('target_rank')
        model=item['model'].replace('Stable Audio 3 ','')
        category='风叶' if item['category']=='trees' else '湖岸水声'
        rows.append(f'<tr><th>{esc(model)}</th><td>{category}</td><td>{item["seed"]}</td><td>{item["cfg"]:g}</td><td>{item["official_cli_wall_seconds"]:.2f}s</td><td>{score:.4f} / {rank}</td></tr>')
        audio.append(f'<div class="raw-item"><p>{esc(item["id"])} · {esc(model)} · {category}</p><audio controls preload="none" src="../assets/generated_raw/{Path(item["wav"]).name}"></audio></div>')
    dynamics=[]
    for group,name in [(selected,'AI生成'),(reference,'录音对照')]:
        for item in group['items']:
            d=item.get('dynamics') or {}
            dynamics.append(f'<tr><th>{name}</th><td>{"风叶" if item["category"]=="trees" else "水声"}</td><td>{item["integrated_lufs"]:.2f}</td><td>{item["true_peak_4x_dbtp"]:.2f}</td><td>{d.get("maximum_gain_reduction_db",0):.2f}</td><td>{d.get("p95_gain_reduction_db",0):.2f}</td></tr>')
    output='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stable Audio 3 本地生成试听与评估</title><style>
body{margin:0;background:#f5f4ee;color:#193e31;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:40px 22px 80px}h1{font-size:38px;line-height:1.3;letter-spacing:-.04em}h2{font-size:25px}.lead{font-size:22px}.panel{border:1px solid #d1ddce;background:#fffef8;border-radius:15px;padding:24px;margin:24px 0}a{color:#216a4d;text-underline-offset:4px}.links{display:flex;gap:12px;flex-wrap:wrap}.button{display:inline-block;padding:12px 19px;background:#225f47;color:#fff;border-radius:9px;text-decoration:none}.button.secondary{background:#e8eee5;color:#204b37}.note{font-size:14px;color:#5a6b5f}table{width:100%;font-size:14px;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #d4ded0}.table-wrap{overflow:auto}details{margin:22px 0}summary{cursor:pointer;min-height:36px}.raw-item{padding:10px 0;border-bottom:1px solid #e0e4d9}audio{width:100%;max-width:600px}a:focus-visible,summary:focus-visible{outline:3px solid #2783b0;outline-offset:3px}footer{margin-top:35px;border-top:1px solid #ccd8c7;padding-top:18px;font-size:14px}@media(max-width:650px){h1{font-size:29px}.panel{padding:16px}}</style>
<main><p class="note">LANDSCAPESOUND / MODEL-GENERATED AUDIO / 2026-10-25</p><h1>Stable Audio 3 已在本机生成，<br>现在可以直接听模型与录音对照。</h1><p class="lead">已部署 Small-SFX 与更大的 Medium，实际生成8段30秒正式候选。当前应用采用 Medium 风叶和湖岸水声素材，由原有图像／深度结果控制方位和相对远近。</p>
<section class="panel"><h2>先试听</h2><p>建议先单独比较水声，再听完整湖岸场景。在播放器的“声音版本”中切换 AI 与自然录音；匹配页保持相同素材起点和空间参数。</p><div class="links"><a class="button" href="../outputs/audio_model_comparison/water_only.html">只听湖岸水声</a><a class="button" href="../outputs/audio_model_comparison/medium_lakes.html">完整湖岸对照</a><a class="button secondary" href="../outputs/audio_model_comparison/wind_only.html">只听风叶</a><a class="button secondary" href="http://127.0.0.1:8501">打开应用</a></div><p class="note">本轮是模型预生成、后处理并缓存的素材。日常播放无需重新运行模型；当前其他照片也使用这套缓存素材，由图像控制空间混音。</p></section>
<h2>这轮试出了什么</h2><p><b>水声：</b>在显式文本集合的 CLAP 检查中，Medium 的“湖岸微浪”目标相似度为0.4647、排名第1；Small最佳候选为0.1532、第2，录音参照为0.3097、第2。本轮 Medium 水声在内容匹配上更明确。</p><p><b>风叶：</b>Medium为0.3362、第7；Small最佳为0.3347、第7，录音参照为0.3460、第3。没有出现同样明确的收益，仍与宽带自然噪声标签混淆。</p><p class="note">CLAP cosine 是这组文本下的相似度，不是声音事件概率或主观音质分数。录音也存在类别混淆；结果不能证明AI更自然、没有鸟／人声，或对视障用户更有效。</p>
<section class="panel"><h2>本机真实运行</h2><p>Windows原生 LiteRT/TFLite + XNNPACK，i9-14900HX CPU，8线程，模型w8a8、8步。主应用的PyTorch环境保持独立。Medium生成30秒音频约16–17秒，峰值进程树内存约2GiB；Small约5–8秒。记录不包含初次模型下载，不是其他机器的速度保证。</p><div class="table-wrap"><table><tr><th>模型</th><th>类型</th><th>种子</th><th>CFG</th><th>CLI时间</th><th>目标cosine / 排名</th></tr>__ROWS__</table></div><p class="note">原始输出均为30秒、44.1kHz立体声、非静音且无样本削波；另保留一段20秒安装烟测。</p></section>
<h2>怎样控制对照条件</h2><p>AI和录音对照都取30秒片段，转为单声道32kHz，经2秒循环交叉淡化得到28秒纹理。两者使用相同的后期动态曲线，并按风叶／水声分别匹配约−23 LUFS；完整片段响度差小于0.01 LU。方位、距离、低通、分类增益与播放起点规则相同。</p><p>Medium水声存在较大的瞬态。应用处理版对其峰值进行了收敛，最大增益衰减约12.55dB，P95约4.70dB；相同曲线对录音的改动程度并不相同。这是经过后期处理的应用对照，不能当作原始模型输出的优劣证明。</p>
<details><summary>查看处理电平与仅增益参照</summary><div class="table-wrap"><table><tr><th>来源</th><th>类型</th><th>最终LUFS</th><th>4×峰值dBTP估计</th><th>最大动态衰减dB</th><th>P95衰减dB</th></tr>__DYNAMICS__</table></div><p class="note">4×过采样是工程峰值估计，非认证真峰表。保留了没有动态压缩、仅共同增益匹配的参照：水声因瞬态需降低共同目标至约−31.24LUFS，试听会更轻。</p><a href="../outputs/audio_model_comparison/uncompressed_lakes.html">只做增益匹配的参照</a> · <a href="../outputs/audio_model_comparison/small_lakes.html">Small-SFX与录音对照</a></details>
<details><summary>保留的原始生成候选</summary><p class="note">以下是未做响度匹配的模型原始立体声输出，音量不同且部分较轻，适合核对原始结果，不能直接用大小声判断质量。</p>__AUDIO__</details>
<section class="panel"><h2>可复查记录</h2><ul><li><a href="../assets/generated_raw/manifest.json">全部提示词、种子、模型、CFG、时长与WAV校验</a></li><li><a href="../assets/generated/manifest.json">当前接入素材与后期处理记录</a></li><li><a href="../outputs/audio_model_run/deployment_verification.json">真实模型运行验真</a></li><li><a href="../outputs/audio_model_qa/clap_summary.json">原始候选的内容匹配摘要</a></li><li><a href="../outputs/audio_model_comparison/player_verification.json">播放器来源与同参数检查</a></li><li><a href="../outputs/audio_model_comparison/browser_verification.json">真实浏览器播放与静音混音检查</a></li><li><a href="../outputs/audio_model_comparison/app_verification.json">普通照片与全景界面集成检查</a></li><li><a href="../outputs/audio_model_comparison/final_numeric_verification.json">独立响度、峰值、文件与报告核验</a></li><li><a href="../outputs/audio_model_comparison/test_results.log">自动检查记录</a></li></ul><p class="note">等响度协议只适用于本页链接的专用对照。主应用仍保留原58秒自然录音，切换时不保证匹配。完整素材的LUFS匹配也不保证每个20秒片段或空间混音输出完全等响。CLAP检查的是原始候选窗口，不是最终压缩处理版。</p></section>
<footer>代码与模型均来自官方固定revision，使用独立audio_model环境与D盘缓存。<a href="https://github.com/Stability-AI/stable-audio-3">Stable Audio 3官方代码</a> · <a href="https://huggingface.co/stabilityai/stable-audio-3-optimized">官方优化模型</a> · <a href="https://huggingface.co/laion/clap-htsat-unfused">CLAP模型</a>。生成音效和录音素材均用于景观模拟，并非照片现场实录；尚未进行耳机偏好或真实视障用户实验。</footer></main></html>'''
    output=output.replace('__ROWS__',''.join(rows)).replace('__DYNAMICS__',''.join(dynamics)).replace('__AUDIO__',''.join(audio))
    target=ROOT/'docs'/'model_audio_evaluation.html';target.write_text(output,encoding='utf-8');print(target)

if __name__=='__main__':main()
