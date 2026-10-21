"""Build or check the TUM RGB-D dataset manifest (thin CLI over rt_mapping.data.manifest)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rt_mapping.data.manifest import (  # noqa: E402
    DEFAULT_SMOKE_FRAMES,
    build_tum_manifest,
    dump_manifest,
)

DEFAULT_SEQUENCE_DIR = "data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz"
DEFAULT_ARCHIVE = "data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz.tgz"
DEFAULT_ARCHIVE_URL = (
    "https://cvg.cit.tum.de/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_xyz.tgz"
)
DEFAULT_OUTPUT = "data/manifests/tum_fr1_xyz.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-dir", type=Path, default=REPO_ROOT / DEFAULT_SEQUENCE_DIR)
    parser.add_argument("--archive", type=Path, default=REPO_ROOT / DEFAULT_ARCHIVE)
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / DEFAULT_OUTPUT)
    parser.add_argument("--smoke-frames", type=int, default=DEFAULT_SMOKE_FRAMES)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild and compare with the existing output; never writes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = dump_manifest(
        build_tum_manifest(
            sequence_dir=args.sequence_dir,
            archive_path=args.archive,
            repo_root=REPO_ROOT,
            archive_url=args.archive_url,
            smoke_frames=args.smoke_frames,
        )
    )
    if args.check:
        if not args.output.is_file():
            print(f"MISSING: {args.output}")
            return 1
        existing = args.output.read_bytes().decode("utf-8")
        if existing != text:
            print(f"MISMATCH: {args.output} differs from a fresh build")
            return 1
        print(f"OK: {args.output} matches a fresh build")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
