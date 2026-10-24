"""Actual synthetic NPZ/CSV handoff -> scale -> map; failure and provenance tests."""
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from rt_mapping.alignment.correspondences import build_correspondences, prediction_grid
from rt_mapping.contracts.geometry import load_prediction, save_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.mapping_run import run_mapping, validate_config
from rt_mapping.runs.synthetic_mapping import KNOWN_SCALE, create_synthetic_inputs
from rt_mapping.slam.sparse import SparseSnapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    return create_synthetic_inputs(tmp_path / "inputs", git_commit="a" * 40)


def hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def run(inputs, tmp_path, **kwargs):
    return run_mapping(ROOT, *inputs, run_id="mapping", output_root=tmp_path / "runs", **kwargs)


def read_snapshot(inputs):
    sparse = inputs[0] / "sparse"
    with np.load(sparse / "landmarks.npz", allow_pickle=False) as data:
        landmarks = dict(data)
    with np.load(sparse / "keyframes.npz", allow_pickle=False) as data:
        cameras = dict(data)
    ints = {"frame_id", "keyframe_id", "point_id", "keypoint_index"}
    with (sparse / "observations.csv").open(newline="") as stream:
        rows = [{k: int(v) if k in ints else float(v) for k, v in r.items()} for r in csv.DictReader(stream)]
    predictions = {int(frame_id): load_prediction(inputs[1] / f"predictions/frame_{frame_id:06d}.npz")
                   for frame_id in cameras["frame_id"]}
    return SparseSnapshot(landmarks, cameras, rows, {}), predictions


def test_synthetic_artifact_pipeline_recovers_scale_fuses_plane_preserves_inputs(inputs, tmp_path):
    before = [hashes(p) for p in inputs]
    directory = run(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    assert record["method"] == "P1-global"
    alignment = json.loads((directory / "alignment.json").read_text())
    assert alignment["scale"] == pytest.approx(KNOWN_SCALE, abs=1e-4)
    assert alignment["calibration_coverage_bins_4x4"] >= 4
    assert alignment["withheld_inlier_ratio"] > 0.8
    with np.load(directory / "map.npz", allow_pickle=False) as cloud:
        assert cloud["xyz_m"].shape[0] > 300
        # Most reconstructed world points lie on the known 3 m plane.
        assert np.mean(np.abs(cloud["xyz_m"][:, 2] - 3.) < 1e-4) > 0.9
    provenance = json.loads((directory / "inputs.json").read_text())
    assert len(provenance["predictions"]) == 3
    assert before == [hashes(p) for p in inputs]
    with (directory / "residuals.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    calibration_ids = {r["point_id"] for r in rows if r["withheld"] == "False"}
    withheld_ids = {r["point_id"] for r in rows if r["withheld"] == "True"}
    assert calibration_ids and withheld_ids and not calibration_ids & withheld_ids
    metrics = json.loads((directory / "metrics.json").read_text())
    assert metrics["ground_truth_evaluation"] == "not performed"
    assert metrics["real_time_claim"] is False
    trajectory = list(csv.DictReader((directory / "trajectory_metric.csv").open()))
    assert [int(r["frame_id"]) for r in trajectory] == [10, 27, 40]
    assert float(trajectory[1]["tx"]) == pytest.approx(0.035 * KNOWN_SCALE, abs=1e-5)


def test_output_run_never_overwritten(inputs, tmp_path):
    directory = run(inputs, tmp_path)
    before = hashes(directory)
    with pytest.raises(FileExistsError):
        run(inputs, tmp_path)
    assert before == hashes(directory)


def test_missing_keyframe_prediction_is_failed_not_partial_success(inputs, tmp_path):
    (inputs[1] / "predictions/frame_000040.npz").unlink()
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed"
    assert "missing_prediction" in record["reason"]


def test_corrupt_sparse_artifact_is_detected(inputs, tmp_path):
    with (inputs[0] / "sparse/observations.csv").open("a") as stream:
        stream.write("corrupt\n")
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "checksum" in record["reason"]


def test_dataset_mismatch_rejected_before_output_creation(inputs, tmp_path):
    # Deliberately corrupt a synthetic input manifest to test validation.
    path = inputs[1] / "run.json"
    value = json.loads(path.read_text())
    value["dataset"]["sequence"] = "different"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="same frozen dataset"):
        run(inputs, tmp_path)
    assert not (tmp_path / "runs").exists()


def test_timestamp_mismatch_and_missing_confidence_fail(inputs, tmp_path):
    path = inputs[1] / "predictions/frame_000010.npz"
    save_prediction(replace(load_prediction(path), timestamp_s=7.), path)
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "timestamp_mismatch" in record["reason"]


def test_confidence_ablation_requires_real_model_confidence(inputs, tmp_path):
    record = load_run_manifest(run(inputs, tmp_path, config={"confidence_threshold": 0.5}) / "run.json")
    assert record["status"] == "failed" and "missing_confidence" in record["reason"]


def test_coverage_gate_rejects_concentrated_observations(inputs, tmp_path, monkeypatch):
    original = build_correspondences
    def concentrated(*args, **kwargs):
        pairs = original(*args, **kwargs)
        return replace(pairs, normalized_pixels=np.full_like(pairs.normalized_pixels, 0.4))
    monkeypatch.setattr("rt_mapping.runs.mapping_run.build_correspondences", concentrated)
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "insufficient_coverage" in record["reason"]


def test_capacity_failure_leaves_terminal_manifest(inputs, tmp_path):
    record = load_run_manifest(run(inputs, tmp_path, config={"max_voxels": 1}) / "run.json")
    assert record["status"] == "failed" and "map_capacity_exceeded" in record["reason"]
    assert "alignment" in record["artifacts"]


def test_validation_rejects_bias_exclusive_to_withheld_landmarks(inputs, tmp_path, monkeypatch):
    original = build_correspondences
    def biased_validation(*args, **kwargs):
        pairs = original(*args, **kwargs)
        ids = np.unique(pairs.point_id)
        withheld = np.random.default_rng(0).permutation(ids)[:int(np.ceil(len(ids) * 0.2))]
        target = pairs.target_depth_m.copy()
        target[np.isin(pairs.point_id, withheld)] *= 1.8
        return replace(pairs, target_depth_m=target)
    monkeypatch.setattr("rt_mapping.runs.mapping_run.build_correspondences", biased_validation)
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "validation_failed" in record["reason"]


def test_optional_plots_are_saved_and_recorded(inputs, tmp_path):
    pytest.importorskip("matplotlib")
    directory = run(inputs, tmp_path, config={"plot": True})
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    for key in ("residual_plot", "visualization"):
        assert (directory / record["artifacts"][key]).read_bytes().startswith(b"\x89PNG")


def test_model_provenance_mismatch_fails(inputs, tmp_path):
    path = inputs[1] / "predictions/frame_000010.npz"
    save_prediction(replace(load_prediction(path), model_id="wrong/model@revision"), path)
    record = load_run_manifest(run(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "model_mismatch" in record["reason"]


def test_empty_map_after_filtering_is_failed(inputs, tmp_path):
    record = load_run_manifest(run(inputs, tmp_path, config={"min_voxel_observations": 100000}) / "run.json")
    assert record["status"] == "failed" and "empty_map" in record["reason"]


def test_keyboard_interrupt_leaves_failed_manifest(inputs, tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr("rt_mapping.runs.mapping_run.build_correspondences", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(inputs, tmp_path)
    record = load_run_manifest(tmp_path / "runs/mapping/run.json")
    assert record["status"] == "failed" and "interrupted" in record["reason"]


def test_processed_grid_replays_resize_and_rejects_stale_intrinsics(inputs):
    snapshot, predictions = read_snapshot(inputs)
    pred = predictions[10]
    matrix, grid = prediction_grid(pred, snapshot.keyframes["K"][0], [80, 60])
    np.testing.assert_allclose(matrix @ [10, 20, 1], [4.75, 9.75, 1])
    assert grid == "raw_distorted"
    with pytest.raises(ValueError, match="missing_intrinsics"):
        prediction_grid(replace(pred, K_processed=snapshot.keyframes["K"][0]), snapshot.keyframes["K"][0], [80, 60])


def test_unsupported_pixel_grid_rejected(inputs):
    snapshot, predictions = read_snapshot(inputs)
    pred = predictions[10]
    predictions[10] = replace(pred, preprocess={**pred.preprocess, "pixel_grid": "guess"})
    with pytest.raises(ValueError, match="unsupported_preprocess"):
        build_correspondences(snapshot, predictions)


def test_invalid_bilinear_depth_is_filtered(inputs):
    snapshot, predictions = read_snapshot(inputs)
    pred = predictions[10]
    depth, valid = pred.depth_m.copy(), pred.valid_mask.copy()
    depth[0:10, 0:10] = np.nan
    valid[0:10, 0:10] = False
    predictions[10] = replace(pred, depth_m=depth, valid_mask=valid)
    pairs = build_correspondences(snapshot, predictions)
    assert pairs.rejected["invalid_depth"] > 0
    assert np.isfinite(pairs.target_depth_m).all()


@pytest.mark.parametrize("config", [{"unknown": 1}, {"min_inliers": True}, {"seed": -1},
    {"residual_threshold_m": 0}, {"validation_fraction": 0.5}, {"confidence_threshold": float("nan")},
    {"min_coverage_bins": 17}, {"max_depth_m": 0.01}, {"plot": "yes"}])
def test_invalid_config_rejected(config):
    with pytest.raises(ValueError):
        validate_config(config)
