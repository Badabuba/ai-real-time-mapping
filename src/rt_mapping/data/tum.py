"""TUM RGB-D reader: index parsing, RGB-depth association and camera intrinsics.

Depth paths are returned only so evaluation code (or a labelled oracle) can load
ground truth. Pipeline inputs must use the RGB FrameRecord alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rt_mapping.contracts.frame import FrameRecord

# Ground-truth depth PNG units per metre (official TUM RGB-D convention).
TUM_DEPTH_FACTOR = 5000.0
TUM_IMAGE_WIDTH = 640
TUM_IMAGE_HEIGHT = 480
DEFAULT_MAX_ASSOCIATION_DELTA_S = 0.02

# Official ROS-default RGB intrinsics per camera (fx, fy, cx, cy).
# Source: https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats
# Lens distortion is not modelled here; freiburg1/2 raw images are distorted.
_TUM_RGB_INTRINSICS: dict[str, tuple[float, float, float, float]] = {
    "freiburg1": (517.3, 516.5, 318.6, 255.3),
    "freiburg2": (520.9, 521.0, 325.1, 249.7),
    "freiburg3": (535.4, 539.2, 320.1, 247.6),
}


@dataclass(frozen=True)
class TumIndexRow:
    timestamp_s: float
    relative_path: str


@dataclass(frozen=True)
class TumAssociation:
    """An RGB frame matched to its nearest depth frame."""

    rgb_timestamp_s: float
    rgb_path: str
    depth_timestamp_s: float
    depth_path: str

    @property
    def delta_s(self) -> float:
        return abs(self.rgb_timestamp_s - self.depth_timestamp_s)


@dataclass(frozen=True)
class TumFrame:
    """Pipeline input frame plus the evaluation-only depth reference."""

    frame: FrameRecord
    gt_depth_timestamp_s: float
    gt_depth_path: str


def camera_name(sequence_id: str) -> str:
    """Return 'freiburg1'/'freiburg2'/'freiburg3' for a TUM sequence id."""
    match = re.search(r"freiburg([123])", sequence_id)
    if match is None:
        raise ValueError(f"Cannot infer TUM camera from sequence id {sequence_id!r}")
    return f"freiburg{match.group(1)}"


def rgb_intrinsics(sequence_id: str) -> np.ndarray:
    """Raw 640x480 RGB intrinsics K (float64) for the sequence's camera."""
    fx, fy, cx, cy = _TUM_RGB_INTRINSICS[camera_name(sequence_id)]
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


def read_index(path: Path) -> list[TumIndexRow]:
    """Parse a TUM rgb.txt / depth.txt file, skipping comments and blank lines."""
    rows: list[TumIndexRow] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        timestamp, relative_path, *_ = line.split()
        rows.append(TumIndexRow(float(timestamp), relative_path))
    return rows


def associate(
    rgb_rows: list[TumIndexRow],
    depth_rows: list[TumIndexRow],
    max_delta_s: float = DEFAULT_MAX_ASSOCIATION_DELTA_S,
) -> list[TumAssociation]:
    """Greedily match each RGB frame to its nearest unused depth frame.

    Pairs are taken in order of increasing time difference; each RGB and depth
    frame is used at most once. The result is sorted by RGB timestamp.
    """
    if max_delta_s < 0:
        raise ValueError(f"max_delta_s must be >= 0, got {max_delta_s}")
    candidates = sorted(
        (abs(rgb.timestamp_s - depth.timestamp_s), rgb_i, depth_i)
        for rgb_i, rgb in enumerate(rgb_rows)
        for depth_i, depth in enumerate(depth_rows)
        if abs(rgb.timestamp_s - depth.timestamp_s) <= max_delta_s
    )
    used_rgb: set[int] = set()
    used_depth: set[int] = set()
    matches: list[TumAssociation] = []
    for _, rgb_i, depth_i in candidates:
        if rgb_i in used_rgb or depth_i in used_depth:
            continue
        used_rgb.add(rgb_i)
        used_depth.add(depth_i)
        rgb, depth = rgb_rows[rgb_i], depth_rows[depth_i]
        matches.append(
            TumAssociation(rgb.timestamp_s, rgb.relative_path, depth.timestamp_s, depth.relative_path)
        )
    return sorted(matches, key=lambda m: (m.rgb_timestamp_s, m.rgb_path, m.depth_timestamp_s))


def load_sequence(
    sequence_dir: Path,
    max_delta_s: float = DEFAULT_MAX_ASSOCIATION_DELTA_S,
    sequence_id: str | None = None,
) -> list[TumFrame]:
    """Read and associate a TUM sequence directory into ordered frames.

    frame_id is the 0-based position in the associated list.
    """
    sequence_dir = Path(sequence_dir)
    for name in ("rgb.txt", "depth.txt"):
        if not (sequence_dir / name).is_file():
            raise FileNotFoundError(sequence_dir / name)
    sequence_id = sequence_id or sequence_dir.name
    k = rgb_intrinsics(sequence_id)
    matches = associate(
        read_index(sequence_dir / "rgb.txt"),
        read_index(sequence_dir / "depth.txt"),
        max_delta_s,
    )
    return [
        TumFrame(
            frame=FrameRecord(
                sequence_id=sequence_id,
                frame_id=index,
                timestamp_s=match.rgb_timestamp_s,
                image_path=match.rgb_path,
                width=TUM_IMAGE_WIDTH,
                height=TUM_IMAGE_HEIGHT,
                K=k,
            ),
            gt_depth_timestamp_s=match.depth_timestamp_s,
            gt_depth_path=match.depth_path,
        )
        for index, match in enumerate(matches)
    ]
