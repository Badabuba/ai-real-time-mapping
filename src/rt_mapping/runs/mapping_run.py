"""Offline WP3/WP4: verified WP1/WP2 run artifacts -> metric keyframe map.

No dataset or ground-truth files are read. The global scale is estimated on
calibration landmarks; different landmark IDs are withheld for validation.
This is artifact integration, not a launcher for native SLAM/CUDA inference.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np

from rt_mapping.alignment import AlignmentError, estimate_scale
from rt_mapping.alignment.correspondences import build_correspondences, prediction_grid
from rt_mapping.contracts.geometry import load_prediction
from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, load_run_manifest, write_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.fusion import VoxelFusion, depth_points, metric_pose, write_ply
from rt_mapping.fusion.voxel import statistical_filter
from rt_mapping.slam.sparse import SparseSnapshot, check_sparse_export

from .geometry_run import collect_git_state, collect_host_info


DEFAULT_CONFIG = {
    "seed": 0, "residual_threshold_m": 0.10, "min_inliers": 30,
    "min_inlier_ratio": 0.5, "min_coverage_bins": 4, "validation_fraction": 0.2,
    "max_reprojection_error_px": 3.0, "confidence_threshold": None,
    "min_depth_m": 0.1, "max_depth_m": 8.0, "voxel_size_m": 0.02,
    "pixel_stride": 2, "keyframe_interval": 1, "max_voxels": 2_000_000,
    "min_voxel_observations": 1, "statistical_neighbors": 0, "statistical_std_ratio": 2.0,
    "plot": False,
}


def validate_config(config):
    if not isinstance(config, dict) or set(config) - DEFAULT_CONFIG.keys():
        raise ValueError("mapping config contains unknown keys")
    result = {**DEFAULT_CONFIG, **config}
    for name in ("seed", "min_inliers", "min_coverage_bins", "pixel_stride", "keyframe_interval",
                 "max_voxels", "min_voxel_observations", "statistical_neighbors"):
        lower = 0 if name in ("seed", "statistical_neighbors") else 1
        if type(result[name]) is not int or result[name] < lower:
            raise ValueError(f"{name} must be an integer >= {lower}")
    if result["min_coverage_bins"] > 16:
        raise ValueError("min_coverage_bins must be <= 16")
    for name in ("residual_threshold_m", "max_reprojection_error_px", "min_depth_m", "max_depth_m",
                 "voxel_size_m", "statistical_std_ratio", "min_inlier_ratio", "validation_fraction"):
        value = result[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if result["max_depth_m"] <= result["min_depth_m"]:
        raise ValueError("max_depth_m must exceed min_depth_m")
    if result["min_inlier_ratio"] > 1 or not 0 < result["validation_fraction"] < 0.5:
        raise ValueError("invalid inlier ratio/validation fraction")
    value = result["confidence_threshold"]
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value)):
        raise ValueError("confidence_threshold must be finite or null")
    if type(result["plot"]) is not bool:
        raise ValueError("plot must be boolean")
    return result


def _json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _artifact(run_dir, manifest, key):
    path = (run_dir / manifest["artifacts"][key]).resolve()
    if not path.is_relative_to(run_dir.resolve()):
        raise ValueError(f"input artifact {key} resolves outside its run")
    return path


def _quaternion(rotation):
    # Symmetric eigenproblem, quaternion order x,y,z,w. No scipy dependency.
    r = rotation
    matrix = np.array([
        [r[0,0]-r[1,1]-r[2,2], r[0,1]+r[1,0], r[0,2]+r[2,0], r[2,1]-r[1,2]],
        [r[0,1]+r[1,0], r[1,1]-r[0,0]-r[2,2], r[1,2]+r[2,1], r[0,2]-r[2,0]],
        [r[0,2]+r[2,0], r[1,2]+r[2,1], r[2,2]-r[0,0]-r[1,1], r[1,0]-r[0,1]],
        [r[2,1]-r[1,2], r[0,2]-r[2,0], r[1,0]-r[0,1], np.trace(r)],
    ]) / 3
    _, vectors = np.linalg.eigh(matrix)
    q = vectors[:, -1]
    return q if q[-1] >= 0 else -q


def _trajectory(path, cameras, scale):
    fields = ["timestamp_s", "frame_id", "tx", "ty", "tz", "qx", "qy", "qz", "qw", "tracking_state"]
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for index in np.argsort(cameras["timestamp_s"]):
            current_scale = scale[int(cameras["frame_id"][index])] if isinstance(scale, dict) else scale
            pose = metric_pose(cameras["T_wc"][index], current_scale)
            writer.writerow([cameras["timestamp_s"][index], int(cameras["frame_id"][index]),
                             *pose[:3, 3], *_quaternion(pose[:3, :3]), "keyframe_snapshot"])


def _plot(path, residuals, validation, threshold):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for mask, label in ((~validation, "Calibration landmarks"), (validation, "Withheld landmarks")):
        axes[0].scatter(np.flatnonzero(mask), residuals[mask], s=9, alpha=0.7, label=label)
        axes[1].hist(residuals[mask], bins=30, alpha=0.6, label=label)
    axes[0].axhline(threshold, color="red", linestyle="--", label="Inlier threshold")
    axes[0].set(xlabel="Correspondence index", ylabel="Absolute camera-z residual [m]")
    axes[1].set(xlabel="Absolute camera-z residual [m]", ylabel="Count")
    axes[0].legend(fontsize=8)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_map(path, points, cameras, scale, synthetic):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    sample = points[np.linspace(0, len(points) - 1, min(len(points), 30_000)).astype(int)]
    centers = cameras["T_wc"][:, :3, 3] * scale
    fig = plt.figure(figsize=(8, 6), constrained_layout=True)
    axis = fig.add_subplot(111, projection="3d")
    cloud = axis.scatter(*sample.T, c=sample[:, 2], s=2, cmap="viridis", alpha=0.7)
    axis.plot(*centers.T, color="red", marker="o", label="Metric keyframe camera centers")
    axis.set(xlabel="World X [m]", ylabel="World Y [m]", zlabel="World Z [m]",
             title="Synthetic correctness fixture" if synthetic else "Predicted-depth fused map")
    axis.legend(fontsize=8)
    fig.colorbar(cloud, ax=axis, shrink=0.6, label="World Z [m]")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_mapping(repo_root: Path, slam_run: Path, geometry_run: Path, *, run_id: str,
                config: dict | None = None, output_root: Path | None = None) -> Path:
    """Preflight errors write nothing; runtime failures leave a terminal run.json.

    All keyframes require predictions. A failed/mismatched source run, missing
    depth, low coverage or failed holdout gate is never treated as success.
    """
    config = validate_config({} if config is None else config)
    repo_root, slam_run, geometry_run = Path(repo_root), Path(slam_run), Path(geometry_run)
    slam = load_run_manifest(slam_run / "run.json")
    geometry = load_run_manifest(geometry_run / "run.json")
    if slam["status"] != "ok" or geometry["status"] != "ok":
        raise ValueError("both input runs must have terminal status ok")
    if slam["method"] != "B0" or geometry["method"] != "model-spike":
        raise ValueError("expected B0 SLAM and model-spike geometry input runs")
    if slam["dataset"] != geometry["dataset"]:
        raise ValueError("input runs must use the same frozen dataset/sequence/split/checksum")
    if slam["slam"]["pose_convention"] != "T_wc":
        raise ValueError("SLAM pose convention must be T_wc")
    state, host = collect_git_state(repo_root), collect_host_info()
    record = dict(run_id=run_id, git_commit=state.commit, dirty_worktree=state.dirty,
                  dataset=slam["dataset"], method="P1-global", model=geometry["model"], slam=slam["slam"],
                  alignment={"method": "robust_median", "thresholds": {
                      "residual_m": config["residual_threshold_m"], "min_inliers": config["min_inliers"],
                      "min_inlier_ratio": config["min_inlier_ratio"], "min_coverage_bins": config["min_coverage_bins"]}},
                  config={**config, "input_runs": {"slam": slam["run_id"], "geometry": geometry["run_id"]},
                          "scope": "offline retained-keyframe artifact integration; no GT input"},
                  hardware={"gpu": None, "cpu": host.cpu, "ram_gb": host.ram_gb},
                  environment={"python": platform.python_version(), "numpy": np.__version__},
                  seed=config["seed"], started_at=format_utc(datetime.now(timezone.utc)),
                  status="running", reason=None, artifacts={})
    running = build_run_manifest(**record)
    directory = Path(output_root or repo_root / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(running, directory)
    start = time.perf_counter()
    try:
        provenance = {"slam_run_sha256": sha256_file(slam_run / "run.json"),
                      "geometry_run_sha256": sha256_file(geometry_run / "run.json"), "predictions": {}}
        sparse_dir = _artifact(slam_run, slam, "sparse_export").parent
        metadata = check_sparse_export(sparse_dir)
        provenance["sparse_export_sha256"] = sha256_file(sparse_dir / "export.json")
        provenance["sparse_artifact_sha256"] = metadata["sha256"]
        with np.load(sparse_dir / "landmarks.npz", allow_pickle=False) as archive:
            landmarks = dict(archive)
        with np.load(sparse_dir / "keyframes.npz", allow_pickle=False) as archive:
            cameras = dict(archive)
        with (sparse_dir / "observations.csv").open(encoding="utf-8", newline="") as stream:
            integer_fields = {"frame_id", "keyframe_id", "point_id", "keypoint_index"}
            rows = [{key: int(value) if key in integer_fields else float(value) for key, value in row.items()}
                    for row in csv.DictReader(stream)]
        snapshot = SparseSnapshot(landmarks, cameras, rows, metadata)
        predictions = {}
        prediction_dir = _artifact(geometry_run, geometry, "predictions")
        for frame_id in cameras["frame_id"]:
            name = f"frame_{frame_id:06d}.npz"
            path = prediction_dir / name
            if not path.resolve().is_relative_to(geometry_run.resolve()):
                raise ValueError("prediction resolves outside its source run")
            if not path.is_file():
                raise AlignmentError("missing_prediction", f"matching keyframe {frame_id} prediction is absent")
            prediction = load_prediction(path)
            if prediction.model_id != f"{geometry['model']['repo']}@{geometry['model']['revision']}":
                raise AlignmentError("model_mismatch", "prediction model differs from source run")
            predictions[int(frame_id)] = prediction
            provenance["predictions"][name] = sha256_file(path)
        _json(directory / "inputs.json", provenance)
        record["artifacts"]["inputs"] = "inputs.json"
        pairs = build_correspondences(snapshot, predictions,
                    max_reprojection_error_px=config["max_reprojection_error_px"],
                    confidence_threshold=config["confidence_threshold"],
                    min_depth_m=config["min_depth_m"], max_depth_m=config["max_depth_m"])
        point_ids = np.unique(pairs.point_id)
        if len(point_ids) < 3:
            raise AlignmentError("insufficient_correspondences", "at least three distinct landmarks required")
        shuffled = np.random.default_rng(config["seed"]).permutation(point_ids)
        withheld = shuffled[:max(1, int(np.ceil(len(shuffled) * config["validation_fraction"])))]
        validation = np.isin(pairs.point_id, withheld)
        training = ~validation
        result = estimate_scale(pairs.source_depth[training], pairs.target_depth_m[training],
                                threshold_m=config["residual_threshold_m"], min_inliers=config["min_inliers"],
                                min_ratio=config["min_inlier_ratio"])
        residuals = np.abs(result.scale * pairs.source_depth - pairs.target_depth_m)
        all_inliers = residuals <= config["residual_threshold_m"]
        coverage = pairs.coverage_bins(training & all_inliers)
        if coverage < config["min_coverage_bins"]:
            raise AlignmentError("insufficient_coverage", "calibration inliers cover too few 4x4 image bins")
        holdout = residuals[validation]
        holdout_ratio = float(np.mean(holdout <= config["residual_threshold_m"]))
        if holdout_ratio < config["min_inlier_ratio"] or np.median(holdout) > config["residual_threshold_m"]:
            raise AlignmentError("validation_failed", "withheld landmark residuals fail the acceptance gate")
        alignment = {**result.to_dict(), "calibration_coverage_bins_4x4": coverage,
                     "withheld_pairs": len(holdout), "withheld_landmarks": len(withheld),
                     "withheld_inlier_ratio": holdout_ratio,
                     "withheld_median_residual_m": float(np.median(holdout)),
                     "withheld_p95_residual_m": float(np.percentile(holdout, 95)),
                     "rejected_pairs": pairs.rejected, "thresholds": record["alignment"]["thresholds"],
                     "scale_application": "SLAM translations/landmarks multiplied by scale; predicted metric depth unchanged"}
        _json(directory / "alignment.json", alignment)
        record["artifacts"]["alignment"] = "alignment.json"
        with (directory / "residuals.csv").open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["frame_id", "point_id", "source_z_slam", "target_z_m", "residual_m", "inlier", "withheld"])
            writer.writerows(zip(pairs.frame_id, pairs.point_id, pairs.source_depth, pairs.target_depth_m,
                                 residuals, all_inliers, validation))
        record["artifacts"]["residuals"] = "residuals.csv"
        if config["plot"]:
            _plot(directory / "residuals.png", residuals, validation, config["residual_threshold_m"])
            record["artifacts"]["residual_plot"] = "residuals.png"
        alignment_ms = (time.perf_counter() - start) * 1000
        fusion = VoxelFusion(config["voxel_size_m"], config["max_voxels"])
        frame_ms, frame_counts = [], []
        order = np.argsort(cameras["timestamp_s"])[::config["keyframe_interval"]]
        for index in order:
            began = time.perf_counter()
            prediction = predictions[int(cameras["frame_id"][index])]
            _, grid = prediction_grid(prediction, cameras["K"][index], cameras["image_size_wh"][index])
            distortion = cameras["distortion"][index] if grid == "raw_distorted" else None
            points = depth_points(prediction, metric_pose(cameras["T_wc"][index], result.scale),
                                  distortion=distortion, min_depth_m=config["min_depth_m"],
                                  max_depth_m=config["max_depth_m"], confidence_threshold=config["confidence_threshold"],
                                  pixel_stride=config["pixel_stride"])
            if not len(points):
                raise AlignmentError("empty_frame", f"all dense points filtered from keyframe {prediction.frame_id}")
            fusion.add(points)
            frame_counts.append({"frame_id": prediction.frame_id, "points": len(points)})
            frame_ms.append((time.perf_counter() - began) * 1000)
        points, counts = fusion.cloud(config["min_voxel_observations"])
        if config["statistical_neighbors"]:
            keep = statistical_filter(points, neighbors=config["statistical_neighbors"], std_ratio=config["statistical_std_ratio"])
            points, counts = points[keep], counts[keep]
        if not len(points):
            raise AlignmentError("empty_map", "fusion filters removed every voxel")
        write_ply(directory / "map.ply", points)
        record["artifacts"]["map"] = "map.ply"
        np.savez_compressed(directory / "map.npz", xyz_m=points, observation_count=counts)
        record["artifacts"]["map_arrays"] = "map.npz"
        _trajectory(directory / "trajectory_metric.csv", cameras, result.scale)
        record["artifacts"]["trajectory"] = "trajectory_metric.csv"
        if config["plot"]:
            _plot_map(directory / "visualization.png", points, cameras, result.scale,
                      slam["dataset"]["name"] == "synthetic")
            record["artifacts"]["visualization"] = "visualization.png"
        _json(directory / "metrics.json", {
            "status": "ok", "units": "meters", "input_keyframes": len(predictions),
            "fused_keyframes": len(order), "input_points": fusion.input_points, "map_points": len(points),
            "per_frame": frame_counts, "scale": result.scale, "alignment_inliers": int(result.inliers.sum()),
            "trajectory_scope": "retained keyframes only; snapshot matches sparse landmarks",
            "ground_truth_evaluation": "not performed", "real_time_claim": False,
        })
        record["artifacts"]["metrics"] = "metrics.json"
        _json(directory / "timing.json", {"alignment_and_input_ms": alignment_ms,
            "fusion_per_keyframe_ms": frame_ms, "fusion_median_ms": float(np.median(frame_ms)),
            "fusion_p95_ms": float(np.percentile(frame_ms, 95)),
            "wall_clock_s": time.perf_counter() - start, "scope": "CPU artifact integration, excluding SLAM/model inference"})
        record["artifacts"]["timing"] = "timing.json"
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: user stopped artifact integration")
        raise
    except Exception as exc:
        reason = exc.reason if isinstance(exc, AlignmentError) else type(exc).__name__
        record.update(status="failed", reason=f"{reason}: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory
