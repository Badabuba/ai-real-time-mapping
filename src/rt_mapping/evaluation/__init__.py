"""Model-independent evaluation: depth metrics and timing summaries.

Ground truth is read only here (or in a labelled oracle), never by the pipeline.
"""

from rt_mapping.evaluation.depth import DepthMetrics, evaluate_depth, mean_depth_metrics, resize_depth_nearest
from rt_mapping.evaluation.timing import TimingSummary, summarize_timings
from rt_mapping.evaluation.tum_depth import load_tum_depth_m

__all__ = [
    "DepthMetrics",
    "TimingSummary",
    "evaluate_depth",
    "load_tum_depth_m",
    "mean_depth_metrics",
    "resize_depth_nearest",
    "summarize_timings",
]
