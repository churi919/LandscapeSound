"""Synthetic geometry checks, not model accuracy or panorama depth validation."""
import math
import unittest

import numpy as np
from PIL import Image

from panorama import heading_label, perspective_view, pixel_azimuth_degrees, validate_equirectangular


def coordinate_panorama(width=720, height=360):
    longitude = (np.arange(width) + 0.5) / width * 2 * math.pi - math.pi
    latitude = math.pi * (0.5 - (np.arange(height) + 0.5) / height)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.rint((np.sin(longitude) + 1) * 127.5)
    image[..., 1] = np.rint((np.cos(longitude) + 1) * 127.5)
    image[..., 2] = np.rint((np.sin(latitude[:, None]) + 1) * 127.5)
    return Image.fromarray(image)


class PerspectiveGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panorama = coordinate_panorama()

    def center(self, yaw=0, pitch=0):
        return np.asarray(perspective_view(self.panorama, yaw, pitch, size=33))[16, 16].astype(int)

    def test_cardinal_heading_centres_match_longitude(self):
        expected = [(0, [128, 255, 128]), (90, [255, 128, 128]),
                    (-90, [0, 128, 128]), (180, [128, 0, 128])]
        for yaw, rgb in expected:
            with self.subTest(yaw=yaw):
                np.testing.assert_allclose(self.center(yaw), rgb, atol=1)

    def test_right_of_forward_looks_at_greater_longitude(self):
        view = np.asarray(perspective_view(self.panorama, size=33))
        self.assertGreater(int(view[16, -1, 0]), int(view[16, 16, 0]))
        self.assertLess(int(view[16, 0, 0]), int(view[16, 16, 0]))

    def test_camera_fov_uses_pinhole_angles(self):
        size = 33
        view = np.asarray(perspective_view(self.panorama, hfov=90, size=size))
        sample_x = (2 * (size - 0.5) / size - 1) * math.tan(math.pi / 4)
        longitude = math.atan2(sample_x, 1)
        expected_red = (math.sin(longitude) + 1) * 127.5
        self.assertAlmostEqual(float(view[16, -1, 0]), expected_red, delta=1)

    def test_yaw_periodicity_is_exact(self):
        first = np.asarray(perspective_view(self.panorama, yaw_degrees=37, size=40))
        for angle in (397, -323, 757):
            with self.subTest(angle=angle):
                np.testing.assert_array_equal(first, perspective_view(self.panorama, yaw_degrees=angle, size=40))

    def test_positive_and_negative_180_share_back_seam(self):
        np.testing.assert_array_equal(
            perspective_view(self.panorama, yaw_degrees=180, size=33),
            perspective_view(self.panorama, yaw_degrees=-180, size=33),
        )

    def test_back_seam_is_continuous_for_periodic_source(self):
        left = self.center(yaw=179)
        right = self.center(yaw=-179)
        self.assertLess(int(np.max(np.abs(left - right))), 6)
        # The view crosses x=width→0. A positive source must never gain black padding.
        width, height = 360, 180
        pixels = np.asarray(coordinate_panorama(width, height)).astype(float)
        positive = Image.fromarray((32 + pixels * 0.75).astype(np.uint8))
        result = np.asarray(perspective_view(positive, yaw_degrees=180, size=99))
        self.assertGreaterEqual(int(result.min()), 32)

    def test_positive_pitch_looks_up_and_poles_clamp(self):
        self.assertEqual(int(self.center(pitch=90)[2]), 255)
        self.assertEqual(int(self.center(pitch=-90)[2]), 0)
        self.assertGreater(int(self.center(pitch=45)[2]), int(self.center()[2]))
        view = np.asarray(perspective_view(self.panorama, size=33))
        self.assertGreater(int(view[0, 16, 2]), int(view[16, 16, 2]))
        self.assertLess(int(view[-1, 16, 2]), int(view[16, 16, 2]))

    def test_single_pixel_view_is_heading_sample(self):
        view = perspective_view(self.panorama, yaw_degrees=90, size=1)
        self.assertEqual(view.size, (1, 1))
        np.testing.assert_allclose(np.asarray(view)[0, 0], [255, 128, 128], atol=1)

    def test_invalid_angles_fov_and_size_rejected(self):
        options = [dict(yaw_degrees=float("nan")), dict(pitch_degrees=float("inf")),
                   dict(pitch_degrees=91), dict(pitch_degrees=-91), dict(hfov=180),
                   dict(hfov=0), dict(hfov=float("nan")), dict(size=0),
                   dict(size=2049), dict(size=32.0), dict(size=True)]
        for option in options:
            with self.subTest(option=option), self.assertRaises(ValueError):
                perspective_view(self.panorama, **option)


class PanoramaInputTests(unittest.TestCase):
    def test_ratio_validates_candidate_not_projection(self):
        validation = validate_equirectangular(Image.new("RGB", (1024, 510)))
        self.assertTrue(validation["ratio_candidate"])
        self.assertFalse(validation["projection_confirmed_by_dimensions"])
        self.assertIn("来源", validation["note"])

    def test_wide_photograph_and_stereo_ratio_rejected(self):
        for size in ((1200, 800), (1024, 1024), (2048, 512), (2, 1)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_equirectangular(Image.new("RGB", size))

    def test_non_image_rejected(self):
        with self.assertRaises(TypeError):
            validate_equirectangular(None)

    def test_relative_heading_labels(self):
        for yaw, text in [(0, "正前方"), (90, "右方"), (180, "后方"),
                          (-180, "后方"), (-90, "左方"), (405, "右前方")]:
            self.assertEqual(heading_label(yaw), text)
        with self.assertRaises(ValueError):
            heading_label(float("nan"))


class PixelAzimuthTests(unittest.TestCase):
    def test_pixel_centres_and_optical_axis(self):
        self.assertEqual(pixel_azimuth_degrees(2, 5), 0.0)
        self.assertEqual(pixel_azimuth_degrees(255.5, 512), 0.0)
        self.assertEqual(pixel_azimuth_degrees(0, 1), 0.0)
        expected_edge = math.degrees(math.atan(0.8))
        self.assertAlmostEqual(pixel_azimuth_degrees(0, 5, 90), -expected_edge)
        self.assertAlmostEqual(pixel_azimuth_degrees(4, 5, 90), expected_edge)
        self.assertLess(expected_edge, 45.0)  # First/last pixel centres are inside image borders.

    def test_left_right_and_monotonic_direction(self):
        rays = [pixel_azimuth_degrees(x, 9, 90) for x in range(9)]
        self.assertTrue(np.all(np.diff(rays) > 0))
        self.assertLess(rays[0], 0)
        self.assertGreater(rays[-1], 0)
        np.testing.assert_allclose(rays, -np.array(rays[::-1]), atol=1e-12)

    def test_matches_perspective_sampling_grid(self):
        width, field = 33, 70
        view = np.asarray(perspective_view(coordinate_panorama(), hfov=field, size=width))
        for x in (0, 5, 16, 27, 32):
            angle = math.radians(pixel_azimuth_degrees(x, width, field))
            expected_red = (math.sin(angle) + 1) * 127.5
            self.assertAlmostEqual(float(view[16, x, 0]), expected_red, delta=1)

    def test_invalid_fov_centroid_and_width_rejected(self):
        invalid = [(-1, 5, 90), (5, 5, 90), (float("nan"), 5, 90),
                   (0, 0, 90), (0, 5.0, 90), (0, True, 90),
                   (0, 5, 0), (0, 5, 180), (0, 5, float("inf"))]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                pixel_azimuth_degrees(*args)


if __name__ == "__main__":
    unittest.main()
