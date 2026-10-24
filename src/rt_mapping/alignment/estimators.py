"""Robust scalar and Umeyama/RANSAC Sim(3), source -> target metres.

Row-array convention: target = scale * source @ R.T + t. Thresholds and
residuals are measured in the target's metric units, never in SLAM units.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class AlignmentError(ValueError):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(f"{reason}: {message}")


@dataclass(frozen=True)
class AlignmentResult:
    scale: float
    R: np.ndarray
    t: np.ndarray
    residuals_m: np.ndarray
    inliers: np.ndarray
    method: str
    threshold_m: float

    def transform(self, points: np.ndarray) -> np.ndarray:
        return self.scale * np.asarray(points) @ self.R.T + self.t

    def to_dict(self, source_frame="slam_world", target_frame="metric_world") -> dict:
        residuals = self.residuals_m[self.inliers]
        return {
            "status": "ok", "failure_reason": None,
            "source_frame": source_frame, "target_frame": target_frame,
            "transform_direction": "target = scale * R @ source + t",
            "scale": self.scale, "R": self.R.tolist(), "t": self.t.tolist(),
            "method": self.method, "number_of_pairs": len(self.inliers),
            "inlier_count": int(self.inliers.sum()), "inlier_ratio": float(self.inliers.mean()),
            "median_residual_m": float(np.median(residuals)),
            "p95_residual_m": float(np.percentile(residuals, 95)),
            "all_pairs_median_residual_m": float(np.median(self.residuals_m)),
            "thresholds": {"residual_m": self.threshold_m},
        }


def _settings(threshold_m, min_inliers, min_ratio):
    if not np.isfinite(threshold_m) or threshold_m <= 0:
        raise ValueError("threshold_m must be finite and positive")
    if type(min_inliers) is not int or min_inliers < 1:
        raise ValueError("min_inliers must be a positive integer")
    if not np.isfinite(min_ratio) or not 0 < min_ratio <= 1:
        raise ValueError("min_ratio must be in (0, 1]")


def _accept(residuals, threshold_m, min_inliers, min_ratio):
    inliers = residuals <= threshold_m
    if inliers.sum() < min_inliers or inliers.mean() < min_ratio:
        raise AlignmentError("insufficient_correspondences", "inlier count/ratio below acceptance gate")
    return inliers


def estimate_scale(source_depth, target_depth_m, *, threshold_m=0.10,
                   min_inliers=30, min_ratio=0.5) -> AlignmentResult:
    """Median positive depth ratio, then median refit on metric-residual inliers.

    Source and target must already have been filtered: malformed samples are
    rejected explicitly. This estimator assumes a majority of correct pairs.
    """
    _settings(threshold_m, min_inliers, min_ratio)
    source, target = np.asarray(source_depth, dtype=float), np.asarray(target_depth_m, dtype=float)
    if source.ndim != 1 or source.shape != target.shape:
        raise ValueError("depth arrays must have equal one-dimensional shapes")
    if len(source) < min_inliers:
        raise AlignmentError("insufficient_correspondences", "too few depth pairs")
    if not np.isfinite(source).all() or not np.isfinite(target).all() or np.any(source <= 0) or np.any(target <= 0):
        raise AlignmentError("invalid_scale", "depth pairs must be positive and finite")
    ratios = target / source
    scale = float(np.median(ratios))
    for _ in range(5):
        residuals = np.abs(scale * source - target)
        inliers = _accept(residuals, threshold_m, min_inliers, min_ratio)
        updated = float(np.median(ratios[inliers]))
        if np.isclose(updated, scale, rtol=1e-12, atol=0):
            break
        scale = updated
    if not np.isfinite(scale) or scale <= 0:
        raise AlignmentError("invalid_scale", "estimated scale is not positive and finite")
    residuals = np.abs(scale * source - target)
    inliers = _accept(residuals, threshold_m, min_inliers, min_ratio)
    return AlignmentResult(scale, np.eye(3), np.zeros(3), residuals, inliers, "robust_median", threshold_m)


def _umeyama(source, target):
    x, y = source - source.mean(axis=0), target - target.mean(axis=0)
    # Planar samples are sufficient; collinear/coincident samples are not.
    if np.linalg.matrix_rank(x) < 2 or np.linalg.matrix_rank(y) < 2:
        raise AlignmentError("degenerate_geometry", "Sim(3) requires non-collinear pairs")
    u, singular, vt = np.linalg.svd(y.T @ x / len(x))
    signs = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1
    rotation = (u * signs) @ vt
    scale = float(np.dot(singular, signs) / np.mean(np.sum(x * x, axis=1)))
    if not np.isfinite(scale) or scale <= 0:
        raise AlignmentError("invalid_scale", "Umeyama produced an invalid scale")
    translation = target.mean(axis=0) - scale * rotation @ source.mean(axis=0)
    return scale, rotation, translation


def estimate_sim3(source_xyz, target_xyz_m, *, threshold_m=0.10,
                  min_inliers=30, min_ratio=0.5, iterations=500, seed=0) -> AlignmentResult:
    """Deterministic 3-pair RANSAC + proper-rotation Umeyama inlier refit."""
    _settings(threshold_m, min_inliers, min_ratio)
    source, target = np.asarray(source_xyz, dtype=float), np.asarray(target_xyz_m, dtype=float)
    if source.ndim != 2 or source.shape[1:] != (3,) or target.shape != source.shape:
        raise ValueError("point arrays must have equal (N, 3) shapes")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise AlignmentError("non_finite_output", "point pairs must be finite")
    if len(source) < max(3, min_inliers):
        raise AlignmentError("insufficient_correspondences", "too few 3D pairs")
    if type(iterations) is not int or iterations < 1 or type(seed) is not int or seed < 0:
        raise ValueError("iterations must be positive and seed nonnegative integers")
    if np.linalg.matrix_rank(source - source.mean(axis=0)) < 2:
        raise AlignmentError("degenerate_geometry", "source points are collinear or coincident")
    rng = np.random.default_rng(seed)
    best, score = None, (-1, -np.inf)
    for _ in range(iterations):
        indices = rng.choice(len(source), 3, replace=False)
        try:
            scale, rotation, translation = _umeyama(source[indices], target[indices])
        except AlignmentError:
            continue
        residuals = np.linalg.norm(scale * source @ rotation.T + translation - target, axis=1)
        mask = residuals <= threshold_m
        candidate = (int(mask.sum()), -float(np.median(residuals[mask])) if mask.any() else -np.inf)
        if candidate > score:
            score, best = candidate, mask
    if best is None or best.sum() < max(3, min_inliers):
        raise AlignmentError("insufficient_correspondences", "RANSAC found no acceptable model")
    for _ in range(5):
        scale, rotation, translation = _umeyama(source[best], target[best])
        residuals = np.linalg.norm(scale * source @ rotation.T + translation - target, axis=1)
        updated = _accept(residuals, threshold_m, min_inliers, min_ratio)
        if np.array_equal(best, updated):
            break
        best = updated
    return AlignmentResult(scale, rotation, translation, residuals, updated, "umeyama_ransac", threshold_m)
