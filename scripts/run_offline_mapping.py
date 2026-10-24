"""Fuse matching B0 SLAM and DA3 run artifacts; no GPU/native backend needed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.mapping_run import run_mapping


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slam-run", type=Path, required=True)
    parser.add_argument("--geometry-run", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/offline_mapping.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        directory = run_mapping(ROOT, args.slam_run, args.geometry_run, run_id=args.run_id,
                                config=config, output_root=args.output_root)
    except (OSError, ValueError, KeyError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2
    record = load_run_manifest(directory / "run.json")
    print(f"{record['status']}: {directory}")
    if record["reason"]:
        print(record["reason"], file=sys.stderr)
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
