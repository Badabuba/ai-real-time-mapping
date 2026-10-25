"""Explicit B1/evaluation-only access to TUM GT depth and world poses.

No function in this module is called by the proposed-method scale estimator.
The B1 control reuses P1's recovered camera scale; GT never fits that scale.
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


def load_oracle_inputs(inputs, sequence_dir, manifest_path, config, *, max_timestamp_delta_s=0.02):
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
    matches = associate_timestamps(cameras["timestamp_s"], stamps, max_timestamp_delta_s)
    if len(matches) != len(cameras["frame_id"]):
        raise ValueError("all retained keyframes need distinct associated GT poses for a shared comparison")
    gt_by_camera = np.empty_like(cameras["T_wc"])
    gt_stamps = np.empty(len(cameras["frame_id"]))
    for ci, gi in matches:
        gt_by_camera[ci] = gt_poses[gi]
        gt_stamps[ci] = stamps[gi]
    predictions = {}
    provenance = {"manifest_sha256": sha256_file(manifest_path),
                  "groundtruth_sha256": sha256_file(sequence_dir / "groundtruth.txt"), "depth_sha256": {},
                  "depth_units": "PNG/5000; dataset depth correction is already applied by TUM",
                  "reference_geometry": "shared calibrated RGB K and Brown coefficients, matching the frozen pipeline",
                  "reference_limitation": "registered depth rectification is approximate; TUM recommends ROS-default K for direct depth clouds",
                  "format_reference": "https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats"}
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
        reference.add(depth_points(oracle, gt_by_camera[ci], distortion=cameras["distortion"][ci],
                                   min_depth_m=config["min_depth_m"], max_depth_m=config["max_depth_m"],
                                   pixel_stride=config["pixel_stride"]))
        provenance["depth_sha256"][item["depth_path"]] = sha256_file(depth_path)
    points, _ = reference.cloud()
    if not len(points):
        raise ValueError("evaluation reference cloud is empty")
    return predictions, points, gt_by_camera, gt_stamps, provenance
