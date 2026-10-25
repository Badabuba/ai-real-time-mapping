"""Measure whole-run B0 wall time and POSIX peak RSS without changing the baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.evaluation.slam_run import measure_slam_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--pyslam-root", type=Path, default=ROOT / "external/pyslam")
    parser.add_argument("--pyslam-python", type=Path, default=ROOT / ".venv-pyslam/bin/python")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--no-export-sparse", action="store_true")
    args = parser.parse_args()
    try:
        report = measure_slam_run(
            ROOT, Path(sys.executable), args.pyslam_root, args.pyslam_python,
            run_id=args.run_id, frames=args.frames, timeout_s=args.timeout,
            output_root=args.output_root, export_sparse=not args.no_export_sparse,
        )
    except (OSError, ValueError) as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 2
    print(f"Resources: {report}")
    return 0 if json.loads(report.read_text())["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
