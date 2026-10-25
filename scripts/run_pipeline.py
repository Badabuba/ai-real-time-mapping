"""Run configured existing/native SLAM and DA3 stages, then align/fuse/compare."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.runs.pipeline_run import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        directory = run_pipeline(ROOT, json.loads(args.config.read_text(encoding="utf-8")), run_id=args.run_id)
    except (ValueError, OSError, KeyError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2
    record = load_run_manifest(directory / "run.json")
    print(f"{record['status']}: {directory}")
    if record["reason"]:
        print(record["reason"], file=sys.stderr)
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
