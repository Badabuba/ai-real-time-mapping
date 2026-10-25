"""Evaluate frozen confidence quantiles from an immutable geometry run.

Default: per-frame 100/75/50% depth-only diagnostic (GT read only for scoring).
--pooled-thresholds: GT-free pooled retain-75%/50% thresholds for map ablations.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.evaluation.confidence_ablation import analyze_run, pooled_confidence_thresholds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sequence-dir", type=Path)
    parser.add_argument("--pooled-thresholds", action="store_true", help="predictions only; never opens GT")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.pooled_thresholds:
        if args.sequence_dir is not None:
            parser.error("--pooled-thresholds is GT-free; do not pass --sequence-dir")
        report = pooled_confidence_thresholds(args.run)
    else:
        if args.sequence_dir is None:
            parser.error("--sequence-dir is required for the depth-only diagnostic")
        report = analyze_run(args.run, args.sequence_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2, allow_nan=False, ensure_ascii=False) + "\n")
    print(report.get("status", "thresholds written"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
