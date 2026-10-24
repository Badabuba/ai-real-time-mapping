"""GeometryPrediction contract: one model's dense metric depth for one frame.

Fields follow docs/ARCHITECTURE.md §2. The contract never holds ground truth.
Serialization is a byte-deterministic NPZ (see save_prediction).
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from rt_mapping.contracts._validation import check_json_value as _check_json_value
from rt_mapping.contracts._validation import is_absolute_path as _is_absolute_path

SCHEMA = "rt_mapping.geometry_prediction/v1"

_ARRAY_FIELDS = ("depth_m", "valid_mask", "K_processed")
_META_KEYS = {"schema", "frame_id", "timestamp_s", "model_id", "preprocess", "inference_ms", "has_confidence"}
# Fixed zip metadata so the same prediction always gives the same bytes.
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_ZIP_CREATE_SYSTEM = 3  # unix; the default depends on the host OS
_ZIP_EXTERNAL_ATTR = 0o644 << 16
_ZIP_COMPRESSLEVEL = 6


def _readonly(array: np.ndarray) -> np.ndarray:
    copy = np.array(array, copy=True)
    copy.setflags(write=False)
    return copy


@dataclass(frozen=True)
class GeometryPrediction:
    """Dense metric depth predicted by one model for one frame.

    depth_m      H×W float32, metres; NaN exactly where valid_mask is False.
    valid_mask   H×W bool, geometrically valid pixels; valid depth is finite and > 0.
    confidence   H×W float32 (higher = more reliable; range documented by the
                 adapter) or None when the model gives no confidence. Never filled in.
    K_processed  3×3 float64 intrinsics of the processed (resized/cropped) image.
    model_id     repo + checkpoint + revision; no absolute paths.
    preprocess   JSON-compatible dict describing resize/crop/normalization/dtype.
                 A copy is stored; no absolute paths or non-finite numbers.
    inference_ms model call only, measured after warm-up (not enforced here).

    Invalid input raises ValueError.
    """

    frame_id: int
    timestamp_s: float
    depth_m: np.ndarray
    valid_mask: np.ndarray
    confidence: np.ndarray | None
    K_processed: np.ndarray
    model_id: str
    preprocess: dict[str, Any]
    inference_ms: float

    def __post_init__(self) -> None:
        if isinstance(self.frame_id, bool) or not isinstance(self.frame_id, (int, np.integer)):
            raise ValueError(f"frame_id must be an integer, got {self.frame_id!r}")
        if self.frame_id < 0:
            raise ValueError(f"frame_id must be >= 0, got {self.frame_id}")
        if not np.isfinite(self.timestamp_s):
            raise ValueError(f"timestamp_s must be finite, got {self.timestamp_s}")

        depth = self.depth_m
        if not isinstance(depth, np.ndarray) or depth.dtype != np.float32:
            raise ValueError(f"depth_m must be a float32 ndarray, got {getattr(depth, 'dtype', type(depth))}")
        if depth.ndim != 2 or depth.shape[0] == 0 or depth.shape[1] == 0:
            raise ValueError(f"depth_m must be a non-empty H×W array, got shape {depth.shape}")

        mask = self.valid_mask
        if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_:
            raise ValueError(f"valid_mask must be a bool ndarray, got {getattr(mask, 'dtype', type(mask))}")
        if mask.shape != depth.shape:
            raise ValueError(f"valid_mask shape {mask.shape} differs from depth_m shape {depth.shape}")
        if not np.array_equal(np.isnan(depth), ~mask):
            raise ValueError("depth_m must be NaN exactly where valid_mask is False")
        valid_depth = depth[mask]
        if not np.all(np.isfinite(valid_depth)) or np.any(valid_depth <= 0):
            raise ValueError("valid depth_m values must be finite and > 0")

        conf = self.confidence
        if conf is not None:
            if not isinstance(conf, np.ndarray) or conf.dtype != np.float32:
                raise ValueError(f"confidence must be None or a float32 ndarray, got {getattr(conf, 'dtype', type(conf))}")
            if conf.shape != depth.shape:
                raise ValueError(f"confidence shape {conf.shape} differs from depth_m shape {depth.shape}")
            if not np.all(np.isfinite(conf[mask])):
                raise ValueError("confidence must be finite on valid pixels")

        k = np.array(self.K_processed, dtype=np.float64)
        if k.shape != (3, 3) or not np.all(np.isfinite(k)):
            raise ValueError(f"K_processed must be a finite 3x3 matrix, got shape {k.shape}")
        if k[0, 0] <= 0 or k[1, 1] <= 0:
            raise ValueError(f"K_processed focal lengths must be > 0, got fx={k[0, 0]}, fy={k[1, 1]}")
        if k[1, 0] != 0 or not np.array_equal(k[2], [0.0, 0.0, 1.0]):
            raise ValueError(f"K_processed must be upper-triangular with last row [0, 0, 1], got {k.tolist()}")

        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be a non-empty string")
        if _is_absolute_path(self.model_id):
            raise ValueError(f"model_id must not be an absolute path, got {self.model_id!r}")

        if not isinstance(self.preprocess, dict):
            raise ValueError(f"preprocess must be a dict, got {type(self.preprocess).__name__}")
        _check_json_value(self.preprocess, "preprocess")
        # JSON round trip = deep copy; later changes to the caller's dict do not leak in.
        preprocess = json.loads(json.dumps(self.preprocess, allow_nan=False, sort_keys=True))

        if isinstance(self.inference_ms, bool) or not isinstance(self.inference_ms, (int, float, np.floating)):
            raise ValueError(f"inference_ms must be a number, got {self.inference_ms!r}")
        if not math.isfinite(self.inference_ms) or self.inference_ms < 0:
            raise ValueError(f"inference_ms must be finite and >= 0, got {self.inference_ms}")

        # frozen dataclass: bypass __setattr__ to store normalised copies.
        object.__setattr__(self, "frame_id", int(self.frame_id))
        object.__setattr__(self, "timestamp_s", float(self.timestamp_s))
        object.__setattr__(self, "depth_m", _readonly(depth))
        object.__setattr__(self, "valid_mask", _readonly(mask))
        object.__setattr__(self, "confidence", None if conf is None else _readonly(conf))
        k.setflags(write=False)
        object.__setattr__(self, "K_processed", k)
        object.__setattr__(self, "preprocess", preprocess)
        object.__setattr__(self, "inference_ms", float(self.inference_ms))


def _entry_names(has_confidence: bool) -> list[str]:
    names = [f"{name}.npy" for name in _ARRAY_FIELDS]
    if has_confidence:
        names.append("confidence.npy")
    return names + ["meta.json"]


def _write_entry(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = _ZIP_CREATE_SYSTEM
    info.external_attr = _ZIP_EXTERNAL_ATTR
    zf.writestr(info, data, compresslevel=_ZIP_COMPRESSLEVEL)


def _array_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.lib.format.write_array(buffer, np.ascontiguousarray(array), allow_pickle=False)
    return buffer.getvalue()


def save_prediction(prediction: GeometryPrediction, path: str | Path) -> None:
    """Write one prediction as a deterministic NPZ (same input -> same bytes).

    Entries: depth_m.npy, valid_mask.npy, K_processed.npy, [confidence.npy], meta.json.
    No paths, host data or ground truth are written.
    """
    has_confidence = prediction.confidence is not None
    meta = {
        "schema": SCHEMA,
        "frame_id": prediction.frame_id,
        "timestamp_s": prediction.timestamp_s,
        "model_id": prediction.model_id,
        "preprocess": prediction.preprocess,
        "inference_ms": prediction.inference_ms,
        "has_confidence": has_confidence,
    }
    meta_bytes = json.dumps(meta, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with zipfile.ZipFile(path, "w") as zf:
        for name in _ARRAY_FIELDS:
            _write_entry(zf, f"{name}.npy", _array_bytes(getattr(prediction, name)))
        if has_confidence:
            _write_entry(zf, "confidence.npy", _array_bytes(prediction.confidence))
        _write_entry(zf, "meta.json", meta_bytes)


def _reject_constant(name: str) -> None:
    raise ValueError(f"meta.json must not contain {name}")


def load_prediction(path: str | Path) -> GeometryPrediction:
    """Read a prediction written by save_prediction; unknown entries are rejected."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "meta.json" not in names:
            raise ValueError(f"{path}: missing meta.json")
        meta = json.loads(zf.read("meta.json").decode("utf-8"), parse_constant=_reject_constant)
        if not isinstance(meta, dict) or set(meta) != _META_KEYS:
            raise ValueError(f"{path}: meta.json keys must be {sorted(_META_KEYS)}")
        if meta["schema"] != SCHEMA:
            raise ValueError(f"{path}: unsupported schema {meta['schema']!r}")
        has_confidence = meta["has_confidence"]
        if not isinstance(has_confidence, bool):
            raise ValueError(f"{path}: has_confidence must be a bool")
        expected = _entry_names(has_confidence)
        if sorted(names) != sorted(expected):
            raise ValueError(f"{path}: entries {sorted(names)} differ from expected {sorted(expected)}")
        arrays = {
            name[: -len(".npy")]: np.lib.format.read_array(io.BytesIO(zf.read(name)), allow_pickle=False)
            for name in expected
            if name.endswith(".npy")
        }
    return GeometryPrediction(
        frame_id=meta["frame_id"],
        timestamp_s=meta["timestamp_s"],
        depth_m=arrays["depth_m"],
        valid_mask=arrays["valid_mask"],
        confidence=arrays.get("confidence"),
        K_processed=arrays["K_processed"],
        model_id=meta["model_id"],
        preprocess=meta["preprocess"],
        inference_ms=meta["inference_ms"],
    )
