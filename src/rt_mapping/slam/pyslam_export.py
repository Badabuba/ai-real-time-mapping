"""Read the pinned Python-core pySLAM map at the normal shutdown boundary.

The opt-in runtime wrapper calls the original shutdown, then exports before
upstream's forced process exit. No source-file edits or tracking changes.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from rt_mapping.slam.sparse import SparseSnapshot, write_sparse_snapshot


def _check_stopped(slam):
    if not slam.has_quit:
        raise ValueError("sparse export requires normal SLAM shutdown")
    workers = [slam.local_mapping, slam.loop_closing, slam.semantic_mapping,
               slam.volumetric_integrator, slam.GBA, slam.GBA_on_demand]
    if slam.loop_closing is not None:
        workers.extend([slam.loop_closing.GBA, slam.loop_closing.loop_detecting_process])
    for worker in workers:
        if worker is not None:
            for name in ("work_thread", "process"):
                handle = getattr(worker, name, None)
                if handle is not None and handle.is_alive():
                    raise ValueError(f"cannot export with active {type(worker).__name__}.{name}")


def collect_pyslam_snapshot(slam, frames: list[dict]) -> SparseSnapshot:
    """Capture retained monocular keyframe observations with their own poses.

    Uses keyframe timestamps, not pySLAM internal IDs, to recover shared frame
    IDs. Geometry is normalized by the first keyframe exactly as the upstream
    final trajectory convention; this snapshot is later than upstream's export.
    """
    _check_stopped(slam)
    stamps = np.array([f["rgb_timestamp_s"] for f in frames], dtype=np.float64)
    if (not np.isfinite(stamps).all() or len(stamps) == 0 or np.any(np.diff(stamps) <= 0)
            or len({f["frame_id"] for f in frames}) != len(frames)):
        raise ValueError("invalid shared frame manifest")
    skipped = Counter()
    with slam.map.update_lock:
        first = slam.map.get_first_keyframe()
        if first is None:
            raise ValueError("map was not initialized")
        source_from_export = np.asarray(first.Twc(), dtype=np.float64)
        export_from_source = np.linalg.inv(source_from_export)
        keyframes = sorted((kf for kf in slam.map.get_keyframes() if not kf.is_bad()), key=lambda kf: kf.kid)
        cameras = {name: [] for name in ("frame_id", "keyframe_id", "upstream_frame_id", "timestamp_s",
                                        "T_wc", "K", "distortion", "image_size_wh")}
        by_object = {}
        for kf in keyframes:
            matches = np.flatnonzero(np.abs(stamps - kf.timestamp) <= 1e-6)
            if len(matches) != 1:
                raise ValueError("keyframe timestamp does not uniquely match shared input")
            frame_id = frames[int(matches[0])]["frame_id"]
            pose = export_from_source @ np.asarray(kf.Twc(), dtype=np.float64)
            record = (int(frame_id), int(kf.kid), int(kf.id), float(kf.timestamp), pose,
                      np.asarray(kf.camera.K, dtype=np.float64),
                      np.asarray(kf.camera.D, dtype=np.float64),
                      [int(kf.camera.width), int(kf.camera.height)])
            by_object[id(kf)] = len(cameras["frame_id"])
            for name, value in zip(cameras, record):
                cameras[name].append(value)
        points = {"point_id": [], "xyz_slam": [], "observation_count": []}
        rows = []
        for point in sorted(slam.map.get_points(), key=lambda p: p.id):
            if point.is_bad():
                skipped["bad_landmarks"] += 1
                continue
            xyz = (export_from_source @ np.r_[point.pt(), 1.0])[:3]
            if not np.isfinite(xyz).all():
                raise ValueError("non-finite landmark position")
            links = []
            for kf, index in point.observations():
                ci = by_object.get(id(kf))
                if ci is None:
                    skipped["observations_of_nonretained_keyframes"] += 1
                    continue
                index = int(index)
                if index < 0 or index >= len(kf.kps) or kf.get_point_match(index) is not point:
                    raise ValueError("broken landmark/keyframe backlink")
                raw, undistorted = np.asarray(kf.kps[index]), np.asarray(kf.kpsu[index])
                if not np.isfinite(np.r_[raw, undistorted]).all():
                    raise ValueError("non-finite keypoint")
                pose = cameras["T_wc"][ci]
                pc = pose[:3, :3].T @ (xyz - pose[:3, 3])
                if pc[2] <= 0:
                    skipped["nonpositive_depth_observations"] += 1
                    continue
                projected = cameras["K"][ci] @ pc
                residual = float(np.linalg.norm(projected[:2] / projected[2] - undistorted))
                links.append(dict(frame_id=cameras["frame_id"][ci], keyframe_id=int(kf.kid),
                                  point_id=int(point.id), keypoint_index=index,
                                  u=float(raw[0]), v=float(raw[1]),
                                  u_undistorted=float(undistorted[0]), v_undistorted=float(undistorted[1]),
                                  reprojection_error_px=residual, depth_slam=float(pc[2])))
            if not links:
                skipped["landmarks_without_exportable_observations"] += 1
                continue
            points["point_id"].append(int(point.id))
            points["xyz_slam"].append(xyz)
            points["observation_count"].append(len(links))
            rows.extend(links)
        for name in points:
            points[name] = np.asarray(points[name], dtype=np.float64 if name == "xyz_slam" else np.int64)
        for name in cameras:
            cameras[name] = np.asarray(cameras[name], dtype=np.int64 if name in (
                "frame_id", "keyframe_id", "upstream_frame_id", "image_size_wh") else np.float64)
    rows.sort(key=lambda row: (row["frame_id"], row["point_id"]))
    metadata = {
        "snapshot_stage": "after original Slam.quit stops workers, before forced process exit; not a convergence guarantee",
        "world_frame": "first upstream keyframe camera frame at snapshot time",
        "T_export_world_from_upstream_world": export_from_source.tolist(),
        "reference_upstream_frame_id": int(first.id), "reference_timestamp_s": float(first.timestamp),
        "input_frame_count": len(frames), "skipped": dict(skipped),
        "keyframe_pose_source": "keyframes.npz; use these poses with these landmarks",
        "limitations": ["Not all-frame tracking observations or timing.",
                        "Upstream trajectory_final.txt predates this snapshot; do not assume identical optimization state.",
                        "Export is a handoff, not a reloadable pySLAM system state; PLY has geometry only."],
    }
    return SparseSnapshot(points, cameras, rows, metadata)


def export_pyslam_snapshot(slam, output: Path, frames: list[dict]) -> dict:
    return write_sparse_snapshot(output, collect_pyslam_snapshot(slam, frames))


def install_shutdown_export(slam_class, output: Path, frames: list[dict]) -> None:
    """Instrument shutdown once in the child process; retain upstream exit logic.

    Upstream headless main finishes with os._exit, so exporting after runpy
    returns cannot work. Keep the original quit and all forced-exit cleanup.
    """
    original = slam_class.quit
    attempted = set()

    def quit_and_export(self):
        result = original(self)
        if id(self) not in attempted:
            attempted.add(id(self))
            metadata = export_pyslam_snapshot(self, output, frames)
            print(f"WP2 sparse export: {metadata['counts']}", flush=True)
        return result

    slam_class.quit = quit_and_export
