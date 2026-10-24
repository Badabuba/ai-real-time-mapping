"""Deterministic dataset manifest for a local TUM RGB-D sequence.

Association, intrinsics and frame ordering come from rt_mapping.data.tum;
this module only records them together with archive checksums. The output
depends only on input file contents: no wall-clock time, host or git data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rt_mapping.data import tum

MANIFEST_SCHEMA_VERSION = 1
TUM_DATASET_PAGE = "https://cvg.cit.tum.de/data/datasets/rgbd-dataset"
# Reference cited next to the intrinsics table in rt_mapping/data/tum.py.
TUM_INTRINSICS_REFERENCE = "https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats"
DEFAULT_SMOKE_FRAMES = 200


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Lowercase hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_relative(path: Path, repo_root: Path) -> str:
    """POSIX path relative to repo_root; refuse anything outside it."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        raise ValueError(f"{path} is outside repository root {repo_root}") from None


def build_tum_manifest(
    sequence_dir: Path,
    archive_path: Path,
    repo_root: Path,
    archive_url: str,
    smoke_frames: int = DEFAULT_SMOKE_FRAMES,
    max_delta_s: float = tum.DEFAULT_MAX_ASSOCIATION_DELTA_S,
) -> dict[str, Any]:
    """Build the manifest dict for one extracted TUM sequence and its archive."""
    sequence_dir = Path(sequence_dir)
    archive_path = Path(archive_path)
    if smoke_frames <= 0:
        raise ValueError(f"smoke_frames must be positive, got {smoke_frames}")
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)

    sequence_id = sequence_dir.name
    frames = tum.load_sequence(sequence_dir, max_delta_s=max_delta_s, sequence_id=sequence_id)
    if len(frames) < smoke_frames:
        raise ValueError(
            f"Requested {smoke_frames} smoke frames, only {len(frames)} associations available"
        )

    camera = tum.camera_name(sequence_id)
    k = tum.rgb_intrinsics(sequence_id)
    index_files = {
        name: {
            "rows": len(tum.read_index(sequence_dir / name)),
            "sha256": sha256_file(sequence_dir / name),
        }
        for name in ("rgb.txt", "depth.txt")
    }

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset": "TUM RGB-D",
        "sequence_id": sequence_id,
        "camera": camera,
        "source": {
            "dataset_page": TUM_DATASET_PAGE,
            "archive_url": archive_url,
            "archive_filename": archive_path.name,
            "archive_size_bytes": archive_path.stat().st_size,
            "archive_sha256": sha256_file(archive_path),
        },
        "extracted_dir": _repo_relative(sequence_dir, repo_root),
        "index_files": index_files,
        "image": {"width": tum.TUM_IMAGE_WIDTH, "height": tum.TUM_IMAGE_HEIGHT},
        "intrinsics": {
            "description": f"TUM-provided {camera} RGB calibration used by the C1 loader",
            "implementation": "rt_mapping.data.tum.rgb_intrinsics",
            "reference": TUM_INTRINSICS_REFERENCE,
            "fx": float(k[0, 0]),
            "fy": float(k[1, 1]),
            "cx": float(k[0, 2]),
            "cy": float(k[1, 2]),
            "distortion_correction_applied_by_loader": False,
        },
        "depth": {
            "png_factor_units_per_m": tum.TUM_DEPTH_FACTOR,
            "usage": "evaluation or labelled oracle B1 only",
        },
        "association": {
            "implementation": "rt_mapping.data.tum.associate",
            "rule": (
                "greedy nearest pairs by |rgb_t - depth_t|, each RGB and depth frame "
                "used at most once, result sorted by RGB timestamp"
            ),
            "max_delta_s": max_delta_s,
            "num_associations": len(frames),
        },
        "splits": {
            "smoke": {
                "rule": f"first {smoke_frames} associations (frame_id 0..{smoke_frames - 1})",
                "num_frames": smoke_frames,
                "frames": [
                    {
                        "frame_id": f.frame.frame_id,
                        "rgb_timestamp_s": f.frame.timestamp_s,
                        "rgb_path": f.frame.image_path,
                        "depth_timestamp_s": f.gt_depth_timestamp_s,
                        "depth_path": f.gt_depth_path,
                    }
                    for f in frames[:smoke_frames]
                ],
            }
        },
    }


def dump_manifest(manifest: dict[str, Any]) -> str:
    """Serialise a manifest to stable JSON text ending with a newline."""
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
