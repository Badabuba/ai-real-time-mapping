"""Recorded B0/B1/P1-raw/P1-global artifact comparison, plus fusion ablations.

The proposed map is completed before any GT is opened. B1 reuses the P1 scale.
Map metrics use one P1-trajectory SE(3) evaluation transform for every method;
no per-map ICP or Sim(3) can conceal recovered metric-scale errors.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np

from rt_mapping.alignment.correspondences import build_correspondences, prediction_grid
from rt_mapping.alignment.causal import causal_window_scales
from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, load_run_manifest, write_run_manifest
from rt_mapping.evaluation.map_geometry import evaluate_map
from rt_mapping.evaluation.oracle import load_oracle_inputs
from rt_mapping.evaluation.trajectory import trajectory_metrics
from rt_mapping.fusion import VoxelFusion, depth_points, metric_pose, write_ply
from rt_mapping.fusion.voxel import statistical_filter
from rt_mapping.runs.artifacts import load_mapping_inputs
from rt_mapping.runs.geometry_run import collect_git_state, collect_host_info
from rt_mapping.runs.mapping_run import _json, _trajectory, run_mapping, validate_config


DEFAULT_COMPARISON = {"mapping": {}, "thresholds_m": [0.02, 0.05, 0.1], "crop_bounds_m": None,
                      "keyframe_intervals": [2, 5], "confidence_thresholds": [], "max_timestamp_delta_s": 0.02,
                      "causal_window_frames": 0}


def comparison_config(value):
    if not isinstance(value, dict) or set(value) - DEFAULT_COMPARISON.keys():
        raise ValueError("unknown comparison config keys")
    config = {**DEFAULT_COMPARISON, **value}
    config["mapping"] = validate_config(config["mapping"])
    if type(config["causal_window_frames"]) is not int or config["causal_window_frames"] < 0:
        raise ValueError("causal_window_frames must be a nonnegative integer; zero disables the conditional ablation")
    intervals, thresholds = config["keyframe_intervals"], config["thresholds_m"]
    if (not isinstance(intervals, list) or len(set(intervals)) != len(intervals)
            or any(type(i) is not int or i <= 1 for i in intervals)):
        raise ValueError("keyframe intervals must be unique integers > 1")
    values = np.asarray(thresholds, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or np.any(values <= 0) or np.any(np.diff(values) <= 0):
        raise ValueError("map thresholds must be positive, finite and strictly increasing")
    confidence = config["confidence_thresholds"]
    if (not isinstance(confidence, list) or any(type(c) not in (float, int) or not np.isfinite(c) for c in confidence)
            or len(set(confidence)) != len(confidence)):
        raise ValueError("confidence thresholds must be unique finite numbers")
    if not np.isfinite(config["max_timestamp_delta_s"]) or config["max_timestamp_delta_s"] < 0:
        raise ValueError("invalid GT timestamp tolerance")
    crop = config["crop_bounds_m"]
    if crop is not None:
        bounds = np.asarray(crop, dtype=float)
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[0] >= bounds[1]):
            raise ValueError("invalid common metric crop bounds")
    return config


def _child_fusion(root, inputs, parent_record, predictions, *, child_id, method, scale, config, label):
    record = {key: value for key, value in parent_record.items() if key != "schema"}
    record.update(run_id=child_id, method=method, model=None if method == "B1" else inputs.geometry["model"],
        alignment=({"method": "causal_robust_median", "thresholds": {"residual_m": config["residual_threshold_m"]}}
                   if method == "P1-window" else {"method": "shared_P1_global_scale", "thresholds": {"scale": scale}}
                   if method == "P1-global" else None),
        config={**config, "control_label": label, "scale": {str(k): v for k,v in scale.items()} if isinstance(scale, dict) else scale,
                "scale_source": "fixed unit-scale assumption" if method == "P1-raw" else
                                "causal past/current window" if method == "P1-window" else "recorded P1-global calibration",
                "source_runs": {"slam": inputs.slam["run_id"], "geometry": inputs.geometry["run_id"]}},
        status="running", reason=None, artifacts={})
    path = root / child_id
    path.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), path)
    began = time.perf_counter()
    frame_times = []
    try:
        fusion = VoxelFusion(config["voxel_size_m"], config["max_voxels"])
        cameras = inputs.snapshot.keyframes
        for i in np.argsort(cameras["timestamp_s"])[::config["keyframe_interval"]]:
            start = time.perf_counter()
            prediction = predictions[int(cameras["frame_id"][i])]
            _, grid = prediction_grid(prediction, cameras["K"][i], cameras["image_size_wh"][i])
            current_scale = scale[int(cameras["frame_id"][i])] if isinstance(scale, dict) else scale
            points = depth_points(prediction, metric_pose(cameras["T_wc"][i], current_scale),
                distortion=cameras["distortion"][i] if grid == "raw_distorted" else None,
                min_depth_m=config["min_depth_m"], max_depth_m=config["max_depth_m"],
                confidence_threshold=config["confidence_threshold"], pixel_stride=config["pixel_stride"])
            if not len(points):
                raise ValueError(f"no valid dense points in selected frame {prediction.frame_id}")
            fusion.add(points)
            frame_times.append((time.perf_counter()-start)*1000)
        cloud, counts = fusion.cloud(config["min_voxel_observations"])
        if config["statistical_neighbors"]:
            keep = statistical_filter(cloud, neighbors=config["statistical_neighbors"], std_ratio=config["statistical_std_ratio"])
            cloud, counts = cloud[keep], counts[keep]
        write_ply(path / "map.ply", cloud)
        np.savez_compressed(path / "map.npz", xyz_m=cloud, observation_count=counts)
        _trajectory(path / "trajectory_metric.csv", cameras, scale)
        _json(path / "metrics.json", {"map_points": len(cloud), "input_points": fusion.input_points,
            "fused_keyframes": len(frame_times), "scale": {str(k): v for k,v in scale.items()} if isinstance(scale, dict) else scale, "label": label,
            "ground_truth_input": method == "B1", "real_time_claim": False})
        _json(path / "timing.json", {"fusion_per_keyframe_ms": frame_times,
            "fusion_median_ms": float(np.median(frame_times)), "fusion_p95_ms": float(np.percentile(frame_times, 95)),
            "wall_clock_s": time.perf_counter()-began, "scope": "CPU fusion only; excludes SLAM/model inference"})
        record.update(status="ok", artifacts={"map": "map.ply", "map_arrays": "map.npz",
            "trajectory": "trajectory_metric.csv", "metrics": "metrics.json", "timing": "timing.json"})
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: fusion control stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"fusion_failed: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), path, overwrite=True)
    if record["status"] != "ok":
        raise RuntimeError(record["reason"])
    return path


def _report(directory, rows, notes, *, plot):
    fields = ["method", "map_points", "accuracy_mean_m", "completeness_mean_m", "chamfer_l1_m",
              "ate_se3_rmse_m", "rpe_translation_rmse_m", "rpe_rotation_rmse_deg", "fusion_median_ms", "fusion_p95_ms"]
    fields += sorted({key for row in rows for key in row if key.startswith("fscore_")})
    with (directory / "comparison.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Alignment/fusion comparison", "", *[f"- {note}" for note in notes], "",
             "| Method | Points | Accuracy [m] | Completeness [m] | Chamfer-L1 [m] | ATE SE(3) [m] |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['method']} | {row['map_points']} | {row['accuracy_mean_m']:.6f} | "
                     f"{row['completeness_mean_m']:.6f} | {row['chamfer_l1_m']:.6f} | {row['ate_se3_rmse_m']:.6f} |")
    (directory / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
        if any(note.startswith("SYNTHETIC") for note in notes):
            fig.suptitle("Synthetic correctness fixture — not a real-data benchmark")
        indices = np.arange(len(rows))
        for offset, field, label in ((-0.2, "accuracy_mean_m", "Accuracy"), (0., "completeness_mean_m", "Completeness"),
                                      (0.2, "chamfer_l1_m", "Chamfer-L1")):
            axes[0].bar(indices+offset, [r[field] for r in rows], width=0.2, label=label)
        axes[0].set(ylabel="Distance [m] (lower is better)")
        axes[0].legend(fontsize=8)
        axes[1].bar(indices, [r["map_points"] for r in rows], color="#4c78a8")
        axes[1].set(ylabel="Points after common evaluation voxel/crop")
        for axis in axes:
            axis.set_xticks(indices, [r["method"] for r in rows], rotation=35, ha="right", fontsize=8)
        fig.savefig(directory / "comparison.png", dpi=150)
        plt.close(fig)


def run_comparison(repo_root, slam_run, geometry_run, sequence_dir, manifest_path, *, run_id,
                   config=None, output_root=None):
    if not isinstance(run_id, str) or len(run_id) > 110:
        raise ValueError("comparison run ID must leave room for child suffixes (max 110 characters)")
    config = comparison_config({} if config is None else config)
    mapping = config["mapping"]
    inputs = load_mapping_inputs(slam_run, geometry_run)
    state, host = collect_git_state(repo_root), collect_host_info()
    record = dict(run_id=run_id, git_commit=state.commit, dirty_worktree=state.dirty,
        dataset=inputs.slam["dataset"], method="P1-global", model=inputs.geometry["model"], slam=inputs.slam["slam"],
        alignment={"method": "robust_median", "thresholds": {"residual_m": mapping["residual_threshold_m"]}},
        config={**config, "scope": "alignment/fusion artifact benchmark; retained keyframes; not full-system timing"},
        hardware={"gpu": None, "cpu": host.cpu, "ram_gb": host.ram_gb},
        environment={"python": platform.python_version(), "numpy": np.__version__}, seed=mapping["seed"],
        started_at=format_utc(datetime.now(timezone.utc)), status="running", reason=None, artifacts={})
    build_run_manifest(**record)
    directory = Path(output_root or Path(repo_root) / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), directory)
    try:
        # This stage has no access to sequence_dir, GT poses or GT depth.
        global_path = run_mapping(Path(repo_root), Path(slam_run), Path(geometry_run), run_id=run_id+".global",
                                  config=mapping, output_root=directory / "methods")
        global_record = load_run_manifest(global_path / "run.json")
        record["artifacts"]["global_run"] = str(global_path.relative_to(directory).as_posix())+"/run.json"
        if global_record["status"] != "ok":
            raise RuntimeError(f"proposed alignment failed: {global_record['reason']}")
        alignment = json.loads((global_path / "alignment.json").read_text(encoding="utf-8"))
        scale = alignment["scale"]
        # Ground truth starts here, after the P1 result is immutable.
        oracle, reference, gt_poses, gt_times, gt_provenance = load_oracle_inputs(inputs, sequence_dir, manifest_path, mapping,
                                                max_timestamp_delta_s=config["max_timestamp_delta_s"])
        _json(directory / "inputs.json", {"pipeline": inputs.provenance, "evaluation_only": gt_provenance})
        record["artifacts"]["inputs"] = "inputs.json"
        np.savez_compressed(directory / "reference_evaluation_only.npz", xyz_m=reference)
        record["artifacts"]["reference"] = "reference_evaluation_only.npz"
        cameras = inputs.snapshot.keyframes
        metric_poses = np.array([metric_pose(pose, scale) for pose in cameras["T_wc"]])
        trajectory = trajectory_metrics(cameras["timestamp_s"], metric_poses, gt_times, gt_poses, alignment="se3",
                                        max_delta_s=config["max_timestamp_delta_s"])
        baseline_trajectory = trajectory_metrics(cameras["timestamp_s"], cameras["T_wc"], gt_times, gt_poses,
                                                 alignment="sim3", max_delta_s=config["max_timestamp_delta_s"])
        transform = trajectory["evaluation_transform"]
        rotation, translation = np.asarray(transform["R"]), np.asarray(transform["t"])
        _json(directory / "trajectory_evaluation.json", {"P1_global_se3": trajectory, "B0_sim3": baseline_trajectory,
            "scope": "retained keyframes, not all-frame trajectory/tracking evaluation"})
        record["artifacts"]["trajectory_evaluation"] = "trajectory_evaluation.json"
        paths = [("P1-global", global_path, scale)]
        paths.append(("P1-raw", _child_fusion(directory / "methods", inputs, record, inputs.predictions,
            child_id=run_id+".raw", method="P1-raw", scale=1., config=mapping,
            label="Raw pose translations assume scale 1; explicit ablation, no recovered metric scale"), 1.))
        paths.append(("B1-oracle", _child_fusion(directory / "methods", inputs, record, oracle,
            child_id=run_id+".oracle", method="B1", scale=scale, config={**mapping, "confidence_threshold": None},
            label="GT depth control with the same P1-global metric camera poses; scale is not fitted to GT"), scale))
        for interval in config["keyframe_intervals"]:
            paths.append((f"P1-keyframes-{interval}", _child_fusion(directory / "methods", inputs, record, inputs.predictions,
                child_id=f"{run_id}.k{interval}", method="P1-global", scale=scale,
                config={**mapping, "keyframe_interval": interval}, label=f"Every {interval}-th retained keyframe; shared P1 scale"), scale))
        skipped = []
        if config["causal_window_frames"]:
            pairs = build_correspondences(inputs.snapshot, inputs.predictions,
                max_reprojection_error_px=mapping["max_reprojection_error_px"], confidence_threshold=mapping["confidence_threshold"],
                min_depth_m=mapping["min_depth_m"], max_depth_m=mapping["max_depth_m"])
            ordered = cameras["frame_id"][np.argsort(cameras["timestamp_s"])]
            scales, window_diagnostics = causal_window_scales(pairs, ordered,
                window_frames=config["causal_window_frames"], seed=mapping["seed"], validation_fraction=mapping["validation_fraction"],
                threshold_m=mapping["residual_threshold_m"], min_inliers=mapping["min_inliers"],
                min_ratio=mapping["min_inlier_ratio"], min_coverage_bins=mapping["min_coverage_bins"])
            _json(directory / "causal_scales.json", {"method": "P1-window", "frames": window_diagnostics,
                    "future_depth_used": False, "ground_truth_used": False})
            record["artifacts"]["causal_scales"] = "causal_scales.json"
            paths.append(("P1-window", _child_fusion(directory / "methods", inputs, record, inputs.predictions,
                child_id=run_id+".window", method="P1-window", scale=scales, config=mapping,
                label="Causal past/current-window calibration; no global/future fallback"), scales))
        else:
            skipped.append({"ablation": "P1-window", "reason": "conditional_on_development_comparison; disabled in config"})
        has_confidence = all(p.confidence is not None for p in inputs.predictions.values())
        if not has_confidence:
            skipped.append({"ablation": "confidence", "reason": "model_supplies_no_confidence; no fake confidence created"})
        else:
            for index, threshold in enumerate(config["confidence_thresholds"]):
                paths.append((f"P1-confidence-{threshold:g}", _child_fusion(directory / "methods", inputs, record, inputs.predictions,
                    child_id=f"{run_id}.c{index}", method="P1-global", scale=scale,
                    config={**mapping, "confidence_threshold": threshold}, label="Shared scale; confidence filtering only"), scale))
        rows, details = [], {}
        (directory / "evaluation").mkdir()
        baseline_points = inputs.snapshot.landmarks["xyz_slam"] * scale
        variants = [("B0-shared-scale", baseline_points, None, scale), *paths]
        for item in variants:
            if item[0] == "B0-shared-scale":
                name, points, path, method_scale = item
            else:
                name, path, method_scale = item
                with np.load(path / "map.npz", allow_pickle=False) as archive:
                    points = archive["xyz_m"]
            evaluated = evaluate_map(points @ rotation.T + translation, reference, voxel_size_m=mapping["voxel_size_m"],
                                      thresholds_m=config["thresholds_m"], crop_bounds=config["crop_bounds_m"])
            poses = np.array([metric_pose(pose, method_scale[int(frame_id)] if isinstance(method_scale, dict) else method_scale)
                              for frame_id, pose in zip(cameras["frame_id"], cameras["T_wc"])])
            pose_metrics = trajectory_metrics(cameras["timestamp_s"], poses, gt_times, gt_poses, alignment="se3",
                                               max_delta_s=config["max_timestamp_delta_s"])
            timing = json.loads((path / "timing.json").read_text(encoding="utf-8")) if path else {}
            row = {"method": name, "map_points": evaluated["estimate_points"],
                   **{k: evaluated[k] for k in ("accuracy_mean_m", "completeness_mean_m", "chamfer_l1_m")},
                   "ate_se3_rmse_m": pose_metrics["ate_rmse_m"],
                   "rpe_translation_rmse_m": pose_metrics["rpe_translation_rmse_m"],
                   "rpe_rotation_rmse_deg": pose_metrics["rpe_rotation_rmse_deg"],
                   "fusion_median_ms": timing.get("fusion_median_ms"), "fusion_p95_ms": timing.get("fusion_p95_ms")}
            rows.append(row)
            row.update({f"fscore_{score['threshold_m']:g}m": score["fscore"] for score in evaluated["fscores"]})
            details[name] = {"map": evaluated, "trajectory": pose_metrics, "fusion_timing": timing,
                             "scale": {str(k): v for k,v in method_scale.items()} if isinstance(method_scale, dict) else method_scale,
                             "shared_map_evaluation_transform": transform}
            _json(directory / "evaluation" / f"{name}.json", details[name])
        notes = ["GT depth/poses are evaluation-only except the explicitly labeled B1 control.",
                 "All maps use the same voxel size, crop and P1 trajectory SE(3) world transform; no per-map alignment.",
                 "B0-shared-scale reuses P1 scale only for a fair sparse/dense map comparison; B0 Sim(3) ATE is separate.",
                 "RPE delta=1 matched retained-keyframe pair; full-frame tracking/timing are not evaluated.",
                 "Fusion timing excludes model and SLAM inference. No real-time claim."]
        if inputs.slam["dataset"]["name"] == "synthetic":
            notes.insert(0, "SYNTHETIC CORRECTNESS FIXTURE — not a TUM or scientific benchmark result.")
        _json(directory / "metrics.json", {"rows": rows, "skipped_ablations": skipped, "notes": notes,
            "dataset": record["dataset"], "hardware": record["hardware"], "real_time_claim": False})
        _report(directory, rows, notes, plot=mapping["plot"])
        record["artifacts"].update(metrics="metrics.json", comparison_csv="comparison.csv", report="report.md", evaluation="evaluation")
        if mapping["plot"]:
            record["artifacts"]["comparison_plot"] = "comparison.png"
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: comparison stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"comparison_failed: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory
