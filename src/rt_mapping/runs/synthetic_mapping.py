"""Deterministic synthetic artifact handoff; never represents a real benchmark."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from rt_mapping.contracts.geometry import GeometryPrediction, save_prediction
from rt_mapping.contracts.run_manifest import build_run_manifest, write_run_manifest
from rt_mapping.geometry.intrinsics import resize_intrinsics
from rt_mapping.geometry.projection import back_project, project
from rt_mapping.slam.sparse import SparseSnapshot, write_sparse_snapshot

KNOWN_SCALE = 2.5


def create_synthetic_inputs(parent: Path, *, git_commit: str, dirty_worktree: bool = True, non_collinear=False,
                            keyframes=3):
    """A known plane seen from translated/rotated cameras, plus depth outliers."""
    if type(keyframes) is not int or not 3 <= keyframes <= 6:
        raise ValueError("synthetic fixture supports 3-6 keyframes")
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=False)
    slam_dir, geometry_dir = parent / "synthetic_slam", parent / "synthetic_geometry"
    slam_dir.mkdir()
    (geometry_dir / "predictions").mkdir(parents=True)
    width, height = 80, 60
    K = np.array([[80., 0, 39.5], [0, 80., 29.5], [0, 0, 1]])
    processed_K = resize_intrinsics(K, (width, height), (40, 30))
    u, v = np.meshgrid(np.linspace(13, 66, 9), np.linspace(9, 50, 8))
    xyz = back_project(np.column_stack((u.ravel(), v.ravel())), np.full(u.size, 1.2), K)
    ids = np.arange(100, 100 + len(xyz), dtype=np.int64)
    frame_ids = np.array([10, 27, 40, 52, 66, 79][:keyframes], dtype=np.int64)
    stamps = np.array([1., 1.1, 1.2, 1.3, 1.4, 1.5][:keyframes])
    poses, rows = [], []
    for index, (frame_id, stamp) in enumerate(zip(frame_ids, stamps)):
        step = (0, 1, 2, 0.5, 1.5, 1.25)[index]  # extra keyframes stay between the first three views
        angle = step * 0.025
        c, s = np.cos(angle), np.sin(angle)
        pose = np.array([[c, 0, s, step * 0.035], [0, 1, 0, (step**2 if non_collinear else step) * 0.01],
                         [-s, 0, c, step * 0.005], [0, 0, 0, 1.]])
        poses.append(pose)
        camera = (xyz - pose[:3, 3]) @ pose[:3, :3]
        uv = project(camera, K)
        for feature_index, (pid, pixel, pc) in enumerate(zip(ids, uv, camera)):
            rows.append(dict(frame_id=int(frame_id), keyframe_id=index, point_id=int(pid),
                             keypoint_index=feature_index, u=float(pixel[0]), v=float(pixel[1]),
                             u_undistorted=float(pixel[0]), v_undistorted=float(pixel[1]),
                             reprojection_error_px=0., depth_slam=float(pc[2])))
        pv, pu = np.indices((30, 40))
        rays = back_project(np.column_stack((pu.ravel(), pv.ravel())), np.ones(pu.size), processed_K)
        depth = ((1.2 - pose[2, 3]) / (rays @ pose[2, :3]) * KNOWN_SCALE).reshape(30, 40).astype(np.float32)
        depth[12:15, 17:20] *= 1.7  # Localized bad predicted depth, not GT input.
        prediction = GeometryPrediction(frame_id=int(frame_id), timestamp_s=float(stamp), depth_m=depth,
            valid_mask=np.ones_like(depth, dtype=bool), confidence=None, K_processed=processed_K,
            model_id="synthetic/plane@" + "0" * 40, inference_ms=0.,
            preprocess={"input_wh": [80, 60], "output_wh": [40, 30],
                        "steps": [{"op": "resize", "from_wh": [80, 60], "to_wh": [40, 30]}],
                        "pixel_grid": "raw_distorted", "intrinsics_convention": "pixel_centers_integer"})
        save_prediction(prediction, geometry_dir / f"predictions/frame_{frame_id:06d}.npz")
    cameras = dict(frame_id=frame_ids, keyframe_id=np.arange(keyframes), upstream_frame_id=np.arange(keyframes)*4+1,
                   timestamp_s=stamps, T_wc=np.array(poses), K=np.repeat(K[None], keyframes, axis=0),
                   distortion=np.zeros((keyframes, 5)), image_size_wh=np.tile([80, 60], (keyframes, 1)))
    snapshot = SparseSnapshot(dict(point_id=ids, xyz_slam=xyz, observation_count=np.full(len(ids), keyframes)),
                              cameras, rows, {"synthetic": True})
    write_sparse_snapshot(slam_dir / "sparse", snapshot)
    common = dict(git_commit=git_commit, dirty_worktree=dirty_worktree,
                  dataset={"name": "synthetic", "sequence": "plane_with_depth_outliers", "split": "smoke",
                           "checksum": hashlib.sha256(b"rt_mapping.synthetic_plane.v1").hexdigest(), "manifest": None},
                  alignment=None, config={"synthetic": True, "purpose": "correctness only; no scientific benchmark"},
                  hardware={"gpu": None, "cpu": "synthetic fixture", "ram_gb": None},
                  environment={"python": "synthetic generator", "numpy": np.__version__}, seed=0,
                  started_at="2026-10-25T00:00:00Z", status="ok", reason=None)
    write_run_manifest(build_run_manifest(**common, run_id=slam_dir.name, method="B0", model=None,
        slam={"repo": "synthetic/slam", "revision": "0" * 40, "config": "synthetic.json", "pose_convention": "T_wc"},
        artifacts={"sparse_export": "sparse/export.json"}), slam_dir)
    write_run_manifest(build_run_manifest(**common, run_id=geometry_dir.name, method="model-spike", slam=None,
        model={"repo": "synthetic/plane", "revision": "0" * 40, "checkpoint": "analytic plane", "dtype": "float32"},
        artifacts={"predictions": "predictions"}), geometry_dir)
    return slam_dir, geometry_dir
