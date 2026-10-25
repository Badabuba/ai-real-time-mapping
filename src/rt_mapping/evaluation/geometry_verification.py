"""Read-only verification of saved geometry runs without model imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np

from rt_mapping.contracts.geometry import load_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.depth import DepthMetrics, evaluate_depth, mean_depth_metrics, resize_depth_nearest
from rt_mapping.evaluation.prediction_grid import resize_prediction
from rt_mapping.evaluation.timing import summarize_timings
from rt_mapping.evaluation.tum_depth import load_tum_depth_m


def inside(root, relative):
    path = (Path(root) / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(Path(root).resolve()):
        raise ValueError("artifact path escapes its root")
    return path


def same(actual, expected, label):
    if set(actual) != set(expected):
        raise ValueError(f"{label}: keys differ")
    for key, value in expected.items():
        found = actual[key]
        if isinstance(value, float):
            if not np.isfinite(found) or not np.isclose(found, value, rtol=1e-12, atol=1e-12):
                raise ValueError(f"{label}.{key}: differs from recomputation")
        elif found != value:
            raise ValueError(f"{label}.{key}: differs from recomputation")


def verify_geometry_run(directory, *, repo_root=None, assets_root=None):
    """Check identities, predictions, aggregate metrics and all timing samples.

    With repo_root and assets_root, recompute metrics/masks from predictions and
    frozen GT bytes. Otherwise report the narrower saved-record verification.
    """
    directory = Path(directory)
    run = load_run_manifest(directory / "run.json")
    if run["status"] != "ok" or run["dirty_worktree"]:
        raise ValueError("verification requires a successful clean-commit run")
    metrics = json.loads(inside(directory, run["artifacts"]["metrics"]).read_text())
    timing = json.loads(inside(directory, run["artifacts"]["timing"]).read_text())
    rows = metrics["per_frame"]
    if len(rows) != run["config"]["frames"] or not rows:
        raise ValueError("frame count differs from run config")
    ids, stamps = [r["frame_id"] for r in rows], [r["timestamp_s"] for r in rows]
    if len(set(ids)) != len(ids) or any(b <= a for a, b in zip(ids, ids[1:])):
        raise ValueError("frame IDs must be unique and increasing")
    if any(not np.isfinite(t) for t in stamps) or any(b <= a for a, b in zip(stamps, stamps[1:])):
        raise ValueError("timestamps must be finite and increasing")
    frames = None
    if (repo_root is None) != (assets_root is None):
        raise ValueError("both roots are required for GT recomputation")
    if repo_root is not None:
        from rt_mapping.runs.geometry_run import verify_tum_split
        manifest_path = inside(repo_root, run["dataset"]["manifest"])
        manifest = json.loads(manifest_path.read_text())
        expected_hash = run["config"].get("dataset_manifest_sha256")
        if expected_hash and sha256_file(manifest_path) != expected_hash:
            raise ValueError("dataset manifest hash mismatch")
        sequence = inside(assets_root, manifest["extracted_dir"])
        frames = verify_tum_split(manifest, sequence, run["dataset"]["split"], len(rows), None)
    recomputed, confidence, shapes, semantics = [], [], set(), set()
    for index, row in enumerate(rows):
        prediction = load_prediction(inside(directory, row["prediction"]))
        if (prediction.frame_id, prediction.timestamp_s) != (row["frame_id"], row["timestamp_s"]):
            raise ValueError("prediction identity differs from metrics")
        if run["model"]["revision"] not in prediction.model_id:
            raise ValueError("prediction revision differs from run")
        if prediction.inference_ms != row["inference_ms"]:
            raise ValueError("prediction latency differs from metrics")
        confidence.append(prediction.confidence is not None)
        shapes.add(prediction.depth_m.shape)
        semantics.add(prediction.preprocess.get("K_processed_source", "documented resize of calibrated K"))
        declared = {key: row[key] for key in DepthMetrics.__dataclass_fields__}
        if frames is None:
            current = DepthMetrics(**declared)
        else:
            item = frames[index]
            actual = tuple(row[k] for k in ("frame_id", "timestamp_s", "rgb_path", "gt_depth_timestamp_s", "gt_depth_path"))
            expected = (item.frame.frame_id, item.frame.timestamp_s, item.frame.image_path,
                        item.gt_depth_timestamp_s, item.gt_depth_path)
            if actual != expected:
                raise ValueError("metrics identity differs from frozen frame")
            gt = load_tum_depth_m(sequence, item.gt_depth_path)
            if run["config"].get("evaluation_grid") == "raw_rgb":
                evaluated = resize_prediction(prediction, (item.frame.width, item.frame.height))
            else:
                evaluated = prediction
                gt = resize_depth_nearest(gt, (prediction.depth_m.shape[1], prediction.depth_m.shape[0]))
            current = evaluate_depth(evaluated, gt)
            same(declared, current.to_dict(), f"frame {prediction.frame_id}")
            mask = np.ascontiguousarray(np.isfinite(gt) & (gt > 0) & evaluated.valid_mask)
            if "evaluation_mask_sha256" in row and hashlib.sha256(mask.tobytes()).hexdigest() != row["evaluation_mask_sha256"]:
                raise ValueError("evaluation mask hash differs from recomputation")
        recomputed.append(current)
    same(metrics["mean"], mean_depth_metrics(recomputed), "mean")
    samples = [{"frame_id": r["frame_id"], "inference_ms": r["inference_ms"]} for r in rows]
    if timing["per_frame_ms"] != samples:
        raise ValueError("timing samples differ from predictions")
    stage = summarize_timings([r["inference_ms"] for r in rows], warmup=run["config"]["warmup"], stage="model_inference").to_dict()
    same(timing["stages"]["model_inference"], stage, "timing")
    prewarm = timing.get("prewarm_samples_ms", [])
    if len(prewarm) != run["config"].get("prewarm_calls", 0):
        raise ValueError("prewarm count differs from config")
    if any(not np.isfinite(t) or t < 0 for t in prewarm):
        raise ValueError("prewarm latency must be finite and non-negative")
    cold = prewarm[0] if prewarm else rows[0]["inference_ms"]
    if timing.get("cold_inference_ms", cold) != cold:
        raise ValueError("cold latency differs from first call")
    if len(set(confidence)) != 1:
        raise ValueError("confidence availability changes between frames")
    return {"run_id": run["run_id"], "git_commit": run["git_commit"], "status": "verified",
            "verification_scope": "predictions + GT recomputation" if frames else "saved predictions/records; GT not checked",
            "frames": len(rows), "metrics": mean_depth_metrics(recomputed), "warm_latency": stage,
            "peak_vram_gb": timing["peak_vram_gb"], "confidence_available": confidence[0],
            "output_shapes_hw": [list(s) for s in sorted(shapes)], "intrinsics_semantics": sorted(semantics),
            "artifacts_sha256": {name: sha256_file(directory / name) for name in ("run.json", "metrics.json", "timing.json")}}
