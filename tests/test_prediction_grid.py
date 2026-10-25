import numpy as np
import pytest

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.evaluation.prediction_grid import resize_prediction
from rt_mapping.geometry.intrinsics import resize_intrinsics


def prediction(depth):
    return GeometryPrediction(0, 1., np.asarray(depth, np.float32), np.ones(np.shape(depth), bool),
                              None, np.array([[10., 0, .5], [0, 10, .5], [0, 0, 1]]), "fake@1", {}, 1.)


def test_bilinear_half_pixel_and_border_replication():
    pred = prediction([[1, 3], [5, 7]])
    actual = resize_prediction(pred, (4, 4))
    np.testing.assert_allclose(actual.depth_m,
        [[1, 1.5, 2.5, 3], [2, 2.5, 3.5, 4], [4, 4.5, 5.5, 6], [5, 5.5, 6.5, 7]])
    np.testing.assert_array_equal(actual.K_processed, resize_intrinsics(pred.K_processed, (2, 2), (4, 4)))
    assert resize_prediction(pred, (2, 2)) is pred
    assert pred.depth_m.shape == (2, 2) and actual.confidence is None


def test_constant_depth_is_not_rescaled():
    pred = prediction(np.full((4, 6), 2.5))
    actual = resize_prediction(pred, (640, 480))
    np.testing.assert_array_equal(actual.depth_m, 2.5)
