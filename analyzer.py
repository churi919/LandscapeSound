"""Local SegFormer + Depth Anything V2 inference, with auditable artifacts."""
import local_config  # Must precede torch / huggingface imports.
import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn.functional as F
from transformers import (AutoImageProcessor, AutoModelForDepthEstimation,
                          SegformerImageProcessor, SegformerForSemanticSegmentation)
from engine import build_scene, normalize_depth, SEMANTIC_GROUPS

SEG_ID = 'nvidia/segformer-b0-finetuned-ade-512-512'
DEPTH_ID = 'depth-anything/Depth-Anything-V2-Small-hf'


@lru_cache(maxsize=1)
def load_models():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(min(8, torch.get_num_threads()))
    offline = __import__('os').environ.get('HF_HUB_OFFLINE') == '1'
    options = dict(local_files_only=offline)
    seg_processor = SegformerImageProcessor.from_pretrained(SEG_ID, **options)
    seg = SegformerForSemanticSegmentation.from_pretrained(SEG_ID, use_safetensors=True, **options).eval().to(device)
    depth_processor = AutoImageProcessor.from_pretrained(DEPTH_ID, **options)
    depth = AutoModelForDepthEstimation.from_pretrained(DEPTH_ID, use_safetensors=True, **options).eval().to(device)
    return device, seg_processor, seg, depth_processor, depth


def colorize_depth(near, sky_mask):
    # Blue (far) -> teal -> yellow (near), with sky explicitly unmeasured.
    anchors = np.array([[36, 61, 108], [38, 147, 150], [250, 219, 91]], dtype=float)
    x = np.clip(near, 0, 1) * 2
    lo = np.minimum(x.astype(int), 1)
    rgb = anchors[lo] * (1 - (x-lo)[..., None]) + anchors[lo+1] * (x-lo)[..., None]
    rgb[sky_mask] = [214, 220, 224]
    return Image.fromarray(rgb.astype(np.uint8))


def colorize_seg(image, segmentation, labels):
    palette = {i: ((i * 47 + 53) % 210 + 25, (i * 83 + 89) % 210 + 25,
                   (i * 131 + 29) % 210 + 25) for i in labels}
    preferred = {'tree': (51, 146, 84), 'palm': (51, 146, 84), 'grass': (151, 192, 90),
                 'water': (39, 157, 215), 'river': (39, 157, 215), 'sea': (39, 157, 215),
                 'sky': (174, 199, 226), 'building': (204, 125, 83), 'road': (166, 150, 145)}
    for name in SEMANTIC_GROUPS['built']:
        preferred[name] = (204, 125, 83)
    for name in SEMANTIC_GROUPS['water']:
        preferred[name] = (39, 157, 215)
    for name in SEMANTIC_GROUPS['vegetation']:
        preferred.setdefault(name, (151, 192, 90))
    rgb = np.zeros((*segmentation.shape, 3), dtype=np.uint8)
    for i in np.unique(segmentation):
        name = labels.get(int(i), str(i)).split(',')[0].strip()
        rgb[segmentation == i] = preferred.get(name, palette.get(int(i), (120, 120, 120)))
    return Image.blend(image, Image.fromarray(rgb), .53)


def analyze_image(image: Image.Image, output_dir: Path, title='景观照片', hfov=70.0):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    image = ImageOps.exif_transpose(image).convert('RGB')
    original_size = list(image.size)
    image.thumbnail((768, 768), Image.Resampling.LANCZOS)
    w, h = image.size
    load_start = time.perf_counter()
    device, sp, sm, dp, dm = load_models()
    load_seconds = time.perf_counter() - load_start
    if device == 'cuda':
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    infer_start = time.perf_counter()
    with torch.inference_mode():
        inputs = {k:v.to(device) for k,v in sp(images=image, return_tensors='pt').items()}
        outputs = sm(**inputs)
        seg = sp.post_process_semantic_segmentation(outputs, target_sizes=[(h,w)])[0].cpu().numpy()
        if device == 'cuda': torch.cuda.synchronize()
        seg_end = time.perf_counter()
        inputs = {k:v.to(device) for k,v in dp(images=image, return_tensors='pt').items()}
        outputs = dm(**inputs)
        inverse = F.interpolate(outputs.predicted_depth.unsqueeze(1), size=(h,w),
                                mode='bicubic', align_corners=False)[0,0].float().cpu().numpy()
    if device == 'cuda': torch.cuda.synchronize()
    infer_end = time.perf_counter()
    labels = {int(k):v for k,v in sm.config.id2label.items()}
    scene = build_scene(seg, inverse, labels, hfov=float(hfov), title=title)
    sky_ids = [i for i, name in labels.items() if name.split(',')[0].strip() == 'sky']
    sky = np.isin(seg, sky_ids)
    near = normalize_depth(inverse, sky)
    files = {name:str(output_dir / (name+'.png')) for name in ('input','segmentation','depth')}
    image.save(files['input'])
    colorize_seg(image, seg, labels).save(files['segmentation'])
    colorize_depth(near, sky).save(files['depth'])
    np.savez_compressed(output_dir/'raw_predictions.npz', segmentation=seg, inverse_depth=inverse, near_score=near)
    metrics = {
        'device': device, 'gpu': torch.cuda.get_device_name(0) if device=='cuda' else None,
        'model_load_seconds': round(load_seconds,3), 'segmentation_seconds': round(seg_end-infer_start,3),
        'depth_seconds': round(infer_end-seg_end,3), 'inference_seconds': round(infer_end-infer_start,3),
        'total_seconds': round(time.perf_counter()-started,3),
        'peak_gpu_memory_mb': round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0,
        'peak_gpu_reserved_mb': round(torch.cuda.max_memory_reserved()/1024**2,1) if device=='cuda' else 0,
    }
    revisions = {'segformer':getattr(sm.config, '_commit_hash', None),
                 'depth_anything':getattr(dm.config, '_commit_hash', None)}
    report = {'schema_version':1, 'title':title, 'scene':scene, 'metrics':metrics, 'files':files,
              'models':{'segmentation':SEG_ID,'depth':DEPTH_ID,'revisions':revisions},
              'input':{'original_size':original_size,'analysis_size':[w,h],
                       'sha256_rgb':hashlib.sha256(image.tobytes()).hexdigest()},
              'sound_provenance':'Procedurally synthesized illustrative sound; not field recording or AI generated.',
              'limitations':['Single-image relative inverse depth; no metric distances.',
                             'Image regions are audio proxies, not measured sound sources.',
                             'Research landscape pre-experience prototype; not navigation or obstacle avoidance.',
                             'No subjective PSD score or user-experience effectiveness is established.'],
              'report_path':str(output_dir/'report.json')}
    Path(report['report_path']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
