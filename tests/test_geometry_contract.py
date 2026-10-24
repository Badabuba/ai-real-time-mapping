from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rt_mapping.contracts import FrameRecord, GeometryPrediction, load_prediction, save_prediction
from rt_mapping.geometry import GeometryAdapter, resize_intrinsics

SRC = Path(__file__).resolve().parents[1] / "src"
K_FR1 = np.array([[517.3, 0.0, 318.6], [0.0, 516.5, 255.3], [0.0, 0.0, 1.0]])
FORBIDDEN_MODULES = ("torch", "depth_anything_3", "unidepth", "pyslam")


def _depth_and_mask() -> tuple[np.ndarray, np.ndarray]:
    depth = np.linspace(0.5, 3.0, 12, dtype=np.float32).reshape(3, 4)
    mask = np.ones((3, 4), dtype=bool)
    mask[0, 0] = mask[2, 3] = False
    depth[~mask] = np.nan
    return depth, mask


def make_prediction(**overrides: Any) -> GeometryPrediction:
    depth, mask = _depth_and_mask()
    fields: dict[str, Any] = {
        "frame_id": 7,
        "timestamp_s": 1305031102.175304,
        "depth_m": depth,
        "valid_mask": mask,
        "confidence": np.full((3, 4), 0.25, dtype=np.float32),
        "K_processed": np.array([[300.0, 0.0, 1.5], [0.0, 310.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float32),
        "model_id": "depth-anything/DA3METRIC-LARGE@abc123",
        "preprocess": {"resize": {"method": "upper_bound_resize", "size": [4, 3]}, "crop": None, "dtype": "float32"},
        "inference_ms": 98.5,
    }
    fields.update(overrides)
    return GeometryPrediction(**fields)


def _assert_equal(a: GeometryPrediction, b: GeometryPrediction) -> None:
    assert (a.frame_id, a.timestamp_s, a.model_id, a.preprocess, a.inference_ms) == (
        b.frame_id,
        b.timestamp_s,
        b.model_id,
        b.preprocess,
        b.inference_ms,
    )
    np.testing.assert_array_equal(a.depth_m, b.depth_m)  # NaN-aware
    np.testing.assert_array_equal(a.valid_mask, b.valid_mask)
    np.testing.assert_array_equal(a.K_processed, b.K_processed)
    if a.confidence is None:
        assert b.confidence is None
    else:
        np.testing.assert_array_equal(a.confidence, b.confidence)
    assert a.depth_m.dtype == b.depth_m.dtype == np.float32
    assert a.K_processed.dtype == b.K_processed.dtype == np.float64


# --- construction -----------------------------------------------------------


def test_valid_prediction_is_normalised_and_read_only() -> None:
    pred = make_prediction()
    assert pred.K_processed.dtype == np.float64
    for array in (pred.depth_m, pred.valid_mask, pred.confidence, pred.K_processed):
        assert not array.flags.writeable
    assert pred.confidence is not None


def test_inputs_are_copied() -> None:
    depth, mask = _depth_and_mask()
    pred = make_prediction(depth_m=depth, valid_mask=mask)
    depth[1, 1] = 99.0
    assert pred.depth_m[1, 1] != 99.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"depth_m": np.ones((3, 4, 1), dtype=np.float32)},
        {"depth_m": np.ones((0, 4), dtype=np.float32), "valid_mask": np.ones((0, 4), bool), "confidence": None},
        {"depth_m": np.ones((3, 4), dtype=np.float64), "valid_mask": np.ones((3, 4), bool)},
        {"depth_m": [[1.0]]},
        {"valid_mask": np.ones((3, 4), dtype=np.uint8)},
        {"valid_mask": np.ones((4, 3), dtype=bool)},
        {"K_processed": np.eye(2)},
        {"K_processed": np.array([[0.0, 0, 1], [0, 300, 1], [0, 0, 1]])},
        {"K_processed": np.array([[300.0, 0, 1], [0, 300, 1], [0, 0, 2]])},
        {"K_processed": np.array([[300.0, 0, 1], [0, 300, 1], [0, 0, np.nan]])},
        {"frame_id": -1},
        {"frame_id": True},
        {"timestamp_s": float("nan")},
        {"model_id": ""},
        {"model_id": "C:\\checkpoints\\da3.safetensors"},
        {"model_id": "/home/user/checkpoints/da3"},
        {"inference_ms": -1.0},
        {"inference_ms": float("nan")},
        {"inference_ms": float("inf")},
        {"inference_ms": "98"},
    ],
)
def test_rejects_invalid_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        make_prediction(**overrides)


# --- depth / mask invariant -------------------------------------------------


@pytest.mark.parametrize(
    "pixel, value",
    [((1, 1), np.nan), ((0, 0), 1.0), ((1, 1), 0.0), ((1, 1), -0.5), ((1, 1), np.inf), ((0, 0), np.inf)],
)
def test_depth_must_match_mask(pixel: tuple[int, int], value: float) -> None:
    depth, mask = _depth_and_mask()
    depth[pixel] = value
    with pytest.raises(ValueError):
        make_prediction(depth_m=depth, valid_mask=mask)


def test_all_invalid_frame_is_allowed() -> None:
    depth = np.full((3, 4), np.nan, dtype=np.float32)
    pred = make_prediction(depth_m=depth, valid_mask=np.zeros((3, 4), bool), confidence=None)
    assert not pred.valid_mask.any()


# --- confidence -------------------------------------------------------------


def test_confidence_none_is_kept() -> None:
    assert make_prediction(confidence=None).confidence is None


def test_constant_confidence_is_accepted() -> None:
    pred = make_prediction(confidence=np.ones((3, 4), dtype=np.float32))
    assert np.all(pred.confidence == 1.0)


def test_confidence_may_be_nan_on_invalid_pixels_only() -> None:
    conf = np.full((3, 4), 0.5, dtype=np.float32)
    conf[0, 0] = np.nan  # invalid pixel
    make_prediction(confidence=conf)
    conf[1, 1] = np.nan  # valid pixel
    with pytest.raises(ValueError):
        make_prediction(confidence=conf)


@pytest.mark.parametrize(
    "conf", [np.ones((3, 4), dtype=np.float64), np.ones((4, 3), dtype=np.float32), [[1.0] * 4] * 3]
)
def test_confidence_rejects_bad_dtype_or_shape(conf: Any) -> None:
    with pytest.raises(ValueError):
        make_prediction(confidence=conf)


# --- preprocess metadata ----------------------------------------------------


def test_preprocess_is_copied_on_construction() -> None:
    preprocess = {"resize": {"size": [4, 3]}, "dtype": "float32"}
    pred = make_prediction(preprocess=preprocess)
    preprocess["dtype"] = "float16"
    preprocess["resize"]["size"].append(99)
    preprocess["new"] = 1
    assert pred.preprocess == {"resize": {"size": [4, 3]}, "dtype": "float32"}


@pytest.mark.parametrize(
    "preprocess",
    [
        {"scale": float("nan")},
        {"nested": {"scale": float("inf")}},
        {"list": [1.0, float("-inf")]},
        {1: "int key"},
        {"nested": {2: "int key"}},
        {"size": (4, 3)},
        {"size": np.int64(4)},
        {"array": np.zeros(2)},
        {"cache": "D:\\models\\da3"},
        {"cache": ["~/models"]},
        ["not", "a", "dict"],
    ],
)
def test_preprocess_rejects_non_json_or_unsafe_values(preprocess: Any) -> None:
    with pytest.raises(ValueError):
        make_prediction(preprocess=preprocess)


# --- serialization ----------------------------------------------------------


@pytest.mark.parametrize("with_confidence", [True, False])
def test_round_trip(tmp_path: Path, with_confidence: bool) -> None:
    pred = make_prediction() if with_confidence else make_prediction(confidence=None)
    path = tmp_path / "pred.npz"
    save_prediction(pred, path)
    loaded = load_prediction(path)
    _assert_equal(pred, loaded)
    assert (loaded.confidence is None) == (not with_confidence)


def test_serialization_is_byte_deterministic(tmp_path: Path) -> None:
    save_prediction(make_prediction(), tmp_path / "a.npz")
    save_prediction(make_prediction(), tmp_path / "b.npz")
    assert (tmp_path / "a.npz").read_bytes() == (tmp_path / "b.npz").read_bytes()


def test_saved_entries_have_no_ground_truth_or_paths(tmp_path: Path) -> None:
    path = tmp_path / "pred.npz"
    save_prediction(make_prediction(), path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        meta = json.loads(zf.read("meta.json"))
    assert names == ["depth_m.npy", "valid_mask.npy", "K_processed.npy", "confidence.npy", "meta.json"]
    assert not any("target" in n or "gt" in n.lower() for n in names + list(meta))
    assert str(tmp_path) not in json.dumps(meta)
    assert set(meta) == {"schema", "frame_id", "timestamp_s", "model_id", "preprocess", "inference_ms", "has_confidence"}


def test_load_rejects_extra_ground_truth_entry(tmp_path: Path) -> None:
    path = tmp_path / "pred.npz"
    save_prediction(make_prediction(), path)
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("target_depth_m.npy", b"")
    with pytest.raises(ValueError):
        load_prediction(path)


def test_load_rejects_missing_confidence_entry(tmp_path: Path) -> None:
    good = tmp_path / "good.npz"
    save_prediction(make_prediction(), good)
    bad = tmp_path / "bad.npz"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            if name != "confidence.npy":
                dst.writestr(name, src.read(name))
    with pytest.raises(ValueError):
        load_prediction(bad)


# --- adapter interface ------------------------------------------------------


class DummyAdapter:
    """Minimal model-free adapter: constant 2 m depth at half resolution."""

    def predict(self, frame: FrameRecord) -> GeometryPrediction:
        size = (frame.width // 2, frame.height // 2)
        depth = np.full((size[1], size[0]), 2.0, dtype=np.float32)
        return GeometryPrediction(
            frame_id=frame.frame_id,
            timestamp_s=frame.timestamp_s,
            depth_m=depth,
            valid_mask=np.ones(depth.shape, dtype=bool),
            confidence=None,
            K_processed=resize_intrinsics(frame.K, (frame.width, frame.height), size),
            model_id="dummy/constant@0",
            preprocess={"resize": {"size": list(size)}},
            inference_ms=0.0,
        )


def _frame() -> FrameRecord:
    return FrameRecord("rgbd_dataset_freiburg1_xyz", 3, 1305031102.175304, "rgb/1305031102.175304.png", 640, 480, K_FR1)


def test_dummy_adapter_satisfies_protocol() -> None:
    adapter = DummyAdapter()
    assert isinstance(adapter, GeometryAdapter)
    assert not isinstance(object(), GeometryAdapter)
    pred = adapter.predict(_frame())
    assert pred.depth_m.shape == (240, 320)
    assert (pred.frame_id, pred.timestamp_s) == (3, 1305031102.175304)
    assert pred.confidence is None


def test_contract_and_adapter_import_no_model_packages() -> None:
    script = (
        "import sys\n"
        "import numpy as np\n"
        "from rt_mapping.contracts import FrameRecord, GeometryPrediction\n"
        "from rt_mapping.geometry import GeometryAdapter, resize_intrinsics\n"
        "class A:\n"
        "    def predict(self, frame):\n"
        "        d = np.ones((2, 2), dtype=np.float32)\n"
        "        return GeometryPrediction(frame.frame_id, frame.timestamp_s, d, np.ones((2, 2), bool), None,\n"
        "            resize_intrinsics(frame.K, (frame.width, frame.height), (2, 2)), 'dummy@0', {}, 0.0)\n"
        "k = np.array([[517.3, 0, 318.6], [0, 516.5, 255.3], [0, 0, 1]])\n"
        "assert isinstance(A(), GeometryAdapter)\n"
        "A().predict(FrameRecord('s', 0, 0.0, 'rgb/0.png', 640, 480, k))\n"
        f"print(sorted(m for m in {FORBIDDEN_MODULES!r} if m in sys.modules))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "[]"
