"""Incremental equal-weight voxel centroids in metres; no GT or model imports."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from rt_mapping.alignment.estimators import AlignmentError
from rt_mapping.geometry.projection import back_project, validate_pose


def metric_pose(T_wc, scale):
    pose = validate_pose(T_wc).copy()
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be finite and positive")
    pose[:3, 3] *= scale
    return pose


def depth_points(prediction, T_wc_metric, *, distortion=None, min_depth_m=0.1,
                 max_depth_m=8.0, confidence_threshold=None, pixel_stride=1):
    pose = validate_pose(T_wc_metric)
    if not np.isfinite([min_depth_m, max_depth_m]).all() or not 0 < min_depth_m < max_depth_m:
        raise ValueError("invalid depth range")
    if type(pixel_stride) is not int or pixel_stride < 1:
        raise ValueError("pixel_stride must be a positive integer")
    mask = prediction.valid_mask.copy()
    mask &= (prediction.depth_m >= min_depth_m) & (prediction.depth_m <= max_depth_m)
    if confidence_threshold is not None:
        if not np.isfinite(confidence_threshold):
            raise ValueError("confidence threshold must be finite")
        if prediction.confidence is None:
            raise AlignmentError("missing_confidence", "confidence threshold requested without confidence")
        mask &= prediction.confidence >= confidence_threshold
    sampled = np.zeros_like(mask)
    sampled[::pixel_stride, ::pixel_stride] = True
    v, u = np.nonzero(mask & sampled)
    camera = back_project(np.column_stack((u, v)), prediction.depth_m[v, u], prediction.K_processed, distortion)
    return camera @ pose[:3, :3].T + pose[:3, 3]


class VoxelFusion:
    def __init__(self, voxel_size_m=0.02, max_voxels=2_000_000):
        if not np.isfinite(voxel_size_m) or voxel_size_m <= 0:
            raise ValueError("voxel size must be finite and positive")
        if type(max_voxels) is not int or max_voxels < 1:
            raise ValueError("max_voxels must be a positive integer")
        self.voxel_size_m, self.max_voxels = float(voxel_size_m), max_voxels
        self._cells = {}
        self.input_points = 0

    def add(self, points):
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError("points must be finite (N, 3)")
        if not len(points):
            return
        scaled = np.floor(points / self.voxel_size_m)
        if not np.isfinite(scaled).all() or np.any(np.abs(scaled) >= np.iinfo(np.int64).max):
            raise ValueError("voxel coordinates overflow int64")
        keys, inverse, counts = np.unique(scaled.astype(np.int64), axis=0, return_inverse=True, return_counts=True)
        sums = np.zeros((len(keys), 3))
        np.add.at(sums, inverse, points)
        entries = [tuple(key) for key in keys]
        if len(self._cells) + sum(key not in self._cells for key in entries) > self.max_voxels:
            raise AlignmentError("map_capacity_exceeded", "voxel limit exceeded; increase size/limit explicitly")
        for key, total, count in zip(entries, sums, counts):
            previous, n = self._cells.get(key, (np.zeros(3), 0))
            self._cells[key] = (previous + total, n + int(count))
        self.input_points += len(points)

    def cloud(self, min_observations=1):
        if type(min_observations) is not int or min_observations < 1:
            raise ValueError("min_observations must be a positive integer")
        values = [(total / count, count) for _, (total, count) in sorted(self._cells.items()) if count >= min_observations]
        return (np.asarray([v[0] for v in values], dtype=float).reshape(-1, 3),
                np.asarray([v[1] for v in values], dtype=np.int64))


def statistical_filter(points, *, neighbors=20, std_ratio=2.0):
    """Optional scipy k-NN filter, after voxel reduction; never silently enabled."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("points must be finite (N, 3)")
    if type(neighbors) is not int or neighbors < 1 or not np.isfinite(std_ratio) or std_ratio <= 0:
        raise ValueError("invalid statistical filter settings")
    if len(points) <= neighbors:
        raise ValueError("statistical filter needs more points than neighbors")
    from scipy.spatial import cKDTree

    distances, _ = cKDTree(points).query(points, k=neighbors + 1)
    means = distances[:, 1:].mean(axis=1)
    return means <= means.mean() + std_ratio * means.std()


def write_ply(path: Path, points):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("map must contain finite XYZ points")
    with Path(path).open("x", encoding="ascii", newline="\n") as stream:
        stream.write("ply\nformat ascii 1.0\ncomment units meters\n"
                     f"element vertex {len(points)}\nproperty double x\nproperty double y\nproperty double z\nend_header\n")
        np.savetxt(stream, points, fmt="%.12g")
