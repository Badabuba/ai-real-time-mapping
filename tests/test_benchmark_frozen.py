"""IC3 protocol freeze: referenced files exist, hashes match, held-out spec is consistent."""
import hashlib
import json
from pathlib import Path

from rt_mapping.runs.comparison_run import comparison_config

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / "configs/benchmark_frozen.json").read_text(encoding="utf-8"))


def _sha(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def test_referenced_files_exist_and_hashes_match():
    for block in (FROZEN["alignment_fusion"], FROZEN["b0"]):
        assert _sha(block["config"]) == block["sha256"]
    assert _sha(FROZEN["heldout"]["manifest"]) == FROZEN["heldout"]["manifest_sha256"]
    assert _sha(FROZEN["derived_from"]["summary"]) == FROZEN["derived_from"]["summary_sha256"]
    assert (ROOT / FROZEN["derived_from"]["doc"]).is_file()


def test_freeze_matches_the_n05_derived_decision():
    chosen = json.loads((ROOT / FROZEN["derived_from"]["summary"]).read_text(encoding="utf-8"))["derived_freeze"]["chosen"]
    p1 = FROZEN["p1"]
    assert chosen["keyframe_interval"] == p1["best_config_keyframe_interval"] == 2
    assert chosen["causal_window_frames"] == p1["causal_window_frames"] == 0 and p1["p1_window_on_heldout"] is False
    assert chosen["confidence_threshold"] is None and p1["confidence_threshold"] is None
    assert FROZEN["model"]["process_res"] == 504


def test_heldout_pipeline_spec_is_consistent_with_frozen_values():
    held = FROZEN["heldout"]
    spec = held["pipeline_config"]
    manifest = json.loads((ROOT / held["manifest"]).read_text(encoding="utf-8"))
    assert spec["split"] == held["split"] == "held-out" and manifest["splits"]["held-out"]["num_frames"] == held["frames"]
    assert spec["dataset_manifest"] == held["manifest"]
    comparison = comparison_config(spec["comparison"])
    ev = FROZEN["evaluation"]
    assert comparison["max_timestamp_delta_s"] == ev["max_timestamp_delta_s"] == 0.02
    assert comparison["thresholds_m"] == ev["map_thresholds_m"] and comparison["crop_bounds_m"] is None
    assert comparison["keyframe_intervals"] == [FROZEN["p1"]["best_config_keyframe_interval"]]
    assert comparison["causal_window_frames"] == 0 and comparison["confidence_thresholds"] == []
    slam, geometry = spec["slam"]["command"], spec["geometry"]["command"]
    assert slam[slam.index("--config") + 1] == FROZEN["b0"]["config"] and "--all-frames" in slam
    assert geometry[geometry.index("--process-res") + 1] == str(FROZEN["model"]["process_res"])
    assert geometry[geometry.index("--model") + 1] == "da3"
    assert geometry[geometry.index("--frames") + 1] == str(held["frames"])


def test_n06_pipeline_config_if_present_equals_frozen_spec():
    path = ROOT / FROZEN["heldout"]["pipeline_config_path"]
    if path.is_file():
        assert json.loads(path.read_text(encoding="utf-8")) == FROZEN["heldout"]["pipeline_config"]
