"""Optional causal sliding-window scale ablation; no future depths or GT.

Landmark validation membership is a fixed hash of ID and seed, so adding a
future landmark cannot change earlier calibration membership or estimates.
Insufficient startup support fails explicitly rather than using a future/global
scale as a hidden fallback.
"""
import hashlib

import numpy as np

from .estimators import AlignmentError, estimate_scale


def causal_window_scales(pairs, ordered_frame_ids, *, window_frames=3, seed=0,
                         validation_fraction=0.2, threshold_m=0.1, min_inliers=30,
                         min_ratio=0.5, min_coverage_bins=4):
    frame_ids = list(ordered_frame_ids)
    if (type(window_frames) is not int or window_frames < 1 or len(set(frame_ids)) != len(frame_ids)
            or type(seed) is not int or seed < 0 or not 0 < validation_fraction < 0.5):
        raise ValueError("invalid causal window settings")
    partition = {}
    for point_id in np.unique(pairs.point_id):
        number = int.from_bytes(hashlib.sha256(f"{seed}:{int(point_id)}".encode()).digest()[:8], "big") / 2**64
        partition[int(point_id)] = number < validation_fraction
    validation = np.array([partition[int(pid)] for pid in pairs.point_id])
    scales, diagnostics = {}, []
    for index, frame_id in enumerate(frame_ids):
        window = frame_ids[max(0, index-window_frames+1):index+1]
        active = np.isin(pairs.frame_id, window)
        training = active & ~validation
        check = active & validation
        result = estimate_scale(pairs.source_depth[training], pairs.target_depth_m[training],
                                threshold_m=threshold_m, min_inliers=min_inliers, min_ratio=min_ratio)
        residuals = np.abs(result.scale*pairs.source_depth-pairs.target_depth_m)
        if pairs.coverage_bins(training & (residuals <= threshold_m)) < min_coverage_bins:
            raise AlignmentError("insufficient_coverage", f"causal window ending at {frame_id} has low image coverage")
        if not check.any() or np.mean(residuals[check] <= threshold_m) < min_ratio or np.median(residuals[check]) > threshold_m:
            raise AlignmentError("validation_failed", f"causal window ending at {frame_id} has no acceptable withheld support")
        scales[int(frame_id)] = result.scale
        diagnostics.append({"frame_id": int(frame_id), "window_frame_ids": [int(i) for i in window],
            "scale": result.scale, "inliers": int(result.inliers.sum()), "withheld_pairs": int(check.sum()),
            "withheld_median_residual_m": float(np.median(residuals[check]))})
    return scales, diagnostics
