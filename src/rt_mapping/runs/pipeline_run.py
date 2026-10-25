"""One-config offline orchestration of the existing WP1/WP2/WP3/WP4 runners.

Stages either reuse a completed run or execute an explicit argv (never a
shell string). No installations/downloads happen here. Each launched adapter
retains its own recorded environment, output and failure semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time

import numpy as np

from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, load_run_manifest, write_run_manifest
from rt_mapping.data.manifest import sha256_file
from rt_mapping.runs.comparison_run import comparison_config, run_comparison
from rt_mapping.runs.geometry_run import collect_git_state, collect_host_info
from rt_mapping.runs.mapping_run import _json, run_mapping, validate_config
from rt_mapping.slam.smoke import execute_upstream

CONFIG_SCHEMA = "rt_mapping.pipeline_config/v1"


def _path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def validate_pipeline_config(root, value):
    required = {"schema", "dataset_manifest", "sequence_dir", "split", "slam", "geometry", "mapping", "comparison", "timeout_s"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != CONFIG_SCHEMA:
        raise ValueError("pipeline config must contain exactly the documented v1 fields")
    if value["split"] not in ("smoke", "development", "selection", "held-out"):
        raise ValueError("unsupported dataset split")
    if type(value["timeout_s"]) is not int or value["timeout_s"] < 1:
        raise ValueError("pipeline timeout must be a positive integer")
    for key in ("dataset_manifest", "sequence_dir"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"{key} must be a nonempty path")
    for key in ("slam", "geometry"):
        stage = value[key]
        if not isinstance(stage, dict) or set(stage) not in ({"reuse_run"}, {"command"}):
            raise ValueError(f"{key} must specify exactly one of reuse_run/command")
        if "reuse_run" in stage:
            load_run_manifest(_path(root, stage["reuse_run"]) / "run.json")
        else:
            argv = stage["command"]
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
                raise ValueError("stage command must be a nonempty argv list")
            if any(a.split("=", 1)[0] in ("--run-id", "--output-root") for a in argv):
                raise ValueError("pipeline owns stage --run-id and --output-root")
            executable = _path(root, argv[0])
            if not executable.is_file() and shutil.which(argv[0]) is None:
                raise ValueError(f"stage executable not found: {argv[0]}")
    mapping = validate_config(value["mapping"])
    if value["comparison"] is not None:
        comparison_config({**value["comparison"], "mapping": mapping})
    manifest = json.loads(_path(root, value["dataset_manifest"]).read_text(encoding="utf-8"))
    if value["split"] not in manifest["splits"]:
        raise ValueError("split is absent from the frozen manifest")
    return manifest, mapping


def _stage(root, directory, pipeline_id, stage_name, spec, timeout_s):
    start = time.perf_counter()
    if "reuse_run" in spec:
        path = _path(root, spec["reuse_run"])
        mode = "reused"
    else:
        stage_id = pipeline_id+"."+stage_name
        path = directory / "stages" / stage_id
        # Relative POSIX paths work for a host Python or a WSL command launched
        # in this workspace. Custom wrappers must retain the workspace cwd.
        output_root = (directory / "stages").resolve().relative_to(root.resolve()).as_posix()
        argv = [*spec["command"], "--run-id", stage_id, "--output-root", output_root]
        (directory / "logs").mkdir(exist_ok=True)
        with (directory / "logs" / f"{stage_name}.log").open("x", encoding="utf-8") as stream:
            code = execute_upstream(argv, cwd=root, env=None, output=stream, timeout_s=timeout_s)
        if code:
            raise RuntimeError(f"{stage_name} adapter exited {code}; see logs/{stage_name}.log")
        mode = "launched"
    record = load_run_manifest(path / "run.json")
    expected = "B0" if stage_name == "slam" else "model-spike"
    if record["status"] != "ok" or record["method"] != expected:
        raise ValueError(f"{stage_name} did not produce completed {expected} artifacts")
    return path, record, {"mode": mode, "run_id": record["run_id"], "manifest_sha256": sha256_file(path / "run.json"),
                           "elapsed_s": time.perf_counter()-start,
                           "command_sha256": hashlib.sha256(json.dumps(spec.get("command"), sort_keys=True).encode()).hexdigest() if mode == "launched" else None}


def run_pipeline(repo_root, config, *, run_id, output_root=None):
    root = Path(repo_root).resolve()
    if not isinstance(run_id, str) or len(run_id) > 90:
        raise ValueError("pipeline ID must leave room for stage suffixes (max 90 characters)")
    manifest, mapping = validate_pipeline_config(root, config)
    state, host = collect_git_state(root), collect_host_info()
    manifest_path = _path(root, config["dataset_manifest"]).resolve()
    initial_geometry = (load_run_manifest(_path(root, config["geometry"]["reuse_run"]) / "run.json")
                        if "reuse_run" in config["geometry"] else None)
    initial_slam = (load_run_manifest(_path(root, config["slam"]["reuse_run"]) / "run.json")
                   if "reuse_run" in config["slam"] else None)
    record = dict(run_id=run_id, git_commit=state.commit, dirty_worktree=state.dirty,
        dataset={"name": manifest["dataset"], "sequence": manifest["sequence_id"], "split": config["split"],
                 "checksum": manifest["source"]["archive_sha256"],
                 "manifest": manifest_path.relative_to(root).as_posix() if manifest_path.is_relative_to(root) else None},
        method="P1-global", model=initial_geometry["model"] if initial_geometry else {
            "repo": "pending/geometry-stage", "revision": "unresolved", "checkpoint": "unresolved", "dtype": "unresolved"},
        slam=initial_slam["slam"] if initial_slam else {"repo": "pending/slam-stage", "revision": "unresolved",
                 "config": "configs/wp2_pyslam_baseline.json", "pose_convention": "T_wc"},
        alignment={"method": "robust_median", "thresholds": {"residual_m": mapping["residual_threshold_m"]}},
        config={"scope": "offline configuration-driven orchestration", "config_sha256": hashlib.sha256(
                    json.dumps(config, sort_keys=True).encode()).hexdigest(), "mapping": mapping},
        hardware={"gpu": None, "cpu": host.cpu, "ram_gb": host.ram_gb},
        environment={"python": platform.python_version(), "numpy": np.__version__}, seed=mapping["seed"],
        started_at=format_utc(datetime.now(timezone.utc)), status="running", reason=None, artifacts={})
    build_run_manifest(**record)
    directory = Path(output_root or root / "results/runs").resolve() / run_id
    if not directory.is_relative_to(root):
        raise ValueError("pipeline output must be inside the shared workspace for cross-runtime stage paths")
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), directory)
    start = time.perf_counter()
    stages = {}
    try:
        slam_path, slam, stages["slam"] = _stage(root, directory, run_id, "slam", config["slam"], config["timeout_s"])
        geometry_path, geometry, stages["geometry"] = _stage(root, directory, run_id, "geometry", config["geometry"], config["timeout_s"])
        record.update(model=geometry["model"], slam=slam["slam"])
        if slam["dataset"] != geometry["dataset"]:
            raise ValueError("completed adapters disagree on frozen dataset/split/checksum")
        if any(slam["dataset"][key] != record["dataset"][key] for key in ("name", "sequence", "split", "checksum")):
            raise ValueError("completed adapter dataset differs from pipeline config")
        _json(directory / "input_stages.json", stages)
        record["artifacts"]["input_stages"] = "input_stages.json"
        if config["comparison"] is None:
            result = run_mapping(root, slam_path, geometry_path, run_id=run_id+".mapping",
                                 config=mapping, output_root=directory / "stages")
        else:
            result = run_comparison(root, slam_path, geometry_path, _path(root, config["sequence_dir"]), manifest_path,
                run_id=run_id+".comparison", config={**config["comparison"], "mapping": mapping}, output_root=directory / "stages")
        record["artifacts"]["result"] = (result.relative_to(directory) / "run.json").as_posix()
        result_record = load_run_manifest(result / "run.json")
        if result_record["status"] != "ok":
            raise RuntimeError(result_record["reason"])
        _json(directory / "timing.json", {"wall_clock_s": time.perf_counter()-start, "stages": stages,
              "inference_included": all(stage["mode"] == "launched" for stage in stages.values()),
              "real_time_claim": False,
              "note": "Reuse mode times artifact verification/integration only; native/model timings stay in source runs."})
        record["artifacts"]["timing"] = "timing.json"
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: pipeline stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"pipeline_failed: {exc}")
    finally:
        if not (directory / "input_stages.json").exists():
            _json(directory / "input_stages.json", stages)
            record["artifacts"]["input_stages"] = "input_stages.json"
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory
