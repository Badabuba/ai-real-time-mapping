from dataclasses import replace

import numpy as np
import pytest

from rt_mapping.alignment.causal import causal_window_scales
from rt_mapping.alignment.correspondences import build_correspondences
from rt_mapping.runs.artifacts import load_mapping_inputs
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs


def test_causal_estimate_is_unchanged_by_future_depths_or_new_landmarks(tmp_path):
    inputs = load_mapping_inputs(*create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40))
    pairs = build_correspondences(inputs.snapshot, inputs.predictions)
    frame_ids = [10, 27, 40]
    original, records = causal_window_scales(pairs, frame_ids, window_frames=2)
    target = pairs.target_depth_m.copy()
    target[pairs.frame_id == 40] *= 1.5
    changed, _ = causal_window_scales(replace(pairs, target_depth_m=target), frame_ids[:2], window_frames=2)
    assert changed[10] == original[10] and changed[27] == original[27]
    assert records[0]["window_frame_ids"] == [10]
    assert records[2]["window_frame_ids"] == [27, 40]
    assert original[10] == pytest.approx(2.5, abs=1e-4)


def test_causal_startup_does_not_fall_back_to_future_support(tmp_path):
    inputs = load_mapping_inputs(*create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40))
    pairs = build_correspondences(inputs.snapshot, inputs.predictions)
    with pytest.raises(ValueError, match="insufficient_correspondences"):
        causal_window_scales(pairs, [10, 27, 40], min_inliers=100)
