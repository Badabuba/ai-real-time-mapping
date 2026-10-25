"""P1-robust U-04 figures from finished U-01/U-03 runs: before/after point cloud and failure cases.

Offline presentation only. Ground truth enters solely in panels labelled
"evaluation only" (distance to the GT reference, GT absolute depth error).
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rt_mapping.alignment.frame_signals import load_sources
from rt_mapping.evaluation.oracle import load_oracle_inputs

POINTCLOUD, FAILURES = "yulian_u04_pointcloud_before_after.png", "yulian_u04_failure_cases.png"
MAX_TOTAL_BYTES = 1_000_000
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
ERROR_RAMP = ("#c6dbef", "#08306b")  # one hue, light (small error) -> dark (large error)
MAX_POINTS = 25_000


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    return plt, LinearSegmentedColormap.from_list("error", ERROR_RAMP)


def _style(axis):
    axis.set_facecolor(SURFACE)
    axis.tick_params(colors=MUTED, labelsize=7)
    for side in axis.spines.values():
        side.set_color("#e4e3df")


def render_pointcloud(path, u03_run, sources):
    """P1-global control vs P1-anchored+gate in the evaluation frame, same axes and view."""
    from scipy.spatial import cKDTree

    record = _json(u03_run / "run.json")
    phase_a = _json(u03_run / "phase_a.json")
    gated = phase_a["variants"]["P1-anchored+gate"]
    if gated["status"] != "ok":
        raise ValueError(f"P1-anchored+gate has no map: {gated['reason']}")
    control_map = u03_run / Path(record["artifacts"]["control_run"]).parent / "map.npz"
    transform = _json(sources.comparison_dir / "trajectory_evaluation.json")["P1_global_se3"]["evaluation_transform"]
    rotation, translation = np.asarray(transform["R"]), np.asarray(transform["t"])
    with np.load(sources.comparison_dir / "reference_evaluation_only.npz", allow_pickle=False) as archive:
        reference = archive["xyz_m"]
    tree = cKDTree(reference)
    # View: the two axes along which the GT reference extends most (deterministic).
    axes_pair = np.sort(np.argsort(np.ptp(reference, axis=0))[::-1][:2])
    names = np.array(["X", "Y", "Z"])[axes_pair]
    panels = []
    for label, source in (("P1-global control", control_map), ("P1-anchored+gate", u03_run / gated["map"])):
        with np.load(source, allow_pickle=False) as archive:
            points = archive["xyz_m"] @ rotation.T + translation
        distances, _ = tree.query(points, k=1)
        order = np.linspace(0, len(points) - 1, min(len(points), MAX_POINTS)).astype(int)
        panels.append((label, points[order], distances[order], float(distances.mean()), len(points)))
    plt, cmap = _pyplot()
    limit = float(np.percentile(np.concatenate([p[2] for p in panels]), 95))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharex=True, sharey=True, constrained_layout=True,
                             facecolor=SURFACE)
    for axis, (label, points, distances, mean, total) in zip(axes, panels):
        order = np.argsort(distances)  # large errors drawn last, on top
        cloud = axis.scatter(points[order, axes_pair[0]], points[order, axes_pair[1]], c=distances[order], s=0.6,
                             cmap=cmap, vmin=0, vmax=limit, linewidths=0, rasterized=True)
        axis.set_title(f"{label}: {total:,} voxels, mean distance {mean:.4f} m", fontsize=9, color=INK)
        axis.set_xlabel(f"Evaluation-frame {names[0]} [m]", fontsize=8, color=MUTED)
        axis.set_aspect("equal")
        _style(axis)
    axes[0].set_ylabel(f"Evaluation-frame {names[1]} [m]", fontsize=8, color=MUTED)
    bar = fig.colorbar(cloud, ax=axes, shrink=0.85, extend="max")
    bar.set_label("Distance to GT reference [m] (evaluation only)", fontsize=8, color=MUTED)
    bar.ax.tick_params(labelsize=7, colors=MUTED)
    fig.suptitle(f"Offline fused maps, same view and colour scale (TUM fr1/xyz smoke-200). Run {record['run_id']}; "
                 f"{len(gated['rejected_frames'])} keyframes rejected by the gate", fontsize=9, color=INK)
    fig.savefig(path, dpi=100, facecolor=SURFACE)
    plt.close(fig)


def render_failures(path, u01_run, u03_run, sources, sequence_dir, manifest_path, cases=3):
    """The worst U-01 map-contribution keyframes: RGB, predicted depth, GT |error| (evaluation only)."""
    table = sorted(_csv(u01_run / "failure_table.csv"), key=lambda r: int(r["rank"]))[:cases]
    gate = {int(r["frame_id"]): r for r in _csv(u03_run / "anchor_gate.csv")}
    after = {int(r["frame_id"]): r for r in _csv(u03_run / "frame_evaluation.csv")}
    inputs, mapping = sources.inputs, sources.mapping
    oracle, *_ = load_oracle_inputs(inputs, sequence_dir, manifest_path, mapping,
                                    max_timestamp_delta_s=sources.comparison["config"]["max_timestamp_delta_s"])
    manifest = _json(manifest_path)
    entries = {int(e["frame_id"]): e for e in manifest["splits"][inputs.slam["dataset"]["split"]]["frames"]}
    plt, cmap = _pyplot()
    from PIL import Image

    fig, axes = plt.subplots(len(table), 4, figsize=(12, 2.9 * len(table)), constrained_layout=True,
                             facecolor=SURFACE, gridspec_kw={"width_ratios": [1, 1, 1, 0.9]}, squeeze=False)
    depth_max = max(float(np.nanpercentile(inputs.predictions[int(r["frame_id"])].depth_m, 99)) for r in table)
    for row_axes, row in zip(axes, table):
        frame_id = int(row["frame_id"])
        prediction, signal = inputs.predictions[frame_id], gate[frame_id]
        rgb_path = entries[frame_id].get("rgb_path")
        if rgb_path and (Path(sequence_dir) / rgb_path).is_file():
            with Image.open(Path(sequence_dir) / rgb_path) as image:
                row_axes[0].imshow(np.asarray(image.convert("RGB")))
        else:
            row_axes[0].text(0.5, 0.5, "RGB unavailable", ha="center", va="center", color=MUTED, fontsize=8)
        row_axes[0].set_title(f"Keyframe {frame_id}: RGB", fontsize=8, color=INK)
        shown = row_axes[1].imshow(np.where(prediction.valid_mask, prediction.depth_m, np.nan), cmap="Greys_r",
                                   vmin=0, vmax=depth_max)
        row_axes[1].set_title("Predicted depth [m] (DA3)", fontsize=8, color=INK)
        fig.colorbar(shown, ax=row_axes[1], shrink=0.8).ax.tick_params(labelsize=6, colors=MUTED)
        gt = oracle[frame_id].depth_m
        error = np.where(prediction.valid_mask & np.isfinite(gt), np.abs(prediction.depth_m - gt), np.nan)
        shown = row_axes[2].imshow(error, cmap=cmap, vmin=0, vmax=0.5)
        row_axes[2].set_title("|pred - GT| [m] (evaluation only)", fontsize=8, color=INK)
        bar = fig.colorbar(shown, ax=row_axes[2], shrink=0.8, extend="max")
        bar.ax.tick_params(labelsize=6, colors=MUTED)
        for axis in row_axes[:3]:
            axis.set_xticks([])
            axis.set_yticks([])
            _style(axis)
        ratio = signal["anchor_ratio"]
        text = [f"Rank {row['rank']} by map-contribution error",
                f"GT-free: a_f = {float(ratio):.3f}" if ratio else f"GT-free: a_f null ({signal['anchor_reason']})",
                f"flags: {signal['flags'] or 'none fired'}; S1 {signal['flag_S1']}",
                f"decision: {signal['decision']}",
                "Evaluation only:",
                f"  map contribution {float(row['eval_map_accuracy_mean_m']):.3f} m",
                f"  AbsRel {float(after[frame_id]['eval_abs_rel_before']):.3f} -> "
                f"{float(after[frame_id]['eval_abs_rel_after']):.3f} after anchoring",
                f"category: {row['category']}"]
        row_axes[3].axis("off")
        row_axes[3].text(0, 0.95, "\n".join(text), va="top", fontsize=7.5, color=INK, wrap=True)
    fig.suptitle(f"Worst map-contribution keyframes (U-01 run {_json(u01_run / 'run.json')['run_id']}; "
                 f"a_f and decisions from U-03 run {_json(u03_run / 'run.json')['run_id']}). Offline.",
                 fontsize=9, color=INK)
    fig.savefig(path, dpi=80, facecolor=SURFACE)
    plt.close(fig)


def render(u01_run, u03_run, comparison_run, slam_run, geometry_run, sequence_dir, manifest_path, output_dir):
    u01_run, u03_run, output_dir = Path(u01_run), Path(u03_run), Path(output_dir)
    for run in (u01_run, u03_run):
        if _json(run / "run.json")["status"] != "ok":
            raise ValueError(f"{run.name} is not a finished ok run")
    targets = (output_dir / POINTCLOUD, output_dir / FAILURES)
    if any(path.exists() for path in targets):
        raise FileExistsError("existing figures are never overwritten")
    sources = load_sources(comparison_run, slam_run, geometry_run)
    if _json(u03_run / "phase_a.json")["sources"] != sources.provenance:
        raise ValueError("U-03 run was produced from different source runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    render_pointcloud(targets[0], u03_run, sources)
    render_failures(targets[1], u01_run, u03_run, sources, sequence_dir, manifest_path)
    total = sum(path.stat().st_size for path in targets)
    if total >= MAX_TOTAL_BYTES:
        raise ValueError(f"figures total {total} bytes, over the {MAX_TOTAL_BYTES} byte limit")
    return targets, total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--u01-run", type=Path, required=True)
    parser.add_argument("--u03-run", type=Path, required=True)
    parser.add_argument("--comparison-run", type=Path, required=True)
    parser.add_argument("--slam-run", type=Path, required=True)
    parser.add_argument("--geometry-run", type=Path, required=True)
    parser.add_argument("--sequence-dir", type=Path, required=True, help="evaluation-only TUM sequence directory")
    parser.add_argument("--manifest", type=Path, required=True, help="evaluation-only frozen dataset manifest")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/plots")
    args = parser.parse_args(argv)
    targets, total = render(args.u01_run, args.u03_run, args.comparison_run, args.slam_run, args.geometry_run,
                            args.sequence_dir, args.manifest, args.output_dir)
    for path in targets:
        print(f"{path} ({path.stat().st_size} bytes)")
    print(f"total {total} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
