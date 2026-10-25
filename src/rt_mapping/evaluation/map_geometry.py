"""Map metrics on an explicitly shared metric frame, voxel grid and crop.

No ICP or scale fitting occurs here. The caller supplies the recorded
trajectory-only evaluation transform; GT never enters the mapping algorithm.
"""
from __future__ import annotations

import numpy as np

from rt_mapping.fusion import VoxelFusion


def prepare_cloud(points, voxel_size_m, crop_bounds=None):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("cloud must be finite (N,3)")
    if crop_bounds is not None:
        bounds = np.asarray(crop_bounds, dtype=float)
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[0] >= bounds[1]):
            raise ValueError("crop must be [[xmin,ymin,zmin],[xmax,ymax,zmax]]")
        points = points[np.all((points >= bounds[0]) & (points <= bounds[1]), axis=1)]
    if not len(points):
        raise ValueError("cloud is empty after the common evaluation crop")
    fusion = VoxelFusion(voxel_size_m, max_voxels=max(1, len(points)))
    fusion.add(points)
    return fusion.cloud()[0]


def evaluate_map(estimate, reference, *, voxel_size_m=0.02,
                 thresholds_m=(0.02, 0.05, 0.1), crop_bounds=None):
    thresholds = np.asarray(thresholds_m, dtype=float)
    if (thresholds.ndim != 1 or not len(thresholds) or not np.isfinite(thresholds).all()
            or np.any(thresholds <= 0) or np.any(np.diff(thresholds) <= 0)):
        raise ValueError("F-score thresholds must be positive and strictly increasing")
    estimated = prepare_cloud(estimate, voxel_size_m, crop_bounds)
    truth = prepare_cloud(reference, voxel_size_m, crop_bounds)
    from scipy.spatial import cKDTree

    accuracy, _ = cKDTree(truth).query(estimated, k=1)
    completeness, _ = cKDTree(estimated).query(truth, k=1)
    fscores = []
    for threshold in thresholds:
        precision, recall = float(np.mean(accuracy <= threshold)), float(np.mean(completeness <= threshold))
        fscore = 2*precision*recall/(precision+recall) if precision+recall else 0.0
        fscores.append({"threshold_m": float(threshold), "precision": precision, "recall": recall, "fscore": fscore})
    return {
        "units": "meters", "estimate_points": len(estimated), "reference_points": len(truth),
        "voxel_size_m": voxel_size_m, "crop_bounds_m": crop_bounds,
        "accuracy_mean_m": float(accuracy.mean()), "accuracy_median_m": float(np.median(accuracy)),
        "completeness_mean_m": float(completeness.mean()), "completeness_median_m": float(np.median(completeness)),
        "chamfer_l1_m": float((accuracy.mean()+completeness.mean())/2),
        "chamfer_definition": "0.5 * (mean estimate-to-reference distance + mean reference-to-estimate distance)",
        "fscores": fscores, "alignment": "none inside map evaluator",
    }
