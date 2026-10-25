"""Evaluate final and retained-keyframe B0 trajectories with evaluation-only Sim(3)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.evaluation.slam_run import evaluate_slam_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--groundtruth", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--max-timestamp-delta", type=float, default=0.02)
    parser.add_argument("--rpe-delta", type=int, default=1)
    args = parser.parse_args()
    try:
        directory = evaluate_slam_run(
            ROOT, args.source_run, args.groundtruth, run_id=args.run_id, output_root=args.output_root,
            resources=args.resources, max_delta_s=args.max_timestamp_delta, rpe_delta=args.rpe_delta,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 2
    print(f"Evaluation: {directory} (degraded: all-frame tracking evaluation pending Y-03)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
