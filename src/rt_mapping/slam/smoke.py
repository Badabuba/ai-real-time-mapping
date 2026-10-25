"""Recorded B0 pySLAM smoke runs; upstream runs in a separate native environment.

The runner validates raw TUM trajectories and upstream frame counts, with an
opt-in retained-keyframe sparse handoff. ATE/RPE and per-stage latency remain
separate work.
Ground truth is verified as dataset metadata, never passed to upstream SLAM.
"""
from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, write_run_manifest
from rt_mapping.slam.setup import inspect_source, prepare_baseline, verify_dataset
from rt_mapping.slam.sparse import check_sparse_export


def upstream_bootstrap(root: Path, preparation: Path, run_dir: Path, *, seed: int, export_sparse: bool) -> str:
    """Preserve upstream __main__/spawn behavior and optionally instrument quit."""
    # Upstream starts in its own source directory, not the caller's cwd.
    root, preparation, run_dir = root.absolute(), preparation.absolute(), run_dir.absolute()
    code = (
        "import sys,runpy,random,numpy as np,cv2; "
        f"random.seed({seed}); np.random.seed({seed}); cv2.setRNGSeed({seed}); "
        "sys.argv=sys.argv[1:]; "
    )
    if export_sparse:
        code += (
            f"sys.path.insert(0, {str(root / 'src')!r}); "
            "from pathlib import Path; import json; "
            "from rt_mapping.slam.pyslam_export import install_shutdown_export; "
            "from pyslam.config import Config; "
            "from pyslam.slam.slam import Slam; "
            f"install_shutdown_export(Slam, Path({str(run_dir / 'sparse')!r}), "
            f"json.loads(Path({str(preparation / 'setup.json')!r}).read_text())['frames']); "
        )
    return code + "runpy.run_path(sys.argv[0],run_name='__main__')"


def execute_upstream(argv, *, cwd, env, output, timeout_s):
    """Own a process group so a failed/timed-out run leaves no SLAM workers."""
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        exit_code = process.wait(timeout=timeout_s)
        if exit_code and os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        return exit_code
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if os.name == "nt":
            # Windows has no killpg. This also targets children of a live
            # launcher; native pySLAM itself is still validated only on POSIX.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise


def check_smoke_artifacts(preparation: Path, frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Reject empty/malformed/off-grid trajectories and incomplete upstream runs."""
    trajectory = preparation / "trajectory/trajectory_final.txt"
    poses = np.loadtxt(trajectory, ndmin=2)
    if poses.shape[1:] != (8,) or len(poses) < 2 or not np.all(np.isfinite(poses)):
        raise ValueError("final trajectory must contain at least two finite TUM poses")
    if np.any(np.diff(poses[:, 0]) <= 0):
        raise ValueError("trajectory timestamps must be strictly increasing")
    if not np.allclose(np.linalg.norm(poses[:, 4:8], axis=1), 1.0, atol=1e-5):
        raise ValueError("trajectory contains non-unit quaternions")
    stamps = np.array([f["rgb_timestamp_s"] for f in frames])
    if np.any(np.min(np.abs(poses[:, 0, None] - stamps[None, :]), axis=1) > 1e-6):
        raise ValueError("trajectory timestamps do not match the frozen RGB inputs")
    counts = {}
    for line in (preparation / "trajectory/other_metrics_info.txt").read_text().splitlines():
        key, value = line.split(":", 1)
        counts[key] = float(value)
    processed, total, lost = (counts[k] for k in ("num_processed_frames", "num_total_frames", "num_lost_frames"))
    if processed != len(frames) or total != len(frames) or not 0 <= lost <= processed or lost != int(lost):
        raise ValueError("upstream frame counters are inconsistent or input run is incomplete")
    return {"input_frames": len(frames), "processed_frames": int(processed),
            "lost_frames": int(lost), "lost_fraction": lost / processed,
            "final_pose_count": len(poses), "final_pose_fraction": len(poses) / len(frames),
            "first_pose_timestamp_s": float(poses[0, 0]), "last_pose_timestamp_s": float(poses[-1, 0]),
            "trajectory_units": "monocular SLAM units; metric scale not recovered",
            "trajectory_alignment": "none", "ate_rpe": "not evaluated",
            "note": "Final pose fraction is not tracking success; initialization/lost-state handling differs."}


def run_smoke(
    root: Path, source: Path, python: Path, config: dict[str, Any], *, run_id: str,
    frames: int = 200, timeout_s: int = 1800, export_sparse: bool = False, output_root: Path | None = None,
) -> Path:
    """Create one immutable terminal run.json and retain upstream log on failure."""
    if frames < 2 or timeout_s < 1:
        raise ValueError("frames must be >= 2 and timeout_s >= 1")
    root, source, python = root.absolute(), source.absolute(), python.absolute()
    data = verify_dataset(root, config)
    state = inspect_source(source, config["upstream"]["revision"])
    if state["status"] != "ok" or not python.is_file():
        raise ValueError("pinned source or runtime interpreter is not ready")
    manifest = json.loads((root / config["dataset_manifest"]).read_text())
    if frames > len(manifest["splits"][config["split"]]["frames"]):
        raise ValueError("requested frames exceed the frozen split")
    run_dir = (Path(output_root) / run_id).absolute() if output_root is not None else root / "results/runs" / run_id
    # build_run_manifest validates the run_id before any directory creation.
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    native = subprocess.check_output([str(python), "-c",
        "import json,platform,importlib.metadata as m,psutil; "
        "print(json.dumps({'python':platform.python_version(),'numpy':m.version('numpy'),"
        "'torch':m.version('torch'),'opencv_python':m.version('opencv-python'),"
        "'ram_gb':round(psutil.virtual_memory().total/1024**3,1)}))"], text=True, timeout=30)
    environment = json.loads(native)
    ram_gb = environment.pop("ram_gb")
    record = dict(
        run_id=run_id, git_commit=commit, dirty_worktree=dirty,
        dataset={"name": "TUM RGB-D", "sequence": data["sequence"], "split": config["split"],
                 "checksum": data["archive_sha256"], "manifest": config["dataset_manifest"]},
        method="B0", model=None, alignment=None,
        slam={"repo": config["upstream"]["repo"], "revision": config["upstream"]["revision"],
              "config": "configs/wp2_pyslam_baseline.json", "pose_convention": "T_wc"},
        config={"runner": "scripts/run_wp2_pyslam.py", "frames": frames, "baseline": config,
                "export_sparse": export_sparse,
                "seed_policy": "parent Python/NumPy/OpenCV seeded; upstream threads/workers may remain nondeterministic",
                "timeout_s": timeout_s},
        hardware={"gpu": None, "cpu": platform.machine(), "ram_gb": ram_gb}, environment=environment,
        seed=config["seed"], started_at=format_utc(datetime.now(timezone.utc)),
        status="running", reason=None, artifacts={},
    )
    running = build_run_manifest(**record)
    if run_dir.exists():
        raise ValueError("run directory already exists; choose a new run_id")
    run_dir.mkdir(parents=True, exist_ok=False)
    write_run_manifest(running, run_dir)
    artifacts = {}
    start = time.perf_counter()
    try:
        preparation = run_dir / "input_setup"
        plan = prepare_baseline(root, source, preparation, config, frames=frames)
        artifacts["preparation"] = "input_setup/setup.json"
        artifacts["upstream_log"] = "upstream.log"
        bootstrap = upstream_bootstrap(root, preparation, run_dir, seed=config["seed"], export_sparse=export_sparse)
        env = {**os.environ, "PYSLAM_USE_CPP": "false", "PYTHONUNBUFFERED": "1", "PYTHONHASHSEED": str(config["seed"]),
               "MPLCONFIGDIR": str(root / ".local/wp2/matplotlib"),
               "XDG_CACHE_HOME": str(root / ".local/wp2/cache"), "QT_QPA_PLATFORM": "offscreen"}
        with (run_dir / "upstream.log").open("w", encoding="utf-8") as output:
            # Match main_slam.py's upstream shebang: python3 -O. This mode is
            # explicit in the versioned configuration and differs from run 01.
            flags = plan["python_flags"]
            exit_code = execute_upstream([str(python), *flags, "-c", bootstrap, *plan["argv_after_python"]],
                                         cwd=source, env=env, output=output, timeout_s=timeout_s)
        if exit_code:
            raise RuntimeError(f"upstream_exit: {exit_code}; see upstream.log")
        metrics = check_smoke_artifacts(preparation, plan["frames"])
        if export_sparse:
            sparse = check_sparse_export(run_dir / "sparse")
            metrics["sparse_export"] = sparse["counts"]
            artifacts.update(sparse_export="sparse/export.json", landmarks="sparse/landmarks.npz",
                             keyframes="sparse/keyframes.npz", observations="sparse/observations.csv",
                             sparse_map="sparse/sparse_map.ply")
        metrics["wall_clock_seconds_including_startup"] = time.perf_counter() - start
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
        artifacts.update(metrics="metrics.json", trajectory="input_setup/trajectory/trajectory_final.txt",
                         upstream_counts="input_setup/trajectory/other_metrics_info.txt")
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: user stopped upstream run")
        raise
    except subprocess.TimeoutExpired:
        record.update(status="failed", reason="timeout: upstream exceeded recorded timeout; see upstream.log")
    except (OSError, ValueError, RuntimeError) as exc:
        record.update(status="failed", reason=f"smoke_failed: {exc}")
    except Exception as exc:
        record.update(status="failed", reason=f"internal_error: {type(exc).__name__}: {exc}")
    finally:
        record["artifacts"] = artifacts
        write_run_manifest(build_run_manifest(**record), run_dir, overwrite=True)
    return run_dir
