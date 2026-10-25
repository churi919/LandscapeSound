"""Auditable semantic-region to spatial-audio mapping for still photographs.

Depth values are relative inverse depth, never metric distances.  Audio sources
are illustrative proxies for visible regions, never detected acoustic events.
"""

from __future__ import annotations

import math
import re
from typing import Mapping

import numpy as np


SEMANTIC_GROUPS: dict[str, frozenset[str]] = {
    "sky": frozenset({"sky"}),
    "vegetation": frozenset({"tree", "palm", "plant", "grass", "flower", "field"}),
    "water": frozenset({"water", "sea", "river", "lake", "waterfall", "fountain", "swimming pool"}),
    "built": frozenset({
        "building", "wall", "house", "fence", "skyscraper", "bridge",
        "tower", "booth", "grandstand", "railing", "pier", "hovel",
        "ceiling", "column", "beam", "awning", "door", "windowpane",
        "screen door", "canopy", "tent", "bannister",
    }),
    "hardscape": frozenset({"road", "sidewalk", "path", "floor", "runway", "stairs", "stairway", "step"}),
}
SOURCE_CLASSES: dict[str, frozenset[str]] = {
    "trees": frozenset({"tree", "palm"}),
    "water": SEMANTIC_GROUPS["water"],
}
SECTORS = (("left", "左侧"), ("center", "中央"), ("right", "右侧"))
MIN_CATEGORY_FRACTION = 0.01
MIN_REGION_FRACTION = 0.006
MAX_SOURCES = 4
DEFAULT_AUDIO_RADIUS = 4.8


def _canonical_label(value: str) -> str:
    """Use ADE's primary class name; aliases after commas/semicolons are metadata."""
    return re.split(r"[,;]", str(value).strip().lower())[0].strip().replace("_", " ")


def _validate_arrays(segmentation: np.ndarray, inverse_depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seg = np.asarray(segmentation)
    depth = np.asarray(inverse_depth, dtype=np.float64)
    if seg.ndim != 2 or depth.ndim != 2 or seg.shape != depth.shape:
        raise ValueError("segmentation and inverse_depth must be matching two-dimensional arrays")
    if seg.size == 0:
        raise ValueError("image arrays must not be empty")
    if not np.issubdtype(seg.dtype, np.integer):
        raise ValueError("segmentation must contain integer class IDs")
    return seg, depth


def _depth_details(inverse_depth: np.ndarray, sky_mask: np.ndarray) -> dict:
    depth = np.asarray(inverse_depth, dtype=np.float64)
    sky = np.asarray(sky_mask, dtype=bool)
    if depth.ndim != 2 or depth.shape != sky.shape or depth.size == 0:
        raise ValueError("inverse_depth and sky_mask must be non-empty matching 2D arrays")
    eligible = ~sky
    valid = eligible & np.isfinite(depth)
    values = depth[valid]
    details = {
        "status": "unavailable",
        "kind": "relative_inverse_depth",
        "larger_is_nearer": True,
        "normalization": "non-sky finite pixels, P5/P95, clipped to [0, 1]",
        "valid_non_sky_pixels": int(values.size),
        "non_sky_pixels": int(eligible.sum()),
        "invalid_depth_pixels": int((~np.isfinite(depth)).sum()),
        "percentile_5": None,
        "percentile_95": None,
        "metric_distance": False,
        "cross_image_comparable": False,
        "reason": "no_valid_non_sky_pixels",
    }
    if values.size < 2:
        return details
    lo, hi = np.percentile(values, [5, 95])
    details["percentile_5"] = float(lo)
    details["percentile_95"] = float(hi)
    scale = max(abs(float(lo)), abs(float(hi)), 1.0)
    if float(hi - lo) <= 1e-8 * scale:
        details["reason"] = "constant_or_degenerate_depth"
        return details
    details.update(status="relative", reason=None)
    return details


def normalize_depth(inverse_depth: np.ndarray, sky_mask: np.ndarray) -> np.ndarray:
    """Normalize finite non-sky inverse depth; zero marks invalid/sky pixels.

    A degenerate map returns zeros.  Callers must consult ``depth_info.status``
    from ``build_scene`` before interpreting these zeros as relative farness.
    """
    depth = np.asarray(inverse_depth, dtype=np.float64)
    sky = np.asarray(sky_mask, dtype=bool)
    info = _depth_details(depth, sky)
    result = np.zeros(depth.shape, dtype=np.float32)
    if info["status"] != "relative":
        return result
    valid = np.isfinite(depth) & ~sky
    result[valid] = np.clip(
        (depth[valid] - info["percentile_5"]) / (info["percentile_95"] - info["percentile_5"]),
        0.0, 1.0,
    ).astype(np.float32)
    return result


def _mask_for(segmentation: np.ndarray, labels: Mapping[int, str], class_names: frozenset[str]) -> np.ndarray:
    ids = [int(class_id) for class_id, label in labels.items() if _canonical_label(label) in class_names]
    return np.isin(segmentation, ids)


def _layout_evidence(mask: np.ndarray, classes: frozenset[str], feature: str) -> dict:
    """Record the exact image-coordinate facts used by spoken descriptions."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    sector_ids = np.minimum(np.arange(w) * 3 // w, 2)
    total = int(mask.sum())
    by_sector = {name: int((mask & (sector_ids[None, :] == index)).sum()) for index, (name, _) in enumerate(SECTORS)}
    return {
        "feature": feature,
        "basis": "semantic_mask",
        "classes": sorted(classes),
        "pixel_count": total,
        "image_fraction": float(mask.mean()),
        "centroid_x_normalized": float(xs.mean() / (w - 1)) if total and w > 1 else (0.5 if total else None),
        "centroid_y_normalized": float(ys.mean() / (h - 1)) if total and h > 1 else (0.5 if total else None),
        "sector_pixels": by_sector,
        "vertical_thresholds": {"upper_below": 0.4, "lower_above": 0.6},
    }


def _vertical_word(fact: dict) -> str:
    value = fact["centroid_y_normalized"]
    return "上部" if value < 0.4 else ("下部" if value > 0.6 else "中部")


def _horizontal_words(fact: dict) -> str:
    minimum = max(fact["pixel_count"] * 0.1, 1)
    present = [zh for name, zh in SECTORS if fact["sector_pixels"][name] >= minimum]
    if not present:
        present = [dict(SECTORS)[max(fact["sector_pixels"], key=fact["sector_pixels"].get)]]
    return "、".join(present)


def _description(
    title: str, fractions: dict[str, float], sources: list[dict], depth_info: dict,
    segmentation: np.ndarray, labels: Mapping[int, str],
) -> tuple[str, list[dict]]:
    groups = {
        "grass": frozenset({"grass", "field"}),
        "water": SOURCE_CLASSES["water"],
        "trees": SOURCE_CLASSES["trees"],
        "overhead": frozenset({"ceiling", "awning", "canopy"}),
        "sky": SEMANTIC_GROUPS["sky"],
        "built": SEMANTIC_GROUPS["built"],
        "hardscape": SEMANTIC_GROUPS["hardscape"],
    }
    facts = {name: _layout_evidence(_mask_for(segmentation, labels, names), names, name) for name, names in groups.items()}
    evidence = [{"feature": "title", "basis": "user_input", "text": title}, *facts.values()]
    # No percentages or subjective experience claims in the spoken narrative.
    parts = [f"{title}。"]
    ground = []
    for name, zh in (("grass", "草地"), ("water", "水面")):
        fact = facts[name]
        if fact["image_fraction"] >= 0.01:
            ground.append(f"{zh}主要位于画面{_vertical_word(fact)}，在{_horizontal_words(fact)}可见")
    if not ground and facts["hardscape"]["image_fraction"] >= 0.03:
        fact = facts["hardscape"]
        ground.append(f"道路或铺装主要位于画面{_vertical_word(fact)}，在{_horizontal_words(fact)}可见")
    if ground:
        parts.append("根据图像识别结果，" + "；".join(ground) + "。")
    trees = facts["trees"]
    if trees["image_fraction"] >= 0.01:
        parts.append(f"可见树木分布在画面{_horizontal_words(trees)}，这里按树群区域概括它们的位置。")
    elif facts["built"]["image_fraction"] >= 0.03:
        fact = facts["built"]
        parts.append(f"建筑及围合界面主要分布在画面{_vertical_word(fact)}的{_horizontal_words(fact)}。")
    context = []
    overhead = facts["overhead"]
    if overhead["image_fraction"] >= 0.005:
        context.append(f"画面{_vertical_word(overhead)}识别到人工顶盖")
    sky = fractions["sky"]
    if sky >= 0.25:
        context.append("天空占据较大的可见画面区域")
    elif sky >= 0.05:
        context.append("画面局部可见天空")
    elif sky >= 0.005:
        context.append("可见天空区域较少")
    else:
        context.append("画面几乎没有识别到天空")
    parts.append("，".join(context) + "。")
    depth_clauses = []
    depth_facts = {"feature": "source_depth", "basis": "retained_semantic_region_sources", "sources": []}
    for category, zh in (("trees", "树木"), ("water", "水体")):
        group_sources = [source for source in sources if source["category"] == category]
        valid_sources = [source for source in group_sources if source["near_score"] is not None]
        for source in group_sources:
            depth_facts["sources"].append({key: source[key] for key in ("id", "sector", "near_score", "area_fraction")})
        if not valid_sources:
            continue
        closest = max(valid_sources, key=lambda source: source["near_score"])
        farthest = min(valid_sources, key=lambda source: source["near_score"])
        if closest["near_score"] - farthest["near_score"] >= 0.2:
            sector_zh = dict(SECTORS)
            depth_clauses.append(f"{sector_zh[closest['sector']]}{zh}比{sector_zh[farthest['sector']]}相对更近")
        else:
            weighted_near = sum(source["near_score"] * source["area_fraction"] for source in valid_sources) / sum(source["area_fraction"] for source in valid_sources)
            relative = "相对较近" if weighted_near >= 0.67 else ("相对较远" if weighted_near <= 0.33 else "处于中间深度层次")
            depth_clauses.append(f"{zh}区域{relative}")
    if depth_clauses:
        parts.append("试听时把照片正前方作为朝向，左右位置都按这个方向理解；按相对深度估计，" + "，".join(depth_clauses) + "。")
    elif sources and depth_info["status"] != "relative":
        parts.append("本图的近远层次暂不能区分，声音采用统一的默认虚拟距离。")
    elif not sources:
        parts.append("本图没有提取出可用于模拟环境声的树木或水体区域。")
    evidence.append(depth_facts)
    parts.append("这是基于照片的模拟声景，近远只在本图内比较。")
    return "".join(parts), evidence


def build_scene(
    segmentation: np.ndarray,
    inverse_depth: np.ndarray,
    labels: Mapping[int, str],
    hfov: float = 70.0,
    title: str = "景观照片",
) -> dict:
    """Return a JSON-safe, reviewable scene from aligned semantic/depth maps."""
    seg, depth = _validate_arrays(segmentation, inverse_depth)
    if not math.isfinite(float(hfov)) or not 1.0 <= float(hfov) <= 170.0:
        raise ValueError("hfov must be a finite horizontal field of view between 1 and 170 degrees")
    title = str(title).strip()[:160] or "景观照片"
    label_map = {int(k): str(v) for k, v in labels.items()}
    h, w = seg.shape
    pixels = h * w
    masks = {name: _mask_for(seg, label_map, names) for name, names in SEMANTIC_GROUPS.items()}
    fractions = {name: float(mask.mean()) for name, mask in masks.items()}
    depth_info = _depth_details(depth, masks["sky"])
    near_map = normalize_depth(depth, masks["sky"])
    x_grid = np.broadcast_to(np.arange(w, dtype=float), (h, w))
    # Exact, non-overlapping thirds, including for narrow images.
    sectors = np.minimum((np.arange(w) * 3 // w), 2)
    sources: list[dict] = []
    for category, names in SOURCE_CLASSES.items():
        mask = _mask_for(seg, label_map, names)
        if float(mask.mean()) < MIN_CATEGORY_FRACTION:
            continue
        for sector_index, (sector_id, sector_zh) in enumerate(SECTORS):
            region = mask & (sectors[None, :] == sector_index)
            area = int(region.sum())
            if area / pixels < MIN_REGION_FRACTION:
                continue
            center_x = float(x_grid[region].mean())
            normalized_x = center_x / (w - 1) if w > 1 else 0.5
            valid_region = region & np.isfinite(depth) & ~masks["sky"]
            valid_ratio = float(valid_region.sum() / area)
            near = None
            if depth_info["status"] == "relative" and valid_ratio >= 0.5:
                near = float(np.median(near_map[valid_region]))
            radius = 1.8 + (1 - near) * 6.0 if near is not None else DEFAULT_AUDIO_RADIUS
            source_name = "树木" if category == "trees" else "水体"
            sources.append({
                "id": f"{category}-{sector_id}",
                "category": category,
                "label": f"{sector_zh}{source_name}区域",
                "enabled": True,
                "azimuth": float((normalized_x - 0.5) * hfov),
                "near_score": near,
                "virtual_radius": float(radius),
                "area_fraction": float(area / pixels),
                "centroid_x": center_x,
                "sector": sector_id,
                "depth_status": "relative" if near is not None else "unavailable",
                "finite_depth_fraction": valid_ratio,
                "provenance": "semantic_region_audio_proxy",
                "audio_kind": "procedural_illustrative_sfx",
            })
    sources.sort(key=lambda source: (-source["area_fraction"], source["category"], source["sector"]))
    discarded_count = max(0, len(sources) - MAX_SOURCES)
    sources = sources[:MAX_SOURCES]
    values, counts = np.unique(seg, return_counts=True)
    class_fractions = [
        {"id": int(class_id), "label": label_map.get(int(class_id), f"unknown_{int(class_id)}"), "fraction": float(count / pixels)}
        for class_id, count in sorted(zip(values, counts), key=lambda pair: (-pair[1], pair[0]))
    ]
    description, description_evidence = _description(title, fractions, sources, depth_info, seg, label_map)
    result = {
        "schema_version": "1.0",
        "title": title,
        "image_size": {"width": w, "height": h},
        "fractions": fractions,
        "semantic_groups": {key: sorted(value) for key, value in SEMANTIC_GROUPS.items()},
        "class_fractions": class_fractions,
        "sources": sources,
        "description": description,
        "description_evidence": description_evidence,
        "depth_info": depth_info,
        "audio_info": {
            "source_kind": "semantic_region_audio_proxy",
            "sound_origin": "procedural_illustrative_sfx",
            "field_recording": False,
            "metric_distance": False,
            "azimuth_convention": "negative=left, positive=right, zero=forward",
            "hfov_degrees": float(hfov),
            "hfov_assumed": True,
            "min_category_fraction": MIN_CATEGORY_FRACTION,
            "min_region_fraction": MIN_REGION_FRACTION,
            "max_sources": MAX_SOURCES,
            "discarded_region_count": discarded_count,
        },
        "limitations": [
            "semantic segmentation and monocular relative depth can be wrong and require review",
            "source regions are left/center/right semantic regions, not object instances or measured sound sources",
            "relative depth is meaningful only within the same image and is not a metric distance",
            "sky pixel fraction is not sky view factor; visual proportions are not subjective PSD scores",
            "illustrative synthetic sounds do not establish actual sound events or serenity",
            "prototype is for landscape pre-experience, not navigation or hazard avoidance",
        ],
    }
    return result
