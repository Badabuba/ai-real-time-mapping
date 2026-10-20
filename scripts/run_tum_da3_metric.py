"""Benchmark DA3 metric depth on a small, reproducible TUM RGB-D subset."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

MODEL_ID = "depth-anything/DA3METRIC-LARGE"
METRIC_FOCAL_DIVISOR = 300.0
TUM_DEPTH_FACTOR = 5000.0
TUM_FR1_K = np.array(
    [[517.3, 0.0, 318.6], [0.0, 516.5, 255.3], [0.0, 0.0, 1.0]],
    dtype=np.float32,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/runs/tum_fr1_xyz_da3metric"))
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--cache-dir", type=Path, default=Path("checkpoints/huggingface"))
    parser.add_argument("--process-res", type=int, default=384)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-association-delta", type=float, default=0.02)
    return parser.parse_args()


def read_index(path: Path) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        timestamp, relative_path, *_ = line.split()
        rows.append((float(timestamp), relative_path))
    return rows


def associate(
    rgb_rows: list[tuple[float, str]],
    depth_rows: list[tuple[float, str]],
    max_delta: float,
) -> list[tuple[float, str, float, str]]:
    """Greedily associate each RGB frame with its nearest unused depth frame."""
    candidates = sorted(
        (abs(rgb_ts - depth_ts), rgb_i, depth_i)
        for rgb_i, (rgb_ts, _) in enumerate(rgb_rows)
        for depth_i, (depth_ts, _) in enumerate(depth_rows)
        if abs(rgb_ts - depth_ts) <= max_delta
    )
    used_rgb: set[int] = set()
    used_depth: set[int] = set()
    matches: list[tuple[float, str, float, str]] = []
    for _, rgb_i, depth_i in candidates:
        if rgb_i in used_rgb or depth_i in used_depth:
            continue
        used_rgb.add(rgb_i)
        used_depth.add(depth_i)
        rgb_ts, rgb_path = rgb_rows[rgb_i]
        depth_ts, depth_path = depth_rows[depth_i]
        matches.append((rgb_ts, rgb_path, depth_ts, depth_path))
    return sorted(matches)


def scalar_int(value: object) -> int:
    if isinstance(value, torch.Tensor):
        return int(value.detach().cpu().reshape(-1)[0].item())
    if isinstance(value, dict):
        return int(value.get("value", 0)) if value else 0
    if hasattr(value, "item"):
        return int(value.item())
    return int(value)


def depth_metrics(prediction_m: np.ndarray, target_m: np.ndarray) -> dict[str, float | int]:
    valid = np.isfinite(prediction_m) & (prediction_m > 0) & (target_m > 0)
    pred = prediction_m[valid]
    target = target_m[valid]
    if not len(pred):
        raise RuntimeError("No valid depth pixels for evaluation")
    ratio = np.maximum(pred / target, target / pred)
    return {
        "valid_pixels": int(valid.sum()),
        "abs_rel": float(np.mean(np.abs(pred - target) / target)),
        "rmse_m": float(np.sqrt(np.mean((pred - target) ** 2))),
        "mae_m": float(np.mean(np.abs(pred - target))),
        "delta1": float(np.mean(ratio < 1.25)),
    }


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for the WP1 DA3 benchmark")
    if args.frames < 1 or args.stride < 1:
        raise ValueError("--frames and --stride must be positive")
    for name in ("rgb.txt", "depth.txt"):
        if not (args.dataset_dir / name).is_file():
            raise FileNotFoundError(args.dataset_dir / name)

    rgb_rows = read_index(args.dataset_dir / "rgb.txt")
    depth_rows = read_index(args.dataset_dir / "depth.txt")
    matches = associate(rgb_rows, depth_rows, args.max_association_delta)
    selected = matches[:: args.stride][: args.frames]
    if len(selected) < args.frames:
        raise RuntimeError(f"Requested {args.frames} frames, only {len(selected)} associations available")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    from depth_anything_3.api import DepthAnything3

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model = DepthAnything3.from_pretrained(args.model_id, cache_dir=args.cache_dir)
    model = model.to(device="cuda").eval()
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_started

    frame_records: list[dict[str, object]] = []
    metric_accumulator: dict[str, list[float]] = {key: [] for key in ("abs_rel", "rmse_m", "mae_m", "delta1")}
    inference_times: list[float] = []

    for frame_index, (rgb_ts, rgb_relative, depth_ts, depth_relative) in enumerate(selected):
        rgb_path = args.dataset_dir / rgb_relative
        depth_path = args.dataset_dir / depth_relative
        raw_k = TUM_FR1_K[None].copy()

        # Use DA3's own preprocessor to transform K exactly as it transforms the image.
        processed_images, _, processed_ks = model.input_processor(
            [str(rgb_path)],
            intrinsics=raw_k,
            process_res=args.process_res,
            process_res_method="upper_bound_resize",
            num_workers=1,
            sequential=True,
        )
        if processed_ks is None:
            raise RuntimeError("DA3 preprocessor did not return transformed intrinsics")
        processed_k = processed_ks[0].numpy()
        processed_height, processed_width = processed_images.shape[-2:]
        focal_px = float((processed_k[0, 0] + processed_k[1, 1]) / 2.0)

        started = time.perf_counter()
        prediction = model.inference(
            [str(rgb_path)],
            intrinsics=raw_k,
            process_res=args.process_res,
            process_res_method="upper_bound_resize",
        )
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        inference_times.append(elapsed)

        raw_prediction = np.asarray(prediction.depth[0], dtype=np.float32)
        if scalar_int(prediction.is_metric):
            prediction_m = raw_prediction
            conversion = "api_output_already_metric"
        else:
            prediction_m = raw_prediction * (focal_px / METRIC_FOCAL_DIVISOR)
            conversion = "processed_mean_focal_times_raw_depth_div_300"

        if prediction_m.shape != (processed_height, processed_width):
            raise RuntimeError(
                f"Prediction shape {prediction_m.shape} differs from preprocessor "
                f"shape {(processed_height, processed_width)}"
            )
        target_raw = Image.open(depth_path)
        target_resized = target_raw.resize(
            (processed_width, processed_height), resample=Image.Resampling.NEAREST
        )
        target_m = np.asarray(target_resized, dtype=np.float32) / TUM_DEPTH_FACTOR
        metrics = depth_metrics(prediction_m, target_m)
        for key in metric_accumulator:
            metric_accumulator[key].append(float(metrics[key]))

        confidence = (
            np.asarray(prediction.conf[0], dtype=np.float32)
            if prediction.conf is not None
            else np.ones_like(prediction_m, dtype=np.float32)
        )
        np.savez_compressed(
            args.output_dir / f"frame_{frame_index:03d}.npz",
            depth_m=prediction_m,
            target_depth_m=target_m,
            confidence=confidence,
            processed_intrinsics=processed_k,
        )
        frame_records.append(
            {
                "index": frame_index,
                "rgb_timestamp": rgb_ts,
                "rgb_path": rgb_relative,
                "depth_timestamp": depth_ts,
                "depth_path": depth_relative,
                "association_delta_seconds": abs(rgb_ts - depth_ts),
                "processed_shape": [processed_height, processed_width],
                "processed_intrinsics": processed_k.tolist(),
                "metric_conversion": conversion,
                "inference_seconds": elapsed,
                "metrics": metrics,
            }
        )
        print(f"[{frame_index + 1:02d}/{len(selected):02d}] {elapsed:.3f}s abs_rel={metrics['abs_rel']:.4f}")

    timing = np.asarray(inference_times, dtype=np.float64)
    warm_timing = timing[1:] if len(timing) > 1 else timing
    summary = {
        "status": "ok",
        "model_id": args.model_id,
        "dataset": "TUM RGB-D rgbd_dataset_freiburg1_xyz",
        "dataset_dir": str(args.dataset_dir),
        "frames": len(selected),
        "stride": args.stride,
        "process_res": args.process_res,
        "camera_intrinsics_source": "TUM Freiburg 1 RGB calibration",
        "raw_intrinsics": TUM_FR1_K.tolist(),
        "depth_factor": TUM_DEPTH_FACTOR,
        "association_max_delta_seconds": args.max_association_delta,
        "metrics_mean": {key: float(np.mean(values)) for key, values in metric_accumulator.items()},
        "timing_seconds": {
            "model_load": load_seconds,
            "inference_mean": float(timing.mean()),
            "inference_median": float(np.median(timing)),
            "inference_p95": float(np.percentile(timing, 95)),
            "fps_from_mean_inference": float(1.0 / timing.mean()),
            "warm_inference_mean": float(warm_timing.mean()),
            "warm_inference_median": float(np.median(warm_timing)),
            "warm_fps_from_mean_inference": float(1.0 / warm_timing.mean()),
        },
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
        },
        "per_frame": frame_records,
    }
    (args.output_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "per_frame"}, indent=2))


if __name__ == "__main__":
    main()
