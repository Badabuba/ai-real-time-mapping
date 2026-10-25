"""Known pose errors, timestamp association, metric scale and gauge tests."""
import numpy as np
import pytest

from rt_mapping.evaluation.trajectory import associate_timestamps, quaternion_rotation, read_tum_trajectory, trajectory_metrics


def poses():
    times = np.arange(6, dtype=float) * 0.1
    result = np.repeat(np.eye(4)[None], 6, axis=0)
    result[:, :3, 3] = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 1], [2, 1, 1], [2, 2, 1]]
    return times, result


def test_association_is_unique_and_keeps_timestamp_deltas():
    matches = associate_timestamps([1., 1.01, 1.1], [1.002, 1.1], max_delta_s=0.02)
    np.testing.assert_array_equal(matches, [[0, 0], [2, 1]])
    assert associate_timestamps([0], [1], 0.1).shape == (0, 2)


def test_perfect_world_gauge_ate_and_rpe():
    times, estimate = poses()
    rotation = quaternion_rotation([0, 0, np.sin(0.3), np.cos(0.3)])
    gauge = np.eye(4)
    gauge[:3, :3], gauge[:3, 3] = rotation, [3, -2, 1]
    truth = gauge @ estimate
    result = trajectory_metrics(times, estimate, times+0.005, truth)
    assert result["ate_rmse_m"] < 1e-12
    assert result["rpe_translation_rmse_m"] < 1e-12
    assert result["rpe_rotation_rmse_deg"] < 1e-5
    assert result["association_max_actual_delta_s"] == pytest.approx(0.005)
    assert result["evaluation_transform"]["scale"] == 1
    assert result["scale_fitted_for_evaluation"] is False


def test_sim3_ate_cannot_hide_missing_metric_scale_in_se3_report():
    times, estimate = poses()
    truth = estimate.copy()
    truth[:, :3, 3] *= 3
    se3 = trajectory_metrics(times, estimate, times, truth, alignment="se3")
    sim3 = trajectory_metrics(times, estimate, times, truth, alignment="sim3")
    assert se3["ate_rmse_m"] > 1
    assert se3["rpe_translation_rmse_m"] == pytest.approx(2)
    assert sim3["ate_rmse_m"] < 1e-12
    assert sim3["evaluation_transform"]["scale"] == pytest.approx(3)
    assert sim3["scale_fitted_for_evaluation"] is True


def test_rotation_rpe_uses_camera_relative_transform():
    times, truth = poses()
    estimate = truth.copy()
    estimate[3, :3, :3] = quaternion_rotation([0, 0, np.sin(0.1), np.cos(0.1)])
    result = trajectory_metrics(times, estimate, times, truth)
    assert result["rpe_rotation_rmse_deg"] > 0


def test_tum_rounding_normalizes_quaternion_and_rejects_invalid_rotation(tmp_path):
    path = tmp_path / "gt.txt"
    path.write_text("1 0 0 0 0 0 0.7071 0.7071\n")
    _, result = read_tum_trajectory(path)
    np.testing.assert_allclose(result[0, :3, :3].T @ result[0, :3, :3], np.eye(3), atol=1e-12)
    path.write_text("1 0 0 0 0 0 0 0\n")
    with pytest.raises(ValueError, match="quaternion"):
        read_tum_trajectory(path)


def test_degenerate_gauge_and_insufficient_association_are_explicit():
    times, source = poses()
    line = source.copy()
    line[:, :3, 3] = np.arange(6)[:, None]
    with pytest.raises(ValueError, match="degenerate"):
        trajectory_metrics(times, line, times, line)
    with pytest.raises(ValueError, match="insufficient"):
        trajectory_metrics(times, source, times+10, source)
