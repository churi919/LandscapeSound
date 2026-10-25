"""Model-independent checks for the interpretation layer, not model accuracy."""

import json
import unittest

import numpy as np

from engine import build_scene, normalize_depth


LABELS = {0: "sky", 1: "tree", 2: "water", 3: "building", 4: "grass", 5: "palm", 6: "person", 7: "road"}


class DepthTests(unittest.TestCase):
    def test_larger_inverse_depth_means_nearer(self):
        depth = np.arange(100, dtype=float).reshape(10, 10)
        near = normalize_depth(depth, np.zeros_like(depth, dtype=bool))
        self.assertAlmostEqual(float(near[0, 0]), 0)
        self.assertAlmostEqual(float(near[-1, -1]), 1)
        self.assertTrue(np.all(np.diff(near.ravel()) >= 0))

    def test_sky_excluded_from_percentiles(self):
        depth = np.array([[1000000.0] * 10, list(range(10))])
        sky = np.zeros_like(depth, dtype=bool)
        sky[0] = True
        near = normalize_depth(depth, sky)
        self.assertTrue(np.all(near[0] == 0))
        self.assertAlmostEqual(float(near[1, -1]), 1)

    def test_constant_depth_is_explicitly_unavailable(self):
        seg = np.ones((20, 30), dtype=int)
        depth = np.full(seg.shape, 7.0)
        scene = build_scene(seg, depth, LABELS)
        self.assertEqual(scene["depth_info"]["status"], "unavailable")
        self.assertTrue(np.all(normalize_depth(depth, np.zeros_like(seg, dtype=bool)) == 0))
        self.assertTrue(all(s["near_score"] is None for s in scene["sources"]))
        self.assertTrue(all(s["virtual_radius"] == 4.8 for s in scene["sources"]))
        json.dumps(scene, allow_nan=False)

    def test_nonfinite_depth_is_not_propagated(self):
        seg = np.ones((12, 12), dtype=int)
        depth = np.arange(144, dtype=float).reshape(12, 12)
        depth[0] = np.nan
        depth[1] = np.inf
        near = normalize_depth(depth, np.zeros_like(seg, dtype=bool))
        self.assertTrue(np.all(np.isfinite(near)))
        scene = build_scene(seg, depth, LABELS)
        self.assertEqual(scene["depth_info"]["invalid_depth_pixels"], 24)
        json.dumps(scene, allow_nan=False)

    def test_all_sky_has_no_valid_depth_or_sources(self):
        seg = np.zeros((10, 10), dtype=int)
        scene = build_scene(seg, np.ones_like(seg), LABELS)
        self.assertEqual(scene["depth_info"]["valid_non_sky_pixels"], 0)
        self.assertEqual(scene["sources"], [])


class SourceTests(unittest.TestCase):
    def test_left_and_right_follow_photo_and_near_radius(self):
        seg = np.zeros((10, 30), dtype=int)
        seg[:, :10] = 1
        seg[:, 20:] = 2
        depth = np.tile(np.linspace(20, 1, 30), (10, 1))
        scene = build_scene(seg, depth, LABELS)
        tree = next(s for s in scene["sources"] if s["category"] == "trees")
        water = next(s for s in scene["sources"] if s["category"] == "water")
        self.assertLess(tree["azimuth"], 0)
        self.assertGreater(water["azimuth"], 0)
        self.assertGreater(tree["near_score"], water["near_score"])
        self.assertLess(tree["virtual_radius"], water["virtual_radius"])

    def test_most_four_largest_regions(self):
        seg = np.ones((30, 30), dtype=int)
        seg[15:] = 2
        scene = build_scene(seg, np.arange(900).reshape(30, 30), LABELS)
        self.assertEqual(len(scene["sources"]), 4)
        self.assertEqual(scene["audio_info"]["discarded_region_count"], 2)

    def test_tiny_regions_filtered(self):
        seg = np.zeros((100, 100), dtype=int)
        seg[0, 0] = 1
        seg[0, -1] = 2
        scene = build_scene(seg, np.arange(10000).reshape(100, 100), LABELS)
        self.assertEqual(scene["sources"], [])

    def test_no_sounds_for_grass_people_or_buildings(self):
        seg = np.full((12, 12), 4, dtype=int)
        seg[:4] = 6
        seg[4:8] = 3
        scene = build_scene(seg, np.arange(144).reshape(12, 12), LABELS)
        self.assertEqual(scene["sources"], [])
        self.assertAlmostEqual(scene["fractions"]["vegetation"], 1 / 3)

    def test_palm_audio_never_implies_birds_or_psd_score(self):
        seg = np.full((12, 12), 5, dtype=int)
        scene = build_scene(seg, np.arange(144).reshape(12, 12), LABELS)
        self.assertTrue(all(s["category"] == "trees" for s in scene["sources"]))
        self.assertNotIn("bird", [s["category"] for s in scene["sources"]])
        self.assertNotIn("psd_score", scene)
        self.assertNotIn("鸟鸣", scene["description"])
        self.assertNotIn("PSD", scene["description"])
        self.assertIn("subjective PSD scores", " ".join(scene["limitations"]))

    def test_architectural_ceiling_and_interfaces_are_counted_as_built(self):
        # ADE20K uses class 5 for ceiling, prominent in the courtyard demo.
        interface_labels = {5: "ceiling", 42: "column", 86: "awning", 14: "door", 8: "windowpane", 112: "canopy"}
        seg = np.repeat(np.array(list(interface_labels), dtype=int), 6).reshape(6, 6)
        scene = build_scene(seg, np.arange(36).reshape(6, 6), interface_labels)
        self.assertEqual(scene["fractions"]["built"], 1.0)
        self.assertEqual(scene["fractions"]["vegetation"], 0.0)
        self.assertEqual(scene["sources"], [])
        self.assertIn("ceiling", scene["semantic_groups"]["built"])
        self.assertIn("人工顶盖", scene["description"])
        self.assertNotIn("庇护感", scene["description"])

    def test_water_layout_follows_mask_vertical_position(self):
        labels = {0: "building", 1: "water"}
        top = np.zeros((12, 12), dtype=int)
        top[:3] = 1
        bottom = np.zeros((12, 12), dtype=int)
        bottom[-3:] = 1
        depth = np.arange(144).reshape(12, 12)
        top_scene = build_scene(top, depth, labels)
        bottom_scene = build_scene(bottom, depth, labels)
        self.assertIn("水面主要位于画面上部", top_scene["description"])
        self.assertIn("水面主要位于画面下部", bottom_scene["description"])
        fact = next(fact for fact in bottom_scene["description_evidence"] if fact["feature"] == "water")
        self.assertGreater(fact["centroid_y_normalized"], 0.6)

    def test_overhead_description_requires_actual_overhead_mask(self):
        labels = {0: "tree", 1: "ceiling"}
        no_ceiling = np.zeros((12, 12), dtype=int)
        with_ceiling = no_ceiling.copy()
        with_ceiling[:3] = 1
        depth = np.arange(144).reshape(12, 12)
        no_scene = build_scene(no_ceiling, depth, labels)
        yes_scene = build_scene(with_ceiling, depth, labels)
        self.assertNotIn("人工顶盖", no_scene["description"])
        self.assertIn("画面上部识别到人工顶盖", yes_scene["description"])
        self.assertNotIn("庇护", no_scene["description"])
        self.assertNotIn("庇护", yes_scene["description"])
        fact = next(fact for fact in yes_scene["description_evidence"] if fact["feature"] == "overhead")
        self.assertEqual(fact["image_fraction"], 0.25)
        self.assertEqual(yes_scene["description_evidence"][0]["basis"], "user_input")

    def test_json_has_only_finite_serializable_values(self):
        seg = np.ones((12, 12), dtype=int)
        scene = build_scene(seg, np.arange(144).reshape(12, 12), {str(k): v for k, v in LABELS.items()})
        json.dumps(scene, ensure_ascii=False, allow_nan=False)

    def test_bad_inputs_rejected(self):
        with self.assertRaises(ValueError):
            build_scene(np.ones((5, 5)), np.ones((5, 5)), LABELS)
        with self.assertRaises(ValueError):
            build_scene(np.ones((5, 5), dtype=int), np.ones((6, 6)), LABELS)
        with self.assertRaises(ValueError):
            build_scene(np.ones((5, 5), dtype=int), np.ones((5, 5)), LABELS, hfov=float("nan"))


if __name__ == "__main__":
    unittest.main()
