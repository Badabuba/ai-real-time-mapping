"""Write a small validated model-selection scorecard from two completed runs."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.evaluation.model_selection import build_scorecard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs=2, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_scorecard(args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print("selected_model:", report["selected_model"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
