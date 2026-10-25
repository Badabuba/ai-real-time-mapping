"""Sparse handoff correctness: geometry, pixel grids, IDs and forced-exit lifecycle."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from threading import RLock
from types import SimpleNamespace

import numpy as np
import pytest

from rt_mapping.slam.pyslam_export import collect_pyslam_snapshot, install_shutdown_export
from rt_mapping.slam.smoke import upstream_bootstrap
from rt_mapping.slam.sparse import check_sparse_export, validate_snapshot, write_sparse_snapshot


class FixtureSlam(SimpleNamespace):
    def quit(self):
        self.has_quit = True
        self.quit_calls += 1


def make_slam(cls=FixtureSlam):
    """A rotated/translated world; dataset IDs differ from backend frame IDs."""
    first = np.array([[0., -1, 0, 2], [1, 0, 0, 3], [0, 0, 1, 1], [0, 0, 0, 1]])
    poses = [first.copy(), first.copy()]
    poses[1][:3, 3] += first[:3, :3] @ [0.1, 0, 0]
    camera = SimpleNamespace(K=np.array([[100., 0, 320], [0, 100, 240], [0, 0, 1]]),
                             D=np.array([0.1, 0, 0, 0, 0]), width=640, height=480)
    points = []
    for pid, xyz in ((8, [0.2, 0.1, 2.]), (19, [0.5, -0.1, 3.])):
        world = (first @ np.r_[xyz, 1])[:3]
        points.append(SimpleNamespace(id=pid, pt=lambda w=world: w.copy(), is_bad=lambda: False))
    keyframes = []
    for uid, kid, timestamp, pose in zip((100, 200), (0, 4), (1., 1.1), poses):
        uv = []
        for point in points:
            pc = pose[:3, :3].T @ (point.pt() - pose[:3, 3])
            projected = camera.K @ pc
            uv.append(projected[:2] / projected[2] + [0.3, 0.4])
        uv = np.array(uv)
        keyframes.append(SimpleNamespace(id=uid, kid=kid, timestamp=timestamp, camera=camera,
            Twc=lambda p=pose: p.copy(), is_bad=lambda: False, kpsu=uv,
            kps=uv + [1.5, -0.75], get_point_match=lambda i: points[i]))
    for index, point in enumerate(points):
        point.observations = lambda i=index: [(kf, i) for kf in keyframes]
    map_ = SimpleNamespace(update_lock=RLock(), get_first_keyframe=lambda: keyframes[0],
                           get_keyframes=lambda: list(reversed(keyframes)),
                           get_points=lambda: list(reversed(points)))
    slam = cls(map=map_, has_quit=True, quit_calls=0, local_mapping=None, loop_closing=None,
               semantic_mapping=None, volumetric_integrator=None, GBA=None, GBA_on_demand=None)
    frames = [{"frame_id": 10, "rgb_timestamp_s": 1.}, {"frame_id": 27, "rgb_timestamp_s": 1.1}]
    return slam, frames


@pytest.fixture
def snapshot():
    return collect_pyslam_snapshot(*make_slam())


def test_normalization_ids_and_distorted_pixels(snapshot):
    validate_snapshot(snapshot)
    np.testing.assert_allclose(snapshot.landmarks["xyz_slam"], [[0.2, 0.1, 2], [0.5, -0.1, 3]])
    np.testing.assert_allclose(snapshot.keyframes["T_wc"][0], np.eye(4))
    np.testing.assert_allclose(snapshot.keyframes["T_wc"][1, :3, 3], [0.1, 0, 0], atol=1e-12)
    assert snapshot.keyframes["frame_id"].tolist() == [10, 27]
    assert snapshot.keyframes["upstream_frame_id"].tolist() == [100, 200]
    assert snapshot.landmarks["observation_count"].tolist() == [2, 2]
    for row in snapshot.observations:
        assert row["u"] - row["u_undistorted"] == pytest.approx(1.5)
        assert row["v"] - row["v_undistorted"] == pytest.approx(-0.75)
        assert row["reprojection_error_px"] == pytest.approx(0.5)


def test_export_roundtrip_and_no_overwrite(tmp_path, snapshot):
    out = tmp_path / "sparse"
    metadata = write_sparse_snapshot(out, snapshot)
    assert check_sparse_export(out) == metadata
    assert metadata["counts"] == {"landmarks": 2, "keyframes": 2, "observations": 4}
    assert "not meters" in metadata["units"]
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError):
        write_sparse_snapshot(out, snapshot)
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}
    text = (out / "sparse_map.ply").read_text().split("end_header\n")[1]
    np.testing.assert_allclose(np.loadtxt(text.splitlines()), snapshot.landmarks["xyz_slam"])


@pytest.mark.parametrize("change, message", [
    (lambda s: s.observations[0].update(point_id=999), "dangling"),
    (lambda s: s.observations[0].update(frame_id=999), "frame/keyframe"),
    (lambda s: s.observations[0].update(reprojection_error_px=42.), "reprojection"),
    (lambda s: s.observations[0].update(depth_slam=-1.), "camera depth"),
    (lambda s: s.observations[0].update(u=640.), "outside image"),
    (lambda s: s.landmarks["observation_count"].__setitem__(0, 99), "observation_count"),
    (lambda s: s.landmarks["xyz_slam"].__setitem__((0, 0), np.nan), "finite array"),
    (lambda s: s.keyframes["T_wc"].__setitem__((0, 0, 0), 2.), "rigid"),
    (lambda s: s.observations.append(copy.deepcopy(s.observations[0])), "duplicate"),
])
def test_invalid_links_rejected_before_writing(tmp_path, snapshot, change, message):
    change(snapshot)
    out = tmp_path / "sparse"
    with pytest.raises(ValueError, match=message):
        write_sparse_snapshot(out, snapshot)
    assert not out.exists()


def test_corruption_rejected(tmp_path, snapshot):
    write_sparse_snapshot(tmp_path / "sparse", snapshot)
    with (tmp_path / "sparse/observations.csv").open("a") as stream:
        stream.write("corrupt\n")
    with pytest.raises(ValueError, match="checksum"):
        check_sparse_export(tmp_path / "sparse")


def test_collection_requires_stopped_workers():
    slam, frames = make_slam()
    slam.has_quit = False
    with pytest.raises(ValueError, match="shutdown"):
        collect_pyslam_snapshot(slam, frames)
    slam.has_quit = True
    slam.local_mapping = SimpleNamespace(work_thread=SimpleNamespace(is_alive=lambda: True))
    with pytest.raises(ValueError, match="active"):
        collect_pyslam_snapshot(slam, frames)


def test_timestamp_mapping_and_backlinks_are_not_guessed():
    slam, frames = make_slam()
    frames[0]["rgb_timestamp_s"] = 0.9
    with pytest.raises(ValueError, match="uniquely match"):
        collect_pyslam_snapshot(slam, frames)
    slam, frames = make_slam()
    slam.map.get_first_keyframe().get_point_match = lambda _: None
    with pytest.raises(ValueError, match="backlink"):
        collect_pyslam_snapshot(slam, frames)


def test_nonretained_views_are_counted():
    slam, frames = make_slam()
    first = slam.map.get_first_keyframe()
    slam.map.get_keyframes = lambda: [first]
    snapshot = collect_pyslam_snapshot(slam, frames)
    validate_snapshot(snapshot)
    assert snapshot.landmarks["observation_count"].tolist() == [1, 1]
    assert snapshot.metadata["skipped"]["observations_of_nonretained_keyframes"] == 2


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("relative_paths", [False, True])
def test_bootstrap_survives_upstream_forced_exit(tmp_path, monkeypatch, enabled, relative_paths):
    """A real child os._exit proves export happens before runpy can return."""
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "fake_upstream"
    package = source / "pyslam/slam"
    package.mkdir(parents=True)
    (source / "pyslam/__init__.py").write_text("")
    (source / "pyslam/config.py").write_text("class Config:\n    pass\n")
    (package / "__init__.py").write_text("")
    (package / "slam.py").write_text(
            f"import runpy, sys\nsys.path.insert(0, {str(root / 'src')!r})\n"
            f"n = runpy.run_path({str(Path(__file__).resolve())!r})\n"
        "class Slam(n['FixtureSlam']):\n    pass\nmake_slam = n['make_slam']\n")
    (source / "cv2.py").write_text("def setRNGSeed(seed):\n    pass\n")
    entry = source / "main_slam.py"
    entry.write_text("import os\nfrom pyslam.slam.slam import Slam, make_slam\n"
                     "slam, frames = make_slam(Slam)\nslam.has_quit = False\n"
                     "slam.quit()\nslam.quit()\nos._exit(0)\n")
    run = tmp_path / "run"
    prep = run / "input_setup"
    prep.mkdir(parents=True)
    (prep / "setup.json").write_text(json.dumps({"frames": make_slam()[1]}))
    monkeypatch.chdir(tmp_path)
    code = upstream_bootstrap(root, prep.relative_to(tmp_path) if relative_paths else prep,
                              run.relative_to(tmp_path) if relative_paths else run,
                              seed=0, export_sparse=enabled)
    done = subprocess.run([sys.executable, "-c", code, str(entry)], cwd=source,
                          capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stdout + done.stderr
    if enabled:
        assert check_sparse_export(run / "sparse")["counts"]["observations"] == 4
    else:
        assert not (run / "sparse").exists()


@pytest.mark.parametrize("enabled", [False, True])
def test_runner_records_sparse_artifacts_only_when_requested(tmp_path, monkeypatch, snapshot, enabled):
    from rt_mapping.slam import smoke
    root = tmp_path
    frames = make_slam()[1]
    config = {"upstream": {"revision": "a" * 40, "repo": "https://example.invalid/pyslam"},
              "seed": 0, "dataset_manifest": "manifest.json", "split": "smoke"}
    (root / "manifest.json").write_text(json.dumps({"splits": {"smoke": {"frames": frames}}}))
    interpreter = root / "python"
    interpreter.touch()
    monkeypatch.setattr(smoke, "verify_dataset", lambda *a: {"sequence": "synthetic",
                                                           "archive_sha256": "b" * 64})
    monkeypatch.setattr(smoke, "inspect_source", lambda *a: {"status": "ok"})

    def metadata(argv, **kwargs):
        if "rev-parse" in argv:
            return "a" * 40
        if "status" in argv:
            return ""
        return json.dumps({"python": "3.11.16", "numpy": "1.26.4", "torch": "2.6.0",
                           "opencv_python": "4.11.0", "ram_gb": 32.})

    monkeypatch.setattr(smoke.subprocess, "check_output", metadata)

    def prepare(root, source, output, config, **kwargs):
        trajectory = output / "trajectory"
        trajectory.mkdir(parents=True)
        np.savetxt(trajectory / "trajectory_final.txt", [[1., 0, 0, 0, 0, 0, 0, 1],
                                                        [1.1, 1, 0, 0, 0, 0, 0, 1]])
        (trajectory / "other_metrics_info.txt").write_text(
            "num_total_frames: 2\nnum_processed_frames: 2\nnum_lost_frames: 0\n")
        return {"frames": frames, "python_flags": [], "argv_after_python": ["main_slam.py"]}

    def execute(argv, **kwargs):
        assert kwargs["env"]["PYTHONHASHSEED"] == "0"
        compile(argv[2], "bootstrap", "exec")
        if enabled:
            write_sparse_snapshot(root / "results/runs/test_sparse/sparse", snapshot)
        return 0

    monkeypatch.setattr(smoke, "prepare_baseline", prepare)
    monkeypatch.setattr(smoke, "execute_upstream", execute)
    run = smoke.run_smoke(root, root, interpreter, config, run_id="test_sparse", frames=2,
                          export_sparse=enabled, export_tracking=False)
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["status"] == "ok", manifest["reason"]
    assert manifest["config"]["export_sparse"] is enabled
    assert ("landmarks" in manifest["artifacts"]) is enabled
