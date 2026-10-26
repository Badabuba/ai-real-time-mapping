"""Depth Anything 3 Metric (DA3METRIC-LARGE) behind the GeometryAdapter interface.

Facts this adapter relies on (checked in depth_anything_3 git 3d835ec1, see
docs/EXPERIMENTS.md):

- Preprocessing ("upper_bound_resize"): cv2.resize of the longest side to
  process_res, then a second cv2.resize of each side to the nearest multiple
  of 14. TUM 640x480 at 384 -> 384x288 -> 378x294. Depth comes out on that grid.
- cv2.resize maps pixel centres (src = (dst + 0.5) / s - 0.5), so K_processed
  is built with rt_mapping.geometry.intrinsics.resize_intrinsics for each step
  (integer pixel centres). DA3's own K update (cx * s) differs by ~0.2 px.
- DA3METRIC-LARGE has no camera encoder/decoder: input intrinsics are ignored,
  the API returns no intrinsics and no confidence, and is_metric is not set.
  Metric depth = raw * focal / 300 with focal in processed pixels (DA3 README).
- DepthAnything3.forward autocasts to bfloat16 when the GPU supports it,
  otherwise float16; the weights stay float32.

torch / depth_anything_3 / huggingface_hub are imported only in
TorchDa3Backend.load, never at module import.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.geometry.adapter import GeometryAdapterError
from rt_mapping.geometry.intrinsics import resize_intrinsics

DEFAULT_REPO = "depth-anything/DA3METRIC-LARGE"
# Hugging Face commit of the locally cached snapshot used for all WP1 runs.
DEFAULT_REVISION = "4010e39f3634a45bc60553321fb49fb760bd594e"
DEFAULT_PROCESS_RES = 384
PATCH_SIZE = 14
METRIC_FOCAL_DIVISOR = 300.0
SUPPORTED_METHODS = ("upper_bound_resize",)
SUPPORTED_DTYPES = ("bfloat16", "float16")
# Weight files tried in this order, as huggingface_hub.PyTorchModelHubMixin does.
WEIGHT_FILENAMES = ("model.safetensors", "pytorch_model.bin")
CONFIDENCE_DESCRIPTION = "raw DA3 depth_conf (unbounded, higher = more reliable)"
K_CONVENTION = "pixel_centers_integer"

_DEVICE_RE = re.compile(r"^cuda(:\d+)?$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Da3MetricConfig:
    """Explicit model configuration. Invalid values raise GeometryAdapterError(unsupported_config).

    cache_dir is where the Hugging Face cache lives; it is never written to run
    records (it may be an absolute, user-specific path). Downloads are disabled.
    """

    repo: str = DEFAULT_REPO
    revision: str = DEFAULT_REVISION
    device: str = "cuda"
    dtype: str = "bfloat16"
    process_res: int = DEFAULT_PROCESS_RES
    process_res_method: str = "upper_bound_resize"
    seed: int = 0
    cache_dir: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        def bad(message: str) -> GeometryAdapterError:
            return GeometryAdapterError("unsupported_config", message)

        if not isinstance(self.repo, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", self.repo):
            raise bad(f"repo must look like 'org/name', got {self.repo!r}")
        if not isinstance(self.revision, str) or not _REVISION_RE.match(self.revision):
            raise bad(f"revision must be a full 40-char commit hash, got {self.revision!r}")
        if not isinstance(self.device, str) or not _DEVICE_RE.match(self.device):
            raise bad(f"device must be 'cuda' or 'cuda:N' (no CPU fallback), got {self.device!r}")
        if self.dtype not in SUPPORTED_DTYPES:
            raise bad(f"dtype must be one of {list(SUPPORTED_DTYPES)} (DA3 API autocast), got {self.dtype!r}")
        if isinstance(self.process_res, bool) or not isinstance(self.process_res, int) or self.process_res < PATCH_SIZE:
            raise bad(f"process_res must be an integer >= {PATCH_SIZE}, got {self.process_res!r}")
        if self.process_res_method not in SUPPORTED_METHODS:
            raise bad(f"process_res_method must be one of {list(SUPPORTED_METHODS)}, got {self.process_res_method!r}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise bad(f"seed must be an integer >= 0, got {self.seed!r}")

    @property
    def model_id(self) -> str:
        return f"{self.repo}@{self.revision}"

    def to_record(self) -> dict[str, Any]:
        """JSON-compatible config without host paths."""
        return {
            "repo": self.repo,
            "revision": self.revision,
            "device": self.device,
            "dtype": self.dtype,
            "process_res": self.process_res,
            "process_res_method": self.process_res_method,
            "seed": self.seed,
            "local_files_only": True,
        }


# ---------------------------------------------------------------------------
# Pure helpers (numpy only): sizes, K_processed, metric conversion.
# ---------------------------------------------------------------------------


def _nearest_multiple(value: int, patch: int) -> int:
    # Same tie rule as InputProcessor._make_divisible_by_resize (ties go up).
    down = (value // patch) * patch
    up = down + patch
    return up if abs(up - value) <= abs(value - down) else down


def da3_preprocess_plan(
    K: np.ndarray, width: int, height: int, process_res: int, method: str = "upper_bound_resize"
) -> tuple[np.ndarray, list[dict[str, Any]], tuple[int, int]]:
    """Mirror DA3 preprocessing for one image of size (width, height).

    Returns (K_processed, steps, (out_width, out_height)). Each resize DA3
    performs becomes one step and one resize_intrinsics call; unchanged sizes
    add no step (DA3 skips them too).
    """
    if method not in SUPPORTED_METHODS:
        raise GeometryAdapterError("unsupported_config", f"unsupported process_res_method {method!r}")
    if width <= 0 or height <= 0:
        raise GeometryAdapterError("unexpected_input", f"image size must be positive, got {width}x{height}")
    k = np.array(K, dtype=np.float64)
    steps: list[dict[str, Any]] = []

    # 1) longest side -> process_res (InputProcessor._resize_longest_side)
    w, h = width, height
    longest = max(w, h)
    if longest != process_res:
        scale = process_res / float(longest)
        new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        interp = "cv2.INTER_CUBIC" if scale > 1.0 else "cv2.INTER_AREA"
        k = resize_intrinsics(k, (w, h), (new_w, new_h))
        steps.append({"op": "resize", "from_wh": [w, h], "to_wh": [new_w, new_h], "interpolation": interp})
        w, h = new_w, new_h

    # 2) each side -> nearest multiple of PATCH_SIZE (InputProcessor._make_divisible_by_resize)
    new_w, new_h = max(1, _nearest_multiple(w, PATCH_SIZE)), max(1, _nearest_multiple(h, PATCH_SIZE))
    if (new_w, new_h) != (w, h):
        interp = "cv2.INTER_CUBIC" if (new_w > w or new_h > h) else "cv2.INTER_AREA"
        k = resize_intrinsics(k, (w, h), (new_w, new_h))
        steps.append({"op": "resize", "from_wh": [w, h], "to_wh": [new_w, new_h], "interpolation": interp})
        w, h = new_w, new_h

    return k, steps, (w, h)


def da3_processed_size(width: int, height: int, process_res: int, method: str = "upper_bound_resize") -> tuple[int, int]:
    """(width, height) of the depth map DA3 returns for an input of (width, height)."""
    eye = np.eye(3)
    return da3_preprocess_plan(eye, width, height, process_res, method)[2]


def raw_to_metric_depth(raw_depth: np.ndarray, K_processed: np.ndarray) -> np.ndarray:
    """DA3METRIC conversion: metres = raw * mean(fx, fy) / 300, focal in processed pixels."""
    focal_px = float((K_processed[0, 0] + K_processed[1, 1]) / 2.0)
    return (np.asarray(raw_depth, dtype=np.float32) * np.float32(focal_px / METRIC_FOCAL_DIVISOR)).astype(np.float32)


# ---------------------------------------------------------------------------
# Backend boundary (the only place that touches torch / DA3).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawDa3Output:
    """What one DA3 API call returned for one image."""

    depth: np.ndarray
    conf: np.ndarray | None
    is_metric: bool
    intrinsics: np.ndarray | None
    inference_ms: float


@dataclass(frozen=True)
class Da3BackendInfo:
    """Facts about the loaded model, reported by the backend."""

    autocast_dtype: str
    weights_dtype: str
    gpu_name: str | None
    checkpoint_file: str
    checkpoint_sha256: str
    load_seconds: float
    environment: dict[str, str]


class Da3Backend(Protocol):
    def load(self, config: Da3MetricConfig) -> Da3BackendInfo: ...

    def infer(self, image_rgb: np.ndarray, config: Da3MetricConfig) -> RawDa3Output: ...

    def peak_memory_gb(self) -> float | None: ...


def _sha256_file(path: Path, chunk_size: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _da3_package_record() -> str | None:
    """'<version>+git<commit>' for a git install of depth-anything-3, else the version."""
    from importlib import metadata

    try:
        dist = metadata.distribution("depth-anything-3")
    except metadata.PackageNotFoundError:
        return None
    text = dist.read_text("direct_url.json")
    commit = None
    if text:
        try:
            commit = json.loads(text).get("vcs_info", {}).get("commit_id")
        except ValueError:
            commit = None
    return f"{dist.version}+git{commit}" if commit else dist.version


def _scalar_flag(value: Any) -> bool:
    """DA3 sets is_metric via an Addict Dict, which yields {} when the field is absent."""
    if isinstance(value, dict):
        return bool(value.get("value", 0)) if value else False
    if hasattr(value, "detach"):
        return bool(int(value.detach().cpu().reshape(-1)[0].item()))
    if hasattr(value, "item"):
        return bool(int(value.item()))
    return bool(int(value))


class TorchDa3Backend:
    """Real DA3 backend on CUDA. Loads once; never downloads."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir
        self._model: Any = None
        self._torch: Any = None
        self._device: Any = None

    def load(self, config: Da3MetricConfig) -> Da3BackendInfo:
        try:
            import torch
        except ImportError as exc:
            raise GeometryAdapterError("model_load_failed", f"torch is not importable: {exc}") from exc
        if not torch.cuda.is_available():
            raise GeometryAdapterError("cuda_unavailable", "torch.cuda.is_available() is False")
        device = torch.device(config.device)
        index = device.index if device.index is not None else 0
        if index >= torch.cuda.device_count():
            raise GeometryAdapterError(
                "cuda_unavailable", f"{config.device} requested, {torch.cuda.device_count()} CUDA device(s) visible"
            )
        torch.cuda.set_device(index)
        torch.manual_seed(config.seed)
        np.random.seed(config.seed)

        try:
            from huggingface_hub import hf_hub_download
            from huggingface_hub.errors import EntryNotFoundError, LocalEntryNotFoundError
            from depth_anything_3.api import DepthAnything3
        except ImportError as exc:
            raise GeometryAdapterError("model_load_failed", f"model packages are not importable: {exc}") from exc

        weight_path = None
        for filename in WEIGHT_FILENAMES:
            try:
                weight_path = Path(
                    hf_hub_download(
                        repo_id=config.repo,
                        filename=filename,
                        revision=config.revision,
                        cache_dir=self._cache_dir,
                        local_files_only=True,
                    )
                )
                break
            except (EntryNotFoundError, LocalEntryNotFoundError, FileNotFoundError):
                continue
        if weight_path is None:
            raise GeometryAdapterError(
                "model_load_failed",
                f"no weights ({', '.join(WEIGHT_FILENAMES)}) for {config.model_id} in the local cache; downloads are disabled",
            )
        checkpoint_sha256 = _sha256_file(weight_path)

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        started = time.perf_counter()
        try:
            model = DepthAnything3.from_pretrained(
                config.repo, revision=config.revision, cache_dir=self._cache_dir, local_files_only=True
            )
            model = model.to(device=device).eval()
            torch.cuda.synchronize(device)
        except torch.cuda.OutOfMemoryError as exc:
            raise GeometryAdapterError("model_oom", f"loading {config.model_id}: {exc}") from exc
        except Exception as exc:  # anything else while loading is a load failure, reported with its cause
            raise GeometryAdapterError("model_load_failed", f"{type(exc).__name__}: {exc}") from exc
        load_seconds = time.perf_counter() - started

        # Mirrors DepthAnything3.forward: bf16 if supported, else fp16.
        autocast = "bfloat16" if torch.cuda.is_bf16_supported() else "float16"
        weights_dtype = str(next(model.parameters()).dtype).removeprefix("torch.")

        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "torch": torch.__version__,
        }
        if torch.version.cuda:
            environment["cuda_runtime"] = str(torch.version.cuda)
        for key, value in (
            ("depth_anything_3", _da3_package_record()),
            ("huggingface_hub", _package_version("huggingface_hub")),
            ("opencv", _package_version("opencv-python") or _package_version("opencv-python-headless")),
            ("pillow", _package_version("pillow")),
        ):
            if value:
                environment[key] = value

        self._model, self._torch, self._device = model, torch, device
        return Da3BackendInfo(
            autocast_dtype=autocast,
            weights_dtype=weights_dtype,
            gpu_name=torch.cuda.get_device_name(device),
            checkpoint_file=weight_path.name,
            checkpoint_sha256=checkpoint_sha256,
            load_seconds=load_seconds,
            environment=environment,
        )

    def infer(self, image_rgb: np.ndarray, config: Da3MetricConfig) -> RawDa3Output:
        if self._model is None:
            raise RuntimeError("TorchDa3Backend.infer called before load")
        torch = self._torch
        try:
            torch.cuda.synchronize(self._device)
            started = time.perf_counter()
            prediction = self._model.inference(
                [image_rgb], process_res=config.process_res, process_res_method=config.process_res_method
            )
            torch.cuda.synchronize(self._device)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        except torch.cuda.OutOfMemoryError as exc:
            raise GeometryAdapterError("model_oom", str(exc)) from exc
        depth = np.asarray(prediction.depth)
        conf = None if prediction.conf is None else np.asarray(prediction.conf)
        if depth.ndim != 3 or depth.shape[0] != 1:
            raise GeometryAdapterError("unexpected_model_output", f"expected depth of shape (1, H, W), got {depth.shape}")
        if conf is not None and (conf.ndim != 3 or conf.shape[0] != 1):
            raise GeometryAdapterError("unexpected_model_output", f"expected conf of shape (1, H, W), got {conf.shape}")
        intrinsics = getattr(prediction, "intrinsics", None)
        return RawDa3Output(
            depth=depth[0],
            conf=None if conf is None else conf[0],
            is_metric=_scalar_flag(prediction.is_metric),
            intrinsics=None if intrinsics is None else np.asarray(intrinsics),
            inference_ms=elapsed_ms,
        )

    def peak_memory_gb(self) -> float | None:
        if self._torch is None:
            return None
        return float(self._torch.cuda.max_memory_allocated(self._device) / 1024**3)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _read_rgb(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


class Da3MetricAdapter:
    """GeometryAdapter for DA3METRIC-LARGE. The model is loaded once, in __init__.

    image_root is the directory FrameRecord.image_path is relative to.
    """

    def __init__(self, config: Da3MetricConfig, image_root: str | Path, backend: Da3Backend | None = None) -> None:
        self.config = config
        self.image_root = Path(image_root)
        self._backend: Da3Backend = backend if backend is not None else TorchDa3Backend(config.cache_dir)
        self.info = self._backend.load(config)
        if self.info.autocast_dtype != config.dtype:
            raise GeometryAdapterError(
                "unsupported_config",
                f"requested dtype {config.dtype!r} but the DA3 API will autocast to {self.info.autocast_dtype!r} on this GPU",
            )

    @property
    def model_id(self) -> str:
        return self.config.model_id

    @property
    def load_seconds(self) -> float:
        return self.info.load_seconds

    def describe(self) -> dict[str, Any]:
        """Run-record facts: model block, environment, gpu name and model config."""
        return {
            "model": {
                "repo": self.config.repo,
                "revision": self.config.revision,
                "checkpoint": f"{self.info.checkpoint_file}@sha256:{self.info.checkpoint_sha256}",
                "dtype": self.config.dtype,
            },
            "environment": dict(self.info.environment),
            "gpu": self.info.gpu_name,
            "config": {
                **self.config.to_record(),
                "autocast_dtype": self.info.autocast_dtype,
                "weights_dtype": self.info.weights_dtype,
                "checkpoint_file": self.info.checkpoint_file,
                "checkpoint_sha256": self.info.checkpoint_sha256,
                "k_convention": K_CONVENTION,
                "metric_conversion": f"raw * mean(fx, fy) / {METRIC_FOCAL_DIVISOR:g} (processed K)",
                "timing_scope": "one DA3 inference() call (preprocess + forward + postprocess), CUDA-synchronized; image decode excluded",
            },
        }

    def peak_memory_gb(self) -> float | None:
        return self._backend.peak_memory_gb()

    def predict(self, frame: FrameRecord) -> GeometryPrediction:
        path = self.image_root / frame.image_path
        if not path.is_file():
            raise GeometryAdapterError("missing_input", f"frame {frame.frame_id}: image {frame.image_path} not found")
        rgb = _read_rgb(path)
        height, width = rgb.shape[:2]
        if (width, height) != (frame.width, frame.height):
            raise GeometryAdapterError(
                "unexpected_input",
                f"frame {frame.frame_id}: image is {width}x{height}, FrameRecord says {frame.width}x{frame.height}",
            )
        k_processed, steps, (out_w, out_h) = da3_preprocess_plan(
            frame.K, width, height, self.config.process_res, self.config.process_res_method
        )

        raw = self._backend.infer(rgb, self.config)
        if raw.intrinsics is not None:
            raise GeometryAdapterError(
                "unexpected_model_output",
                "DA3 returned intrinsics; their convention is not verified for this adapter, refusing to guess",
            )
        depth = np.asarray(raw.depth)
        if depth.ndim != 2 or depth.shape != (out_h, out_w):
            raise GeometryAdapterError(
                "unexpected_model_output",
                f"frame {frame.frame_id}: depth shape {depth.shape}, expected {(out_h, out_w)} from DA3 preprocessing",
            )
        if not np.issubdtype(depth.dtype, np.floating):
            raise GeometryAdapterError("unexpected_model_output", f"depth dtype {depth.dtype} is not floating point")

        if raw.is_metric:
            depth_m = depth.astype(np.float32)
            conversion = "none (API reported metric output)"
        else:
            depth_m = raw_to_metric_depth(depth, k_processed)
            conversion = f"raw * mean(fx, fy) / {METRIC_FOCAL_DIVISOR:g}"
        n_bad = int(np.count_nonzero(~np.isfinite(depth_m) | (depth_m <= 0)))
        if n_bad:
            raise GeometryAdapterError(
                "non_finite_output", f"frame {frame.frame_id}: {n_bad} of {depth_m.size} depth values are non-finite or <= 0"
            )

        confidence = None
        if raw.conf is not None:
            conf = np.asarray(raw.conf)
            if conf.shape != depth_m.shape or not np.issubdtype(conf.dtype, np.floating):
                raise GeometryAdapterError(
                    "unexpected_model_output", f"confidence shape/dtype {conf.shape}/{conf.dtype} does not match depth"
                )
            confidence = conf.astype(np.float32)
            if not np.all(np.isfinite(confidence)):
                raise GeometryAdapterError("non_finite_output", f"frame {frame.frame_id}: confidence is not finite")

        preprocess = {
            "library": "depth_anything_3",
            "process_res": self.config.process_res,
            "process_res_method": self.config.process_res_method,
            "patch_size": PATCH_SIZE,
            "input_wh": [width, height],
            "output_wh": [out_w, out_h],
            "steps": steps,
            "normalization": "imagenet mean/std",
            "intrinsics_convention": K_CONVENTION,
            "metric_conversion": conversion,
            "autocast_dtype": self.info.autocast_dtype,
            "weights_dtype": self.info.weights_dtype,
            "confidence": CONFIDENCE_DESCRIPTION if confidence is not None else "not provided by model",
        }
        return GeometryPrediction(
            frame_id=frame.frame_id,
            timestamp_s=frame.timestamp_s,
            depth_m=depth_m,
            valid_mask=np.ones(depth_m.shape, dtype=bool),
            confidence=confidence,
            K_processed=k_processed,
            model_id=self.model_id,
            preprocess=preprocess,
            inference_ms=raw.inference_ms,
        )
