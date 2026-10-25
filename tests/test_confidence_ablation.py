import numpy as np
import pytest

from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.evaluation.confidence_ablation import filter_confidence
from rt_mapping.evaluation.depth import evaluate_depth


def prediction(confidence):
    return GeometryPrediction(0, 1., np.array([[1., 2.], [3., 4.]], np.float32), np.ones((2, 2), bool),
                              confidence, np.eye(3), "fake", {}, 1.)


def test_quantiles_use_only_predicted_confidence_and_keep_higher_scores():
    pred = prediction(np.array([[.1, .9], [.8, .2]], np.float32))
    selected = filter_confidence(pred, .5)
    np.testing.assert_array_equal(selected.valid_mask, [[False, True], [True, False]])
    assert np.isnan(selected.depth_m[~selected.valid_mask]).all()
    score = evaluate_depth(selected, np.full((2, 2), 2., np.float32))
    assert score.n_evaluated == 2 and score.valid_coverage == .5
    assert score.abs_rel == .25
    assert filter_confidence(pred, 1).valid_mask.all()
    assert pred.valid_mask.all()  # original prediction immutable


def test_missing_confidence_and_bad_fractions_are_not_faked():
    with pytest.raises(ValueError, match="no confidence"):
        filter_confidence(prediction(None), .5)
    pred = prediction(np.ones((2, 2), np.float32))
    for fraction in (0, -1, 2):
        with pytest.raises(ValueError):
            filter_confidence(pred, fraction)


def _confidence_run(tmp_path, confidences):
    """A real clean geometry run whose fake adapter emits the given per-frame confidence maps."""
    from PIL import Image
    from rt_mapping.data.manifest import build_tum_manifest, dump_manifest
    from rt_mapping.runs.geometry_run import GitState, HostInfo, RunSpec, run_geometry_benchmark
    seq = tmp_path / "rgbd_dataset_freiburg1_synth"
    (seq / "rgb").mkdir(parents=True)
    (seq / "depth").mkdir()
    n = len(confidences)
    for i in range(n):
        Image.fromarray(np.zeros((480, 640, 3), np.uint8)).save(seq / f"rgb/{i}.png")
        Image.fromarray(np.full((480, 640), 10000, np.uint16)).save(seq / f"depth/{i}.png")
    (seq / "rgb.txt").write_text("".join(f"{i + 1}.0 rgb/{i}.png\n" for i in range(n)))
    (seq / "depth.txt").write_text("".join(f"{i + 1}.001 depth/{i}.png\n" for i in range(n)))
    archive = tmp_path / "fixture.tgz"
    archive.write_bytes(b"fixture")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(dump_manifest(build_tum_manifest(seq, archive, tmp_path, "https://example.invalid/a",
                                                              smoke_frames=n)))

    class Fake:
        def describe(self):
            return {"model": {"repo": "fake/model", "revision": "a" * 40, "checkpoint": "fake", "dtype": "float32"},
                    "config": {"confidence": "fixture"}, "environment": {}, "gpu": None}

        def predict(self, frame):
            conf = confidences[frame.frame_id]
            return GeometryPrediction(frame.frame_id, frame.timestamp_s, np.full(conf.shape, 2., np.float32),
                                      np.ones(conf.shape, bool), conf, frame.K, "fake", {}, 1.)
    spec = RunSpec("conf", tmp_path / "runs", seq, manifest_path, "data/manifests/fixture.json", "smoke", n, 0, 0,
                   Fake().describe()["model"], {}, archive, evaluation_grid="raw_rgb")
    result = run_geometry_benchmark(spec, Fake, git_state=GitState("a" * 40, False),
                                    host_info=HostInfo("fixture", None), log=lambda _: None)
    assert result.exit_code == 0
    return result.run_dir, seq


def test_pooled_thresholds_pool_all_frames_and_never_open_gt(tmp_path, monkeypatch):
    from rt_mapping.evaluation import confidence_ablation
    frames = [np.full((480, 640), -1., np.float32), np.full((480, 640), -3., np.float32)]
    frames[1][:240] = -2.
    run_dir, _ = _confidence_run(tmp_path, frames)
    monkeypatch.setattr(confidence_ablation, "load_tum_depth_m", lambda *a: pytest.fail("GT opened"))
    report = confidence_ablation.pooled_confidence_thresholds(run_dir)
    assert report["ground_truth_used"] is False and report["frames"] == 2
    assert report["valid_pixels"] == 2 * 480 * 640
    by_keep = {row["keep_fraction_requested"]: row for row in report["thresholds"]}
    # pooled values: 50% at -1, 25% at -2, 25% at -3; linear quantiles land between the levels
    assert by_keep[0.5]["threshold"] == pytest.approx(-1.5) and by_keep[0.5]["retained_fraction"] == 0.5
    assert by_keep[0.75]["threshold"] == pytest.approx(-2.25) and by_keep[0.75]["retained_fraction"] == 0.75
    coverage = confidence_ablation.confidence_coverage(run_dir, [-2.0, -1.5], frame_ids=[1])
    assert [row["retained_fraction"] for row in coverage] == [0.5, 0.0]
    with pytest.raises(ValueError, match="missing"):
        confidence_ablation.confidence_coverage(run_dir, [-2.0], frame_ids=[7])
    with pytest.raises(ValueError):
        confidence_ablation.pooled_confidence_thresholds(run_dir, keep_fractions=(1.0,))


def test_cli_pooled_mode_refuses_ground_truth_input(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "analyze_confidence", Path(__file__).resolve().parents[1] / "scripts" / "analyze_confidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit):
        module.main(["--run", "x", "--pooled-thresholds", "--sequence-dir", "y", "--output", str(tmp_path / "o")])
    with pytest.raises(SystemExit):
        module.main(["--run", "x", "--output", str(tmp_path / "o")])
