"""Pixel/depth/pose correctness, including raw distorted image grids."""
from dataclasses import replace

import numpy as np
import pytest

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.fusion import VoxelFusion, depth_points, metric_pose, write_ply
from rt_mapping.fusion.voxel import statistical_filter
from rt_mapping.geometry.intrinsics import crop_intrinsics, resize_intrinsics
from rt_mapping.geometry.projection import back_project, project
from rt_mapping.runs.mapping_run import _quaternion


K = np.array([[400., 0, 320], [0, 410., 240], [0, 0, 1]])
D = np.array([0.262383, -0.953104, -0.005358, 0.002628, 1.163314])


@pytest.mark.parametrize("distortion", [None, np.zeros(5), D])
def test_backprojection_projection_roundtrip_after_resize_and_crop(distortion):
    k = crop_intrinsics(resize_intrinsics(K, (640, 480), (378, 294)), (378, 294), (4, 7, 360, 280))
    u, v = np.meshgrid(np.linspace(1, 358, 12), np.linspace(1, 278, 10))
    pixels = np.column_stack((u.ravel(), v.ravel()))
    depth = np.linspace(0.5, 6, len(pixels))
    points = back_project(pixels, depth, k, distortion)
    np.testing.assert_allclose(project(points, k, distortion), pixels, atol=1e-5)
    np.testing.assert_allclose(points[:, 2], depth)


def prediction():
    return GeometryPrediction(frame_id=0, timestamp_s=1., depth_m=np.full((4, 6), 2., dtype=np.float32),
        valid_mask=np.ones((4, 6), dtype=bool), confidence=None, K_processed=np.array([[5., 0, 2.5], [0, 5., 1.5], [0, 0, 1]]),
        model_id="synthetic/test@0", preprocess={}, inference_ms=0.)


def test_metric_pose_scales_only_translation_and_fusion_uses_camera_to_world():
    pose = np.array([[0., -1, 0, 1], [1, 0, 0, 2], [0, 0, 1, 3], [0, 0, 0, 1]])
    metric = metric_pose(pose, 2.5)
    np.testing.assert_array_equal(metric[:3, :3], pose[:3, :3])
    np.testing.assert_array_equal(metric[:3, 3], [2.5, 5., 7.5])
    result = depth_points(prediction(), metric)
    expected = back_project([[0, 0]], [2.], prediction().K_processed) @ metric[:3, :3].T + metric[:3, 3]
    np.testing.assert_allclose(result[0], expected[0])
    np.testing.assert_array_equal(pose[:3, 3], [1, 2, 3])


def test_invalid_pose_and_missing_confidence_fail_explicitly():
    pose = np.eye(4)
    pose[0, 0] = -1
    with pytest.raises(ValueError, match="proper rigid"):
        depth_points(prediction(), pose)
    with pytest.raises(ValueError, match="missing_confidence"):
        depth_points(prediction(), np.eye(4), confidence_threshold=0.5)


def test_depth_mask_range_confidence_and_stride():
    sample = prediction()
    depth = sample.depth_m.copy()
    valid = sample.valid_mask.copy()
    valid[0, 0] = False
    depth[0, 0] = np.nan
    depth[2, 2] = 10
    confidence = np.ones(depth.shape, dtype=np.float32)
    confidence[2, 4] = 0.1
    sample = replace(sample, depth_m=depth, valid_mask=valid, confidence=confidence)
    points = depth_points(sample, np.eye(4), confidence_threshold=0.5, pixel_stride=2)
    assert len(points) == 3  # 6 strided samples - invalid - range - confidence.


def test_voxel_centroids_are_weighted_by_points_across_frames_and_handle_negative_cells(tmp_path):
    fusion = VoxelFusion(1)
    fusion.add([[0.1, 0, 0], [0.3, 0, 0], [-0.1, 0, 0]])
    fusion.add([[0.8, 0, 0]])
    points, counts = fusion.cloud()
    np.testing.assert_allclose(points, [[-0.1, 0, 0], [0.4, 0, 0]])
    np.testing.assert_array_equal(counts, [1, 3])
    assert fusion.input_points == 4
    assert len(fusion.cloud(min_observations=2)[0]) == 1
    path = tmp_path / "map.ply"
    write_ply(path, points)
    assert "comment units meters" in path.read_text()
    with pytest.raises(FileExistsError):
        write_ply(path, points)


def test_voxel_capacity_failure_is_atomic():
    fusion = VoxelFusion(1, max_voxels=1)
    fusion.add([[0, 0, 0]])
    with pytest.raises(ValueError, match="map_capacity_exceeded"):
        fusion.add([[2, 0, 0], [0.5, 0, 0]])
    np.testing.assert_array_equal(fusion.cloud()[0], [[0, 0, 0]])
    assert fusion.input_points == 1


def test_statistical_filter_removes_isolated_outlier():
    pytest.importorskip("scipy")
    points = np.vstack([np.random.default_rng(0).normal(0, 0.01, (50, 3)), [[10, 10, 10]]])
    keep = statistical_filter(points, neighbors=5)
    assert not keep[-1] and keep[:-1].sum() > 40


@pytest.mark.parametrize("angle", [0., 0.5, 2., np.pi])
def test_exported_quaternion_rotation_direction(angle):
    c, s = np.cos(angle), np.sin(angle)
    q = _quaternion(np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]))
    np.testing.assert_allclose(q, [0, 0, np.sin(angle/2), np.cos(angle/2)], atol=1e-12)
