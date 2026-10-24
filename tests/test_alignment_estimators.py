"""Known transforms, gross outliers, direction, and degeneracy gates."""
import numpy as np
import pytest

from rt_mapping.alignment import AlignmentError, estimate_scale, estimate_sim3


def test_scale_recovers_metric_units_with_gross_outliers():
    rng = np.random.default_rng(4)
    source = rng.uniform(0.3, 4, 150)
    target = source * 2.75
    target[:45] *= 4
    result = estimate_scale(source, target, threshold_m=0.01)
    assert result.scale == pytest.approx(2.75)
    assert result.inliers.sum() == 105
    np.testing.assert_array_equal(result.R, np.eye(3))
    np.testing.assert_array_equal(result.t, 0)
    report = result.to_dict()
    assert report["source_frame"] == "slam_world"
    assert report["inlier_ratio"] == 0.7
    assert report["median_residual_m"] < 1e-12


@pytest.mark.parametrize("bad", [0., -1., np.nan, np.inf])
def test_scale_rejects_invalid_samples(bad):
    source = np.ones(40)
    source[0] = bad
    with pytest.raises(AlignmentError, match="invalid_scale"):
        estimate_scale(source, np.ones(40))


def test_scale_rejects_too_few_pairs_and_weak_consensus():
    with pytest.raises(AlignmentError, match="insufficient_correspondences"):
        estimate_scale(np.ones(29), np.ones(29))
    with pytest.raises(AlignmentError, match="insufficient_correspondences"):
        estimate_scale(np.ones(60), np.arange(1, 61.), threshold_m=0.01)


@pytest.mark.parametrize("threshold", [0, -1, np.nan, np.inf])
def test_bad_threshold_rejected(threshold):
    with pytest.raises(ValueError, match="threshold"):
        estimate_scale(np.ones(50), np.ones(50), threshold_m=threshold)


def known_sim3(planar=False):
    rng = np.random.default_rng(92)
    source = rng.normal(size=(150, 3))
    if planar:
        source[:, 2] = 0
    angle = 0.8
    rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
    translation = np.array([2., -3., 0.7])
    target = 1.7 * source @ rotation.T + translation
    target[:40] = rng.uniform(-8, 8, (40, 3))
    return source, target, rotation, translation


@pytest.mark.parametrize("planar", [False, True])
def test_sim3_recovers_rotation_translation_scale_with_outliers(planar):
    source, target, rotation, translation = known_sim3(planar)
    result = estimate_sim3(source, target, threshold_m=1e-5, seed=42)
    assert result.scale == pytest.approx(1.7, abs=1e-10)
    np.testing.assert_allclose(result.R, rotation, atol=1e-10)
    np.testing.assert_allclose(result.t, translation, atol=1e-10)
    np.testing.assert_allclose(result.transform(source[40:]), target[40:], atol=1e-10)
    assert result.inliers.sum() == 110
    assert np.linalg.det(result.R) == pytest.approx(1)
    second = estimate_sim3(source, target, threshold_m=1e-5, seed=42)
    np.testing.assert_array_equal(result.inliers, second.inliers)


def test_sim3_noisy_data_remains_accurate():
    source, target, rotation, translation = known_sim3()
    target[40:] += np.random.default_rng(1).normal(0, 0.002, (110, 3))
    result = estimate_sim3(source, target, threshold_m=0.015)
    assert result.scale == pytest.approx(1.7, abs=0.002)
    np.testing.assert_allclose(result.R, rotation, atol=0.002)
    np.testing.assert_allclose(result.t, translation, atol=0.002)


def test_sim3_rejects_collinear_and_reflected_data():
    line = np.tile(np.arange(40.)[:, None], (1, 3))
    with pytest.raises(AlignmentError, match="degenerate_geometry"):
        estimate_sim3(line, line * 2)
    points = np.random.default_rng(0).normal(size=(80, 3))
    with pytest.raises(AlignmentError):
        estimate_sim3(points, points * [-1, 1, 1], threshold_m=1e-6, min_ratio=0.9)


@pytest.mark.parametrize("points", [np.ones((3, 2)), np.ones((2, 3)), np.full((40, 3), np.nan)])
def test_sim3_rejects_malformed_points(points):
    with pytest.raises(ValueError):
        estimate_sim3(points, points)
