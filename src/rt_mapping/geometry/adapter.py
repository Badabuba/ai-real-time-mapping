"""Common interface for dense geometry models (docs/ARCHITECTURE.md §1, step 3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction


@runtime_checkable
class GeometryAdapter(Protocol):
    """Runs exactly one model on one frame.

    Implementations live outside generic modules and own model loading and
    image reading. They must:
    - take the raw K from frame.K and report K_processed for the image the model
      actually saw (use rt_mapping.geometry.intrinsics for resize/crop);
    - return metric depth in metres (relative-depth models do not fit this contract);
    - set confidence to None when the model gives none, never a placeholder;
    - time only the model call in inference_ms;
    - raise on failure instead of returning a silent fallback.
    """

    def predict(self, frame: FrameRecord) -> GeometryPrediction: ...
