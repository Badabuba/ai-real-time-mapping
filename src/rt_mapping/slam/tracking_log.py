"""Causal per-call observations for pinned pySLAM, without importing the backend.

Only original Slam.track wall time is measured. Mapping and whole-loop latency
are intentionally unmeasured. Successful Map.add_keyframe calls are events;
later keyframe culling cannot rewrite the log.
"""
from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
import csv
from functools import wraps
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from rt_mapping.contracts.slam import (MAPPING_REASON, POSE_FIELDS, STATES, TIMING_FIELDS,
    TOTAL_REASON, TRAJECTORY_FIELDS, SlamFrame, pose_values, validate_frames, validate_rows)
from rt_mapping.evaluation.trajectory import quaternion_rotation
from rt_mapping.geometry.projection import validate_pose

SCHEMA = "rt_mapping.slam_tracking_export/v1"
FILES = ("trajectory_all.csv", "timing.csv")
METADATA = "tracking_export.json"


def _number(value):
    return format(float(value), ".17g")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TrackingLog:
    def __init__(self, directory, frames):
        self.stamps = validate_frames(frames)
        self.frames = frames
        self.directory = Path(directory)
        self.rows = []
        self.closed = False
        if any((self.directory / name).exists() for name in (*FILES, METADATA)):
            raise ValueError("tracking export already exists; never overwrite a run")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.streams = [(self.directory / name).open("x", encoding="utf-8", newline="") for name in FILES]
        self.writers = [csv.writer(stream, lineterminator="\n") for stream in self.streams]
        for writer, fields in zip(self.writers, (TRAJECTORY_FIELDS, TIMING_FIELDS)):
            writer.writerow(fields)
        for stream in self.streams:
            stream.flush()

    def frame_for(self, timestamp):
        matches = np.flatnonzero(np.abs(self.stamps-float(timestamp)) <= 1e-6)
        if len(matches) != 1:
            raise ValueError("backend timestamp does not uniquely identify a frozen input")
        return self.frames[int(matches[0])]

    def append(self, row):
        row.validate()
        index = len(self.rows)
        if index >= len(self.frames) or row.frame_id != self.frames[index]["frame_id"]:
            raise ValueError("tracking input order/coverage differs from frozen frames")
        pose = [""] * 7 if row.T_wc is None else [_number(v) for v in pose_values(row.T_wc)]
        events = row.created_keyframe_frame_ids
        self.writers[0].writerow([row.frame_id, _number(row.timestamp_s), row.tracking_state, row.state_reason or "",
            *pose, row.pose_reason or "", "" if events is None else int(bool(events)),
            "" if events is None else json.dumps(events, separators=(",", ":")), row.keyframe_reason or "", row.error or ""])
        self.writers[1].writerow([row.frame_id, _number(row.timestamp_s), _number(row.tracking_ms),
                                  "", MAPPING_REASON, "", TOTAL_REASON])
        for stream in self.streams:
            stream.flush()  # upstream can terminate with os._exit
        self.rows.append(row)

    def finish(self):
        if self.closed:
            return
        for stream in self.streams:
            stream.close()
        self.closed = True
        validate_rows(self.rows, self.frames)
        metadata = {"schema": SCHEMA, "frame_count": len(self.rows),
            "state_counts": dict(sorted(Counter(r.tracking_state for r in self.rows).items())),
            "pose_count": sum(r.T_wc is not None for r in self.rows),
            "keyframes_created": sum(len(r.created_keyframe_frame_ids or ()) for r in self.rows),
            "observation_errors": sum(bool(r.error) for r in self.rows),
            "files": {name: _digest(self.directory / name) for name in FILES},
            "pose_units": "monocular SLAM units; no metric-scale recovery",
            "pose_frame": "upstream world at track return; not normalized to the final sparse snapshot",
            "pose_temporality": "online/causal; never replaced with final optimized poses",
            "keyframe_semantics": "successful Map.add_keyframe calls during this track call; not final retained membership",
            "tracking_timing_scope": "Slam.track wall time; includes waits and in-call event-hook overhead; excludes post-call pose/CSV work",
            "mapping_timing": MAPPING_REASON, "total_timing": TOTAL_REASON}
        with (self.directory / METADATA).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(metadata, sort_keys=True, indent=2, allow_nan=False) + "\n")
        read_tracking_log(self.directory, self.frames)


def read_tracking_log(directory, frames):
    directory = Path(directory)
    metadata = json.loads((directory / METADATA).read_text(encoding="utf-8"))
    if metadata.get("schema") != SCHEMA or set(metadata.get("files", {})) != set(FILES):
        raise ValueError("invalid tracking export schema/files")
    for name, digest in metadata["files"].items():
        if _digest(directory / name) != digest:
            raise ValueError("tracking export checksum mismatch")
    tables = []
    for name, fields in zip(FILES, (TRAJECTORY_FIELDS, TIMING_FIELDS)):
        with (directory / name).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != fields:
                raise ValueError("tracking export field mismatch")
            table = list(reader)
            if any(set(row) != set(fields) or None in row.values() for row in table):
                raise ValueError("malformed tracking CSV row")
            tables.append(table)
    if len(tables[0]) != len(tables[1]):
        raise ValueError("trajectory/timing row count differs")
    rows = []
    for row, timing in zip(*tables):
        if any(row[k] != timing[k] for k in ("frame_id", "timestamp_s")):
            raise ValueError("trajectory/timing identity mismatch")
        if (timing["mapping_ms"] or timing["total_ms"] or timing["mapping_reason"] != MAPPING_REASON
                or timing["total_reason"] != TOTAL_REASON):
            raise ValueError("unmeasured timing must remain blank with its scope reason")
        values = [row[k] for k in POSE_FIELDS]
        pose = None
        if any(values):
            if not all(values):
                raise ValueError("partial pose is invalid")
            xyzq = np.array(values, dtype=float)
            if not np.isfinite(xyzq).all() or not np.isclose(np.linalg.norm(xyzq[3:]), 1., rtol=0, atol=1e-8):
                raise ValueError("invalid serialized translation/xyzw")
            pose = np.eye(4)
            pose[:3, :3] = quaternion_rotation(xyzq[3:])
            pose[:3, 3] = xyzq[:3]
        events = None if row["created_keyframe_frame_ids"] == "" else json.loads(row["created_keyframe_frame_ids"])
        if events is not None and not isinstance(events, list):
            raise ValueError("keyframe events must be a list")
        if row["is_keyframe_created"] != ("" if events is None else str(int(bool(events)))):
            raise ValueError("keyframe flag differs from creation events")
        rows.append(SlamFrame(int(row["frame_id"]), float(row["timestamp_s"]), row["tracking_state"],
            row["state_reason"] or None, pose, row["pose_reason"] or None,
            None if events is None else tuple(events), row["keyframe_reason"] or None,
            float(timing["tracking_ms"]), row["error"] or None))
    validate_rows(rows, frames)
    expected = {"frame_count": len(rows), "state_counts": dict(Counter(r.tracking_state for r in rows)),
        "pose_count": sum(r.T_wc is not None for r in rows),
        "keyframes_created": sum(len(r.created_keyframe_frame_ids or ()) for r in rows),
        "observation_errors": sum(bool(r.error) for r in rows)}
    if any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError("tracking metadata counts differ from CSV")
    return rows, metadata


def install_tracking_export(slam_class, map_class, directory, frames, *, clock=time.perf_counter_ns):
    """Observe native methods, preserving return values, exceptions and shutdown."""
    if slam_class.__dict__.get("_rt_mapping_tracking_installed", False):
        raise ValueError("tracking export already installed on this class")
    log = TrackingLog(directory, frames)
    active = ContextVar("rt_mapping_tracking_call", default=None)
    original_track, original_add, original_quit = slam_class.track, map_class.add_keyframe, slam_class.quit

    @wraps(original_add)
    def add_keyframe(self, keyframe, *args, **kwargs):
        result = original_add(self, keyframe, *args, **kwargs)
        current = active.get()
        if current is not None and self is current["map"]:
            try:
                current["events"].append(log.frame_for(keyframe.timestamp)["frame_id"])
            except Exception as exc:
                current["keyframe_error"] = f"keyframe_observation_failed:{type(exc).__name__}"
        return result

    @wraps(original_track)
    def track(self, img, img_right, depth, img_id, timestamp=None, mask=None, mask_right=None):
        frame = log.frame_for(timestamp)
        current = {"map": self.map, "events": [], "keyframe_error": None}
        token = active.set(current)
        error = None
        start = clock()
        try:
            return original_track(self, img, img_right, depth, img_id, timestamp, mask, mask_right)
        except BaseException as exc:
            error = f"track_raised:{type(exc).__name__}"
            raise
        finally:
            elapsed_ms = (clock()-start)/1_000_000
            active.reset(token)
            tracking = getattr(self, "tracking", None)
            state = getattr(getattr(tracking, "state", None), "name", None)
            state_reason = None
            if state not in STATES or state == "UNKNOWN":
                state, state_reason = "UNKNOWN", "upstream_state_unobservable"
            pose, reason = None, error or f"tracking_state:{state}"
            if state == "OK" and error is None:
                try:
                    current_frame = tracking.f_cur
                    if abs(float(current_frame.timestamp)-frame["rgb_timestamp_s"]) > 1e-6:
                        raise ValueError("stale current frame")
                    pose = validate_pose(current_frame.Twc()).copy()
                    reason = None
                except Exception as exc:
                    reason = f"current_pose_unobservable:{type(exc).__name__}"
            log.append(SlamFrame(frame["frame_id"], float(frame["rgb_timestamp_s"]), state, state_reason,
                pose, reason, None if current["keyframe_error"] else tuple(current["events"]),
                current["keyframe_error"], elapsed_ms, error))

    @wraps(original_quit)
    def quit(self, *args, **kwargs):
        result = original_quit(self, *args, **kwargs)
        log.finish()  # normal shutdown, before upstream's forced exit
        return result

    slam_class.track, slam_class.quit = track, quit
    map_class.add_keyframe = add_keyframe
    slam_class._rt_mapping_tracking_installed = True
    return log
