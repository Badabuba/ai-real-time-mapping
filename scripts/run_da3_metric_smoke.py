"""Run one-image DA3 metric-depth inference and save reproducible artifacts."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, help="RGB image; omit for a synthetic smoke input")
    parser.add_argument("--output-dir", type=Path, default=Path("results/runs/da3metric_smoke"))
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--process-res", type=int, default=384)
    parser.add_argument(
        "--processed-focal-px",
        type=float,
        help="Focal length after DA3 preprocessing; required for real images if API returns no K",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("checkpoints/huggingface"))
    return parser.parse_args()


def synthetic_image() -> Image.Image:
    height, width = 360, 640
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = x[None, :]
    image[..., 1] = y
    image[..., 2] = 127
    return Image.fromarray(image, mode="RGB")


def scalar_int(value: object) -> int:
    if isinstance(value, torch.Tensor):
        return int(value.detach().cpu().reshape(-1)[0].item())
    if isinstance(value, dict):
        # DA3's Addict output auto-creates an empty Dict for a missing is_metric field.
        return int(value.get("value", 0)) if value else 0
    if hasattr(value, "item"):
        return int(value.item())
    return int(value)


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for the WP1 DA3 smoke run")

    if args.image is not None and not args.image.is_file():
        raise FileNotFoundError(args.image)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    image: Image.Image | str = str(args.image) if args.image else synthetic_image()

    from depth_anything_3.api import DepthAnything3

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    load_started = time.perf_counter()
    model = DepthAnything3.from_pretrained(args.model_id, cache_dir=args.cache_dir)
    model = model.to(device="cuda").eval()
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_started

    inference_started = time.perf_counter()
    prediction = model.inference([image], process_res=args.process_res)
    torch.cuda.synchronize()
    inference_seconds = time.perf_counter() - inference_started

    raw_depth = np.asarray(prediction.depth[0], dtype=np.float32)
    is_metric = scalar_int(prediction.is_metric)
    if is_metric:
        depth_m = raw_depth
        metric_conversion = "api_output_already_metric"
        focal_px = None
    else:
        if prediction.intrinsics is not None:
            focal_px = float(
                (prediction.intrinsics[0, 0, 0] + prediction.intrinsics[0, 1, 1]) / 2.0
            )
            metric_conversion = "predicted_focal_px_times_raw_depth_div_300"
        elif args.processed_focal_px is not None:
            focal_px = args.processed_focal_px
            metric_conversion = "provided_processed_focal_px_times_raw_depth_div_300"
        elif args.image is None:
            focal_px = METRIC_FOCAL_DIVISOR
            metric_conversion = "synthetic_placeholder_focal_300_smoke_only"
        else:
            raise RuntimeError(
                "DA3METRIC-LARGE requires --processed-focal-px for metric conversion "
                "when the API returns no intrinsics"
            )
        depth_m = raw_depth * (focal_px / METRIC_FOCAL_DIVISOR)

    confidence = (
        np.asarray(prediction.conf[0], dtype=np.float32)
        if prediction.conf is not None
        else np.ones_like(depth_m, dtype=np.float32)
    )
    if prediction.intrinsics is not None:
        intrinsics = np.asarray(prediction.intrinsics[0], dtype=np.float32)
    elif focal_px is not None:
        height, width = depth_m.shape
        intrinsics = np.array(
            [[focal_px, 0.0, width / 2.0], [0.0, focal_px, height / 2.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
    else:
        intrinsics = np.full((3, 3), np.nan, dtype=np.float32)
    valid = np.isfinite(depth_m) & (depth_m > 0)

    np.savez_compressed(
        args.output_dir / "prediction.npz",
        depth_m=depth_m,
        raw_depth=raw_depth,
        confidence=confidence,
        intrinsics=intrinsics,
        valid_mask=valid,
    )

    manifest = {
        "status": "ok",
        "model_id": args.model_id,
        "image": str(args.image) if args.image else "synthetic_gradient_640x360",
        "process_res": args.process_res,
        "output_shape": list(depth_m.shape),
        "api_is_metric": is_metric,
        "metric_conversion": metric_conversion,
        "processed_focal_px": focal_px,
        "valid_fraction": float(valid.mean()),
        "depth_m": {
            "min": float(depth_m[valid].min()),
            "median": float(np.median(depth_m[valid])),
            "max": float(depth_m[valid].max()),
        },
        "timing_seconds": {"model_load": load_seconds, "inference": inference_seconds},
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
        },
    }
    (args.output_dir / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
