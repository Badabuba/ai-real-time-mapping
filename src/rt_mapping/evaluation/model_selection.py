"""Validate paired frozen 50-frame runs and compute the preregistered scorecard."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.geometry_verification import verify_geometry_run

WEIGHTS = {"quality": .35, "runtime": .25, "memory": .15, "integration": .15, "license": .10}
IDENTITY = ("frame_id", "timestamp_s", "rgb_path", "gt_depth_timestamp_s", "gt_depth_path", "evaluation_mask_sha256")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_scorecard(run_dirs: list[Path]) -> dict:
    if len(run_dirs) != 2:
        raise ValueError("exactly two candidate runs are required")
    rows = []
    identities = []
    for directory in map(Path, run_dirs):
        run = load_run_manifest(directory / "run.json")
        metrics, timing = _read(directory / "metrics.json"), _read(directory / "timing.json")
        if run["status"] != "ok" or run["dirty_worktree"]:
            raise ValueError("selection requires successful clean committed runs")
        if run["method"] != "model-spike" or run["config"].get("evaluation_grid") != "raw_rgb":
            raise ValueError("selection requires raw-grid model-spike runs")
        if run["config"].get("prewarm_calls", 0) < 10 or len(metrics["per_frame"]) != 50:
            raise ValueError("selection requires 10 prewarm calls and exactly 50 measured frames")
        if (run["config"].get("warmup") != 0 or run["config"].get("prewarm_calls") != 10
                or run["config"].get("frames") != 50
                or [r["frame_id"] for r in metrics["per_frame"]] != list(range(50))):
            raise ValueError("selection requires the frozen prefix50 and ten separate warmups")
        verified = verify_geometry_run(directory)
        if metrics["protocol"]["scale_alignment"] != "none (raw metric depth)":
            raise ValueError("scale-aligned results cannot select a metric model")
        if metrics["mean"]["valid_coverage"] != 1:
            raise ValueError("all candidates must evaluate the full GT-valid mask")
        identity = [{key: frame[key] for key in IDENTITY} for frame in metrics["per_frame"]]
        identities.append((run["dataset"], run["config"]["dataset_manifest_sha256"], identity))
        repo = run["model"]["repo"]
        if repo == "depth-anything/DA3METRIC-LARGE":
            integration, license_score = 4.5, 5.
        elif repo == "lpiccinelli/unidepth-v2-vitl14":
            integration, license_score = 4.5, 3.
        else:
            raise ValueError(f"candidate is not in the frozen two-model protocol: {repo}")
        if any(row["model"]["repo"] == repo for row in rows):
            raise ValueError("candidate models must differ")
        stage = timing["stages"]["model_inference"]
        peak = timing["peak_vram_gb"]
        if not isinstance(peak, (int, float)) or not 0 < peak < 7.5:
            raise ValueError("candidate exceeds the 8 GB device budget (7.5 GB allocated limit)")
        rows.append({"run_id": run["run_id"], "git_commit": run["git_commit"], "model": run["model"],
                     "config": run["config"], "hardware": run["hardware"], "environment": run["environment"],
                     "metrics": metrics["mean"], "warm_latency": stage, "peak_vram_gb": peak,
                     "cold_inference_ms": timing["cold_inference_ms"], "wall_clock_s": timing["wall_clock_s"],
                     "confidence_available": verified["confidence_available"],
                     "intrinsics_semantics": verified["intrinsics_semantics"],
                     "output_shapes_hw": verified["output_shapes_hw"],
                     "stability": "50/50 valid saved predictions; full common mask",
                     "repeatability": "one run per candidate; cross-run variation is reported separately",
                     "scores": {"integration": integration, "license": license_score},
                     "artifacts_sha256": {name: sha256_file(directory / name)
                                          for name in ("run.json", "metrics.json", "timing.json")}})
    if identities[0] != identities[1]:
        raise ValueError("candidates differ in dataset, frozen frames, or evaluation masks")
    if rows[0]["hardware"] != rows[1]["hardware"]:
        raise ValueError("candidate hardware differs")
    best_rel = min(row["metrics"]["abs_rel"] for row in rows)
    best_delta = max(row["metrics"]["delta1"] for row in rows)
    best_p95 = min(row["warm_latency"]["warm_p95_ms"] for row in rows)
    best_mem = min(row["peak_vram_gb"] for row in rows)
    for row in rows:
        rel = row["metrics"]["abs_rel"]
        quality_rel = 1. if rel == 0 else best_rel / rel
        row["scores"].update({
            "quality": 2.5 * (quality_rel + row["metrics"]["delta1"] / best_delta),
            "runtime": 5 * best_p95 / row["warm_latency"]["warm_p95_ms"],
            "memory": 5 * best_mem / row["peak_vram_gb"],
        })
        row["weighted_score"] = sum(WEIGHTS[key] * row["scores"][key] for key in WEIGHTS)
    selected = max(rows, key=lambda row: row["weighted_score"])
    fingerprint = hashlib.sha256(json.dumps(identities[0], sort_keys=True).encode()).hexdigest()
    return {"schema": "rt_mapping.model_selection/v1", "weights": WEIGHTS,
            "dataset": identities[0][0], "pair_identity_sha256": fingerprint,
            "rubric": {
                "quality": "2.5*(best_AbsRel/AbsRel + delta1/best_delta1)",
                "runtime": "5*best_p95/p95", "memory": "5*best_peak/peak",
                "integration": "5 minus 0.5 missing confidence (DA3) or separate environment (UniDepth)",
                "license": "DA3 Apache-2.0=5; UniDepth CC-BY-NC-4.0, no separate checkpoint-card license=3",
            }, "candidates": rows, "selected_model": selected["model"]["repo"],
            "decision_status": "implementation decision; external team review pending",
            "limitations": ["50 consecutive frames per sequence are correlated; held-out untouched",
                            "documented native modes; internal grids and FP16/BF16 differ",
                            "allocated VRAM only; model latency excludes future SLAM/alignment/fusion"]}
