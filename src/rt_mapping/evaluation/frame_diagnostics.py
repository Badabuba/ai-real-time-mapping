"""Evaluation-only join of GT-free keyframe signals with depth and map error (U-01).

Phase A (rt_mapping.alignment.frame_signals) is computed and written before any
ground truth is opened here. GT depth/poses enter only through the explicit
evaluation helpers below; nothing is fed back into the signals or thresholds.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform

import numpy as np

from rt_mapping.alignment.correspondences import prediction_grid
from rt_mapping.alignment.frame_signals import (SIGNAL_FIELDS, check_recorded_residuals, flag_rules,
                                                frame_signals, load_sources, rebuild_pairs, tracking_states,
                                                write_csv, write_json)
from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, write_run_manifest
from rt_mapping.evaluation.depth import evaluate_depth
from rt_mapping.evaluation.oracle import load_oracle_inputs
from rt_mapping.fusion import depth_points, metric_pose
from rt_mapping.runs.artifacts import artifact_path
from rt_mapping.runs.geometry_run import collect_git_state, collect_host_info

EVALUATION_FIELDS = (
    "frame_id", "eval_depth_source", "eval_abs_rel", "eval_rmse_m", "eval_delta1",
    "eval_abs_rel_crosscheck_difference", "eval_map_points", "eval_map_accuracy_mean_m",
    "eval_map_accuracy_median_m", "eval_map_accuracy_p90_m",
)
CORRELATED_SIGNALS = ("abs_log_anchor_ratio", "one_minus_frame_inlier_ratio", "median_abs_residual_m",
                      "withheld_median_abs_residual_m", "predicted_depth_median_m")
TARGETS = ("eval_abs_rel", "eval_map_accuracy_mean_m")
FAILURE_FIELDS = ("rank", "frame_id", "eval_map_accuracy_mean_m", "eval_abs_rel", "anchor_ratio",
                  "flags", "category")
CATEGORY = {"A1": "A1 insufficient sparse anchors", "A2": "D1 per-frame metric-scale error (A2)",
            "A3": "A3 high withheld residual", "A4": "A4 low anchor image coverage", "S1": "S1 tracking not OK"}
UNFLAGGED = "unflagged; гіпотеза: D2 local depth error"


def _ranks(values):
    """Average ranks (1-based) with ties sharing their mean rank."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    sorted_values = values[order]
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and sorted_values[stop] == sorted_values[start]:
            stop += 1
        ranks[order[start:stop]] = (start + stop + 1) / 2
        start = stop
    return ranks


def spearman(x, y):
    """Spearman rho as the Pearson correlation of average ranks; None if undefined."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) != len(y) or len(x) < 3:
        return None
    rx, ry = _ranks(x) - (len(x) + 1) / 2, _ranks(y) - (len(y) + 1) / 2
    denominator = math.sqrt(float(np.sum(rx * rx) * np.sum(ry * ry)))
    return float(np.sum(rx * ry) / denominator) if denominator else None


def _signal_value(row, name):
    if name == "one_minus_frame_inlier_ratio":
        return None if row["frame_inlier_ratio"] is None else 1 - row["frame_inlier_ratio"]
    return row[name]


def correlations(signals, evaluation):
    by_frame = {row["frame_id"]: row for row in evaluation}
    result = {}
    for name in CORRELATED_SIGNALS:
        for target in TARGETS:
            pairs = [(_signal_value(row, name), by_frame[row["frame_id"]][target]) for row in signals]
            kept = [(x, y) for x, y in pairs if x is not None and y is not None]
            rho = spearman(*zip(*kept)) if len(kept) >= 3 else None
            result[f"{name}__vs__{target}"] = {
                "signal": name, "target": target, "spearman_rho": rho, "n": len(kept),
                "excluded_nulls": len(pairs) - len(kept),
                "reason": None if rho is not None else "fewer than 3 non-null pairs or a constant variable"}
    return result


def _flags(row):
    return [name for name in ("A1", "A2", "A3", "A4", "S1") if row[f"flag_{name}"]]


def failure_table(signals, evaluation):
    by_frame = {row["frame_id"]: row for row in evaluation}
    ordered = sorted(signals, key=lambda r: (-by_frame[r["frame_id"]]["eval_map_accuracy_mean_m"], r["frame_id"]))
    table = []
    for rank, row in enumerate(ordered, 1):
        flags = _flags(row)
        table.append({"rank": rank, "frame_id": row["frame_id"],
                      "eval_map_accuracy_mean_m": by_frame[row["frame_id"]]["eval_map_accuracy_mean_m"],
                      "eval_abs_rel": by_frame[row["frame_id"]]["eval_abs_rel"], "anchor_ratio": row["anchor_ratio"],
                      "flags": ";".join(flags),
                      "category": "; ".join(CATEGORY[f] for f in flags) if flags else UNFLAGGED})
    return table


def evaluate_frames(sources, signals, sequence_dir, manifest_path):
    """GT depth metrics and per-keyframe map contribution against the recorded reference."""
    mapping, inputs = sources.mapping, sources.inputs
    oracle, _, _, _, _ = load_oracle_inputs(inputs, sequence_dir, manifest_path, mapping,
                                            max_timestamp_delta_s=sources.comparison["config"]["max_timestamp_delta_s"])
    recorded = {}
    if "metrics" in inputs.geometry["artifacts"]:
        metrics = json.loads(artifact_path(sources.geometry_dir, inputs.geometry, "metrics").read_text(encoding="utf-8"))
        recorded = {int(item["frame_id"]): item for item in metrics["per_frame"]}
    with np.load(sources.comparison_dir / "reference_evaluation_only.npz", allow_pickle=False) as archive:
        reference = archive["xyz_m"]
    transform = json.loads((sources.comparison_dir / "trajectory_evaluation.json").read_text(encoding="utf-8"))
    transform = transform["P1_global_se3"]["evaluation_transform"]
    rotation, translation = np.asarray(transform["R"]), np.asarray(transform["t"])
    from scipy.spatial import cKDTree

    tree = cKDTree(reference)
    cameras, scale = inputs.snapshot.keyframes, float(sources.alignment["scale"])
    index_of = {int(frame_id): i for i, frame_id in enumerate(cameras["frame_id"])}
    rows = []
    for signal in signals:
        frame_id = signal["frame_id"]
        i, prediction = index_of[frame_id], inputs.predictions[frame_id]
        recomputed = evaluate_depth(prediction, oracle[frame_id].depth_m)
        source = recorded.get(frame_id)
        depth = source if source is not None else recomputed.to_dict()
        _, grid = prediction_grid(prediction, cameras["K"][i], cameras["image_size_wh"][i])
        points = depth_points(prediction, metric_pose(cameras["T_wc"][i], scale),
                              distortion=cameras["distortion"][i] if grid == "raw_distorted" else None,
                              min_depth_m=mapping["min_depth_m"], max_depth_m=mapping["max_depth_m"],
                              confidence_threshold=mapping["confidence_threshold"], pixel_stride=mapping["pixel_stride"])
        distances, _ = tree.query(points @ rotation.T + translation, k=1)
        rows.append({"frame_id": frame_id,
                     "eval_depth_source": "geometry_run_metrics" if source is not None else "recomputed_from_oracle",
                     "eval_abs_rel": float(depth["abs_rel"]), "eval_rmse_m": float(depth["rmse_m"]),
                     "eval_delta1": float(depth["delta1"]),
                     "eval_abs_rel_crosscheck_difference": abs(float(depth["abs_rel"]) - recomputed.abs_rel),
                     "eval_map_points": len(points), "eval_map_accuracy_mean_m": float(distances.mean()),
                     "eval_map_accuracy_median_m": float(np.median(distances)),
                     "eval_map_accuracy_p90_m": float(np.percentile(distances, 90))})
    return rows


def _plot_timeline(path, signals, evaluation, threshold, tracking_note):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    by_frame = {row["frame_id"]: row for row in evaluation}
    x = np.arange(len(signals))
    labels = [str(r["frame_id"]) for r in signals]
    nan = lambda v: np.nan if v is None else v
    fig, axes = plt.subplots(5, 1, figsize=(9, 10), sharex=True, constrained_layout=True)
    anchor = [nan(r["anchor_ratio"]) for r in signals]
    axes[0].plot(x, anchor, marker="o", label="anchor ratio a_f (GT-free)")
    for bound in (1 / 1.25, 1.0, 1.25):
        axes[0].axhline(bound, color="grey", linestyle="--" if bound != 1 else ":", linewidth=0.8)
    flagged = [i for i, r in enumerate(signals) if _flags(r)]
    axes[0].scatter(flagged, [anchor[i] if np.isfinite(anchor[i]) else 1.0 for i in flagged], marker="x", color="red",
                    s=60, zorder=3, label="any flag A1-A4/S1")
    axes[0].set(ylabel="a_f")
    axes[0].legend(fontsize=7, loc="best")
    axes[1].plot(x, [nan(r["frame_inlier_ratio"]) for r in signals], marker="o", color="#4c78a8")
    axes[1].set(ylabel="Inlier ratio\n(global scale)")
    axes[2].plot(x, [nan(r["withheld_median_abs_residual_m"]) for r in signals], marker="o", color="#f58518")
    axes[2].axhline(threshold, color="red", linestyle="--", linewidth=0.8)
    axes[2].set(ylabel="Withheld median\n|residual| [m]")
    axes[3].plot(x, [by_frame[r["frame_id"]]["eval_abs_rel"] for r in signals], marker="o", color="#54a24b")
    axes[3].set(ylabel="AbsRel\n(evaluation only)")
    axes[4].plot(x, [by_frame[r["frame_id"]]["eval_map_accuracy_mean_m"] for r in signals], marker="o", color="#b279a2")
    axes[4].set(ylabel="Map-contribution\nmean dist. [m]\n(evaluation only)", xlabel="Retained keyframe (frame_id)")
    axes[4].set_xticks(x, labels, rotation=60, fontsize=7)
    fig.suptitle(f"Per-keyframe diagnostics, TUM fr1/xyz smoke-200 (offline). Tracking: {tracking_note}", fontsize=9)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_signal(path, signals, evaluation, correlation):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    name = correlation["signal"]
    by_frame = {row["frame_id"]: row for row in evaluation}
    points = [(_signal_value(r, name), by_frame[r["frame_id"]]["eval_map_accuracy_mean_m"], r["frame_id"])
              for r in signals if _signal_value(r, name) is not None]
    fig, axis = plt.subplots(figsize=(6, 4.5), constrained_layout=True)
    axis.scatter([p[0] for p in points], [p[1] for p in points], color="#4c78a8")
    for x, y, frame_id in points:
        axis.annotate(str(frame_id), (x, y), fontsize=6, xytext=(2, 2), textcoords="offset points")
    axis.set(xlabel=f"{name} (GT-free)", ylabel="Map-contribution mean distance [m] (evaluation only)",
             title=f"Spearman rho = {correlation['spearman_rho']:.3f}, n = {correlation['n']} (descriptive only)")
    fig.savefig(path, dpi=110)
    plt.close(fig)


def run_frame_diagnostics(repo_root, comparison_run, slam_run, geometry_run, sequence_dir, manifest_path, *,
                          run_id, output_root=None, plot=False):
    """Preflight refusals write nothing; later failures leave a terminal run.json."""
    sources = load_sources(comparison_run, slam_run, geometry_run)
    pairs, withheld = rebuild_pairs(sources.inputs, sources.mapping)
    residual_check = check_recorded_residuals(sources.global_dir / "residuals.csv", pairs, withheld)
    tracking, tracking_info = tracking_states(slam_run, sources.inputs.slam)
    state, host = collect_git_state(repo_root), collect_host_info()
    inputs = sources.inputs
    record = dict(run_id=run_id, git_commit=state.commit, dirty_worktree=state.dirty, dataset=inputs.slam["dataset"],
                  method="P1-global", model=inputs.geometry["model"], slam=inputs.slam["slam"],
                  alignment={"method": sources.global_record["alignment"]["method"],
                             "thresholds": sources.global_record["alignment"]["thresholds"]},
                  config={"control_label": "per-keyframe diagnostics; no new map", "sources": sources.provenance,
                          "mapping": sources.mapping, "flag_rules": flag_rules(sources.mapping),
                          "scope": "offline retained-keyframe diagnostics; GT-free phase written before evaluation"},
                  hardware={"gpu": None, "cpu": host.cpu, "ram_gb": host.ram_gb},
                  environment={"python": platform.python_version(), "numpy": np.__version__},
                  seed=sources.mapping["seed"], started_at=format_utc(datetime.now(timezone.utc)),
                  status="running", reason=None, artifacts={})
    build_run_manifest(**record)
    directory = Path(output_root or Path(repo_root) / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), directory)
    try:
        signals = frame_signals(sources, pairs, withheld, tracking)
        write_csv(directory / "frame_signals.csv", SIGNAL_FIELDS, signals)
        counts = {name: sum(bool(r[f"flag_{name}"]) for r in signals) for name in ("A1", "A2", "A3", "A4", "S1")}
        write_json(directory / "signals.json", {
            "scope": "GT-free", "keyframes": len(signals), "flag_counts": counts, "flag_rules": flag_rules(sources.mapping),
            "global_scale": float(sources.alignment["scale"]), "tracking": tracking_info,
            "residuals_crosscheck": residual_check, "sources": sources.provenance})
        record["artifacts"].update(frame_signals="frame_signals.csv", signals="signals.json")
        # GT-free phase is now immutable on disk; evaluation starts below.
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
        evaluation = evaluate_frames(sources, signals, sequence_dir, manifest_path)
        write_csv(directory / "frame_evaluation.csv", EVALUATION_FIELDS, evaluation)
        correlation = correlations(signals, evaluation)
        write_json(directory / "correlations.json", {"scope": "evaluation_only", "method": "Spearman, average ranks",
            "note": "descriptive only; no significance claim for small n", "correlations": correlation})
        table = failure_table(signals, evaluation)
        write_csv(directory / "failure_table.csv", FAILURE_FIELDS, table)
        by_frame = {row["frame_id"]: row for row in evaluation}
        write_csv(directory / "frame_diagnostics.csv", SIGNAL_FIELDS + EVALUATION_FIELDS[1:],
                  [{**row, **by_frame[row["frame_id"]]} for row in signals])
        record["artifacts"].update(frame_evaluation="frame_evaluation.csv", correlations="correlations.json",
                                   failure_table="failure_table.csv", frame_diagnostics="frame_diagnostics.csv")
        defined = [c for c in correlation.values() if c["target"] == "eval_map_accuracy_mean_m" and c["spearman_rho"] is not None]
        if plot:
            note = "available" if tracking_info["available"] else "unavailable (run predates Y-01 export)"
            _plot_timeline(directory / "timeline.png", signals, evaluation, sources.mapping["residual_threshold_m"], note)
            record["artifacts"]["timeline_plot"] = "timeline.png"
            if defined:
                _plot_signal(directory / "signal_vs_error.png", signals, evaluation,
                             max(defined, key=lambda c: (abs(c["spearman_rho"]), c["signal"])))
                record["artifacts"]["signal_plot"] = "signal_vs_error.png"
        write_json(directory / "diagnostics_summary.json", {
            "scope": "GT-free signals + evaluation_only join; offline; no real-time claim",
            "keyframes": len(signals), "flag_counts": counts, "tracking": tracking_info,
            "residuals_crosscheck": residual_check, "global_scale": float(sources.alignment["scale"]),
            "depth_crosscheck_max_abs_rel_difference": max(r["eval_abs_rel_crosscheck_difference"] for r in evaluation),
            "correlations": correlation, "failure_table": table, "sources": sources.provenance})
        record["artifacts"]["summary"] = "diagnostics_summary.json"
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: diagnostics stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"diagnostics_failed: {type(exc).__name__}: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory


__all__ = ["correlations", "evaluate_frames", "failure_table", "run_frame_diagnostics", "spearman"]
