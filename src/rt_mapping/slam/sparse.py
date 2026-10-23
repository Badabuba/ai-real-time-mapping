"""Validated sparse-map handoff, with no pySLAM imports or metric-scale claims.

Observations refer to retained keyframes only. Raw pixels sample the original
distorted RGB/depth grid; residuals are Euclidean errors on the undistorted grid.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np


OBSERVATION_FIELDS = (
    "frame_id", "keyframe_id", "point_id", "keypoint_index", "u", "v",
    "u_undistorted", "v_undistorted", "reprojection_error_px", "depth_slam",
)
FILES = ("landmarks.npz", "keyframes.npz", "observations.csv", "sparse_map.ply")


@dataclass
class SparseSnapshot:
    landmarks: dict[str, np.ndarray]
    keyframes: dict[str, np.ndarray]
    observations: list[dict]
    metadata: dict


def _array(fields, name, shape, *, integer=False):
    a = np.asarray(fields[name])
    if a.shape != shape or not np.issubdtype(a.dtype, np.number) or not np.isfinite(a).all():
        raise ValueError(f"invalid finite array {name}: expected {shape}")
    if integer and (a.dtype.kind not in "iu" or np.any(a < 0)):
        raise ValueError(f"{name} must contain nonnegative integers")
    return a


def validate_snapshot(snapshot: SparseSnapshot) -> None:
    """Check foreign keys, counts, rigid poses and independently reproject links."""
    points, cameras, rows = snapshot.landmarks, snapshot.keyframes, snapshot.observations
    n, k = len(points["point_id"]), len(cameras["frame_id"])
    if n == 0 or k == 0 or not rows:
        raise ValueError("sparse snapshot must have landmarks, keyframes and observations")
    ids = _array(points, "point_id", (n,), integer=True)
    xyz = _array(points, "xyz_slam", (n, 3))
    counts = _array(points, "observation_count", (n,), integer=True)
    if len(np.unique(ids)) != n:
        raise ValueError("duplicate point IDs")
    for name in ("frame_id", "keyframe_id", "upstream_frame_id"):
        values = _array(cameras, name, (k,), integer=True)
        if len(np.unique(values)) != k:
            raise ValueError(f"duplicate {name}")
    _array(cameras, "timestamp_s", (k,))
    poses = _array(cameras, "T_wc", (k, 4, 4))
    intrinsics = _array(cameras, "K", (k, 3, 3))
    _array(cameras, "distortion", (k, 5))
    sizes = _array(cameras, "image_size_wh", (k, 2), integer=True)
    if np.any(sizes <= 0) or np.any(intrinsics[:, (0, 1), (0, 1)] <= 0):
        raise ValueError("invalid image size or focal length")
    if not np.allclose(intrinsics[:, 2, :], [0, 0, 1]):
        raise ValueError("invalid intrinsics last row")
    rotations = poses[:, :3, :3]
    if (not np.allclose(poses[:, 3, :], [0, 0, 0, 1], atol=1e-6)
            or not np.allclose(rotations.transpose(0, 2, 1) @ rotations, np.eye(3), atol=1e-5)
            or not np.allclose(np.linalg.det(rotations), 1, atol=1e-5)):
        raise ValueError("T_wc must be a proper rigid transform")
    point_index = {int(value): i for i, value in enumerate(ids)}
    camera_index = {int(value): i for i, value in enumerate(cameras["keyframe_id"])}
    actual_counts = np.zeros(n, dtype=np.int64)
    seen = set()
    for row in rows:
        if set(row) != set(OBSERVATION_FIELDS):
            raise ValueError("invalid observation fields")
        for name in OBSERVATION_FIELDS[:4]:
            if type(row[name]) is not int or row[name] < 0:
                raise ValueError(f"invalid observation integer {name}")
        if not np.isfinite([row[name] for name in OBSERVATION_FIELDS[4:]]).all():
            raise ValueError("non-finite observation")
        try:
            pi, ci = point_index[row["point_id"]], camera_index[row["keyframe_id"]]
        except KeyError as exc:
            raise ValueError("dangling point/keyframe reference") from exc
        if row["frame_id"] != int(cameras["frame_id"][ci]):
            raise ValueError("observation frame/keyframe mismatch")
        link = (row["keyframe_id"], row["point_id"])
        feature = (row["keyframe_id"], "feature", row["keypoint_index"])
        if link in seen or feature in seen:
            raise ValueError("duplicate observation or keypoint assignment")
        seen.update((link, feature))
        if not (0 <= row["u"] < sizes[ci, 0] and 0 <= row["v"] < sizes[ci, 1]):
            raise ValueError("raw observation outside image")
        pc = rotations[ci].T @ (xyz[pi] - poses[ci, :3, 3])
        if pc[2] <= 0 or not np.isclose(row["depth_slam"], pc[2], rtol=1e-6, atol=1e-8):
            raise ValueError("invalid observation camera depth")
        projected = intrinsics[ci] @ pc
        residual = np.linalg.norm(projected[:2] / projected[2]
                                  - [row["u_undistorted"], row["v_undistorted"]])
        if not np.isclose(row["reprojection_error_px"], residual, rtol=1e-6, atol=1e-6):
            raise ValueError("inconsistent undistorted reprojection error")
        actual_counts[pi] += 1
    if not np.array_equal(counts, actual_counts) or np.any(counts == 0):
        raise ValueError("observation_count does not match exported links")


def write_sparse_snapshot(output: Path, snapshot: SparseSnapshot) -> dict:
    """Write a new directory; export.json is the completion marker, written last."""
    validate_snapshot(snapshot)
    output.mkdir(parents=True, exist_ok=False)
    for name, arrays in (("landmarks.npz", snapshot.landmarks), ("keyframes.npz", snapshot.keyframes)):
        with (output / name).open("xb") as stream:
            np.savez_compressed(stream, **arrays)
    with (output / "observations.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OBSERVATION_FIELDS)
        writer.writeheader()
        writer.writerows(snapshot.observations)
    xyz = snapshot.landmarks["xyz_slam"]
    with (output / "sparse_map.ply").open("x", encoding="ascii") as stream:
        stream.write("ply\nformat ascii 1.0\ncomment units arbitrary_monocular_SLAM_units\n"
                     f"element vertex {len(xyz)}\nproperty double x\nproperty double y\n"
                     "property double z\nend_header\n")
        np.savetxt(stream, xyz, fmt="%.17g")
    metadata = {
        **snapshot.metadata, "schema": "rt_mapping.sparse_export/v1", "status": "ok",
        "pose_convention": "T_wc", "units": "arbitrary monocular SLAM units; not meters",
        "observation_scope": "retained keyframes only; not all tracked frames",
        "pixel_convention": "u right, v down; integer pixel centers; original distorted image grid",
        "reprojection_error_convention": "Euclidean pixel residual against undistorted keypoints using K",
        "counts": {"landmarks": len(xyz), "keyframes": len(snapshot.keyframes["frame_id"]),
                   "observations": len(snapshot.observations)},
        "sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in FILES},
    }
    with (output / "export.json").open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return metadata


def check_sparse_export(output: Path) -> dict:
    """Read back and verify the handoff without importing the SLAM backend."""
    metadata = json.loads((output / "export.json").read_text())
    if metadata["schema"] != "rt_mapping.sparse_export/v1" or metadata["status"] != "ok":
        raise ValueError("incomplete or unsupported sparse export")
    for name in FILES:
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != metadata["sha256"][name]:
            raise ValueError(f"sparse artifact checksum mismatch: {name}")
    with np.load(output / "landmarks.npz", allow_pickle=False) as archive:
        points = dict(archive)
    with np.load(output / "keyframes.npz", allow_pickle=False) as archive:
        cameras = dict(archive)
    with (output / "observations.csv").open(newline="") as stream:
        rows = [{name: (int(value) if name in OBSERVATION_FIELDS[:4] else float(value))
                 for name, value in row.items()} for row in csv.DictReader(stream)]
    validate_snapshot(SparseSnapshot(points, cameras, rows, metadata))
    counts = {"landmarks": len(points["point_id"]), "keyframes": len(cameras["frame_id"]),
              "observations": len(rows)}
    if metadata["counts"] != counts:
        raise ValueError("sparse metadata counts mismatch")
    return metadata
