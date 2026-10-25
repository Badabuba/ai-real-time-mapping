"""All-input-frame online SLAM observations; missing poses are never identities."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rt_mapping.geometry.projection import validate_pose

STATES = frozenset(("NO_IMAGES_YET", "NOT_INITIALIZED", "OK", "LOST", "RELOCALIZE", "INIT_RELOCALIZE", "UNKNOWN"))
POSE_FIELDS = ("tx", "ty", "tz", "qx", "qy", "qz", "qw")
TRAJECTORY_FIELDS = ("frame_id", "timestamp_s", "tracking_state", "state_reason", *POSE_FIELDS,
                     "pose_reason", "is_keyframe_created", "created_keyframe_frame_ids", "keyframe_reason", "error")
TIMING_FIELDS = ("frame_id", "timestamp_s", "tracking_ms", "mapping_ms", "mapping_reason", "total_ms", "total_reason")
MAPPING_REASON = "not_attributable_to_input_frame; background mapping may overlap tracking"
TOTAL_REASON = "whole_input_iteration_not_instrumented; image_decode_and_output_are_excluded"


def validate_frames(frames):
    ids = [f["frame_id"] for f in frames]
    stamps = np.array([f["rgb_timestamp_s"] for f in frames], dtype=float)
    if (not len(frames) or any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids)
            or any(isinstance(f["rgb_timestamp_s"], (bool, np.bool_)) for f in frames)
            or not np.isfinite(stamps).all() or np.any(np.diff(stamps) <= 0)):
        raise ValueError("frozen frames need unique nonnegative IDs and strictly ordered timestamps")
    return stamps


def pose_values(pose):
    """Proper T_wc to translation/xyzw, with a deterministic quaternion sign."""
    pose = validate_pose(pose)
    r = pose[:3, :3]
    matrix = np.array([
        [r[0,0]-r[1,1]-r[2,2], r[0,1]+r[1,0], r[0,2]+r[2,0], r[2,1]-r[1,2]],
        [r[0,1]+r[1,0], r[1,1]-r[0,0]-r[2,2], r[1,2]+r[2,1], r[0,2]-r[2,0]],
        [r[0,2]+r[2,0], r[1,2]+r[2,1], r[2,2]-r[0,0]-r[1,1], r[1,0]-r[0,1]],
        [r[2,1]-r[1,2], r[0,2]-r[2,0], r[1,0]-r[0,1], np.trace(r)]]) / 3
    _, vectors = np.linalg.eigh(matrix)
    q = vectors[:, -1]
    if q[np.argmax(np.abs(q))] < 0:
        q = -q
    return np.r_[pose[:3, 3], q]


@dataclass(frozen=True)
class SlamFrame:
    frame_id: int
    timestamp_s: float
    tracking_state: str
    state_reason: str | None
    T_wc: np.ndarray | None
    pose_reason: str | None
    created_keyframe_frame_ids: tuple[int, ...] | None
    keyframe_reason: str | None
    tracking_ms: float
    error: str | None = None

    def validate(self):
        if (type(self.frame_id) is not int or self.frame_id < 0 or isinstance(self.timestamp_s, (bool, np.bool_))
                or not np.isfinite(self.timestamp_s)):
            raise ValueError("invalid frame identity")
        if self.tracking_state not in STATES or (self.tracking_state == "UNKNOWN" and not self.state_reason):
            raise ValueError("unknown tracking states require a reason")
        if self.T_wc is None:
            if not self.pose_reason:
                raise ValueError("missing pose requires a reason")
        elif self.tracking_state != "OK" or self.error or self.pose_reason:
            raise ValueError("only a successful OK observation can contain a pose")
        else:
            validate_pose(self.T_wc)
        if self.created_keyframe_frame_ids is None:
            if not self.keyframe_reason:
                raise ValueError("unobservable keyframes require a reason")
        elif (self.keyframe_reason or any(type(i) is not int or i < 0 for i in self.created_keyframe_frame_ids)
              or len(set(self.created_keyframe_frame_ids)) != len(self.created_keyframe_frame_ids)):
            raise ValueError("invalid keyframe events")
        if isinstance(self.tracking_ms, bool) or not np.isfinite(self.tracking_ms) or self.tracking_ms < 0:
            raise ValueError("tracking_ms must be a finite nonnegative measurement")


def validate_rows(rows, frames):
    validate_frames(frames)
    if len(rows) != len(frames):
        raise ValueError("tracking row count differs from frozen input frames")
    created = set()
    available = set()
    for row, frame in zip(rows, frames):
        row.validate()
        if row.frame_id != frame["frame_id"] or abs(row.timestamp_s-frame["rgb_timestamp_s"]) > 1e-6:
            raise ValueError("tracking rows differ from frozen frame IDs/timestamps")
        available.add(row.frame_id)
        for event in row.created_keyframe_frame_ids or ():
            if event not in available or event in created:
                raise ValueError("keyframe event uses a future/unknown frame or was duplicated")
            created.add(event)
