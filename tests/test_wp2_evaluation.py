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


def test_no_gt_matches_are_null_with_reason(source, tmp_path):
    tum(source[1], source[2] + 100, source[3])
    final = json.loads((invoke(source, tmp_path) / "metrics.json").read_text())["final_trajectory"]
    assert final["metrics"] is None and "insufficient" in final["reason"]
    assert final["coverage"]["gt_associated_poses"] == 0


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
