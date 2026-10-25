"""P1-robust real smoke (U-03): control reproduction, anchored and gated maps, then GT evaluation.

Phase A is GT-free. The control is the unchanged public run_mapping with the
recorded mapping config; the two variants reuse the frozen U-02 anchoring and
gate, whose decisions must equal the committed U-02 summary; the frozen config
must carry the sha256 recorded there. Every map is written before any ground
truth is opened. Phase B evaluates every variant with the unchanged evaluate_map
against the recorded reference and shared SE(3) evaluation transform, and copies
the recorded B0/B1/P1-raw rows after checking that they used the same transform.
Offline final-snapshot anchors; CPU artifact processing only; no real-time claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np

from rt_mapping.alignment.anchoring import (ANCHOR_GATE_FIELDS, anchor_gate_rows, anchored_prediction,
                                            check_config_against_sources, load_config)
from rt_mapping.alignment.correspondences import prediction_grid
from rt_mapping.alignment.frame_signals import (SIGNAL_FIELDS, check_recorded_residuals, frame_signals, load_sources,
                                                rebuild_pairs, tracking_states, write_csv, write_json)
from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, load_run_manifest, write_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.depth import evaluate_depth
from rt_mapping.evaluation.map_geometry import evaluate_map
from rt_mapping.evaluation.oracle import load_oracle_inputs
from rt_mapping.fusion import VoxelFusion, depth_points, metric_pose, write_ply
from rt_mapping.fusion.voxel import statistical_filter
from rt_mapping.runs.geometry_run import collect_git_state, collect_host_info
from rt_mapping.runs.mapping_run import run_mapping

CONTROL, ANCHORED, GATED = "P1-global-control", "P1-anchored", "P1-anchored+gate"
RECORDED = ("B0-shared-scale", "B1-oracle", "P1-raw")
VARIANT_DIRS = {ANCHORED: "anchored", GATED: "anchored_gate"}
CPU_LABEL = "CPU artifact processing only; excludes SLAM and model inference; not real-time"
COMPARISON_FIELDS = (
    "method", "role", "frames_fused", "frames_rejected", "input_points", "map_voxels", "eval_estimate_points",
    "eval_accuracy_mean_m", "eval_accuracy_median_m", "eval_completeness_mean_m", "eval_completeness_median_m",
    "eval_chamfer_l1_m", "eval_precision_0.02m", "eval_recall_0.02m", "eval_fscore_0.02m", "eval_precision_0.05m",
    "eval_recall_0.05m", "eval_fscore_0.05m", "eval_precision_0.1m", "eval_recall_0.1m", "eval_fscore_0.1m",
    "eval_ate_se3_rmse_m", "fusion_median_ms", "fusion_p95_ms",
)
FRAME_FIELDS = (
    "frame_id", "decision", "flags", "applied_scale", "points", "eval_abs_rel_before", "eval_abs_rel_after",
    "eval_rmse_before_m", "eval_rmse_after_m", "eval_delta1_before", "eval_delta1_after",
    "eval_map_accuracy_mean_before_m", "eval_map_accuracy_mean_after_m",
    "eval_map_accuracy_median_before_m", "eval_map_accuracy_median_after_m",
)
U02_SHARED = ("config_sha256", "decisions", "sources")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _decisions(rows):
    return [{"frame_id": r["frame_id"], "decision": r["decision"], "flags": r["flags"],
             "applied_scale": r["applied_scale"]} for r in rows]


def preflight(comparison_run, slam_run, geometry_run, config_path, u02_summary):
    """Every refusal happens here, before a run directory exists; no GT is read."""
    config, config_sha256 = load_config(config_path)
    u02 = _read_json(u02_summary)
    missing = [key for key in U02_SHARED if key not in u02]
    if missing:
        raise ValueError(f"U-02 summary lacks {missing}")
    if config_sha256 != u02["config_sha256"]:
        raise ValueError(f"robust_fusion config sha256 {config_sha256} differs from the frozen U-02 hash "
                         f"{u02['config_sha256']}; refusing to run")
    sources = load_sources(comparison_run, slam_run, geometry_run)
    if sources.provenance != u02["sources"]:
        raise ValueError("source runs differ from the provenance recorded in the U-02 summary")
    check_config_against_sources(config, sources)
    pairs, withheld = rebuild_pairs(sources.inputs, sources.mapping)
    residual_check = check_recorded_residuals(sources.global_dir / "residuals.csv", pairs, withheld)
    tracking, tracking_info = tracking_states(slam_run, sources.inputs.slam)
    began = time.perf_counter()
    signals = frame_signals(sources, pairs, withheld, tracking)
    rows = anchor_gate_rows(sources, pairs, withheld, signals, config)
    signals_ms = (time.perf_counter() - began) * 1000
    if _decisions(rows) != u02["decisions"]:
        raise ValueError("recomputed gate decisions differ from the committed U-02 decisions")
    return dict(config=config, config_sha256=config_sha256, u02=u02, sources=sources, signals=signals, rows=rows,
                residual_check=residual_check, tracking_info=tracking_info, signals_ms=signals_ms)


def _frame_points(prediction, cameras, index, scale, mapping):
    """Exactly the merged run_mapping per-keyframe back-projection."""
    _, grid = prediction_grid(prediction, cameras["K"][index], cameras["image_size_wh"][index])
    return depth_points(prediction, metric_pose(cameras["T_wc"][index], scale),
                        distortion=cameras["distortion"][index] if grid == "raw_distorted" else None,
                        min_depth_m=mapping["min_depth_m"], max_depth_m=mapping["max_depth_m"],
                        confidence_threshold=mapping["confidence_threshold"], pixel_stride=mapping["pixel_stride"])


def fuse(cameras, predictions, frame_ids, scale, mapping):
    """The merged run_mapping fusion loop restricted to frame_ids (timestamp order, keyframe_interval)."""
    keep = set(frame_ids)
    fusion = VoxelFusion(mapping["voxel_size_m"], mapping["max_voxels"])
    per_frame, frame_ms = [], []
    for index in np.argsort(cameras["timestamp_s"])[::mapping["keyframe_interval"]]:
        frame_id = int(cameras["frame_id"][index])
        if frame_id not in keep:
            continue
        began = time.perf_counter()
        points = _frame_points(predictions[frame_id], cameras, index, scale, mapping)
        if not len(points):
            raise ValueError(f"all dense points filtered from keyframe {frame_id}")
        fusion.add(points)
        per_frame.append({"frame_id": frame_id, "points": len(points)})
        frame_ms.append((time.perf_counter() - began) * 1000)
    if not per_frame:
        raise ValueError("no keyframe selected for fusion")
    cloud, counts = fusion.cloud(mapping["min_voxel_observations"])
    if mapping["statistical_neighbors"]:
        kept = statistical_filter(cloud, neighbors=mapping["statistical_neighbors"],
                                  std_ratio=mapping["statistical_std_ratio"])
        cloud, counts = cloud[kept], counts[kept]
    if not len(cloud):
        raise ValueError("fusion filters removed every voxel")
    return cloud, counts, per_frame, frame_ms, fusion.input_points


def reproduction_check(control_npz, recorded_npz, voxel_size_m):
    """Plan §3.5: byte-identical arrays, else identical voxel keys/counts and centroids within
    |Δ| <= γ_n · max|x|, γ_n = n·u/(1 − n·u), u = 2⁻⁵³. Anything else is a defect."""
    arrays = []
    for path in (control_npz, recorded_npz):
        with np.load(path, allow_pickle=False) as archive:
            arrays.append((archive["xyz_m"], archive["observation_count"]))
    (control, control_counts), (recorded, recorded_counts) = arrays
    result = {"points": int(len(recorded)), "numpy": np.__version__}
    if np.array_equal(control, recorded) and np.array_equal(control_counts, recorded_counts):
        return {**result, "byte_identical_arrays": True, "max_abs_difference_m": 0.0, "max_bound_ratio": 0.0}
    if control.shape != recorded.shape or not np.array_equal(control_counts, recorded_counts):
        raise ValueError("control map voxel count or observation counts differ from the recorded P1-global map")
    if not np.array_equal(np.floor(control / voxel_size_m), np.floor(recorded / voxel_size_m)):
        raise ValueError("control map voxel keys differ from the recorded P1-global map")
    unit = 2.0 ** -53
    n = recorded_counts.astype(float)[:, None]
    # Contributing points lie inside their voxel, so per coordinate |x| <= |centroid| + voxel size.
    bound = n * unit / (1 - n * unit) * (np.abs(recorded) + voxel_size_m)
    difference = np.abs(control - recorded)
    if np.any(difference > bound):
        raise ValueError("control map centroids exceed the float64 summation error bound")
    return {**result, "byte_identical_arrays": False, "max_abs_difference_m": float(difference.max()),
            "max_bound_ratio": float((difference / bound).max())}


def _percentiles(values):
    return ({"p50_ms": float(np.median(values)), "p95_ms": float(np.percentile(values, 95))} if len(values)
            else {"p50_ms": None, "p95_ms": None})


def _map_row(method, role, evaluated, *, frames_fused, frames_rejected, input_points, map_voxels, ate, timing):
    row = {"method": method, "role": role, "frames_fused": frames_fused, "frames_rejected": frames_rejected,
           "input_points": input_points, "map_voxels": map_voxels, "eval_estimate_points": evaluated["estimate_points"],
           "eval_ate_se3_rmse_m": ate, "fusion_median_ms": timing.get("fusion_median_ms"),
           "fusion_p95_ms": timing.get("fusion_p95_ms")}
    for key in ("accuracy_mean_m", "accuracy_median_m", "completeness_mean_m", "completeness_median_m", "chamfer_l1_m"):
        row[f"eval_{key}"] = evaluated[key]
    for score in evaluated["fscores"]:
        for key in ("precision", "recall", "fscore"):
            row[f"eval_{key}_{score['threshold_m']:g}m"] = score[key]
    return row


def _same_map_metrics(control, recorded, identical):
    """Exact equality for byte-identical maps; otherwise the float64 tolerance of §3.5."""
    if identical:
        return control == recorded
    flat = lambda m: [m[k] for k in ("accuracy_mean_m", "accuracy_median_m", "completeness_mean_m",
                                     "completeness_median_m", "chamfer_l1_m")] + \
        [s[k] for s in m["fscores"] for k in ("precision", "recall", "fscore")]
    return (control["estimate_points"] == recorded["estimate_points"]
            and np.allclose(flat(control), flat(recorded), rtol=0, atol=1e-9))


def _plot_comparison(path, rows):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    series = (("eval_accuracy_mean_m", "Accuracy (mean)", "#2a78d6"),
              ("eval_completeness_mean_m", "Completeness (mean)", "#eb6834"),
              ("eval_chamfer_l1_m", "Chamfer-L1", "#1baf7a"))
    ramp = (("0.02", "#c8c2f2"), ("0.05", "#9085e9"), ("0.1", "#4b3bb0"))
    labels = [f"{r['method']}\n{r['frames_fused']} kf" if r["frames_fused"] is not None else f"{r['method']}\nsparse"
              for r in rows]
    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True, facecolor="#fcfcfb")
    for axis, entries, ylabel in ((axes[0], series, "Distance to reference [m] (lower is better)"),
                                  (axes[1], [(f"eval_fscore_{t}m", f"F-score @ {float(t) * 100:g} cm", c)
                                             for t, c in ramp], "F-score (higher is better)")):
        width = 0.8 / len(entries)
        for k, (field, label, color) in enumerate(entries):
            axis.bar(x + (k - (len(entries) - 1) / 2) * width, [r[field] for r in rows], width=width * 0.9,
                     color=color, label=label, edgecolor="#fcfcfb", linewidth=1)
        axis.set_facecolor("#fcfcfb")
        axis.set_ylabel(ylabel, color=muted, fontsize=9)
        axis.set_xticks(x, labels, rotation=30, ha="right", fontsize=8, color=ink)
        axis.tick_params(axis="y", colors=muted, labelsize=8)
        axis.yaxis.grid(True, color=grid, linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            axis.spines[side].set_color(grid)
        axis.legend(fontsize=8, frameon=False, labelcolor=ink)
    fig.suptitle("P1-robust U-03, TUM fr1/xyz smoke-200: offline maps, evaluation-only metrics "
                 "(B1 uses GT depth; B0 is the sparse map)", fontsize=10, color=ink)
    fig.savefig(path, dpi=100, facecolor="#fcfcfb")
    plt.close(fig)


def run_robust_fusion(repo_root, comparison_run, slam_run, geometry_run, sequence_dir, manifest_path, config_path,
                      u02_summary, *, run_id, output_root=None, plot=False):
    """Preflight refusals write nothing; later failures leave a terminal run.json."""
    checked = preflight(comparison_run, slam_run, geometry_run, config_path, u02_summary)
    sources, config, rows = checked["sources"], checked["config"], checked["rows"]
    mapping, inputs = sources.mapping, sources.inputs
    state, host = collect_git_state(repo_root), collect_host_info()
    record = dict(run_id=run_id, git_commit=state.commit, dirty_worktree=state.dirty, dataset=inputs.slam["dataset"],
                  method="P1-global", model=inputs.geometry["model"], slam=inputs.slam["slam"],
                  alignment={"method": sources.global_record["alignment"]["method"],
                             "thresholds": sources.global_record["alignment"]["thresholds"]},
                  config={"control_label": "P1-global control plus P1-anchored and P1-anchored+gate variants",
                          "sources": sources.provenance, "mapping": mapping, "robust_fusion": config,
                          "robust_fusion_sha256": checked["config_sha256"],
                          "u02_summary": {"file": Path(u02_summary).name, "sha256": sha256_file(u02_summary),
                                          "run_id": checked["u02"].get("run_id")},
                          "scope": "offline retained-keyframe maps; GT-free Phase A written before evaluation"},
                  hardware={"gpu": None, "cpu": host.cpu, "ram_gb": host.ram_gb},
                  environment={"python": platform.python_version(), "numpy": np.__version__},
                  seed=mapping["seed"], started_at=format_utc(datetime.now(timezone.utc)),
                  status="running", reason=None, artifacts={})
    build_run_manifest(**record)
    directory = Path(output_root or Path(repo_root) / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), directory)
    try:
        # Phase A: GT-free. Control first, with the unchanged public mapping entry point.
        control_dir = run_mapping(Path(repo_root), Path(slam_run), Path(geometry_run), run_id=f"{run_id}.control",
                                  config={**mapping, "plot": False}, output_root=directory / "methods")
        control_record = load_run_manifest(control_dir / "run.json")
        record["artifacts"]["control_run"] = (control_dir.relative_to(directory) / "run.json").as_posix()
        if control_record["status"] != "ok":
            raise RuntimeError(f"control run_mapping failed: {control_record['reason']}")
        scale = float(sources.alignment["scale"])
        if _read_json(control_dir / "alignment.json")["scale"] != scale:
            raise ValueError("control global scale differs from the recorded P1-global scale")
        reproduction = reproduction_check(control_dir / "map.npz", sources.global_dir / "map.npz",
                                          mapping["voxel_size_m"])
        reproduction["residuals_csv_identical"] = (sha256_file(control_dir / "residuals.csv")
                                                   == sources.provenance["residuals_sha256"])
        write_csv(directory / "frame_signals.csv", SIGNAL_FIELDS, checked["signals"])
        write_csv(directory / "anchor_gate.csv", ANCHOR_GATE_FIELDS, rows)
        record["artifacts"].update(frame_signals="frame_signals.csv", anchor_gate="anchor_gate.csv")
        recorded_hashes = checked["u02"].get("run_artifact_sha256", {})
        for name in ("frame_signals.csv", "anchor_gate.csv"):
            if name in recorded_hashes and sha256_file(directory / name) != recorded_hashes[name]:
                raise ValueError(f"{name} differs byte-wise from the committed U-02 run artifact")
        cameras = inputs.snapshot.keyframes
        anchored, anchor_ms = {}, []
        for row in rows:
            began = time.perf_counter()
            anchored[row["frame_id"]] = anchored_prediction(inputs.predictions[row["frame_id"]],
                                                            row["applied_scale"] if row["anchor_applied"] else None)
            anchor_ms.append((time.perf_counter() - began) * 1000)
        control_metrics = _read_json(control_dir / "metrics.json")
        all_frames = [item["frame_id"] for item in control_metrics["per_frame"]]
        accepted = [r["frame_id"] for r in rows if r["decision"] == "accept"]
        rejected = [r["frame_id"] for r in rows if r["decision"] == "reject"]
        # The variant fusion loop must reproduce the control map byte-for-byte on unanchored depth,
        # so the variants differ from the control only by anchored depth and gating.
        loop_cloud, loop_counts, *_ = fuse(cameras, inputs.predictions, all_frames, scale, mapping)
        with np.load(control_dir / "map.npz", allow_pickle=False) as archive:
            if not (np.array_equal(loop_cloud, archive["xyz_m"]) and np.array_equal(loop_counts,
                                                                                     archive["observation_count"])):
                raise ValueError("variant fusion loop does not reproduce the control map")
        reproduction["variant_fusion_loop_reproduces_control"] = True
        variants = {}
        for name, frames in ((ANCHORED, all_frames), (GATED, [f for f in all_frames if f in accepted])):
            path = directory / "variants" / VARIANT_DIRS[name]
            path.mkdir(parents=True)
            if not frames:
                variants[name] = {"status": "failed", "reason": "the pre-registered gate rejected every keyframe",
                                  "frames": [], "rejected_frames": rejected}
                continue
            cloud, counts, per_frame, frame_ms, input_points = fuse(cameras, anchored, frames, scale, mapping)
            write_ply(path / "map.ply", cloud)
            np.savez_compressed(path / "map.npz", xyz_m=cloud, observation_count=counts)
            variants[name] = {"status": "ok", "reason": None, "frames": frames,
                              "rejected_frames": [f for f in all_frames if f not in frames],
                              "per_frame": per_frame, "input_points": input_points, "map_voxels": len(cloud),
                              "map": f"variants/{VARIANT_DIRS[name]}/map.npz",
                              "fusion_per_keyframe_ms": frame_ms, "fusion_median_ms": float(np.median(frame_ms)),
                              "fusion_p95_ms": float(np.percentile(frame_ms, 95))}
        if variants[ANCHORED]["frames"] != all_frames:
            raise ValueError("P1-anchored must fuse exactly the control keyframe set")
        control_timing = _read_json(control_dir / "timing.json")
        cpu = {"label": CPU_LABEL,
               "signals_and_gate_total_ms": checked["signals_ms"],
               "signals_and_gate_mean_ms_per_keyframe": checked["signals_ms"] / len(rows),
               "signals_and_gate_per_keyframe_percentiles": None,
               "signals_and_gate_percentiles_reason": "U-01/U-02 signals are computed in one batch over all keyframes",
               "anchoring_per_keyframe": _percentiles(anchor_ms),
               "fusion_per_keyframe": {name: _percentiles(v.get("fusion_per_keyframe_ms", [])) for name, v in variants.items()},
               "control_fusion_per_keyframe": {"p50_ms": control_timing["fusion_median_ms"],
                                               "p95_ms": control_timing["fusion_p95_ms"]}}
        write_json(directory / "phase_a.json", {
            "scope": "GT-free; written before any ground truth is opened", "keyframes": len(rows),
            "accepted": accepted, "rejected": rejected, "decisions": _decisions(rows),
            "decisions_equal_u02": True, "config_sha256": checked["config_sha256"],
            "config_sha256_equal_u02": True, "global_scale": scale, "reproduction": reproduction,
            "residuals_crosscheck": checked["residual_check"], "tracking": checked["tracking_info"],
            "control_frames": all_frames, "variants": variants, "cpu_overhead": cpu, "sources": sources.provenance})
        record["artifacts"].update(phase_a="phase_a.json", variants="variants")
        # Phase A is now immutable on disk; ground truth starts below.
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)

        oracle, rebuilt_reference, _, _, _ = load_oracle_inputs(
            inputs, sequence_dir, manifest_path, mapping,
            max_timestamp_delta_s=sources.comparison["config"]["max_timestamp_delta_s"])
        comparison_dir = sources.comparison_dir
        with np.load(comparison_dir / "reference_evaluation_only.npz", allow_pickle=False) as archive:
            reference = archive["xyz_m"]
        transform = _read_json(comparison_dir / "trajectory_evaluation.json")["P1_global_se3"]["evaluation_transform"]
        rotation, translation = np.asarray(transform["R"]), np.asarray(transform["t"])
        recorded = {}
        for name in (*RECORDED, "P1-global"):
            detail = _read_json(comparison_dir / "evaluation" / f"{name}.json")
            if detail["shared_map_evaluation_transform"] != transform:
                raise ValueError(f"recorded {name} row used a different evaluation transform")
            recorded[name] = detail
        evaluation = {"voxel_size_m": config["map_evaluation"]["voxel_size_m"]["value"],
                      "thresholds_m": config["map_evaluation"]["thresholds_m"]["value"],
                      "crop_bounds": sources.comparison["config"]["crop_bounds_m"]}
        evaluate = lambda points: evaluate_map(points @ rotation.T + translation, reference,
                                               voxel_size_m=evaluation["voxel_size_m"],
                                               thresholds_m=evaluation["thresholds_m"],
                                               crop_bounds=evaluation["crop_bounds"])
        ate = recorded["P1-global"]["trajectory"]["ate_rmse_m"]
        with np.load(control_dir / "map.npz", allow_pickle=False) as archive:
            control_eval = evaluate(archive["xyz_m"])
        if not _same_map_metrics(control_eval, recorded["P1-global"]["map"], reproduction["byte_identical_arrays"]):
            raise ValueError("control map metrics differ from the recorded P1-global row")
        table = [_map_row(CONTROL, "control (reproduced recorded P1-global)", control_eval,
                          frames_fused=len(all_frames), frames_rejected=0, input_points=control_metrics["input_points"],
                          map_voxels=control_metrics["map_points"], ate=ate, timing=control_timing)]
        details = {CONTROL: control_eval}
        for name in (ANCHORED, GATED):
            variant = variants[name]
            if variant["status"] != "ok":
                details[name] = {"status": "failed", "reason": variant["reason"]}
                continue
            with np.load(directory / variant["map"], allow_pickle=False) as archive:
                details[name] = evaluate(archive["xyz_m"])
            table.append(_map_row(name, "variant", details[name], frames_fused=len(variant["frames"]),
                                  frames_rejected=len(variant["rejected_frames"]), input_points=variant["input_points"],
                                  map_voxels=variant["map_voxels"], ate=ate, timing=variant))
        for name in RECORDED:
            detail = recorded[name]
            table.append(_map_row(name, "recorded reference row (same transform, reference and voxel grid)",
                                  detail["map"], frames_fused=None if name == "B0-shared-scale" else len(all_frames),
                                  frames_rejected=None, input_points=None, map_voxels=None,
                                  ate=detail["trajectory"]["ate_rmse_m"], timing=detail["fusion_timing"]))
        write_csv(directory / "comparison.csv", COMPARISON_FIELDS, table)
        from scipy.spatial import cKDTree

        tree = cKDTree(reference)
        index_of = {int(f): i for i, f in enumerate(cameras["frame_id"])}
        frame_rows = []
        for row in rows:
            frame_id, i = row["frame_id"], index_of[row["frame_id"]]
            entry = {"frame_id": frame_id, "decision": row["decision"], "flags": row["flags"],
                     "applied_scale": row["applied_scale"]}
            for suffix, prediction in (("before", inputs.predictions[frame_id]), ("after", anchored[frame_id])):
                depth = evaluate_depth(prediction, oracle[frame_id].depth_m)
                points = _frame_points(prediction, cameras, i, scale, mapping)
                distances, _ = tree.query(points @ rotation.T + translation, k=1)
                entry.update({f"eval_abs_rel_{suffix}": depth.abs_rel, f"eval_rmse_{suffix}_m": depth.rmse_m,
                              f"eval_delta1_{suffix}": depth.delta1,
                              f"eval_map_accuracy_mean_{suffix}_m": float(distances.mean()),
                              f"eval_map_accuracy_median_{suffix}_m": float(np.median(distances)), "points": len(points)})
            frame_rows.append(entry)
        write_csv(directory / "frame_evaluation.csv", FRAME_FIELDS, frame_rows)
        improved = lambda before, after: sum(r[after] < r[before] for r in frame_rows)
        delta = {name: {key: details[name][key] - control_eval[key] for key in
                        ("accuracy_mean_m", "accuracy_median_m", "completeness_mean_m", "completeness_median_m",
                         "chamfer_l1_m")} | {f"fscore_{s['threshold_m']:g}m": s["fscore"] - c["fscore"]
                                            for s, c in zip(details[name]["fscores"], control_eval["fscores"])}
                 for name in (ANCHORED, GATED) if variants[name]["status"] == "ok"}
        rejected_points = sum(p["points"] for p in variants[ANCHORED]["per_frame"] if p["frame_id"] in rejected)
        write_json(directory / "robust_summary.json", {
            "scope": "evaluation_only metrics of offline maps; GT-free Phase A decisions; no real-time claim",
            "keyframes": len(rows), "accepted": len(accepted), "rejected": len(rejected),
            "rejected_frames": rejected, "rejected_points_before_voxelization": rejected_points,
            "variants": {name: {"status": v["status"], "reason": v["reason"], "frames_fused": len(v["frames"])}
                         for name, v in variants.items()},
            "map_evaluation": {**evaluation, "transform": "recorded P1_global_se3 evaluation_transform",
                               "reference": "recorded reference_evaluation_only.npz",
                               "reference_rebuilt_identical": bool(np.array_equal(rebuilt_reference, reference))},
            "control_matches_recorded_p1_global": True, "reproduction": reproduction,
            "maps": details, "delta_vs_control": delta, "rows": table,
            "per_frame_depth": {"frames": len(frame_rows),
                                "abs_rel_improved": improved("eval_abs_rel_before", "eval_abs_rel_after"),
                                "map_accuracy_mean_improved": improved("eval_map_accuracy_mean_before_m",
                                                                       "eval_map_accuracy_mean_after_m"),
                                "median_abs_rel_before": float(np.median([r["eval_abs_rel_before"] for r in frame_rows])),
                                "median_abs_rel_after": float(np.median([r["eval_abs_rel_after"] for r in frame_rows])),
                                "gt_depth_source": "evaluation.oracle grid recomputation (same for before and after)"},
            "trajectory": "all variants use the recorded P1-global metric poses; ATE copied from the recorded row",
            "cpu_overhead": cpu, "tracking": checked["tracking_info"], "real_time_claim": False})
        record["artifacts"].update(comparison_csv="comparison.csv", frame_evaluation="frame_evaluation.csv",
                                   summary="robust_summary.json")
        if plot:
            _plot_comparison(directory / "comparison.png", table)
            record["artifacts"]["comparison_plot"] = "comparison.png"
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: robust fusion stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"robust_fusion_failed: {type(exc).__name__}: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory


__all__ = ["fuse", "preflight", "reproduction_check", "run_robust_fusion"]
