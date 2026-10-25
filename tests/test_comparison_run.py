import hashlib
import json
from pathlib import Path

import pytest

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs.comparison_run import comparison_config, run_comparison
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40, non_collinear=True)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    return slam, geometry, sequence, manifest


def invoke(inputs, tmp_path, config=None):
    return run_comparison(ROOT, *inputs, run_id="comparison", config=config, output_root=tmp_path / "runs")


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def test_complete_comparison_has_oracle_controls_fscore_csv_and_honest_timing(inputs, tmp_path):
    before = [digest(p) for p in inputs[:3]]
    directory = invoke(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    result = json.loads((directory / "metrics.json").read_text())
    rows = {r["method"]: r for r in result["rows"]}
    assert set(rows) == {"B0-shared-scale", "P1-global", "P1-raw", "B1-oracle", "P1-keyframes-2", "P1-keyframes-5"}
    assert rows["P1-global"]["chamfer_l1_m"] < rows["P1-raw"]["chamfer_l1_m"]
    assert rows["B1-oracle"]["chamfer_l1_m"] < rows["P1-global"]["chamfer_l1_m"]
    assert rows["B0-shared-scale"]["completeness_mean_m"] > rows["P1-global"]["completeness_mean_m"]
    assert "fscore_0.05m" in (directory / "comparison.csv").read_text()
    assert result["real_time_claim"] is False
    assert any("model_supplies_no_confidence" in item["reason"] for item in result["skipped_ablations"])
    assert "SYNTHETIC" in (directory / "report.md").read_text()
    oracle_record = load_run_manifest(directory / "methods/comparison.oracle/run.json")
    assert oracle_record["method"] == "B1" and oracle_record["model"] is None
    assert oracle_record["config"]["scale_source"] == "recorded P1-global calibration"
    assert before == [digest(p) for p in inputs[:3]]


def test_missing_gt_cannot_change_finished_proposed_map(inputs, tmp_path):
    (inputs[2] / "groundtruth.txt").unlink()
    directory = invoke(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "failed"
    global_run = directory / "methods/comparison.global"
    assert load_run_manifest(global_run / "run.json")["status"] == "ok"
    assert (global_run / "map.npz").exists()


def test_wrong_gt_dataset_fails_instead_of_comparing_unrelated_reference(inputs, tmp_path):
    value = json.loads(inputs[3].read_text())
    value["source"]["archive_sha256"] = "b"*64
    inputs[3].write_text(json.dumps(value))
    record = load_run_manifest(invoke(inputs, tmp_path) / "run.json")
    assert record["status"] == "failed" and "provenance" in record["reason"]


def test_existing_comparison_never_overwritten(inputs, tmp_path):
    directory = invoke(inputs, tmp_path)
    before = digest(directory)
    with pytest.raises(FileExistsError):
        invoke(inputs, tmp_path)
    assert before == digest(directory)


def test_opt_in_causal_window_comparison_records_per_frame_scale(inputs, tmp_path):
    directory = invoke(inputs, tmp_path, {"causal_window_frames": 2, "keyframe_intervals": []})
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    window = load_run_manifest(directory / "methods/comparison.window/run.json")
    assert window["method"] == "P1-window"
    assert window["config"]["scale_source"] == "causal past/current window"
    assert set(window["config"]["scale"]) == {"10", "27", "40"}
    diagnostics = json.loads((directory / "causal_scales.json").read_text())
    assert diagnostics["future_depth_used"] is False and diagnostics["ground_truth_used"] is False


@pytest.mark.parametrize("config", [{"bad": 1}, {"keyframe_intervals": [0]}, {"thresholds_m": [0]},
    {"confidence_thresholds": [float("nan")]}, {"crop_bounds_m": [[0,0,0],[0,0,0]]}])
def test_bad_comparison_config_rejected(config):
    with pytest.raises(ValueError):
        comparison_config(config)
