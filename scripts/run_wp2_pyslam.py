"""Run the frozen RGB-only pySLAM B0 smoke in its separate native environment."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.slam.setup import load_setup_config
from rt_mapping.slam.smoke import run_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/wp2_pyslam_baseline.json")
    parser.add_argument("--pyslam-root", type=Path, default=ROOT / "external/pyslam")
    parser.add_argument("--pyslam-python", type=Path, default=ROOT / ".venv-pyslam/bin/python")
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--export-sparse", action="store_true",
                        help="Export retained landmarks/keyframe pixel links after shutdown (new run only)")
    parser.add_argument("--run-id", default=f"yaropolk_b0_fr1_xyz_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    args = parser.parse_args()
    try:
        directory = run_smoke(ROOT, args.pyslam_root, args.pyslam_python, load_setup_config(args.config),
                              run_id=args.run_id, frames=args.frames, timeout_s=args.timeout,
                              export_sparse=args.export_sparse)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 2
    record = json.loads((directory / "run.json").read_text())
    print(json.dumps({"status": record["status"], "reason": record["reason"], "run_dir": str(directory)}, indent=2))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
