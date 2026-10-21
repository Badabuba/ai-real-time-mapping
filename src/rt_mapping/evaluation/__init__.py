"""Model-independent evaluation: depth metrics and timing summaries.

Ground truth is read only here (or in a labelled oracle), never by the pipeline.
"""

from rt_mapping.evaluation.depth import DepthMetrics, evaluate_depth, mean_depth_metrics, resize_depth_nearest
from rt_mapping.evaluation.timing import TimingSummary, summarize_timings

__all__ = [
    "DepthMetrics",
    "TimingSummary",
    "evaluate_depth",
    "mean_depth_metrics",
    "resize_depth_nearest",
    "summarize_timings",
]
