"""Model-independent geometry interface and camera helpers."""

from rt_mapping.geometry.adapter import ADAPTER_FAILURE_REASONS, GeometryAdapter, GeometryAdapterError
from rt_mapping.geometry.intrinsics import crop_intrinsics, resize_intrinsics

__all__ = [
    "ADAPTER_FAILURE_REASONS",
    "GeometryAdapter",
    "GeometryAdapterError",
    "crop_intrinsics",
    "resize_intrinsics",
]
