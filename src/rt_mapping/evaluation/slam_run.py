"""Derived B0 evaluation, causal tracking metrics and scoped resources (WP2).

GT is opened only here. Sim(3) is an evaluation gauge, never scale recovery.
Final upstream poses and stopped retained-keyframe poses are evaluated separately.
"""
from __future__ import annotations

from collections import Counter
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
from rt_mapping.evaluation.timing import summarize_timings
from rt_mapping.evaluation.trajectory import (
    associate_timestamps, read_tum_trajectory, trajectory_metrics,
)
from rt_mapping.geometry.projection import validate_pose
from rt_mapping.runs.artifacts import artifact_path
from rt_mapping.runs.geometry_run import collect_git_state
from rt_mapping.slam.sparse import load_sparse_snapshot
from rt_mapping.slam.tracking_log import read_tracking_log


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



def _state_segments(rows):
    segments = []
    for row in rows:
        if not segments or segments[-1]["state"] != row.tracking_state:
            segments.append({"state": row.tracking_state, "first_frame_id": row.frame_id,
                             "last_frame_id": row.frame_id, "first_timestamp_s": row.timestamp_s,
                             "last_timestamp_s": row.timestamp_s, "frame_count": 1})
        else:
            segments[-1].update(last_frame_id=row.frame_id, last_timestamp_s=row.timestamp_s)
            segments[-1]["frame_count"] += 1
    for segment in segments:
        segment["timestamp_span_s"] = segment["last_timestamp_s"] - segment["first_timestamp_s"]
    return segments


def evaluate_tracking(rows, gt_times, gt_poses, *, max_delta_s=0.02, rpe_delta=1, warmup=1):
    """Evaluate validated Y-01 rows. No imputation, segment-wise gauge or GT tuning.

    Fit one Sim(3) on associated causal poses using the unchanged trajectory
    evaluator. Use that single evaluation-only scale for every relative pair.
    A pair is discarded if any intervening input lacks a successful OK pose,
    including UNKNOWN states, observation exceptions and OK-without-pose rows.
    """
    if not rows:
        raise ValueError("tracking evaluation requires frozen input rows")
    if type(warmup) is not int or warmup < 0 or type(rpe_delta) is not int or rpe_delta < 1:
        raise ValueError("warmup must be nonnegative and RPE delta positive")
    for row in rows:
        row.validate()
    counts = Counter(row.tracking_state for row in rows)
    usable = np.array([r.tracking_state == "OK" and r.T_wc is not None and not r.error for r in rows])
    valid_indices = np.flatnonzero(usable)
    times = np.array([r.timestamp_s for r in rows])
    segments = _state_segments(rows)
    incomplete_states = counts["UNKNOWN"] > 0 or any(r.error for r in rows)
    success = None if incomplete_states else counts["OK"] / len(rows)
    reason = "UNKNOWN state or track exception prevents a complete success measurement" if incomplete_states else None
    online, online_reason = None, "no usable causal OK poses"
    matches = np.empty((0, 2), dtype=np.int64)
    poses = np.array([rows[i].T_wc for i in valid_indices])
    if len(valid_indices):
        matches = associate_timestamps(times[valid_indices], gt_times, max_delta_s=max_delta_s)
        try:
            # Delta=1 is only used to obtain the existing evaluator's one global
            # alignment/ATE. Its ungated RPE fields are intentionally not exposed.
            fitted = trajectory_metrics(times[valid_indices], poses, gt_times, gt_poses,
                                        alignment="sim3", max_delta_s=max_delta_s, rpe_delta=1)
            online = {k: v for k, v in fitted.items() if not k.startswith("rpe_")}
            online_reason = None
        except ValueError as exc:
            online_reason = str(exc)
    candidates = max(0, len(matches) - rpe_delta)
    pairs, excluded = [], []
    for i in range(candidates):
        j = i + rpe_delta
        a, b = (int(valid_indices[matches[k, 0]]) for k in (i, j))
        identity = [rows[a].frame_id, rows[b].frame_id]
        if not usable[a:b+1].all():
            excluded.append(identity)
        else:
            pairs.append((i, j, identity))
    rpe, rpe_reason = None, None
    if online is None:
        rpe_reason = "evaluation-only scale unavailable: " + online_reason
    elif not pairs:
        rpe_reason = "no eligible GT-associated pairs remain after delta and non-OK/missing-pose gap filtering"
    else:
        scale = online["evaluation_transform"]["scale"]
        estimates = poses[matches[:, 0]].copy()
        estimates[:, :3, 3] *= scale
        truth = np.asarray(gt_poses)[matches[:, 1]]
        translation_errors, rotation_errors = [], []
        for i, j, _ in pairs:
            relative_estimate = np.linalg.inv(estimates[i]) @ estimates[j]
            relative_truth = np.linalg.inv(truth[i]) @ truth[j]
            error = np.linalg.inv(relative_truth) @ relative_estimate
            translation_errors.append(np.linalg.norm(error[:3, 3]))
            rotation_errors.append(np.degrees(np.arccos(np.clip((np.trace(error[:3, :3])-1)/2, -1, 1))))
        rpe = {"rpe_translation_rmse_m": float(np.sqrt(np.mean(np.square(translation_errors)))),
               "rpe_rotation_rmse_deg": float(np.sqrt(np.mean(np.square(rotation_errors)))),
               "rpe_pairs": len(pairs)}
    try:
        latency = summarize_timings([r.tracking_ms for r in rows], warmup=warmup, stage="slam_track").to_dict()
        latency["warm_p50_ms"] = latency["warm_median_ms"]
        latency_reason = None
    except ValueError as exc:
        latency, latency_reason = None, str(exc)
    categories = {
        "initializing": sum(counts[s] for s in ("NO_IMAGES_YET", "NOT_INITIALIZED")),
        "lost": counts["LOST"],
        "relocalizing": sum(counts[s] for s in ("RELOCALIZE", "INIT_RELOCALIZE")),
        "unknown_state": counts["UNKNOWN"],
        "ok_without_pose": sum(r.tracking_state == "OK" and r.T_wc is None for r in rows),
        "track_exception": sum(bool(r.error) for r in rows),
        "keyframe_observation_error": sum(r.created_keyframe_frame_ids is None for r in rows),
        "gt_unassociated_usable_pose": len(valid_indices) - len(matches),
    }
    return {
        "input_frames": len(rows), "success_numerator": counts["OK"],
        "success_denominator": "all frozen associated RGB-depth input frames submitted to SLAM, including initialization/LOST/UNKNOWN",
        "tracking_success": success, "tracking_success_reason": reason,
        "observed_ok_fraction": counts["OK"] / len(rows), "usable_pose_fraction": len(valid_indices) / len(rows),
        "state_counts": dict(sorted(counts.items())), "state_segments": segments,
        "non_ok_segments": [s for s in segments if s["state"] != "OK"],
        "failure_table": [{"category": k, "frame_count": int(v)} for k, v in categories.items()],
        "failure_table_scope": "counts may overlap; GT-unassociated is an evaluation limitation, not tracking loss",
        "online_trajectory": {"metrics": online, "reason": online_reason,
                              "scope": "online/causal upstream world; separate evaluation-only Sim(3), not final optimized poses"},
        "gap_aware_rpe": {"metrics": rpe, "reason": rpe_reason,
                          "rpe_delta": rpe_delta, "rpe_delta_unit": "matched causal pose rows before gap filtering",
                          "candidate_pairs": candidates, "excluded_gap_pairs": len(excluded),
                          "excluded_frame_id_pairs": excluded, "eligible_frame_id_pairs": [p[2] for p in pairs],
                          "scale_use": "one global evaluation-only Sim(3) fit on causal poses; no per-segment fitting",
                          "gap_rule": "every intervening frozen input must have OK state, a valid causal pose and no track exception"},
        "tracking_latency": {"summary": latency, "reason": latency_reason, "warmup_frames": warmup,
                             "warmup_policy": "exclude the first N frozen input rows regardless of state; remaining initialization/lost rows are included",
                             "scope": "Slam.track wall time including waits/hook overhead, excluding decode and post-call CSV work",
                             "cold_sample_scope": "first Slam.track invocation only; not process/model startup",
                             "mapping_ms": None, "mapping_reason": "background mapping is not attributable per input frame",
                             "total_ms": None, "total_reason": "whole input-loop latency is not instrumented"},
    }


def _plot_tracking(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    states = ["NO_IMAGES_YET", "NOT_INITIALIZED", "OK", "LOST", "RELOCALIZE", "INIT_RELOCALIZE", "UNKNOWN"]
    palette = ["#8c8c8c", "#d8a31a", "#228b55", "#cb3d3d", "#9557b0", "#b476ce", "#303030"]
    figure, (state_ax, latency_ax) = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True,
                                               gridspec_kw={"height_ratios": [1, 2]}, constrained_layout=True)
    for state, color in zip(states, palette):
        selected = [r for r in rows if r.tracking_state == state]
        if selected:
            state_ax.scatter([r.frame_id for r in selected], [states.index(state)] * len(selected),
                             s=13, color=color, label=state)
    present = [i for i, state in enumerate(states) if any(r.tracking_state == state for r in rows)]
    state_ax.set_yticks(present, [states[i] for i in present])
    state_ax.set_ylim(min(present)-0.5, max(present)+0.5)
    state_ax.set_title("Observed tracking states — all frozen inputs")
    latency_ax.plot([r.frame_id for r in rows], [r.tracking_ms for r in rows], color="#2466a4", linewidth=1)
    latency_ax.set(xlabel="Frozen input frame ID", ylabel="Slam.track wall time [ms]")
    latency_ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    latency_ax.grid(alpha=0.25)
    figure.savefig(path, dpi=160, metadata={"Software": "rt_mapping WP2 Y-03"})
    plt.close(figure)

def evaluate_slam_run(root, source_run, groundtruth, *, run_id, output_root=None,
                      max_delta_s=0.02, rpe_delta=1, resources=None, tracking_warmup=1, plot=False):
    """Evaluate final poses and optional verified causal Y-01 exports into a new run."""
    root, source_run, groundtruth = Path(root), Path(source_run), Path(groundtruth)
    if not np.isfinite(max_delta_s) or max_delta_s < 0 or type(rpe_delta) is not int or rpe_delta < 1:
        raise ValueError("invalid timestamp tolerance or RPE delta")
    if type(tracking_warmup) is not int or tracking_warmup < 0:
        raise ValueError("tracking warmup must be a nonnegative integer")
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
    tracking, tracking_rows = None, None
    keys = {"trajectory_all": "trajectory_all.csv", "tracking_timing": "timing.csv", "tracking_export": "tracking_export.json"}
    advertised = set(keys) & source["artifacts"].keys()
    if advertised:
        if advertised != set(keys):
            raise ValueError("source must advertise all three Y-01 tracking artifacts")
        for key, filename in keys.items():
            path = artifact_path(source_run, source, key)
            if path != source_run.resolve() / filename:
                raise ValueError("tracking artifacts must use canonical Y-01 paths")
            provenance[filename + "_sha256"] = sha256_file(path)
        tracking_rows, metadata = read_tracking_log(source_run, frames)
        tracking = evaluate_tracking(tracking_rows, gt_times, gt_poses, max_delta_s=max_delta_s,
                                     rpe_delta=rpe_delta, warmup=tracking_warmup)
        tracking["export_semantics"] = {k: metadata[k] for k in ("pose_frame", "pose_temporality", "tracking_timing_scope")}
    if plot and tracking_rows is None:
        raise ValueError("state timeline plot requires a verified Y-01 export")
    if plot:
        import matplotlib  # fail before creating an output directory if unavailable
    metrics = {
        "schema": "rt_mapping.slam_evaluation/v1", "final_trajectory": final,
        "retained_keyframes": retained, "resources": resource_report,
        "tracking": tracking if tracking is not None else _missing("source has no Y-01 causal export"),
        "tracking_success": tracking["tracking_success"] if tracking else None,
        "tracking_success_reason": tracking["tracking_success_reason"] if tracking else "source has no Y-01 causal export",
        "real_time_claim": False,
    }
    reasons = []
    if tracking is None:
        reasons.append("source has no Y-01 causal export")
    else:
        if tracking["tracking_success"] is None:
            reasons.append(tracking["tracking_success_reason"])
        for block in (tracking["online_trajectory"], tracking["gap_aware_rpe"]):
            if block["metrics"] is None:
                reasons.append(block["reason"])
        if tracking["tracking_latency"]["summary"] is None:
            reasons.append(tracking["tracking_latency"]["reason"])
        if any(r.error or (r.tracking_state == "OK" and r.T_wc is None) or r.created_keyframe_frame_ids is None
               for r in tracking_rows):
            reasons.append("causal observation errors or missing OK pose/keyframe telemetry")
    if final["metrics"] is None:
        reasons.append("final trajectory: " + final["reason"])
    if source["status"] != "ok":
        reasons.append("source run is degraded: " + source["reason"])
    git = collect_git_state(root)
    record = build_run_manifest(
        run_id=run_id, git_commit=git.commit, dirty_worktree=git.dirty,
        dataset=source["dataset"], method="B0", model=None, slam=source["slam"], alignment=None,
        config={"runner": "scripts/evaluate_wp2_run.py", "source_run_id": source["run_id"],
                "max_timestamp_delta_s": max_delta_s, "rpe_delta": rpe_delta,
                "scale_use": "evaluation-only", "pose_convention": "T_wc",
                "tracking_warmup": tracking_warmup, "plot": plot},
        hardware={"cpu": platform.machine(), "gpu": None, "ram_gb": None},
        environment={"python": platform.python_version(), "numpy": np.__version__},
        seed=source["seed"], started_at=format_utc(datetime.now(timezone.utc)),
        status="degraded" if reasons else "ok", reason="; ".join(reasons) if reasons else None,
        artifacts={"metrics": "metrics.json", "inputs": "inputs.json",
                   **({"tracking_states_plot": "tracking_states.png"} if plot else {})},
    )
    directory = (Path(output_root) if output_root else root / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    _json(directory / "metrics.json", metrics)
    _json(directory / "inputs.json", provenance)
    if plot:
        _plot_tracking(tracking_rows, directory / "tracking_states.png")
    write_run_manifest(record, directory)
    return directory
