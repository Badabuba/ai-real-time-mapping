"""Prepare pySLAM config and an RGB-only smoke view; never install or run upstream."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.slam.setup import load_setup_config, prepare_baseline, verify_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/wp2_pyslam_baseline.json")
    parser.add_argument("--pyslam-root", type=Path, default=ROOT / "external/pyslam")
    parser.add_argument("--output", type=Path, required=True, help="new directory under ignored outputs/wp2/")
    parser.add_argument("--frames", type=int, default=200)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if not output.is_relative_to((ROOT / "outputs/wp2").resolve()):
            raise ValueError("output must be under outputs/wp2/")
        config = load_setup_config(args.config)
        verify_dataset(ROOT, config)
        plan = prepare_baseline(ROOT, args.pyslam_root, output, config, frames=args.frames)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": plan["status"], "frames": len(plan["frames"]), "setup": str(output / "setup.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
