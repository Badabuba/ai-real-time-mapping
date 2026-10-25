"""Evaluation-only prediction resampling to a common pixel grid (no GT input)."""

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.geometry.intrinsics import resize_intrinsics


def resize_prediction(prediction: GeometryPrediction, target_wh: tuple[int, int]) -> GeometryPrediction:
    """Bilinear, align_corners=False, border replication; requires all-valid input.

    The original prediction artifact is never changed. Strict adapters currently
    reject invalid values; refusing partial masks avoids manufacturing coverage.
    """
    width, height = target_wh
    old_h, old_w = prediction.depth_m.shape
    if (width, height) == (old_w, old_h):
        return prediction
    if not prediction.valid_mask.all():
        raise ValueError("common-grid evaluation requires all-valid predictions")
    if width < 1 or height < 1:
        raise ValueError("target grid must be positive")
    xx = np.clip((np.arange(width) + .5) * old_w / width - .5, 0, old_w - 1)
    yy = np.clip((np.arange(height) + .5) * old_h / height - .5, 0, old_h - 1)
    x0, y0 = np.floor(xx).astype(int), np.floor(yy).astype(int)
    x1, y1 = np.minimum(x0 + 1, old_w - 1), np.minimum(y0 + 1, old_h - 1)
    wx, wy = xx - x0, yy - y0

    def interpolate(array):
        rows = array[:, x0] * (1 - wx) + array[:, x1] * wx
        return (rows[y0] * (1 - wy[:, None]) + rows[y1] * wy[:, None]).astype(np.float32)

    return GeometryPrediction(
        prediction.frame_id, prediction.timestamp_s, interpolate(prediction.depth_m),
        np.ones((height, width), bool),
        None if prediction.confidence is None else interpolate(prediction.confidence),
        resize_intrinsics(prediction.K_processed, (old_w, old_h), target_wh),
        prediction.model_id, {**prediction.preprocess, "evaluation_resize": {
            "from_wh": [old_w, old_h], "to_wh": [width, height],
            "mode": "bilinear align_corners=False; border replication"}}, prediction.inference_ms,
    )
