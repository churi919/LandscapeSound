"""Extract ordinary perspective views from a full-sphere 2:1 panorama.

Coordinates: panorama x=width/2 faces forward, increasing x turns right;
the left/right image seam faces backward. Positive pitch looks upward.
Pixel-centre camera rays are rotated, converted to longitude/latitude, then
sampled bilinearly with a periodic horizontal seam and clamped vertical edge.

Projection does not calibrate depth. Independently inferred perspective-view
depths remain local relative estimates, not a common 360-degree distance map.

Background: Peng and Zhang, 2021, https://arxiv.org/abs/2111.12018
Panorama-vs-perspective limitations: https://arxiv.org/abs/2102.03550
"""
from __future__ import annotations

import math
from numbers import Integral

import numpy as np
from PIL import Image


def _finite_angle(value: float, name: str) -> float:
    try:
        angle = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite angle in degrees") from exc
    if not math.isfinite(angle):
        raise ValueError(f"{name} must be a finite angle in degrees")
    return angle


def validate_equirectangular(image: Image.Image) -> dict:
    """Reject unsupported dimensions; a 2:1 ratio alone does not certify ERP.

    The caller must still confirm from the source that the image is a complete
    360 by 180 degree, monoscopic equirectangular panorama. A wide ordinary
    photograph, a partial panorama or a stereo pair must not be auto-converted.
    A relative ratio tolerance of 2 percent allows modest export rounding.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL Image")
    width, height = image.size
    if width < 4 or height < 2:
        raise ValueError("panorama must be at least 4 by 2 pixels")
    ratio = width / height
    if abs(ratio - 2.0) / 2.0 > 0.02:
        raise ValueError(
            "Expected a complete 360°×180° equirectangular panorama near 2:1; "
            f"received {width}×{height} ({ratio:.3f}:1). "
            "An arbitrary wide photograph is not a spherical panorama."
        )
    return {
        "width": width,
        "height": height,
        "aspect_ratio": ratio,
        "ratio_candidate": True,
        "projection_confirmed_by_dimensions": False,
        "required_projection": "full_sphere_monoscopic_equirectangular",
        "note": "近2:1仅作尺寸筛选，仍须由图像来源确认360°×180°等距柱状投影。",
    }


def heading_label(yaw: float) -> str:
    """Return a relative heading, independent of geographic north."""
    angle = _finite_angle(yaw, "yaw") % 360.0
    labels = ("正前方", "右前方", "右方", "右后方", "后方", "左后方", "左方", "左前方")
    return labels[int(math.floor((angle + 22.5) / 45.0)) % 8]


def pixel_azimuth_degrees(centroid_x: float, width: int, hfov: float = 90.0) -> float:
    """Map a perspective pixel centre to its camera-relative horizontal ray.

    Pixel indices lie in [0,width-1]; the continuous optical centre is
    ``(width-1)/2``. The formula exactly follows ``perspective_view``'s
    pixel-centre sampling convention. Negative angles are left, positive right.
    This is a direction within one view, not a cross-view depth calibration.
    """
    if isinstance(width, bool) or not isinstance(width, Integral) or width < 1:
        raise ValueError("width must be a positive integer")
    x = _finite_angle(centroid_x, "centroid_x")
    if not 0.0 <= x <= width - 1.0:
        raise ValueError("centroid_x must be between 0 and width-1")
    field = _finite_angle(hfov, "hfov")
    if not 1.0 <= field < 180.0:
        raise ValueError("hfov must be at least 1 and strictly below 180 degrees")
    ray_x = (2.0 * (x + 0.5) / int(width) - 1.0) * math.tan(math.radians(field) / 2.0)
    return math.degrees(math.atan2(ray_x, 1.0))


def perspective_view(
    image: Image.Image,
    yaw_degrees: float = 0.0,
    pitch_degrees: float = 0.0,
    hfov: float = 90.0,
    size: int = 512,
) -> Image.Image:
    """Render a square pinhole view at the panorama capture position.

    ``yaw_degrees`` is periodic; 0 is the middle of the panorama, +90 its
    right-hand quarter and ±180 the wrap seam. ``pitch_degrees`` is in [-90,90].
    ``hfov`` is a horizontal field of view in [1,180) degrees. Square output
    means vertical and horizontal FOV are identical. No synthetic scenery,
    hole filling or black padding is introduced. Output is display RGB.
    """
    info = validate_equirectangular(image)
    yaw = _finite_angle(yaw_degrees, "yaw_degrees")
    pitch = _finite_angle(pitch_degrees, "pitch_degrees")
    field = _finite_angle(hfov, "hfov")
    if not -90.0 <= pitch <= 90.0:
        raise ValueError("pitch_degrees must lie between -90 and 90")
    if not 1.0 <= field < 180.0:
        raise ValueError("hfov must be at least 1 and strictly below 180 degrees")
    if isinstance(size, bool) or not isinstance(size, Integral) or not 1 <= size <= 2048:
        raise ValueError("size must be an integer between 1 and 2048")
    size = int(size)
    yaw = math.radians((yaw + 180.0) % 360.0 - 180.0)
    pitch = math.radians(pitch)
    extent = math.tan(math.radians(field) / 2.0)
    # Coordinates sample output pixel centres rather than the image border.
    horizontal = (2.0 * (np.arange(size, dtype=np.float64) + 0.5) / size - 1.0) * extent
    vertical = -horizontal
    camera_x, camera_y = np.meshgrid(horizontal, vertical)
    camera_z = np.ones_like(camera_x)

    # Pitch around camera-right, then yaw around world-up. The local forward
    # axis is +z; the browser audio layer independently uses its own -z forward.
    pitched_y = math.cos(pitch) * camera_y + math.sin(pitch) * camera_z
    pitched_z = -math.sin(pitch) * camera_y + math.cos(pitch) * camera_z
    world_x = math.cos(yaw) * camera_x + math.sin(yaw) * pitched_z
    world_z = -math.sin(yaw) * camera_x + math.cos(yaw) * pitched_z
    longitude = np.arctan2(world_x, world_z)
    latitude = np.arctan2(pitched_y, np.hypot(world_x, world_z))

    width, height = info["width"], info["height"]
    source_x = (longitude / (2.0 * math.pi) + 0.5) * width - 0.5
    source_y = np.clip((0.5 - latitude / math.pi) * height - 0.5, 0.0, height - 1.0)
    floor_x = np.floor(source_x)
    floor_y = np.floor(source_y)
    x0 = floor_x.astype(np.int64) % width
    x1 = (x0 + 1) % width
    y0 = floor_y.astype(np.int64)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = (source_x - floor_x)[..., None]
    wy = (source_y - floor_y)[..., None]
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    top = pixels[y0, x0] * (1.0 - wx) + pixels[y0, x1] * wx
    bottom = pixels[y1, x0] * (1.0 - wx) + pixels[y1, x1] * wx
    result = top * (1.0 - wy) + bottom * wy
    return Image.fromarray(np.clip(np.rint(result), 0, 255).astype(np.uint8))
