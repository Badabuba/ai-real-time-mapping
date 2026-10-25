"""Evaluate final and retained-keyframe B0 trajectories with evaluation-only Sim(3)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.evaluation.slam_run import evaluate_slam_run
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.trajectory import NoGroundTruthOverlap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--groundtruth", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--max-timestamp-delta", type=float, default=0.02)
    parser.add_argument("--rpe-delta", type=int, default=1)
    parser.add_argument("--tracking-warmup", type=int, default=1, help="exclude first N input rows from warm tracking latency")
    parser.add_argument("--plot", action="store_true", help="save observed state and tracking-latency timeline")
    args = parser.parse_args()
    try:
        directory = evaluate_slam_run(
            ROOT, args.source_run, args.groundtruth, run_id=args.run_id, output_root=args.output_root,
            resources=args.resources, max_delta_s=args.max_timestamp_delta, rpe_delta=args.rpe_delta,
            tracking_warmup=args.tracking_warmup, plot=args.plot,
        )
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, NoGroundTruthOverlap):
            print(json.dumps({"status": "failed", "reason": str(exc), "gt_coverage": exc.coverage}),
                  file=sys.stderr)
        else:
            print(f"Rejected: {exc}", file=sys.stderr)
        return 2
    record = load_run_manifest(directory / "run.json")
    print(f"Evaluation: {directory} ({record['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
