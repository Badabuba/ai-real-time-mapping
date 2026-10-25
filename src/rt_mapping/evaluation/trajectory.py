"""TUM pose association, SE(3)/Sim(3) ATE and fixed-pair RPE.

GT is an evaluation input only. Quaternions use x,y,z,w; poses are T_wc.
Association is greedy by timestamp distance, one-to-one, like the official
TUM tools. RPE delta is measured in matched pose rows, not input RGB frames.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from rt_mapping.geometry.projection import validate_pose


GT_MATCH_TOLERANCE_S = 0.02


class NoGroundTruthOverlap(ValueError):
    """No frame can be evaluated; retain structured coverage for diagnostics."""

    def __init__(self, coverage):
        self.coverage = coverage
        super().__init__(
            f"no_valid_gt_overlap: 0/{coverage['total_rgb_frames']} RGB frames have a distinct "
            f"GT timestamp within {coverage['max_timestamp_delta_s']:g} s")


def quaternion_rotation(quaternion):
    q = np.asarray(quaternion, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError("quaternion must be finite nonzero xyzw")
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def read_tum_trajectory(path: Path):
    rows = np.loadtxt(path, comments="#", ndmin=2)
    if rows.shape[1:] != (8,) or not len(rows) or not np.isfinite(rows).all() or np.any(np.diff(rows[:, 0]) <= 0):
        raise ValueError("trajectory needs finite strictly ordered timestamp tx ty tz qx qy qz qw")
    norms2 = np.sum(rows[:, 4:]**2, axis=1)
    if np.any(np.abs(norms2 - 1) > 5e-4):
        raise ValueError("GT quaternion exceeds documented TUM rounding tolerance")
    poses = np.repeat(np.eye(4)[None], len(rows), axis=0)
    poses[:, :3, 3] = rows[:, 1:4]
    poses[:, :3, :3] = [quaternion_rotation(q) for q in rows[:, 4:]]
    return rows[:, 0], poses


def associate_timestamps(source, target, max_delta_s=0.02):
    source, target = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if (source.ndim != 1 or target.ndim != 1 or not len(source) or not len(target)
            or not np.isfinite(source).all() or not np.isfinite(target).all()
            or np.any(np.diff(source) <= 0) or np.any(np.diff(target) <= 0)):
        raise ValueError("timestamps must be finite, nonempty and strictly increasing")
    if not np.isfinite(max_delta_s) or max_delta_s < 0:
        raise ValueError("timestamp tolerance must be finite and nonnegative")
    candidates = []
    for i, stamp in enumerate(source):
        lo = np.searchsorted(target, stamp - max_delta_s, side="left")
        hi = np.searchsorted(target, stamp + max_delta_s, side="right")
        candidates.extend((abs(stamp-target[j]), i, j) for j in range(lo, hi))
    used_source, used_target, matches = set(), set(), []
    for _, i, j in sorted(candidates):
        if i not in used_source and j not in used_target:
            matches.append((i, j))
            used_source.add(i)
            used_target.add(j)
    return np.asarray(sorted(matches), dtype=np.int64).reshape(-1, 2)


def gt_timestamp_coverage(frame_ids, timestamps_s, gt_timestamps_s, *, max_delta_s=GT_MATCH_TOLERANCE_S):
    """Report GT eligibility without filtering or modifying RGB inputs.

    Uses the existing greedy one-to-one, inclusive timestamp matcher unchanged.
    Nearest deltas explain exclusions only, never authorize farther matches.
    Empty GT returns zero coverage for explicit caller failure diagnostics.
    """
    ids = np.asarray(frame_ids)
    stamps, gt = np.asarray(timestamps_s, dtype=float), np.asarray(gt_timestamps_s, dtype=float)
    if (ids.shape != stamps.shape or ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer)
            or len(np.unique(ids)) != len(ids) or np.any(ids < 0)):
        raise ValueError("unique nonnegative integer frame IDs must align with timestamps")
    associate_timestamps(stamps, stamps, max_delta_s)  # validate even for empty GT
    if gt.ndim != 1:
        raise ValueError("GT timestamps must be a vector")
    matches = (associate_timestamps(stamps, gt, max_delta_s) if len(gt)
               else np.empty((0, 2), dtype=np.int64))
    matched = np.zeros(len(stamps), dtype=bool)
    matched[matches[:, 0]] = True
    excluded = []
    for i in np.flatnonzero(~matched):
        within = bool(len(gt) and np.any((gt >= stamps[i]-max_delta_s) & (gt <= stamps[i]+max_delta_s)))
        excluded.append({
            "frame_id": int(ids[i]), "timestamp_s": float(stamps[i]),
            "nearest_gt_delta_s": float(np.min(np.abs(gt-stamps[i]))) if len(gt) else None,
            "reason": ("gt_pose_within_tolerance_assigned_to_other_frame" if within
                       else "no_gt_pose_within_tolerance"),
        })
    return {
        "max_timestamp_delta_s": float(max_delta_s),
        "association": "greedy one-to-one by timestamp distance, inclusive tolerance; no interpolation",
        "total_rgb_frames": len(stamps), "matched_gt_frames": len(matches),
        "unmatched_gt_frames": len(excluded), "coverage_percent": 100.0 * len(matches) / len(stamps),
        "matched_frame_ids": [int(f) for f in ids[matched]],
        "excluded_frame_ids": [item["frame_id"] for item in excluded], "excluded": excluded,
        "exclusion_scope": "GT-dependent evaluation metrics only; retain every RGB input for SLAM",
    }, matches


def fit_trajectory_alignment(source_xyz, target_xyz, *, recover_scale):
    source, target = np.asarray(source_xyz, dtype=float), np.asarray(target_xyz, dtype=float)
    if source.ndim != 2 or source.shape[1:] != (3,) or source.shape != target.shape or len(source) < 3:
        raise ValueError("trajectory alignment requires at least three paired 3D centers")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError("trajectory centers must be finite")
    x, y = source-source.mean(axis=0), target-target.mean(axis=0)
    if np.linalg.matrix_rank(x) < 2 or np.linalg.matrix_rank(y) < 2:
        raise ValueError("trajectory alignment gauge is degenerate (collinear/static centers)")
    u, singular, vt = np.linalg.svd(y.T @ x / len(x))
    signs = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1
    rotation = (u * signs) @ vt
    scale = float(np.dot(singular, signs) / np.mean(np.sum(x*x, axis=1))) if recover_scale else 1.0
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("trajectory alignment returned invalid scale")
    translation = target.mean(axis=0) - scale * rotation @ source.mean(axis=0)
    return scale, rotation, translation


def trajectory_metrics(estimate_timestamps, estimate_poses, gt_timestamps, gt_poses, *,
                       alignment="se3", max_delta_s=0.02, rpe_delta=1):
    if alignment not in ("se3", "sim3"):
        raise ValueError("trajectory alignment must be se3 or sim3")
    if type(rpe_delta) is not int or rpe_delta < 1:
        raise ValueError("rpe_delta must be a positive integer")
    estimate, gt = np.asarray(estimate_poses, dtype=float), np.asarray(gt_poses, dtype=float)
    for poses, stamps in ((estimate, estimate_timestamps), (gt, gt_timestamps)):
        if poses.shape != (len(stamps), 4, 4):
            raise ValueError("poses must have shape (timestamps,4,4)")
        for pose in poses:
            validate_pose(pose)
    matches = associate_timestamps(estimate_timestamps, gt_timestamps, max_delta_s)
    if len(matches) < max(3, rpe_delta+1):
        raise ValueError("insufficient timestamp-associated poses for ATE/RPE")
    estimated, truth = estimate[matches[:, 0]].copy(), gt[matches[:, 1]]
    scale, rotation, translation = fit_trajectory_alignment(estimated[:, :3, 3], truth[:, :3, 3],
                                                            recover_scale=alignment == "sim3")
    centers = scale * estimated[:, :3, 3] @ rotation.T + translation
    residuals = np.linalg.norm(centers - truth[:, :3, 3], axis=1)
    # A left world-gauge transform cancels in relative poses. Scale translations
    # explicitly for the Sim(3)-aligned diagnostic, never rotations.
    estimated[:, :3, 3] *= scale
    translation_errors, rotation_errors = [], []
    for i in range(len(estimated)-rpe_delta):
        j = i+rpe_delta
        relative_est = np.linalg.inv(estimated[i]) @ estimated[j]
        relative_gt = np.linalg.inv(truth[i]) @ truth[j]
        error = np.linalg.inv(relative_gt) @ relative_est
        translation_errors.append(np.linalg.norm(error[:3, 3]))
        rotation_errors.append(np.degrees(np.arccos(np.clip((np.trace(error[:3, :3])-1)/2, -1, 1))))
    return {
        "alignment_mode": alignment, "matched_poses": len(matches), "input_poses": len(estimate),
        "max_timestamp_delta_s": float(max_delta_s),
        "association_max_actual_delta_s": float(np.max(np.abs(np.asarray(estimate_timestamps)[matches[:, 0]]
                                                               - np.asarray(gt_timestamps)[matches[:, 1]]))),
        "ate_rmse_m": float(np.sqrt(np.mean(residuals**2))), "ate_median_m": float(np.median(residuals)),
        "rpe_translation_rmse_m": float(np.sqrt(np.mean(np.square(translation_errors)))),
        "rpe_rotation_rmse_deg": float(np.sqrt(np.mean(np.square(rotation_errors)))),
        "rpe_pairs": len(translation_errors), "rpe_delta": rpe_delta, "rpe_delta_unit": "matched_pose_rows",
        "evaluation_transform": {"scale": scale, "R": rotation.tolist(), "t": translation.tolist(),
                                 "direction": "reference_world = scale * R @ estimate_world + t"},
        "scale_fitted_for_evaluation": alignment == "sim3",
    }
