import json
from pathlib import Path
import sys

import pytest

from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs.geometry_run import GitState, HostInfo
from rt_mapping.runs.pipeline_run import run_pipeline, validate_pipeline_config
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a"*40, non_collinear=True)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    monkeypatch.setattr("rt_mapping.runs.pipeline_run.collect_git_state", lambda root: GitState("a"*40, False))
    monkeypatch.setattr("rt_mapping.runs.pipeline_run.collect_host_info", lambda: HostInfo("fixture CPU", None))
    # Child runs use the same deterministic synthetic code revision facts.
    monkeypatch.setattr("rt_mapping.runs.mapping_run.collect_git_state", lambda root: GitState("a"*40, False))
    monkeypatch.setattr("rt_mapping.runs.comparison_run.collect_git_state", lambda root: GitState("a"*40, False))
    config = dict(schema="rt_mapping.pipeline_config/v1", dataset_manifest=str(manifest),
        sequence_dir=str(sequence), split="smoke", slam={"reuse_run": str(slam)}, geometry={"reuse_run": str(geometry)},
        mapping={}, comparison={"keyframe_intervals": []}, timeout_s=30)
    return tmp_path, config


def test_one_config_executes_mapping_or_comparison_and_records_reuse(pipeline):
    root, config = pipeline
    directory = run_pipeline(root, config, run_id="pipeline")
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    assert load_run_manifest(directory / record["artifacts"]["result"])["status"] == "ok"
    timing = json.loads((directory / "timing.json").read_text())
    assert timing["inference_included"] is False and timing["real_time_claim"] is False
    assert all(s["mode"] == "reused" for s in timing["stages"].values())
    config["comparison"] = None
    second = run_pipeline(root, config, run_id="mapping_only")
    assert load_run_manifest(second / "run.json")["status"] == "ok"


def test_explicit_argv_launches_recorded_stages_without_shell_interpolation(pipeline):
    root, config = pipeline
    launcher = root / "fake_adapter.py"
    launcher.write_text("""import argparse,json,shutil
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--source'); p.add_argument('--run-id'); p.add_argument('--output-root'); a=p.parse_args()
target=Path(a.output_root)/a.run_id
shutil.copytree(a.source,target)
record=json.loads((target/'run.json').read_text()); record['run_id']=a.run_id
(target/'run.json').write_text(json.dumps(record))
""")
    for key in ("slam", "geometry"):
        source = config[key]["reuse_run"]
        config[key] = {"command": [sys.executable, str(launcher), "--source", source]}
    config["comparison"] = None
    directory = run_pipeline(root, config, run_id="launched")
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    inputs = json.loads((directory / "input_stages.json").read_text())
    assert all(s["mode"] == "launched" and s["command_sha256"] for s in inputs.values())
    assert (directory / "logs/slam.log").exists()


def test_adapter_failure_propagates_and_retains_log(pipeline):
    root, config = pipeline
    config["geometry"] = {"command": [sys.executable, "-c", "raise SystemExit(9)"]}
    directory = run_pipeline(root, config, run_id="failed")
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "failed" and "exited 9" in record["reason"]
    assert (directory / "logs/geometry.log").exists()


def test_existing_pipeline_is_not_overwritten(pipeline):
    root, config = pipeline
    config["comparison"] = None
    directory = run_pipeline(root, config, run_id="once")
    before = (directory / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        run_pipeline(root, config, run_id="once")
    assert (directory / "run.json").read_bytes() == before


def test_pipeline_rejects_owned_cli_flags_and_missing_executable(pipeline):
    root, config = pipeline
    config["geometry"] = {"command": [sys.executable, "script.py", "--run-id=escape"]}
    with pytest.raises(ValueError, match="owns"):
        validate_pipeline_config(root, config)
    config["geometry"] = {"command": ["missing_executable_12345678"]}
    with pytest.raises(ValueError, match="not found"):
        validate_pipeline_config(root, config)
