"""P1-robust smoke (U-03): control reproduction, anchored and gated maps (GT-free), then evaluation."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.robust_fusion_run import run_robust_fusion


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-run", type=Path, required=True)
    parser.add_argument("--slam-run", type=Path, required=True)
    parser.add_argument("--geometry-run", type=Path, required=True)
    parser.add_argument("--sequence-dir", type=Path, required=True, help="evaluation-only TUM sequence directory")
    parser.add_argument("--manifest", type=Path, required=True, help="evaluation-only frozen dataset manifest")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/robust_fusion.json")
    parser.add_argument("--u02-summary", type=Path, required=True,
                        help="committed U-02 summary holding the frozen config sha256 and decisions")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", args.run_id):
        parser.error("invalid run ID")
    if (args.output_root / args.run_id).exists():
        parser.error("existing run is never overwritten")
    path = run_robust_fusion(ROOT, args.comparison_run, args.slam_run, args.geometry_run, args.sequence_dir,
                             args.manifest, args.config, args.u02_summary, run_id=args.run_id,
                             output_root=args.output_root, plot=args.plot)
    record = load_run_manifest(path / "run.json")
    print(f"{record['status']}: {path}")
    if record["reason"]:
        print(record["reason"], file=sys.stderr)
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
