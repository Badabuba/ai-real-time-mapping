"""FrameRecord contract: one raw RGB frame plus its intrinsics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FrameRecord:
    """One input RGB frame, as defined in docs/ARCHITECTURE.md §2.

    image_path is relative to the sequence directory (as written in TUM rgb.txt).
    K holds the intrinsics of the raw, unresized image.
    """

    sequence_id: str
    frame_id: int
    timestamp_s: float
    image_path: str
    width: int
    height: int
    K: np.ndarray

    def __post_init__(self) -> None:
        if not self.sequence_id:
            raise ValueError("sequence_id must be non-empty")
        if self.frame_id < 0:
            raise ValueError(f"frame_id must be >= 0, got {self.frame_id}")
        if not np.isfinite(self.timestamp_s):
            raise ValueError(f"timestamp_s must be finite, got {self.timestamp_s}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"image size must be positive, got {self.width}x{self.height}")
        k = np.array(self.K, dtype=np.float64)
        if k.shape != (3, 3) or not np.all(np.isfinite(k)):
            raise ValueError(f"K must be a finite 3x3 matrix, got shape {k.shape}")
        k.setflags(write=False)
        # frozen dataclass: bypass __setattr__ to store the normalised copy.
        object.__setattr__(self, "K", k)
        object.__setattr__(self, "timestamp_s", float(self.timestamp_s))
