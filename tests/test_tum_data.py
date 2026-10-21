from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from rt_mapping.contracts import FrameRecord
from rt_mapping.data import tum

FIXTURE = Path(__file__).parent / "fixtures" / "rgbd_dataset_freiburg1_mini"
SRC = Path(__file__).resolve().parents[1] / "src" / "rt_mapping"


def test_read_index_skips_comments_blank_lines_and_extra_columns() -> None:
    depth = tum.read_index(FIXTURE / "depth.txt")
    assert [row.timestamp_s for row in depth] == [0.995, 1.012, 1.150, 1.205]
    assert depth[1].relative_path == "depth/1.012.png"
    assert len(tum.read_index(FIXTURE / "rgb.txt")) == 4


def test_associate_is_greedy_unique_and_within_delta() -> None:
    matches = tum.associate(
        tum.read_index(FIXTURE / "rgb.txt"), tum.read_index(FIXTURE / "depth.txt"), 0.02
    )
    pairs = [(m.rgb_timestamp_s, m.depth_timestamp_s) for m in matches]
    # 1.000 takes its closest depth (0.995), leaving 1.012 for 1.030;
    # 1.100 has no depth within 20 ms and is dropped.
    assert pairs == [(1.000, 0.995), (1.030, 1.012), (1.200, 1.205)]
    assert all(m.delta_s <= 0.02 for m in matches)


def test_associate_rejects_negative_delta() -> None:
    with pytest.raises(ValueError):
        tum.associate([], [], -0.1)


def test_load_sequence_builds_frame_records() -> None:
    frames = tum.load_sequence(FIXTURE)
    assert [f.frame.frame_id for f in frames] == [0, 1, 2]
    first = frames[0]
    assert first.frame.sequence_id == "rgbd_dataset_freiburg1_mini"
    assert first.frame.image_path == "rgb/1.000.png"
    assert (first.frame.width, first.frame.height) == (640, 480)
    assert first.frame.K.dtype == np.float64
    np.testing.assert_allclose(first.frame.K[[0, 1, 0, 1], [0, 1, 2, 2]], [517.3, 516.5, 318.6, 255.3])
    assert first.gt_depth_path == "depth/0.995.png"


def test_load_sequence_requires_index_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tum.load_sequence(tmp_path / "rgbd_dataset_freiburg1_missing")


@pytest.mark.parametrize(
    ("sequence_id", "expected"),
    [
        ("rgbd_dataset_freiburg1_xyz", (517.3, 516.5, 318.6, 255.3)),
        ("rgbd_dataset_freiburg2_desk", (520.9, 521.0, 325.1, 249.7)),
        ("rgbd_dataset_freiburg3_long_office_household", (535.4, 539.2, 320.1, 247.6)),
    ],
)
def test_rgb_intrinsics_per_camera(sequence_id: str, expected: tuple[float, ...]) -> None:
    k = tum.rgb_intrinsics(sequence_id)
    assert (k[0, 0], k[1, 1], k[0, 2], k[1, 2]) == expected
    assert k[2].tolist() == [0.0, 0.0, 1.0]


def test_unknown_camera_is_rejected() -> None:
    with pytest.raises(ValueError):
        tum.rgb_intrinsics("kitti_00")


def test_frame_record_validates_and_freezes_k() -> None:
    record = FrameRecord("seq", 0, 1.0, "rgb/a.png", 640, 480, np.eye(3, dtype=np.float32))
    assert record.K.dtype == np.float64
    with pytest.raises(ValueError):
        record.K[0, 0] = 2.0
    with pytest.raises(ValueError):
        FrameRecord("seq", 0, 1.0, "rgb/a.png", 640, 480, np.eye(2))
    with pytest.raises(ValueError):
        FrameRecord("seq", -1, 1.0, "rgb/a.png", 640, 480, np.eye(3))
    with pytest.raises(ValueError):
        FrameRecord("seq", 0, float("nan"), "rgb/a.png", 640, 480, np.eye(3))


@pytest.mark.parametrize("package", ["contracts", "data", "geometry"])
def test_generic_modules_do_not_import_models(package: str) -> None:
    forbidden = {"torch", "depth_anything_3", "pyslam", "unidepth"}
    for path in (SRC / package).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not {n.split(".")[0] for n in names} & forbidden, f"{path} imports {names}"
