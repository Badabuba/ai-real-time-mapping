"""Prediction-only confidence quantiles with GT read exclusively for scoring."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction, load_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.depth import evaluate_depth, mean_depth_metrics
from rt_mapping.evaluation.tum_depth import load_tum_depth_m


def filter_confidence(prediction: GeometryPrediction, keep_fraction: float) -> GeometryPrediction:
    if not 0 < keep_fraction <= 1:
        raise ValueError("keep_fraction must be in (0,1]")
    if prediction.confidence is None:
        raise ValueError("model provides no confidence")
    threshold = float(np.quantile(prediction.confidence[prediction.valid_mask], 1 - keep_fraction))
    mask = prediction.valid_mask & (prediction.confidence >= threshold)
    return GeometryPrediction(
        prediction.frame_id, prediction.timestamp_s,
        np.where(mask, prediction.depth_m, np.nan).astype(np.float32), mask,
        prediction.confidence, prediction.K_processed, prediction.model_id,
        {**prediction.preprocess, "confidence_ablation": {
            "keep_fraction": keep_fraction, "threshold": threshold,
            "selection": "prediction confidence only; ties retained"}}, prediction.inference_ms,
    )


def analyze_run(run_dir: Path, sequence_dir: Path) -> dict:
    record = load_run_manifest(run_dir / "run.json")
    if record["status"] != "ok" or record["dirty_worktree"]:
        raise ValueError("ablation requires a successful clean source run")
    metric_doc = json.loads((run_dir / "metrics.json").read_text())
    first = load_prediction(run_dir / metric_doc["per_frame"][0]["prediction"])
    base = {"schema": "rt_mapping.confidence_ablation/v1", "source_run": record["run_id"],
            "source_commit": record["git_commit"], "dataset": record["dataset"],
            "source_run_sha256": sha256_file(run_dir / "run.json"),
            "mode": "raw metric depth; depth-only diagnostic, not map F-score/completeness"}
    if first.confidence is None:
        return {**base, "status": "skipped", "reason": "model supplies no confidence", "results": []}
    results = []
    for fraction in (1., .75, .5):
        metrics = []
        for frame in metric_doc["per_frame"]:
            prediction = load_prediction(run_dir / frame["prediction"])
            gt = load_tum_depth_m(sequence_dir, frame["gt_depth_path"])
            if prediction.depth_m.shape != gt.shape:
                raise ValueError("confidence diagnostic requires native raw-grid predictions")
            metrics.append(evaluate_depth(filter_confidence(prediction, fraction), gt))
        results.append({"keep_fraction_requested": fraction, "metrics": mean_depth_metrics(metrics)})
    return {**base, "status": "ok", "results": results,
            "limitation": "thresholds fixed at 100/75/50%; no GT used to select pixels or tune thresholds"}


def _clean_predictions(run_dir: Path):
    record = load_run_manifest(run_dir / "run.json")
    if record["status"] != "ok" or record["dirty_worktree"]:
        raise ValueError("thresholds require a successful clean source run")
    metric_doc = json.loads((run_dir / "metrics.json").read_text())
    return record, [load_prediction(run_dir / frame["prediction"]) for frame in metric_doc["per_frame"]]


def pooled_confidence_thresholds(run_dir: Path, keep_fractions=(0.75, 0.5)) -> dict:
    """Pooled per-pixel confidence quantiles from saved predictions only.

    Opens no GT file: only run.json, metrics.json (for prediction paths) and the
    prediction NPZs. A threshold t keeps pixels with confidence >= t, matching
    rt_mapping.fusion.depth_points.
    """
    record, predictions = _clean_predictions(Path(run_dir))
    if any(p.confidence is None for p in predictions):
        raise ValueError("model provides no confidence")
    values = np.concatenate([p.confidence[p.valid_mask].astype(np.float64) for p in predictions])
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("confidence values must be finite and nonempty")
    thresholds = []
    for fraction in keep_fractions:
        if not 0 < fraction < 1:
            raise ValueError("keep fractions must be in (0,1)")
        threshold = float(np.quantile(values, 1 - fraction))
        thresholds.append({"keep_fraction_requested": fraction, "quantile": 1 - fraction, "threshold": threshold,
                           "retained_pixels": int(np.count_nonzero(values >= threshold)),
                           "retained_fraction": float(np.mean(values >= threshold))})
    return {"schema": "rt_mapping.confidence_thresholds/v1", "source_run": record["run_id"],
            "source_commit": record["git_commit"], "dataset": record["dataset"], "model": record["model"],
            "source_run_sha256": sha256_file(Path(run_dir) / "run.json"),
            "confidence_semantics": record["config"].get("model", {}).get("confidence"),
            "pooling": "all valid prediction pixels of all frames; numpy.quantile linear", "frames": len(predictions),
            "valid_pixels": int(len(values)), "thresholds": thresholds, "ground_truth_used": False}


def confidence_coverage(run_dir: Path, thresholds, frame_ids=None) -> list[dict]:
    """GT-free fraction of valid prediction pixels kept by each fixed threshold."""
    _, predictions = _clean_predictions(Path(run_dir))
    if frame_ids is not None:
        wanted = {int(f) for f in frame_ids}
        predictions = [p for p in predictions if p.frame_id in wanted]
        if len(predictions) != len(wanted):
            raise ValueError("coverage frames missing from source run")
    if any(p.confidence is None for p in predictions):
        raise ValueError("model provides no confidence")
    values = np.concatenate([p.confidence[p.valid_mask].astype(np.float64) for p in predictions])
    return [{"threshold": float(t), "frames": len(predictions), "valid_pixels": int(len(values)),
             "retained_pixels": int(np.count_nonzero(values >= t)), "retained_fraction": float(np.mean(values >= t))}
            for t in thresholds]
