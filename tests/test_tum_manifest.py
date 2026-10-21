from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from rt_mapping.data import tum
from rt_mapping.data.manifest import build_tum_manifest, dump_manifest, sha256_file

FIXTURE = Path(__file__).parent / "fixtures" / "rgbd_dataset_freiburg1_mini"
URL = "https://example.invalid/rgbd_dataset_freiburg1_mini.tgz"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A fake repo root holding the mini fixture and a small fake archive."""
    raw = tmp_path / "data" / "raw" / "tum_rgbd"
    shutil.copytree(FIXTURE, raw / FIXTURE.name)
    (raw / f"{FIXTURE.name}.tgz").write_bytes(b"fake archive bytes")
    return tmp_path


def _build(repo: Path, **kwargs: object) -> dict:
    raw = repo / "data" / "raw" / "tum_rgbd"
    return build_tum_manifest(
        sequence_dir=raw / FIXTURE.name,
        archive_path=raw / f"{FIXTURE.name}.tgz",
        repo_root=repo,
        archive_url=URL,
        **kwargs,
    )


def test_manifest_records_source_archive_and_metadata(repo: Path) -> None:
    manifest = _build(repo, smoke_frames=2)
    source = manifest["source"]
    assert source["archive_url"] == URL
    assert source["archive_filename"] == f"{FIXTURE.name}.tgz"
    assert source["archive_size_bytes"] == len(b"fake archive bytes")
    assert source["archive_sha256"] == hashlib.sha256(b"fake archive bytes").hexdigest()
    assert manifest["sequence_id"] == FIXTURE.name
    assert manifest["camera"] == "freiburg1"
    assert manifest["depth"]["png_factor_units_per_m"] == 5000.0
    assert manifest["index_files"]["rgb.txt"]["rows"] == 4
    assert manifest["index_files"]["depth.txt"]["sha256"] == sha256_file(FIXTURE / "depth.txt")
    intr = manifest["intrinsics"]
    assert (intr["fx"], intr["fy"], intr["cx"], intr["cy"]) == (517.3, 516.5, 318.6, 255.3)
    assert intr["distortion_correction_applied_by_loader"] is False


def test_associations_and_smoke_split_come_from_c1_loader(repo: Path) -> None:
    manifest = _build(repo, smoke_frames=2)
    frames = tum.load_sequence(FIXTURE)
    assert manifest["association"]["max_delta_s"] == tum.DEFAULT_MAX_ASSOCIATION_DELTA_S
    assert manifest["association"]["num_associations"] == len(frames) == 3
    smoke = manifest["splits"]["smoke"]
    assert smoke["num_frames"] == len(smoke["frames"]) == 2
    assert [
        (row["frame_id"], row["rgb_path"], row["depth_path"], row["depth_timestamp_s"])
        for row in smoke["frames"]
    ] == [
        (f.frame.frame_id, f.frame.image_path, f.gt_depth_path, f.gt_depth_timestamp_s)
        for f in frames[:2]
    ]


def test_too_few_associations_is_rejected(repo: Path) -> None:
    with pytest.raises(ValueError):
        _build(repo, smoke_frames=4)
    with pytest.raises(ValueError):
        _build(repo, smoke_frames=0)


def test_paths_are_repo_relative_and_outside_paths_rejected(repo: Path) -> None:
    manifest = _build(repo, smoke_frames=3)
    assert manifest["extracted_dir"] == f"data/raw/tum_rgbd/{FIXTURE.name}"
    text = dump_manifest(manifest)
    assert str(repo) not in text and repo.as_posix() not in text
    with pytest.raises(ValueError):
        build_tum_manifest(
            sequence_dir=repo / "data" / "raw" / "tum_rgbd" / FIXTURE.name,
            archive_path=repo / "data" / "raw" / "tum_rgbd" / f"{FIXTURE.name}.tgz",
            repo_root=repo / "elsewhere",
            archive_url=URL,
            smoke_frames=3,
        )


def test_manifest_output_is_deterministic(repo: Path) -> None:
    first = dump_manifest(_build(repo, smoke_frames=3))
    second = dump_manifest(_build(repo, smoke_frames=3))
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["schema_version"] == 1
