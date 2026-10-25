"""Validate web-GPT visual audio proposals and bind them to exact panoramas.

The web reply is source data, never executable instructions. Image hashes,
response hashes and source URLs are supplied locally. Spatial sources created
here are GPT visual proxies with deliberately virtual distances, not detected
or measured acoustic sources. The audio model receives the exact validated
English prompt rather than an automatically embellished version.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from scene_audio_plan import MODEL


PLANNER_VERSION = "web-gpt-panorama-audio-v1"
CLI_PLANNER_VERSION = "logged-in-gpt-panorama-audio-v1"
ALLOWED_CATEGORIES = frozenset({"surf", "stream", "traffic", "wind", "trees", "water"})
ALLOWED_VIEWS = frozenset({"front", "right", "back", "left"})
CONTROL_PROMPTS = {
    "surf": "Soft ocean waves breaking and washing back along a beach.",
    "stream": "A flowing stream with gently bubbling and splashing water.",
    "traffic": "Restrained road vehicle ambience with occasional distant engine and tire movement.",
    "wind": "A soft outdoor breeze with gently varying airy wind sound.",
    "trees": "Soft irregular tree leaves rustling in a light breeze.",
    "water": "Small gentle water ripples lapping against a quiet edge.",
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError(f"{name} must be a complete SHA256 hex digest")
    return value.lower()


def _text(value, name, *, maximum=3000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain nonempty text of at most {maximum} characters")
    return value.strip()


def _texts(value, name, *, maximum=20, optional=False):
    if value is None and optional:
        return []
    if not isinstance(value, list) or not (0 if optional else 1) <= len(value) <= maximum:
        raise ValueError(f"{name} must be a list of {'zero or more' if optional else 'one or more'} text entries")
    return [_text(item, f"{name}[{i}]", maximum=1600) for i, item in enumerate(value)]


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a numeric value in {low}..{high}")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be finite and in {low}..{high}")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _validate_scene(scene):
    if not isinstance(scene, dict):
        raise ValueError("Every scene must be a JSON object")
    # Serializability also rejects non-finite values in unexpected properties.
    _canonical(scene)
    sid = _text(scene.get("id"), "scene.id", maximum=100)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", sid):
        raise ValueError("scene.id must be a simple scene identifier")
    _texts(scene.get("visible_facts_zh"), "scene.visible_facts_zh")
    _texts(scene.get("uncertainties_zh"), "scene.uncertainties_zh")
    stems = scene.get("stems")
    if not isinstance(stems, list) or not 1 <= len(stems) <= 3:
        raise ValueError("scene.stems must contain one to three distinct category proposals")
    categories = set(); ids = set(); enabled_count = 0
    for index, stem in enumerate(stems):
        if not isinstance(stem, dict):
            raise ValueError("Every stem must be an object")
        category = stem.get("category")
        if not isinstance(category, str) or category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Unsupported stem category: {category}")
        if category in categories:
            raise ValueError("Each scene category must occur once; independent stems cannot overwrite one another")
        categories.add(category)
        stem_id = str(stem.get("id", category))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", stem_id) or stem_id in ids:
            raise ValueError("Stem identifiers must be simple and unique")
        ids.add(stem_id)
        _text(stem.get("label_zh"), f"stem[{index}].label_zh", maximum=100)
        _texts(stem.get("visual_evidence_zh"), f"stem[{index}].visual_evidence_zh")
        _texts(stem.get("simulation_assumptions_zh"), f"stem[{index}].simulation_assumptions_zh")
        prompt = _text(stem.get("prompt_en"), f"stem[{index}].prompt_en", maximum=2400)
        words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", prompt)
        if not 20 <= len(words) <= 240 or len(prompt) < 80:
            raise ValueError("prompt_en must be an English audio description of 20..240 words, at least 80 characters")
        enabled = stem.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("stem.enabled must be boolean")
        level = _number(stem.get("relative_level"), "stem.relative_level", 0, 1)
        if enabled and level <= 0:
            raise ValueError("An enabled stem must have positive relative_level")
        enabled_count += int(enabled)
        views = stem.get("views")
        if not isinstance(views, list) or not 1 <= len(views) <= 4:
            raise ValueError("Each stem needs one to four view-specific visual proxies")
        view_ids = set()
        for view in views:
            if not isinstance(view, dict) or not isinstance(view.get("view_id"), str) or view.get("view_id") not in ALLOWED_VIEWS:
                raise ValueError("Unknown view_id; use front/right/back/left")
            if view["view_id"] in view_ids:
                raise ValueError("A stem may contain only one proxy per view")
            view_ids.add(view["view_id"])
            _number(view.get("azimuth"), "view.azimuth", -45, 45)
            _number(view.get("spread_degrees"), "view.spread_degrees", 0, 45)
            _number(view.get("virtual_radius"), "view.virtual_radius", 1.8, 7.8)
            _text(view.get("basis_zh"), "view.basis_zh", maximum=1600)
    if not enabled_count:
        raise ValueError("No enabled GPT audio stems; no generic audio will be substituted")
    return copy.deepcopy(scene)


def parse_gpt_audio_response(text: str, expected_scene_ids=None) -> dict:
    """Parse pure JSON or one complete JSON fence; reject ambiguous replies.

    Return ``{schema_version: 1, scenes: [...]}``. Optional
    ``expected_scene_ids`` requires exactly the requested IDs, preventing a
    partial or mislabelled batch from silently being applied to other images.
    """
    if not isinstance(text, str) or len(text) > 300_000:
        raise ValueError("GPT reply must be bounded UTF-8 JSON text")
    value = text.strip().lstrip("\ufeff")
    if value.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", value, re.I)
        if not match:
            raise ValueError("Reply must contain one complete JSON object or JSON code fence")
        value = match.group(1).strip()
    try:
        parsed = json.loads(value, object_pairs_hook=_unique_object,
                            parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Non-finite JSON number: "+x)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid GPT audio JSON: "+str(exc)) from exc
    if not isinstance(parsed, dict) or type(parsed.get("schema_version")) is not int or parsed.get("schema_version") != 1:
        raise ValueError("GPT audio response needs schema_version=1")
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 12:
        raise ValueError("GPT response needs one to twelve scene objects")
    ids = []
    for scene in scenes:
        _validate_scene(scene); ids.append(scene["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("GPT scene identifiers must be unique")
    if expected_scene_ids is not None and set(ids) != set(expected_scene_ids):
        raise ValueError("GPT scene identifiers do not exactly match the requested image batch")
    return parsed


def _provenance(report, provenance):
    if not isinstance(provenance, dict):
        raise ValueError("Actual GPT response provenance is required")
    result = copy.deepcopy(provenance)
    digest = _sha(report.get("input", {}).get("sha256_rgb"), "report.input.sha256_rgb")
    if _sha(result.get("image_sha256_rgb"), "provenance.image_sha256_rgb") != digest:
        raise ValueError("GPT provenance is bound to a different panorama image")
    result["image_sha256_rgb"] = digest
    result["response_sha256"] = _sha(result.get("response_sha256"), "provenance.response_sha256")
    provider = result.get("provider", "web_chatgpt")
    if provider == "web_chatgpt":
        url = _text(result.get("conversation_url"), "provenance.conversation_url", maximum=2000)
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"}
                or parsed.username or parsed.password):
            raise ValueError("GPT conversation provenance must use an official HTTPS conversation URL")
        result["conversation_url"] = url
    elif provider == "codex_cli":
        if result.get("conversation_url"):
            raise ValueError("Automatic CLI responses must not impersonate a web conversation")
        for name,limit in [("model",160),("cli_version",200),("response_file",3000)]:
            result[name] = _text(result.get(name), "provenance."+name, maximum=limit)
        # The official client handles its own normal ChatGPT login. No key,
        # browser cookie or authentication file is accepted as plan evidence.
        if any(name in result for name in ("api_key","access_token","refresh_token","cookies")):
            raise ValueError("Credentials are not valid GPT plan provenance")
    else:
        raise ValueError("Unsupported GPT provenance provider")
    result["provider"] = provider
    if result.get("contact_sheet_sha256") is not None:
        result["contact_sheet_sha256"] = _sha(result["contact_sheet_sha256"], "provenance.contact_sheet_sha256")
    _canonical(result)
    return digest, result


def _finish(plan):
    plan["items"] = copy.deepcopy(plan["stems"])
    plan.pop("cache_key", None)
    plan["cache_key"] = _hash(plan)
    return plan


def build_gpt_panorama_audio_plan(report: dict, response_scene: dict, provenance: dict) -> dict:
    """Bind a validated GPT proposal to this panorama and local model version."""
    scene = _validate_scene(response_scene)
    digest, source = _provenance(report, provenance)
    if scene.get("image_sha256_rgb") is not None and _sha(scene["image_sha256_rgb"], "scene.image_sha256_rgb") != digest:
        raise ValueError("GPT response scene names a different image fingerprint")
    expected_id = report.get("id", report.get("source_id"))
    if expected_id is not None and str(expected_id) != scene["id"]:
        raise ValueError("GPT scene id does not match this panorama report")
    raw_views = report.get("views")
    if not isinstance(raw_views, list) or not raw_views:
        raise ValueError("A GPT panorama plan requires analyzed perspective views")
    views = {}
    for view in raw_views:
        if not isinstance(view, dict) or not isinstance(view.get("id"), str) or view.get("id") not in ALLOWED_VIEWS or view["id"] in views:
            raise ValueError("Panorama report has unknown or duplicate view IDs")
        views[view["id"]] = {"label": str(view.get("label", view["id"])), "yaw": view.get("yaw", 0),
            "source_ids": [], "categories": [], "sources": []}
    specs = []
    for proposed in scene["stems"]:
        if not proposed.get("enabled", True):
            continue
        category = proposed["category"]
        prompt = proposed["prompt_en"].strip()
        seed = int(_hash({"image": digest, "category": category, "prompt": prompt,
                          "model": MODEL, "planner": PLANNER_VERSION})[:8], 16) & 0x7FFFFFFF
        spec = {"id": str(proposed.get("id", category)), "category": category,
            "label_zh": proposed["label_zh"].strip(), "prompt": prompt, "negative_prompt": None,
            "negative_prompt_note": "CFG=1 does not activate a separate negative branch; requested exclusions are not absence guarantees.",
            "seed": seed, "seconds": MODEL["seconds"], "relative_level": float(proposed["relative_level"]),
            "views": [v["view_id"] for v in proposed["views"]],
            "visual_facts": copy.deepcopy(proposed["visual_evidence_zh"]),
            "sound_assumptions": copy.deepcopy(proposed["simulation_assumptions_zh"]),
            "prompt_source": "web_chatgpt_visual_interpretation" if source['provider']=='web_chatgpt' else "logged_in_gpt_visual_interpretation"}
        specs.append(spec)
        for proxy in proposed["views"]:
            view_id = proxy["view_id"]
            if view_id not in views:
                raise ValueError(f"GPT source references a view absent from this report: {view_id}")
            source_id = "gpt-"+spec["id"]+"-"+view_id
            item = {"id": source_id, "category": category, "label": spec["label_zh"], "enabled": True,
                "azimuth": float(proxy["azimuth"]), "spread_degrees": float(proxy["spread_degrees"]),
                "virtual_radius": float(proxy["virtual_radius"]), "near_score": None,
                "area_fraction": 1.0,
                "area_fraction_basis": "Equal proxy weight, not measured pixel area or acoustic energy",
                "relative_level": spec["relative_level"],
                "source_basis": "GPT visual proxy", "basis_zh": proxy["basis_zh"].strip(),
                "distance_basis": "Virtual rendering choice from visual interpretation, not metres or measured depth"}
            views[view_id]["sources"].append(item)
            views[view_id]["source_ids"].append(source_id)
            views[view_id]["categories"].append(category)
    for view in views.values():
        view["categories"] = sorted(view["categories"])
    planner = PLANNER_VERSION if source['provider']=='web_chatgpt' else CLI_PLANNER_VERSION
    method = "Web ChatGPT interpretation of labelled panorama and four perspective views" if source['provider']=='web_chatgpt' else "Automatic GPT interpretation through the official signed-in Codex client"
    plan = {"schema_version": 1, "planner_version": planner, "condition": "gpt_detailed",
        "scene_id": scene["id"], "scene_title": str(report.get("title", scene["id"])),
        "image_sha256_rgb": digest, "model": copy.deepcopy(MODEL),
        "evidence": {"method": method,
            "visible_facts_zh": copy.deepcopy(scene["visible_facts_zh"]),
            "uncertainties_zh": copy.deepcopy(scene["uncertainties_zh"]),
            "gpt_response_scene": scene, "gpt_provenance": source,
            "source_mapping": "GPT visual proxies; original semantic/depth report is preserved and not silently overwritten",
            "no_inferred_real_sound_measurement": True},
        "assumptions": ["Static images do not establish actual wind, traffic motion, water sound level, or time-varying acoustic events.",
            "Each enabled sound is a documented simulation assumption; direction, spread and radius are visual rendering proxies, not measured acoustic positions."],
        "pictured_site_recording": False, "stems": specs, "views": views}
    return _finish(plan)


def build_category_only_control(plan: dict) -> dict:
    """Change prompts while holding images, stems, seeds and rendering fixed.

    This is a within-scene prompt-detail control. Comparing unrelated pictures
    or unrelated old audio does not by itself isolate the effect of GPT detail.
    """
    if not isinstance(plan, dict) or plan.get("condition") != "gpt_detailed":
        raise ValueError("A category-only control requires a detailed GPT plan")
    if plan.get("cache_key") != _hash({k: v for k, v in plan.items() if k != "cache_key"}):
        raise ValueError("Detailed plan cache key does not match its contents")
    result = copy.deepcopy(plan)
    result["condition"] = "category_only_control"
    result["original_detailed_cache_key"] = plan["cache_key"]
    result["evidence"]["control_protocol"] = {
        "changed": ["positive audio prompt", "condition and prompt provenance"],
        "held_constant": ["input panorama", "enabled categories", "per-stem seed", "audio model and sampling settings",
                          "per-view sources", "relative category levels", "postprocessing algorithm"],
        "boundary": "Matching seed reduces one source of variation; it does not guarantee equal subjective quality or establish causality from one sample per scene."}
    for stem in result["stems"]:
        stem["prompt"] = CONTROL_PROMPTS[stem["category"]]
        stem["prompt_source"] = "fixed_category_only_control"
    return _finish(result)


def load_gpt_panorama_audio_plan(report: dict, path) -> dict | None:
    """Load a saved plan only for the exact image; reject a corrupt matching plan.

    A missing file or another picture returns None. A matching-image record with
    an invalid key, altered prompts, or incomplete provenance raises, so a UI
    cannot silently claim that unrelated cached GPT audio belongs to this image.
    """
    path = Path(path)
    if not path.is_file():
        return None
    stored = json.loads(path.read_text(encoding="utf-8"))
    digest = _sha(report.get("input", {}).get("sha256_rgb"), "report.input.sha256_rgb")
    if not isinstance(stored, dict) or stored.get("image_sha256_rgb") != digest:
        return None
    if stored.get("planner_version") not in {PLANNER_VERSION, CLI_PLANNER_VERSION}:
        raise ValueError("Saved GPT plan has an unsupported planner version")
    evidence = stored.get("evidence", {})
    rebuilt = build_gpt_panorama_audio_plan(report, evidence.get("gpt_response_scene"), evidence.get("gpt_provenance"))
    if stored.get("condition") == "category_only_control":
        rebuilt = build_category_only_control(rebuilt)
    if stored != rebuilt:
        raise ValueError("Saved GPT plan differs from its image-bound source response")
    return stored
