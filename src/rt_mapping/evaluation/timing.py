"""Latency summaries for one pipeline stage (docs/EXPERIMENTS.md §4.4).

The first `warmup` samples are excluded from the warm statistics; the very
first sample is always reported separately as cold_start_ms. p95 uses
numpy.percentile(..., method="linear"). No FPS is derived: effective FPS needs
wall-clock time of the whole pipeline, not per-stage latencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

PERCENTILE_METHOD = "linear"


@dataclass(frozen=True)
class TimingSummary:
    stage: str
    unit: str
    n_total: int
    n_warmup: int
    n_warm: int
    cold_start_ms: float
    warm_mean_ms: float
    warm_median_ms: float
    warm_p95_ms: float
    warm_min_ms: float
    warm_max_ms: float
    percentile_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_timings(samples_ms: Sequence[float], *, warmup: int, stage: str) -> TimingSummary:
    """Summarise per-frame latencies in milliseconds for one named stage.

    Raises ValueError for empty, non-1-D, non-finite, negative or bool samples,
    a bad warmup count, or when no sample remains after warm-up.
    """
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("stage must be a non-empty string, e.g. 'model_inference'")
    if isinstance(warmup, bool) or not isinstance(warmup, (int, np.integer)) or warmup < 0:
        raise ValueError(f"warmup must be an integer >= 0, got {warmup!r}")

    if isinstance(samples_ms, np.ndarray):
        array = samples_ms
    else:
        items = list(samples_ms)
        # np.asarray would silently turn True/False into 1.0/0.0 in a mixed list.
        if any(isinstance(v, (bool, np.bool_)) for v in items):
            raise ValueError("samples_ms must be numbers, not bools")
        array = np.asarray(items)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"samples_ms must be a non-empty 1-D sequence, got shape {array.shape}")
    if array.dtype == np.bool_:
        raise ValueError("samples_ms must be numbers, not bools")
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(array.dtype, np.complexfloating):
        raise ValueError(f"samples_ms must be real numbers, got dtype {array.dtype}")
    array = array.astype(np.float64)
    if not np.all(np.isfinite(array)) or np.any(array < 0):
        raise ValueError("samples_ms must be finite and >= 0")

    warm = array[int(warmup):]
    if warm.size == 0:
        raise ValueError(f"no samples left after warmup={warmup} (n_total={array.size})")

    p95 = float(np.percentile(warm, 95, method=PERCENTILE_METHOD))
    return TimingSummary(
        stage=stage,
        unit="ms",
        n_total=int(array.size),
        n_warmup=int(warmup),
        n_warm=int(warm.size),
        cold_start_ms=float(array[0]),
        warm_mean_ms=float(np.mean(warm)),
        warm_median_ms=float(np.median(warm)),
        warm_p95_ms=p95,
        warm_min_ms=float(np.min(warm)),
        warm_max_ms=float(np.max(warm)),
        percentile_method=PERCENTILE_METHOD,
    )
