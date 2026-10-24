"""Camera projection with OpenCV's five-coefficient Brown distortion model.

Coordinates are integer-centred pixels, camera x right/y down/z forward.
The distortion coefficients stay unchanged under image resize/crop.
"""
from __future__ import annotations

import numpy as np


def validate_pose(T_wc):
    pose = np.asarray(T_wc, dtype=float)
    if (pose.shape != (4, 4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-8)
            or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(pose[:3, :3]), 1, atol=1e-6)):
        raise ValueError("T_wc must be a finite proper rigid pose")
    return pose


def validate_K(K):
    k = np.asarray(K, dtype=float)
    if (k.shape != (3, 3) or not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0
            or not np.allclose(k[2], [0, 0, 1]) or abs(np.linalg.det(k)) < 1e-12):
        raise ValueError("invalid pinhole intrinsics")
    return k


def distort_normalized(xy, distortion):
    xy = np.asarray(xy, dtype=float)
    coefficients = np.asarray(distortion, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
        raise ValueError("normalized points must be finite (N, 2)")
    if coefficients.shape != (5,) or not np.isfinite(coefficients).all():
        raise ValueError("distortion must be finite k1,k2,p1,p2,k3")
    x, y = xy.T
    k1, k2, p1, p2, k3 = coefficients
    radius2 = x*x + y*y
    radial = 1 + radius2 * (k1 + radius2 * (k2 + radius2 * k3))
    return np.column_stack((x * radial + 2*p1*x*y + p2*(radius2 + 2*x*x),
                            y * radial + p1*(radius2 + 2*y*y) + 2*p2*x*y))


def pixel_rays(pixels, K, distortion=None):
    """Invert lens distortion using Newton iterations; refuse unconverged rays."""
    pixels, k = np.asarray(pixels, dtype=float), validate_K(K)
    if pixels.ndim != 2 or pixels.shape[1] != 2 or not np.isfinite(pixels).all():
        raise ValueError("pixels must be finite (N, 2)")
    rays = np.column_stack((pixels, np.ones(len(pixels)))) @ np.linalg.inv(k).T
    target = rays[:, :2] / rays[:, 2, None]
    if distortion is None:
        return np.column_stack((target, np.ones(len(target))))
    d = np.asarray(distortion, dtype=float)
    # Validate even for empty pixels.
    distort_normalized(target, d)
    xy = target.copy()
    for _ in range(30):
        projected = distort_normalized(xy, d)
        error = projected - target
        if not len(error) or np.max(np.abs(error)) < 1e-11:
            break
        h = 1e-6
        dx = (distort_normalized(xy + [h, 0], d) - projected) / h
        dy = (distort_normalized(xy + [0, h], d) - projected) / h
        determinant = dx[:, 0]*dy[:, 1] - dy[:, 0]*dx[:, 1]
        if np.any(np.abs(determinant) < 1e-12):
            raise ValueError("lens distortion inversion is singular")
        step = np.column_stack(((dy[:, 1]*error[:, 0] - dy[:, 0]*error[:, 1]) / determinant,
                                (-dx[:, 1]*error[:, 0] + dx[:, 0]*error[:, 1]) / determinant))
        xy -= step
    if not np.isfinite(xy).all() or (len(xy) and np.max(np.abs(distort_normalized(xy, d) - target)) > 1e-8):
        raise ValueError("lens distortion inversion did not converge")
    return np.column_stack((xy, np.ones(len(xy))))


def back_project(pixels, depth, K, distortion=None):
    depth = np.asarray(depth, dtype=float)
    if depth.shape != (len(pixels),) or not np.isfinite(depth).all() or np.any(depth <= 0):
        raise ValueError("depth must be positive finite camera z, one per pixel")
    return pixel_rays(pixels, K, distortion) * depth[:, None]


def project(points, K, distortion=None):
    points, k = np.asarray(points, dtype=float), validate_K(K)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all() or np.any(points[:, 2] <= 0):
        raise ValueError("points must be finite (N, 3) with positive z")
    xy = points[:, :2] / points[:, 2, None]
    if distortion is not None:
        xy = distort_normalized(xy, distortion)
    homogeneous = np.column_stack((xy, np.ones(len(xy)))) @ k.T
    return homogeneous[:, :2] / homogeneous[:, 2, None]
