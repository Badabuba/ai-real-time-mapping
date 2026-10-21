"""Per-frame metric-depth evaluation against ground truth (docs/EXPERIMENTS.md §4.2).

Ground truth is passed separately and never stored in a GeometryPrediction.
Raw metric depth is scored as is: no median or scale alignment happens here.

Masks:
    gt_valid  = finite(gt) & (gt > 0)
    evaluated = gt_valid & prediction.valid_mask
Metrics use only evaluated pixels; valid_coverage = n_evaluated / n_gt_valid.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction

DELTA1_THRESHOLD = 1.25
_METRIC_KEYS = ("abs_rel", "rmse_m", "mae_m", "delta1")
_COUNT_KEYS = ("n_pixels", "n_gt_valid", "n_pred_valid", "n_evaluated")


@dataclass(frozen=True)
class DepthMetrics:
    """Depth metrics for one frame. Distances in metres, ratios in [0, 1]."""

    frame_id: int
    abs_rel: float
    rmse_m: float
    mae_m: float
    delta1: float
    n_pixels: int
    n_gt_valid: int
    n_pred_valid: int
    n_evaluated: int
    valid_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resize_depth_nearest(depth: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize of an H×W depth map to size = (width, height).

    Pixel centres have integer coordinates (docs/ARCHITECTURE.md §3). Output
    pixel x' has its centre at source coordinate (x' + 0.5)·W/W' - 0.5; the
    nearest source pixel is floor((x' + 0.5)·W/W'), computed exactly as
    ((2x' + 1)·W) // (2W'). Same for rows. Ties go to the higher index.
    Only copies existing values (zeros and NaN stay as they are).
    """
    array = np.asarray(depth)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] == 0:
        raise ValueError(f"depth must be a non-empty H×W array, got shape {array.shape}")
    width, height = size
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError(f"size {name} must be a positive integer, got {value!r}")
    src_h, src_w = array.shape
    cols = np.minimum((2 * np.arange(width, dtype=np.int64) + 1) * src_w // (2 * int(width)), src_w - 1)
    rows = np.minimum((2 * np.arange(height, dtype=np.int64) + 1) * src_h // (2 * int(height)), src_h - 1)
    return array[rows[:, None], cols[None, :]]


def evaluate_depth(prediction: GeometryPrediction, gt_depth_m: np.ndarray) -> DepthMetrics:
    """Score one prediction against ground-truth depth in metres on the same pixel grid.

    Raises ValueError on a shape mismatch or when no pixel is both GT-valid and predicted-valid.
    """
    if not isinstance(prediction, GeometryPrediction):
        raise ValueError(f"prediction must be a GeometryPrediction, got {type(prediction).__name__}")
    gt = np.asarray(gt_depth_m)
    if gt.shape != prediction.depth_m.shape:
        raise ValueError(
            f"gt_depth_m shape {gt.shape} differs from prediction shape {prediction.depth_m.shape}; "
            "resize ground truth explicitly first (resize_depth_nearest)"
        )
    if not np.issubdtype(gt.dtype, np.number) or np.issubdtype(gt.dtype, np.complexfloating):
        raise ValueError(f"gt_depth_m must be a real numeric array, got dtype {gt.dtype}")
    gt = gt.astype(np.float64)

    with np.errstate(invalid="ignore"):
        gt_valid = np.isfinite(gt) & (gt > 0)
    evaluated = gt_valid & prediction.valid_mask
    n_evaluated = int(evaluated.sum())
    n_gt_valid = int(gt_valid.sum())
    if n_evaluated == 0:
        raise ValueError(
            f"frame {prediction.frame_id}: no evaluation pixels "
            f"(gt_valid={n_gt_valid}, pred_valid={int(prediction.valid_mask.sum())})"
        )

    pred = prediction.depth_m[evaluated].astype(np.float64)
    target = gt[evaluated]
    error = pred - target
    ratio = np.maximum(pred / target, target / pred)
    return DepthMetrics(
        frame_id=prediction.frame_id,
        abs_rel=float(np.mean(np.abs(error) / target)),
        rmse_m=float(np.sqrt(np.mean(error**2))),
        mae_m=float(np.mean(np.abs(error))),
        delta1=float(np.mean(ratio < DELTA1_THRESHOLD)),
        n_pixels=int(gt.size),
        n_gt_valid=n_gt_valid,
        n_pred_valid=int(prediction.valid_mask.sum()),
        n_evaluated=n_evaluated,
        valid_coverage=n_evaluated / n_gt_valid,
    )


def mean_depth_metrics(frames: Sequence[DepthMetrics]) -> dict[str, Any]:
    """Unweighted per-frame mean of the metrics plus summed pixel counts.

    valid_coverage here is pooled: sum(n_evaluated) / sum(n_gt_valid).
    """
    if not frames:
        raise ValueError("mean_depth_metrics needs at least one frame")
    if not all(isinstance(f, DepthMetrics) for f in frames):
        raise ValueError("frames must all be DepthMetrics")
    summary: dict[str, Any] = {"aggregation": "frame_mean", "n_frames": len(frames)}
    for key in _METRIC_KEYS:
        summary[key] = float(np.mean([getattr(f, key) for f in frames]))
    for key in _COUNT_KEYS:
        summary[key] = int(sum(getattr(f, key) for f in frames))
    summary["valid_coverage"] = summary["n_evaluated"] / summary["n_gt_valid"]
    return summary
