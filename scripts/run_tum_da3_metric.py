"""Run DA3METRIC-LARGE on a frozen TUM split and record a validated run (thin CLI).

Logic lives in rt_mapping.adapters.da3_metric (adapter) and
rt_mapping.runs.geometry_run (dataset check, loop, evaluation, run.json).
Exit codes: 0 ok, 1 run failed (run.json says why), 2 request rejected before any write.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rt_mapping.adapters.da3_metric import (  # noqa: E402
    DEFAULT_PROCESS_RES,
    DEFAULT_REPO,
    DEFAULT_REVISION,
    SUPPORTED_DTYPES,
    Da3MetricAdapter,
    Da3MetricConfig,
)
from rt_mapping.geometry.adapter import GeometryAdapterError  # noqa: E402
from rt_mapping.runs.geometry_run import (  # noqa: E402
    EXIT_PREFLIGHT,
    PreflightError,
    RunSpec,
    collect_git_state,
    collect_host_info,
    load_dataset_manifest,
    run_geometry_benchmark,
)

DEFAULT_SEQUENCE_DIR = "data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz"
DEFAULT_ARCHIVE = "data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz.tgz"
DEFAULT_MANIFEST = "data/manifests/tum_fr1_xyz.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence-dir", type=Path, default=REPO_ROOT / DEFAULT_SEQUENCE_DIR)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=REPO_ROOT / DEFAULT_ARCHIVE)
    parser.add_argument("--skip-archive-hash", action="store_true", help="do not re-hash the archive (recorded in run.json)")
    parser.add_argument("--split", default="smoke")
    parser.add_argument("--frames", type=int, default=20, help="first N frames of the split")
    parser.add_argument("--warmup", type=int, default=1, help="leading samples excluded from warm timing stats")
    parser.add_argument("--run-id", default=None, help="default: <UTC time>_<sequence>_da3metric_f<N>_r<res>")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "results" / "runs")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", default="bfloat16", choices=SUPPORTED_DTYPES)
    parser.add_argument("--process-res", type=int, default=DEFAULT_PROCESS_RES)
    parser.add_argument("--model-repo", default=DEFAULT_REPO)
    parser.add_argument("--model-revision", default=DEFAULT_REVISION)
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "checkpoints" / "huggingface")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        raise PreflightError(f"{path} must be inside the repository") from None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = Da3MetricConfig(
            repo=args.model_repo,
            revision=args.model_revision,
            device=args.device,
            dtype=args.dtype,
            process_res=args.process_res,
            seed=args.seed,
            cache_dir=args.cache_dir,
        )
        manifest = load_dataset_manifest(args.manifest)
        run_id = args.run_id or (
            f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{manifest['sequence_id'].removeprefix('rgbd_dataset_')}"
            f"_da3metric_f{args.frames}_r{args.process_res}"
        )
        spec = RunSpec(
            run_id=run_id,
            output_root=args.output_root,
            sequence_dir=args.sequence_dir,
            manifest_path=args.manifest,
            manifest_rel=repo_relative(args.manifest),
            split=args.split,
            frames=args.frames,
            warmup=args.warmup,
            seed=args.seed,
            initial_model={
                "repo": config.repo,
                "revision": config.revision,
                "checkpoint": "unresolved (resolved from the local cache at model load)",
                "dtype": config.dtype,
            },
            config={"runner": "scripts/run_tum_da3_metric.py", "batch": 1, "model": config.to_record()},
            archive_path=None if args.skip_archive_hash else args.archive,
        )
        result = run_geometry_benchmark(
            spec,
            lambda: Da3MetricAdapter(config, image_root=args.sequence_dir),
            git_state=collect_git_state(REPO_ROOT),
            host_info=collect_host_info(),
        )
    except (PreflightError, GeometryAdapterError) as exc:
        print(f"REJECTED before running: {exc}", file=sys.stderr)
        return EXIT_PREFLIGHT
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
