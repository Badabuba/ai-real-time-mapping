from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from rt_mapping.evaluation import summarize_timings

SAMPLES = [100.0, 10.0, 20.0, 30.0, 40.0]


def test_warmup_excluded_and_cold_start_reported() -> None:
    s = summarize_timings(SAMPLES, warmup=1, stage="model_inference")
    assert (s.n_total, s.n_warmup, s.n_warm) == (5, 1, 4)
    assert s.cold_start_ms == 100.0
    assert s.warm_mean_ms == 25.0
    assert s.warm_median_ms == 25.0
    # linear: position 0.95 * 3 = 2.85 -> 30 + 0.85 * 10
    assert s.warm_p95_ms == pytest.approx(38.5)
    assert (s.warm_min_ms, s.warm_max_ms) == (10.0, 40.0)
    assert (s.unit, s.stage, s.percentile_method) == ("ms", "model_inference", "linear")


def test_p95_matches_numpy_linear() -> None:
    rng = np.random.default_rng(0)
    samples = rng.uniform(5, 50, size=37)
    s = summarize_timings(samples, warmup=2, stage="x")
    assert s.warm_p95_ms == float(np.percentile(samples[2:], 95, method="linear"))
    assert s.warm_median_ms == float(np.median(samples[2:]))


def test_warmup_zero_keeps_all_samples() -> None:
    s = summarize_timings(SAMPLES, warmup=0, stage="x")
    assert s.n_warm == 5 and s.cold_start_ms == 100.0 and s.warm_max_ms == 100.0


def test_single_warm_sample() -> None:
    s = summarize_timings([7.0, 3.0], warmup=1, stage="x")
    assert s.warm_median_ms == s.warm_p95_ms == 3.0


def test_to_dict_has_no_fps() -> None:
    d = summarize_timings(SAMPLES, warmup=1, stage="x").to_dict()
    assert not any("fps" in key for key in d)
    assert d["warm_p95_ms"] == pytest.approx(38.5)


@pytest.mark.parametrize(
    "samples",
    [[], [1.0, np.nan], [1.0, np.inf], [1.0, -0.1], [True, 1.0], np.array([True, False]), [[1.0, 2.0]], ["1"]],
)
def test_rejects_bad_samples(samples: Any) -> None:
    with pytest.raises(ValueError):
        summarize_timings(samples, warmup=0, stage="x")


@pytest.mark.parametrize("warmup", [-1, 1.0, True, 5, 6])
def test_rejects_bad_warmup(warmup: Any) -> None:
    with pytest.raises(ValueError):
        summarize_timings(SAMPLES, warmup=warmup, stage="x")


@pytest.mark.parametrize("stage", ["", "  ", None])
def test_rejects_bad_stage(stage: Any) -> None:
    with pytest.raises(ValueError):
        summarize_timings(SAMPLES, warmup=0, stage=stage)
