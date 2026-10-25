"""Missing-GT-pose policy: keyframes without a GT pose inside the unchanged 20 ms
tolerance are excluded from GT-dependent evaluation, identically for every
method, and recorded. They are never matched to a farther or interpolated pose."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.oracle import GT_POSE_POLICY, gt_pose_eligibility, load_oracle_inputs
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.evaluation.trajectory import read_tum_trajectory, trajectory_metrics
from rt_mapping.fusion import metric_pose
from rt_mapping.runs.artifacts import load_mapping_inputs
from rt_mapping.runs.comparison_run import DEFAULT_COMPARISON, run_comparison
from rt_mapping.runs.mapping_run import validate_config
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = DEFAULT_COMPARISON["max_timestamp_delta_s"]
METHODS = ("B0-shared-scale", "P1-global", "P1-raw", "B1-oracle", "P1-keyframes-2", "P1-keyframes-5")
# N-02 keyframe frame_id 195 and its neighbouring fr1/xyz GT poses (110 ms gap).
N02_STAMP, N02_GT_BEFORE, N02_GT_AFTER = 1305031108.876515, 1305031108.8357, 1305031108.9458


@pytest.fixture
def inputs(tmp_path):
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40, non_collinear=True, keyframes=6)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    return slam, geometry, sequence, manifest


def edit_gt(sequence, *, drop=(), shift=None):
    """Drop GT rows by keyframe index, or move one row to a new keyframe offset."""
    path = sequence / "groundtruth.txt"
    rows = np.loadtxt(path, ndmin=2)
    if shift is not None:
        index, offset_s = shift
        rows[index, 0] += offset_s - 0.001
    np.savetxt(path, np.delete(rows, list(drop), axis=0), fmt="%.12g")


def invoke(inputs, tmp_path, run_id="comparison"):
    return run_comparison(ROOT, *inputs, run_id=run_id, output_root=tmp_path / "runs")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def eligibility(stamps, gt):
    return gt_pose_eligibility(np.arange(len(stamps))+100, stamps, gt, TOLERANCE)[0]


def test_tolerance_stays_frozen_at_20_ms():
    assert TOLERANCE == 0.02


def test_match_just_inside_tolerance_is_eligible():
    summary = eligibility([1., 2.], [1.0199, 2.])
    assert summary["evaluated_frame_ids"] == [100, 101] and summary["excluded"] == []


def test_match_exactly_at_boundary_is_eligible_like_the_frozen_inclusive_association():
    summary = eligibility([1., 2.], [1.+TOLERANCE, 2.-TOLERANCE])
    assert summary["evaluated_keyframes"] == 2 and summary["coverage_fraction"] == 1.0


def test_n02_nearest_pose_at_40_8_ms_is_rejected_never_used():
    stamps, gt = [N02_STAMP-1., N02_STAMP], [N02_STAMP-1., N02_GT_BEFORE, N02_GT_AFTER]
    summary, matches = gt_pose_eligibility([180, 195], stamps, gt, TOLERANCE)
    assert matches.tolist() == [[0, 0]]
    assert summary["evaluated_frame_ids"] == [180] and summary["excluded_frame_ids"] == [195]
    [item] = summary["excluded"]
    assert item["reason"] == "no_gt_pose_within_tolerance" and item["timestamp_s"] == N02_STAMP
    assert item["nearest_gt_delta_s"] == pytest.approx(0.040815, abs=1e-6)
    assert summary["max_timestamp_delta_s"] == 0.02 and summary["policy"] == GT_POSE_POLICY


def test_pose_claimed_by_a_closer_keyframe_has_its_own_reason():
    summary = eligibility([1., 1.015], [1.001])
    assert summary["excluded"][0]["reason"] == "gt_pose_within_tolerance_assigned_to_closer_keyframe"


def test_coverage_fraction_and_deterministic_ordering_and_serialization():
    stamps, gt = [1., 1.1, 1.2, 1.3, 1.4], [1.001, 1.301]
    first, second = eligibility(stamps, gt), eligibility(stamps, gt)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["candidate_keyframes"] == 5 and first["evaluated_keyframes"] == 2 and first["excluded_keyframes"] == 3
    assert first["coverage_fraction"] == 0.4
    assert first["evaluated_frame_ids"] == [100, 103] and first["excluded_frame_ids"] == [101, 102, 104]
    assert [item["frame_id"] for item in first["excluded"]] == first["excluded_frame_ids"]


def test_strict_default_still_fails_and_exclusion_is_opt_in(inputs):
    edit_gt(inputs[2], drop=[2])
    loaded = load_mapping_inputs(inputs[0], inputs[1])
    mapping = validate_config({})
    with pytest.raises(ValueError, match="all retained keyframes need distinct associated GT poses"):
        load_oracle_inputs(loaded, inputs[2], inputs[3], mapping)
    oracle, _, gt_poses, gt_times, provenance = load_oracle_inputs(loaded, inputs[2], inputs[3], mapping,
                                                                   exclude_missing_gt_poses=True)
    assert len(gt_poses) == len(gt_times) == 5
    assert sorted(oracle) == [10, 27, 40, 52, 66, 79]  # GT depth needs no GT pose
    assert provenance["gt_pose_eligibility"]["excluded_frame_ids"] == [40]


def test_full_coverage_reproduces_the_strict_oracle_and_full_keyframe_metrics(inputs, tmp_path):
    loaded = load_mapping_inputs(inputs[0], inputs[1])
    mapping = validate_config({})
    strict = load_oracle_inputs(loaded, inputs[2], inputs[3], mapping)
    relaxed = load_oracle_inputs(loaded, inputs[2], inputs[3], mapping, exclude_missing_gt_poses=True)
    for a, b in zip(strict[1:4], relaxed[1:4]):
        assert np.array_equal(a, b)
    for frame_id, prediction in strict[0].items():
        assert np.array_equal(prediction.depth_m, relaxed[0][frame_id].depth_m, equal_nan=True)

    directory = invoke(inputs, tmp_path)
    assert load_run_manifest(directory / "run.json")["status"] == "ok"
    metrics = read(directory / "metrics.json")
    coverage = metrics["gt_pose_coverage"]
    assert coverage["coverage_fraction"] == 1.0 and coverage["excluded"] == [] and coverage["candidate_keyframes"] == 6
    cameras = loaded.snapshot.keyframes
    scale = read(directory / "methods/comparison.global/alignment.json")["scale"]
    poses = np.array([metric_pose(pose, scale) for pose in cameras["T_wc"]])
    # The pre-policy computation: every retained keyframe against its own GT rows.
    expected = trajectory_metrics(cameras["timestamp_s"], poses, strict[3], strict[2], alignment="se3")
    rows = {row["method"]: row for row in metrics["rows"]}
    assert rows["P1-global"]["ate_se3_rmse_m"] == expected["ate_rmse_m"]
    assert rows["P1-global"]["rpe_translation_rmse_m"] == expected["rpe_translation_rmse_m"]
    assert read(directory / "trajectory_evaluation.json")["P1_global_se3"] == expected
    assert "GT keyframes" in (directory / "report.md").read_text(encoding="utf-8")


def test_one_missing_keyframe_is_excluded_identically_for_every_method(inputs, tmp_path):
    edit_gt(inputs[2], drop=[2])
    before = [digest(path) for path in inputs[:3]]
    directory = invoke(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    assert before == [digest(path) for path in inputs[:3]]
    metrics = read(directory / "metrics.json")
    coverage = metrics["gt_pose_coverage"]
    assert coverage["evaluated_frame_ids"] == [10, 27, 52, 66, 79] and coverage["excluded_frame_ids"] == [40]
    assert coverage["coverage_fraction"] == 5/6 and coverage["max_timestamp_delta_s"] == 0.02
    [item] = coverage["excluded"]
    assert item == {"frame_id": 40, "timestamp_s": 1.2, "nearest_gt_delta_s": pytest.approx(0.099),
                    "reason": "no_gt_pose_within_tolerance"}
    assert read(directory / "inputs.json")["evaluation_only"]["gt_pose_eligibility"] == coverage
    trajectory = read(directory / "trajectory_evaluation.json")
    assert trajectory["gt_pose_coverage"] == coverage
    assert trajectory["P1_global_se3"]["matched_poses"] == trajectory["B0_sim3"]["matched_poses"] == 5
    for name in METHODS:
        detail = read(directory / "evaluation" / f"{name}.json")
        assert detail["gt_pose_coverage"]["evaluated_frame_ids"] == coverage["evaluated_frame_ids"]
        assert detail["trajectory"]["matched_poses"] == 5
    for row in metrics["rows"]:
        assert (row["gt_evaluated_keyframes"], row["gt_candidate_keyframes"]) == (5, 6)
    # Excluded keyframes stay in every fused map; only GT-dependent metrics drop them.
    for child in ("global", "raw", "oracle"):
        assert read(directory / f"methods/comparison.{child}/metrics.json")["fused_keyframes"] == 6
    report = (directory / "report.md").read_text(encoding="utf-8")
    assert "| 40 | 1.200000 | 0.099000 | no_gt_pose_within_tolerance |" in report
    assert "5/6" in report and "gt_coverage_fraction" in (directory / "comparison.csv").read_text(encoding="utf-8")


def test_excluded_metrics_equal_a_direct_evaluation_of_the_eligible_subset(inputs, tmp_path):
    edit_gt(inputs[2], shift=(3, 0.0408))  # keyframe 52: nearest GT pose now 40.8 ms away
    directory = invoke(inputs, tmp_path)
    assert load_run_manifest(directory / "run.json")["status"] == "ok"
    coverage = read(directory / "metrics.json")["gt_pose_coverage"]
    assert coverage["excluded_frame_ids"] == [52]
    assert coverage["excluded"][0]["nearest_gt_delta_s"] == pytest.approx(0.0408)
    cameras = load_mapping_inputs(inputs[0], inputs[1]).snapshot.keyframes
    keep = cameras["frame_id"] != 52
    stamps, gt_poses = read_tum_trajectory(inputs[2] / "groundtruth.txt")
    scale = read(directory / "methods/comparison.global/alignment.json")["scale"]
    poses = np.array([metric_pose(pose, scale) for pose in cameras["T_wc"][keep]])
    expected = trajectory_metrics(cameras["timestamp_s"][keep], poses, stamps, gt_poses)
    assert read(directory / "trajectory_evaluation.json")["P1_global_se3"] == expected


def test_multiple_missing_keyframes_are_all_reported_in_order(inputs, tmp_path):
    edit_gt(inputs[2], drop=[4, 1])
    directory = invoke(inputs, tmp_path)
    assert load_run_manifest(directory / "run.json")["status"] == "ok"
    coverage = read(directory / "metrics.json")["gt_pose_coverage"]
    assert coverage["excluded_frame_ids"] == [27, 66] and coverage["evaluated_keyframes"] == 4
    assert coverage["coverage_fraction"] == 4/6
    assert [item["timestamp_s"] for item in coverage["excluded"]] == [1.1, 1.4]


def test_too_few_eligible_keyframes_make_metrics_unavailable_not_fabricated(inputs, tmp_path):
    edit_gt(inputs[2], drop=[0, 2, 3, 5])
    directory = invoke(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "failed" and "insufficient_gt_coverage" in record["reason"]
    assert "[10, 40, 52, 79]" in record["reason"]
    assert read(directory / "inputs.json")["evaluation_only"]["gt_pose_eligibility"]["evaluated_frame_ids"] == [27, 66]
    assert not (directory / "metrics.json").exists() and not (directory / "trajectory_evaluation.json").exists()
    assert load_run_manifest(directory / "methods/comparison.global/run.json")["status"] == "ok"


def test_no_matched_keyframe_fails_explicitly(inputs, tmp_path):
    edit_gt(inputs[2], drop=[1, 2, 3, 4, 5], shift=(0, 10.))  # one GT pose, 10 s after the first keyframe
    directory = invoke(inputs, tmp_path)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "failed"
    assert "no retained keyframe has a GT pose within 0.02 s" in record["reason"]
    assert load_run_manifest(directory / "methods/comparison.global/run.json")["status"] == "ok"


def test_runtime_modules_do_not_load_gt_evaluation_code():
    runtime = ["rt_mapping.alignment", "rt_mapping.alignment.correspondences", "rt_mapping.fusion",
               "rt_mapping.runs.mapping_run", "rt_mapping.runs.geometry_run"]
    code = (f"import importlib, sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
            f"[importlib.import_module(n) for n in {runtime!r}]; "
            "bad = sorted(n for n in sys.modules if n in ('rt_mapping.evaluation.oracle', "
            "'rt_mapping.evaluation.trajectory', 'rt_mapping.runs.comparison_run')); print(','.join(bad))")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == ""
