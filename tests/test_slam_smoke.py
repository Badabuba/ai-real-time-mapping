"""Validate actual artifact semantics and run failures without pretending to run SLAM."""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from rt_mapping.slam.smoke import check_smoke_artifacts, execute_upstream


@pytest.fixture
def artifacts(tmp_path):
    directory = tmp_path / "trajectory"
    directory.mkdir()
    poses = np.array([[1.0, 0, 0, 0, 0, 0, 0, 1], [1.1, 1, 0, 0, 0, 0, 0, 1]])
    np.savetxt(directory / "trajectory_final.txt", poses)
    (directory / "other_metrics_info.txt").write_text(
        "num_total_frames: 3\nnum_processed_frames: 3\nnum_lost_frames: 1\npercent_lost: 33.33\n"
    )
    frames = [{"rgb_timestamp_s": v} for v in (1.0, 1.1, 1.2)]
    return tmp_path, frames, poses


def test_smoke_metrics_distinguish_pose_coverage_from_tracking(artifacts):
    path, frames, _ = artifacts
    result = check_smoke_artifacts(path, frames)
    assert result["processed_frames"] == 3 and result["lost_frames"] == 1
    assert result["final_pose_count"] == 2
    assert result["ate_rpe"] == "not evaluated"
    assert "monocular SLAM units" in result["trajectory_units"]


@pytest.mark.parametrize("change, message", [
    (lambda p: p.__setitem__((1, 0), 42), "frozen RGB"),
    (lambda p: p.__setitem__((1, 0), 1), "strictly increasing"),
    (lambda p: p.__setitem__((1, 1), np.nan), "finite TUM"),
    (lambda p: p.__setitem__((1, 7), 0), "non-unit"),
])
def test_invalid_trajectory_rejected(artifacts, change, message):
    path, frames, poses = artifacts
    change(poses)
    np.savetxt(path / "trajectory/trajectory_final.txt", poses)
    with pytest.raises(ValueError, match=message):
        check_smoke_artifacts(path, frames)


def test_zero_exit_with_incomplete_input_is_not_success(artifacts):
    path, frames, _ = artifacts
    (path / "trajectory/other_metrics_info.txt").write_text(
        "num_total_frames: 3\nnum_processed_frames: 2\nnum_lost_frames: 0\n"
    )
    with pytest.raises(ValueError, match="incomplete"):
        check_smoke_artifacts(path, frames)


def test_process_exit_is_preserved(tmp_path):
    with (tmp_path / "log").open("w") as output:
        assert execute_upstream([sys.executable, "-c", "raise SystemExit(7)"],
                                cwd=tmp_path, env=None, output=output, timeout_s=5) == 7


def test_timeout_stops_upstream_worker_group(tmp_path):
    with (tmp_path / "log").open("w") as output:
        with pytest.raises(subprocess.TimeoutExpired):
            execute_upstream([sys.executable, "-c", "import time; time.sleep(20)"],
                             cwd=tmp_path, env=None, output=output, timeout_s=0.1)
