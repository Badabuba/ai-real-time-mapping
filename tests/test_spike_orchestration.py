import json
from pathlib import Path

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.data.manifest import build_tum_manifest, dump_manifest, sha256_file
from rt_mapping.runs.geometry_run import RunSpec, GitState, HostInfo, run_geometry_benchmark


def test_prewarm_is_separate_and_frozen_content_is_verified(tmp_path):
    from PIL import Image
    seq = tmp_path / "rgbd_dataset_freiburg1_synth"
    (seq / "rgb").mkdir(parents=True)
    (seq / "depth").mkdir()
    for i in range(2):
        Image.fromarray(np.zeros((480, 640, 3), np.uint8)).save(seq / f"rgb/{i}.png")
        Image.fromarray(np.full((480, 640), 10000, np.uint16)).save(seq / f"depth/{i}.png")
    (seq / "rgb.txt").write_text("1.0 rgb/0.png\n2.0 rgb/1.png\n")
    (seq / "depth.txt").write_text("1.001 depth/0.png\n2.001 depth/1.png\n")
    archive = tmp_path / "fixture.tgz"
    archive.write_bytes(b"fixture")
    manifest = build_tum_manifest(seq, archive, tmp_path, "https://example.invalid/a", smoke_frames=2)
    manifest["splits"]["selection"] = manifest["splits"].pop("smoke")
    for entry in manifest["splits"]["selection"]["frames"]:
        entry["rgb_sha256"] = sha256_file(seq / entry["rgb_path"])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(dump_manifest(manifest))

    class Fake:
        calls = 0
        def describe(self):
            return {"model": {"repo": "fake/model", "revision": "a" * 40, "checkpoint": "fake", "dtype": "float32"},
                    "config": {}, "environment": {}, "gpu": "fake"}
        def predict(self, frame):
            self.calls += 1
            # Native prediction is small, but evaluation must use every raw GT-valid pixel.
            return GeometryPrediction(frame.frame_id, frame.timestamp_s, np.full((2, 2), 2., np.float32),
                                      np.ones((2, 2), bool), None, frame.K, "fake", {}, float(self.calls))

    fake = Fake()
    def run(run_id):
        spec = RunSpec(run_id, tmp_path / "results", seq, manifest_path, "data/manifests/fixture.json",
                       "selection", 2, 0, 0, fake.describe()["model"], {}, archive,
                       prewarm_calls=10, evaluation_grid="raw_rgb")
        return run_geometry_benchmark(spec, lambda: fake, git_state=GitState("a" * 40, False),
                                      host_info=HostInfo("fake", None), log=lambda _: None)
    first = run("first")
    assert first.exit_code == 0 and fake.calls == 12
    metrics = json.loads((first.run_dir / "metrics.json").read_text())
    assert metrics["mean"]["n_evaluated"] == 2 * 640 * 480
    assert metrics["mean"]["abs_rel"] == 0
    timing = json.loads((first.run_dir / "timing.json").read_text())
    assert timing["prewarm_samples_ms"] == list(range(1, 11))
    assert timing["cold_inference_ms"] == 1
    (seq / "rgb/0.png").write_bytes(b"changed")
    second = run("changed")
    assert second.status == "failed" and second.reason.startswith("dataset_mismatch:")
    assert fake.calls == 12
