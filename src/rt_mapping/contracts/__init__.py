"""Typed data contracts shared between pipeline modules (see docs/ARCHITECTURE.md §2)."""

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction, load_prediction, save_prediction

__all__ = ["FrameRecord", "GeometryPrediction", "load_prediction", "save_prediction"]
