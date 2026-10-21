"""TUM ground-truth depth PNG reader (evaluation only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rt_mapping.evaluation.tum_depth import load_tum_depth_m


def test_uint16_png_is_read_in_metres_and_zeros_stay_invalid(tmp_path: Path) -> None:
    from PIL import Image

    raw = np.array([[0, 5000, 7500], [1, 65535, 2500]], dtype=np.uint16)
    (tmp_path / "depth").mkdir()
    Image.fromarray(raw).save(tmp_path / "depth" / "d.png")
    depth = load_tum_depth_m(tmp_path, "depth/d.png")
    assert depth.dtype == np.float32
    np.testing.assert_allclose(depth, raw.astype(np.float64) / 5000.0, rtol=1e-6)
    assert depth[0, 0] == 0.0


def test_missing_and_non_depth_files_raise(tmp_path: Path) -> None:
    from PIL import Image

    with pytest.raises(FileNotFoundError):
        load_tum_depth_m(tmp_path, "nope.png")
    Image.fromarray(np.zeros((2, 2, 3), np.uint8)).save(tmp_path / "rgb.png")
    with pytest.raises(ValueError, match="16-bit"):
        load_tum_depth_m(tmp_path, "rgb.png")
