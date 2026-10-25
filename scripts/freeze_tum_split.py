"""Freeze a documented TUM split; never overwrite an existing manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rt_mapping.data.manifest import build_tum_split_manifest, dump_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-url", required=True)
    parser.add_argument("--split", choices=["development", "selection", "held-out"], required=True)
    parser.add_argument("--frames", type=int, default=None, help="default: entire sequence")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-repo-root", type=Path, default=REPO_ROOT, help="root for portable extracted_dir")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = dump_manifest(build_tum_split_manifest(
        args.sequence_dir, args.archive, args.data_repo_root, args.archive_url,
        args.split, args.frames,
    ))
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != content.encode("utf-8"):
            print("MISMATCH: frozen split differs")
            return 1
        print("OK: frozen split matches input bytes")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    print(f"Wrote {args.output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
