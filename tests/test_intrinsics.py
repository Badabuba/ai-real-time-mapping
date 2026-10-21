from __future__ import annotations

import numpy as np
import pytest

from rt_mapping.geometry import crop_intrinsics, resize_intrinsics

# TUM freiburg1 RGB intrinsics (rt_mapping.data.tum), raw 640x480.
K_FR1 = np.array([[517.3, 0.0, 318.6], [0.0, 516.5, 255.3], [0.0, 0.0, 1.0]])
RAW_SIZE = (640, 480)
# DA3 process_res=384 shape from results/runs/tum_fr1_xyz_da3metric/run.json (H=294, W=378).
DA3_SIZE = (378, 294)
# processed_intrinsics recorded by that run (DA3 preprocessor, float32); file is not read here.
DA3_RECORDED_K = np.array(
    [
        [305.5303039550781, 0.0, 188.17312622070312],
        [0.0, 316.3562927246094, 156.3712615966797],
        [0.0, 0.0, 1.0],
    ]
)


def _project(k: np.ndarray, points: np.ndarray) -> np.ndarray:
    uvw = points @ k.T
    return uvw[:, :2] / uvw[:, 2:3]


def test_anisotropic_resize_matches_hand_computed_values() -> None:
    k = resize_intrinsics(K_FR1, RAW_SIZE, DA3_SIZE)
    sx, sy = 378 / 640, 294 / 480
    assert (sx, sy) == (0.590625, 0.6125)
    expected = np.array(
        [[305.5303125, 0.0, 187.9684375], [0.0, 316.35625, 156.1775], [0.0, 0.0, 1.0]]
    )
    np.testing.assert_allclose(k, expected, rtol=0, atol=1e-9)
    assert k.dtype == np.float64


def test_resize_vs_recorded_da3_intrinsics() -> None:
    # DA3 scales cx by sx only; with integer pixel centres the principal point
    # differs by 0.5 * (s - 1). Focal lengths agree.
    k = resize_intrinsics(K_FR1, RAW_SIZE, DA3_SIZE)
    np.testing.assert_allclose(k[[0, 1], [0, 1]], DA3_RECORDED_K[[0, 1], [0, 1]], atol=1e-4)
    offset = k[:2, 2] - DA3_RECORDED_K[:2, 2]
    np.testing.assert_allclose(offset, [-0.2046875, -0.19375], atol=1e-4)


def test_resize_maps_pixel_centres_and_image_edges() -> None:
    k_dst = resize_intrinsics(K_FR1, RAW_SIZE, DA3_SIZE)
    sx, sy = DA3_SIZE[0] / RAW_SIZE[0], DA3_SIZE[1] / RAW_SIZE[1]
    rng = np.random.default_rng(0)
    points = np.column_stack([rng.uniform(-1, 1, 50), rng.uniform(-1, 1, 50), rng.uniform(0.5, 5, 50)])
    uv_src = _project(K_FR1, points)
    uv_dst = _project(k_dst, points)
    np.testing.assert_allclose(uv_dst[:, 0], (uv_src[:, 0] + 0.5) * sx - 0.5, atol=1e-9)
    np.testing.assert_allclose(uv_dst[:, 1], (uv_src[:, 1] + 0.5) * sy - 0.5, atol=1e-9)
    # Image edges [-0.5, W-0.5] map onto the new image's edges.
    for u_src, u_dst in ((-0.5, -0.5), (RAW_SIZE[0] - 0.5, DA3_SIZE[0] - 0.5)):
        x = (u_src - K_FR1[0, 2]) / K_FR1[0, 0]
        assert _project(k_dst, np.array([[x, 0.0, 1.0]]))[0, 0] == pytest.approx(u_dst, abs=1e-9)


def test_crop_offsets_principal_point() -> None:
    k = crop_intrinsics(K_FR1, RAW_SIZE, (10, 20, 600, 440))
    expected = K_FR1.copy()
    expected[0, 2] -= 10
    expected[1, 2] -= 20
    np.testing.assert_array_equal(k, expected)


@pytest.mark.parametrize(
    "box",
    [(-1, 0, 100, 100), (0, -1, 100, 100), (0, 0, 0, 100), (600, 0, 41, 100), (0, 400, 100, 81), (0.5, 0, 100, 100)],
)
def test_crop_rejects_boxes_outside_image_or_non_integer(box: tuple) -> None:
    with pytest.raises(ValueError):
        crop_intrinsics(K_FR1, RAW_SIZE, box)


def test_resize_then_crop_and_crop_then_resize() -> None:
    sx, sy = 0.5, 0.75
    # resize 640x480 -> 320x360, then crop (8, 4, 300, 350)
    k = crop_intrinsics(resize_intrinsics(K_FR1, RAW_SIZE, (320, 360)), (320, 360), (8, 4, 300, 350))
    expected = np.array(
        [
            [sx * 517.3, 0.0, (318.6 + 0.5) * sx - 0.5 - 8],
            [0.0, sy * 516.5, (255.3 + 0.5) * sy - 0.5 - 4],
            [0.0, 0.0, 1.0],
        ]
    )
    np.testing.assert_allclose(k, expected, atol=1e-9)
    # crop (40, 0, 560, 480), then resize 560x480 -> 280x240
    k = resize_intrinsics(crop_intrinsics(K_FR1, RAW_SIZE, (40, 0, 560, 480)), (560, 480), (280, 240))
    expected = np.array(
        [
            [0.5 * 517.3, 0.0, (318.6 - 40 + 0.5) * 0.5 - 0.5],
            [0.0, 0.5 * 516.5, (255.3 + 0.5) * 0.5 - 0.5],
            [0.0, 0.0, 1.0],
        ]
    )
    np.testing.assert_allclose(k, expected, atol=1e-9)


def test_identity_operations_and_input_not_mutated() -> None:
    original = K_FR1.copy()
    np.testing.assert_array_equal(resize_intrinsics(K_FR1, RAW_SIZE, RAW_SIZE), K_FR1)
    np.testing.assert_array_equal(crop_intrinsics(K_FR1, RAW_SIZE, (0, 0, 640, 480)), K_FR1)
    np.testing.assert_array_equal(K_FR1, original)


@pytest.mark.parametrize(
    "k, src, dst",
    [
        (np.eye(2), RAW_SIZE, DA3_SIZE),
        (np.array([[1.0, 0, 0], [0, 1, 0], [0, 0, 2]]), RAW_SIZE, DA3_SIZE),
        (K_FR1, (0, 480), DA3_SIZE),
        (K_FR1, RAW_SIZE, (378.0, 294)),
    ],
)
def test_resize_rejects_bad_inputs(k: np.ndarray, src: tuple, dst: tuple) -> None:
    with pytest.raises(ValueError):
        resize_intrinsics(k, src, dst)
