"""Analytic synthetic GT for testing the evaluator, never a real-data result."""
from pathlib import Path

import numpy as np

from rt_mapping.fusion import metric_pose
from rt_mapping.geometry.projection import back_project
from rt_mapping.runs.artifacts import load_mapping_inputs
from rt_mapping.runs.mapping_run import _json, _quaternion
from rt_mapping.runs.synthetic_mapping import KNOWN_SCALE


def create_synthetic_reference(parent, slam_run, geometry_run):
    from PIL import Image

    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=False)
    (parent / "depth").mkdir()
    inputs = load_mapping_inputs(slam_run, geometry_run)
    cameras = inputs.snapshot.keyframes
    entries, pose_rows = [], []
    # Arbitrary GT world gauge verifies that evaluation uses the correct direction.
    angle = 0.4
    c, s = np.cos(angle), np.sin(angle)
    gauge = np.array([[c, -s, 0, 0.5], [s, c, 0, -0.3], [0, 0, 1, 0.2], [0, 0, 0, 1.]])
    for i, frame_id in enumerate(cameras["frame_id"]):
        width, height = map(int, cameras["image_size_wh"][i])
        v, u = np.indices((height, width))
        rays = back_project(np.column_stack((u.ravel(), v.ravel())), np.ones(u.size), cameras["K"][i])
        pose = cameras["T_wc"][i]
        depth = ((1.2-pose[2, 3])/(rays @ pose[2, :3])*KNOWN_SCALE).reshape(height, width)
        name = f"depth/{frame_id:06d}.png"
        Image.fromarray(np.rint(depth*5000).astype(np.uint16)).save(parent / name)
        world_pose = gauge @ metric_pose(pose, KNOWN_SCALE)
        stamp = float(cameras["timestamp_s"][i])+0.001
        pose_rows.append([stamp, *world_pose[:3, 3], *_quaternion(world_pose[:3, :3])])
        entries.append({"frame_id": int(frame_id), "rgb_timestamp_s": float(cameras["timestamp_s"][i]),
                        "depth_timestamp_s": float(cameras["timestamp_s"][i]), "depth_path": name})
    np.savetxt(parent / "groundtruth.txt", pose_rows, fmt="%.12g")
    dataset = inputs.slam["dataset"]
    _json(parent / "manifest.json", {"dataset": dataset["name"], "sequence_id": dataset["sequence"],
        "source": {"archive_sha256": dataset["checksum"]}, "index_files": {},
        "splits": {dataset["split"]: {"frames": entries}}, "synthetic_only": True})
    return parent, parent / "manifest.json"
