"""Audio texture planning checks independent of models and browser rendering."""
import json
import math
import unittest

from audio_layers import plan_audio_layers


def region(name, category="water", radius=4.0, area=.1, angle=0, **extra):
    return {"id": name, "category": category, "virtual_radius": radius,
            "area_fraction": area, "azimuth": angle, "near_score": .5,
            "enabled": True, **extra}


class AudioLayerTests(unittest.TestCase):
    def test_three_parts_of_water_become_one_texture(self):
        sources = [region("left", angle=-30), region("middle"), region("right", angle=30)]
        layers = plan_audio_layers(sources)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["member_ids"], ["left", "middle", "right"])
        self.assertAlmostEqual(layers[0]["azimuth"], 0)
        self.assertAlmostEqual(layers[0]["spread_degrees"], 21)
        self.assertAlmostEqual(layers[0]["category_gain"], .9)

    def test_spatial_average_respects_area_instead_of_sector_count(self):
        layer = plan_audio_layers([region("small", area=.05, angle=-40, radius=4),
                                   region("large", area=.15, angle=20, radius=5)])[0]
        self.assertAlmostEqual(layer["azimuth"], 5)
        self.assertAlmostEqual(layer["virtual_radius"], 4.75)
        self.assertAlmostEqual(layer["area_fraction"], .2)

    def test_clear_near_and_far_layers_are_preserved(self):
        layers = plan_audio_layers([region("near", radius=2, area=.2),
                                    region("far", radius=7, area=.3)])
        self.assertEqual(len(layers), 2)
        self.assertEqual({tuple(layer["member_ids"]) for layer in layers}, {("near",), ("far",)})
        self.assertGreater(max(layer["virtual_radius"] for layer in layers)
                           - min(layer["virtual_radius"] for layer in layers), 2.1)

    def test_tiny_distant_fragment_does_not_add_a_layer(self):
        layers = plan_audio_layers([region("main", radius=2, area=.9),
                                    region("tiny", radius=7, area=.1)])
        self.assertEqual(len(layers), 1)
        self.assertEqual(set(layers[0]["member_ids"]), {"main", "tiny"})

    def test_fifteen_percent_boundary_is_allowed_but_small_gap_is_not(self):
        self.assertEqual(len(plan_audio_layers([region("near", radius=2, area=.15),
                                                region("far", radius=7, area=.85)])), 2)
        self.assertEqual(len(plan_audio_layers([region("near", radius=2, area=.5),
                                                region("far", radius=4.1, area=.5)])), 1)

    def test_source_partition_does_not_change_material_gain(self):
        whole = plan_audio_layers([region("whole", area=.3), region("tree", "trees", area=.2)])
        parts = plan_audio_layers([region("a"), region("b"), region("c"),
                                   region("tree", "trees", area=.2)])
        gain = lambda layers: {layer["category"]: layer["category_gain"] for layer in layers}
        self.assertEqual(set(gain(whole)), {"water", "trees"})
        for category in gain(whole):
            self.assertAlmostEqual(gain(whole)[category], gain(parts)[category])

    def test_two_depth_layers_share_one_material_energy_budget(self):
        layers = plan_audio_layers([region("near", radius=2, area=.3),
                                    region("far", radius=7, area=.6),
                                    region("tree", "trees", area=.1)])
        per_category = {}
        for layer in layers:
            per_category[layer["category"]] = per_category.get(layer["category"], 0) + layer["category_gain"] ** 2
        self.assertAlmostEqual(per_category["water"], .9 ** 2 / 2)
        self.assertAlmostEqual(per_category["trees"], .9 ** 2 / 2)

    def test_disabled_and_unknown_sources_are_not_audible(self):
        self.assertEqual(plan_audio_layers([region("off", enabled=False), region("unknown", "music")]), [])
        self.assertEqual(plan_audio_layers([]), [])
        self.assertEqual(plan_audio_layers(None), [])

    def test_birds_are_never_inferred_but_manual_bird_is_preserved(self):
        trees = plan_audio_layers([region("tree", "trees")])
        self.assertTrue(all(layer["category"] != "bird" for layer in trees))
        bird = plan_audio_layers([region("manual", "bird")])
        self.assertEqual(bird[0]["member_ids"], ["manual"])

    def test_invalid_values_fall_back_to_finite_json(self):
        layers = plan_audio_layers([
            region("bad", area=float("nan"), angle=float("inf"), radius=float("nan"), near_score=None),
            region("zero", area=0, angle=-1000, radius=-1, near_score=float("inf")),
            {"id": "missing", "category": "trees"},
            {"id": "huge", "category": "trees", "area_fraction": 1e308},
        ])
        json.dumps(layers, allow_nan=False)
        for layer in layers:
            self.assertTrue(-90 <= layer["azimuth"] <= 90)
            self.assertTrue(1.8 <= layer["virtual_radius"] <= 7.8)
            self.assertTrue(0 <= layer["spread_degrees"] <= 25)
            self.assertTrue(math.isfinite(layer["category_gain"]))

    def test_limit_four_retains_largest_supported_layers(self):
        sources = [region("wn", radius=2, area=.3), region("wf", radius=7, area=.4),
                   region("tn", "trees", radius=2, area=.2), region("tf", "trees", radius=7, area=.3),
                   region("bn", "bird", radius=2, area=.01), region("bf", "bird", radius=7, area=.01)]
        layers = plan_audio_layers(sources)
        self.assertEqual(len(layers), 4)
        self.assertTrue(all(layer["category"] != "bird" for layer in layers))
        self.assertLessEqual(len(layers), len(sources))

    def test_reordering_identified_regions_preserves_layer_identity(self):
        sources = [region("a", radius=2, area=.2), region("b", radius=7, area=.3)]
        self.assertEqual(plan_audio_layers(sources), plan_audio_layers(list(reversed(sources))))


if __name__ == "__main__":
    unittest.main()
