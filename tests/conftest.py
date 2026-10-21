"""Shared test helpers: a synthetic TUM sequence on disk and a fake DA3 backend.

Nothing here imports torch or depth_anything_3, and nothing downloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pytest

from rt_mapping.data.manifest import build_tum_manifest, dump_manifest
from rt_mapping.data.tum import rgb_intrinsics
from rt_mapping.adapters.da3_metric import Da3BackendInfo, RawDa3Output, da3_preprocess_plan, da3_processed_size

SYNTH_SEQUENCE = "rgbd_dataset_freiburg1_synth"
SYNTH_URL = "https://example.invalid/rgbd_dataset_freiburg1_synth.tgz"
GT_DEPTH_M = 1.5


@dataclass(frozen=True)
class SynthRepo:
    root: Path
    sequence_dir: Path
    archive: Path
    manifest_path: Path
    manifest_rel: str
    n_frames: int


def make_synthetic_repo(root: Path, n_frames: int = 3) -> SynthRepo:
    from PIL import Image

    seq = root / "data" / "raw" / "tum_rgbd" / SYNTH_SEQUENCE
    (seq / "rgb").mkdir(parents=True)
    (seq / "depth").mkdir()
    rgb_lines = ["# color images", "# timestamp filename"]
    depth_lines = ["# depth maps", "# timestamp filename"]
    yy, xx = np.mgrid[0:480, 0:640]
    for i in range(n_frames):
        ts = 100.0 + 0.1 * i
        rgb_name = f"rgb/{ts:.6f}.png"
        depth_name = f"depth/{ts + 0.005:.6f}.png"
        rgb = np.stack([(xx + 10 * i) % 256, (yy + 20 * i) % 256, (xx + yy) % 256], axis=-1).astype(np.uint8)
        Image.fromarray(rgb).save(seq / rgb_name)
        depth = np.full((480, 640), int(GT_DEPTH_M * 5000), dtype=np.uint16)
        depth[:, :8] = 0  # missing measurements
        Image.fromarray(depth).save(seq / depth_name)
        rgb_lines.append(f"{ts:.6f} {rgb_name}")
        depth_lines.append(f"{ts + 0.005:.6f} {depth_name}")
    (seq / "rgb.txt").write_text("\n".join(rgb_lines) + "\n", encoding="utf-8")
    (seq / "depth.txt").write_text("\n".join(depth_lines) + "\n", encoding="utf-8")
    archive = seq.parent / f"{SYNTH_SEQUENCE}.tgz"
    archive.write_bytes(b"synthetic archive bytes")

    manifest = build_tum_manifest(seq, archive, root, SYNTH_URL, smoke_frames=n_frames)
    manifest_rel = "data/manifests/synth.json"
    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(dump_manifest(manifest), encoding="utf-8")
    return SynthRepo(root, seq, archive, manifest_path, manifest_rel, n_frames)


@pytest.fixture
def synth_repo(tmp_path: Path) -> SynthRepo:
    return make_synthetic_repo(tmp_path / "repo")


def metric_constant_raw(target_m: float, process_res: int = 384) -> Callable[[np.ndarray, tuple[int, int]], np.ndarray]:
    """Raw DA3 output that converts to target_m metres for a 640x480 freiburg1 frame."""
    k_processed, _, _ = da3_preprocess_plan(rgb_intrinsics("freiburg1"), 640, 480, process_res)
    focal = (k_processed[0, 0] + k_processed[1, 1]) / 2.0

    def make(rgb: np.ndarray, hw: tuple[int, int]) -> np.ndarray:
        return np.full(hw, target_m * 300.0 / focal, dtype=np.float32)

    return make


class FakeDa3Backend:
    """Stands in for TorchDa3Backend. Output depends only on its inputs and call count."""

    def __init__(
        self,
        *,
        autocast: str = "bfloat16",
        depth_fn: Callable[[np.ndarray, tuple[int, int]], np.ndarray] | None = None,
        conf: bool = False,
        is_metric: bool = False,
        intrinsics: np.ndarray | None = None,
        fail_load: Exception | None = None,
        fail_on_call: tuple[int, Exception] | None = None,
    ) -> None:
        self.autocast = autocast
        self.depth_fn = depth_fn
        self.conf = conf
        self.is_metric = is_metric
        self.intrinsics = intrinsics
        self.fail_load = fail_load
        self.fail_on_call = fail_on_call
        self.load_calls = 0
        self.infer_calls = 0

    def load(self, config) -> Da3BackendInfo:
        self.load_calls += 1
        if self.fail_load is not None:
            raise self.fail_load
        return Da3BackendInfo(
            autocast_dtype=self.autocast,
            weights_dtype="float32",
            gpu_name="Fake GPU",
            checkpoint_file="model.safetensors",
            checkpoint_sha256="ab" * 32,
            load_seconds=0.25,
            environment={"python": "3.11.0", "torch": "fake"},
        )

    def infer(self, image_rgb: np.ndarray, config) -> RawDa3Output:
        self.infer_calls += 1
        if self.fail_on_call is not None and self.infer_calls == self.fail_on_call[0]:
            raise self.fail_on_call[1]
        width, height = da3_processed_size(image_rgb.shape[1], image_rgb.shape[0], config.process_res)
        if self.depth_fn is not None:
            depth = self.depth_fn(image_rgb, (height, width))
        else:
            # deterministic, positive, depends on the image content
            depth = np.full((height, width), 2.0 + float(image_rgb.mean()) / 255.0, dtype=np.float32)
        conf = np.linspace(1.0, 5.0, depth.size, dtype=np.float32).reshape(depth.shape) if self.conf else None
        return RawDa3Output(
            depth=depth,
            conf=conf,
            is_metric=self.is_metric,
            intrinsics=self.intrinsics,
            inference_ms=10.0 + self.infer_calls,
        )

    def peak_memory_gb(self) -> float:
        return 1.0
