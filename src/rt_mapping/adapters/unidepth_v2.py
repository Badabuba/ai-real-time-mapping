"""Official UniDepth V2 behind GeometryAdapter, with explicit local-only weights.

Source: lpiccinelli-eth/UniDepth@8d8cfe4c7ee15297099983607febf0d4f32eb3d6.
infer() returns camera-z depth in metres on the original input image grid.
The returned predicted K is a camera-head diagnostic even when input K supplies
the rays. It must not replace the calibrated camera used for those rays.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import time
import io
import subprocess
import tarfile
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.geometry.adapter import GeometryAdapterError

REPO = "lpiccinelli/unidepth-v2-vitl14"
REVISION = "52b349b514bd8b47642f67ac78cb7b5dc5c51dd9"
CODE_REVISION = "8d8cfe4c7ee15297099983607febf0d4f32eb3d6"
WEIGHT_SHA256 = "ba73d3de735302ccc64a50f1e557122050c4b1893e6060b28dba05d6af3e67c6"
CONFIG_SHA256 = "09eb0ea8de53a6c9a1d428ac98c79847fe2602ea417701261f3f628099a30816"


@dataclass(frozen=True)
class UniDepthConfig:
    checkpoint_dir: Path = field(default=Path("checkpoints/unidepth-v2-vitl14-52b349b"), compare=False)
    source_dir: Path = field(default=Path("checkpoints/upstream/UniDepth"), compare=False)
    device: str = "cuda"
    resolution_level: int = 0
    seed: int = 0

    def __post_init__(self):
        if not re.fullmatch(r"cuda(:\d+)?", self.device):
            raise GeometryAdapterError("unsupported_config", "UniDepth requires cuda or cuda:N")
        for name, value, upper in (("resolution_level", self.resolution_level, 9), ("seed", self.seed, 2**32 - 1)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper:
                raise GeometryAdapterError("unsupported_config", f"invalid {name}")

    def to_record(self):
        return {"repo": REPO, "revision": REVISION, "code_revision": CODE_REVISION,
                "device": self.device, "dtype": "float16", "weights_dtype": "float32",
                "resolution_level": self.resolution_level, "seed": self.seed,
                "local_files_only": True, "camera_mode": "calibrated_pinhole"}


def camera_for_native_resize(K, width, height, resolution_level, constraints):
    """Compensate the official infer() camera scaling, without modifying upstream.

    UniDepth grids have half-integer centres and camera.resize(r) uses a scalar
    before dimensions are rounded up to /14. Supply K so its internal camera
    equals the actual per-axis image resize. infer() restores the raw grid, so
    GeometryPrediction.K_processed remains the original integer-centre K.
    """
    ratio = width / height
    minimum, maximum = constraints["ratio_bounds"]
    target = min(maximum, max(minimum, ratio))
    padded_w, padded_h = width, height
    if ratio > target:
        padded_h = int(width / target)
    else:
        padded_w = int(height * target)
    left, top = (padded_w - width) // 2, (padded_h - height) // 2
    lo, hi = constraints["pixels_min"], constraints["pixels_max"]
    step = (hi - lo) / 10
    target_area = min(lo + (resolution_level + 1) * step,
                      max(lo + resolution_level * step, padded_w * padded_h))
    nominal = math.sqrt(target_area / (padded_w * padded_h))
    new_w = math.ceil(int(padded_w * nominal) / 14) * 14
    new_h = math.ceil(int(padded_h * nominal) / 14) * 14
    sx, sy = new_w / padded_w, new_h / padded_h
    native = np.array(K, dtype=np.float64, copy=True)
    native[0, 0] *= sx / nominal
    native[1, 1] *= sy / nominal
    native[0, 2] = (K[0, 2] + 0.5 + left) * sx / nominal - left
    native[1, 2] = (K[1, 2] + 0.5 + top) * sy / nominal - top
    return native, {"internal_wh": [new_w, new_h], "padded_wh": [padded_w, padded_h],
                    "padding_left_top": [left, top], "nominal_resize_factor": nominal,
                    "actual_scale_xy": [sx, sy]}


@dataclass(frozen=True)
class UniDepthOutput:
    depth_m: np.ndarray
    error_estimate: np.ndarray | None
    predicted_intrinsics: np.ndarray
    inference_ms: float
    preprocess: dict[str, Any]


class UniDepthBackend(Protocol):
    def load(self, config: UniDepthConfig) -> dict[str, Any]: ...
    def infer(self, rgb: np.ndarray, K: np.ndarray, config: UniDepthConfig) -> UniDepthOutput: ...
    def peak_memory_gb(self) -> float | None: ...


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installed_source(source_dir: Path, package_dir: Path) -> str:
    """Compare installed Python bytes with the pinned Git tree, without imports.

    A version string alone cannot establish which locally installed source is
    running. The checkout is read through Git objects; neither checkout changes
    nor an unverified distribution can silently inherit CODE_REVISION.
    """
    try:
        archive = subprocess.run(
            ["git", "archive", CODE_REVISION, "unidepth"], cwd=source_dir,
            capture_output=True, check=True, timeout=30,
        ).stdout
        expected = {}
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            for member in tree:
                if member.isfile() and member.name.endswith(".py"):
                    expected[member.name.removeprefix("unidepth/")] = tree.extractfile(member).read()
        actual = {p.relative_to(package_dir).as_posix(): p.read_bytes()
                  for p in package_dir.rglob("*.py")}
        if not expected or expected != actual:
            raise ValueError("installed UniDepth Python files differ from the pinned source tree")
        digest = hashlib.sha256()
        for name, content in sorted(expected.items()):
            digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
        return digest.hexdigest()
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        raise GeometryAdapterError("model_load_failed", f"cannot verify UniDepth source: {exc}") from exc


class TorchUniDepthBackend:
    """No Hub calls: instantiate from verified config and strict safetensors load."""

    def load(self, config):
        directory = Path(config.checkpoint_dir)
        for name, expected in (("model.safetensors", WEIGHT_SHA256), ("config.json", CONFIG_SHA256)):
            if not (directory / name).is_file():
                raise GeometryAdapterError("model_load_failed", f"missing local {name}; download explicitly first")
            if sha256(directory / name) != expected:
                raise GeometryAdapterError("model_load_failed", f"{name} SHA-256 mismatch")
        model_config = json.loads((directory / "config.json").read_text())
        if model_config["model"]["pixel_encoder"]["pretrained"] is not None:
            raise GeometryAdapterError("unsupported_config", "backbone download must be disabled")
        spec = importlib.util.find_spec("unidepth")
        if spec is None or not spec.submodule_search_locations:
            raise GeometryAdapterError("model_load_failed", "UniDepth is not installed")
        source_hash = verify_installed_source(config.source_dir, Path(next(iter(spec.submodule_search_locations))))
        try:
            import torch
            from safetensors.torch import load_model
            from unidepth.models import UniDepthV2
            from importlib.metadata import version
        except ImportError as exc:
            raise GeometryAdapterError("model_load_failed", f"install the optional UniDepth environment: {exc}") from exc
        if not torch.cuda.is_available():
            raise GeometryAdapterError("cuda_unavailable", "CUDA is unavailable")
        device = torch.device(config.device)
        if (device.index or 0) >= torch.cuda.device_count():
            raise GeometryAdapterError("cuda_unavailable", "requested CUDA device is unavailable")
        torch.cuda.set_device(device.index if device.index is not None else 0)
        torch.manual_seed(config.seed)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        start = time.perf_counter()
        try:
            model = UniDepthV2(config=model_config)
            load_model(model, str(directory / "model.safetensors"), strict=True, device="cpu")
            model.resolution_level = config.resolution_level
            model = model.to(device).eval()
            torch.cuda.synchronize(device)
        except torch.cuda.OutOfMemoryError as exc:
            raise GeometryAdapterError("model_oom", "UniDepth load exhausted VRAM") from exc
        except Exception as exc:
            raise GeometryAdapterError("model_load_failed", f"{type(exc).__name__}: {exc}") from exc
        self.model, self.torch, self.device = model, torch, device
        return {"load_seconds": time.perf_counter() - start,
                "gpu": torch.cuda.get_device_name(device),
                "environment": {"python": platform.python_version(), "numpy": np.__version__,
                                "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
                                "unidepth": version("unidepth"), "unidepth_source_revision": CODE_REVISION,
                                "unidepth_source_sha256": source_hash}}

    def infer(self, rgb, K, config):
        torch = self.torch
        height, width = rgb.shape[:2]
        native_k, plan = camera_for_native_resize(K, width, height, config.resolution_level,
                                                  self.model.shape_constraints)
        try:
            image = torch.from_numpy(rgb.copy()).permute(2, 0, 1)
            camera = torch.from_numpy(native_k.astype(np.float32)).unsqueeze(0)
            torch.cuda.synchronize(self.device)
            started = time.perf_counter()
            with torch.inference_mode():
                result = self.model.infer(image, camera=camera)
            torch.cuda.synchronize(self.device)
            def array(name):
                return result[name].detach().float().cpu().numpy()
            error = array("confidence")[0, 0] if result.get("confidence") is not None else None
            depth, predicted_k = array("depth")[0, 0], array("intrinsics")[0]
            # DA3's API already returns CPU arrays inside its timed call. Include
            # the required UniDepth exports too, so runtime does not hide transfers.
            elapsed = (time.perf_counter() - started) * 1000
            return UniDepthOutput(depth, error, predicted_k, elapsed, plan)
        except torch.cuda.OutOfMemoryError as exc:
            raise GeometryAdapterError("model_oom", "UniDepth inference exhausted VRAM") from exc
        except (KeyError, IndexError) as exc:
            raise GeometryAdapterError("unexpected_model_output", f"malformed UniDepth output: {exc}") from exc

    def peak_memory_gb(self):
        return float(self.torch.cuda.max_memory_allocated(self.device) / 1024**3)


class UniDepthV2Adapter:
    def __init__(self, config: UniDepthConfig, image_root: Path, backend: UniDepthBackend | None = None):
        self.config, self.image_root = config, Path(image_root)
        self.backend = backend if backend is not None else TorchUniDepthBackend()
        self.info = self.backend.load(config)

    @property
    def load_seconds(self):
        return self.info["load_seconds"]

    def peak_memory_gb(self):
        return self.backend.peak_memory_gb()

    def describe(self):
        return {"model": {"repo": REPO, "revision": REVISION,
                          "checkpoint": "model.safetensors@sha256:" + WEIGHT_SHA256, "dtype": "float16"},
                "environment": self.info["environment"], "gpu": self.info["gpu"],
                "config": {**self.config.to_record(), "license": "CC-BY-NC-4.0",
                           "timing_scope": "upstream infer plus required CPU depth/confidence/K export; CUDA-synchronized; image decode and camera plan excluded",
                           "confidence": "negative official scale-invariant log-error estimate; relative ranking, not probability"}}

    def predict(self, frame: FrameRecord):
        from PIL import Image

        path = self.image_root / frame.image_path
        if not path.is_file():
            raise GeometryAdapterError("missing_input", f"frame {frame.frame_id}: RGB file missing")
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"))
        if rgb.shape[:2] != (frame.height, frame.width):
            raise GeometryAdapterError("unexpected_input", "image size differs from FrameRecord")
        out = self.backend.infer(rgb, frame.K, self.config)
        depth = np.asarray(out.depth_m)
        if depth.shape != (frame.height, frame.width) or not np.issubdtype(depth.dtype, np.floating):
            raise GeometryAdapterError("unexpected_model_output", "UniDepth depth must be floating HxW on the input grid")
        depth = depth.astype(np.float32)
        if not np.all(np.isfinite(depth) & (depth > 0)):
            raise GeometryAdapterError("non_finite_output", "UniDepth depth contains non-finite or non-positive values")
        predicted_k = np.asarray(out.predicted_intrinsics)
        if (predicted_k.shape != (3, 3) or not np.all(np.isfinite(predicted_k))
                or predicted_k[0, 0] <= 0 or predicted_k[1, 1] <= 0
                or not np.array_equal(predicted_k[2], [0., 0., 1.])):
            raise GeometryAdapterError("unexpected_model_output", "predicted camera diagnostic is invalid")
        confidence = None
        if out.error_estimate is not None:
            error = np.asarray(out.error_estimate)
            if error.shape != depth.shape or not np.issubdtype(error.dtype, np.floating):
                raise GeometryAdapterError("unexpected_model_output", "error estimate shape/dtype differs from depth")
            if not np.all(np.isfinite(error) & (error >= 0)):
                raise GeometryAdapterError("non_finite_output", "error estimate must be finite and non-negative")
            # Only reverse the official error's direction to meet higher=better.
            # No guessed probability, normalization, or confidence proxy is added.
            confidence = -error.astype(np.float32)
        return GeometryPrediction(
            frame.frame_id, frame.timestamp_s, depth, np.ones(depth.shape, dtype=bool), confidence,
            frame.K, f"{REPO}@{REVISION}",
            # Raw RGB goes in without rectification and infer() returns depth on
            # that same input grid, so no resize/crop steps apply and K_processed
            # is the input integer-centre K (same grid semantics as DA3).
            {**out.preprocess, "input_wh": [frame.width, frame.height], "output_wh": [frame.width, frame.height],
             "pixel_grid": "raw_distorted", "intrinsics_convention": "pixel_centers_integer", "steps": [],
             "normalization": "upstream infer: RGB uint8 / 255, ImageNet mean/std",
             "metric_conversion": "none; upstream points[:, z] already in metres",
             "camera_mode": "calibrated pinhole; half-centre and actual-resize compensation",
             "K_processed_source": "input calibration; infer restores input grid",
             "predicted_K_diagnostic_only": predicted_k.tolist(),
             "confidence": "none" if confidence is None else "negative official log-error; higher=more reliable; range (-inf,0]; relative within frame",
             "dtype": "float16 autocast; float32 weights", "code_revision": CODE_REVISION},
            out.inference_ms,
        )
