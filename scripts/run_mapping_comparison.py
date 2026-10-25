"""Compare exported B0/B1/P1 maps; GT is used only for oracle/evaluation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.comparison_run import run_comparison


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slam-run", type=Path, required=True)
    parser.add_argument("--geometry-run", type=Path, required=True)
    parser.add_argument("--sequence-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/tum_fr1_xyz.json")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/mapping_comparison.json")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        directory = run_comparison(ROOT, args.slam_run, args.geometry_run, args.sequence_dir, args.manifest,
                                   run_id=args.run_id, config=json.loads(args.config.read_text(encoding="utf-8")))
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
