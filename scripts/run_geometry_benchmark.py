"""Run either WP1 adapter through the existing generic orchestration."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.runs.geometry_run import (
    RunSpec, PreflightError, collect_git_state, collect_host_info,
    load_dataset_manifest, run_geometry_benchmark,
)
from rt_mapping.geometry.adapter import GeometryAdapterError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["da3", "unidepth"], required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", default="smoke")
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--prewarm", type=int, default=10)
    parser.add_argument("--process-res", type=int, default=504)
    parser.add_argument("--resolution-level", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--assets-root", type=Path, default=ROOT,
                        help="checkout holding data/raw, checkpoints and results/runs")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        manifest_path = args.manifest.resolve()
        manifest_rel = manifest_path.relative_to(ROOT).as_posix()
        manifest = load_dataset_manifest(manifest_path)
        sequence = args.assets_root / manifest["extracted_dir"]
        if args.model == "da3":
            from rt_mapping.adapters.da3_metric import Da3MetricConfig, Da3MetricAdapter
            config = Da3MetricConfig(device=args.device, process_res=args.process_res, seed=args.seed,
                                     cache_dir=args.assets_root / "checkpoints/huggingface")
            factory = lambda: Da3MetricAdapter(config, sequence)
            initial = {"repo": config.repo, "revision": config.revision, "dtype": config.dtype, "checkpoint": "unresolved"}
        else:
            from rt_mapping.adapters.unidepth_v2 import UniDepthConfig, UniDepthV2Adapter, REPO, REVISION
            config = UniDepthConfig(device=args.device, resolution_level=args.resolution_level, seed=args.seed,
                                   checkpoint_dir=args.assets_root / "checkpoints/unidepth-v2-vitl14-52b349b",
                                   source_dir=args.assets_root / "checkpoints/upstream/UniDepth")
            factory = lambda: UniDepthV2Adapter(config, sequence)
            initial = {"repo": REPO, "revision": REVISION, "dtype": "float16", "checkpoint": "unresolved"}
        spec = RunSpec(
            run_id=args.run_id, output_root=args.assets_root / "results/runs", sequence_dir=sequence,
            manifest_path=manifest_path, manifest_rel=manifest_rel, split=args.split, frames=args.frames,
            warmup=0, prewarm_calls=args.prewarm, evaluation_grid="raw_rgb", seed=args.seed,
            initial_model=initial, config={"runner": "scripts/run_geometry_benchmark.py", "batch": 1,
                                          "model": config.to_record()},
            archive_path=args.assets_root / "data/raw/tum_rgbd" / manifest["source"]["archive_filename"],
        )
        return run_geometry_benchmark(spec, factory, git_state=collect_git_state(ROOT),
                                      host_info=collect_host_info()).exit_code
    except (PreflightError, GeometryAdapterError, ValueError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
