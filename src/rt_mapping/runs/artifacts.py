"""Verified, backend-free inputs shared by mapping comparisons."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rt_mapping.alignment.correspondences import prediction_grid
from rt_mapping.contracts.geometry import load_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.slam.sparse import SparseSnapshot, load_sparse_snapshot


def artifact_path(run_dir, record, key):
    root = Path(run_dir).resolve()
    path = (root / record["artifacts"][key]).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"artifact {key} resolves outside input run")
    return path


@dataclass
class MappingInputs:
    slam: dict
    geometry: dict
    snapshot: SparseSnapshot
    predictions: dict
    provenance: dict


def load_mapping_inputs(slam_run, geometry_run):
    slam_run, geometry_run = Path(slam_run), Path(geometry_run)
    slam, geometry = load_run_manifest(slam_run / "run.json"), load_run_manifest(geometry_run / "run.json")
    if slam["status"] != "ok" or geometry["status"] != "ok" or slam["method"] != "B0" or geometry["method"] != "model-spike":
        raise ValueError("comparison requires completed B0/model-spike source runs")
    if slam["dataset"] != geometry["dataset"] or slam["slam"]["pose_convention"] != "T_wc":
        raise ValueError("source dataset/split/checksum or T_wc convention mismatch")
    export_path = artifact_path(slam_run, slam, "sparse_export")
    snapshot = load_sparse_snapshot(export_path.parent)
    directory = artifact_path(geometry_run, geometry, "predictions")
    predictions = {}
    provenance = {"slam_run_sha256": sha256_file(slam_run / "run.json"),
                  "geometry_run_sha256": sha256_file(geometry_run / "run.json"),
                  "sparse_export_sha256": sha256_file(export_path),
                  "sparse_sha256": snapshot.metadata["sha256"], "predictions": {}}
    for i, frame_id in enumerate(snapshot.keyframes["frame_id"]):
        path = directory / f"frame_{frame_id:06d}.npz"
        if not path.resolve().is_relative_to(geometry_run.resolve()):
            raise ValueError("prediction resolves outside source run")
        prediction = load_prediction(path)
        if prediction.frame_id != int(frame_id) or abs(prediction.timestamp_s - snapshot.keyframes["timestamp_s"][i]) > 1e-6:
            raise ValueError("source prediction frame/timestamp mismatch")
        if prediction.model_id != f"{geometry['model']['repo']}@{geometry['model']['revision']}":
            raise ValueError("source prediction model differs from run manifest")
        prediction_grid(prediction, snapshot.keyframes["K"][i], snapshot.keyframes["image_size_wh"][i])
        predictions[int(frame_id)] = prediction
        provenance["predictions"][path.name] = sha256_file(path)
    return MappingInputs(slam, geometry, snapshot, predictions, provenance)
