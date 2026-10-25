"""Opt-in installed-backend API check; no images, tracking or worker processes.

WP2_NATIVE_SPARSE_TEST=1 .venv-pyslam/bin/python -O -m unittest discover \
    -s tests -p test_pyslam_sparse_native.py -v
"""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np


@unittest.skipUnless(os.environ.get("WP2_NATIVE_SPARSE_TEST") == "1", "requires installed pinned pySLAM runtime")
class NativeSparseExportTest(unittest.TestCase):
    def test_actual_map_keyframe_point_apis(self):
        root = Path(__file__).resolve().parents[1]
        source = Path(os.environ.get("WP2_PYSLAM_ROOT", root / "external/pyslam"))
        sys.path.insert(0, str(root / "src"))
        sys.path.insert(0, str(source))
        os.environ["PYSLAM_USE_CPP"] = "false"
        # Match main's required import order: Config registers native lib paths.
        from pyslam.config import Config
        from pyslam.slam.slam import Slam
        from pyslam.slam.camera import PinholeCamera
        from pyslam.slam.frame import Frame
        from pyslam.slam.keyframe import KeyFrame
        from pyslam.slam.map_point import MapPoint
        from pyslam.slam.map import Map
        from rt_mapping.slam.pyslam_export import export_pyslam_snapshot
        from rt_mapping.slam.sparse import check_sparse_export

        camera = PinholeCamera()
        camera.K = np.array([[100., 0, 320], [0, 100, 240], [0, 0, 1]])
        camera.D = np.array([0.1, 0, 0, 0, 0])
        camera.width, camera.height = 640, 480
        map_ = Map()
        points = [MapPoint(np.array(xyz), np.array([100, 120, 140]))
                  for xyz in ([0.2, 0.1, 2.], [0.5, -0.1, 3.])]
        frames = []
        for frame_id, stamp, tx in [(10, 1., 0.), (27, 1.1, 0.1)]:
            T_cw = np.eye(4)
            T_cw[0, 3] = -tx
            frame = Frame(img=None, camera=camera, pose=T_cw, id=frame_id + 100, timestamp=stamp)
            pcs = np.array([point.pt() for point in points])
            pcs[:, 0] -= tx
            projected = (camera.K @ pcs.T).T
            frame.kpsu = projected[:, :2] / projected[:, 2:]
            frame.kps = frame.kpsu + [1.5, -0.75]
            frame.points = list(points)
            kf = KeyFrame(frame)
            map_.add_keyframe(kf)
            for index, point in enumerate(points):
                point.add_observation(kf, index)
            frames.append({"frame_id": frame_id, "rgb_timestamp_s": stamp})
        for point in points:
            map_.add_point(point)
        slam = SimpleNamespace(map=map_, has_quit=True, local_mapping=None, loop_closing=None,
                               semantic_mapping=None, volumetric_integrator=None, GBA=None, GBA_on_demand=None)
        with tempfile.TemporaryDirectory(prefix="wp2-native-sparse-") as directory:
            out = Path(directory) / "sparse"
            export_pyslam_snapshot(slam, out, frames)
            self.assertEqual(check_sparse_export(out)["counts"],
                             {"landmarks": 2, "keyframes": 2, "observations": 4})
            with np.load(out / "keyframes.npz", allow_pickle=False) as archive:
                self.assertEqual(archive["frame_id"].tolist(), [10, 27])


if __name__ == "__main__":
    unittest.main()
