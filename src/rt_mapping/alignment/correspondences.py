"""Join WP2 keyframe observations to C3 predictions without ground truth."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.geometry.intrinsics import crop_intrinsics, resize_intrinsics
from rt_mapping.slam.sparse import SparseSnapshot, validate_snapshot

from .estimators import AlignmentError


@dataclass(frozen=True)
class Correspondences:
    frame_id: np.ndarray
    point_id: np.ndarray
    source_depth: np.ndarray
    target_depth_m: np.ndarray
    normalized_pixels: np.ndarray
    rejected: dict

    def coverage_bins(self, selection=None, grid=4):
        xy = self.normalized_pixels if selection is None else self.normalized_pixels[selection]
        cells = np.clip(np.floor(xy * grid).astype(int), 0, grid - 1)
        return len(np.unique(cells, axis=0))


def prediction_grid(prediction, K_raw, raw_size):
    """Replay declared resize/crop steps and verify the processed calibration.

    A raw distorted image must never be silently treated as a pinhole image.
    DA3's existing adapter processes raw RGB without rectification. Other
    adapters must declare pixel_grid explicitly.
    """
    meta = prediction.preprocess
    grid = meta.get("pixel_grid")
    if grid is None and meta.get("library") == "depth_anything_3":
        grid = "raw_distorted"
    if grid not in ("raw_distorted", "undistorted"):
        raise AlignmentError("unsupported_preprocess", "prediction must declare its pixel grid")
    if meta.get("intrinsics_convention") != "pixel_centers_integer":
        raise AlignmentError("unsupported_preprocess", "integer pixel-centre convention required")
    size = tuple(int(v) for v in raw_size)
    if tuple(meta.get("input_wh", ())) != size:
        raise AlignmentError("unexpected_input", "prediction input size differs from keyframe")
    k = np.array(K_raw, dtype=float)
    transform = np.eye(3)
    for step in meta.get("steps", []):
        previous = k.copy()
        if step["op"] == "resize" and tuple(step["from_wh"]) == size:
            new_size = tuple(step["to_wh"])
            k = resize_intrinsics(k, size, new_size)
            size = new_size
        elif step["op"] == "crop":
            box = tuple(step["box"])
            k = crop_intrinsics(k, size, box)
            size = (box[2], box[3])
        else:
            raise AlignmentError("unsupported_preprocess", "only declared resize/crop steps are supported")
        transform = k @ np.linalg.inv(previous) @ transform
    if (tuple(meta.get("output_wh", ())) != size or prediction.depth_m.shape != (size[1], size[0])
            or not np.allclose(k, prediction.K_processed, rtol=1e-9, atol=1e-8)):
        raise AlignmentError("missing_intrinsics", "K_processed/shape does not match declared preprocessing")
    return transform, grid


def _sample(prediction, u, v, confidence_threshold):
    """Bilinear depth, rejecting invalid/low-confidence contributing pixels."""
    h, w = prediction.depth_m.shape
    if not (0 <= u < w - 1 and 0 <= v < h - 1):
        return None, "border"
    x, y = int(np.floor(u)), int(np.floor(v))
    if not prediction.valid_mask[y:y+2, x:x+2].all():
        return None, "invalid_depth"
    if confidence_threshold is not None:
        if prediction.confidence is None:
            raise AlignmentError("missing_confidence", "confidence filtering requested but model supplies none")
        if np.any(prediction.confidence[y:y+2, x:x+2] < confidence_threshold):
            return None, "low_confidence"
    a, b = u - x, v - y
    values = prediction.depth_m[y:y+2, x:x+2]
    return float(values[0, 0]*(1-a)*(1-b) + values[0, 1]*a*(1-b)
                 + values[1, 0]*(1-a)*b + values[1, 1]*a*b), None


def build_correspondences(snapshot: SparseSnapshot, predictions: dict[int, GeometryPrediction], *,
                          max_reprojection_error_px=3.0, confidence_threshold=None,
                          min_depth_m=0.1, max_depth_m=8.0, timestamp_tolerance_s=1e-6):
    validate_snapshot(snapshot)
    if (not np.isfinite([min_depth_m, max_depth_m, max_reprojection_error_px, timestamp_tolerance_s]).all()
            or not 0 < min_depth_m < max_depth_m or max_reprojection_error_px <= 0 or timestamp_tolerance_s < 0):
        raise ValueError("invalid correspondence thresholds")
    if confidence_threshold is not None and not np.isfinite(confidence_threshold):
        raise ValueError("confidence_threshold must be finite or None")
    cameras = snapshot.keyframes
    lookup, maps = {}, {}
    for index, frame_id in enumerate(cameras["frame_id"]):
        frame_id = int(frame_id)
        if frame_id not in predictions:
            raise AlignmentError("missing_prediction", f"no depth prediction for keyframe {frame_id}")
        prediction = predictions[frame_id]
        if prediction.frame_id != frame_id or abs(prediction.timestamp_s - cameras["timestamp_s"][index]) > timestamp_tolerance_s:
            raise AlignmentError("timestamp_mismatch", f"keyframe {frame_id} does not match prediction")
        if confidence_threshold is not None and prediction.confidence is None:
            raise AlignmentError("missing_confidence", f"keyframe {frame_id} has no confidence")
        maps[frame_id] = prediction_grid(prediction, cameras["K"][index], cameras["image_size_wh"][index])
        lookup[frame_id] = index
    frame_ids, point_ids, source, target, pixels = [], [], [], [], []
    rejected = Counter()
    for row in snapshot.observations:
        frame_id = row["frame_id"]
        if row["reprojection_error_px"] > max_reprojection_error_px:
            rejected["reprojection_error"] += 1
            continue
        transform, grid = maps[frame_id]
        u, v = (row["u"], row["v"]) if grid == "raw_distorted" else (row["u_undistorted"], row["v_undistorted"])
        mapped = transform @ [u, v, 1]
        depth, reason = _sample(predictions[frame_id], *(mapped[:2] / mapped[2]), confidence_threshold)
        if reason:
            rejected[reason] += 1
            continue
        if not min_depth_m <= depth <= max_depth_m:
            rejected["depth_range"] += 1
            continue
        width, height = cameras["image_size_wh"][lookup[frame_id]]
        frame_ids.append(frame_id)
        point_ids.append(row["point_id"])
        source.append(row["depth_slam"])
        target.append(depth)
        pixels.append([(u + 0.5) / width, (v + 0.5) / height])
    return Correspondences(np.asarray(frame_ids, dtype=np.int64), np.asarray(point_ids, dtype=np.int64),
                           np.asarray(source), np.asarray(target), np.asarray(pixels).reshape(-1, 2), dict(rejected))
