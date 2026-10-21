"""DA3 Metric adapter with a fake backend (CPU only, no torch, no model download)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from conftest import FakeDa3Backend, SynthRepo
from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import load_prediction, save_prediction
from rt_mapping.data import tum
from rt_mapping.geometry.adapter import GeometryAdapter, GeometryAdapterError
from rt_mapping.geometry.intrinsics import resize_intrinsics
from rt_mapping.adapters.da3_metric import (
    DEFAULT_REVISION,
    Da3MetricAdapter,
    Da3MetricConfig,
    da3_preprocess_plan,
    da3_processed_size,
    raw_to_metric_depth,
)

K_FR1 = tum.rgb_intrinsics("freiburg1")


def frames(repo: SynthRepo) -> list[FrameRecord]:
    return [f.frame for f in tum.load_sequence(repo.sequence_dir)]


def adapter(repo: SynthRepo, backend: FakeDa3Backend | None = None, **config) -> Da3MetricAdapter:
    return Da3MetricAdapter(Da3MetricConfig(**config), repo.sequence_dir, backend=backend or FakeDa3Backend())


# --- preprocessing geometry -------------------------------------------------


@pytest.mark.parametrize(
    "size, res, expected",
    [
        ((640, 480), 384, (378, 294)),  # 384x288 -> nearest multiples of 14
        ((640, 480), 504, (504, 378)),  # 504x378 already divisible
        ((480, 640), 384, (294, 378)),  # portrait
        ((378, 294), 378, (378, 294)),  # nothing to do
    ],
)
def test_processed_size_matches_da3_rules(size, res, expected) -> None:
    assert da3_processed_size(*size, res) == expected


def test_preprocess_plan_records_both_da3_resizes() -> None:
    _, steps, out = da3_preprocess_plan(K_FR1, 640, 480, 384)
    assert out == (378, 294)
    assert steps == [
        {"op": "resize", "from_wh": [640, 480], "to_wh": [384, 288], "interpolation": "cv2.INTER_AREA"},
        {"op": "resize", "from_wh": [384, 288], "to_wh": [378, 294], "interpolation": "cv2.INTER_CUBIC"},
    ]
    assert da3_preprocess_plan(K_FR1, 378, 294, 378)[1] == []


def test_unsupported_resize_method_is_rejected() -> None:
    with pytest.raises(GeometryAdapterError, match="unsupported_config"):
        da3_preprocess_plan(K_FR1, 640, 480, 384, "upper_bound_crop")


def test_k_processed_uses_integer_pixel_centres_and_documents_historical_offset() -> None:
    k, _, _ = da3_preprocess_plan(K_FR1, 640, 480, 384)
    two_step = resize_intrinsics(resize_intrinsics(K_FR1, (640, 480), (384, 288)), (384, 288), (378, 294))
    one_step = resize_intrinsics(K_FR1, (640, 480), (378, 294))
    np.testing.assert_allclose(k, two_step, rtol=0, atol=1e-12)
    np.testing.assert_allclose(k, one_step, rtol=0, atol=1e-9)

    # Historical runner (DA3 _resize_ixt): every K row scaled, i.e. cx * sx, cy * sy.
    sx, sy = 378 / 640, 294 / 480
    historical = np.array([[517.3 * sx, 0, 318.6 * sx], [0, 516.5 * sy, 255.3 * sy], [0, 0, 1]])
    np.testing.assert_allclose(k[[0, 1], [0, 1]], historical[[0, 1], [0, 1]], atol=1e-9)  # same focal
    assert k[0, 2] - historical[0, 2] == pytest.approx(-0.5 * (1 - sx), abs=1e-9)  # -0.2047 px
    assert k[1, 2] - historical[1, 2] == pytest.approx(-0.5 * (1 - sy), abs=1e-9)  # -0.1937 px
    # Values recorded by the historical 20-frame run (float32): 188.17313, 156.37126.
    assert k[0, 2] - 188.17312622070312 == pytest.approx(-0.2047, abs=1e-3)
    assert k[1, 2] - 156.3712615966797 == pytest.approx(-0.1937, abs=1e-3)


def test_metric_conversion_uses_mean_processed_focal() -> None:
    k, _, _ = da3_preprocess_plan(K_FR1, 640, 480, 384)
    raw = np.array([[1.0, 2.0]], dtype=np.float32)
    focal = (k[0, 0] + k[1, 1]) / 2
    out = raw_to_metric_depth(raw, k)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, raw * focal / 300.0, rtol=1e-6)


# --- config -------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"dtype": "float32"},
        {"device": "cpu"},
        {"device": "cuda:x"},
        {"process_res": 0},
        {"process_res": True},
        {"process_res_method": "lower_bound_resize"},
        {"revision": "main"},
        {"repo": "/abs/path"},
        {"seed": -1},
    ],
)
def test_config_rejects_unsupported_values(overrides) -> None:
    with pytest.raises(GeometryAdapterError) as info:
        Da3MetricConfig(**overrides)
    assert info.value.reason == "unsupported_config"


def test_config_record_has_no_host_paths() -> None:
    record = Da3MetricConfig(cache_dir=Path("C:/Users/someone/cache")).to_record()
    assert "cache_dir" not in record
    assert "someone" not in json.dumps(record)
    assert Da3MetricConfig().model_id == f"depth-anything/DA3METRIC-LARGE@{DEFAULT_REVISION}"


def test_requested_dtype_must_match_backend_autocast(synth_repo: SynthRepo) -> None:
    with pytest.raises(GeometryAdapterError) as info:
        adapter(synth_repo, FakeDa3Backend(autocast="float16"), dtype="bfloat16")
    assert info.value.reason == "unsupported_config"
    assert adapter(synth_repo, FakeDa3Backend(autocast="float16"), dtype="float16").info.autocast_dtype == "float16"


# --- predict ----------------------------------------------------------------


def test_predict_returns_valid_contract_and_loads_model_once(synth_repo: SynthRepo) -> None:
    backend = FakeDa3Backend()
    a = adapter(synth_repo, backend)
    assert isinstance(a, GeometryAdapter)
    preds = [a.predict(f) for f in frames(synth_repo)]
    assert backend.load_calls == 1 and backend.infer_calls == len(preds)
    k, steps, _ = da3_preprocess_plan(K_FR1, 640, 480, 384)
    for frame, pred in zip(frames(synth_repo), preds):
        assert pred.frame_id == frame.frame_id and pred.timestamp_s == frame.timestamp_s
        assert pred.depth_m.shape == (294, 378) and pred.depth_m.dtype == np.float32
        assert pred.valid_mask.all()
        np.testing.assert_array_equal(pred.K_processed, k)
        assert pred.model_id == f"depth-anything/DA3METRIC-LARGE@{DEFAULT_REVISION}"
        assert pred.preprocess["steps"] == steps
        assert pred.preprocess["intrinsics_convention"] == "pixel_centers_integer"
        assert pred.preprocess["metric_conversion"] == "raw * mean(fx, fy) / 300"
        assert pred.inference_ms > 0


def test_no_confidence_is_never_fabricated(synth_repo: SynthRepo, tmp_path: Path) -> None:
    pred = adapter(synth_repo).predict(frames(synth_repo)[0])
    assert pred.confidence is None
    assert pred.preprocess["confidence"] == "not provided by model"
    path = tmp_path / "p.npz"
    save_prediction(pred, path)
    with zipfile.ZipFile(path) as zf:
        assert sorted(zf.namelist()) == ["K_processed.npy", "depth_m.npy", "meta.json", "valid_mask.npy"]
        assert json.loads(zf.read("meta.json"))["has_confidence"] is False
    assert load_prediction(path).confidence is None


def test_model_confidence_is_passed_through(synth_repo: SynthRepo) -> None:
    pred = adapter(synth_repo, FakeDa3Backend(conf=True)).predict(frames(synth_repo)[0])
    assert pred.confidence is not None and pred.confidence.dtype == np.float32
    assert not np.all(pred.confidence == 1.0)
    assert pred.preprocess["confidence"].startswith("raw DA3 depth_conf")


def test_metric_output_from_api_is_not_rescaled(synth_repo: SynthRepo) -> None:
    pred = adapter(synth_repo, FakeDa3Backend(is_metric=True, depth_fn=lambda rgb, hw: np.full(hw, 1.25, np.float32))).predict(
        frames(synth_repo)[0]
    )
    np.testing.assert_array_equal(pred.depth_m, np.full((294, 378), 1.25, np.float32))
    assert pred.preprocess["metric_conversion"].startswith("none")


@pytest.mark.parametrize(
    "backend, reason",
    [
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.full(hw, np.nan, np.float32)), "non_finite_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.full(hw, np.inf, np.float32)), "non_finite_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.zeros(hw, np.float32)), "non_finite_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: -np.ones(hw, np.float32)), "non_finite_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.ones((hw[0] + 1, hw[1]), np.float32)), "unexpected_model_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.ones((1, *hw), np.float32)), "unexpected_model_output"),
        (FakeDa3Backend(depth_fn=lambda rgb, hw: np.ones(hw, np.int32)), "unexpected_model_output"),
        (FakeDa3Backend(intrinsics=np.eye(3)), "unexpected_model_output"),
    ],
)
def test_bad_model_output_raises_with_reason(synth_repo: SynthRepo, backend, reason) -> None:
    with pytest.raises(GeometryAdapterError) as info:
        adapter(synth_repo, backend).predict(frames(synth_repo)[0])
    assert info.value.reason == reason


def test_single_bad_pixel_is_not_silently_masked(synth_repo: SynthRepo) -> None:
    def one_nan(rgb, hw):
        depth = np.ones(hw, np.float32)
        depth[3, 4] = np.nan
        return depth

    with pytest.raises(GeometryAdapterError, match="1 of 111132"):
        adapter(synth_repo, FakeDa3Backend(depth_fn=one_nan)).predict(frames(synth_repo)[0])


def test_missing_image_and_wrong_size_are_input_errors(synth_repo: SynthRepo) -> None:
    frame = frames(synth_repo)[0]
    a = adapter(synth_repo)
    missing = FrameRecord(frame.sequence_id, 0, 1.0, "rgb/nope.png", 640, 480, frame.K)
    with pytest.raises(GeometryAdapterError) as info:
        a.predict(missing)
    assert info.value.reason == "missing_input"
    wrong = FrameRecord(frame.sequence_id, 0, 1.0, frame.image_path, 320, 240, frame.K)
    with pytest.raises(GeometryAdapterError) as info:
        a.predict(wrong)
    assert info.value.reason == "unexpected_input"


def test_describe_gives_truthful_model_record(synth_repo: SynthRepo) -> None:
    d = adapter(synth_repo).describe()
    assert d["model"] == {
        "repo": "depth-anything/DA3METRIC-LARGE",
        "revision": DEFAULT_REVISION,
        "checkpoint": "model.safetensors@sha256:" + "ab" * 32,
        "dtype": "bfloat16",
    }
    assert d["gpu"] == "Fake GPU"
    assert d["config"]["autocast_dtype"] == "bfloat16" and d["config"]["weights_dtype"] == "float32"
    json.dumps(d, allow_nan=False)


def test_preprocess_is_deterministic(synth_repo: SynthRepo) -> None:
    frame = frames(synth_repo)[1]
    one = adapter(synth_repo).predict(frame)
    two = adapter(synth_repo).predict(frame)
    assert json.dumps(one.preprocess, sort_keys=True) == json.dumps(two.preprocess, sort_keys=True)
    np.testing.assert_array_equal(one.depth_m, two.depth_m)
