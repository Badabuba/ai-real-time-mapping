"""Pinhole intrinsics updates for image resize and crop.

Pixel convention (docs/ARCHITECTURE.md §3): u right, v down, pixel centres at
integer coordinates (OpenCV/TUM calibration). The top-left pixel centre is
(0, 0) and a W×H image spans [-0.5, W-0.5] × [-0.5, H-0.5].

Lens distortion is neither modelled nor corrected; only K is updated.
"""

from __future__ import annotations

import numpy as np


def _as_intrinsics(K: np.ndarray) -> np.ndarray:
    k = np.array(K, dtype=np.float64)
    if k.shape != (3, 3) or not np.all(np.isfinite(k)):
        raise ValueError(f"K must be a finite 3x3 matrix, got shape {k.shape}")
    if not np.array_equal(k[2], [0.0, 0.0, 1.0]):
        raise ValueError(f"K last row must be [0, 0, 1], got {k[2].tolist()}")
    return k


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    return int(value)


def _as_size(size: tuple[int, int], name: str) -> tuple[int, int]:
    width, height = size
    width, height = _as_int(width, f"{name} width"), _as_int(height, f"{name} height")
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive, got {width}x{height}")
    return width, height


def resize_intrinsics(
    K: np.ndarray, src_size: tuple[int, int], dst_size: tuple[int, int]
) -> np.ndarray:
    """K for an image resized from src_size to dst_size, both (width, height).

    With sx = W'/W and sy = H'/H (may differ):
        fx' = sx·fx, fy' = sy·fy, cx' = (cx + 0.5)·sx - 0.5, cy' = (cy + 0.5)·sy - 0.5
    """
    k = _as_intrinsics(K)
    src_w, src_h = _as_size(src_size, "src_size")
    dst_w, dst_h = _as_size(dst_size, "dst_size")
    sx, sy = dst_w / src_w, dst_h / src_h
    pixel_map = np.array(
        [[sx, 0.0, 0.5 * (sx - 1.0)], [0.0, sy, 0.5 * (sy - 1.0)], [0.0, 0.0, 1.0]]
    )
    return pixel_map @ k


def crop_intrinsics(
    K: np.ndarray, image_size: tuple[int, int], box: tuple[int, int, int, int]
) -> np.ndarray:
    """K for the crop box = (left, top, width, height) of an image of image_size (width, height).

    The box must lie inside the image. cx' = cx - left, cy' = cy - top; focal lengths are unchanged.
    """
    k = _as_intrinsics(K)
    image_w, image_h = _as_size(image_size, "image_size")
    left, top, width, height = (_as_int(v, f"box[{i}]") for i, v in enumerate(box))
    if left < 0 or top < 0 or width <= 0 or height <= 0 or left + width > image_w or top + height > image_h:
        raise ValueError(f"crop box {box} is not inside a {image_w}x{image_h} image")
    pixel_map = np.array([[1.0, 0.0, -left], [0.0, 1.0, -top], [0.0, 0.0, 1.0]])
    return pixel_map @ k
