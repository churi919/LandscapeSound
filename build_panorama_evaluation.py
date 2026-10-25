"""Source-backed local panorama comparison; no accuracy claims without labels."""
import html
import json
from pathlib import Path
from local_config import ROOT

NOTES={
 'lakes':('湖岸后方最适合展示', '四方向把道路、不同侧的水面和树林分开呈现。后方视图的大片水面、近岸与远岸层次在视觉上较清楚。',
          '同一片水被分为lake/water/sea/river等细类，细分类不稳定；统一归为水体后用于示意。少量前景斑块仍需核对。', 'back'),
 'autumn_forest_01':('林下结构可辨，局部要素遗漏', '右方与后方的近树干、远树群在相对深度图中有层次。',
                     '正前方的大岩石没有独立识别；树群扇区中位数会掩盖局部近树干，正前方三个树源近度仅约0.11–0.19。', 'right'),
 'suburban_garden':('庭院总体可辨，泳池明确漏检', '草地、建筑、树木的主要界面能够分开呈现。',
                    '右方画面最右侧和后方画面左侧可见蓝色池水，但四方向水体预测均为0。没有水声源于漏检，不能解释为场景中没有水。', 'back'),
}

def main():
    manifest=json.loads((ROOT/'samples'/'panoramas'/'manifest.json').read_text(encoding='utf-8'))
    records=json.loads((ROOT/'outputs'/'panorama'/'batch_results.json').read_text(encoding='utf-8'))
    by_id={Path(x['report_path']).parent.name:x for x in records};esc=html.escape
    cards=[];rows=[]
    for item in manifest:
        slug=item['id'];r=by_id[slug];verdict,good,weak,preferred=NOTES[slug]
        m=r['metrics'];author='、'.join(item['author'])
        rows.append(f'<tr><th>{esc(item["title"])}</th><td>{m["four_view_inference_seconds"]:.3f}s</td><td>{m["total_seconds"]:.2f}s</td><td>{m["peak_gpu_memory_mb"]:.0f}MB</td><td>{verdict}</td></tr>')
        nav=[];views=[]
        for v in r['views']:
            vid=v['id'];s=v['report']['scene'];files=v['report']['files'];base=f'../outputs/panorama/{slug}/views/{vid}'
            selected=vid==preferred
            nav.append(f'<button type="button" data-target="{slug}-{vid}" aria-pressed="{str(selected).lower()}">{v["label"]} {int(v["yaw"])}°</button>')
            imgs=''.join(f'<figure><img src="{base}/{key}.png" alt="{esc(item["title"])} {v["label"]} {label}" loading="lazy"><figcaption>{label}</figcaption></figure>' for key,label in [('input','透视画面'),('segmentation','语义分割叠加'),('depth','相对近度：黄近蓝远，灰色天空')])
            source_rows=''.join(f'<tr><td>{esc(x["label"])}</td><td>{x["azimuth"]:.1f}°</td><td>{x["near_score"]:.3f}</td></tr>' for x in s['sources'] if x['near_score'] is not None)
            hidden='' if selected else ' hidden'
            views.append(f'''<div class="view" id="{slug}-{vid}"{hidden}><div class="images">{imgs}</div><p class="note">该视角预测水体像素：{s['fractions']['water']:.1%} · 树/水区域声源：{len(s['sources'])}个</p><details><summary>查看声源与本地规则描述</summary><table><tr><th>声源</th><th>相对当前视角方位</th><th>本视角近度</th></tr>{source_rows}</table><blockquote>{esc(s['description'])}</blockquote></details><a href="{base}/listen.html">打开此方向双耳试听 →</a></div>''')
        cards.append(f'''<article><h2>{esc(item['title'])}</h2><p class="source"><a href="{item['source_url']}">{esc(item['source_title'])} / Poly Haven</a> · {esc(author)} · CC0</p><img class="panorama" src="../outputs/panorama/{slug}/panorama.jpg" alt="{esc(item['title'])}完整全景"><p><b>结果：</b>{good}</p><p><b>问题：</b>{weak}</p><div class="direction-nav" role="group" aria-label="{esc(item['title'])}切换视角">{''.join(nav)}</div>{''.join(views)}<details><summary>原版平铺输入与四视角总览</summary><p class="note">第一行是旧版将360°压进70°的输入；后四行是90°透视方向。这里比较几何与结果表现；投影和采样分辨率同时变化，不能据此计算准确率提升。</p><img class="overview" src="../outputs/panorama/{slug}/overview.jpg" alt="平铺基线与四方向三图对照"></details><p><a href="../outputs/panorama/{slug}/report.json">完整结果JSON</a></p></article>''')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LandscapeSound 全景实跑评估</title><style>
body{margin:0;background:#f5f4ee;color:#193e31;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1140px;margin:auto;padding:40px 22px 70px}h1{font-size:38px;line-height:1.3;letter-spacing:-.04em}h2{font-size:26px}a{color:#216c4e;text-underline-offset:4px}.lead{font-size:22px}.source,.note{font-size:14px;color:#5b6b60}.panel,article{background:#fffef9;border:1px solid #d3ddcf;border-radius:16px;padding:25px;margin:25px 0}.panorama{width:100%;display:block;border-radius:10px}.images{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}figure img{width:100%;display:block}figcaption{font-size:13px;color:#52675c;margin:5px 0 14px}.direction-nav{display:flex;gap:10px;flex-wrap:wrap;margin:25px 0 15px}button{font:inherit;padding:9px 18px;background:#fff;border:1px solid #91ac99;border-radius:8px;color:#193e31;cursor:pointer}button[aria-pressed=true]{background:#205e46;color:white}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #287fbc;outline-offset:3px}details{margin:15px 0}summary{cursor:pointer;min-height:35px}.overview{width:100%;max-width:1000px}table{width:100%;border-collapse:collapse;font-size:15px}td,th{text-align:left;padding:10px;border-bottom:1px solid #d9e0d5}blockquote{padding:12px 20px;border-left:3px solid #79a28b;margin:15px 0}.table-wrap{overflow:auto}footer{margin-top:35px;padding-top:20px;border-top:1px solid #ccd7c9;font-size:14px}@media(max-width:700px){.images{grid-template-columns:1fr}h1{font-size:29px}.panel,article{padding:16px}}
</style><main><aside class="panel"><b>音频已接入 Stable Audio 3 Medium</b>：本机已生成并测试Small-SFX与Medium，保留AI、自然录音和原程序素材可切换。<a href="model_audio_evaluation.html">打开本轮等响度对照与评估</a>。下面的图像识别评价仍然适用；早期音频检查对应原版。</aside><p class="note">LANDSCAPESOUND / 360° PANORAMA TEST / 2026-10-25</p><h1>全景适合分方向预体验，<br>需要先还原透视视角。</h1><p class="lead">已下载3张真实拍摄全景，完成12个方向视图及3张旧版平铺基线的本地GPU分析。原版把整圈360°压缩成约70°，现已加入前、右、后、左四方向预览与试听。</p><p><a href="http://127.0.0.1:8501">打开应用，选择“360° 全景测试” →</a></p>
<section class="panel"><h2>本轮结论</h2><p>湖岸后方的水面最适合展示；森林能看到部分近树干与远林层次。庭院的小面积泳池明确漏识别，证明换成全景并不能自动解决语义错误。</p><p>四向投影、接缝周期采样、视角内方位和应用切换已经跑通。当前声音以选中视角为正前方，各视角深度独立归一化；尚未实现一套统一距离尺度、连续转头的360°声场。天顶和脚下未分析。</p></section>
<h2>真实运行记录</h2><div class="table-wrap"><table><tr><th>全景</th><th>四视角模型推理合计</th><th>全流程含基线/导出</th><th>本进程显存峰值</th><th>视觉判断</th></tr>__ROWS__</table></div><p class="note">每视角512×512、90°，模型本地缓存；总耗时含投影、旧版基线、四视角推理和保存。第一例包含本进程首次模型加载与GPU初始化。没有像素标注或实测深度，因此不报告准确率或精度提升。</p>
__CARDS__
<section class="panel"><h2>验证与限制</h2><ul><li>32项核心及投影测试通过，包括±180°接缝、360°周期、俯仰及像素方位。接缝采样正确不等于跨视角语义或深度已拼接一致。</li><li>3场景×4方向，共12个界面组合通过；普通照片/GPT缓存描述仍可使用。全景新图使用本地规则描述，本轮未上传GPT。</li><li>方位采用透视射线atan计算。0°是全景图像中点，不代表地理北；虚拟距离只在当前视角内解释。</li><li>只有树与水有自动示意声源，岩石、草地、建筑等视觉要素不自动配声。声音现可切换自然录音纹理与原版程序素材，未做目标用户听辨实验。</li></ul><p><a href="../samples/panoramas/manifest.json">素材来源与校验清单</a> · <a href="../outputs/panorama/batch_results.json">全部运行结果</a> · <a href="../outputs/panorama_test_results.log">测试记录</a></p></section>
<p>下一步优先改善小面积水体/反射分割，并将树群按深度层拆分；需要统一全景距离时，应引入全景专用深度或跨视角对齐与一致性验证。</p><footer>Powered by Poly Haven。素材来自官方8K tonemapped JPG，校验后缩为4096×2048测试副本，无AI生成。<a href="https://polyhaven.com/license">Poly Haven CC0许可</a>。本轮仅是工程和视觉检查，不能证明视障用户的实际使用效果。</footer></main><script>
document.querySelectorAll('.direction-nav').forEach(nav=>{nav.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{const article=nav.closest('article');article.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==button.dataset.target);nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));});
</script></html>'''
    page=page.replace('__ROWS__',''.join(rows)).replace('__CARDS__',''.join(cards))
    path=ROOT/'docs'/'panorama_evaluation.html';path.write_text(page,encoding='utf-8');print(path)

if __name__=='__main__':main()
