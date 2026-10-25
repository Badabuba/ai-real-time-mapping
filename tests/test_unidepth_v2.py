from pathlib import Path
import subprocess
import sys
import io
import tarfile
from types import SimpleNamespace
import json

import numpy as np
import pytest

from rt_mapping.adapters.unidepth_v2 import (
    UniDepthConfig, UniDepthOutput, UniDepthV2Adapter, camera_for_native_resize,
    verify_installed_source,
)
from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.geometry.adapter import GeometryAdapter, GeometryAdapterError

K = np.array([[500., 0, 319.5], [0, 510., 239.5], [0, 0, 1]])
CONSTRAINTS = {"ratio_bounds": [0.5, 2.5], "pixels_min": 200000, "pixels_max": 600000}


class Fake:
    def __init__(self, error=True, bad=None):
        self.loads = self.calls = 0
        self.error, self.bad = error, bad

    def load(self, config):
        self.loads += 1
        return {"load_seconds": .1, "gpu": "fake", "environment": {"python": "fake"}}

    def infer(self, rgb, k, config):
        self.calls += 1
        shape = rgb.shape[:2]
        depth = np.full(shape, 2., np.float32)
        if self.bad == "nan":
            depth[0, 0] = np.nan
        if self.bad == "shape":
            depth = depth[:1]
        error = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) if self.error else None
        return UniDepthOutput(depth, error, K, 10., {"internal_wh": [574, 434]})

    def peak_memory_gb(self):
        return .5


@pytest.fixture
def frame(tmp_path):
    from PIL import Image
    Image.fromarray(np.zeros((6, 8, 3), np.uint8)).save(tmp_path / "rgb.png")
    return FrameRecord("fixture", 0, 1., "rgb.png", 8, 6, K)


def test_adapter_uses_metric_z_original_grid_and_single_load(tmp_path, frame):
    backend = Fake()
    adapter = UniDepthV2Adapter(UniDepthConfig(), tmp_path, backend)
    assert isinstance(adapter, GeometryAdapter)
    one, two = adapter.predict(frame), adapter.predict(frame)
    assert backend.loads == 1 and backend.calls == 2
    np.testing.assert_array_equal(one.depth_m, 2.)
    np.testing.assert_array_equal(one.K_processed, K)
    assert one.depth_m.shape == (6, 8) and two.frame_id == frame.frame_id
    assert one.confidence[0, 0] > one.confidence[-1, -1]
    np.testing.assert_array_equal(one.confidence, -np.arange(48, dtype=np.float32).reshape(6, 8))
    assert one.preprocess["predicted_K_diagnostic_only"] == K.tolist()
    assert "checkpoint_dir" not in adapter.describe()["config"]
    assert "source_dir" not in adapter.describe()["config"]


def test_absent_confidence_is_none(tmp_path, frame):
    adapter = UniDepthV2Adapter(UniDepthConfig(), tmp_path, Fake(error=False))
    assert adapter.predict(frame).confidence is None


@pytest.mark.parametrize("bad,reason", [("nan", "non_finite_output"), ("shape", "unexpected_model_output")])
def test_bad_predictions_fail_explicitly(tmp_path, frame, bad, reason):
    adapter = UniDepthV2Adapter(UniDepthConfig(), tmp_path, Fake(bad=bad))
    with pytest.raises(GeometryAdapterError) as exc:
        adapter.predict(frame)
    assert exc.value.reason == reason


@pytest.mark.parametrize("size", [(640, 480), (480, 640), (1600, 300), (300, 1600)])
def test_native_camera_after_upstream_transform_matches_actual_grid(size):
    width, height = size
    native, plan = camera_for_native_resize(K, width, height, 0, CONSTRAINTS)
    left, top = plan["padding_left_top"]
    scalar = plan["nominal_resize_factor"]
    sx, sy = plan["actual_scale_xy"]
    # Mirror upstream camera.crop(-pad) then camera.resize(scalar).
    native[0, 2] += left
    native[1, 2] += top
    native[:2] *= scalar
    expected = K.copy()
    expected[0, 2] += .5 + left
    expected[1, 2] += .5 + top
    expected[0] *= sx
    expected[1] *= sy
    np.testing.assert_allclose(native, expected, atol=1e-10, rtol=0)
    assert all(n % 14 == 0 for n in plan["internal_wh"])


@pytest.mark.parametrize("kwargs", [{"device": "cpu"}, {"device": "cuda:x"}, {"resolution_level": 10},
                                  {"resolution_level": True}, {"seed": -1}])
def test_invalid_config(kwargs):
    with pytest.raises(GeometryAdapterError):
        UniDepthConfig(**kwargs)


def test_import_does_not_load_model_frameworks():
    root = Path(__file__).resolve().parents[1]
    code = f"import sys; sys.path.insert(0,{str(root / 'src')!r}); import rt_mapping.adapters.unidepth_v2; assert not any(x in sys.modules for x in ['torch','unidepth','PIL','huggingface_hub'])"
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_installed_source_is_checked_against_pinned_git_tree(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    content = b"# official test fixture\n"
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("unidepth/__init__.py")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=buffer.getvalue()))
    (tmp_path / "__init__.py").write_bytes(content)
    assert len(verify_installed_source(tmp_path, tmp_path)) == 64
    (tmp_path / "__init__.py").write_bytes(b"# modified\n")
    with pytest.raises(GeometryAdapterError, match="differ from the pinned"):
        verify_installed_source(tmp_path, tmp_path)


def test_namespace_package_reaches_source_verification(tmp_path, monkeypatch):
    import rt_mapping.adapters.unidepth_v2 as module
    (tmp_path / "config.json").write_text(json.dumps({"model": {"pixel_encoder": {"pretrained": None}}}))
    (tmp_path / "model.safetensors").write_bytes(b"fake weights")
    monkeypatch.setattr(module, "sha256", lambda p: module.CONFIG_SHA256 if p.name == "config.json" else module.WEIGHT_SHA256)
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: SimpleNamespace(submodule_search_locations=[str(tmp_path)]))
    seen = []
    def checked(source, package):
        seen.append(package)
        raise GeometryAdapterError("model_load_failed", "source checked before framework imports")
    monkeypatch.setattr(module, "verify_installed_source", checked)
    with pytest.raises(GeometryAdapterError, match="source checked"):
        module.TorchUniDepthBackend().load(UniDepthConfig(checkpoint_dir=tmp_path))
    assert seen == [tmp_path]


def test_prediction_declares_raw_grid_accepted_by_unchanged_alignment(tmp_path, frame):
    # N-04 D-3 gate failed with "prediction must declare its pixel grid".
    from rt_mapping.alignment.correspondences import prediction_grid
    from rt_mapping.alignment import AlignmentError

    one = UniDepthV2Adapter(UniDepthConfig(), tmp_path, Fake()).predict(frame)
    assert one.preprocess["pixel_grid"] == "raw_distorted"
    assert one.preprocess["intrinsics_convention"] == "pixel_centers_integer"
    assert one.preprocess["steps"] == []
    assert one.preprocess["input_wh"] == one.preprocess["output_wh"] == [8, 6]
    transform, grid = prediction_grid(one, K, (8, 6))
    assert grid == "raw_distorted"
    np.testing.assert_array_equal(transform, np.eye(3))
    # Validation is not weakened: a wrong K or a different keyframe size still fails.
    with pytest.raises(AlignmentError, match="K_processed"):
        prediction_grid(one, K * np.array([[1.01], [1.], [1.]]), (8, 6))
    with pytest.raises(AlignmentError, match="input size"):
        prediction_grid(one, K, (640, 480))
