"""WP2 dataset verification and isolated pySLAM readiness checks.

These checks do not run SLAM, install packages, or modify the input dataset.
The lightweight tools environment is deliberately separate from upstream's
native runtime. A successful dataset check does not imply SLAM is installed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from rt_mapping.data.manifest import build_tum_manifest, build_tum_split_manifest, sha256_file
from rt_mapping.data.tum import load_sequence, read_index


def load_setup_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config["schema"] != "rt_mapping.wp2_setup/v1":
        raise ValueError("unsupported WP2 setup schema")
    if config["sensor_type"] != "mono":
        raise ValueError("WP2 B0 must use monocular RGB")
    optimization = config.get("python_optimization", 1)
    if type(optimization) is not int or optimization not in (0, 1):
        raise ValueError("python_optimization must be 0 or 1")
    return config



def _load_split(repo_root: Path, config: dict[str, Any]):
    manifest = json.loads((repo_root / config["dataset_manifest"]).read_text(encoding="utf-8"))
    split = config["split"]
    if manifest.get("schema_version") != 1 or split not in manifest.get("splits", {}):
        raise ValueError("configured split is missing from the frozen TUM manifest")
    frozen = manifest["splits"][split]
    count = frozen["num_frames"]
    if (type(count) is not int or count < 1 or len(frozen["frames"]) != count
            or [row["frame_id"] for row in frozen["frames"]] != list(range(count))):
        raise ValueError("frozen split count/frame IDs are inconsistent")
    if manifest["sequence_id"] != Path(config["sequence_dir"]).name:
        raise ValueError("configured sequence differs from the frozen manifest")
    return manifest, frozen


def resolve_frame_count(repo_root: Path, config: dict[str, Any], frames: int | None) -> int:
    """None means the entire configured split; integers request a frozen prefix."""
    _, frozen = _load_split(repo_root, config)
    count = frozen["num_frames"] if frames is None else frames
    if type(count) is not int or count < 2:
        raise ValueError("baseline preparation requires at least two frames")
    if count > frozen["num_frames"]:
        raise ValueError("requested frames exceed the frozen split")
    return count

def verify_extracted_archive(archive: Path, sequence_dir: Path) -> int:
    """Compare every regular archive member with its extracted file; never extract.

    Refuse links and paths outside the named sequence. Reads decompressed content
    in bounded chunks rather than keeping the entire dataset in memory.
    """
    count = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            parts = Path(member.name).parts
            if not parts or parts[0] != sequence_dir.name or ".." in parts:
                raise ValueError(f"unsafe archive member: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"unsupported archive member: {member.name}")
            local = sequence_dir.joinpath(*parts[1:])
            if not local.resolve().is_relative_to(sequence_dir.resolve()):
                raise ValueError(f"archive member resolves outside sequence: {member.name}")
            if not local.is_file() or local.stat().st_size != member.size:
                raise ValueError(f"missing or wrong-size extracted file: {member.name}")
            digest = hashlib.sha256()
            with source.extractfile(member) as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
            if sha256_file(local) != digest.hexdigest():
                raise ValueError(f"extracted contents differ: {member.name}")
            count += 1
    return count


def _check_png(path: Path, width: int, height: int, bit_depth: int) -> None:
    with path.open("rb") as image:
        header = image.read(29)
    if len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path.name}")
    if struct.unpack(">II", header[16:24]) != (width, height) or header[24] != bit_depth:
        raise ValueError(f"unexpected dimensions or bit depth: {path.name}")


def verify_dataset(repo_root: Path, config: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    """Verify archive/index hashes, frozen manifest, images, timestamps and GT poses.

    Ground truth is inspected here only as evaluation data, never used for fitting.
    TUM quaternion components are rounded to four decimals; squared norm tolerance
    5e-4 accommodates that precision. Evaluation should normalize before use.
    """
    seq = repo_root / config["sequence_dir"]
    archive = repo_root / config["archive"]
    manifest, frozen = _load_split(repo_root, config)
    # Frozen wider manifests carry content hashes per selected RGB/depth file.
    # Use the existing data API unchanged; keep legacy C2 smoke reconstruction.
    hashed_split = config["split"] != "smoke" or any(
        key in row for row in frozen["frames"] for key in ("rgb_sha256", "depth_sha256"))
    if hashed_split:
        rebuilt = build_tum_split_manifest(
            seq, archive, repo_root, manifest["source"]["archive_url"],
            config["split"], num_frames=frozen["num_frames"],
        )
    else:
        rebuilt = build_tum_manifest(
            seq, archive, repo_root, manifest["source"]["archive_url"],
            smoke_frames=frozen["num_frames"], max_delta_s=manifest["association"]["max_delta_s"],
        )
    if rebuilt != manifest:
        raise ValueError("local archive/indexes do not reproduce the frozen dataset manifest")
    counts = {}
    for name, depth in (("rgb.txt", 8), ("depth.txt", 16)):
        rows = read_index(seq / name)
        stamps = [row.timestamp_s for row in rows]
        if not all(math.isfinite(t) for t in stamps) or any(a >= b for a, b in zip(stamps, stamps[1:])):
            raise ValueError(f"{name}: timestamps must be finite and strictly increasing")
        for row in rows:
            path = seq / row.relative_path
            if not path.resolve().is_relative_to(seq.resolve()):
                raise ValueError(f"{name}: image path outside sequence")
            _check_png(path, manifest["image"]["width"], manifest["image"]["height"], depth)
        counts[name] = len(rows)
    gt = []
    for line in (seq / "groundtruth.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            row = list(map(float, line.split()))
            if len(row) != 8 or not all(map(math.isfinite, row)):
                raise ValueError("invalid groundtruth row")
            if abs(sum(v * v for v in row[4:]) - 1.0) > 5e-4:
                raise ValueError("groundtruth quaternion exceeds rounding tolerance")
            gt.append(row)
    if not gt or any(a[0] > b[0] for a, b in zip(gt, gt[1:])):
        raise ValueError("groundtruth timestamps must be nonempty and nondecreasing")
    duplicate_gt_pairs = sum(a[0] == b[0] for a, b in zip(gt, gt[1:]))
    frames = load_sequence(seq, max_delta_s=manifest["association"]["max_delta_s"])
    if gt[-1][0] < frames[0].frame.timestamp_s or gt[0][0] > frames[-1].frame.timestamp_s:
        raise ValueError("groundtruth time range does not overlap associated RGB frames")
    # Official TUM sequences may start/end outside the motion-capture interval.
    # Keep every frozen RGB input; GT association/coverage belongs to evaluation.
    outside_gt = sum(not gt[0][0] <= f.frame.timestamp_s <= gt[-1][0] for f in frames)
    return {
        "status": "ok", "sequence": manifest["sequence_id"],
        "archive_sha256": rebuilt["source"]["archive_sha256"],
        "archive_size_bytes": rebuilt["source"]["archive_size_bytes"],
        "rgb_frames": counts["rgb.txt"], "depth_frames": counts["depth.txt"],
        "associations": len(frames),
        **({"smoke_frames": len(frozen["frames"])} if config["split"] == "smoke" else
           {"split": config["split"], "split_frames": len(frozen["frames"]),
            "selected_input_hashes_verified": 2 * len(frozen["frames"])}),
        "groundtruth_poses": len(gt), "quaternion_norm_squared_tolerance": 5e-4,
        "associated_rgb_frames_outside_gt_time_range": outside_gt,
        "extracted_files_verified": verify_extracted_archive(archive, seq) if full else None,
        "checks": ["frozen_manifest", "archive_sha256", "index_sha256", "PNG_headers", "timestamps", "evaluation_GT"]
                  + (["selected_rgb_depth_sha256"] if hashed_split else []),
        **({"groundtruth_duplicate_timestamp_pairs": duplicate_gt_pairs} if duplicate_gt_pairs else {}),
        "limitations": ([] if full else ["PNG headers checked; extracted bytes not compared with archive (use --full)."] )
                       + (["Ground-truth timestamps contain duplicates; evaluation must explicitly handle/reference only its time window. RGB/depth inputs are unaffected."] if duplicate_gt_pairs else [])
                       + (["Associated RGB frames extend beyond the GT time range; all frozen inputs are retained. Evaluation must report unmatched poses using its unchanged timestamp tolerance."] if outside_gt else []),
    }


def inspect_source(source: Path, revision: str) -> dict[str, Any]:
    if not (source / ".git").exists():
        return {"status": "missing", "reason": "external pySLAM checkout not found"}
    try:
        def git(*args: str) -> str:
            return subprocess.check_output(["git", *args], cwd=source, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
        actual = git("rev-parse", "HEAD")
        # Upstream's own installer creates auxiliary source/build directories
        # (e.g. thirdparty/gtsam_local). Check tracked source changes separately.
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
        untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
        sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"], cwd=source, capture_output=True, text=True).stdout.strip() == "true"
        missing = [p for p in ("main_slam.py", "pyslam/config.py", "settings/TUM1.yaml", "thirdparty/g2opy") if not (source / p).exists()]
        return {"status": "ok" if actual == revision and not dirty and not missing else "incomplete",
                "revision": actual, "revision_matches": actual == revision, "dirty": dirty,
                "untracked_file_count": len(untracked),
                "sparse_checkout": sparse, "missing_paths": missing}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "reason": str(exc)}


def probe_runtime(python: Path, source: Path, *, timeout_s: int = 180) -> dict[str, Any]:
    """Import actual upstream entry-point dependencies in a child process, without running main.

    Success proves imports only, not tracking or map quality. Output is retained
    as diagnostics; no upstream source is edited.
    """
    code = "import runpy,sys; print('WP2_PYTHON',sys.version.split()[0],flush=True); runpy.run_path('main_slam.py',run_name='wp2_import_probe')"
    try:
        done = subprocess.run(
            # Preserve the venv executable path: resolve() follows its symlink
            # to the base interpreter and silently loses the venv site-packages.
            [str(python.absolute()), "-c", code], cwd=source,
            env={**os.environ, "PYSLAM_USE_CPP": "false", "PYTHONDONTWRITEBYTECODE": "1",
                 "MPLCONFIGDIR": os.environ.get("MPLCONFIGDIR", str(source.absolute() / ".cache/wp2/matplotlib")),
                 "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", str(source.absolute() / ".cache/wp2")),
                 "QT_QPA_PLATFORM": "offscreen", "PYTHONUNBUFFERED": "1"},
            capture_output=True, text=True, timeout=timeout_s,
        )
        return {"status": "ok" if done.returncode == 0 else "failed", "exit_code": done.returncode,
                "scope": "upstream entry-point imports only", "stdout": done.stdout[-12000:], "stderr": done.stderr[-12000:]}
    except subprocess.TimeoutExpired as exc:
        def readable(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        return {"status": "failed", "reason": str(exc), "stdout": readable(exc.stdout)[-12000:], "stderr": readable(exc.stderr)[-12000:]}
    except OSError as exc:
        return {"status": "failed", "reason": str(exc)}


def host_report(repo_root: Path) -> dict[str, Any]:
    import shutil
    return {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
            "free_disk_gib": round(shutil.disk_usage(repo_root).free / 1024**3, 1),
            "tools": {name: shutil.which(name) is not None for name in ("git", "cmake", "clang", "brew", "docker")}}


def prepare_baseline(
    repo_root: Path, source: Path, output: Path, config: dict[str, Any], *, frames: int | None,
) -> dict[str, Any]:
    """Prepare an RGB-only frozen split input and upstream YAML; does not run SLAM.

    Files go into a new ignored output directory. Neither the original dataset
    nor the external upstream checkout is edited. Original shared frame IDs and
    timestamps are recorded alongside the view. No depth/GT is exposed to SLAM.
    """
    import yaml

    frames = resolve_frame_count(repo_root, config, frames)
    if output.exists():
        raise ValueError("output already exists; choose a new preparation directory")
    seq = repo_root / config["sequence_dir"]
    if output.resolve().is_relative_to(seq.resolve()) or output.resolve().is_relative_to(source.resolve()):
        raise ValueError("output must be outside the dataset and external source")
    state = inspect_source(source, config["upstream"]["revision"])
    if not state.get("revision_matches") or state.get("dirty"):
        raise ValueError("source must be a clean checkout of the pinned pySLAM revision")
    manifest, frozen = _load_split(repo_root, config)
    selected = frozen["frames"][:frames]
    if len(selected) != frames:
        raise ValueError("requested frames exceed the frozen split")
    for item in selected:
        path = seq / item["rgb_path"]
        if not path.resolve().is_relative_to(seq.resolve()) or not path.is_file():
            raise ValueError("missing RGB input or input outside sequence")
    settings = yaml.safe_load((source / "settings/TUM1.yaml").read_text(encoding="utf-8"))
    # Keep the same TUM1 baseline settings; change only camera calibration.
    # Freiburg3 omits k3 in its upstream YAML: explicitly zero it rather than
    # leaking the TUM1 coefficient into an already-undistorted dataset.
    camera = manifest["camera"]
    if camera not in ("freiburg1", "freiburg2", "freiburg3"):
        raise ValueError("unsupported TUM camera calibration")
    if camera != "freiburg1":
        calibration = yaml.safe_load((source / f"settings/TUM{camera[-1]}.yaml").read_text(encoding="utf-8"))
        for key in ("k1", "k2", "p1", "p2", "k3"):
            settings[f"Camera.{key}"] = calibration.get(f"Camera.{key}", 0.0)
    # Shared WP1 manifest intrinsics are authoritative for every camera.
    intr = manifest["intrinsics"]
    for key in ("fx", "fy", "cx", "cy"):
        settings[f"Camera.{key}"] = intr[key]
    settings.update({"Viewer.on": 0, "FeatureTrackerConfig.name": config["feature_tracker"],
                     "FeatureTrackerConfig.nFeatures": config["num_features"],
                     "LoopDetectionConfig.name": config["loop_detector"], "Camera.RGB": 0})
    # FolderDataset uses cv2.imread -> BGR, hence Camera.RGB=0.
    output = output.resolve()
    view = output / "input"
    yaml_path = output / "pyslam.yaml"
    upstream_config = {
        "DATASET": {"type": "FOLDER_DATASET"},
        "FOLDER_DATASET": {"type": "folder", "sensor_type": "mono", "base_path": str(view),
                           "name": "*.png", "settings": str(output / "camera.yaml"),
                           "timestamps": "times.txt", "fps": 30},
        "SYSTEM_STATE": {"load_state": False, "folder_path": os.path.relpath(output / "slam_state", source)},
        "SAVE_TRAJECTORY": {"save_trajectory": True, "format_type": "tum",
                            "output_folder": str(output / "trajectory"), "basename": "trajectory"},
        "GLOBAL_PARAMETERS": {"USE_CPP_CORE": config["use_cpp_core"], "kUseLoopClosing": True,
                              "kDoVolumetricIntegration": False,
                              "kUseDepthEstimatorInFrontEnd": False,
                              "kDoSparseSemanticMappingAndSegmentation": False,
                              "kLogsFolder": str(output / "logs")},
    }
    # JSON is valid YAML and avoids interpolating host paths into shell commands.
    plan = {"schema": "rt_mapping.wp2_preparation/v1", "status": "prepared_not_run",
            "upstream": config["upstream"], "seed": config["seed"], "frames": selected,
            "dataset_archive_sha256": manifest["source"]["archive_sha256"],
            "environment": {"PYSLAM_USE_CPP": "false"},
            "python_flags": ["-O"] if config.get("python_optimization", 1) == 1 else [],
            "argv_after_python": [str(source.resolve() / "main_slam.py"), "--config_path", str(yaml_path), "--headless", "--no_output_date"],
            "cwd": str(source.resolve()),
            "limitations": ["Native runtime not validated by preparation.",
                            "Preparation alone does not seed execution; upstream threaded ORB2/SLAM determinism is not guaranteed.",
                            "No trajectory normalization, sparse export, ATE/RPE or run.json yet."]}
    view.mkdir(parents=True, exist_ok=False)
    for index, item in enumerate(selected):
        target = (seq / item["rgb_path"]).resolve()
        destination = view / f"{index:06d}.png"
        try:
            destination.symlink_to(target)
        except OSError as exc:
            if os.name != "nt" or getattr(exc, "winerror", None) != 1314:
                raise
            # Windows commonly forbids symlinks without Developer Mode/admin.
            # A byte-preserving copy keeps the input view usable without it.
            shutil.copyfile(target, destination)
    plan["input_view_storage"] = "symlinks_or_byte_identical_copies"
    (view / "times.txt").write_text("".join(f"{item['rgb_timestamp_s']:.9f}\n" for item in selected), encoding="utf-8")
    for path, data in ((output / "camera.yaml", settings), (yaml_path, upstream_config), (output / "setup.json", plan)):
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return plan
