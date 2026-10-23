"""Run orchestration with the real adapter over a fake backend, in temporary directories."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from conftest import GT_DEPTH_M, FakeDa3Backend, SynthRepo, metric_constant_raw
from rt_mapping.contracts.geometry import load_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.data import tum
from rt_mapping.evaluation.depth import evaluate_depth, resize_depth_nearest
from rt_mapping.evaluation.timing import summarize_timings
from rt_mapping.evaluation.tum_depth import load_tum_depth_m
from rt_mapping.geometry.adapter import GeometryAdapterError
from rt_mapping.adapters.da3_metric import Da3MetricAdapter, Da3MetricConfig
from rt_mapping.runs.geometry_run import (
    EXIT_FAILED,
    EXIT_OK,
    GitState,
    HostInfo,
    PreflightError,
    RunSpec,
    cpu_description,
    run_geometry_benchmark,
)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
CLEAN = GitState(COMMIT, False)
HOST = HostInfo(cpu="Test CPU", ram_gb=16.0)
FIXED_CLOCK = lambda: datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def spec(repo: SynthRepo, run_id: str = "run_a", **overrides) -> RunSpec:
    config = Da3MetricConfig()
    fields = dict(
        run_id=run_id,
        output_root=repo.root / "results" / "runs",
        sequence_dir=repo.sequence_dir,
        manifest_path=repo.manifest_path,
        manifest_rel=repo.manifest_rel,
        split="smoke",
        frames=repo.n_frames,
        warmup=1,
        seed=0,
        initial_model={"repo": config.repo, "revision": config.revision, "checkpoint": "unresolved", "dtype": config.dtype},
        config={"runner": "test", "batch": 1, "model": config.to_record()},
        archive_path=repo.archive,
    )
    fields.update(overrides)
    return RunSpec(**fields)


def factory(repo: SynthRepo, backend: FakeDa3Backend | None = None):
    backend = backend or FakeDa3Backend(depth_fn=metric_constant_raw(1.4))
    return lambda: Da3MetricAdapter(Da3MetricConfig(), repo.sequence_dir, backend=backend)


def run(repo: SynthRepo, run_spec: RunSpec | None = None, backend: FakeDa3Backend | None = None, git=CLEAN):
    return run_geometry_benchmark(
        run_spec or spec(repo), factory(repo, backend), git_state=git, host_info=HOST, clock=FIXED_CLOCK, log=lambda _: None
    )


def tree_bytes(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


# --- success ------------------------------------------------------------------


def test_successful_run_writes_valid_records(synth_repo: SynthRepo) -> None:
    result = run(synth_repo)
    assert (result.status, result.reason, result.exit_code) == ("ok", None, EXIT_OK)
    manifest = load_run_manifest(result.run_dir / "run.json")
    assert manifest["status"] == "ok" and manifest["method"] == "model-spike"
    assert manifest["slam"] is None and manifest["alignment"] is None
    assert manifest["git_commit"] == COMMIT and manifest["dirty_worktree"] is False
    assert manifest["dataset"]["checksum"] == json.loads(synth_repo.manifest_path.read_text())["source"]["archive_sha256"]
    assert manifest["dataset"]["manifest"] == synth_repo.manifest_rel
    assert manifest["model"]["checkpoint"] == "model.safetensors@sha256:" + "ab" * 32
    assert manifest["hardware"] == {"gpu": "Fake GPU", "cpu": "Test CPU", "ram_gb": 16.0}
    assert manifest["environment"]["torch"] == "fake"
    assert manifest["config"]["archive_hash_verified"] is True
    assert manifest["config"]["model"]["k_convention"] == "pixel_centers_integer"
    assert manifest["started_at"] == "2026-10-21T12:00:00Z"
    assert manifest["artifacts"] == {"predictions": "predictions", "metrics": "metrics.json", "timing": "timing.json"}


def test_predictions_hold_no_ground_truth(synth_repo: SynthRepo) -> None:
    result = run(synth_repo)
    files = sorted((result.run_dir / "predictions").iterdir())
    assert [f.name for f in files] == [f"frame_{i:06d}.npz" for i in range(synth_repo.n_frames)]
    for path in files:
        with zipfile.ZipFile(path) as zf:
            assert sorted(zf.namelist()) == ["K_processed.npy", "depth_m.npy", "meta.json", "valid_mask.npy"]
        pred = load_prediction(path)
        assert pred.confidence is None
        # GT is exactly 1.5 m; the fake model predicts 1.4 m, so no stored array equals GT.
        assert not np.any(np.isclose(pred.depth_m, GT_DEPTH_M))


def test_metrics_and_timing_match_c4_functions(synth_repo: SynthRepo) -> None:
    result = run(synth_repo)
    metrics = json.loads((result.run_dir / "metrics.json").read_text())
    timing = json.loads((result.run_dir / "timing.json").read_text())
    frames = tum.load_sequence(synth_repo.sequence_dir)
    expected = []
    for item in frames:
        pred = load_prediction(result.run_dir / f"predictions/frame_{item.frame.frame_id:06d}.npz")
        gt = resize_depth_nearest(load_tum_depth_m(synth_repo.sequence_dir, item.gt_depth_path), (378, 294))
        expected.append(evaluate_depth(pred, gt).to_dict())
    for got, want in zip(metrics["per_frame"], expected):
        assert {k: got[k] for k in want} == want
    assert metrics["mean"]["abs_rel"] == pytest.approx(0.1 / 1.5, rel=1e-5)
    assert metrics["mean"]["delta1"] == 1.0
    assert 0 < metrics["mean"]["valid_coverage"] <= 1
    want_timing = summarize_timings([11.0, 12.0, 13.0], warmup=1, stage="model_inference").to_dict()
    assert timing["stages"]["model_inference"] == want_timing
    assert timing["model_load_s"] == 0.25 and timing["peak_vram_gb"] == 1.0
    assert timing["finished_at"] == "2026-10-21T12:00:00Z"


def test_same_inputs_give_identical_artifacts(synth_repo: SynthRepo) -> None:
    one = run(synth_repo, spec(synth_repo, "run_one"))
    two = run(synth_repo, spec(synth_repo, "run_two"))
    a, b = tree_bytes(one.run_dir), tree_bytes(two.run_dir)
    for name in a:
        if name.startswith("predictions/") or name == "metrics.json":
            assert a[name] == b[name], name


def test_dirty_worktree_and_skipped_archive_hash_are_recorded(synth_repo: SynthRepo) -> None:
    result = run(synth_repo, spec(synth_repo, archive_path=None), git=GitState(COMMIT, True))
    manifest = load_run_manifest(result.run_dir / "run.json")
    assert manifest["dirty_worktree"] is True
    assert manifest["config"]["archive_hash_verified"] is False


# --- explicit failures --------------------------------------------------------


def _failed(result, reason: str) -> dict:
    assert (result.status, result.exit_code) == ("failed", EXIT_FAILED)
    manifest = load_run_manifest(result.run_dir / "run.json")
    assert manifest["status"] == "failed"
    assert manifest["reason"].startswith(f"{reason}: ")
    return manifest


def test_model_failure_mid_run_is_recorded(synth_repo: SynthRepo) -> None:
    backend = FakeDa3Backend(depth_fn=metric_constant_raw(1.4), fail_on_call=(2, GeometryAdapterError("model_oom", "boom")))
    manifest = _failed(run(synth_repo, backend=backend), "model_oom")
    assert manifest["artifacts"] == {"predictions": "predictions"}
    assert [p.name for p in (synth_repo.root / "results/runs/run_a/predictions").iterdir()] == ["frame_000000.npz"]
    assert not (synth_repo.root / "results/runs/run_a/metrics.json").exists()


def test_non_finite_output_is_recorded(synth_repo: SynthRepo) -> None:
    backend = FakeDa3Backend(depth_fn=lambda rgb, hw: np.full(hw, np.nan, np.float32))
    _failed(run(synth_repo, backend=backend), "non_finite_output")


def test_model_load_failure_is_recorded(synth_repo: SynthRepo) -> None:
    backend = FakeDa3Backend(fail_load=GeometryAdapterError("model_load_failed", "not cached"))
    manifest = _failed(run(synth_repo, backend=backend), "model_load_failed")
    assert manifest["model"]["checkpoint"] == "unresolved"
    assert manifest["artifacts"] == {}


def test_unexpected_exception_is_recorded_as_internal_error(synth_repo: SynthRepo) -> None:
    backend = FakeDa3Backend(fail_on_call=(1, KeyError("oops")))
    _failed(run(synth_repo, backend=backend), "internal_error")


def test_tampered_index_file_is_dataset_mismatch(synth_repo: SynthRepo) -> None:
    with (synth_repo.sequence_dir / "rgb.txt").open("a", encoding="utf-8") as handle:
        handle.write("# edited\n")
    backend = FakeDa3Backend()
    _failed(run(synth_repo, backend=backend), "dataset_mismatch")
    assert backend.load_calls == 0  # model never loaded on bad data


def test_archive_hash_mismatch_and_missing_archive(synth_repo: SynthRepo) -> None:
    synth_repo.archive.write_bytes(b"different")
    _failed(run(synth_repo, spec(synth_repo, "run_bad")), "dataset_mismatch")
    synth_repo.archive.unlink()
    _failed(run(synth_repo, spec(synth_repo, "run_missing")), "missing_input")


def test_missing_gt_depth_is_evaluation_failure(synth_repo: SynthRepo) -> None:
    item = tum.load_sequence(synth_repo.sequence_dir)[1]
    (synth_repo.sequence_dir / item.gt_depth_path).unlink()
    _failed(run(synth_repo), "evaluation_failed")


# --- preflight and terminal-run protection -----------------------------------


@pytest.mark.parametrize("status", ["ok", "running"])
def test_existing_run_directory_is_never_touched(synth_repo: SynthRepo, status: str) -> None:
    first = run(synth_repo)
    if status == "running":
        record = json.loads((first.run_dir / "run.json").read_text())
        record["status"] = "running"
        (first.run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    before = tree_bytes(first.run_dir)
    with pytest.raises(PreflightError, match="already exists"):
        run(synth_repo)
    assert tree_bytes(first.run_dir) == before


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"frames": 4}, "has 3 frames"),
        ({"frames": 0}, "frames must be >= 1"),
        ({"warmup": 3}, "warmup must satisfy"),
        ({"warmup": -1}, "warmup must satisfy"),
        ({"split": "held-out"}, "not in the dataset manifest"),
        ({"run_id": "bad id/../x"}, "invalid run record"),
    ],
)
def test_preflight_rejects_without_writing(synth_repo: SynthRepo, overrides: dict, message: str) -> None:
    backend = FakeDa3Backend()
    with pytest.raises(PreflightError, match=message):
        run(synth_repo, spec(synth_repo, **overrides), backend=backend)
    assert not (synth_repo.root / "results").exists()
    assert backend.load_calls == 0


def test_cpu_description_is_never_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import platform

    monkeypatch.setattr(platform, "processor", lambda: "")
    monkeypatch.setattr(platform, "machine", lambda: "  ")
    monkeypatch.setattr(platform, "system", lambda: "")
    assert cpu_description() == "unknown"
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    assert cpu_description() == "AMD64"
