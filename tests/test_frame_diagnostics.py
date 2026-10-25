"""U-01 per-keyframe diagnostics on the synthetic comparison fixture (CPU only, no backends)."""
import csv
import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from rt_mapping.alignment.frame_signals import NO_TRACKING_REASON
from rt_mapping.contracts.geometry import load_prediction, save_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation import frame_diagnostics
from rt_mapping.evaluation.frame_diagnostics import run_frame_diagnostics, spearman
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs.comparison_run import run_comparison
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
PATCH = (slice(12, 15), slice(17, 20))  # the fixture's injected 1.7x predicted-depth patch


def _rewrite(geometry, frame_id, change):
    path = geometry / f"predictions/frame_{frame_id:06d}.npz"
    prediction = load_prediction(path)
    depth = prediction.depth_m.copy()
    change(depth)
    path.unlink()
    save_prediction(dataclasses.replace(prediction, depth_m=depth), path)


def build(tmp_path, mutate=None):
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a" * 40, non_collinear=True)
    if mutate:
        mutate(geometry)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    comparison = run_comparison(ROOT, slam, geometry, sequence, manifest, run_id="comparison",
                                output_root=tmp_path / "runs")
    assert load_run_manifest(comparison / "run.json")["status"] == "ok"
    return comparison, slam, geometry, sequence, manifest


def diagnose(sources, tmp_path, run_id="diag", plot=False):
    return run_frame_diagnostics(ROOT, *sources, run_id=run_id, output_root=tmp_path / "out", plot=plot)


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture
def sources(tmp_path):
    return build(tmp_path)


def test_clean_synthetic_anchor_ratio_matches_recorded_scale(sources, tmp_path):
    """Synthetic depth is float32: relative rounding ~6e-8, so a_f must equal 1 within 1e-6."""
    directory = diagnose(sources, tmp_path, plot=True)
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    assert record["method"] == "P1-global" and record["config"]["control_label"].startswith("per-keyframe")
    signals = rows(directory / "frame_signals.csv")
    assert [int(r["frame_id"]) for r in signals] == [10, 27, 40]
    for row in signals:
        assert abs(float(row["anchor_ratio"]) - 1) < 1e-6
        assert row["flag_A1"] == row["flag_A2"] == row["flag_A4"] == "false"
    assert len(rows(directory / "frame_evaluation.csv")) == 3
    assert len(rows(directory / "failure_table.csv")) == 3
    correlations = json.loads((directory / "correlations.json").read_text(encoding="utf-8"))
    assert correlations["scope"] == "evaluation_only"
    assert (directory / "timeline.png").stat().st_size > 0


def test_injected_patch_is_visible_only_in_the_patched_frame(tmp_path):
    """The 1.7x patch hits ~2 of 72 landmarks, so a median is robust to it by design.

    The contamination must therefore appear in the inlier ratio, not in the median.
    """
    def restore_clean(geometry):
        for frame_id in (27, 40):
            _rewrite(geometry, frame_id, lambda d: d.__setitem__(PATCH, d[PATCH] / np.float32(1.7)))

    directory = diagnose(build(tmp_path, restore_clean), tmp_path)
    by_frame = {int(r["frame_id"]): r for r in rows(directory / "frame_signals.csv")}
    assert float(by_frame[10]["frame_inlier_ratio"]) < 1.0
    assert float(by_frame[27]["frame_inlier_ratio"]) == float(by_frame[40]["frame_inlier_ratio"]) == 1.0
    assert all(float(by_frame[f]["median_abs_residual_m"]) < 1e-5 for f in by_frame)


def test_per_frame_scale_error_raises_anchor_flag(tmp_path):
    directory = diagnose(build(tmp_path, lambda g: _rewrite(g, 27, lambda d: d.__imul__(np.float32(1.3)))), tmp_path)
    by_frame = {int(r["frame_id"]): r for r in rows(directory / "frame_signals.csv")}
    assert abs(float(by_frame[27]["anchor_ratio"]) - 1 / 1.3) < 1e-6
    assert by_frame[27]["flag_A2"] == "true" and by_frame[27]["flag_A3"] == "true"
    assert by_frame[10]["flag_A2"] == by_frame[40]["flag_A2"] == "false"
    table = rows(directory / "failure_table.csv")
    category = next(r["category"] for r in table if r["frame_id"] == "27")
    assert "D1 per-frame metric-scale error (A2)" in category.split("; ")


def test_gt_is_opened_only_after_gt_free_phase_is_written(sources, tmp_path, monkeypatch):
    original, seen = frame_diagnostics.load_oracle_inputs, []

    def guarded(*args, **kwargs):
        directory = tmp_path / "out" / "diag"
        assert (directory / "frame_signals.csv").is_file() and (directory / "signals.json").is_file()
        assert "frame_signals" in load_run_manifest(directory / "run.json")["artifacts"]
        seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(frame_diagnostics, "load_oracle_inputs", guarded)
    assert load_run_manifest(diagnose(sources, tmp_path) / "run.json")["status"] == "ok"
    assert seen == [True]


def test_missing_tracking_export_is_null_with_reason(sources, tmp_path):
    directory = diagnose(sources, tmp_path)
    for row in rows(directory / "frame_signals.csv"):
        assert row["tracking_state"] == "" and row["tracking_reason"] == NO_TRACKING_REASON
        assert row["flag_S1"] == "false"
    tracking = json.loads((directory / "signals.json").read_text(encoding="utf-8"))["tracking"]
    assert tracking == {"available": False, "reason": NO_TRACKING_REASON}


def test_provenance_mismatch_is_refused_without_a_run_directory(sources, tmp_path):
    comparison = sources[0]
    path = comparison / "inputs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pipeline"]["slam_run_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        diagnose(sources, tmp_path)
    assert not (tmp_path / "out" / "diag").exists()


def test_residuals_mismatch_is_refused_without_a_run_directory(sources, tmp_path):
    path = sources[0] / "methods/comparison.global/residuals.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = lines[1].split(",")
    first[-1] = "False" if first[-1] == "True" else "True"
    lines[1] = ",".join(first)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="residuals.csv"):
        diagnose(sources, tmp_path)
    assert not (tmp_path / "out" / "diag").exists()


def test_rerun_produces_byte_identical_data_files(sources, tmp_path):
    first, second = diagnose(sources, tmp_path, "diag_a"), diagnose(sources, tmp_path, "diag_b")
    for name in ("frame_signals.csv", "frame_evaluation.csv", "correlations.json", "failure_table.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        diagnose(sources, tmp_path, "diag_a")


def test_spearman_average_ranks_hand_example():
    # ranks x = [1, 2.5, 2.5, 4], y = [1, 3, 2, 4]: rho = 4.5 / sqrt(4.5 * 5) = 3 / sqrt(10)
    assert spearman([1, 2, 2, 3], [1, 3, 2, 4]) == pytest.approx(3 / math.sqrt(10), abs=1e-15)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1, 2], [2, 1]) is None
