from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from rt_mapping.contracts import GeometryPrediction
from rt_mapping.evaluation import evaluate_depth, mean_depth_metrics, resize_depth_nearest

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_MODULES = ("torch", "depth_anything_3", "unidepth", "pyslam", "cv2", "PIL")


def make_prediction(depth: np.ndarray, frame_id: int = 0) -> GeometryPrediction:
    depth = np.asarray(depth, dtype=np.float32)
    mask = np.isfinite(depth)
    return GeometryPrediction(
        frame_id=frame_id,
        timestamp_s=0.0,
        depth_m=depth,
        valid_mask=mask,
        confidence=None,
        K_processed=np.array([[100.0, 0.0, 1.0], [0.0, 100.0, 0.5], [0.0, 0.0, 1.0]]),
        model_id="dummy@0",
        preprocess={},
        inference_ms=0.0,
    )


# Pixels used: (0,0) exact; (0,1) ratio 1.2 -> counted in δ1; (1,0) ratio exactly 1.25 -> not counted.
# Excluded: (0,2) GT 0; (1,1) prediction invalid; (1,2) GT NaN.
PRED = [[1.0, 2.0, 4.0], [1.25, np.nan, 3.0]]
GT = np.array([[1.0, 2.4, 0.0], [1.0, 2.0, np.nan]])


def test_hand_computed_metrics() -> None:
    m = evaluate_depth(make_prediction(PRED, frame_id=5), GT)
    assert m.frame_id == 5
    assert m.abs_rel == pytest.approx((0.0 + 0.4 / 2.4 + 0.25) / 3)
    assert m.mae_m == pytest.approx((0.0 + 0.4 + 0.25) / 3)
    assert m.rmse_m == pytest.approx(math.sqrt((0.0 + 0.16 + 0.0625) / 3))
    assert m.delta1 == pytest.approx(2 / 3)
    assert (m.n_pixels, m.n_gt_valid, m.n_pred_valid, m.n_evaluated) == (6, 4, 5, 3)
    assert m.valid_coverage == pytest.approx(3 / 4)


def test_to_dict_has_all_fields() -> None:
    d = evaluate_depth(make_prediction(PRED), GT).to_dict()
    assert set(d) == {
        "frame_id", "abs_rel", "rmse_m", "mae_m", "delta1",
        "n_pixels", "n_gt_valid", "n_pred_valid", "n_evaluated", "valid_coverage",
    }


def test_inputs_are_not_modified() -> None:
    gt = GT.copy()
    pred = make_prediction(PRED)
    evaluate_depth(pred, gt)
    np.testing.assert_array_equal(gt, GT)
    assert not hasattr(pred, "gt_depth_m")


@pytest.mark.parametrize("bad", [0.0, -1.0, np.nan, np.inf, -np.inf])
def test_invalid_gt_values_are_excluded(bad: float) -> None:
    gt = np.array([[2.0, bad]])
    m = evaluate_depth(make_prediction([[2.0, 1.0]]), gt)
    assert (m.n_gt_valid, m.n_evaluated, m.abs_rel, m.valid_coverage) == (1, 1, 0.0, 1.0)


def test_coverage_counts_prediction_holes() -> None:
    gt = np.full((2, 2), 2.0)
    m = evaluate_depth(make_prediction([[2.0, np.nan], [np.nan, np.nan]]), gt)
    assert (m.n_gt_valid, m.n_evaluated, m.valid_coverage) == (4, 1, 0.25)


def test_rejects_zero_evaluation_pixels() -> None:
    with pytest.raises(ValueError, match="no evaluation pixels"):
        evaluate_depth(make_prediction([[1.0, np.nan]]), np.array([[0.0, 2.0]]))


def test_rejects_all_invalid_ground_truth() -> None:
    with pytest.raises(ValueError, match="no evaluation pixels"):
        evaluate_depth(make_prediction([[1.0, 2.0]]), np.array([[np.nan, 0.0]]))


def test_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="resize ground truth"):
        evaluate_depth(make_prediction([[1.0, 2.0]]), np.ones((2, 2)))


def test_rejects_non_prediction() -> None:
    with pytest.raises(ValueError, match="GeometryPrediction"):
        evaluate_depth(np.ones((2, 2), dtype=np.float32), np.ones((2, 2)))  # type: ignore[arg-type]


def test_integer_gt_is_accepted() -> None:
    m = evaluate_depth(make_prediction([[2.0, 4.0]]), np.array([[2, 4]], dtype=np.uint16))
    assert m.abs_rel == 0.0 and m.delta1 == 1.0


def test_mean_depth_metrics_is_frame_mean_with_pooled_coverage() -> None:
    a = evaluate_depth(make_prediction(PRED, 0), GT)
    b = evaluate_depth(make_prediction([[2.0, np.nan]], 1), np.array([[1.0, 1.0]]))
    s = mean_depth_metrics([a, b])
    assert s["aggregation"] == "frame_mean" and s["n_frames"] == 2
    assert s["abs_rel"] == pytest.approx((a.abs_rel + b.abs_rel) / 2)
    assert s["delta1"] == pytest.approx((2 / 3 + 0.0) / 2)
    assert (s["n_gt_valid"], s["n_evaluated"]) == (6, 4)
    assert s["valid_coverage"] == pytest.approx(4 / 6)


def test_mean_depth_metrics_rejects_empty() -> None:
    with pytest.raises(ValueError):
        mean_depth_metrics([])


# --- nearest-neighbour resize ---------------------------------------------------


def _index_grid(h: int, w: int) -> np.ndarray:
    return np.arange(h * w, dtype=np.float64).reshape(h, w)


def test_resize_identity() -> None:
    src = _index_grid(3, 5)
    np.testing.assert_array_equal(resize_depth_nearest(src, (5, 3)), src)


@pytest.mark.parametrize(
    ("src_w", "dst_w", "expected_cols"),
    [(4, 2, [1, 3]), (2, 4, [0, 0, 1, 1]), (3, 2, [0, 2]), (5, 3, [0, 2, 4])],
)
def test_resize_column_map(src_w: int, dst_w: int, expected_cols: list[int]) -> None:
    src = _index_grid(1, src_w)
    np.testing.assert_array_equal(resize_depth_nearest(src, (dst_w, 1))[0], expected_cols)


def test_resize_tum_to_da3_grid_matches_integer_formula() -> None:
    src = _index_grid(480, 640)
    out = resize_depth_nearest(src, (378, 294))
    assert out.shape == (294, 378)
    rows = [((2 * y + 1) * 480) // (2 * 294) for y in range(294)]
    cols = [((2 * x + 1) * 640) // (2 * 378) for x in range(378)]
    np.testing.assert_array_equal(out, src[np.ix_(rows, cols)])
    np.testing.assert_array_equal(resize_depth_nearest(src, (378, 294)), out)  # deterministic


def test_resize_preserves_values_and_dtype() -> None:
    src = np.array([[0.0, np.nan], [1.5, 2.5]], dtype=np.float32)
    out = resize_depth_nearest(src, (4, 4))
    assert out.dtype == np.float32
    assert set(np.unique(out[np.isfinite(out)]).tolist()) <= {0.0, 1.5, 2.5}
    assert np.isnan(out[0, 3]) and out[0, 0] == 0.0


@pytest.mark.parametrize("size", [(0, 2), (2, -1), (2.0, 2), (True, 2)])
def test_resize_rejects_bad_size(size: tuple) -> None:
    with pytest.raises(ValueError):
        resize_depth_nearest(np.ones((2, 2)), size)


def test_resize_rejects_non_2d() -> None:
    with pytest.raises(ValueError):
        resize_depth_nearest(np.ones((2, 2, 1)), (2, 2))


def test_evaluation_and_run_manifest_import_no_model_packages() -> None:
    script = (
        "import sys\n"
        "import rt_mapping.evaluation, rt_mapping.contracts.run_manifest\n"
        f"print(sorted(m for m in {FORBIDDEN_MODULES!r} if m in sys.modules))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "[]"
