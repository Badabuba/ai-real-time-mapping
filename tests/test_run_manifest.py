from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from rt_mapping.contracts import (
    build_run_manifest,
    dump_run_manifest,
    format_utc,
    load_run_manifest,
    validate_run_manifest,
    write_run_manifest,
)
from rt_mapping.contracts.run_manifest import SCHEMA, is_secret_key

SHA = "a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98"
COMMIT = "5ce9da36a0a07e9cae4337c818dc713530f2beec"


def fields(**overrides: Any) -> dict[str, Any]:
    """A complete P1-global manifest without schema (every block non-null)."""
    base: dict[str, Any] = {
        "run_id": "2026-10-21_tum_f1xyz_p1_global_seed0",
        "git_commit": COMMIT,
        "dirty_worktree": False,
        "dataset": {
            "name": "TUM-RGBD",
            "sequence": "rgbd_dataset_freiburg1_xyz",
            "split": "smoke",
            "checksum": SHA,
            "manifest": "data/manifests/tum_fr1_xyz.json",
        },
        "method": "P1-global",
        "model": {
            "repo": "ByteDance-Seed/Depth-Anything-3",
            "revision": "abc123",
            "checkpoint": "depth-anything/DA3METRIC-LARGE",
            "dtype": "float32",
        },
        "slam": {"repo": "luigifreda/pyslam", "revision": "def456", "config": "configs/tum_fr1.yaml", "pose_convention": "T_wc"},
        "alignment": {"method": "robust_median_scale", "thresholds": {"min_inliers": 30, "min_inlier_ratio": 0.5}},
        "config": {"process_res": 384, "batch": 1, "keyframe_interval": 1, "tokenizer": None, "max_tokens": 0},
        "hardware": {"gpu": "NVIDIA GeForce RTX 5070 Laptop GPU", "cpu": "x86_64", "ram_gb": 32},
        "environment": {"python": "3.11.16", "torch": "2.11.0+cu128"},
        "seed": 0,
        "started_at": "2026-10-21T10:00:00Z",
        "status": "planned",
        "reason": None,
        "artifacts": {"metrics": "metrics.json", "timing": "timing.csv"},
    }
    base.update(overrides)
    return base


def model_spike(**overrides: Any) -> dict[str, Any]:
    return fields(method="model-spike", slam=None, alignment=None, **overrides)


def full() -> dict[str, Any]:
    return {**fields(), "schema": SCHEMA}


def _key_paths(manifest: dict[str, Any]) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    for key, value in manifest.items():
        paths.append((key,))
        if key in ("dataset", "model", "slam", "alignment", "hardware"):
            paths.extend((key, sub) for sub in value)
    paths.append(("environment", "python"))
    return paths


def _delete(manifest: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    out = copy.deepcopy(manifest)
    target = out
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return out


def _set(manifest: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(manifest)
    keys = path.split(".")
    target = out
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return out


def test_valid_manifest_builds_and_is_a_copy() -> None:
    source = fields()
    manifest = build_run_manifest(**source)
    assert manifest["schema"] == SCHEMA
    assert set(manifest) == set(source) | {"schema"}
    source["dataset"]["sequence"] = "changed"
    assert manifest["dataset"]["sequence"] == "rgbd_dataset_freiburg1_xyz"


def test_model_spike_manifest_is_valid() -> None:
    manifest = build_run_manifest(**model_spike(status="ok"))
    assert manifest["slam"] is None and manifest["alignment"] is None


def test_baseline_manifest_without_model_is_valid() -> None:
    build_run_manifest(**fields(method="B0", model=None, alignment=None))


@pytest.mark.parametrize("path", _key_paths(full()), ids=lambda p: ".".join(p))
def test_rejects_every_missing_required_key(path: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        validate_run_manifest(_delete(full(), path))


@pytest.mark.parametrize("block", ["", "dataset", "model", "slam", "alignment", "hardware"])
def test_rejects_unknown_keys(block: str) -> None:
    manifest = full()
    (manifest[block] if block else manifest)["extra"] = "x"
    with pytest.raises(ValueError, match="unknown keys"):
        validate_run_manifest(manifest)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema", "rt_mapping.run_manifest/v0"),
        ("run_id", ""),
        ("run_id", "../escape"),
        ("run_id", "a b"),
        ("git_commit", "TODO"),
        ("git_commit", COMMIT[:7]),
        ("git_commit", COMMIT.upper()),
        ("dirty_worktree", 0),
        ("dataset.name", ""),
        ("dataset.split", "test"),
        ("dataset.checksum", "sha256:" + SHA),
        ("dataset.checksum", SHA.upper()),
        ("dataset.checksum", SHA[:-1]),
        ("dataset.manifest", "data\\manifests\\x.json"),
        ("dataset.manifest", "../data/x.json"),
        ("method", "P3"),
        ("model.dtype", ""),
        ("model.repo", 5),
        ("slam.config", "/etc/pyslam.yaml"),
        ("alignment.thresholds", {"min_inliers": "30"}),
        ("alignment.thresholds", {"min_inliers": True}),
        ("alignment.thresholds", []),
        ("config", []),
        ("hardware.cpu", None),
        ("hardware.gpu", ""),
        ("hardware.ram_gb", 0),
        ("hardware.ram_gb", "32"),
        ("hardware.ram_gb", True),
        ("environment", {"torch": "2.11"}),
        ("environment", {"python": 3.11}),
        ("seed", -1),
        ("seed", 1.0),
        ("seed", True),
        ("started_at", "TODO"),
        ("started_at", "2026-10-21T10:00:00"),
        ("started_at", "2026-10-21T10:00:00+03:00"),
        ("started_at", "2026-13-01T10:00:00Z"),
        ("status", "done"),
        ("reason", "should be null when planned"),
        ("artifacts", {"map": "../map.ply"}),
        ("artifacts", {"map": ""}),
        ("artifacts", ["metrics.json"]),
    ],
)
def test_rejects_invalid_values(path: str, value: Any) -> None:
    with pytest.raises(ValueError):
        validate_run_manifest(_set(full(), path, value))


@pytest.mark.parametrize("status", ["degraded", "failed", "skipped"])
def test_reason_required_for_problem_statuses(status: str) -> None:
    with pytest.raises(ValueError, match="reason"):
        build_run_manifest(**fields(status=status))
    manifest = build_run_manifest(**fields(status=status, reason="insufficient_correspondences"))
    assert manifest["reason"] == "insufficient_correspondences"


@pytest.mark.parametrize(
    "overrides",
    [
        {"method": "B0"},  # model must be null
        {"method": "B1", "model": None},  # slam ok, alignment must be null
        {"method": "P1-raw"},  # alignment must be null
        {"method": "P1-raw", "alignment": None, "slam": None},  # slam required
        {"model": None},  # P1-global needs a model
        {"alignment": None},  # P1-global needs alignment
        {"method": "model-spike", "alignment": None},  # slam must be null
        {"method": "model-spike", "slam": None},  # alignment must be null
    ],
)
def test_method_conditional_blocks(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        build_run_manifest(**fields(**overrides))


def test_p2_may_omit_slam() -> None:
    build_run_manifest(**fields(method="P2", slam=None))
    build_run_manifest(**fields(method="P2"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("path", ["config.process_res", "hardware.ram_gb", "alignment.thresholds.min_inlier_ratio"])
def test_rejects_non_finite(path: str, value: float) -> None:
    with pytest.raises(ValueError):
        validate_run_manifest(_set(full(), path, value))


@pytest.mark.parametrize(
    "value", ["C:\\Users\\nazar\\data", "C:/Users/nazar", "/home/nazar/data", "\\\\server\\share\\x", "~/data"]
)
@pytest.mark.parametrize("path", ["config.data_dir", "model.checkpoint", "environment.python", "dataset.sequence"])
def test_rejects_host_specific_paths(path: str, value: str) -> None:
    with pytest.raises(ValueError):
        validate_run_manifest(_set(full(), path, value))


@pytest.mark.parametrize(
    "key", ["password", "api_key", "apiKey", "APIKEY", "hf_token", "access_token", "AWS_SECRET_ACCESS_KEY", "credentials", "private-key"]
)
def test_rejects_secret_keys(key: str) -> None:
    with pytest.raises(ValueError, match="secret-like"):
        validate_run_manifest(_set(full(), f"config.{key}", "x"))


@pytest.mark.parametrize("key", ["tokenizer", "max_tokens", "num_tokens", "keyframe_interval", "secretary_note", "passthrough"])
def test_secret_check_has_no_substring_false_positives(key: str) -> None:
    assert not is_secret_key(key)
    validate_run_manifest(_set(full(), f"config.{key}", 1))


def test_rejects_non_json_values() -> None:
    with pytest.raises(ValueError):
        validate_run_manifest(_set(full(), "config.shape", (1, 2)))
    with pytest.raises(ValueError):
        validate_run_manifest(_set(full(), "config", {1: "x"}))


def test_dump_is_deterministic_and_round_trips(tmp_path: Path) -> None:
    a = build_run_manifest(**fields())
    b = json.loads(json.dumps(a))
    b = dict(reversed(list(b.items())))
    b["config"] = dict(reversed(list(b["config"].items())))
    text = dump_run_manifest(a)
    assert text == dump_run_manifest(b)
    assert text.endswith("}\n")
    path = tmp_path / "run.json"
    path.write_text(text, encoding="utf-8")
    assert load_run_manifest(path) == a


def test_load_rejects_nan_literal(tmp_path: Path) -> None:
    text = dump_run_manifest(build_run_manifest(**fields())).replace('"ram_gb": 32', '"ram_gb": NaN')
    path = tmp_path / "run.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="NaN"):
        load_run_manifest(path)


def test_load_rejects_legacy_runner_json(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"status": "ok", "model_id": "depth-anything/DA3METRIC-LARGE"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required keys"):
        load_run_manifest(path)


def test_write_refuses_to_edit_finished_run(tmp_path: Path) -> None:
    planned = build_run_manifest(**fields())
    run_dir = tmp_path / planned["run_id"]
    path = write_run_manifest(planned, run_dir)
    assert load_run_manifest(path) == planned
    running = {**planned, "status": "running"}
    with pytest.raises(ValueError, match="overwrite=True"):
        write_run_manifest(running, run_dir)
    write_run_manifest(running, run_dir, overwrite=True)
    done = {**planned, "status": "ok"}
    write_run_manifest(done, run_dir, overwrite=True)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="never edited"):
        write_run_manifest({**planned, "status": "failed", "reason": "x"}, run_dir, overwrite=True)
    assert path.read_bytes() == before


def test_write_refuses_unreadable_existing_file(tmp_path: Path) -> None:
    planned = build_run_manifest(**fields())
    run_dir = tmp_path / planned["run_id"]
    run_dir.mkdir()
    (run_dir / "run.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be read"):
        write_run_manifest(planned, run_dir, overwrite=True)


def test_write_requires_dir_named_after_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        write_run_manifest(build_run_manifest(**fields()), tmp_path / "other")


def test_format_utc() -> None:
    kyiv = timezone(timedelta(hours=3))
    assert format_utc(datetime(2026, 10, 21, 13, 0, 0, tzinfo=kyiv)) == "2026-10-21T10:00:00Z"
    stamp = format_utc(datetime(2026, 10, 21, 10, 0, 0, 1234, tzinfo=timezone.utc))
    assert stamp == "2026-10-21T10:00:00.001234Z"
    build_run_manifest(**fields(started_at=stamp))
    with pytest.raises(ValueError):
        format_utc(datetime(2026, 10, 21, 10, 0, 0))
