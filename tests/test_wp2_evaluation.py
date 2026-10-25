"""Y-02: recorded gauges, immutable source runs and scoped resource evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from rt_mapping.contracts.run_manifest import build_run_manifest, load_run_manifest, write_run_manifest
from rt_mapping.evaluation.slam_run import evaluate_slam_run, measure_process, measure_slam_run, rss_bytes
from rt_mapping.evaluation.trajectory import trajectory_metrics
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs
from rt_mapping.slam.sparse import load_sparse_snapshot

ROOT = Path(__file__).resolve().parents[1]


def digest(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def tum(path, times, xyz):
    np.savetxt(path, np.column_stack((times, xyz, np.tile([0, 0, 0, 1], (len(times), 1)))), fmt="%.17g")


@pytest.fixture
def source(tmp_path):
    directory = tmp_path / "b0"
    (directory / "input_setup/trajectory").mkdir(parents=True)
    times = 10 + np.arange(6) * 0.1
    xyz = np.array([[0,0,0], [1,0,0], [1,1,0], [1,1,1], [2,1,1], [2,2,1]], dtype=float)
    tum(directory / "input_setup/trajectory/trajectory_final.txt", times, xyz)
    prep = {"frames": [{"frame_id": i, "rgb_timestamp_s": float(t)} for i, t in enumerate(times)]}
    (directory / "input_setup/setup.json").write_text(json.dumps(prep))
    record = build_run_manifest(
        run_id="b0", git_commit="a"*40, dirty_worktree=False,
        dataset={"name": "synthetic", "sequence": "noncollinear", "split": "smoke", "checksum": "b"*64, "manifest": None},
        method="B0", model=None, alignment=None,
        slam={"repo": "synthetic/slam", "revision": "a"*40, "config": "synthetic.json", "pose_convention": "T_wc"},
        config={"frames": 6}, hardware={"gpu": None, "cpu": "synthetic", "ram_gb": None},
        environment={"python": "fixture"}, seed=0, started_at="2026-10-25T00:00:00Z", status="ok", reason=None,
        artifacts={"preparation": "input_setup/setup.json", "trajectory": "input_setup/trajectory/trajectory_final.txt"},
    )
    write_run_manifest(record, directory)
    gt = tmp_path / "groundtruth.txt"
    tum(gt, times, 3 * xyz + [4, -2, 1])
    return directory, gt, times, xyz


def invoke(source, tmp_path, **kwargs):
    return evaluate_slam_run(ROOT, source[0], source[1], run_id="evaluation", output_root=tmp_path / "runs", **kwargs)


def test_exact_sim3_is_evaluation_only_and_source_is_immutable(source, tmp_path):
    before = digest(source[0])
    directory = invoke(source, tmp_path)
    record = load_run_manifest(directory / "run.json")
    metrics = json.loads((directory / "metrics.json").read_text())
    final = metrics["final_trajectory"]
    assert record["status"] == "degraded" and record["method"] == "B0"
    assert record["alignment"] is None and record["model"] is None
    assert final["metrics"]["ate_rmse_m"] < 1e-12
    assert final["metrics"]["rpe_translation_rmse_m"] < 1e-12
    assert final["metrics"]["evaluation_transform"]["scale"] == pytest.approx(3)
    assert final["coverage"]["pose_fraction"] == 1
    assert metrics["tracking_success"] is None and metrics["real_time_claim"] is False
    assert metrics["resources"]["value"] is None
    assert metrics["retained_keyframes"]["metrics"] is None
    assert before == digest(source[0])
    after = digest(directory)
    with pytest.raises(FileExistsError):
        invoke(source, tmp_path)
    assert after == digest(directory)


def test_noisy_final_pose_errors_are_measured(source, tmp_path):
    xyz = source[3].copy()
    xyz[3] += [0.1, -0.05, 0.02]
    tum(source[0] / "input_setup/trajectory/trajectory_final.txt", source[2], xyz)
    result = json.loads((invoke(source, tmp_path) / "metrics.json").read_text())["final_trajectory"]["metrics"]
    assert result["ate_rmse_m"] > 0.01
    assert result["rpe_translation_rmse_m"] > 0.01


def test_partial_pose_coverage_is_not_tracking_success(source, tmp_path):
    tum(source[0] / "input_setup/trajectory/trajectory_final.txt", source[2][2:], source[3][2:])
    final = json.loads((invoke(source, tmp_path) / "metrics.json").read_text())["final_trajectory"]
    assert final["coverage"]["pose_fraction"] == pytest.approx(4/6)
    assert final["coverage"]["tracking_success"] is None


def test_no_gt_matches_fail_explicitly_before_output(source, tmp_path):
    tum(source[1], source[2] + 100, source[3])
    with pytest.raises(ValueError, match="no_valid_gt_overlap") as error:
        invoke(source, tmp_path)
    assert error.value.coverage["unmatched_gt_frames"] == 6
    assert error.value.coverage["excluded_frame_ids"] == list(range(6))
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("tolerance", [0.019, 0.020001, 0.03])
def test_recorded_wp2_evaluation_keeps_frozen_20_ms_tolerance(source, tmp_path, tolerance):
    with pytest.raises(ValueError, match="frozen at exactly 0.02"):
        invoke(source, tmp_path, max_delta_s=tolerance)
    assert not (tmp_path / "runs").exists()


def test_evaluation_cli_reports_coverage_and_fails_on_zero_overlap(source, tmp_path):
    tum(source[1], source[2]+100, source[3])
    done = subprocess.run([
        sys.executable, str(ROOT / "scripts/evaluate_wp2_run.py"), "--source-run", str(source[0]),
        "--groundtruth", str(source[1]), "--run-id", "no_overlap", "--output-root", str(tmp_path / "runs"),
    ], capture_output=True, text=True, timeout=30)
    assert done.returncode == 2
    report = json.loads(done.stderr)
    assert report["status"] == "failed" and "no_valid_gt_overlap" in report["reason"]
    assert report["gt_coverage"]["total_rgb_frames"] == 6
    assert report["gt_coverage"]["excluded_frame_ids"] == list(range(6))
    assert not (tmp_path / "runs").exists()


def test_collinear_gauge_is_null_with_reason(source, tmp_path):
    tum(source[0] / "input_setup/trajectory/trajectory_final.txt", source[2], np.tile(np.arange(6)[:,None], (1,3)))
    final = json.loads((invoke(source, tmp_path) / "metrics.json").read_text())["final_trajectory"]
    assert final["metrics"] is None and "degenerate" in final["reason"]


def test_off_grid_final_pose_rejected_before_output(source, tmp_path):
    tum(source[0] / "input_setup/trajectory/trajectory_final.txt", source[2] + 1, source[3])
    with pytest.raises(ValueError, match="frozen input grid"):
        invoke(source, tmp_path)
    assert not (tmp_path / "runs").exists()


def test_retained_keyframe_row_matches_comparison_b0_semantics(tmp_path):
    slam, _ = create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40, non_collinear=True)
    snapshot = load_sparse_snapshot(slam / "sparse")
    cameras = snapshot.keyframes
    # Build a new fixture run rather than modifying its finished manifest.
    directory = tmp_path / "retained"
    directory.mkdir()
    import shutil
    shutil.copytree(slam / "sparse", directory / "sparse")
    # Preserve strict timestamp order around the sparse IDs.
    times = np.interp(np.arange(41), [0, 10, 27, 40], [0.9, 1., 1.1, 1.2])
    (directory / "setup.json").write_text(json.dumps({"frames": [
        {"frame_id": i, "rgb_timestamp_s": float(t)} for i, t in enumerate(times)]}))
    tum(directory / "final.txt", cameras["timestamp_s"], cameras["T_wc"][:, :3, 3])
    record = load_run_manifest(slam / "run.json")
    record.update(run_id="retained", config={"frames": 41}, artifacts={
        "preparation": "setup.json", "trajectory": "final.txt", "keyframes": "sparse/keyframes.npz"})
    write_run_manifest(record, directory)
    gt = tmp_path / "gt.txt"
    tum(gt, cameras["timestamp_s"], cameras["T_wc"][:, :3, 3] * 2.5)
    output = evaluate_slam_run(ROOT, directory, gt, run_id="evaluation", output_root=tmp_path / "runs")
    from rt_mapping.evaluation.trajectory import read_tum_trajectory
    gt_times, gt_poses = read_tum_trajectory(gt)
    expected = trajectory_metrics(cameras["timestamp_s"], cameras["T_wc"], gt_times, gt_poses, alignment="sim3")
    retained = json.loads((output / "metrics.json").read_text())["retained_keyframes"]
    assert retained["metrics"] == expected
    assert retained["coverage"]["pose_fraction"] == pytest.approx(3/41)


def test_resource_report_must_match_exact_source_hash(source, tmp_path):
    path = tmp_path / "resources.json"
    report = {"schema": "rt_mapping.slam_resources/v1", "source_run_id": "b0", "source_run_sha256": "0"*64}
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="exact source"):
        invoke(source, tmp_path, resources=path)
    report["source_run_sha256"] = hashlib.sha256((source[0] / "run.json").read_bytes()).hexdigest()
    path.write_text(json.dumps(report))
    output = invoke(source, tmp_path, resources=path)
    assert json.loads((output / "metrics.json").read_text())["resources"] == report


@pytest.mark.parametrize("system,expected", [("Darwin", 123), ("Linux", 123*1024), ("Other", None)])
def test_rss_platform_units(system, expected):
    assert rss_bytes(123, system) == expected
    assert rss_bytes(0, system) is None


def test_measurement_uses_fresh_child_rusage_not_cumulative_difference(monkeypatch, tmp_path):
    resource = pytest.importorskip("resource")
    values = iter([SimpleNamespace(ru_maxrss=0, ru_utime=0, ru_stime=0), SimpleNamespace(ru_maxrss=2048)])
    monkeypatch.setattr(resource, "getrusage", lambda _: next(values))
    monkeypatch.setattr("rt_mapping.evaluation.slam_run.platform.system", lambda: "Linux")
    report = measure_process([sys.executable, "-c", "pass"], cwd=tmp_path)
    assert report["exit_code"] == 0 and report["wall_clock_s"] > 0
    assert report["peak_rss_bytes"] == 2048*1024
    assert report["cold_start_s"] is None


def test_prior_child_usage_is_not_misattributed(monkeypatch, tmp_path):
    resource = pytest.importorskip("resource")
    monkeypatch.setattr(resource, "getrusage", lambda _: SimpleNamespace(ru_maxrss=99, ru_utime=1, ru_stime=1))
    report = measure_process([sys.executable, "-c", "raise SystemExit(7)"], cwd=tmp_path)
    assert report["exit_code"] == 7
    assert report["peak_rss_bytes"] is None and "prior" in report["peak_rss_reason"]


def test_failed_launch_has_no_fabricated_rss(tmp_path):
    report = measure_process([str(tmp_path / "missing-python")], cwd=tmp_path)
    assert report["exit_code"] is None and report["launch_error"]


def test_wrapper_preserves_preflight_failure_and_refuses_overwrite(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/run_wp2_pyslam.py").write_text("raise SystemExit(2)\n")
    report_path = measure_slam_run(root, sys.executable, root, sys.executable, run_id="failed")
    report = json.loads(report_path.read_text())
    assert report["status"] == "failed" and report["exit_code"] == 2
    assert report["effective_fps"] is None and report["source_run_sha256"] is None
    with pytest.raises(ValueError, match="already exists"):
        measure_slam_run(root, sys.executable, root, sys.executable, run_id="failed")


def test_module_import_does_not_load_native_or_model_frameworks():
    code = f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); import rt_mapping.evaluation.slam_run; print([m for m in ('cv2','torch','pyslam','psutil') if m in sys.modules])"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"

# Y-03 exercises native-state semantics and causal poses, not final pose counts.
from rt_mapping.contracts.slam import SlamFrame
from rt_mapping.evaluation.slam_run import evaluate_tracking
from rt_mapping.slam.tracking_log import TrackingLog
from rt_mapping.evaluation.trajectory import read_tum_trajectory


def causal_rows(source, states=None):
    states = states or ["OK"] * len(source[2])
    result = []
    for i, (time, xyz, state) in enumerate(zip(source[2], source[3], states)):
        pose = np.eye(4)
        pose[:3, 3] = xyz
        result.append(SlamFrame(i, float(time), state,
                                "unobservable" if state == "UNKNOWN" else None,
                                pose if state == "OK" else None,
                                None if state == "OK" else f"tracking_state:{state}",
                                (), None, float((i+1)*10)))
    return result


def tracking_result(source, rows=None, **kwargs):
    gt_times, gt_poses = read_tum_trajectory(source[1])
    return evaluate_tracking(rows if rows is not None else causal_rows(source), gt_times, gt_poses, **kwargs)


def attach_tracking(source, rows):
    """New fixture run: never rewrite the original terminal manifest."""
    import shutil
    old = source[0]
    target = old.parent / "with_tracking"
    shutil.copytree(old, target, ignore=shutil.ignore_patterns("run.json"))
    prep = json.loads((target / "input_setup/setup.json").read_text())
    log = TrackingLog(target, prep["frames"])
    for row in rows:
        log.append(row)
    log.finish()
    record = load_run_manifest(old / "run.json")
    record.update(run_id=target.name)
    record["artifacts"].update(trajectory_all="trajectory_all.csv", tracking_timing="timing.csv",
                               tracking_export="tracking_export.json")
    write_run_manifest(record, target)
    return (target, *source[1:])


@pytest.mark.parametrize("keep", [[2, 3, 4, 5], [0, 1, 3, 4, 5]])
def test_partial_gt_excludes_only_geometric_metrics_and_reports_every_input(source, tmp_path, keep):
    tum(source[1], source[2][keep], 3*source[3][keep]+[4, -2, 1])
    excluded = sorted(set(range(6))-set(keep))
    bad_xyz = source[3].copy()
    bad_xyz[excluded] = [999, -999, 999]  # must not affect the GT alignment/errors
    tum(source[0] / "input_setup/trajectory/trajectory_final.txt", source[2], bad_xyz)
    with_tracking = (source[0], source[1], source[2], bad_xyz)
    with_tracking = attach_tracking(with_tracking, causal_rows(with_tracking))
    before = digest(with_tracking[0])
    gt_before = source[1].read_bytes()
    metrics = json.loads((invoke(with_tracking, tmp_path) / "metrics.json").read_text())
    coverage = metrics["gt_coverage"]
    assert coverage["total_rgb_frames"] == 6
    assert coverage["matched_gt_frames"] == len(keep)
    assert coverage["unmatched_gt_frames"] == len(excluded)
    assert coverage["coverage_percent"] == pytest.approx(100*len(keep)/6)
    assert coverage["excluded_frame_ids"] == excluded
    assert {item["reason"] for item in coverage["excluded"]} == {"no_gt_pose_within_tolerance"}
    final = metrics["final_trajectory"]
    assert final["coverage"]["pose_count"] == 6
    assert final["coverage"]["gt_coverage"]["excluded_frame_ids"] == excluded
    assert final["metrics"]["matched_poses"] == len(keep)
    assert final["metrics"]["ate_rmse_m"] < 1e-12
    tracking = metrics["tracking"]
    assert tracking["tracking_success"] == 1
    assert tracking["input_frames"] == tracking["tracking_latency"]["summary"]["n_total"] == 6
    assert tracking["online_trajectory"]["metrics"]["matched_poses"] == len(keep)
    assert tracking["online_trajectory"]["metrics"]["ate_rmse_m"] < 1e-12
    assert tracking["gap_aware_rpe"]["metrics"]["rpe_translation_rmse_m"] < 1e-12
    assert before == digest(with_tracking[0]) and source[1].read_bytes() == gt_before


def test_gap_free_causal_metrics_match_existing_evaluator_and_warmup_policy(source):
    result = tracking_result(source, warmup=1)
    assert result["tracking_success"] == 1
    assert result["success_numerator"] == 6 and result["input_frames"] == 6
    assert result["gap_aware_rpe"]["candidate_pairs"] == 5
    assert result["gap_aware_rpe"]["excluded_gap_pairs"] == 0
    gt_times, gt_poses = read_tum_trajectory(source[1])
    rows = causal_rows(source)
    expected = trajectory_metrics(source[2], np.array([r.T_wc for r in rows]), gt_times, gt_poses, alignment="sim3")
    for key in ("rpe_translation_rmse_m", "rpe_rotation_rmse_deg", "rpe_pairs"):
        assert result["gap_aware_rpe"]["metrics"][key] == pytest.approx(expected[key])
    assert all(not k.startswith("rpe_") for k in result["online_trajectory"]["metrics"])
    latency = result["tracking_latency"]["summary"]
    assert latency["cold_start_ms"] == 10
    assert latency["n_warm"] == 5 and latency["warm_p50_ms"] == 40
    assert latency["warm_p95_ms"] == pytest.approx(58)
    assert result["tracking_latency"]["mapping_ms"] is None


def test_rpe_does_not_bridge_lost_inputs_and_uses_one_global_scale(source):
    rows = causal_rows(source, ["OK", "OK", "LOST", "OK", "LOST", "OK"])
    result = tracking_result(source, rows)
    gap = result["gap_aware_rpe"]
    assert gap["eligible_frame_id_pairs"] == [[0, 1]]
    assert gap["excluded_frame_id_pairs"] == [[1, 3], [3, 5]]
    assert gap["metrics"]["rpe_pairs"] == 1
    assert gap["metrics"]["rpe_translation_rmse_m"] < 1e-12
    assert result["online_trajectory"]["metrics"]["evaluation_transform"]["scale"] == pytest.approx(3)
    assert result["tracking_success"] == pytest.approx(4/6)
    assert [(s["first_frame_id"], s["last_frame_id"]) for s in result["non_ok_segments"]] == [(2,2), (4,4)]


def test_rpe_delta_checks_all_intervening_inputs_not_only_endpoints(source):
    result = tracking_result(source, causal_rows(source, ["OK", "OK", "LOST", "OK", "OK", "OK"]), rpe_delta=2)
    gap = result["gap_aware_rpe"]
    assert gap["eligible_frame_id_pairs"] == [[3, 5]]
    assert gap["excluded_frame_id_pairs"] == [[0, 3], [1, 4]]


def test_all_lost_has_zero_success_but_undefined_geometry_not_zero_error(source):
    result = tracking_result(source, causal_rows(source, ["LOST"]*6))
    assert result["tracking_success"] == 0
    assert result["online_trajectory"]["metrics"] is None
    assert result["gap_aware_rpe"]["metrics"] is None
    assert "no usable" in result["gap_aware_rpe"]["reason"]
    assert result["non_ok_segments"][0]["frame_count"] == 6
    assert result["tracking_latency"]["summary"]["n_total"] == 6


def test_unknown_states_are_not_imputed_as_failures_or_successes(source):
    result = tracking_result(source, causal_rows(source, ["OK", "OK", "UNKNOWN", "OK", "OK", "OK"]))
    assert result["tracking_success"] is None
    assert "UNKNOWN" in result["tracking_success_reason"]
    assert result["observed_ok_fraction"] == pytest.approx(5/6)
    assert [1, 3] in result["gap_aware_rpe"]["excluded_frame_id_pairs"]


def test_missing_ok_pose_and_track_exception_also_break_pairs(source):
    from dataclasses import replace
    rows = causal_rows(source)
    rows[2] = replace(rows[2], T_wc=None, pose_reason="unobservable")
    rows[4] = replace(rows[4], T_wc=None, pose_reason="track_raised:RuntimeError", error="track_raised:RuntimeError")
    result = tracking_result(source, rows)
    assert result["tracking_success"] is None  # exception; no fabricated successful tracking
    assert result["gap_aware_rpe"]["eligible_frame_id_pairs"] == [[0,1]]
    table = {r["category"]: r["frame_count"] for r in result["failure_table"]}
    assert table["ok_without_pose"] == 2 and table["track_exception"] == 1


def test_no_pairs_with_large_delta_preserves_online_ate(source):
    result = tracking_result(source, rpe_delta=100)
    assert result["online_trajectory"]["metrics"]["ate_rmse_m"] < 1e-12
    assert result["gap_aware_rpe"]["metrics"] is None
    assert "no eligible" in result["gap_aware_rpe"]["reason"]


def test_no_gt_matches_or_exhausted_warmup_are_null_with_reasons(source):
    tum(source[1], source[2]+100, source[3])
    result = tracking_result(source, warmup=6)
    assert result["online_trajectory"]["metrics"] is None
    assert result["gap_aware_rpe"]["metrics"] is None
    assert result["tracking_latency"]["summary"] is None
    assert "no samples" in result["tracking_latency"]["reason"]
    assert result["tracking_success"] == 1


def test_initializing_and_relocalizing_segments_and_latency_include_all_states(source):
    rows = causal_rows(source, ["NOT_INITIALIZED", "NOT_INITIALIZED", "RELOCALIZE", "OK", "OK", "OK"])
    result = tracking_result(source, rows, warmup=1)
    assert result["non_ok_segments"][0]["frame_count"] == 2
    assert result["non_ok_segments"][0]["timestamp_span_s"] == pytest.approx(0.1)
    assert result["non_ok_segments"][1]["state"] == "RELOCALIZE"
    assert result["tracking_success"] == 0.5
    assert result["tracking_latency"]["summary"]["n_warm"] == 5


def test_recorded_tracking_outputs_and_plot_are_byte_identical_on_reevaluation(source, tmp_path):
    pytest.importorskip("matplotlib")
    with_tracking = attach_tracking(source, causal_rows(source))
    before = digest(with_tracking[0])
    first = invoke(with_tracking, tmp_path, plot=True)
    second = evaluate_slam_run(ROOT, with_tracking[0], with_tracking[1], run_id="second", output_root=tmp_path / "runs", plot=True)
    for name in ("metrics.json", "inputs.json", "tracking_states.png"):
        assert (first/name).read_bytes() == (second/name).read_bytes()
    assert load_run_manifest(first/"run.json")["status"] == "ok"
    assert json.loads((first/"metrics.json").read_text())["tracking_success"] == 1
    assert before == digest(with_tracking[0])


def test_tampered_tracking_file_is_rejected_before_output(source, tmp_path):
    with_tracking = attach_tracking(source, causal_rows(source))
    path = with_tracking[0] / "timing.csv"
    path.write_text(path.read_text() + "corrupt\n")
    with pytest.raises(ValueError, match="checksum"):
        invoke(with_tracking, tmp_path)
    assert not (tmp_path / "runs").exists()


def test_invalid_tracking_warmup_and_plot_without_export_are_rejected(source, tmp_path):
    with pytest.raises(ValueError, match="warmup"):
        invoke(source, tmp_path, tracking_warmup=-1)
    with pytest.raises(ValueError, match="requires"):
        invoke(source, tmp_path, plot=True)
