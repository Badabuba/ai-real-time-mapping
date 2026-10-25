"""Per-keyframe sparse anchoring and pre-registered frame gate for P1-robust (U-02); GT-free."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.alignment.anchoring import run_anchor_gate
from rt_mapping.contracts.run_manifest import load_run_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-run", type=Path, required=True)
    parser.add_argument("--slam-run", type=Path, required=True)
    parser.add_argument("--geometry-run", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/robust_fusion.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", args.run_id):
        parser.error("invalid run ID")
    if (args.output_root / args.run_id).exists():
        parser.error("existing run is never overwritten")
    path = run_anchor_gate(ROOT, args.comparison_run, args.slam_run, args.geometry_run, args.config,
                           run_id=args.run_id, output_root=args.output_root)
    record = load_run_manifest(path / "run.json")
    print(f"{record['status']}: {path}")
    if record["reason"]:
        print(record["reason"], file=sys.stderr)
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
