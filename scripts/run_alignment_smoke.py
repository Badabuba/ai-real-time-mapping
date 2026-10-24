"""Synthetic WP3/WP4 smoke: generated artifacts -> known scale -> fused map."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.geometry_run import collect_git_state
from rt_mapping.runs.mapping_run import run_mapping
from rt_mapping.runs.synthetic_mapping import KNOWN_SCALE, create_synthetic_inputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=f"synthetic_mapping_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--plot", action="store_true", help="requires the plots extra (matplotlib)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,110}", args.run_id):
        parser.error("invalid run ID")
    if (args.output_root / args.run_id).exists():
        parser.error("run already exists; choose a new ID")
    state = collect_git_state(ROOT)
    try:
        slam, geometry = create_synthetic_inputs(args.output_root / f"{args.run_id}_inputs",
                                                git_commit=state.commit, dirty_worktree=state.dirty)
        directory = run_mapping(ROOT, slam, geometry, run_id=args.run_id, config={"plot": args.plot}, output_root=args.output_root)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    record = load_run_manifest(directory / "run.json")
    if record["status"] != "ok":
        print(record["reason"], file=sys.stderr)
        return 1
    result = json.loads((directory / "alignment.json").read_text(encoding="utf-8"))
    error = abs(result["scale"] - KNOWN_SCALE)
    print(json.dumps({"synthetic_only": True, "run_dir": str(directory), "known_scale": KNOWN_SCALE,
                      "estimated_scale": result["scale"], "absolute_scale_error": error}, indent=2))
    return 0 if error < 1e-4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
