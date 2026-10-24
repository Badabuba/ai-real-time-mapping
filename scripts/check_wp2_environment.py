"""Check WP2 data/source/runtime without installing packages or modifying inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.slam.setup import host_report, inspect_source, load_setup_config, probe_runtime, verify_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/wp2_pyslam_baseline.json")
    parser.add_argument("--pyslam-root", type=Path, default=ROOT / "external/pyslam")
    parser.add_argument("--pyslam-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--dataset-only", action="store_true")
    parser.add_argument("--full", action="store_true", help="compare all extracted files with archive bytes")
    parser.add_argument("--probe-runtime", action="store_true", help="import actual pySLAM entry point in a subprocess")
    args = parser.parse_args()
    report = {"schema": "rt_mapping.wp2_preflight/v1", "scope": "setup verification, not a SLAM benchmark", "host": host_report(ROOT)}
    try:
        config = load_setup_config(args.config)
        report["dataset"] = verify_dataset(ROOT, config, full=args.full)
        if not args.dataset_only:
            report["source"] = inspect_source(args.pyslam_root, config["upstream"]["revision"])
            report["runtime"] = probe_runtime(args.pyslam_python, args.pyslam_root) if args.probe_runtime else {"status": "not_checked"}
        report["status"] = "ok" if args.dataset_only else (
            "ok" if report["source"]["status"] == "ok" and report["runtime"]["status"] == "ok" else "blocked"
        )
    except (OSError, ValueError, KeyError) as exc:
        report["status"], report["reason"] = "failed", str(exc)
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
