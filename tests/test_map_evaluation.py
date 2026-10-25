import numpy as np
import pytest

from rt_mapping.evaluation.map_geometry import evaluate_map


def test_identical_maps_have_zero_error_and_perfect_fscore():
    points = np.random.default_rng(0).normal(size=(100, 3))
    result = evaluate_map(points, points)
    assert result["chamfer_l1_m"] == 0
    assert all(s["precision"] == s["recall"] == s["fscore"] == 1 for s in result["fscores"])


def test_sparse_cloud_has_accuracy_but_low_completeness():
    reference = np.column_stack((np.arange(10.), np.zeros((10, 2))))
    result = evaluate_map(reference[:1], reference, thresholds_m=[0.1])
    assert result["accuracy_mean_m"] == 0
    assert result["completeness_mean_m"] == pytest.approx(4.5)
    assert result["chamfer_l1_m"] == pytest.approx(2.25)
    assert result["fscores"][0]["precision"] == 1
    assert result["fscores"][0]["recall"] == 0.1


def test_common_crop_and_voxel_preprocessing_are_explicit():
    reference = np.array([[0, 0, 0], [0.001, 0, 0], [10, 10, 10]])
    result = evaluate_map(reference, reference, voxel_size_m=0.02, crop_bounds=[[-1,-1,-1],[1,1,1]])
    assert result["estimate_points"] == result["reference_points"] == 1
    with pytest.raises(ValueError, match="empty"):
        evaluate_map(reference, reference, crop_bounds=[[2,2,2],[3,3,3]])


@pytest.mark.parametrize("thresholds", [[0], [0.1, 0.02], [float("nan")]])
def test_invalid_metric_thresholds_rejected(thresholds):
    with pytest.raises(ValueError, match="thresholds"):
        evaluate_map([[0,0,0]], [[0,0,0]], thresholds_m=thresholds)
