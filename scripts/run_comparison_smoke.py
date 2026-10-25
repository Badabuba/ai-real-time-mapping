"""Synthetic-only complete mapping/comparison smoke, with analytic GT control."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs.comparison_run import run_comparison
from rt_mapping.runs.geometry_run import collect_git_state
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=f"synthetic_comparison_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", args.run_id):
        parser.error("invalid run ID")
    if (args.output_root / args.run_id).exists():
        parser.error("existing run is never overwritten")
    state = collect_git_state(ROOT)
    slam, geometry = create_synthetic_inputs(args.output_root / (args.run_id+"_inputs"),
                            git_commit=state.commit, dirty_worktree=state.dirty, non_collinear=True)
    sequence, manifest = create_synthetic_reference(args.output_root / (args.run_id+"_evaluation"), slam, geometry)
    path = run_comparison(ROOT, slam, geometry, sequence, manifest, run_id=args.run_id,
                           config={"mapping": {"plot": args.plot}}, output_root=args.output_root)
    record = load_run_manifest(path / "run.json")
    print(f"SYNTHETIC ONLY: {record['status']}: {path}")
    if record["reason"]:
        print(record["reason"], file=sys.stderr)
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
