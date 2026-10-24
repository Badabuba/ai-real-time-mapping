"""Typed data contracts shared between pipeline modules (see docs/ARCHITECTURE.md §2)."""

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction, load_prediction, save_prediction
from rt_mapping.contracts.run_manifest import (
    build_run_manifest,
    dump_run_manifest,
    format_utc,
    load_run_manifest,
    validate_run_manifest,
    write_run_manifest,
)

__all__ = [
    "FrameRecord",
    "GeometryPrediction",
    "build_run_manifest",
    "dump_run_manifest",
    "format_utc",
    "load_prediction",
    "load_run_manifest",
    "save_prediction",
    "validate_run_manifest",
    "write_run_manifest",
]
