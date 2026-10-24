"""Common interface for dense geometry models (docs/ARCHITECTURE.md §1, step 3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction

# Machine-readable failure reasons (docs/ARCHITECTURE.md §7) used by adapters.
ADAPTER_FAILURE_REASONS = frozenset(
    {
        "missing_input",
        "unexpected_input",
        "missing_intrinsics",
        "unsupported_config",
        "cuda_unavailable",
        "model_load_failed",
        "model_oom",
        "non_finite_output",
        "unexpected_model_output",
    }
)


class GeometryAdapterError(RuntimeError):
    """An adapter failure with a machine-readable reason code.

    reason is one of ADAPTER_FAILURE_REASONS; str(error) is "<reason>: <message>".
    """

    def __init__(self, reason: str, message: str) -> None:
        if reason not in ADAPTER_FAILURE_REASONS:
            raise ValueError(f"unknown adapter failure reason {reason!r}")
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


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
    - raise on failure instead of returning a silent fallback
      (GeometryAdapterError with a reason code where the cause is known).
    """

    def predict(self, frame: FrameRecord) -> GeometryPrediction: ...
