"""Validate web-reply data, exact image bindings and within-image controls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from gpt_scene_audio import (build_category_only_control, build_gpt_panorama_audio_plan,
                            load_gpt_panorama_audio_plan, parse_gpt_audio_response)


PROMPT = ("A restrained road ambience with soft distant engine movement and a dry fine tire wash. "
          "One gradual pass builds gently, settles into a short quiet gap, then another subtle low engine tone moves away. "
          "Keep the foreground clear with moderate detail and slow natural variation.")


def report():
    return {"id": "urban_road", "title": "道路示例", "input": {"sha256_rgb": "a"*64},
            "views": [{"id": key, "label": key, "yaw": yaw, "report": {"scene": {"sources": []}}}
                      for key, yaw in [("front", 0), ("right", 90), ("back", 180), ("left", -90)]]}


def scene():
    return {"id": "urban_road", "visible_facts_zh": ["道路与车辆可见。"],
            "uncertainties_zh": ["静态照片不能确认车辆在移动或实际声压。"],
            "stems": [{"id": "road", "category": "traffic", "label_zh": "道路背景",
                       "visual_evidence_zh": ["正前方可见道路上的车辆。"],
                       "simulation_assumptions_zh": ["低强度车轮与引擎运动是模拟设定。"],
                       "prompt_en": PROMPT, "relative_level": .6,
                       "views": [{"view_id": "front", "azimuth": -12, "spread_degrees": 20,
                                  "virtual_radius": 5.8, "basis_zh": "道路在画面左中部。"}]}]}


def provenance():
    return {"provider": "web_chatgpt", "image_sha256_rgb": "a"*64,
            "response_sha256": "b"*64, "conversation_url": "https://chatgpt.com/c/test-source"}


class GPTSceneAudioTests(unittest.TestCase):
    def test_parse_plain_or_complete_json_fence(self):
        data = {"schema_version": 1, "scenes": [scene()]}
        text = json.dumps(data, ensure_ascii=False)
        self.assertEqual(parse_gpt_audio_response(text, ["urban_road"]), data)
        self.assertEqual(parse_gpt_audio_response("```json\n"+text+"\n```"), data)
        with self.assertRaises(ValueError): parse_gpt_audio_response("Explanation\n"+text)
        with self.assertRaises(ValueError): parse_gpt_audio_response(text, ["other_image"])

    def test_duplicate_keys_nonfinite_numbers_and_repeated_scene_ids_rejected(self):
        for text in ['{"schema_version":1,"schema_version":1,"scenes":[]}',
                     '{"schema_version":1,"scenes":[],"value":NaN}']:
            with self.assertRaises(ValueError): parse_gpt_audio_response(text)
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_gpt_audio_response(json.dumps({"schema_version": 1, "scenes": [scene(), scene()]}))

    def test_schema_range_category_and_prompt_fail_closed(self):
        changes = [lambda s: s["stems"][0].update(category="bird"),
                   lambda s: s["stems"][0].update(category=["traffic"]),
                   lambda s: s["stems"][0].update(prompt_en="Make sound."),
                   lambda s: s["stems"][0].update(relative_level=1.1),
                   lambda s: s["stems"][0].update(enabled="yes"),
                   lambda s: s["stems"][0].update(simulation_assumptions_zh=[]),
                   lambda s: s["stems"][0]["views"][0].update(view_id="ceiling"),
                   lambda s: s["stems"][0]["views"][0].update(azimuth=46),
                   lambda s: s["stems"][0]["views"][0].update(virtual_radius=8),
                   lambda s: s["stems"][0]["views"][0].update(spread_degrees=-1)]
        for change in changes:
            value = scene(); change(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_gpt_panorama_audio_plan(report(), value, provenance())

    def test_unknown_or_empty_scene_does_not_substitute_generic_audio(self):
        value = scene(); value["id"] = "wrong_image"
        with self.assertRaisesRegex(ValueError, "id does not match"):
            build_gpt_panorama_audio_plan(report(), value, provenance())
        value = scene(); value["stems"][0]["enabled"] = False
        with self.assertRaisesRegex(ValueError, "No enabled"):
            build_gpt_panorama_audio_plan(report(), value, provenance())
        value = scene(); value["stems"].append(copy.deepcopy(value["stems"][0]))
        with self.assertRaisesRegex(ValueError, "occur once"):
            build_gpt_panorama_audio_plan(report(), value, provenance())

    def test_exact_spatial_proxies_and_prompt_are_preserved_without_measured_depth(self):
        original = report(); value = scene()
        plan = build_gpt_panorama_audio_plan(original, value, provenance())
        source = plan["views"]["front"]["sources"][0]
        self.assertEqual(source["category"], "traffic")
        self.assertEqual(source["azimuth"], -12)
        self.assertEqual(source["spread_degrees"], 20)
        self.assertEqual(source["relative_level"], .6)
        self.assertIsNone(source["near_score"])
        self.assertEqual(source["source_basis"], "GPT visual proxy")
        self.assertEqual(plan["views"]["back"]["sources"], [])
        self.assertEqual(plan["stems"][0]["prompt"], PROMPT)
        self.assertEqual(plan["stems"], plan["items"])
        self.assertEqual(original["views"][0]["report"]["scene"]["sources"], [])

    def test_image_and_reply_source_are_required_and_bound(self):
        changed = provenance(); changed["image_sha256_rgb"] = "c"*64
        with self.assertRaisesRegex(ValueError, "different panorama"):
            build_gpt_panorama_audio_plan(report(), scene(), changed)
        changed = provenance(); changed["conversation_url"] = "https://example.com/fake-gpt"
        with self.assertRaisesRegex(ValueError, "official HTTPS"):
            build_gpt_panorama_audio_plan(report(), scene(), changed)
        changed = provenance(); changed.pop("response_sha256")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            build_gpt_panorama_audio_plan(report(), scene(), changed)

    def test_changed_prompt_reply_or_model_fact_invalidates_cache(self):
        original = build_gpt_panorama_audio_plan(report(), scene(), provenance())
        self.assertEqual(original, build_gpt_panorama_audio_plan(report(), scene(), provenance()))
        changed = scene(); changed["stems"][0]["prompt_en"] += " Very restrained."
        self.assertNotEqual(original["cache_key"], build_gpt_panorama_audio_plan(report(), changed, provenance())["cache_key"])
        changed = provenance(); changed["response_sha256"] = "c"*64
        self.assertNotEqual(original["cache_key"], build_gpt_panorama_audio_plan(report(), scene(), changed)["cache_key"])
        changed = scene(); changed["uncertainties_zh"].append("实际混响未知。")
        self.assertNotEqual(original["cache_key"], build_gpt_panorama_audio_plan(report(), changed, provenance())["cache_key"])

    def test_control_only_changes_prompt_and_condition_provenance(self):
        detailed = build_gpt_panorama_audio_plan(report(), scene(), provenance())
        control = build_category_only_control(detailed)
        self.assertEqual(control["condition"], "category_only_control")
        self.assertNotEqual(control["cache_key"], detailed["cache_key"])
        self.assertEqual(control["original_detailed_cache_key"], detailed["cache_key"])
        self.assertEqual(control["model"], detailed["model"])
        self.assertEqual(control["views"], detailed["views"])
        self.assertEqual(control["stems"][0]["seed"], detailed["stems"][0]["seed"])
        self.assertEqual(control["stems"][0]["relative_level"], detailed["stems"][0]["relative_level"])
        self.assertNotEqual(control["stems"][0]["prompt"], detailed["stems"][0]["prompt"])
        self.assertEqual(control["stems"], control["items"])
        with self.assertRaises(ValueError): build_category_only_control(control)

    def test_saved_plan_requires_exact_image_and_unchanged_source_response(self):
        detailed = build_gpt_panorama_audio_plan(report(), scene(), provenance())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"plan.json"
            self.assertIsNone(load_gpt_panorama_audio_plan(report(), path))
            for value in [detailed, build_category_only_control(detailed)]:
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(load_gpt_panorama_audio_plan(report(), path), value)
            changed = report(); changed["input"]["sha256_rgb"] = "c"*64
            self.assertIsNone(load_gpt_panorama_audio_plan(changed, path))
            altered = copy.deepcopy(detailed); altered["stems"][0]["prompt"] += " Altered"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                load_gpt_panorama_audio_plan(report(), path)


if __name__ == "__main__": unittest.main()
