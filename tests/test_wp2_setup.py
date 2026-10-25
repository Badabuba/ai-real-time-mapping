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
    (seq / "groundtruth.txt").write_text("".join(
        f"{t} 0 0 0 0 0 0.7071 0.7071\n" for t in (0.9, 1.0, 1.1, 1.2, 1.3)))
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
    assert report["groundtruth_poses"] == 5
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
    image = output / "input/000001.png"
    assert image.read_bytes() == (seq / "rgb/1.png").read_bytes()
    if image.is_symlink():
        assert image.resolve() == seq / "rgb/1.png"
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

# Y-04: the same baseline over frozen development/selection/held-out inputs.
from rt_mapping.data.manifest import build_tum_split_manifest
from rt_mapping.slam.setup import load_setup_config, resolve_frame_count


def freeze_split(dataset, split="development", count=None, camera="freiburg1"):
    root, seq, archive, config = dataset
    if camera != "freiburg1":
        new_seq = seq.with_name(seq.name.replace("freiburg1", camera))
        seq.rename(new_seq)
        seq = new_seq
        archive = seq.with_suffix(".tgz")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(seq, arcname=seq.name)
        config.update(sequence_dir=str(seq.relative_to(root)), archive=str(archive.relative_to(root)))
    manifest = build_tum_split_manifest(seq, archive, root, "https://example.invalid/tum.tgz", split, count)
    config["split"] = split
    (root / config["dataset_manifest"]).write_text(json.dumps(manifest))
    return root, seq, archive, config


def fake_source(root, monkeypatch):
    source = root / "external/pyslam"
    (source / "settings").mkdir(parents=True)
    (source / "settings/TUM1.yaml").write_text(
        "Camera.fx: 999\nCamera.k1: 0.262383\nCamera.k2: -0.953104\nCamera.k3: 1.163314\n"
        "Camera.p1: -0.005358\nCamera.p2: 0.002628\nCamera.width: 640\nCamera.height: 480\n"
        "FrozenAlgorithmParameter: 123\n")
    (source / "settings/TUM2.yaml").write_text(
        "Camera.k1: 0.231222\nCamera.k2: -0.784899\nCamera.p1: -0.003257\nCamera.p2: -0.000105\n"
        "Camera.k3: 0.917205\nFrozenAlgorithmParameter: 999\n")
    (source / "settings/TUM3.yaml").write_text(
        "Camera.k1: 0.0\nCamera.k2: 0.0\nCamera.p1: 0.0\nCamera.p2: 0.0\nFrozenAlgorithmParameter: 999\n")
    monkeypatch.setattr("rt_mapping.slam.setup.inspect_source", lambda *a: {"revision_matches": True, "dirty": False})
    return source


@pytest.mark.parametrize("split", ["development", "selection", "held-out"])
def test_split_verification_rebuilds_frozen_input_hashes_and_preserves_data(dataset, split):
    root, seq, _, config = freeze_split(dataset, split, count=2)
    before = {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}
    manifest_before = (root / config["dataset_manifest"]).read_bytes()
    report = verify_dataset(root, config, full=True)
    assert report["status"] == "ok" and report["split"] == split
    assert report["split_frames"] == 2 and report["associations"] == 3
    assert report["selected_input_hashes_verified"] == 4
    assert report["extracted_files_verified"] == 9
    assert before == {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}
    assert manifest_before == (root / config["dataset_manifest"]).read_bytes()


@pytest.mark.parametrize("kind", ["rgb", "depth"])
def test_split_verification_detects_selected_image_byte_changes(dataset, kind):
    root, seq, _, config = freeze_split(dataset, "selection", count=2)
    image = seq / f"{kind}/0.png"
    data = image.read_bytes()
    image.write_bytes(data[:-1]+bytes([data[-1]^1]))  # header remains valid
    with pytest.raises(ValueError, match="frozen dataset manifest"):
        verify_dataset(root, config)


@pytest.mark.parametrize("case", ["split", "count", "frame_id", "sequence", "hash"])
def test_malformed_or_mismatched_frozen_split_is_rejected(dataset, case):
    root, _, _, config = freeze_split(dataset, "development", count=2)
    path = root/config["dataset_manifest"]
    value = json.loads(path.read_text())
    if case == "split":
        config["split"] = "held-out"
    elif case == "count":
        value["splits"]["development"]["num_frames"] = 3
    elif case == "frame_id":
        value["splits"]["development"]["frames"][0]["frame_id"] = 9
    elif case == "sequence":
        value["sequence_id"] = "rgbd_dataset_freiburg2_wrong"
    else:
        value["splits"]["development"]["frames"][0]["rgb_sha256"] = "0"*64
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        verify_dataset(root, config)


def test_all_frames_means_configured_split_not_whole_sequence(dataset, monkeypatch):
    root, seq, _, config = freeze_split(dataset, "selection", count=2)
    source = fake_source(root, monkeypatch)
    assert resolve_frame_count(root, config, None) == 2
    assert resolve_frame_count(root, config, 2) == 2
    for invalid in (0, 1, True, -1, 3):
        with pytest.raises(ValueError):
            resolve_frame_count(root, config, invalid)
    output = root / "outputs/wp2/all"
    plan = prepare_baseline(root, source, output, config, frames=None)
    assert len(plan["frames"]) == 2
    assert len(list((output/"input").glob("*.png"))) == 2
    assert not (output/"input/000002.png").exists()
    assert not (output/"trajectory").exists()  # prepare never runs SLAM


@pytest.mark.parametrize("camera,k1,k3,fx", [
    ("freiburg1", 0.262383, 1.163314, 517.3),
    ("freiburg2", 0.231222, 0.917205, 520.9),
    ("freiburg3", 0., 0., 535.4),
])
def test_camera_calibration_changes_without_algorithm_changes(dataset, monkeypatch, camera, k1, k3, fx):
    import yaml
    root, _, _, config = freeze_split(dataset, "held-out", camera=camera)
    source = fake_source(root, monkeypatch)
    output = root / "outputs/wp2/camera"
    plan = prepare_baseline(root, source, output, config, frames=None)
    settings = yaml.safe_load((output/"camera.yaml").read_text())
    assert settings["Camera.fx"] == fx
    assert settings["Camera.k1"] == k1 and settings["Camera.k3"] == k3
    assert settings["FrozenAlgorithmParameter"] == 123
    assert settings["Camera.RGB"] == 0
    assert len(plan["frames"]) == 3 and plan["status"] == "prepared_not_run"
    assert all(p.suffix == ".png" or p.name == "times.txt" for p in (output/"input").iterdir())


def test_committed_configs_change_dataset_fields_only():
    root = Path(__file__).resolve().parents[1]
    baseline = load_setup_config(root/"configs/wp2_pyslam_baseline.json")
    allowed = {"dataset_manifest", "sequence_dir", "archive", "split"}
    expected = {"development": ("development",573), "selection": ("selection",50), "heldout": ("held-out",2488)}
    for suffix, (split, count) in expected.items():
        config = load_setup_config(root/f"configs/wp2_pyslam_{suffix}.json")
        assert {k:v for k,v in config.items() if k not in allowed} == {
            k:v for k,v in baseline.items() if k not in allowed}
        assert config["split"] == split
        assert resolve_frame_count(root, config, None) == count
        manifest=json.loads((root/config["dataset_manifest"]).read_text())
        assert config["sequence_dir"] == manifest["extracted_dir"]
        assert Path(config["archive"]).name == manifest["source"]["archive_filename"]


def load_cli(name):
    import importlib.util
    path = Path(__file__).resolve().parents[1]/"scripts"/(name+".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cli_config(root, config):
    path = root/"wp2_config.json"
    path.write_text(json.dumps({**config, "schema":"rt_mapping.wp2_setup/v1", "sensor_type":"mono"}))
    return path


def test_run_cli_resolves_all_frames_before_calling_runner(dataset, monkeypatch):
    import sys
    root, _, _, config = freeze_split(dataset, "selection", count=2)
    path = cli_config(root, config)
    module = load_cli("run_wp2_pyslam")
    monkeypatch.setattr(module, "ROOT", root)
    calls=[]
    def fake_run(*args, **kwargs):
        calls.append((args,kwargs))
        directory=root/"result"
        directory.mkdir()
        (directory/"run.json").write_text(json.dumps({"status":"ok", "reason":None}))
        return directory
    monkeypatch.setattr(module, "run_smoke", fake_run)
    monkeypatch.setattr(sys, "argv", ["run_wp2_pyslam.py", "--config", str(path), "--all-frames"])
    assert module.main() == 0
    assert calls[0][1]["frames"] == 2
    assert calls[0][1]["run_id"].startswith("yaropolk_b0_")
    assert "fr1_xyz" not in calls[0][1]["run_id"]


def test_run_cli_preserves_default_200_and_forbids_conflicting_flags(monkeypatch, tmp_path):
    import sys
    module=load_cli("run_wp2_pyslam")
    calls=[]
    monkeypatch.setattr(module,"resolve_frame_count",lambda root,config,frames: calls.append(frames) or frames)
    def fake_run(*a,**kw):
        directory=tmp_path/"default"
        directory.mkdir()
        (directory/"run.json").write_text(json.dumps({"status":"ok","reason":None}))
        return directory
    monkeypatch.setattr(module,"run_smoke",fake_run)
    monkeypatch.setattr(sys,"argv",["run_wp2_pyslam.py"])
    assert module.main()==0 and calls==[200]
    monkeypatch.setattr(sys,"argv",["run_wp2_pyslam.py","--frames","2","--all-frames"])
    with pytest.raises(SystemExit) as exc:module.main()
    assert exc.value.code==2


def test_prepare_cli_all_frames_writes_rgb_view_only(dataset, monkeypatch):
    import sys
    root, _, _, config = freeze_split(dataset, "held-out", count=2)
    path=cli_config(root,config)
    source=fake_source(root,monkeypatch)
    module=load_cli("prepare_wp2_baseline")
    monkeypatch.setattr(module,"ROOT",root)
    output=root/"outputs/wp2/heldout_preflight"
    monkeypatch.setattr(sys,"argv",["prepare_wp2_baseline.py","--config",str(path),"--all-frames",
                                    "--pyslam-root",str(source),"--output",str(output)])
    assert module.main()==0
    assert len(list((output/"input").glob("*.png")))==2
    assert not (output/"trajectory").exists()



def test_preflight_reports_official_style_duplicate_gt_without_fitting(dataset):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text(
        "0.9 0 0 0 0 0 0 1\n0.9 0.001 0 0 0 0 0 1\n1.1 0 0 0 0 0 0 1\n1.3 0 0 0 0 0 0 1\n")
    before = (seq / "groundtruth.txt").read_bytes()
    report = verify_dataset(root, config)
    assert report["status"] == "ok"
    assert report["groundtruth_duplicate_timestamp_pairs"] == 1
    assert any("duplicates" in reason for reason in report["limitations"])
    assert (seq / "groundtruth.txt").read_bytes() == before


def test_preflight_still_rejects_decreasing_gt_timestamps(dataset):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text(
        "0.9 0 0 0 0 0 0 1\n0.8 0 0 0 0 0 0 1\n1.3 0 0 0 0 0 0 1\n")
    with pytest.raises(ValueError, match="nondecreasing"):
        verify_dataset(root, config)


@pytest.mark.parametrize("start,end", [(1.05, 1.3), (0.9, 1.15), (1.05, 1.15)])
def test_preflight_reports_gt_boundary_gaps_without_changing_inputs(dataset, start, end):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text(
        f"{start} 0 0 0 0 0 0 1\n1.1 0 0 0 0 0 0 1\n{end} 0 0 0 0 0 0 1\n")
    before = {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}
    report = verify_dataset(root, config)
    assert report["status"] == "ok"
    assert report["associations"] == 3
    assert report["associated_rgb_frames_outside_gt_time_range"] == (2 if start > 1 and end < 1.2 else 1)
    assert any("beyond the GT time range" in reason for reason in report["limitations"])
    assert before == {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}


@pytest.mark.parametrize("start,end", [(0.8, 0.9), (1.3, 1.4)])
def test_preflight_rejects_gt_without_time_overlap(dataset, start, end):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text(
        f"{start} 0 0 0 0 0 0 1\n{end} 0 0 0 0 0 0 1\n")
    with pytest.raises(ValueError, match="no_valid_gt_overlap"):
        verify_dataset(root, config)


def test_fr3_partial_gt_preflight_and_preparation_retain_every_frozen_rgb(dataset, monkeypatch):
    root, seq, _, _ = dataset
    stamps = [1341847980.722988, 1341847980.754743, 1341847980.786856]
    (seq / "rgb.txt").write_text("".join(f"{t:.6f} rgb/{i}.png\n" for i, t in enumerate(stamps)))
    (seq / "depth.txt").write_text("".join(f"{t+.00001:.6f} depth/{i}.png\n" for i, t in enumerate(stamps)))
    (seq / "groundtruth.txt").write_text(
        "1341847980.7900 0 0 0 0 0 0 1\n1341847980.8000 0 0 0 0 0 0 1\n")
    root, seq, _, config = freeze_split(dataset, "held-out", camera="freiburg3")
    before = {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}
    original_config = copy.deepcopy(config)
    report = verify_dataset(root, config, full=True)
    assert report["rgb_frames"] == report["split_frames"] == 3
    coverage = report["gt_coverage"]
    assert coverage["total_rgb_frames"] == 3 and coverage["matched_gt_frames"] == 1
    assert coverage["unmatched_gt_frames"] == 2
    assert coverage["coverage_percent"] == pytest.approx(100/3)
    assert coverage["excluded_frame_ids"] == [0, 1]
    assert report["associated_rgb_frames_outside_gt_time_range"] == 3
    source = fake_source(root, monkeypatch)
    output = root / "outputs/wp2/fr3_partial"
    plan = prepare_baseline(root, source, output, config, frames=None)
    assert [f["frame_id"] for f in plan["frames"]] == [0, 1, 2]
    assert len(list((output / "input").glob("*.png"))) == 3
    assert [float(t) for t in (output / "input/times.txt").read_text().split()] == stamps
    assert config == original_config
    assert before == {p: p.read_bytes() for p in seq.rglob("*") if p.is_file()}


def test_overlapping_gt_endpoints_without_a_20_ms_match_fail_with_coverage(dataset):
    root, seq, _, config = dataset
    # Time ranges overlap, but there is no GT sample within 20 ms of any input.
    (seq / "groundtruth.txt").write_text("0.9 0 0 0 0 0 0 1\n1.3 0 0 0 0 0 0 1\n")
    with pytest.raises(ValueError, match="no_valid_gt_overlap") as error:
        verify_dataset(root, config)
    coverage = error.value.coverage
    assert coverage["total_rgb_frames"] == 2  # frozen smoke prefix, not raw index
    assert coverage["matched_gt_frames"] == 0 and coverage["coverage_percent"] == 0
    assert coverage["excluded_frame_ids"] == [0, 1]


def test_duplicate_gt_inside_evaluated_interval_is_not_silently_deduplicated(dataset):
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text(
        "1.0 0 0 0 0 0 0 1\n1.0 1 0 0 0 0 0 1\n1.1 0 0 0 0 0 0 1\n")
    with pytest.raises(ValueError, match="ambiguous GT"):
        verify_dataset(root, config)


def test_dataset_cli_reports_excluded_ids_on_zero_gt_overlap(dataset, monkeypatch, capsys):
    import sys
    root, seq, _, config = dataset
    (seq / "groundtruth.txt").write_text("0.9 0 0 0 0 0 0 1\n1.3 0 0 0 0 0 0 1\n")
    path = cli_config(root, config)
    module = load_cli("check_wp2_environment")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["check_wp2_environment.py", "--config", str(path), "--dataset-only"])
    assert module.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed" and "no_valid_gt_overlap" in report["reason"]
    assert report["gt_coverage"]["raw_rgb_index_frames"] == 3
    assert report["gt_coverage"]["excluded_frame_ids"] == [0, 1]
