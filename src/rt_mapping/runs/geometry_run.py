"""Run one GeometryAdapter over a frozen TUM split and record everything (WP1 C5).

Flow (docs/EXPERIMENTS.md §5):
    preflight  -> validate inputs and the initial run.json; nothing is written on failure
    running    -> run dir created, run.json status "running"
    work       -> dataset check vs C2 manifest, model load, predict -> save -> evaluate
    terminal   -> run.json "ok", or "failed" with "<reason>: <message>"

Predictions (C3 NPZ) never contain ground truth; GT depth is read only for
evaluation. An existing run directory is never touched.
Model-agnostic: the adapter comes from a factory; torch is never imported here.
"""

from __future__ import annotations

import json
import hashlib
import platform
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from rt_mapping.contracts.frame import FrameRecord
from rt_mapping.contracts.geometry import GeometryPrediction, save_prediction
from rt_mapping.contracts.run_manifest import RUN_JSON, build_run_manifest, format_utc, write_run_manifest
from rt_mapping.data import tum
from rt_mapping.data.manifest import sha256_file
from rt_mapping.evaluation.depth import evaluate_depth, mean_depth_metrics, resize_depth_nearest
from rt_mapping.evaluation.timing import summarize_timings
from rt_mapping.evaluation.tum_depth import load_tum_depth_m
from rt_mapping.evaluation.prediction_grid import resize_prediction
from rt_mapping.geometry.adapter import GeometryAdapterError

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PREFLIGHT = 2

METHOD = "model-spike"
TIMING_STAGE = "model_inference"
PREDICTIONS_DIR = "predictions"
METRICS_JSON = "metrics.json"
TIMING_JSON = "timing.json"
METRICS_SCHEMA = "rt_mapping.depth_metrics/v1"
TIMING_SCHEMA = "rt_mapping.timing/v1"


class PreflightError(ValueError):
    """Invalid request; raised before any file is written."""


class RunFailure(RuntimeError):
    """A known, non-adapter failure during a run (reason code + message)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


class BenchmarkAdapter(Protocol):
    """GeometryAdapter plus what a run record needs. describe() returns
    {"model": {repo, revision, checkpoint, dtype}, "environment": {...}, "gpu": str|None, "config": {...}}."""

    def predict(self, frame: FrameRecord) -> GeometryPrediction: ...

    def describe(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


@dataclass(frozen=True)
class HostInfo:
    cpu: str
    ram_gb: float | None


@dataclass(frozen=True)
class RunSpec:
    """Everything a run needs except the adapter.

    manifest_rel is the repo-relative POSIX path recorded in run.json.
    initial_model is the model block known before loading (checkpoint is
    resolved at load and replaced from adapter.describe()).
    archive_path None means the archive hash is not re-checked (recorded).
    """

    run_id: str
    output_root: Path
    sequence_dir: Path
    manifest_path: Path
    manifest_rel: str
    split: str
    frames: int
    warmup: int
    seed: int
    initial_model: dict[str, Any]
    config: dict[str, Any]
    archive_path: Path | None = None
    prewarm_calls: int = 0
    evaluation_grid: str = "prediction"


@dataclass(frozen=True)
class RunResult:
    run_dir: Path
    status: str
    reason: str | None
    exit_code: int
    artifacts: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Host / git facts
# ---------------------------------------------------------------------------


def collect_git_state(repo_root: str | Path) -> GitState:
    """HEAD commit and whether tracked or untracked (non-ignored) files differ."""

    def git(*args: str) -> str:
        try:
            done = subprocess.run(
                ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PreflightError(f"git {' '.join(args)} failed: {exc}") from exc
        return done.stdout

    commit = git("rev-parse", "HEAD").strip()
    dirty = bool(git("status", "--porcelain").strip())
    return GitState(commit=commit, dirty=dirty)


def cpu_description() -> str:
    """Non-empty CPU description; platform.processor() is empty on some systems."""
    for candidate in (platform.processor(), platform.machine(), platform.system()):
        if candidate and candidate.strip():
            return candidate.strip()
    return "unknown"


def collect_host_info() -> HostInfo:
    ram_gb = None
    try:
        import psutil  # optional; not a project dependency

        ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        ram_gb = None
    return HostInfo(cpu=cpu_description(), ram_gb=ram_gb)


def base_environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__}


# ---------------------------------------------------------------------------
# Dataset manifest (C2) checks
# ---------------------------------------------------------------------------


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PreflightError(f"cannot read dataset manifest {path}: {exc}") from exc
    for key in ("sequence_id", "source", "index_files", "image", "intrinsics", "association", "splits", "dataset"):
        if key not in manifest:
            raise PreflightError(f"dataset manifest {path} has no {key!r}")
    return manifest


def split_frames(manifest: dict[str, Any], split: str) -> list[dict[str, Any]]:
    splits = manifest["splits"]
    if split not in splits:
        raise PreflightError(f"split {split!r} is not in the dataset manifest (has {sorted(splits)})")
    return list(splits[split]["frames"])


def verify_tum_split(
    manifest: dict[str, Any],
    sequence_dir: Path,
    split: str,
    n_frames: int,
    archive_path: Path | None,
) -> list[tum.TumFrame]:
    """Check the local sequence against the C2 manifest and return the first n_frames of split.

    Raises RunFailure("dataset_mismatch" | "missing_input").
    """
    sequence_dir = Path(sequence_dir)
    if sequence_dir.name != manifest["sequence_id"]:
        raise RunFailure("dataset_mismatch", f"sequence dir {sequence_dir.name!r} != manifest {manifest['sequence_id']!r}")
    for name, expected in manifest["index_files"].items():
        path = sequence_dir / name
        if not path.is_file():
            raise RunFailure("missing_input", f"{name} not found in the sequence directory")
        if sha256_file(path) != expected["sha256"]:
            raise RunFailure("dataset_mismatch", f"{name} sha256 differs from the manifest")
    if archive_path is not None:
        if not Path(archive_path).is_file():
            raise RunFailure("missing_input", f"archive {Path(archive_path).name} not found (use --skip-archive-hash to record it as unverified)")
        if sha256_file(archive_path) != manifest["source"]["archive_sha256"]:
            raise RunFailure("dataset_mismatch", "archive sha256 differs from the manifest")

    frames = tum.load_sequence(
        sequence_dir, max_delta_s=manifest["association"]["max_delta_s"], sequence_id=manifest["sequence_id"]
    )
    if len(frames) != manifest["association"]["num_associations"]:
        raise RunFailure(
            "dataset_mismatch", f"{len(frames)} associations, manifest says {manifest['association']['num_associations']}"
        )
    intr = manifest["intrinsics"]
    k = tum.rgb_intrinsics(manifest["sequence_id"])
    if [k[0, 0], k[1, 1], k[0, 2], k[1, 2]] != [intr["fx"], intr["fy"], intr["cx"], intr["cy"]]:
        raise RunFailure("dataset_mismatch", "loader intrinsics differ from the manifest")

    selected: list[tum.TumFrame] = []
    for entry in split_frames(manifest, split)[:n_frames]:
        frame_id = entry["frame_id"]
        if not 0 <= frame_id < len(frames):
            raise RunFailure("dataset_mismatch", f"manifest frame_id {frame_id} is out of range")
        item = frames[frame_id]
        actual = (item.frame.timestamp_s, item.frame.image_path, item.gt_depth_timestamp_s, item.gt_depth_path)
        expected = (entry["rgb_timestamp_s"], entry["rgb_path"], entry["depth_timestamp_s"], entry["depth_path"])
        if actual != expected:
            raise RunFailure("dataset_mismatch", f"frame {frame_id}: loader gives {actual}, manifest {expected}")
        for field, relative in (("rgb_sha256", item.frame.image_path), ("depth_sha256", item.gt_depth_path)):
            if field in entry and sha256_file(sequence_dir / relative) != entry[field]:
                raise RunFailure("dataset_mismatch", f"frame {frame_id}: {field} differs from frozen bytes")
        if (item.frame.width, item.frame.height) != (manifest["image"]["width"], manifest["image"]["height"]):
            raise RunFailure("dataset_mismatch", f"frame {frame_id}: image size differs from the manifest")
        selected.append(item)
    if len(selected) != n_frames:
        raise RunFailure("dataset_mismatch", f"split {split!r} has only {len(selected)} frames, {n_frames} requested")
    return selected


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def prediction_name(frame_id: int) -> str:
    return f"{PREDICTIONS_DIR}/frame_{frame_id:06d}.npz"


def preflight(spec: RunSpec, manifest: dict[str, Any]) -> None:
    """Request checks that need no files written. Raises PreflightError."""
    for name, value in (("frames", spec.frames), ("warmup", spec.warmup), ("seed", spec.seed)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise PreflightError(f"{name} must be an integer, got {value!r}")
    if spec.frames < 1:
        raise PreflightError(f"frames must be >= 1, got {spec.frames}")
    if isinstance(spec.prewarm_calls, bool) or not isinstance(spec.prewarm_calls, int) or spec.prewarm_calls < 0:
        raise PreflightError("prewarm_calls must be a non-negative integer")
    if spec.evaluation_grid not in {"prediction", "raw_rgb"}:
        raise PreflightError("evaluation_grid must be prediction or raw_rgb")
    if not 0 <= spec.warmup < spec.frames:
        raise PreflightError(f"warmup must satisfy 0 <= warmup < frames ({spec.frames}), got {spec.warmup}")
    available = len(split_frames(manifest, spec.split))
    if spec.frames > available:
        raise PreflightError(f"split {spec.split!r} has {available} frames, {spec.frames} requested")
    run_dir = Path(spec.output_root) / spec.run_id
    if run_dir.exists():
        raise PreflightError(f"run directory {run_dir} already exists; a run is never overwritten (choose a new --run-id)")


def run_geometry_benchmark(
    spec: RunSpec,
    adapter_factory: Callable[[], BenchmarkAdapter],
    *,
    git_state: GitState,
    host_info: HostInfo,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    log: Callable[[str], None] = print,
) -> RunResult:
    """Execute one run. Raises PreflightError (nothing written) or returns a RunResult."""
    manifest = load_dataset_manifest(spec.manifest_path)
    preflight(spec, manifest)

    started = clock()
    record: dict[str, Any] = {
        "run_id": spec.run_id,
        "git_commit": git_state.commit,
        "dirty_worktree": git_state.dirty,
        "dataset": {
            "name": manifest["dataset"],
            "sequence": manifest["sequence_id"],
            "split": spec.split,
            "checksum": manifest["source"]["archive_sha256"],
            "manifest": spec.manifest_rel,
        },
        "method": METHOD,
        "model": dict(spec.initial_model),
        "slam": None,
        "alignment": None,
        "config": {
            **spec.config,
            "frames": spec.frames,
            "warmup": spec.warmup,
            "archive_hash_verified": spec.archive_path is not None,
            "dataset_manifest_sha256": sha256_file(spec.manifest_path),
            "prewarm_calls": spec.prewarm_calls,
            "evaluation_grid": spec.evaluation_grid,
        },
        "hardware": {"gpu": None, "cpu": host_info.cpu, "ram_gb": host_info.ram_gb},
        "environment": base_environment(),
        "seed": spec.seed,
        "started_at": format_utc(started),
        "status": "running",
        "reason": None,
        "artifacts": {},
    }
    try:
        running = build_run_manifest(**record)
    except ValueError as exc:
        raise PreflightError(f"invalid run record: {exc}") from exc

    run_dir = Path(spec.output_root) / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_run_manifest(running, run_dir)

    artifacts: dict[str, str] = {}
    status, reason = "ok", None
    wall_started = time.perf_counter()
    try:
        frames = verify_tum_split(manifest, spec.sequence_dir, spec.split, spec.frames, spec.archive_path)
        log(f"dataset ok: {len(frames)} frames of split {spec.split!r}")

        adapter = adapter_factory()
        description = adapter.describe()
        record["model"] = dict(description["model"])
        record["environment"] = {**record["environment"], **description["environment"]}
        record["hardware"]["gpu"] = description.get("gpu")
        record["config"]["model"] = description["config"]

        prewarm_ms = []
        for _ in range(spec.prewarm_calls):
            prewarm_ms.append(adapter.predict(frames[0].frame).inference_ms)

        (run_dir / PREDICTIONS_DIR).mkdir()
        per_frame: list[dict[str, Any]] = []
        metrics = []
        samples_ms: list[float] = []
        for index, item in enumerate(frames):
            frame = item.frame
            prediction = adapter.predict(frame)
            if prediction.frame_id != frame.frame_id or prediction.timestamp_s != frame.timestamp_s:
                raise GeometryAdapterError(
                    "unexpected_model_output", f"prediction for frame {frame.frame_id} carries frame_id {prediction.frame_id}"
                )
            name = prediction_name(frame.frame_id)
            save_prediction(prediction, run_dir / name)
            artifacts["predictions"] = PREDICTIONS_DIR

            try:
                gt = load_tum_depth_m(spec.sequence_dir, item.gt_depth_path)
                height, width = prediction.depth_m.shape
                if spec.evaluation_grid == "raw_rgb":
                    evaluated_prediction = resize_prediction(prediction, (frame.width, frame.height))
                    if gt.shape != (frame.height, frame.width):
                        raise ValueError("GT grid differs from raw RGB")
                    frame_metrics = evaluate_depth(evaluated_prediction, gt)
                else:
                    frame_metrics = evaluate_depth(prediction, resize_depth_nearest(gt, (width, height)))
            except (OSError, ValueError) as exc:
                raise RunFailure("evaluation_failed", f"frame {frame.frame_id}: {exc}") from exc
            metrics.append(frame_metrics)
            samples_ms.append(prediction.inference_ms)
            per_frame.append(
                {
                    **frame_metrics.to_dict(),
                    "evaluation_mask_sha256": hashlib.sha256(
                        np.ascontiguousarray(
                            (np.isfinite(gt) & (gt > 0) & evaluated_prediction.valid_mask)
                            if spec.evaluation_grid == "raw_rgb" else
                            (np.isfinite(resize_depth_nearest(gt, (width, height)))
                             & (resize_depth_nearest(gt, (width, height)) > 0) & prediction.valid_mask)
                        ).tobytes()
                    ).hexdigest(),
                    "timestamp_s": frame.timestamp_s,
                    "rgb_path": frame.image_path,
                    "gt_depth_timestamp_s": item.gt_depth_timestamp_s,
                    "gt_depth_path": item.gt_depth_path,
                    "prediction": name,
                    "inference_ms": prediction.inference_ms,
                }
            )
            log(
                f"[{index + 1:02d}/{len(frames):02d}] frame {frame.frame_id}: "
                f"{prediction.inference_ms:.1f} ms abs_rel={frame_metrics.abs_rel:.4f}"
            )

        timing = summarize_timings(samples_ms, warmup=spec.warmup, stage=TIMING_STAGE)
        metrics_doc = {
            "schema": METRICS_SCHEMA,
            "protocol": {
                "ground_truth": "TUM depth PNG / 5000 (rt_mapping.evaluation.tum_depth), evaluation only",
                "gt_resize": ("none; prediction bilinear to raw RGB grid" if spec.evaluation_grid == "raw_rgb"
                              else "rt_mapping.evaluation.depth.resize_depth_nearest to the prediction grid"),
                "mask": "finite(gt) & gt > 0 & prediction.valid_mask",
                "scale_alignment": "none (raw metric depth)",
                "aggregation": "frame_mean",
            },
            "mean": mean_depth_metrics(metrics),
            "per_frame": per_frame,
        }
        _write_text(run_dir / METRICS_JSON, _dump_json(metrics_doc))
        artifacts["metrics"] = METRICS_JSON

        finished = clock()
        peak = getattr(adapter, "peak_memory_gb", None)
        load_seconds = getattr(adapter, "load_seconds", None)
        timing_doc = {
            "schema": TIMING_SCHEMA,
            "stages": {TIMING_STAGE: timing.to_dict()},
            "per_frame_ms": [{"frame_id": m.frame_id, "inference_ms": ms} for m, ms in zip(metrics, samples_ms)],
            "model_load_s": load_seconds,
            "prewarm_samples_ms": prewarm_ms,
            "cold_inference_ms": prewarm_ms[0] if prewarm_ms else samples_ms[0],
            "peak_vram_gb": peak() if callable(peak) else None,
            "started_at": format_utc(started),
            "finished_at": format_utc(finished),
            "wall_clock_s": time.perf_counter() - wall_started,
            "notes": "per-stage latency only; no FPS is derived (docs/EXPERIMENTS.md §4.4)",
        }
        _write_text(run_dir / TIMING_JSON, _dump_json(timing_doc))
        artifacts["timing"] = TIMING_JSON
        log(
            f"mean abs_rel={metrics_doc['mean']['abs_rel']:.4f} rmse={metrics_doc['mean']['rmse_m']:.4f} m "
            f"delta1={metrics_doc['mean']['delta1']:.4f}; warm median {timing.warm_median_ms:.1f} ms, "
            f"p95 {timing.warm_p95_ms:.1f} ms"
        )
    except (GeometryAdapterError, RunFailure) as exc:
        status, reason = "failed", f"{exc.reason}: {exc.message}"
    except Exception as exc:  # unknown bug: still leave a terminal record, then show the traceback
        status, reason = "failed", f"internal_error: {type(exc).__name__}: {exc}"
        traceback.print_exc()
    except KeyboardInterrupt:
        _finish(running, record, run_dir, "failed", "internal_error: interrupted by user", artifacts, log)
        raise

    status, reason = _finish(running, record, run_dir, status, reason, artifacts, log)
    if reason:
        log(f"run {spec.run_id} FAILED: {reason}")
    else:
        log(f"run {spec.run_id} ok -> {run_dir / RUN_JSON}")
    return RunResult(
        run_dir=run_dir,
        status=status,
        reason=reason,
        exit_code=EXIT_OK if status == "ok" else EXIT_FAILED,
        artifacts=artifacts,
    )


def _finish(
    running: dict[str, Any],
    record: dict[str, Any],
    run_dir: Path,
    status: str,
    reason: str | None,
    artifacts: dict[str, str],
    log: Callable[[str], None],
) -> tuple[str, str | None]:
    """Write the terminal run.json. If the collected record is invalid, fall back
    to the validated "running" record marked failed, so a run never stays "running"."""
    record = {**record, "status": status, "reason": reason, "artifacts": dict(artifacts)}
    try:
        final = build_run_manifest(**record)
    except ValueError as exc:
        status, reason = "failed", f"internal_error: invalid run record: {exc}"
        log(reason)
        fallback = {key: value for key, value in running.items() if key != "schema"}
        final = build_run_manifest(**{**fallback, "status": status, "reason": reason, "artifacts": dict(artifacts)})
    write_run_manifest(final, run_dir, overwrite=True)
    return status, reason
