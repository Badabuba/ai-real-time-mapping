"""Explicit B1/evaluation-only access to TUM GT depth and world poses.

No function in this module is called by the proposed-method scale estimator.
The B1 control reuses P1's recovered camera scale; GT never fits that scale.

A retained keyframe without a GT pose inside the unchanged association
tolerance is unavailable for GT evaluation, not an invalid SLAM/depth frame.
It is never interpolated or matched to a farther pose; callers either fail
(default) or exclude it explicitly and record it (``exclude_missing_gt_poses``).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rt_mapping.alignment.correspondences import prediction_grid
from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.depth import resize_depth_nearest
from rt_mapping.evaluation.trajectory import associate_timestamps, read_tum_trajectory
from rt_mapping.evaluation.tum_depth import load_tum_depth_m
from rt_mapping.fusion import VoxelFusion, depth_points


GT_POSE_POLICY = "exclude_keyframes_without_gt_pose_within_tolerance"


def gt_pose_eligibility(frame_ids, timestamps_s, gt_timestamps_s, max_timestamp_delta_s):
    """Which retained keyframes have a distinct GT pose within the tolerance.

    Uses the frozen one-to-one association unchanged (inclusive boundary).
    Excluded keyframes are listed in keyframe timestamp order with the nearest
    GT delta for diagnosis only; that pose is never used.
    """
    frame_ids = np.asarray(frame_ids, dtype=np.int64)
    stamps, gt = np.asarray(timestamps_s, dtype=float), np.asarray(gt_timestamps_s, dtype=float)
    if frame_ids.shape != stamps.shape:
        raise ValueError("keyframe IDs and timestamps must align")
    matches = associate_timestamps(stamps, gt, max_timestamp_delta_s)
    matched = np.zeros(len(stamps), dtype=bool)
    matched[matches[:, 0]] = True
    excluded = []
    for i in np.flatnonzero(~matched):
        within = np.any((gt >= stamps[i]-max_timestamp_delta_s) & (gt <= stamps[i]+max_timestamp_delta_s))
        excluded.append({"frame_id": int(frame_ids[i]), "timestamp_s": float(stamps[i]),
                         "nearest_gt_delta_s": float(np.min(np.abs(gt-stamps[i]))),
                         "reason": ("gt_pose_within_tolerance_assigned_to_closer_keyframe" if within
                                    else "no_gt_pose_within_tolerance")})
    summary = {"policy": GT_POSE_POLICY, "max_timestamp_delta_s": float(max_timestamp_delta_s),
               "association": "one-to-one nearest timestamp, inclusive tolerance; no interpolation, no farther pose",
               "candidate_keyframes": len(stamps), "evaluated_keyframes": len(matches),
               "excluded_keyframes": len(excluded), "coverage_fraction": len(matches)/len(stamps),
               "evaluated_frame_ids": [int(f) for f in frame_ids[matched]],
               "excluded_frame_ids": [item["frame_id"] for item in excluded], "excluded": excluded}
    return summary, matches


def load_oracle_inputs(inputs, sequence_dir, manifest_path, config, *, max_timestamp_delta_s=0.02,
                       exclude_missing_gt_poses=False):
    sequence_dir, manifest_path = Path(sequence_dir), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = inputs.slam["dataset"]
    if (manifest["sequence_id"] != dataset["sequence"] or manifest["dataset"] != dataset["name"]
            or manifest["source"]["archive_sha256"] != dataset["checksum"]):
        raise ValueError("evaluation dataset does not match source run provenance")
    for name, entry in manifest.get("index_files", {}).items():
        path = (sequence_dir / name).resolve()
        if not path.is_relative_to(sequence_dir.resolve()) or sha256_file(path) != entry["sha256"]:
            raise ValueError("evaluation dataset index checksum mismatch")
    entries = {int(item["frame_id"]): item for item in manifest["splits"][dataset["split"]]["frames"]}
    cameras = inputs.snapshot.keyframes
    stamps, gt_poses = read_tum_trajectory(sequence_dir / "groundtruth.txt")
    eligibility, matches = gt_pose_eligibility(cameras["frame_id"], cameras["timestamp_s"], stamps,
                                               max_timestamp_delta_s)
    if eligibility["excluded_keyframes"] and not exclude_missing_gt_poses:
        raise ValueError("all retained keyframes need distinct associated GT poses for a shared comparison")
    if not eligibility["evaluated_keyframes"]:
        raise ValueError(f"no retained keyframe has a GT pose within {max_timestamp_delta_s} s; "
                         "GT evaluation is unavailable")
    # Rows follow the eligible keyframes in keyframe order; with full coverage
    # this is every keyframe, exactly as before the exclusion policy.
    gt_by_camera, gt_stamps = gt_poses[matches[:, 1]], stamps[matches[:, 1]]
    gt_row = {int(ci): row for row, ci in enumerate(matches[:, 0])}
    predictions = {}
    provenance = {"manifest_sha256": sha256_file(manifest_path),
                  "groundtruth_sha256": sha256_file(sequence_dir / "groundtruth.txt"), "depth_sha256": {},
                  "depth_units": "PNG/5000; dataset depth correction is already applied by TUM",
                  "reference_geometry": "shared calibrated RGB K and Brown coefficients, matching the frozen pipeline",
                  "reference_limitation": "registered depth rectification is approximate; TUM recommends ROS-default K for direct depth clouds",
                  "format_reference": "https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats",
                  "gt_pose_eligibility": eligibility}
    reference = VoxelFusion(config["voxel_size_m"], config["max_voxels"])
    for ci, frame_id in enumerate(cameras["frame_id"]):
        item = entries[int(frame_id)]
        source = inputs.predictions[int(frame_id)]
        if abs(item["rgb_timestamp_s"] - source.timestamp_s) > 1e-6:
            raise ValueError("GT manifest RGB timestamp differs from source prediction")
        depth_path = (sequence_dir / item["depth_path"]).resolve()
        if not depth_path.is_relative_to(sequence_dir.resolve()):
            raise ValueError("GT depth path outside evaluation dataset")
        depth = load_tum_depth_m(sequence_dir, item["depth_path"])
        if depth.shape != (int(cameras["image_size_wh"][ci, 1]), int(cameras["image_size_wh"][ci, 0])):
            raise ValueError("GT depth raw shape differs from shared RGB calibration")
        _, grid = prediction_grid(source, cameras["K"][ci], cameras["image_size_wh"][ci])
        if grid != "raw_distorted":
            raise ValueError("TUM oracle comparison requires raw-grid predictions; GT rectification is not implicit")
        for step in source.preprocess.get("steps", []):
            if step["op"] == "resize":
                depth = resize_depth_nearest(depth, tuple(step["to_wh"]))
            elif step["op"] == "crop":
                left, top, width, height = step["box"]
                depth = depth[top:top+height, left:left+width]
            else:
                raise ValueError("unsupported GT-to-prediction grid transform")
        valid = np.isfinite(depth) & (depth > 0)
        depth = depth.astype(np.float32)
        depth[~valid] = np.nan
        oracle = GeometryPrediction(frame_id=int(frame_id), timestamp_s=source.timestamp_s,
                   depth_m=depth, valid_mask=valid, confidence=None, K_processed=source.K_processed,
                   model_id="oracle/TUM-RGBD-depth", preprocess=source.preprocess, inference_ms=0.)
        predictions[int(frame_id)] = oracle
        # GT depth needs no GT pose, so B1 keeps every retained keyframe like P1;
        # only the GT-posed reference cloud is restricted to eligible keyframes.
        if ci in gt_row:
            reference.add(depth_points(oracle, gt_by_camera[gt_row[ci]], distortion=cameras["distortion"][ci],
                                       min_depth_m=config["min_depth_m"], max_depth_m=config["max_depth_m"],
                                       pixel_stride=config["pixel_stride"]))
        provenance["depth_sha256"][item["depth_path"]] = sha256_file(depth_path)
    points, _ = reference.cloud()
    if not len(points):
        raise ValueError("evaluation reference cloud is empty")
    return predictions, points, gt_by_camera, gt_stamps, provenance
