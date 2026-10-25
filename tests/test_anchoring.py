"""U-02 sparse anchoring and pre-registered frame gate on the synthetic fixture (CPU only, no backends, no GT)."""
import copy
import csv
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from rt_mapping.alignment import anchoring
from rt_mapping.alignment.anchoring import (anchored_prediction, gate_decision, load_config, run_anchor_gate,
                                            validate_config)
from rt_mapping.alignment.frame_signals import ANCHOR_BAND, NO_TRACKING_REASON
from rt_mapping.contracts.geometry import load_prediction, save_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs.comparison_run import DEFAULT_COMPARISON, run_comparison
from rt_mapping.runs.mapping_run import DEFAULT_CONFIG
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/robust_fusion.json"
EVALUATION_ONLY = ("reference_evaluation_only.npz", "trajectory_evaluation.json", "evaluation")


def _rewrite(geometry, frame_id, change):
    path = geometry / f"predictions/frame_{frame_id:06d}.npz"
    prediction = load_prediction(path)
    depth = prediction.depth_m.copy()
    change(depth)
    path.unlink()
    save_prediction(dataclasses.replace(prediction, depth_m=depth), path)


def build(tmp_path, mutate=None):
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a" * 40, non_collinear=True)
    if mutate:
        mutate(geometry)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    comparison = run_comparison(ROOT, slam, geometry, sequence, manifest, run_id="comparison",
                                output_root=tmp_path / "runs")
    assert load_run_manifest(comparison / "run.json")["status"] == "ok"
    return comparison, slam, geometry


def gate(sources, tmp_path, run_id="gate", config=CONFIG):
    return run_anchor_gate(ROOT, *sources, config, run_id=run_id, output_root=tmp_path / "out")


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return {int(r["frame_id"]): r for r in csv.DictReader(stream)}


def ok(directory):
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    return record


def digest(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(directory).rglob("*")) if p.is_file()}


@pytest.fixture
def sources(tmp_path):
    return build(tmp_path)


@pytest.fixture
def config():
    return load_config(CONFIG)[0]


def valid_signal(**change):
    row = {"anchor_ratio": 1.02, "anchor_reason": None, "n_withheld_pairs": 12,
           "withheld_median_abs_residual_m": 0.03, "coverage_bins_4x4": 9, "tracking_state": None,
           "tracking_reason": NO_TRACKING_REASON}
    row.update(change)
    return row


def test_committed_config_holds_the_pre_registered_merged_defaults(config):
    values = anchoring.gate_values(config)
    assert values == {"residual_threshold_m": DEFAULT_CONFIG["residual_threshold_m"],
                      "min_anchor_inliers": DEFAULT_CONFIG["min_inliers"],
                      "min_anchor_inlier_ratio": DEFAULT_CONFIG["min_inlier_ratio"],
                      "min_coverage_bins": DEFAULT_CONFIG["min_coverage_bins"], "min_withheld_pairs": 1,
                      "anchor_band": ANCHOR_BAND, "tracking_ok_state": "OK"}
    assert values == {"residual_threshold_m": 0.1, "min_anchor_inliers": 30, "min_anchor_inlier_ratio": 0.5,
                      "min_coverage_bins": 4, "min_withheld_pairs": 1, "anchor_band": 1.25, "tracking_ok_state": "OK"}
    assert config["map_evaluation"]["thresholds_m"]["value"] == DEFAULT_COMPARISON["thresholds_m"] == [0.02, 0.05, 0.1]
    assert config["map_evaluation"]["voxel_size_m"]["value"] == DEFAULT_CONFIG["voxel_size_m"] == 0.02
    assert [v["name"] for v in config["variants"]] == ["P1-global-control", "P1-anchored", "P1-anchored+gate"]


@pytest.mark.parametrize("path", [(), ("gate",), ("gate", "anchor_band"), ("map_evaluation",), ("inputs",)])
def test_unknown_or_missing_config_keys_are_rejected(config, path):
    unknown, missing = copy.deepcopy(config), copy.deepcopy(config)
    target = unknown
    for key in path:
        target = target[key]
    target["surprise"] = 1
    with pytest.raises(ValueError, match="keys differ"):
        validate_config(unknown)
    target = missing
    for key in path:
        target = target[key]
    del target[sorted(target)[0]]
    with pytest.raises(ValueError, match="keys differ"):
        validate_config(missing)


@pytest.mark.parametrize("key,value", [("residual_threshold_m", 0.0), ("residual_threshold_m", float("nan")),
                                       ("min_anchor_inliers", 30.0), ("min_anchor_inliers", True),
                                       ("min_anchor_inlier_ratio", 1.5), ("min_coverage_bins", 17),
                                       ("min_withheld_pairs", 0), ("anchor_band", 1.0), ("anchor_band", float("inf")),
                                       ("tracking_ok_state", "FINE")])
def test_invalid_config_values_are_rejected(config, key, value):
    config["gate"][key]["value"] = value
    with pytest.raises(ValueError):
        validate_config(config)


def test_valid_frame_is_accepted_with_every_flag_clear_or_unavailable(config):
    decision = gate_decision(valid_signal(), config)
    assert decision["decision"] == "accept" and decision["accepted"] and decision["flags"] == ()
    assert decision["flag_states"] == {"A1": False, "A2": False, "A3": False, "A4": False, "S1": None}
    assert decision["reason"] == f"accept: no flag fired; unavailable: S1 ({NO_TRACKING_REASON})"
    known = gate_decision(valid_signal(tracking_state="OK", tracking_reason=None), config)
    assert known["flag_states"]["S1"] is False and known["reason"] == "accept: no flag fired"


@pytest.mark.parametrize("change,flag", [
    ({"anchor_ratio": None, "anchor_reason": "insufficient_correspondences: too few depth pairs"}, "A1"),
    ({"anchor_ratio": 1.26}, "A2"),
    ({"anchor_ratio": 1 / 1.26}, "A2"),
    ({"withheld_median_abs_residual_m": 0.1000001}, "A3"),
    ({"coverage_bins_4x4": 3}, "A4"),
    ({"tracking_state": "LOST", "tracking_reason": None}, "S1"),
    ({"tracking_state": "NOT_INITIALIZED", "tracking_reason": None}, "S1"),
])
def test_each_flag_alone_rejects_the_frame(config, change, flag):
    decision = gate_decision(valid_signal(**change), config)
    assert decision["decision"] == "reject" and not decision["accepted"]
    assert decision["flags"] == (flag,)
    assert decision["reason"].startswith(f"reject: {flag} ")


@pytest.mark.parametrize("change", [{"anchor_ratio": 1.25}, {"anchor_ratio": 1 / 1.25}, {"anchor_ratio": 0.80001},
                                    {"withheld_median_abs_residual_m": 0.1}, {"coverage_bins_4x4": 4}])
def test_pre_registered_boundaries_do_not_fire(config, change):
    assert gate_decision(valid_signal(**change), config)["decision"] == "accept"


def test_simultaneous_flags_are_all_recorded_in_order(config):
    decision = gate_decision(valid_signal(anchor_ratio=None, anchor_reason="invalid_scale: x",
                                          withheld_median_abs_residual_m=0.4, coverage_bins_4x4=1,
                                          tracking_state="LOST", tracking_reason=None), config)
    assert decision["flags"] == ("A1", "A3", "A4", "S1")
    assert decision["flag_states"]["A2"] is None
    reason = decision["reason"]
    assert reason.index("A1 ") < reason.index("A3 ") < reason.index("A4 ") < reason.index("S1 ")
    assert "unavailable: A2 needs an anchor ratio" in reason
    both = gate_decision(valid_signal(anchor_ratio=2.0, withheld_median_abs_residual_m=0.2), config)
    assert both["flags"] == ("A2", "A3")


def test_a3_is_unavailable_without_withheld_pairs(config):
    decision = gate_decision(valid_signal(n_withheld_pairs=0, withheld_median_abs_residual_m=None), config)
    assert decision["decision"] == "accept" and decision["flag_states"]["A3"] is None
    assert "A3 needs >= 1 withheld pair(s), frame has 0" in decision["reason"]


@pytest.mark.parametrize("change", [
    {"anchor_ratio": float("nan")}, {"anchor_ratio": float("inf")}, {"anchor_ratio": 0.0}, {"anchor_ratio": -1.1},
    {"anchor_ratio": True}, {"anchor_ratio": "1.0"},
    {"anchor_ratio": None, "anchor_reason": None},
    {"withheld_median_abs_residual_m": float("nan")}, {"withheld_median_abs_residual_m": -0.01},
    {"withheld_median_abs_residual_m": None},
    {"n_withheld_pairs": 0}, {"n_withheld_pairs": -1}, {"n_withheld_pairs": 2.0},
    {"coverage_bins_4x4": 17}, {"coverage_bins_4x4": -1}, {"coverage_bins_4x4": 4.0},
    {"tracking_state": "FINE", "tracking_reason": None}, {"tracking_state": None, "tracking_reason": ""},
])
def test_malformed_decision_inputs_are_refused_not_defaulted(config, change):
    with pytest.raises(ValueError):
        gate_decision(valid_signal(**change), config)


def test_anchored_prediction_is_a_scaled_copy_and_leaves_the_input_untouched(sources):
    path = sources[2] / "predictions/frame_000027.npz"
    before = path.read_bytes()
    prediction = load_prediction(path)
    original = prediction.depth_m.copy()
    anchored = anchored_prediction(prediction, 0.8)
    assert anchored is not prediction
    np.testing.assert_array_equal(anchored.depth_m, (original.astype(np.float64) * 0.8).astype(np.float32))
    assert anchored.depth_m.dtype == np.float32
    for field in ("valid_mask", "K_processed"):
        np.testing.assert_array_equal(getattr(anchored, field), getattr(prediction, field))
    assert (anchored.confidence, anchored.frame_id, anchored.model_id, anchored.preprocess) == \
        (prediction.confidence, prediction.frame_id, prediction.model_id, prediction.preprocess)
    np.testing.assert_array_equal(prediction.depth_m, original)
    assert path.read_bytes() == before
    np.testing.assert_array_equal(anchored_prediction(prediction, 1.0).depth_m, original)
    assert anchored_prediction(prediction, None) is prediction


@pytest.mark.parametrize("ratio", [float("nan"), float("inf"), -float("inf"), 0.0, -0.5, True, "2"])
def test_anchored_prediction_refuses_invalid_ratios(sources, ratio):
    prediction = load_prediction(sources[2] / "predictions/frame_000027.npz")
    with pytest.raises(ValueError):
        anchored_prediction(prediction, ratio)


def test_clean_fixture_accepts_every_frame_without_correction_effect(sources, tmp_path):
    directory = gate(sources, tmp_path)
    record = ok(directory)
    assert record["method"] == "P1-global" and record["config"]["robust_fusion_sha256"] == load_config(CONFIG)[1]
    assert set(record["artifacts"]) == {"frame_signals", "anchor_gate", "summary"}
    by_frame = rows(directory / "anchor_gate.csv")
    assert sorted(by_frame) == [10, 27, 40]
    for row in by_frame.values():
        assert row["decision"] == "accept" and row["flags"] == "" and row["anchor_applied"] == "true"
        assert abs(float(row["applied_scale"]) - 1) < 1e-6
        assert row["flag_S1"] == "unavailable" and NO_TRACKING_REASON in row["decision_reason"]
    summary = json.loads((directory / "anchor_gate.json").read_text(encoding="utf-8"))
    assert summary["accepted"] == 3 and summary["rejected"] == 0 and not summary["all_frames_rejected"]
    assert summary["flag_counts"]["S1"] == {"fired": 0, "clear": 0, "unavailable": 3}
    assert summary["config_sha256"] == hashlib.sha256(CONFIG.read_bytes()).hexdigest()


def test_known_per_frame_bias_is_recovered_and_flagged(tmp_path):
    """A x1.2 depth bias on frame 27 gives a_f = 1/1.2 (|log| = 0.182 < log 1.25 = 0.223, so A2 stays clear);
    the ~0.6 m withheld residual fires A3, and since U-01 coverage counts calibration inliers under the global
    scale, almost no pair of the biased frame survives and A4 fires too. Float32 depth limits the recovery to
    ~1e-6 relative."""
    directory = gate(build(tmp_path, lambda g: _rewrite(g, 27, lambda d: d.__imul__(np.float32(1.2)))), tmp_path)
    ok(directory)
    by_frame = rows(directory / "anchor_gate.csv")
    biased = by_frame[27]
    assert abs(float(biased["anchor_ratio"]) - 1 / 1.2) < 1e-6
    assert biased["flag_A2"] == "false" and biased["flag_A3"] == "true" and biased["flags"] == "A3;A4"
    assert biased["decision"] == "reject" and biased["decision_reason"].startswith("reject: A3 withheld")
    assert float(biased["withheld_median_abs_residual_before_m"]) > 0.4
    assert float(biased["withheld_median_abs_residual_after_m"]) < 1e-5
    assert by_frame[10]["decision"] == by_frame[40]["decision"] == "accept"
    summary = json.loads((directory / "anchor_gate.json").read_text(encoding="utf-8"))
    assert summary["rejected"] == 1 and summary["flag_counts"]["A3"]["fired"] == 1
    assert [d["decision"] for d in summary["decisions"]] == ["accept", "reject", "accept"]


def test_insufficient_sparse_support_leaves_the_frame_uncorrected_and_rejected(tmp_path):
    """Per-pixel depth noise of +-50% (~1.5 m at 3 m) leaves far fewer than half the pairs within 0.10 m."""
    noise = np.random.default_rng(0).uniform(0.5, 1.5, size=(30, 40)).astype(np.float32)
    directory = gate(build(tmp_path, lambda g: _rewrite(g, 40, lambda d: d.__imul__(noise))), tmp_path)
    ok(directory)
    row = rows(directory / "anchor_gate.csv")[40]
    assert row["anchor_ratio"] == "" and row["anchor_applied"] == "false" and row["applied_scale"] == "1.0"
    assert row["anchor_reason"] and row["flag_A1"] == "true" and row["flag_A2"] == "unavailable"
    assert row["flags"].split(";")[0] == "A1" and len(row["flags"].split(";")) >= 2
    assert row["withheld_median_abs_residual_after_m"] == row["withheld_median_abs_residual_before_m"]
    assert row["decision"] == "reject" and row["anchor_reason"] in row["decision_reason"]


def test_config_differing_from_the_recorded_mapping_is_refused_without_a_run_directory(sources, tmp_path, config):
    config["gate"]["residual_threshold_m"]["value"] = 0.2
    path = tmp_path / "other.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="residual_threshold_m=0.2"):
        gate(sources, tmp_path, config=path)
    assert not (tmp_path / "out" / "gate").exists()


def test_unknown_config_key_in_a_file_is_refused_without_a_run_directory(sources, tmp_path, config):
    config["gate"]["min_depth_ratio"] = {"value": 0.5, "source": "unplanned"}
    path = tmp_path / "other.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown \\['min_depth_ratio'\\]"):
        gate(sources, tmp_path, config=path)
    assert not (tmp_path / "out" / "gate").exists()


def test_provenance_mismatch_is_refused_without_a_run_directory(sources, tmp_path):
    path = sources[0] / "inputs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pipeline"]["geometry_run_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        gate(sources, tmp_path)
    assert not (tmp_path / "out" / "gate").exists()


def test_rerun_is_byte_identical_and_never_overwrites(sources, tmp_path):
    first, second = gate(sources, tmp_path, "gate_a"), gate(sources, tmp_path, "gate_b")
    for name in ("frame_signals.csv", "anchor_gate.csv", "anchor_gate.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        gate(sources, tmp_path, "gate_a")


def test_decisions_need_no_ground_truth_and_inputs_stay_unchanged(sources, tmp_path):
    """The existing global path is untouched: every source file is byte-identical afterwards, and deleting
    all GT/evaluation-only material does not change a single decision byte."""
    comparison, slam, geometry = sources
    before = {str(p): digest(p) for p in sources}
    with_gt = gate(sources, tmp_path, "with_gt")
    assert {str(p): digest(p) for p in sources} == before
    shutil.rmtree(tmp_path / "evaluation")
    for name in EVALUATION_ONLY:
        target = comparison / name
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    without_gt = gate(sources, tmp_path, "without_gt")
    ok(without_gt)
    for name in ("frame_signals.csv", "anchor_gate.csv", "anchor_gate.json"):
        assert (with_gt / name).read_bytes() == (without_gt / name).read_bytes()


def test_cli_runs_without_loading_evaluation_modules(sources, tmp_path):
    comparison, slam, geometry = sources
    script = str(ROOT / "scripts/run_anchor_gate.py")
    code = (f"import runpy, sys\nsys.argv = [{script!r}, *sys.argv[1:]]\n"
            "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit as exit:\n    status = exit.code\n"
            "loaded = sorted(n for n in sys.modules if n.startswith('rt_mapping.evaluation'))\n"
            "assert not loaded, loaded\nsys.exit(status)\n")
    argv = ["--comparison-run", str(comparison), "--slam-run", str(slam), "--geometry-run", str(geometry),
            "--run-id", "cli", "--output-root", str(tmp_path / "out")]
    run = lambda: subprocess.run([sys.executable, "-c", code, *argv], capture_output=True, text=True, timeout=120)
    done = run()
    assert done.returncode == 0, done.stdout + done.stderr
    ok(tmp_path / "out" / "cli")
    again = run()
    assert again.returncode == 2 and "never overwritten" in again.stderr
