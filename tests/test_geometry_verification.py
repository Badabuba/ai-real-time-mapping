import json
import pytest

from test_geometry_run import run, spec, tree_bytes
from rt_mapping.evaluation.geometry_verification import verify_geometry_run


def test_recompute_from_saved_predictions_and_gt_without_writes(synth_repo):
    result = run(synth_repo, spec(synth_repo, prewarm_calls=10, evaluation_grid="raw_rgb", warmup=0))
    before = tree_bytes(result.run_dir)
    report = verify_geometry_run(result.run_dir, repo_root=synth_repo.root, assets_root=synth_repo.root)
    assert report["frames"] == 3 and report["confidence_available"] is False
    assert report["verification_scope"] == "predictions + GT recomputation"
    assert tree_bytes(result.run_dir) == before


@pytest.mark.parametrize("change", ["metric", "mask", "timing", "identity", "path"])
def test_tampered_evidence_rejected(synth_repo, change):
    result = run(synth_repo, spec(synth_repo, evaluation_grid="raw_rgb"))
    filename = "timing.json" if change == "timing" else "metrics.json"
    path = result.run_dir / filename
    data = json.loads(path.read_text())
    if change == "metric":
        data["per_frame"][0]["abs_rel"] = .00001
    elif change == "mask":
        data["per_frame"][0]["evaluation_mask_sha256"] = "a" * 64
    elif change == "identity":
        data["per_frame"][0]["timestamp_s"] += .001
    elif change == "path":
        data["per_frame"][0]["prediction"] = "../outside.npz"
    else:
        data["stages"]["model_inference"]["warm_p95_ms"] = 1.
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify_geometry_run(result.run_dir, repo_root=synth_repo.root, assets_root=synth_repo.root)
