"""U-03 P1-robust control/anchored/gated maps on the synthetic comparison fixture (CPU only, no backends)."""
import ast
import csv
import dataclasses
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from rt_mapping.alignment.anchoring import run_anchor_gate
from rt_mapping.contracts.geometry import load_prediction, save_prediction
from rt_mapping.contracts.run_manifest import load_run_manifest
from rt_mapping.evaluation.synthetic_scene import create_synthetic_reference
from rt_mapping.runs import robust_fusion_run
from rt_mapping.runs.comparison_run import run_comparison
from rt_mapping.runs.robust_fusion_run import reproduction_check, run_robust_fusion
from rt_mapping.runs.synthetic_mapping import create_synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/robust_fusion.json"
NATIVE_OR_MODEL = ("pyslam", "torch", "depth_anything_3", "unidepth")


def _rewrite(geometry, frame_id, change):
    path = geometry / f"predictions/frame_{frame_id:06d}.npz"
    prediction = load_prediction(path)
    depth = prediction.depth_m.copy()
    change(depth)
    path.unlink()
    save_prediction(dataclasses.replace(prediction, depth_m=depth), path)


def build(tmp_path, mutate=None):
    """Synthetic comparison plus its U-02 decisions (anchor_gate.json stands in for the committed summary)."""
    slam, geometry = create_synthetic_inputs(tmp_path / "inputs", git_commit="a" * 40, non_collinear=True)
    if mutate:
        mutate(geometry)
    sequence, manifest = create_synthetic_reference(tmp_path / "evaluation", slam, geometry)
    comparison = run_comparison(ROOT, slam, geometry, sequence, manifest, run_id="comparison",
                                output_root=tmp_path / "runs")
    assert load_run_manifest(comparison / "run.json")["status"] == "ok"
    gate = run_anchor_gate(ROOT, comparison, slam, geometry, CONFIG, run_id="gate", output_root=tmp_path / "gate")
    assert load_run_manifest(gate / "run.json")["status"] == "ok"
    return dict(comparison=comparison, slam=slam, geometry=geometry, sequence=sequence, manifest=manifest,
                u02=gate / "anchor_gate.json")


def robust(case, tmp_path, run_id="robust", config=CONFIG, u02=None, plot=False):
    return run_robust_fusion(ROOT, case["comparison"], case["slam"], case["geometry"], case["sequence"],
                             case["manifest"], config, u02 or case["u02"], run_id=run_id,
                             output_root=tmp_path / "out", plot=plot)


def ok(directory):
    record = load_run_manifest(directory / "run.json")
    assert record["status"] == "ok", record["reason"]
    return record


def table(directory, name="comparison.csv"):
    with (directory / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return archive["xyz_m"], archive["observation_count"]


@pytest.fixture
def clean(tmp_path):
    return build(tmp_path)


def test_control_reproduces_the_comparison_global_map_byte_for_byte(clean, tmp_path):
    directory = robust(clean, tmp_path, plot=True)
    ok(directory)
    control = directory / "methods/robust.control/map.npz"
    recorded = clean["comparison"] / "methods/comparison.global/map.npz"
    for mine, theirs in zip(arrays(control), arrays(recorded)):
        np.testing.assert_array_equal(mine, theirs)
    phase_a = json.loads((directory / "phase_a.json").read_text(encoding="utf-8"))
    assert phase_a["reproduction"]["byte_identical_arrays"] and phase_a["reproduction"]["residuals_csv_identical"]
    assert phase_a["reproduction"]["variant_fusion_loop_reproduces_control"]
    summary = json.loads((directory / "robust_summary.json").read_text(encoding="utf-8"))
    recorded_row = json.loads((clean["comparison"] / "evaluation/P1-global.json").read_text(encoding="utf-8"))["map"]
    assert summary["maps"]["P1-global-control"] == recorded_row
    assert summary["map_evaluation"]["reference_rebuilt_identical"] is True
    methods = [row["method"] for row in table(directory)]
    assert methods == ["P1-global-control", "P1-anchored", "P1-anchored+gate", "B0-shared-scale", "B1-oracle", "P1-raw"]
    assert summary["accepted"] == 3 and summary["rejected"] == 0
    assert summary["cpu_overhead"]["label"].endswith("not real-time") and summary["real_time_claim"] is False
    assert (directory / "comparison.png").stat().st_size > 0


def test_anchoring_removes_an_injected_bias_and_the_gate_drops_exactly_the_flagged_frame(tmp_path):
    """x1.2 depth on frame 27: U-02 recovers a_f = 1/1.2 and rejects the frame (A3;A4)."""
    case = build(tmp_path, lambda g: _rewrite(g, 27, lambda d: d.__imul__(np.float32(1.2))))
    directory = robust(case, tmp_path)
    ok(directory)
    rows = {row["method"]: row for row in table(directory)}
    control, anchored = rows["P1-global-control"], rows["P1-anchored"]
    assert float(anchored["eval_accuracy_mean_m"]) < float(control["eval_accuracy_mean_m"])
    assert float(anchored["eval_chamfer_l1_m"]) < float(control["eval_chamfer_l1_m"])
    assert anchored["frames_fused"] == "3" and rows["P1-anchored+gate"]["frames_fused"] == "2"
    assert rows["P1-anchored+gate"]["frames_rejected"] == "1"
    phase_a = json.loads((directory / "phase_a.json").read_text(encoding="utf-8"))
    assert phase_a["rejected"] == [27] and phase_a["variants"]["P1-anchored+gate"]["frames"] == [10, 40]
    frames = {int(r["frame_id"]): r for r in table(directory, "frame_evaluation.csv")}
    assert float(frames[27]["eval_abs_rel_before"]) > 0.15
    assert float(frames[27]["eval_abs_rel_after"]) < float(frames[27]["eval_abs_rel_before"]) / 10
    assert frames[27]["decision"] == "reject" and frames[27]["flags"] == "A3;A4"


def test_ground_truth_is_opened_only_after_every_map_exists(clean, tmp_path, monkeypatch):
    original, seen = robust_fusion_run.load_oracle_inputs, []

    def guarded(*args, **kwargs):
        directory = tmp_path / "out/robust"
        for name in ("phase_a.json", "methods/robust.control/map.npz", "variants/anchored/map.npz",
                     "variants/anchored_gate/map.npz", "frame_signals.csv", "anchor_gate.csv"):
            assert (directory / name).is_file(), name
        assert "phase_a" in load_run_manifest(directory / "run.json")["artifacts"]
        assert not (directory / "comparison.csv").exists()
        seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(robust_fusion_run, "load_oracle_inputs", guarded)
    ok(robust(clean, tmp_path))
    assert seen == [True]


def test_config_hash_mismatch_is_refused_without_a_run_directory(clean, tmp_path):
    changed = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed["description"] += " (edited)"
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the frozen U-02 hash"):
        robust(clean, tmp_path, config=path)
    assert not (tmp_path / "out/robust").exists()


@pytest.mark.parametrize("field,value", [("decision", "reject"), ("applied_scale", 1.0)])
def test_decisions_differing_from_u02_are_refused_without_a_run_directory(clean, tmp_path, field, value):
    summary = json.loads(clean["u02"].read_text(encoding="utf-8"))
    summary["decisions"][1][field] = value
    path = tmp_path / "u02.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="differ from the committed U-02 decisions"):
        robust(clean, tmp_path, u02=path)
    assert not (tmp_path / "out/robust").exists()


def test_reproduction_check_applies_the_float64_bound(tmp_path):
    xyz = np.array([[0.011, 0.031, 1.001], [0.051, 0.013, 1.003]])
    counts = np.array([5, 1_000_000])
    def save(name, points, n=counts):
        np.savez(tmp_path / name, xyz_m=points, observation_count=n)
        return tmp_path / name

    recorded = save("recorded.npz", xyz)
    assert reproduction_check(save("same.npz", xyz.copy()), recorded, 0.02)["byte_identical_arrays"]
    tiny = xyz.copy()
    tiny[1, 2] = np.nextafter(tiny[1, 2], 2.0)  # one ulp, far inside γ_n·max|x| for n = 1e6
    within = reproduction_check(save("tiny.npz", tiny), recorded, 0.02)
    assert not within["byte_identical_arrays"] and 0 < within["max_bound_ratio"] <= 1
    large = xyz.copy()
    large[0, 0] += 1e-9
    with pytest.raises(ValueError, match="error bound"):
        reproduction_check(save("large.npz", large), recorded, 0.02)
    with pytest.raises(ValueError, match="observation counts"):
        reproduction_check(save("counts.npz", xyz.copy(), np.array([5, 999_999])), recorded, 0.02)


def test_cli_runs_and_never_overwrites(clean, tmp_path):
    argv = [sys.executable, str(ROOT / "scripts/run_robust_fusion.py"), "--comparison-run", str(clean["comparison"]),
            "--slam-run", str(clean["slam"]), "--geometry-run", str(clean["geometry"]),
            "--sequence-dir", str(clean["sequence"]), "--manifest", str(clean["manifest"]),
            "--u02-summary", str(clean["u02"]), "--run-id", "cli", "--output-root", str(tmp_path / "out")]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    ok(tmp_path / "out/cli")
    again = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    assert again.returncode == 2 and "never overwritten" in again.stderr


def _imports(path):
    names = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_robust_fusion_modules_load_no_native_or_model_runtime():
    for path in ("src/rt_mapping/runs/robust_fusion_run.py", "scripts/run_robust_fusion.py"):
        bad = {n for n in _imports(path) for p in NATIVE_OR_MODEL if n == p or n.startswith(p + ".")}
        assert not bad, f"{path} imports {sorted(bad)}"
    code = (f"import sys; sys.path.insert(0,{str(ROOT / 'src')!r}); import rt_mapping.runs.robust_fusion_run; "
            f"loaded = [n for n in {NATIVE_OR_MODEL!r} if n in sys.modules]; assert not loaded, loaded")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
