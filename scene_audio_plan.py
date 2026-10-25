"""Build image-bound, auditable panorama sound prompts without inventing events.

The planner uses the existing four-view semantic reports. It does not infer
wind speed, moving water, people, birds, or other acoustic events from a still
image. Low-intensity motion is an explicit simulation assumption. Optional
reviewed observations are accepted only for the exact panorama RGB digest.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path


PLANNER_VERSION = "panorama-content-audio-v1"
MODEL = {
    "id": "stable-audio-3",
    "name": "Stable Audio 3 Medium",
    "revision": "08b17423649b5714b22eab20f96bf00751f2358a",
    "seconds": 30,
    "steps": 8,
    "cfg": 1.0,
    "dit": "medium",
    "decoder": "same-l",
    "precision": "w8a8",
}
NEGATIVE_PROMPT = (
    "speech, voices, music, singing, birds, insects, traffic, engines, footsteps, "
    "lawn mower, pool pump, splashing people, rain, thunder, roaring wind, "
    "waterfall, distortion, loud impacts, abrupt cuts, rhythmic pulses"
)
_ROOT = Path(__file__).resolve().parent
_PROFILES = {
    "autumn_woodland": (
        "A quiet deciduous woodland with remaining autumn leaves above a leaf-covered forest floor. "
        "Faint papery rustling in the overhead leaves and small irregular leafy swishes, "
        "a soft diffuse canopy texture with short gentle pauses, low intensity. "
        "A very light simulated breeze only; no footsteps or leaves being stepped on."
    ),
    "garden_shrubs": (
        "An open domestic garden with low planted shrubs, clipped hedges, and scattered small trees. "
        "Soft close leaf brushing in dense green shrub foliage, delicate irregular brushing "
        "and a little airy movement between the plants, sparse and subdued, "
        "with separated light gusts rather than a broad roaring canopy."
    ),
    "open_bank_foliage": (
        "Sparse leaves and fine twigs beside an open bank and a hard path. "
        "Delicate individual leaf flicks and short papery flutters, separated by quiet gaps. "
        "Soft leaf-to-leaf brushing, restrained volume, distinct small details. "
        "Very slight foliage movement is simulated."
    ),
    "general_foliage": (
        "The tree and planted foliage regions visible across this outdoor scene. "
        "Soft irregular leaf brushing and subtle airy rustling, a low-intensity "
        "simulated breeze with gradual variations and quiet gaps."
    ),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_demo_observations(report: dict) -> dict | None:
    """Return hand-reviewed facts only when the input panorama digest matches."""
    digest = report.get("input", {}).get("sha256_rgb")
    try:
        records = json.loads((_ROOT / "scene_audio_demo_observations.json").read_text(encoding="utf-8"))
        for item in records.get("items", []):
            if item.get("image_sha256_rgb") == digest:
                return copy.deepcopy(item)
    except (OSError, ValueError, TypeError):
        pass
    return None


def build_panorama_audio_plan(report: dict, observations: dict | None = None) -> dict:
    """Return deterministic per-category prompts and the exact per-view sources.

    ``stems`` is the canonical generation list; ``items`` is a compatibility
    alias with the same entries. Empty stems are valid: the caller should show
    that no supported visible source was found, rather than reuse old audio.
    """
    digest = report.get("input", {}).get("sha256_rgb")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError("A panorama RGB SHA256 is required to bind generated audio to its image")
    digest = digest.lower()
    observations = copy.deepcopy(observations) if observations else None
    if observations and observations.get("image_sha256_rgb", "").lower() != digest:
        raise ValueError("Reviewed visual observations do not match this panorama image")
    valid_views = [v for v in report.get("views", []) if isinstance(v, dict) and isinstance(v.get("report"), dict)]
    if not valid_views:
        raise ValueError("A panorama plan requires at least one analyzed perspective view")

    views = {}
    class_totals = {}
    visual_evidence = []
    categories = set()
    for index, view in enumerate(valid_views):
        view_id = str(view.get("id", f"view_{index}"))
        if view_id in views:
            raise ValueError("Panorama view identifiers must be unique")
        scene = view["report"].get("scene", {})
        active = [copy.deepcopy(s) for s in scene.get("sources", [])
                  if isinstance(s, dict) and s.get("category") in {"trees", "water"} and s.get("enabled", True)]
        for source_index, source in enumerate(active):
            source["id"] = str(source.get("id", f"{view_id}-source-{source_index}"))
        view_categories = sorted({s["category"] for s in active})
        categories.update(view_categories)
        fractions = []
        for item in scene.get("class_fractions", []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", ""))
            fraction = item.get("fraction")
            if not isinstance(fraction, (float, int)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
                continue
            class_totals[label] = class_totals.get(label, 0) + float(fraction)
            fractions.append({"label": label, "fraction": round(float(fraction), 8)})
        views[view_id] = {
            "label": str(view.get("label", view_id)),
            "yaw": view.get("yaw", 0),
            "source_ids": [s["id"] for s in active],
            "categories": view_categories,
            "sources": active,
        }
        visual_evidence.append({"view_id": view_id, "enabled_source_categories": view_categories,
                                "class_fractions": fractions})
    means = {label: round(value / len(valid_views), 8) for label, value in sorted(class_totals.items())}
    amount = lambda *labels: sum(means.get(label, 0) for label in labels)
    if amount("tree") > .3 and amount("earth") > .2:
        auto_profile = "woodland_canopy"
        # Class labels alone do not establish season or dry leaves.
        auto_foliage = (
            "Tree regions and exposed ground are prominent in the analyzed outdoor views. "
            "Diffuse soft tree-foliage rustling, overlapping delicate swishes "
            "with quiet gaps and gradual low-intensity variations."
        )
    elif amount("grass") > .2 and amount("plant", "building", "house", "wall") > .06:
        auto_profile = "garden_shrubs"
        # Grass + plant/built classes do not identify a domestic garden, hedge,
        # clipped planting, species, or small-tree size. Those need visual review.
        auto_foliage = (
            "Grass areas and other vegetation are visible in the analyzed outdoor views. "
            "A restrained vegetation-only texture of soft irregular leaf brushing, "
            "delicate airy rustling and separated light movements with quiet intervals. "
            "The very light breeze is simulated, not measured from the image."
        )
    elif "water" in categories and amount("road", "path", "earth") > .1:
        auto_profile = "open_bank_foliage"
        # Co-occurring water/path/earth classes do not prove an exposed bank,
        # sparse foliage, low shrubs, or adjacency between individual objects.
        auto_foliage = (
            "The analyzed outdoor views contain vegetation, water regions, and hard surfaces or exposed ground. "
            "An isolated soft foliage texture with irregular delicate leaf rustles, "
            "gradual light airy movements and quiet gaps. "
            "This is a low-intensity simulated breeze, with no water in this isolated sound layer."
        )
    else:
        auto_profile = "general_foliage"
        auto_foliage = (
            "Visible vegetation regions in the analyzed outdoor views. "
            "Soft irregular leaf brushing and subtle airy rustling, a low-intensity "
            "simulated breeze with gradual variations and quiet gaps."
        )
    reviewed_profiles = observations.get("profiles", {}) if observations else {}
    reviewed_tree_profile = reviewed_profiles.get("trees")
    tree_style = reviewed_tree_profile if reviewed_tree_profile in _PROFILES else auto_profile
    foliage_prompt = _PROFILES[reviewed_tree_profile] if reviewed_tree_profile in _PROFILES else auto_foliage

    assumption = (
        "A still panorama does not establish actual wind, water motion, time-varying events, or sound level. "
        "A low-intensity breeze and, only where supported water sources exist, small water-edge ripples "
        "are deliberate simulation assumptions rather than recovered site sound."
    )
    reviewed_facts = list(observations.get("visual_facts", [])) if observations else []
    stem_specs = []
    tail = (
        " Continuous isolated field-recording-style texture for landscape simulation, detailed but restrained, "
        "steady without dramatic changes. No music, voices, birds, traffic, or rhythmic pulses."
    )
    for category in sorted(categories):
        matching_views = [name for name, v in views.items() if category in v["categories"]]
        facts = [f"Enabled {category} regions in analyzed views: {', '.join(matching_views)}."]
        facts.extend(reviewed_facts)
        if category == "trees":
            # At CFG=1, naming excluded broadband events in the positive text
            # can itself evoke them. Keep this reviewed sparse-leaf prompt
            # focused on brief discrete leaf details and quiet gaps.
            if reviewed_tree_profile == "open_bank_foliage":
                prompt = foliage_prompt + " An isolated simulated leaf-only texture."
            else:
                prompt = foliage_prompt + tail + " No water or rain in this foliage-only layer."
            style = tree_style
            sound_assumptions = ["Very light breeze through the visible foliage; motion and strength are not measured from the image."]
        else:
            reviewed_water = reviewed_profiles.get("water")
            if reviewed_water == "quiet_inland_lake":
                prompt = (
                    "A quiet inland lake edge with an open reflective water surface and a low bank. "
                    "Tiny irregular ripples gently lap against the edge, a soft shallow liquid wash "
                    "with small distinct laps and quiet intervals, restrained and low energy. "
                    "No crashing surf, waterfall, running stream, boats, or splashing people."
                )
                style = "quiet_inland_lake"
            elif amount("lake") > amount("river", "sea", "waterfall"):
                prompt = (
                    "An outdoor lake-water surface identified in the analyzed views. "
                    "A low-intensity simulation of tiny irregular water-edge ripples, "
                    "soft shallow liquid laps and quiet intervals. "
                    "No crashing surf, waterfall, running stream, boats, or splashing people."
                )
                style = "lake_edge_simulation"
            elif amount("swimming pool") > 0:
                prompt = (
                    "A swimming-pool water surface identified in the analyzed views. Very faint isolated water-edge ripples, "
                    "long quiet gaps and tiny subdued liquid laps only. No pump, fountain, swimmers, "
                    "running stream, ocean surf, or splashing people."
                )
                style = "still_pool_edge_simulation"
            else:
                prompt = (
                    "Water regions identified in the analyzed outdoor views. A soft sparse water texture, "
                    "small gentle irregular liquid laps with quiet intervals and low energy. "
                    "No waterfall, rushing river, crashing ocean surf, pump, or splashing people."
                )
                style = "general_water_edge"
            prompt += tail + " No wind or foliage in this water-only layer."
            sound_assumptions = ["Small low-energy water-edge ripples are simulated; movement and audibility cannot be established from the still picture."]
        seed_payload = {"image": digest, "category": category, "prompt": prompt, "model": MODEL, "planner": PLANNER_VERSION}
        seed = int(_hash(seed_payload)[:8], 16) & 0x7FFFFFFF
        stem_specs.append({
            "id": f"{digest[:12]}_{category}_{_hash(seed_payload)[:12]}",
            "category": category, "prompt": prompt, "negative_prompt": NEGATIVE_PROMPT,
            "negative_prompt_note": "CFG=1 does not activate a negative branch; exclusions are requested, not verified absent.",
            "seed": seed, "seconds": MODEL["seconds"], "style": style,
            "views": matching_views, "visual_facts": facts, "sound_assumptions": sound_assumptions,
        })
    evidence = {
        "method": "Existing four horizontal perspective segmentation/source reports, optionally supplemented by exact-image visual review",
        "views": visual_evidence,
        "mean_class_fractions": means,
        "fraction_boundary": "Unweighted mean of the analyzed perspective view fractions; not a full-sphere area or accuracy estimate.",
        "reviewed_observations": observations,
        "automatic_foliage_profile": auto_profile,
        "no_manual_sources_added": True,
    }
    scene_id = str(observations.get("scene_id")) if observations and observations.get("scene_id") else str(report.get("id", "panorama_" + digest[:12]))
    plan = {
        "schema_version": 1, "planner_version": PLANNER_VERSION,
        "scene_id": scene_id, "scene_title": str(report.get("title", "Panorama")),
        "image_sha256_rgb": digest, "model": copy.deepcopy(MODEL),
        "evidence": evidence, "assumptions": [assumption],
        "unverified_events_not_added": ["birds", "insects", "voices", "traffic", "footsteps", "pool pumps", "waterfalls"],
        "pictured_site_recording": False,
        "stems": stem_specs, "views": views,
    }
    # Bind image, prompt facts, exact spatial sources, model and planner version.
    plan["cache_key"] = _hash(plan)
    plan["items"] = copy.deepcopy(stem_specs)
    return plan
