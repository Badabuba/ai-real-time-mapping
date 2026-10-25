"""Read-only audit of an immutable geometry run, without importing GPU packages."""
import argparse
import json
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.contracts.geometry import load_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.geometry_verification import verify_geometry_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--checkpoint-file", type=Path)
    parser.add_argument("--assets-root", type=Path, help="recompute metrics/masks from frozen local data")
    args = parser.parse_args()
    run = load_run_manifest(args.run / "run.json")
    if run["status"] != "ok" or run["dirty_worktree"]:
        raise ValueError("expected a successful clean-commit run")
    subprocess.run(["git", "cat-file", "-e", run["git_commit"] + "^{commit}"], cwd=ROOT, check=True)
    metrics = json.loads((args.run / run["artifacts"]["metrics"]).read_text())
    timing = json.loads((args.run / run["artifacts"]["timing"]).read_text())
    for row in metrics["per_frame"]:
        prediction = load_prediction(args.run / row["prediction"])
        if (prediction.frame_id, prediction.timestamp_s) != (row["frame_id"], row["timestamp_s"]):
            raise ValueError("prediction identity differs from metrics")
        if run["model"]["revision"] not in prediction.model_id:
            raise ValueError("prediction model revision differs from run")
    if len(metrics["per_frame"]) != run["config"]["frames"]:
        raise ValueError("frame count differs from request")
    if args.checkpoint_file:
        expected = run["model"]["checkpoint"].split("@sha256:", 1)[1]
        if sha256_file(args.checkpoint_file) != expected:
            raise ValueError("checkpoint hash mismatch")
    report = verify_geometry_run(args.run, repo_root=ROOT if args.assets_root else None,
                                 assets_root=args.assets_root)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
