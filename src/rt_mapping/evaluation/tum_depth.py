"""TUM ground-truth depth reader. Evaluation (or labelled oracle B1) only.

Pillow is imported when a file is read, not at module import.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rt_mapping.data.tum import TUM_DEPTH_FACTOR


def load_tum_depth_m(sequence_dir: str | Path, relative_path: str) -> np.ndarray:
    """Read a TUM 16-bit depth PNG as float32 metres (value / 5000).

    Zero (no measurement) stays 0; evaluation treats it as invalid.
    """
    from PIL import Image

    path = Path(sequence_dir) / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        raw = np.asarray(image)
    if raw.ndim != 2 or raw.dtype not in (np.uint16, np.int32, np.uint32):
        raise ValueError(f"{relative_path}: expected a single-channel 16-bit depth PNG, got {raw.dtype} {raw.shape}")
    return (raw.astype(np.float32) / np.float32(TUM_DEPTH_FACTOR)).astype(np.float32)
