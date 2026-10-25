"""Plan a small number of continuous textures from semantic image regions.

One visible water surface split into image sectors must not become several
perfectly synchronized copies of the same waveform.  These are audio proxies,
not measured sound sources. Call this function for one view at a time: relative
depth and virtual radii from different panorama views must never be combined.
"""
from __future__ import annotations

import math
from collections.abc import Mapping


_LABELS = {"trees": "树叶与风", "water": "水面", "bird": "鸟鸣（人工启用）",
           "surf": "海浪", "stream": "流水", "traffic": "道路背景", "wind": "风声"}
_MIN_DEPTH_GAP = 2.1
_MIN_SIDE_WEIGHT = 0.15
_MAX_LAYERS = 4


def _number(value, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _weight(value) -> float:
    weight = _number(value, 1.0)
    # A non-positive or out-of-range image fraction is not a useful area.
    # Manual sources and older reports may omit area, so equal weighting is
    # the explicit fallback rather than silently deleting an enabled source.
    return weight if 0 < weight <= 1 else 1.0


def _mean(members: list[dict], key: str) -> float:
    total = math.fsum(member["area_fraction"] for member in members)
    return math.fsum(member[key] * member["area_fraction"] for member in members) / total


def _depth_groups(members: list[dict]) -> list[list[dict]]:
    ordered = sorted(members, key=lambda s: (s["virtual_radius"], s["azimuth"], s["id"]))
    total = math.fsum(member["area_fraction"] for member in ordered)
    candidates = []
    left_weight = 0.0
    for index in range(len(ordered) - 1):
        left_weight += ordered[index]["area_fraction"]
        gap = ordered[index + 1]["virtual_radius"] - ordered[index]["virtual_radius"]
        right_weight = total - left_weight
        if (gap > _MIN_DEPTH_GAP + 1e-9
                and left_weight / total + 1e-12 >= _MIN_SIDE_WEIGHT
                and right_weight / total + 1e-12 >= _MIN_SIDE_WEIGHT):
            candidates.append((gap, index))
    if not candidates:
        return [ordered]
    # At most two material layers. Choose the clearest supported depth gap;
    # a tiny distant fragment does not earn a separate full texture layer.
    _, split = max(candidates, key=lambda item: (item[0], -item[1]))
    return [ordered[:split + 1], ordered[split + 1:]]


def plan_audio_layers(sources) -> list[dict]:
    """Return JSON-safe continuous texture layers for enabled sources.

    Tree/water regions are grouped by material, with one optional meaningful
    depth split. An explicitly supplied enabled bird source is preserved, but
    no bird or other category is inferred or added. ``category_gain`` budgets
    expected energy per material across independently rendered texture layers;
    it is not a measured environmental sound level.
    """
    categories: dict[str, list[dict]] = {}
    for index, source in enumerate(sources or []):
        if not isinstance(source, Mapping) or not bool(source.get("enabled", True)):
            continue
        category = source.get("category")
        if not isinstance(category, str) or category not in _LABELS:
            continue
        radius = _number(source.get("virtual_radius"), 4.8)
        radius = max(1.8, min(7.8, radius)) if radius > 0 else 4.8
        near = source.get("near_score")
        near = _number(near, float("nan")) if near is not None else float("nan")
        near = max(0.0, min(1.0, near)) if math.isfinite(near) else None
        member = {
            "id": str(source.get("id") if source.get("id") is not None else f"source-{index}"),
            "azimuth": max(-90.0, min(90.0, _number(source.get("azimuth"), 0.0))),
            "virtual_radius": radius,
            "near_score": near,
            "area_fraction": _weight(source.get("area_fraction", 1.0)),
            "spread_degrees": max(0.0, min(45.0, _number(source.get("spread_degrees"), 0.0))),
        }
        categories.setdefault(category, []).append(member)

    layers = []
    for category in sorted(categories):
        groups = _depth_groups(categories[category])
        for index, members in enumerate(groups):
            total = math.fsum(member["area_fraction"] for member in members)
            known = [member for member in members if member["near_score"] is not None]
            near = _mean(known, "near_score") if known else None
            angles = [member["azimuth"] for member in members]
            prefix = ("较近的" if index == 0 else "较远的") if len(groups) > 1 else ""
            layers.append({
                "id": f"{category}-layer-{index}",
                "category": category,
                "label": prefix + _LABELS[category],
                "azimuth": max(-90.0, min(90.0, _mean(members, "azimuth"))),
                "virtual_radius": _mean(members, "virtual_radius"),
                "near_score": near,
                "enabled": True,
                "member_ids": sorted(member["id"] for member in members),
                "area_fraction": total,
                "spread_degrees": max(min(25.0, 0.35 * (max(angles) - min(angles))),
                                      max(member["spread_degrees"] for member in members)),
            })

    # Only the retained layers enter the gain budget: a dropped small layer
    # must not leave the audible material unexpectedly quieter.
    layers.sort(key=lambda layer: (-layer["area_fraction"], layer["id"]))
    layers = layers[:_MAX_LAYERS]
    category_totals: dict[str, float] = {}
    for layer in layers:
        category_totals[layer["category"]] = category_totals.get(layer["category"], 0.0) + layer["area_fraction"]
    if not category_totals:
        return []
    base_gain = 0.9 / math.sqrt(len(category_totals))
    for layer in layers:
        layer["category_gain"] = base_gain * math.sqrt(
            layer["area_fraction"] / category_totals[layer["category"]]
        )
    return layers
