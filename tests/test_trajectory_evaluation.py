"""Known pose errors, timestamp association, metric scale and gauge tests."""
import numpy as np
import pytest

from rt_mapping.evaluation.trajectory import (
    GT_MATCH_TOLERANCE_S, associate_timestamps, gt_timestamp_coverage,
    quaternion_rotation, read_tum_trajectory, trajectory_metrics,
)


def poses():
    times = np.arange(6, dtype=float) * 0.1
    result = np.repeat(np.eye(4)[None], 6, axis=0)
    result[:, :3, 3] = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 1], [2, 1, 1], [2, 2, 1]]
    return times, result


def test_association_is_unique_and_keeps_timestamp_deltas():
    matches = associate_timestamps([1., 1.01, 1.1], [1.002, 1.1], max_delta_s=0.02)
    np.testing.assert_array_equal(matches, [[0, 0], [2, 1]])
    assert associate_timestamps([0], [1], 0.1).shape == (0, 2)


def test_fr3_initial_rgb_frames_are_not_confused_with_gt_endpoint_coverage():
    # Three RGB timestamps precede official fr3 GT, but the third is within 20 ms.
    rgb = [1341847980.722988, 1341847980.754743, 1341847980.786856,
           1341847980.822978, 1341847980.854676]
    gt = [1341847980.7900, 1341847980.8000, 1341847980.8100,
          1341847980.8201, 1341847980.8301, 1341847980.8400, 1341847980.8500]
    coverage, matches = gt_timestamp_coverage(range(5), rgb, gt)
    assert coverage["max_timestamp_delta_s"] == GT_MATCH_TOLERANCE_S == 0.02
    assert coverage["total_rgb_frames"] == 5
    assert coverage["matched_gt_frames"] == 3 and coverage["unmatched_gt_frames"] == 2
    assert coverage["coverage_percent"] == 60
    assert coverage["excluded_frame_ids"] == [0, 1]
    assert coverage["matched_frame_ids"] == [2, 3, 4]
    assert {r["reason"] for r in coverage["excluded"]} == {"no_gt_pose_within_tolerance"}
    np.testing.assert_array_equal(matches, associate_timestamps(rgb, gt, 0.02))


def test_coverage_preserves_inclusive_20_ms_boundary_and_explains_competition():
    coverage, matches = gt_timestamp_coverage([4, 8, 9], [0., .1, .2], [.02, .120001, .22])
    assert coverage["matched_frame_ids"] == [4, 9]
    assert coverage["excluded_frame_ids"] == [8]
    assert coverage["excluded"][0]["nearest_gt_delta_s"] == pytest.approx(.020001)
    coverage, matches = gt_timestamp_coverage([3, 7], [1., 1.015], [1.001])
    assert coverage["excluded_frame_ids"] == [7]
    assert coverage["excluded"][0]["reason"] == "gt_pose_within_tolerance_assigned_to_other_frame"
    assert matches.tolist() == [[0, 0]]


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
