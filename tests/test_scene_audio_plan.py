"""Image binding and evidence boundaries for content-conditioned audio plans."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scene_audio_plan import build_panorama_audio_plan, load_demo_observations


def report(digest="a" * 64, label="tree", fraction=.6, sources=None):
    return {"title": "Test panorama", "input": {"sha256_rgb": digest}, "views": [
        {"id": "front", "yaw": 0, "report": {"scene": {
            "sources": sources if sources is not None else [{"id": "tree-left", "category": "trees", "azimuth": -20, "virtual_radius": 4, "enabled": True}],
            "class_fractions": [{"label": label, "fraction": fraction}]
        }}}
    ]}


class SceneAudioPlanTests(unittest.TestCase):
    def test_cache_is_stable_but_image_or_prompt_fact_changes_invalidate(self):
        original = report()
        a = build_panorama_audio_plan(original)
        self.assertEqual(a, build_panorama_audio_plan(copy.deepcopy(original)))
        changed = copy.deepcopy(original); changed["input"]["sha256_rgb"] = "b" * 64
        self.assertNotEqual(a["cache_key"], build_panorama_audio_plan(changed)["cache_key"])
        observed = {"image_sha256_rgb": "a" * 64, "profiles": {"trees": "garden_shrubs"}, "visual_facts": ["Visible planted shrubs."]}
        b = build_panorama_audio_plan(original, observed)
        self.assertNotEqual(a["cache_key"], b["cache_key"])
        self.assertNotEqual(a["stems"][0]["prompt"], b["stems"][0]["prompt"])

    def test_wrong_image_observation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            build_panorama_audio_plan(report(), {"image_sha256_rgb": "b" * 64})

    def test_source_category_mapping_preserves_spatial_sources(self):
        r = report(sources=[{"id": "water-right", "category": "water", "azimuth": 32, "virtual_radius": 6}])
        r["views"].append({"id": "back", "yaw": 180, "report": {"scene": {
            "sources": [{"id": "tree-left", "category": "trees", "azimuth": -41, "virtual_radius": 2}],
            "class_fractions": []}}})
        p = build_panorama_audio_plan(r)
        self.assertEqual(p["views"]["front"]["categories"], ["water"])
        self.assertEqual(p["views"]["back"]["categories"], ["trees"])
        self.assertEqual(p["views"]["front"]["sources"][0]["azimuth"], 32)
        by = {s["category"]: s for s in p["stems"]}
        self.assertEqual(by["water"]["views"], ["front"])
        self.assertEqual(by["trees"]["views"], ["back"])
        self.assertNotEqual(by["water"]["prompt"], by["trees"]["prompt"])

    def test_no_supported_enabled_source_does_not_invent_one(self):
        r = report(sources=[{"category": "bird"}, {"category": "water", "enabled": False}])
        p = build_panorama_audio_plan(r)
        self.assertEqual(p["stems"], [])
        self.assertEqual(p["views"]["front"]["sources"], [])
        self.assertFalse(p["pictured_site_recording"])

    def test_semantics_can_change_prompt_without_hand_review(self):
        a = report()
        b = report()
        a["views"][0]["report"]["scene"]["class_fractions"] += [{"label": "earth", "fraction": .3}]
        b["views"][0]["report"]["scene"]["class_fractions"] = [
            {"label": "grass", "fraction": .4}, {"label": "plant", "fraction": .2}]
        pa = build_panorama_audio_plan(a); pb = build_panorama_audio_plan(b)
        self.assertNotEqual(pa["stems"][0]["prompt"], pb["stems"][0]["prompt"])
        self.assertNotIn("autumn leaves", pa["stems"][0]["prompt"])

    def test_rgb_digest_required(self):
        with self.assertRaisesRegex(ValueError, "RGB SHA256"):
            build_panorama_audio_plan(report(digest="unknown"))

    def test_automatic_profiles_do_not_invent_reviewed_planting_details(self):
        r = report()
        r["views"][0]["report"]["scene"]["class_fractions"] = [
            {"label": "grass", "fraction": .4}, {"label": "plant", "fraction": .2}]
        prompt = build_panorama_audio_plan(r)["stems"][0]["prompt"]
        for unsupported in ["domestic", "clipped", "hedge", "small trees"]:
            self.assertNotIn(unsupported, prompt)
        r["views"][0]["report"]["scene"]["sources"].append({"category": "water", "id": "water"})
        r["views"][0]["report"]["scene"]["class_fractions"] = [
            {"label": "tree", "fraction": .1}, {"label": "road", "fraction": .3}]
        prompt = next(s["prompt"] for s in build_panorama_audio_plan(r)["stems"] if s["category"] == "trees")
        for unsupported in ["sparse", "shrubs", "exposed open bank"]:
            self.assertNotIn(unsupported, prompt)

    def test_reviewed_profiles_produce_distinct_foliage_without_inventing_pool_source(self):
        # Entirely synthetic observations exercise the real loader and planner;
        # no local photograph, model report or saved visual review is required.
        profiles=['open_bank_foliage','autumn_woodland','garden_shrubs']
        records={'items':[{'scene_id':'fixture_'+str(index),'image_sha256_rgb':digest*64,
            'profiles':{'trees':profile},
            'visual_facts':['Synthetic fixture only: visible foliage; '
                'a described pool does not establish an enabled water source.']}
            for index,(digest,profile) in enumerate(zip('abc',profiles))]}
        prompts=[]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'scene_audio_demo_observations.json').write_text(json.dumps(records),encoding='utf-8')
            with patch('scene_audio_plan._ROOT',root):
                for digest in 'abc':
                    r=report(digest=digest*64)
                    observations=load_demo_observations(r)
                    self.assertIsNotNone(observations)
                    p=build_panorama_audio_plan(r,observations)
                    prompts.append(next(s['prompt'] for s in p['stems'] if s['category']=='trees'))
                    self.assertEqual(p['items'],p['stems'])
                    self.assertEqual([s['category'] for s in p['stems']],['trees'])
                    self.assertTrue(p['evidence']['no_manual_sources_added'])
                self.assertIsNone(load_demo_observations(report(digest='d'*64)))
        self.assertEqual(len(set(prompts)),3)


if __name__ == "__main__":
    unittest.main()
