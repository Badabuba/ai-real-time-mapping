"""Plot an existing pySLAM TUM trajectory; never launch SLAM or overwrite results.

Run with .venv-pyslam/bin/python from the repository root. Pass --show for
rotatable Matplotlib windows (requires an interactive backend, e.g. Qt5Agg).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from scipy.spatial.transform import Rotation


def load_poses(path):
    data = np.loadtxt(path, ndmin=2)
    if data.shape[1] != 8 or len(data) < 2 or not np.isfinite(data).all():
        raise ValueError(f"Invalid timestamp/translation/xyzw trajectory: {path}")
    if not np.all(np.diff(data[:, 0]) > 0):
        raise ValueError("Timestamps must strictly increase")
    if not np.allclose(np.linalg.norm(data[:, 4:8], axis=1), 1, atol=1e-5):
        raise ValueError("Quaternions must have unit norm")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=Path(
        "results/runs/yaropolk_b0_fr1_xyz_200_20261023_02"))
    parser.add_argument("--output-dir", type=Path,
                        help="New directory only; defaults to a unique results/visualizations directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.lines import Line2D
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    run = args.run_dir.absolute()
    source = run / "input_setup/trajectory/trajectory_final.txt"
    data = load_poses(source)
    metrics_path = run / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    subtitle = f"{len(data)} final poses"
    if "input_frames" in metrics:
        subtitle += f" from {metrics['input_frames']} input frames"
    xyz = data[:, 1:4]
    elapsed = data[:, 0] - data[0, 0]
    rotations = Rotation.from_quat(data[:, 4:8]).as_matrix()  # R_wc, xyzw
    out = args.output_dir or Path("results/visualizations") / run.name / datetime.now(
        timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    out = out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    # Fingerprint every original regular artifact; exclude the 200 raw-image symlinks.
    sources = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(run.rglob("*")) if p.is_file() and not p.is_symlink()}
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 14,
                         "figure.facecolor": "white", "savefig.facecolor": "white"})
    norm = Normalize(0, elapsed[-1])
    segments = np.stack((xyz[:-1], xyz[1:]), axis=1)
    indices = np.unique(np.linspace(0, len(data) - 1, 9).astype(int))
    axis_length = float(np.ptp(xyz, axis=0).max() * 0.10)

    def trajectory(ax):
        line = Line3DCollection(segments, cmap="viridis", norm=norm, linewidth=2.4)
        line.set_array((elapsed[:-1] + elapsed[1:]) / 2)
        ax.add_collection3d(line)
        ax.scatter(*xyz[0], color="#009E73", s=90, edgecolor="black", label="Start", zorder=5)
        ax.scatter(*xyz[-1], color="#D55E00", s=100, marker="X", label="End", zorder=5)
        ax.set(xlabel="World X [SLAM units]", ylabel="World Y [SLAM units]",
               zlabel="World Z [SLAM units]")
        ax.view_init(elev=24, azim=-58)
        # Equal world-unit lengths on screen, including space for the orientation arrows.
        radius = np.ptp(xyz, axis=0).max() * 0.64
        center = (xyz.min(axis=0) + xyz.max(axis=0)) / 2
        for setter, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), center):
            setter(c - radius, c + radius)
        ax.set_box_aspect((1, 1, 1))
        return line

    figures = []
    for orientation in (False, True):
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111, projection="3d")
        line = trajectory(ax)
        title = "Camera orientation along final trajectory" if orientation else "Estimated camera trajectory"
        ax.set_title(f"{title}\n{subtitle}", pad=20)
        if orientation:
            colors = ("#D62728", "#2CA02C", "#1F77B4")
            for i in indices:
                for k, color in enumerate(colors):
                    ax.quiver(*xyz[i], *(rotations[i, :, k] * axis_length),
                              color=color, linewidth=1.5, arrow_length_ratio=0.25)
            handles, labels = ax.get_legend_handles_labels()
            handles += [Line2D([0], [0], color=c, lw=2) for c in colors]
            labels += ["Camera +X: right", "Camera +Y: down", "Camera +Z: forward"]
            ax.legend(handles, labels, loc="upper left", fontsize=9)
        else:
            ax.legend(loc="upper left")
        fig.colorbar(line, ax=ax, shrink=0.55, pad=0.07,
                     label="Seconds since first exported pose")
        fig.text(0.5, 0.045, "Monocular scale is unknown. World axes are not gravity aligned.\n"
                 + ("Arrows show R_wc columns at 9 poses; arrow length is schematic."
                    if orientation else "Final optimized pose snapshot; no ground-truth alignment or accuracy evaluation."),
                 ha="center", fontsize=10)
        fig.subplots_adjust(left=0.01, right=0.92, bottom=0.12, top=0.87)
        name = "camera_orientation_3d.png" if orientation else "trajectory_3d.png"
        fig.savefig(out / name, dpi=180)
        figures.append(fig)

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    fig.subplots_adjust(left=0.06, right=0.85, bottom=0.21, top=0.85, wspace=0.55)
    for ax, (i, j) in zip(axes, ((0, 1), (0, 2), (1, 2))):
        ax.plot(xyz[:, i], xyz[:, j], color="#dddddd", linewidth=1, zorder=0)
        scatter = ax.scatter(xyz[:, i], xyz[:, j], c=elapsed, norm=norm, cmap="viridis", s=9)
        ax.scatter(xyz[0, i], xyz[0, j], color="#009E73", s=70, edgecolor="black")
        ax.scatter(xyz[-1, i], xyz[-1, j], color="#D55E00", marker="X", s=85)
        ax.set(xlabel=f"World {'XYZ'[i]} [SLAM units]", ylabel=f"World {'XYZ'[j]} [SLAM units]")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.2)
    fig.suptitle("Final camera trajectory: orthogonal projections (equal axis scale)", fontsize=15)
    colorbar_ax = fig.add_axes([0.89, 0.28, 0.013, 0.48])
    fig.colorbar(scatter, cax=colorbar_ax, label="Seconds since first exported pose")
    fig.text(0.48, 0.035, "Green circle = start | Orange cross = end | Unknown monocular scale; no GT alignment",
             ha="center")
    fig.savefig(out / "trajectory_projections.png", dpi=180)
    figures.append(fig)

    summary = {
        "source_run": str(run), "pose_format": "timestamp tx ty tz qx qy qz qw; T_wc",
        "pose_count": len(data), "timestamp_start_s": float(data[0, 0]),
        "timestamp_end_s": float(data[-1, 0]), "duration_s": float(elapsed[-1]),
        "axis_ranges_slam_units": np.ptp(xyz, axis=0).tolist(),
        "sampled_path_length_slam_units": float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum()),
        "start_to_end_distance_slam_units": float(np.linalg.norm(xyz[-1] - xyz[0])),
        "orientation_sample_row_indices_zero_based": indices.tolist(),
        "orientation_axes": "columns of R_wc: +X right, +Y down, +Z forward",
        "axis_arrow_length_slam_units": axis_length,
        "units": "arbitrary monocular SLAM units; not meters", "gt_evaluation": "not performed",
        "source_artifact_sha256": sources,
    }
    for relative, digest in sources.items():
        if hashlib.sha256((run / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Original artifact changed: {relative}")
    summary["original_artifacts_unchanged_after_plotting"] = True
    with (out / "inspection.json").open("x") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(out)
    print(f"{len(data)} poses, {elapsed[-1]:.6f} seconds; original artifacts unchanged")
    if args.show:
        plt.show()
    else:
        for fig in figures:
            plt.close(fig)


if __name__ == "__main__":
    main()
