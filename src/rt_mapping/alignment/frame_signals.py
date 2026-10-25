"""GT-free per-keyframe sparse-anchor signals for P1-robust diagnostics (U-01).

Inputs are finished B0, model-spike and P1-global artifacts only. No dataset,
ground-truth depth or ground-truth pose is read here; evaluation joins live in
rt_mapping.evaluation.frame_diagnostics. Thresholds are the merged mapping
defaults recorded in the source comparison run, plus the delta1 band.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np

from rt_mapping.alignment.correspondences import Correspondences, build_correspondences
from rt_mapping.alignment.estimators import AlignmentError, estimate_scale
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.runs.artifacts import MappingInputs, load_mapping_inputs

# The delta1 band of the project depth metric (docs/EXPERIMENTS.md §4.2); fixed, never tuned.
ANCHOR_BAND = 1.25
NO_TRACKING_REASON = "source SLAM run predates Y-01 tracking export (be9bff2)"
SIGNAL_FIELDS = (
    "frame_id", "timestamp_s", "n_pairs", "n_calibration_pairs", "n_withheld_pairs",
    "frame_inlier_ratio", "median_abs_residual_m", "withheld_median_abs_residual_m", "withheld_reason",
    "coverage_bins_4x4", "anchor_ratio", "anchor_inliers", "anchor_reason", "abs_log_anchor_ratio",
    "predicted_depth_median_m", "predicted_depth_p95_m", "predicted_valid_fraction",
    "tracking_state", "tracking_reason", "flag_A1", "flag_A2", "flag_A3", "flag_A4", "flag_S1",
)


@dataclass
class SourceRuns:
    comparison: dict
    comparison_dir: Path
    global_dir: Path
    global_record: dict
    alignment: dict
    mapping: dict
    inputs: MappingInputs
    provenance: dict
    slam_dir: Path
    geometry_dir: Path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_sources(comparison_run, slam_run, geometry_run) -> SourceRuns:
    """Verify that the comparison was produced from exactly these source runs."""
    comparison_dir, slam_run, geometry_run = Path(comparison_run), Path(slam_run), Path(geometry_run)
    comparison = load_run_manifest(comparison_dir / "run.json")
    if comparison["status"] != "ok":
        raise ValueError("source comparison run must have terminal status ok")
    recorded = _read_json(comparison_dir / "inputs.json")["pipeline"]
    actual = {"slam_run_sha256": sha256_file(slam_run / "run.json"),
              "geometry_run_sha256": sha256_file(geometry_run / "run.json")}
    if any(recorded.get(key) != value for key, value in actual.items()):
        raise ValueError("slam/geometry run.json sha256 differs from the comparison provenance")
    global_dirs = sorted((comparison_dir / "methods").glob("*.global"))
    if len(global_dirs) != 1:
        raise ValueError("comparison must contain exactly one P1-global child run")
    global_record = load_run_manifest(global_dirs[0] / "run.json")
    if global_record["status"] != "ok" or global_record["method"] != "P1-global":
        raise ValueError("P1-global child run must have terminal status ok")
    inputs = load_mapping_inputs(slam_run, geometry_run)
    provenance = {"comparison_run_id": comparison["run_id"], "global_run_id": global_record["run_id"],
                  "slam_run_id": inputs.slam["run_id"], "geometry_run_id": inputs.geometry["run_id"],
                  "comparison_run_sha256": sha256_file(comparison_dir / "run.json"),
                  "global_run_sha256": sha256_file(global_dirs[0] / "run.json"),
                  "alignment_sha256": sha256_file(global_dirs[0] / "alignment.json"),
                  "residuals_sha256": sha256_file(global_dirs[0] / "residuals.csv"), **actual}
    return SourceRuns(comparison, comparison_dir, global_dirs[0], global_record,
                      _read_json(global_dirs[0] / "alignment.json"), comparison["config"]["mapping"], inputs, provenance,
                      slam_run, geometry_run)


def rebuild_pairs(inputs: MappingInputs, mapping: dict):
    """Replay the merged mapping_run correspondences and landmark holdout split."""
    pairs = build_correspondences(inputs.snapshot, inputs.predictions,
                                  max_reprojection_error_px=mapping["max_reprojection_error_px"],
                                  confidence_threshold=mapping["confidence_threshold"],
                                  min_depth_m=mapping["min_depth_m"], max_depth_m=mapping["max_depth_m"])
    point_ids = np.unique(pairs.point_id)
    shuffled = np.random.default_rng(mapping["seed"]).permutation(point_ids)
    withheld = shuffled[:max(1, int(np.ceil(len(shuffled) * mapping["validation_fraction"])))]
    return pairs, np.isin(pairs.point_id, withheld)


def check_recorded_residuals(path, pairs: Correspondences, withheld) -> dict:
    """The rebuilt pairs must match the recorded P1-global residuals.csv row by row."""
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(pairs.frame_id):
        raise ValueError("rebuilt correspondences differ in count from the recorded residuals.csv")
    frame_ids = np.array([int(r["frame_id"]) for r in rows])
    point_ids = np.array([int(r["point_id"]) for r in rows])
    recorded_withheld = np.array([r["withheld"] == "True" for r in rows])
    if (not np.array_equal(frame_ids, pairs.frame_id) or not np.array_equal(point_ids, pairs.point_id)
            or not np.array_equal(recorded_withheld, withheld)):
        raise ValueError("rebuilt frame_id/point_id/withheld columns differ from the recorded residuals.csv")
    source = np.array([float(r["source_z_slam"]) for r in rows])
    target = np.array([float(r["target_z_m"]) for r in rows])
    return {"rows": len(rows), "frame_point_withheld_identical": True,
            "max_abs_source_z_difference": float(np.max(np.abs(source - pairs.source_depth))),
            "max_abs_target_z_difference_m": float(np.max(np.abs(target - pairs.target_depth_m)))}


def tracking_states(slam_run, slam_record):
    """Per-frame Y-01 states when the SLAM run exported them; never imputed."""
    slam_run = Path(slam_run)
    if not slam_record["config"].get("export_tracking") or not (slam_run / "tracking_export.json").is_file():
        return None, {"available": False, "reason": NO_TRACKING_REASON}
    from rt_mapping.slam.tracking_log import read_tracking_log

    frames = _read_json(slam_run / slam_record["artifacts"]["preparation"])["frames"]
    rows, _ = read_tracking_log(slam_run, frames)
    return {row.frame_id: row.tracking_state for row in rows}, {"available": True, "reason": None}


def _median(values):
    return float(np.median(values)) if len(values) else None


def frame_signals(sources: SourceRuns, pairs: Correspondences, withheld, tracking=None):
    """One GT-free row per retained keyframe, ordered by timestamp."""
    mapping, scale = sources.mapping, float(sources.alignment["scale"])
    threshold = mapping["residual_threshold_m"]
    residuals = np.abs(scale * pairs.source_depth - pairs.target_depth_m)
    inliers = residuals <= threshold
    cameras = sources.inputs.snapshot.keyframes
    rows = []
    for index in np.argsort(cameras["timestamp_s"]):
        frame_id = int(cameras["frame_id"][index])
        frame = pairs.frame_id == frame_id
        calibration, check = frame & ~withheld, frame & withheld
        row = {"frame_id": frame_id, "timestamp_s": float(cameras["timestamp_s"][index]),
               "n_pairs": int(frame.sum()), "n_calibration_pairs": int(calibration.sum()),
               "n_withheld_pairs": int(check.sum()),
               "frame_inlier_ratio": float(inliers[frame].mean()) if frame.any() else None,
               "median_abs_residual_m": _median(residuals[frame]),
               "withheld_median_abs_residual_m": _median(residuals[check]),
               "withheld_reason": None if check.any() else "no withheld landmark observed in this keyframe",
               "coverage_bins_4x4": pairs.coverage_bins(calibration & inliers) if (calibration & inliers).any() else 0}
        try:
            # Inverse direction of the merged global estimator: metric depth -> scaled SLAM depth.
            result = estimate_scale(pairs.target_depth_m[calibration], scale * pairs.source_depth[calibration],
                                    threshold_m=threshold, min_inliers=mapping["min_inliers"],
                                    min_ratio=mapping["min_inlier_ratio"])
            row.update(anchor_ratio=result.scale, anchor_inliers=int(result.inliers.sum()), anchor_reason=None,
                       abs_log_anchor_ratio=abs(math.log(result.scale)))
        except AlignmentError as exc:
            row.update(anchor_ratio=None, anchor_inliers=None, anchor_reason=str(exc), abs_log_anchor_ratio=None)
        prediction = sources.inputs.predictions[frame_id]
        valid = prediction.valid_mask & (prediction.depth_m >= mapping["min_depth_m"]) & (prediction.depth_m <= mapping["max_depth_m"])
        depth = prediction.depth_m[valid].astype(float)
        row.update(predicted_depth_median_m=_median(depth),
                   predicted_depth_p95_m=float(np.percentile(depth, 95)) if len(depth) else None,
                   predicted_valid_fraction=float(valid.mean()))
        if tracking is None:
            row.update(tracking_state=None, tracking_reason=NO_TRACKING_REASON)
        else:
            row.update(tracking_state=tracking.get(frame_id),
                       tracking_reason=None if frame_id in tracking else "keyframe absent from the tracking export")
        row.update(
            flag_A1=row["anchor_ratio"] is None,
            flag_A2=row["anchor_ratio"] is not None and row["abs_log_anchor_ratio"] > math.log(ANCHOR_BAND),
            flag_A3=row["withheld_median_abs_residual_m"] is not None and row["withheld_median_abs_residual_m"] > threshold,
            flag_A4=row["coverage_bins_4x4"] < mapping["min_coverage_bins"],
            flag_S1=row["tracking_state"] is not None and row["tracking_state"] != "OK")
        rows.append(row)
    return rows


def flag_rules(mapping):
    return {"A1": f"anchor_ratio null: fewer than min_inliers={mapping['min_inliers']} anchors or inlier ratio < "
                  f"min_inlier_ratio={mapping['min_inlier_ratio']} (merged mapping defaults)",
            "A2": f"|log anchor_ratio| > log({ANCHOR_BAND}) (delta1 accuracy band, docs/EXPERIMENTS.md §4.2)",
            "A3": f"withheld median |residual| > residual_threshold_m={mapping['residual_threshold_m']} "
                  "(only with >= 1 withheld pair, as in alignment/causal.py)",
            "A4": f"calibration-inlier coverage_bins_4x4 < min_coverage_bins={mapping['min_coverage_bins']} (merged default)",
            "S1": "tracking_state known and != OK (Y-01 contract); unavailable when the run has no tracking export"}


def format_value(value):
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_csv(path, fields, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows([[format_value(row[field]) for field in fields] for row in rows])


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
