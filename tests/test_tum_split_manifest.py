"""Frozen frame identities and byte hashes, independent of GPU backends."""

from pathlib import Path
import json
import re
import shutil

import pytest

from rt_mapping.data.manifest import build_tum_split_manifest, dump_manifest, sha256_file


def inputs(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures/rgbd_dataset_freiburg1_mini"
    seq = tmp_path / fixture.name
    shutil.copytree(fixture, seq)
    # Index-only fixture: supply small byte payloads to exercise content hashes.
    for name in ("rgb.txt", "depth.txt"):
        for line in (seq / name).read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            relative = line.split()[1]
            target = seq / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(relative.encode())
    archive = tmp_path / "fixture.tgz"
    archive.write_bytes(b"archive")
    return seq, archive


def test_freeze_exact_prefix_and_detect_content_changes(tmp_path):
    seq, archive = inputs(tmp_path)
    kwargs = dict(sequence_dir=seq, archive_path=archive, repo_root=tmp_path,
                  archive_url="https://example.invalid/fixture.tgz", split="selection", num_frames=2)
    one = build_tum_split_manifest(**kwargs)
    assert set(one["splits"]) == {"selection"}
    rows = one["splits"]["selection"]["frames"]
    assert [row["frame_id"] for row in rows] == [0, 1]
    assert rows[0]["rgb_sha256"] == sha256_file(seq / rows[0]["rgb_path"])
    assert dump_manifest(one) == dump_manifest(build_tum_split_manifest(**kwargs))
    (seq / rows[0]["rgb_path"]).write_bytes(b"changed")
    assert dump_manifest(one) != dump_manifest(build_tum_split_manifest(**kwargs))


def test_whole_sequence_and_invalid_requests(tmp_path):
    seq, archive = inputs(tmp_path)
    args = (seq, archive, tmp_path, "https://example.invalid/fixture.tgz")
    whole = build_tum_split_manifest(*args, "held-out")
    assert whole["splits"]["held-out"]["num_frames"] == 3
    for count in (0, True, -1, 4):
        with pytest.raises(ValueError):
            build_tum_split_manifest(*args, "selection", count)
    with pytest.raises(ValueError):
        build_tum_split_manifest(*args, "training", 2)


MANIFESTS = Path(__file__).resolve().parents[1] / "data/manifests"
# name -> (sequence_id, splits key, frames, associations in the full sequence)
FROZEN = {
    "tum_fr1_desk_development": ("rgbd_dataset_freiburg1_desk", "development", 573, 573),
    "tum_fr1_desk_spike50": ("rgbd_dataset_freiburg1_desk", "development", 50, 573),
    "tum_fr2_desk_selection50": ("rgbd_dataset_freiburg2_desk", "selection", 50, 2893),
    "tum_fr3_long_office_heldout": (
        "rgbd_dataset_freiburg3_long_office_household", "held-out", 2488, 2488),
}
SHA256 = re.compile(r"[0-9a-f]{64}")


def load(name):
    return json.loads((MANIFESTS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_committed_frozen_manifest_roles_and_portable_paths(name):
    sequence_id, split, count, associations = FROZEN[name]
    text = (MANIFESTS / f"{name}.json").read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert manifest["sequence_id"] == sequence_id
    assert manifest["extracted_dir"] == f"data/raw/tum_rgbd/{sequence_id}"
    assert manifest["source"]["archive_filename"] == f"{sequence_id}.tgz"
    assert manifest["source"]["archive_url"].startswith("https://")
    assert SHA256.fullmatch(manifest["source"]["archive_sha256"])
    assert all(SHA256.fullmatch(meta["sha256"]) for meta in manifest["index_files"].values())
    assert manifest["association"]["num_associations"] == associations
    assert list(manifest["splits"]) == [split]
    frozen = manifest["splits"][split]
    assert frozen["num_frames"] == count == len(frozen["frames"])
    assert [row["frame_id"] for row in frozen["frames"]] == list(range(count))
    for row in frozen["frames"]:
        for key in ("rgb_path", "depth_path"):
            assert "\\" not in row[key] and not row[key].startswith("/")
        assert SHA256.fullmatch(row["rgb_sha256"]) and SHA256.fullmatch(row["depth_sha256"])
    # No drive letters, UNC paths or home directories anywhere in the file.
    assert "\\" not in text
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:/|/home/|/Users/", text)


def test_spike50_is_exact_development_prefix():
    development = load("tum_fr1_desk_development")
    spike = load("tum_fr1_desk_spike50")
    assert spike["source"] == development["source"]
    assert spike["index_files"] == development["index_files"]
    assert spike["splits"]["development"]["frames"] == (
        development["splits"]["development"]["frames"][:50])
