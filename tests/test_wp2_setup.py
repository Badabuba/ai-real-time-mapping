"""WP2 setup correctness: real PNG/tar fixtures, no installed SLAM or model weights."""
from __future__ import annotations

import copy
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rt_mapping.data.manifest import build_tum_manifest
from rt_mapping.slam.setup import prepare_baseline, verify_dataset, verify_extracted_archive


@pytest.fixture
def dataset(tmp_path):
    seq = tmp_path / "data/raw/tum_rgbd/rgbd_dataset_freiburg1_mini"
    (seq / "rgb").mkdir(parents=True)
    (seq / "depth").mkdir()
    rgb, depth = [], []
    for i in range(3):
        Image.fromarray(np.zeros((480, 640, 3), np.uint8)).save(seq / f"rgb/{i}.png")
        Image.fromarray(np.full((480, 640), 5000, np.uint16)).save(seq / f"depth/{i}.png")
        rgb.append(f"{1+i*0.1:.6f} rgb/{i}.png\n")
        depth.append(f"{1+i*0.1+0.005:.6f} depth/{i}.png\n")
    (seq / "rgb.txt").write_text("".join(rgb))
    (seq / "depth.txt").write_text("".join(depth))
    # Four-decimal quaternion rounding: not exactly unit length, valid TUM precision.
    (seq / "groundtruth.txt").write_text("0.9 0 0 0 0 0 0.7071 0.7071\n1.3 0 0 0 0 0 0.7071 0.7071\n")
    archive = seq.with_suffix(".tgz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(seq, arcname=seq.name)
    manifest = build_tum_manifest(seq, archive, tmp_path, "https://example.invalid/tum.tgz", smoke_frames=2)
    manifest_path = tmp_path / "data/manifests/mini.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(manifest))
    config = {"sequence_dir": str(seq.relative_to(tmp_path)), "archive": str(archive.relative_to(tmp_path)),
              "dataset_manifest": str(manifest_path.relative_to(tmp_path)), "split": "smoke",
              "upstream": {"revision": "a" * 40}, "feature_tracker": "ORB2", "num_features": 1000,
              "loop_detector": "DBOW3", "use_cpp_core": False, "seed": 0}
    return tmp_path, seq, archive, config


def test_full_verification_checks_real_archive_and_rounded_gt(dataset):
    root, seq, archive, config = dataset
    before = {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}
    report = verify_dataset(root, config, full=True)
    assert report["status"] == "ok"
    assert report["rgb_frames"] == report["depth_frames"] == report["associations"] == 3
    assert report["groundtruth_poses"] == 2
    assert report["extracted_files_verified"] == 9
    assert before == {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}


def test_corrupted_extracted_image_is_detected(dataset):
    _, seq, archive, _ = dataset
    path = seq / "rgb/0.png"
    data = path.read_bytes()
    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError, match="contents differ"):
        verify_extracted_archive(archive, seq)


def test_wrong_archive_is_rejected(dataset):
    root, _, archive, config = dataset
    archive.write_bytes(b"wrong archive")
    with pytest.raises(ValueError, match="frozen dataset manifest"):
        verify_dataset(root, config)


def test_bad_gt_rotation_is_rejected(dataset):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text("0.9 0 0 0 0 0 0 0\n1.3 0 0 0 0 0 0 1\n")
    with pytest.raises(ValueError, match="quaternion"):
        verify_dataset(root, config)


def test_unsafe_tar_member_is_rejected(tmp_path):
    import io
    seq = tmp_path / "sequence"
    seq.mkdir()
    archive = tmp_path / "unsafe.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("sequence/../../outside")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe archive"):
        verify_extracted_archive(archive, seq)


def test_prepared_view_preserves_timestamps_ids_and_excludes_gt(dataset, monkeypatch):
    import yaml
    root, seq, _, config = dataset
    source = root / "external/pyslam"
    (source / "settings").mkdir(parents=True)
    (source / "settings/TUM1.yaml").write_text("Camera.fx: 999\nCamera.k1: 0.262383\nCamera.width: 640\nCamera.height: 480\n")
    monkeypatch.setattr("rt_mapping.slam.setup.inspect_source", lambda *args: {"revision_matches": True, "dirty": False})
    output = root / "outputs/wp2/smoke"
    original = copy.deepcopy(config)
    plan = prepare_baseline(root, source, output, config, frames=2)
    assert config == original
    assert plan["status"] == "prepared_not_run"
    assert plan["python_flags"] == ["-O"]
    assert [f["frame_id"] for f in plan["frames"]] == [0, 1]
    assert sorted(p.name for p in (output / "input").iterdir()) == ["000000.png", "000001.png", "times.txt"]
    assert (output / "input/000001.png").resolve() == seq / "rgb/1.png"
    assert [float(s) for s in (output / "input/times.txt").read_text().split()] == [1, 1.1]
    cfg = yaml.safe_load((output / "pyslam.yaml").read_text())
    assert cfg["FOLDER_DATASET"]["sensor_type"] == "mono"
    assert "groundtruth_file" not in cfg["FOLDER_DATASET"]
    assert cfg["GLOBAL_PARAMETERS"]["kUseDepthEstimatorInFrontEnd"] is False
    assert cfg["GLOBAL_PARAMETERS"]["kDoVolumetricIntegration"] is False
    camera = yaml.safe_load((output / "camera.yaml").read_text())
    assert camera["Camera.fx"] == 517.3 and camera["Camera.RGB"] == 0
    assert camera["LoopDetectionConfig.name"] == "DBOW3"
    before = (output / "setup.json").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        prepare_baseline(root, source, output, config, frames=2)
    assert (output / "setup.json").read_bytes() == before


def test_preparation_rejects_unpinned_source_without_writing(dataset, monkeypatch):
    root, _, _, config = dataset
    monkeypatch.setattr("rt_mapping.slam.setup.inspect_source", lambda *args: {"revision_matches": False, "dirty": False})
    output = root / "outputs/wp2/rejected"
    with pytest.raises(ValueError, match="pinned"):
        prepare_baseline(root, root / "external/pyslam", output, config, frames=2)
    assert not output.exists()


def test_runtime_probe_preserves_virtual_environment_interpreter(tmp_path):
    import os
    import venv
    from rt_mapping.slam.setup import probe_runtime

    env = tmp_path / "runtime"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(env)
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    source = tmp_path / "upstream"
    source.mkdir()
    (source / "main_slam.py").write_text(
        f"import sys\nassert sys.prefix == {str(env)!r}, (sys.prefix, sys.base_prefix)\n"
    )
    result = probe_runtime(python, source)
    assert result["status"] == "ok", result
