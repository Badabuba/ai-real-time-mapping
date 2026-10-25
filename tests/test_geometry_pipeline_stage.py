"""N-04: scripts/run_geometry_benchmark.py works as a scripts/run_pipeline.py geometry stage.

The launcher appends --run-id/--output-root; the stage must land under the
pipeline's stages/ directory and pass the launcher's completed-artifact check
for either model. Fake adapters replace the GPU backends.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data.manifest import build_tum_manifest, dump_manifest
from rt_mapping.runs import pipeline_run
from rt_mapping.runs.geometry_run import GitState, HostInfo

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_geometry_benchmark.py"
REPOS = {"da3": ("depth-anything/DA3METRIC-LARGE", "4010e39f3634a45bc60553321fb49fb760bd594e"),
         "unidepth": ("lpiccinelli/unidepth-v2-vitl14", "52b349b514bd8b47642f67ac78cb7b5dc5c51dd9")}


def _fake_adapter(model):
    repo, revision = REPOS[model]

    class Fake:
        def __init__(self, config, image_root, backend=None):
            self.config = config

        def describe(self):
            return {"model": {"repo": repo, "revision": revision, "checkpoint": "fake@sha256:" + "0" * 64,
                              "dtype": "float32"}, "config": self.config.to_record(), "environment": {}, "gpu": None}

        def predict(self, frame):
            confidence = np.full((frame.height, frame.width), -0.1, np.float32) if model == "unidepth" else None
            return GeometryPrediction(frame.frame_id, frame.timestamp_s,
                                      np.full((frame.height, frame.width), 2., np.float32),
                                      np.ones((frame.height, frame.width), bool), confidence, frame.K,
                                      f"{repo}@{revision}", {}, 1.)
    return Fake


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from PIL import Image
    root = tmp_path / "repo"
    seq = root / "data/raw/tum_rgbd/rgbd_dataset_freiburg1_synth"
    (seq / "rgb").mkdir(parents=True)
    (seq / "depth").mkdir()
    for i in range(2):
        Image.fromarray(np.zeros((480, 640, 3), np.uint8)).save(seq / f"rgb/{i}.png")
        Image.fromarray(np.full((480, 640), 10000, np.uint16)).save(seq / f"depth/{i}.png")
    (seq / "rgb.txt").write_text("1.0 rgb/0.png\n2.0 rgb/1.png\n")
    (seq / "depth.txt").write_text("1.001 depth/0.png\n2.001 depth/1.png\n")
    archive = root / "data/raw/tum_rgbd/fixture.tgz"
    archive.write_bytes(b"fixture")
    manifest = build_tum_manifest(seq, archive, root, "https://example.invalid/a", smoke_frames=2)
    (root / "data/manifests").mkdir(parents=True)
    (root / "data/manifests/fixture.json").write_text(dump_manifest(manifest))

    spec = importlib.util.spec_from_file_location("run_geometry_benchmark_stage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "collect_git_state", lambda _: GitState("a" * 40, False))
    monkeypatch.setattr(module, "collect_host_info", lambda: HostInfo("fixture CPU", None))
    monkeypatch.setattr("rt_mapping.adapters.da3_metric.Da3MetricAdapter", _fake_adapter("da3"))
    monkeypatch.setattr("rt_mapping.adapters.unidepth_v2.UniDepthV2Adapter", _fake_adapter("unidepth"))
    monkeypatch.chdir(root)
    calls = []

    def execute(argv, *, cwd, env, output, timeout_s):
        # In-process stand-in for the subprocess launch: same argv, same cwd.
        assert Path(cwd).resolve() == root.resolve()
        calls.append(argv)
        script = argv.index("scripts/run_geometry_benchmark.py")
        return module.main(argv[script + 1:])
    monkeypatch.setattr(pipeline_run, "execute_upstream", execute)
    return root, calls, module


@pytest.mark.parametrize("model", ["da3", "unidepth"])
def test_launcher_runs_geometry_stage_for_either_model(workspace, model):
    root, calls, _ = workspace
    spec = {"command": [sys.executable, "scripts/run_geometry_benchmark.py", "--model", model,
                        "--manifest", "data/manifests/fixture.json", "--split", "smoke", "--frames", "2",
                        "--prewarm", "1"]}
    directory = root / "results/runs/pipe"
    directory.mkdir(parents=True)
    path, record, stage = pipeline_run._stage(root, directory, "pipe", "geometry", spec, 30)

    assert calls[0][-4:] == ["--run-id", "pipe.geometry", "--output-root", "results/runs/pipe/stages"]
    assert path == directory / "stages" / "pipe.geometry"
    assert record["status"] == "ok" and record["method"] == "model-spike" and record["dirty_worktree"] is False
    assert record["model"]["repo"] == REPOS[model][0]
    assert record["dataset"]["manifest"] == "data/manifests/fixture.json"
    assert stage["mode"] == "launched" and stage["run_id"] == "pipe.geometry"
    assert not (root / "results/runs/pipe.geometry").exists()
    metrics = json.loads((path / "metrics.json").read_text())
    assert len(metrics["per_frame"]) == 2 and metrics["mean"]["abs_rel"] == 0
    assert load_run_manifest(path / "run.json")["config"]["model"]["device"] == "cuda"


def test_standalone_cli_keeps_default_output_root(workspace):
    root, _, module = workspace
    argv = ["--model", "unidepth", "--manifest", "data/manifests/fixture.json", "--split", "smoke",
            "--frames", "2", "--prewarm", "0", "--run-id", "standalone"]
    assert module.main(argv) == 0
    assert load_run_manifest(root / "results/runs/standalone/run.json")["status"] == "ok"
    assert module.main(argv) != 0  # an existing run directory is never overwritten
