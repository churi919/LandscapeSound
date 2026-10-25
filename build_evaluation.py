"""Create an inspectable local evaluation with the actual demo artifacts."""
import html
import json
from pathlib import Path
from local_config import ROOT

OBSERVATIONS = {
    '01_park': ('基础场景可用', '草地、树木与天空分区清楚；深度图呈现近草地、远树林。',
                '中央主树与背景树群被同一扇区聚合，三个树源均偏远，主树的独立层次不足。'),
    '02_marina': ('细杆与围栏有误差', '水、天空和码头大体分开，深度图捕捉到前景围栏。',
                  '帆杆等细物体分割较粗；水面被压成三个深度相近的点源，不能重建连续水域。'),
    '03_mangrove': ('明显失败案例', '深度图能显示前景枝条、远处通道和近处船头的部分层次。',
                    '倒影水面大片错分为植被：模型水体仅约2.4%、植被约96.7%。语义错误直接传递为过多树声、过少水声。'),
    '04_lake': ('最适合演示', '开阔水面、天空和远岸树群的分区清楚；近水远岸关系视觉合理。',
                '最多四源按面积截断后，三个水源占位，仅保留右侧树源，左岸和中央树群声源被省略。'),
    '05_courtyard': ('低照度仍有层次', '近处铺地与远处植物具有可见深度层次；顶盖被识别为ceiling。',
                     '暗部和细小物体边界不精确。已修复人工界面统计漏算顶盖的代码问题；仍不能据此断言主观庇护感。'),
}

def main():
    reports=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'outputs'/'demo').glob('*/report.json'))]
    initial=json.loads((ROOT/'outputs'/'initial_benchmark.json').read_text(encoding='utf-8'))
    gpt_path=ROOT/'outputs'/'gpt_captions.json'
    gpt=json.loads(gpt_path.read_text(encoding='utf-8')) if gpt_path.is_file() else {}
    gpt_items={item['analysis_rgb_sha256']:item for item in gpt.get('items',[])}
    hot=[x['metrics']['inference_seconds'] for x in initial[1:]]
    wall=[x['metrics']['total_seconds'] for x in initial[1:]]
    esc=html.escape
    rows=[]; cards=[]
    for r in reports:
        slug=Path(r['report_path']).parent.name
        verdict,good,weak=OBSERVATIONS[slug]
        scene=r['scene'];m=r['metrics'];f=scene['fractions']
        gpt_item=gpt_items.get(r.get('input',{}).get('sha256_rgb'))
        gpt_block=''
        gpt_link=''
        if gpt_item:
            gpt_block='<details open><summary>GPT辅助景观描述（已按照片核对）</summary><blockquote>'+esc(gpt_item['description'])+'</blockquote><p class="note">来源：网页版ChatGPT；只补充文字，不修改本地分割与声源参数。'+esc(gpt_item.get('review_note',''))+'</p></details>'
            gpt_link=f' · <a href="../outputs/demo/{slug}/listen_gpt.html">GPT描述试听</a>'
        rows.append(f'<tr><th scope="row">{esc(r["title"])}</th><td>{m["inference_seconds"]:.3f}s</td><td>{len(scene["sources"])}</td><td>{f["vegetation"]:.1%} / {f["water"]:.1%}</td><td>{verdict}</td></tr>')
        images=''.join(f'<figure><img src="../outputs/demo/{slug}/{key}.png" alt="{esc(r["title"])}：{label}" loading="lazy"><figcaption>{label}</figcaption></figure>' for key,label in [('input','原照片'),('segmentation','语义分割叠加'),('depth','相对近度，黄近蓝远，灰色为天空')])
        source_rows=''.join(f'<tr><td>{esc(s["label"])}</td><td>{s["azimuth"]:.1f}°</td><td>{s["near_score"]:.3f}</td><td>{s["virtual_radius"]:.2f}</td></tr>' for s in scene['sources'] if s['near_score'] is not None)
        cards.append(f'''<article><div class="section-title"><h2>{esc(r['title'])}</h2><span class="tag">{verdict}</span></div>
<div class="images">{images}</div><p><b>观察：</b>{good}</p><p><b>局限：</b>{weak}</p>{gpt_block}
<details><summary>查看声源参数和景观描述</summary><table><thead><tr><th>区域声源</th><th>方位</th><th>同图相对近度</th><th>虚拟音频距离</th></tr></thead><tbody>{source_rows}</tbody></table><blockquote>{esc(scene['description'])}</blockquote></details>
<p class="links"><a href="../outputs/demo/{slug}/listen.html">规则描述试听</a>{gpt_link} · <a href="../outputs/demo/{slug}/report.json">查看本地分析 JSON</a></p></article>''')
    output='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LandscapeSound 本地部署与效果评估</title>
<style>body{margin:0;background:#f5f4ee;color:#193b30;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1120px;margin:auto;padding:45px 24px 80px}h1{font-size:38px;line-height:1.25;letter-spacing:-.04em;margin:8px 0 20px}h2{font-size:25px;margin:8px 0}h3{font-size:20px}a{color:#166a4c;text-underline-offset:4px}p{max-width:980px}.eyebrow{font-size:13px;letter-spacing:.15em}.lead{font-size:22px;line-height:1.6;max-width:950px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:28px 0}.metric,article,.panel{background:#fffef8;border:1px solid #d7dfd5;border-radius:16px;padding:24px}.metric strong{font-size:32px;display:block}.metric small{color:#57685e}article{margin:24px 0}.section-title{display:flex;justify-content:space-between;align-items:center;gap:15px}.tag{font-size:13px;background:#e8eee5;border-radius:20px;padding:5px 13px}.images{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}figure{margin:0}img{display:block;width:100%;height:300px;object-fit:contain;background:#eeeee6;border-radius:8px}figcaption{font-size:13px;margin-top:7px;color:#55675d}table{border-collapse:collapse;width:100%;font-size:15px;margin:20px 0}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #d8ded6}th{font-weight:650}blockquote{border-left:3px solid #759c84;padding:8px 20px;margin:20px 0;color:#355c47}details{padding:10px 0}summary{cursor:pointer}footer{font-size:14px;border-top:1px solid #cbd5c9;padding-top:20px;margin-top:40px}.links{font-size:15px}.note{color:#5f6b62;font-size:14px}.scroll{overflow-x:auto}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #287fbc;outline-offset:3px}@media(max-width:720px){.metrics,.images{grid-template-columns:1fr}h1{font-size:30px}img{height:auto;max-height:400px}.section-title{display:block}}</style>
<main><aside class="panel"><b>音频已接入 Stable Audio 3 Medium</b>：已在本机生成并测试Small-SFX与Medium，保留AI、自然录音和原程序素材可切换。<a href="model_audio_evaluation.html">打开本轮等响度对照与评估</a>。下面的图像识别评价仍然适用；早期音频检查对应原版。</aside><p class="eyebrow">LANDSCAPESOUND / LOCAL RESEARCH PROTOTYPE / 2026-10-25</p><h1>本地链路已经成立，<br>体验目标仍需验证。</h1>
<p class="lead">已在这台 RTX 4060 笔记本上完成部署，用五张本地真实照片跑通“景观分割 → 相对深度 → 空间音频 → 中文描述”。硬件性能足够；复杂倒影、区域聚合和音效自然度是目前的主要缺口。</p>
<p><a href="http://127.0.0.1:8501">打开 LandscapeSound 应用 →</a></p>
<div class="metrics"><div class="metric"><strong>5 张</strong><small>真实照片端到端完成，并保留图层及JSON</small></div><div class="metric"><strong>__HOT__ 秒</strong><small>初次批跑后四图的热推理：分割+深度</small></div><div class="metric"><strong>386 MB</strong><small>本进程GPU分配峰值，非全部系统显存</small></div></div>
<section class="panel"><h2>是否达到了原先设想</h2><p><b>已达到：</b>在本机完成照片分析；用同图相对深度控制虚拟音频距离、衰减和低通；用画面位置控制HRTF左右方位；提供中文规则描述、人工校正、普通混音对照和JSON导出。</p>
<p><b>尚未达到：</b>可靠还原所有场景的空间结构、自然真实的景观声景，以及已经证明能帮助盲人或低视力用户理解景观。已安装并实际测试Stable Audio 3 Small-SFX与Medium，默认采用Medium预生成缓存素材。未进行目标用户试验，也没有主观耳机听感评分。</p></section>
<h2 style="margin-top:40px">五图实跑结果</h2><p class="note">植被/水体为模型预测的画面像素比例，不能当作准确率、真实覆盖率或主观PSD评分。图片缩放至长边≤768像素；水平视野假定70°。</p>
<div class="scroll"><table><thead><tr><th>场景</th><th>本次推理</th><th>声源</th><th>植被 / 水体</th><th>视觉判断</th></tr></thead><tbody>__ROWS__</tbody></table></div>
__CARDS__
<section class="panel"><h2>实际验证了什么</h2><ul><li>PyTorch CUDA可用，五图在RTX 4060 Laptop 8188MiB上完成；另用离线模式真实分析一图，模型无需云端推理。</li>
<li>首次批跑后四图全流程耗时__WALL__秒；首次下载/加载与GPU首次初始化另计，初次五图数据保存在initial_benchmark.json。</li>
<li>首轮原版Chrome静音OfflineAudioContext检查6/6通过：左源L/R RMS 3.44、右源R/L RMS 3.48；较近/较远RMS 4.24；远/近高频代理量0.097。证实浏览器生成了预期信号差异。</li>
<li>应用按钮重跑成功；播放显示三个声源运行，停止按钮和朗读回调正常。检测到三个本机中文语音。没有据此声称实际耳机听辨有效。</li>
<li>核心测试__TESTS__项通过；界面测试确认切换demo、改为42°、修改描述后导出JSON包含对应校正。</li></ul>
<p class="links"><a href="../outputs/browser_audio_verification.json">音频实测记录</a> · <a href="../audio_validation.html">在本浏览器重新自检</a> · <a href="../outputs/diagnostics.json">本机诊断</a> · <a href="../outputs/initial_benchmark.json">初次性能记录</a></p></section>
<h2 style="margin-top:40px">下一轮应优先改进</h2><ol><li><b>先修倒影水面的语义错误。</b>为水面、反射、细枝条场景增加人工标注对照，比较更强分割或可校正掩膜；无标注前不公布“准确率”。</li>
<li><b>按区域与深度共同拆分声源。</b>同类树木需要区分前景与背景；有限的声源名额应覆盖主要类别，避免水声把远岸树源全部挤掉。</li>
<li><b>比较声音素材与景观表达。</b>已保留生成式AI与授权自然录音的等响度对照，下一步进行耳机听辨和偏好评价。描述已补入可审计的画面布局规则，但仍不能代替完整场景理解。</li>
<li><b>验证视障用户是否能用。</b>比较普通混音与深度声景，测左右/近远判断、空间概念理解、认知负担和偏好。工程通过不等于体验有效。</li></ol>
<footer>部署：i9-14900HX / 约32GB RAM / RTX 4060 Laptop 8GB；Python3.11.15 / torch2.8.0+cu128 / transformers4.44.2 / Streamlit1.50.0。模型、环境及缓存位于D盘。照片为电脑现有文件的缩小副本，未改动原件。本地视觉分析和音频运行无需上传；本次依用户追加授权，将五张无EXIF的示例副本提交网页版ChatGPT，补充文字后缓存到本地。<br>
来源：原讨论附件 LandscapeSound_V2_Windows_Guide.md；<a href="https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512">SegFormer B0</a>（研究/评估的非商业条件）、<a href="https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf">Depth Anything V2 Small</a>（Apache2.0）、<a href="https://developer.mozilla.org/en-US/docs/Web/API/PannerNode">Web Audio HRTF</a>。声音可选Stable Audio 3 AI生成缓存、自然录音与原程序素材，均为示意；虚拟距离不是米；本原型用于景观预体验。</footer></main></html>'''
    collected=__import__('subprocess').run([str(ROOT/'.venv'/'Scripts'/'python.exe'),'-m','pytest','--collect-only','-q'],cwd=ROOT,capture_output=True,text=True)
    count=sum(1 for line in collected.stdout.splitlines() if line.startswith('tests/') and '::' in line)
    output=output.replace('__HOT__',f'{min(hot):.2f}–{max(hot):.2f}').replace('__WALL__',f'{min(wall):.2f}–{max(wall):.2f}').replace('__ROWS__',''.join(rows)).replace('__CARDS__',''.join(cards)).replace('__TESTS__',str(count))
    if gpt_items:
        section='<section class="panel"><h2>网页版 GPT 的补充作用</h2><p>五张示例已使用网页版ChatGPT补充更自然的景观布局文字，逐图核对后按分析图片指纹缓存。应用可切换本地规则与GPT辅助描述，日常试听无需再次联网。新上传的不同图片不会自动套用这些缓存。</p><p>红树林的文字可以指出水面与倒影，但它没有修正语义分割掩膜，因此树声/水声配置的错误仍然存在。GPT增强了表达，未替代模型准确性或目标用户体验验证。</p><p><a href="'+esc(gpt.get('conversation_url','https://chatgpt.com/'))+'">查看生成原对话</a> · <a href="../outputs/gpt_captions.json">来源、逐图依据与审阅记录</a></p></section>'
        output=output.replace('<h2 style="margin-top:40px">下一轮应优先改进</h2>',section+'<h2 style="margin-top:40px">下一轮应优先改进</h2>')
    target=ROOT/'docs'/'evaluation.html';target.write_text(output,encoding='utf-8');print(target)

if __name__=='__main__':main()
