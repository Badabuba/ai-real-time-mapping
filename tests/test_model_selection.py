import json

import pytest
import numpy as np

from test_run_manifest import model_spike
from rt_mapping.contracts.run_manifest import build_run_manifest
from rt_mapping.evaluation.model_selection import build_scorecard
from rt_mapping.contracts.geometry import GeometryPrediction, save_prediction
from rt_mapping.evaluation.depth import evaluate_depth, mean_depth_metrics
from rt_mapping.evaluation.timing import summarize_timings


def runs(tmp_path):
    paths = []
    for index, repo in enumerate(("depth-anything/DA3METRIC-LARGE", "lpiccinelli/unidepth-v2-vitl14")):
        path = tmp_path / f"candidate{index}"
        path.mkdir()
        run = build_run_manifest(**model_spike(run_id=path.name, status="ok", model={
            "repo": repo, "revision": "a" * 40, "checkpoint": "model.safetensors@sha256:" + "b" * 64,
            "dtype": "float16"}, config={"prewarm_calls": 10, "evaluation_grid": "raw_rgb", "frames": 50, "warmup": 0,
                                        "dataset_manifest_sha256": "c" * 64},
            artifacts={"metrics": "metrics.json", "timing": "timing.json"}))
        frame_metrics = []
        rows = []
        for i in range(50):
            prediction = GeometryPrediction(i, float(i), np.full((2, 2), 2.2 + index * .04, np.float32),
                np.ones((2, 2), bool), None if index == 0 else np.full((2, 2), -.1, np.float32),
                np.eye(3), repo + "@" + "a" * 40, {"K_processed_source": "fake test calibration"}, 100. + index)
            save_prediction(prediction, path / f"frame_{i}.npz")
            metric = evaluate_depth(prediction, np.full((2, 2), 2.))
            frame_metrics.append(metric)
            rows.append({**metric.to_dict(), "timestamp_s": float(i), "rgb_path": f"rgb/{i}.png",
                         "gt_depth_timestamp_s": float(i), "gt_depth_path": f"depth/{i}.png",
                         "evaluation_mask_sha256": "d" * 64, "prediction": f"frame_{i}.npz", "inference_ms": 100. + index})
        metrics = {"mean": mean_depth_metrics(frame_metrics),
                   "protocol": {"scale_alignment": "none (raw metric depth)"},
                   "per_frame": rows}
        timing = {"stages": {"model_inference": summarize_timings([100. + index] * 50, warmup=0, stage="model_inference").to_dict()},
                  "per_frame_ms": [{"frame_id": i, "inference_ms": 100. + index} for i in range(50)],
                  "prewarm_samples_ms": [1000.] * 10,
                  "peak_vram_gb": 2. + index, "cold_inference_ms": 1000., "wall_clock_s": 12.}
        for filename, data in (("run.json", run), ("metrics.json", metrics), ("timing.json", timing)):
            (path / filename).write_text(json.dumps(data))
        paths.append(path)
    return paths


def test_weighted_score_and_source_hashes(tmp_path):
    report = build_scorecard(runs(tmp_path))
    assert report["selected_model"] == "depth-anything/DA3METRIC-LARGE"
    assert report["candidates"][0]["weighted_score"] > report["candidates"][1]["weighted_score"]
    assert len(report["pair_identity_sha256"]) == 64
    assert set(report["candidates"][0]["artifacts_sha256"]) == {"run.json", "metrics.json", "timing.json"}


@pytest.mark.parametrize("change", ["mask", "dirty", "frames", "prewarm", "scale", "mean", "timing", "duplicate"])
def test_non_comparable_evidence_is_rejected(tmp_path, change):
    paths = runs(tmp_path)
    name = "run.json" if change in {"dirty", "prewarm"} else ("timing.json" if change == "timing" else "metrics.json")
    path = paths[1] / name
    data = json.loads(path.read_text())
    if change == "mask":
        data["per_frame"][0]["evaluation_mask_sha256"] = "e" * 64
    elif change == "dirty":
        data["dirty_worktree"] = True
    elif change == "frames":
        data["per_frame"].pop()
    elif change == "prewarm":
        data["config"]["prewarm_calls"] = 0
    elif change == "scale":
        data["protocol"]["scale_alignment"] = "median"
    elif change == "mean":
        data["mean"]["abs_rel"] = .00001
    elif change == "timing":
        data["stages"]["model_inference"]["warm_p95_ms"] = 1.
    else:
        data["per_frame"][1]["frame_id"] = 0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        build_scorecard(paths)
