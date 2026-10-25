"""Derived B0 evaluation and POSIX resource measurement (WP2 Y-02).

GT is opened only here. Sim(3) is an evaluation gauge, never scale recovery.
Final upstream poses and stopped retained-keyframe poses are evaluated separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import time

import numpy as np

from rt_mapping.contracts.run_manifest import (
    build_run_manifest, format_utc, load_run_manifest, write_run_manifest,
)
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.trajectory import (
    associate_timestamps, read_tum_trajectory, trajectory_metrics,
)
from rt_mapping.geometry.projection import validate_pose
from rt_mapping.runs.artifacts import artifact_path
from rt_mapping.runs.geometry_run import collect_git_state
from rt_mapping.slam.sparse import load_sparse_snapshot


def _json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _missing(reason):
    return {"value": None, "reason": reason}


def rss_bytes(raw, system):
    """Normalize ru_maxrss; unsupported units must never be guessed."""
    if not np.isfinite(raw) or raw <= 0:
        return None
    if system == "Darwin":
        return int(raw)
    if system == "Linux":
        return int(raw * 1024)
    return None


def measure_process(argv, *, cwd):
    """Run one child in a fresh wrapper process, using POSIX child rusage.

    ru_maxrss is a lifetime high-water mark, not additive and not subtractable.
    If children were already reaped, RSS cannot be attributed to this invocation.
    This is the largest individual-process RSS reported by the OS, not the sum
    of concurrently resident SLAM workers. Descendant accounting is OS-dependent.
    """
    try:
        import resource
    except ImportError:
        resource = None
    before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    start = time.perf_counter()
    launch_error = None
    try:
        exit_code = subprocess.call(argv, cwd=cwd)
    except OSError as exc:
        exit_code, launch_error = None, f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    peak = rss_bytes(after.ru_maxrss, platform.system()) if after else None
    reason = None
    if launch_error is not None:
        peak, reason = None, "child executable could not be launched"
    elif resource is None:
        reason = "POSIX resource module unavailable"
    elif before.ru_maxrss != 0 or before.ru_utime != 0 or before.ru_stime != 0:
        peak, reason = None, "prior reaped children; cumulative RUSAGE_CHILDREN cannot be isolated"
    elif peak is None:
        reason = "RSS unavailable, nonpositive, or platform units unsupported"
    return {
        "exit_code": exit_code, "launch_error": launch_error,
        "wall_clock_s": elapsed,
        "wall_clock_scope": "whole B0 runner child: preflight, startup, tracking, export and shutdown; no warm-up excluded",
        "peak_rss_bytes": peak, "peak_rss_reason": reason,
        "peak_rss_scope": "RUSAGE_CHILDREN ru_maxrss; maximum individual-process RSS reported by OS, not concurrent process-tree RAM; descendant accounting OS-dependent",
        "cold_start_s": None,
        "cold_start_reason": "time to first tracked frame is not instrumented; whole-run wall clock is reported separately",
    }


def measure_slam_run(root, python, source, native_python, *, run_id, frames=200,
                     output_root=None, timeout_s=1800, export_sparse=True):
    """Wrap the existing runner; append no data to its immutable run.json."""
    root = Path(root).absolute()
    output_root = Path(output_root).absolute() if output_root else root / "results/runs"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("invalid run_id")
    if type(frames) is not int or frames < 2 or type(timeout_s) is not int or timeout_s < 1:
        raise ValueError("frames must be >= 2 and timeout_s >= 1")
    directory = output_root / run_id
    report_path = output_root / f"{run_id}.resources.json"
    if directory.exists() or report_path.exists():
        raise ValueError("run or resource report already exists; choose a new run_id")
    output_root.mkdir(parents=True, exist_ok=True)
    argv = [str(Path(python).absolute()), str(root / "scripts/run_wp2_pyslam.py"),
            "--pyslam-root", str(Path(source).absolute()),
            "--pyslam-python", str(Path(native_python).absolute()),
            "--frames", str(frames), "--timeout", str(timeout_s),
            "--output-root", str(output_root), "--run-id", run_id]
    if export_sparse:
        argv.append("--export-sparse")
    result = measure_process(argv, cwd=root)
    source_manifest = directory / "run.json"
    record = load_run_manifest(source_manifest) if source_manifest.is_file() else None
    completed = bool(record and record["status"] == "ok" and result["exit_code"] == 0)
    # A completed runner validates its input coverage; failed runs have no FPS.
    result.update(
        schema="rt_mapping.slam_resources/v1", source_run_id=run_id,
        source_run_sha256=sha256_file(source_manifest) if record else None,
        status="ok" if completed else "failed", source_status=record["status"] if record else None,
        requested_frames=frames, throughput_frames=frames if completed else None,
        effective_fps=frames / result["wall_clock_s"] if completed else None,
        effective_fps_reason=None if completed else "source run did not complete successfully",
        effective_fps_scope="validated frozen input frames / whole-run wall clock, including initialization and startup",
        platform=platform.system(), python=platform.python_version(), real_time_claim=False,
    )
    _json(report_path, result)
    return report_path


def _evaluate(times, poses, gt_times, gt_poses, input_times, *, tolerance, rpe_delta, scope):
    times, poses = np.asarray(times, dtype=float), np.asarray(poses, dtype=float)
    if poses.shape != (len(times), 4, 4):
        raise ValueError("pose array shape mismatch")
    for pose in poses:
        validate_pose(pose)
    # Identity is against actual submitted RGB timestamps, never GT coverage.
    associated = associate_timestamps(times, input_times, max_delta_s=1e-6)
    if len(associated) != len(times):
        raise ValueError("trajectory timestamps do not match the frozen input grid")
    coverage = {
        "pose_count": len(times), "input_frames": len(input_times),
        "pose_fraction": len(times) / len(input_times),
        "denominator": "frozen associated RGB-depth input frames actually submitted to SLAM",
        "tracking_success": None, "tracking_success_reason": "not evaluated in Y-02; pose coverage is not tracking success",
    }
    matches = associate_timestamps(times, gt_times, max_delta_s=tolerance)
    coverage["gt_associated_poses"] = len(matches)
    try:
        metrics = trajectory_metrics(times, poses, gt_times, gt_poses,
                                     alignment="sim3", max_delta_s=tolerance, rpe_delta=rpe_delta)
        reason = None
    except ValueError as exc:
        # Valid poses may lack sufficient GT matches or a nondegenerate gauge.
        metrics, reason = None, str(exc)
    return {"scope": scope, "coverage": coverage, "metrics": metrics, "reason": reason,
            "scale_use": "evaluation-only Sim(3); does not recover metric scale",
            "rpe_scope": "matched pose rows; not gap-aware (Y-03); not input-frame delta"}


def evaluate_slam_run(root, source_run, groundtruth, *, run_id, output_root=None,
                      max_delta_s=0.02, rpe_delta=1, resources=None):
    """Evaluate a finished B0 run into a new derived, explicitly degraded run."""
    root, source_run, groundtruth = Path(root), Path(source_run), Path(groundtruth)
    if not np.isfinite(max_delta_s) or max_delta_s < 0 or type(rpe_delta) is not int or rpe_delta < 1:
        raise ValueError("invalid timestamp tolerance or RPE delta")
    source = load_run_manifest(source_run / "run.json")
    if source["method"] != "B0" or source["status"] not in ("ok", "degraded"):
        raise ValueError("evaluation requires a completed ok/degraded B0 source run")
    if source["slam"]["pose_convention"] != "T_wc":
        raise ValueError("source poses must use T_wc")
    prep_path = artifact_path(source_run, source, "preparation")
    preparation = json.loads(prep_path.read_text(encoding="utf-8"))
    frames = preparation["frames"]
    if not frames or len(frames) != source["config"]["frames"]:
        raise ValueError("input preparation does not match source frame count")
    input_times = np.array([f["rgb_timestamp_s"] for f in frames], dtype=float)
    if [f["frame_id"] for f in frames] != list(range(len(frames))):
        raise ValueError("preparation frame IDs must be consecutive frozen input IDs")
    final_path = artifact_path(source_run, source, "trajectory")
    final_times, final_poses = read_tum_trajectory(final_path)
    # No ground-truth files are used in SLAM or measurement.
    gt_times, gt_poses = read_tum_trajectory(groundtruth)
    final = _evaluate(final_times, final_poses, gt_times, gt_poses, input_times,
                      tolerance=max_delta_s, rpe_delta=rpe_delta,
                      scope="upstream final trajectory; optimized snapshot, not causal all-frame history")
    provenance = {
        "source_run_id": source["run_id"], "source_git_commit": source["git_commit"],
        "source_dirty_worktree": source["dirty_worktree"], "source_status": source["status"],
        "source_hardware": source["hardware"], "source_environment": source["environment"],
        "source_run_sha256": sha256_file(source_run / "run.json"),
        "preparation_sha256": sha256_file(prep_path), "final_trajectory_sha256": sha256_file(final_path),
        "groundtruth_sha256": sha256_file(groundtruth),
        "groundtruth_use": "evaluation only; user-supplied reference trajectory",
    }
    retained = {"metrics": None, "reason": "source run has no retained-keyframe export"}
    if "keyframes" in source["artifacts"]:
        keyframe_path = artifact_path(source_run, source, "keyframes")
        snapshot = load_sparse_snapshot(keyframe_path.parent)
        cameras = snapshot.keyframes
        ids = cameras["frame_id"]
        if np.any(ids >= len(frames)) or not np.allclose(cameras["timestamp_s"], input_times[ids], rtol=0, atol=1e-6):
            raise ValueError("retained keyframe identities differ from frozen inputs")
        order = np.argsort(cameras["timestamp_s"])
        retained = _evaluate(cameras["timestamp_s"][order], cameras["T_wc"][order], gt_times, gt_poses, input_times,
                             tolerance=max_delta_s, rpe_delta=rpe_delta,
                             scope="stopped retained-keyframe snapshot; separate Sim(3) fit, same evaluator as comparison B0_sim3")
        provenance["sparse_export_sha256"] = sha256_file(keyframe_path.parent / "export.json")
        provenance["sparse_sha256"] = snapshot.metadata["sha256"]
    resource_report = _missing("no resource report supplied; historical wall clock is not a peak-RSS measurement")
    if resources is not None:
        resource_report = json.loads(Path(resources).read_text(encoding="utf-8"))
        if (resource_report.get("schema") != "rt_mapping.slam_resources/v1"
                or resource_report.get("source_run_id") != source["run_id"]
                or resource_report.get("source_run_sha256") != provenance["source_run_sha256"]):
            raise ValueError("resource report does not identify this exact source run")
        provenance["resource_report_sha256"] = sha256_file(Path(resources))
    metrics = {
        "schema": "rt_mapping.slam_evaluation/v1", "final_trajectory": final,
        "retained_keyframes": retained, "resources": resource_report,
        "tracking_success": None, "tracking_success_reason": "all-frame states/gaps not evaluated until Y-03",
        "real_time_claim": False,
    }
    git = collect_git_state(root)
    record = build_run_manifest(
        run_id=run_id, git_commit=git.commit, dirty_worktree=git.dirty,
        dataset=source["dataset"], method="B0", model=None, slam=source["slam"], alignment=None,
        config={"runner": "scripts/evaluate_wp2_run.py", "source_run_id": source["run_id"],
                "max_timestamp_delta_s": max_delta_s, "rpe_delta": rpe_delta,
                "scale_use": "evaluation-only", "pose_convention": "T_wc"},
        hardware={"cpu": platform.machine(), "gpu": None, "ram_gb": None},
        environment={"python": platform.python_version(), "numpy": np.__version__},
        seed=source["seed"], started_at=format_utc(datetime.now(timezone.utc)),
        status="degraded", reason="Y-02 evaluates final poses only; all-frame tracking success and gap-aware RPE pending Y-03",
        artifacts={"metrics": "metrics.json", "inputs": "inputs.json"},
    )
    directory = (Path(output_root) if output_root else root / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    _json(directory / "metrics.json", metrics)
    _json(directory / "inputs.json", provenance)
    write_run_manifest(record, directory)
    return directory
