"""GT-free per-keyframe sparse anchoring and pre-registered frame gate (U-02).

Reuses the U-01 signals (rt_mapping.alignment.frame_signals) on finished
artifacts only. No dataset, ground-truth depth or ground-truth pose is read and
no rt_mapping.evaluation module is imported; the GT comparison is U-03. Every
gate value comes from configs/robust_fusion.json and must equal the merged
defaults recorded in the source comparison run, so a_f and the U-01 flags were
computed with exactly these thresholds.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import json
import math
from numbers import Real
from pathlib import Path
import platform
import subprocess

import numpy as np

from rt_mapping.alignment.frame_signals import (ANCHOR_BAND, SIGNAL_FIELDS, check_recorded_residuals, frame_signals,
                                                load_sources, rebuild_pairs, tracking_states, write_csv, write_json)
from rt_mapping.contracts.geometry import GeometryPrediction
from rt_mapping.contracts.run_manifest import build_run_manifest, format_utc, write_run_manifest
from rt_mapping.contracts.slam import STATES
from rt_mapping.data.manifest import sha256_file

CONFIG_SCHEMA = "rt_mapping.p1_robust_config/v1"
FLAGS = ("A1", "A2", "A3", "A4", "S1")
VARIANTS = ("P1-global-control", "P1-anchored", "P1-anchored+gate")
CONFIG_KEYS = frozenset({"schema", "description", "gate", "map_evaluation", "variants", "inputs"})
GATE_KEYS = frozenset({"residual_threshold_m", "min_anchor_inliers", "min_anchor_inlier_ratio", "min_coverage_bins",
                       "min_withheld_pairs", "anchor_band", "tracking_ok_state"})
MAP_KEYS = frozenset({"thresholds_m", "voxel_size_m"})
INPUT_KEYS = frozenset({"source_run_id", "gt_free", "evaluation_only_u03"})
# Config gate value -> recorded comparison mapping key it must equal.
MAPPING_EQUIVALENT = {"residual_threshold_m": "residual_threshold_m", "min_anchor_inliers": "min_inliers",
                      "min_anchor_inlier_ratio": "min_inlier_ratio", "min_coverage_bins": "min_coverage_bins"}
ANCHOR_GATE_FIELDS = (
    "frame_id", "timestamp_s", "n_calibration_pairs", "n_withheld_pairs", "anchor_ratio", "anchor_inliers",
    "abs_log_anchor_ratio", "anchor_reason", "anchor_applied", "applied_scale",
    "withheld_median_abs_residual_before_m", "withheld_median_abs_residual_after_m", "withheld_reason",
    "coverage_bins_4x4", "tracking_state", "tracking_reason",
    "flag_A1", "flag_A2", "flag_A3", "flag_A4", "flag_S1", "flags", "decision", "decision_reason",
)


def _exact(value, keys, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    if set(value) != set(keys):
        raise ValueError(f"{where} keys differ: unknown {sorted(set(value) - set(keys))}, "
                         f"missing {sorted(set(keys) - set(value))}")
    return value


def _number(value, where, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, int if integer else Real) or not math.isfinite(value):
        raise ValueError(f"{where} must be a finite {'integer' if integer else 'number'}, got {value!r}")
    return value


def _text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where} must be a non-empty string")
    return value


def validate_config(config):
    """Exact keys at every level; every threshold carries its source citation."""
    _exact(config, CONFIG_KEYS, "robust_fusion config")
    if config["schema"] != CONFIG_SCHEMA:
        raise ValueError(f"robust_fusion config schema must be {CONFIG_SCHEMA!r}")
    _text(config["description"], "description")
    for section, keys in (("gate", GATE_KEYS), ("map_evaluation", MAP_KEYS)):
        for key, entry in _exact(config[section], keys, section).items():
            _exact(entry, {"value", "source"}, f"{section}.{key}")
            _text(entry["source"], f"{section}.{key}.source")
    gate = gate_values(config)
    if _number(gate["residual_threshold_m"], "residual_threshold_m") <= 0:
        raise ValueError("residual_threshold_m must be > 0")
    for key in ("min_anchor_inliers", "min_withheld_pairs"):
        if _number(gate[key], key, integer=True) < 1:
            raise ValueError(f"{key} must be >= 1")
    if not 0 < _number(gate["min_anchor_inlier_ratio"], "min_anchor_inlier_ratio") <= 1:
        raise ValueError("min_anchor_inlier_ratio must be in (0, 1]")
    if not 1 <= _number(gate["min_coverage_bins"], "min_coverage_bins", integer=True) <= 16:
        raise ValueError("min_coverage_bins must be in [1, 16]")
    if _number(gate["anchor_band"], "anchor_band") <= 1:
        raise ValueError("anchor_band must be > 1")
    if gate["tracking_ok_state"] not in STATES:
        raise ValueError(f"tracking_ok_state must be one of {sorted(STATES)}")
    thresholds = config["map_evaluation"]["thresholds_m"]["value"]
    if (not isinstance(thresholds, list) or not thresholds
            or any(_number(t, "thresholds_m") <= 0 for t in thresholds) or thresholds != sorted(set(thresholds))):
        raise ValueError("thresholds_m must be a non-empty strictly increasing list of positive numbers")
    if _number(config["map_evaluation"]["voxel_size_m"]["value"], "voxel_size_m") <= 0:
        raise ValueError("voxel_size_m must be > 0")
    variants = config["variants"]
    if not isinstance(variants, list) or [_exact(v, {"name", "description"}, "variant")["name"] for v in variants] != list(VARIANTS):
        raise ValueError(f"variants must be exactly {list(VARIANTS)}")
    for variant in variants:
        _text(variant["description"], f"variant {variant['name']} description")
    inputs = _exact(config["inputs"], INPUT_KEYS, "inputs")
    _text(inputs["source_run_id"], "inputs.source_run_id")
    for key in ("gt_free", "evaluation_only_u03"):
        if not isinstance(inputs[key], list) or not inputs[key]:
            raise ValueError(f"inputs.{key} must be a non-empty list")
        for item in inputs[key]:
            _text(item, f"inputs.{key} item")
    return config


def load_config(path):
    """The validated config and the sha256 of its exact bytes (U-03 refuses a different hash)."""
    path = Path(path)
    return validate_config(json.loads(path.read_text(encoding="utf-8"))), sha256_file(path)


def gate_values(config):
    return {key: entry["value"] for key, entry in config["gate"].items()}


def check_config_against_sources(config, sources):
    """Refuse a config whose values differ from the thresholds the source signals were computed with."""
    gate, mapping = gate_values(config), sources.mapping
    mismatches = [f"{key}={gate[key]!r} vs recorded mapping {name}={mapping[name]!r}"
                  for key, name in MAPPING_EQUIVALENT.items() if gate[key] != mapping[name]]
    if gate["anchor_band"] != ANCHOR_BAND:
        mismatches.append(f"anchor_band={gate['anchor_band']!r} vs U-01 ANCHOR_BAND={ANCHOR_BAND!r}")
    voxel = config["map_evaluation"]["voxel_size_m"]["value"]
    if voxel != mapping["voxel_size_m"]:
        mismatches.append(f"voxel_size_m={voxel!r} vs recorded mapping voxel_size_m={mapping['voxel_size_m']!r}")
    thresholds = config["map_evaluation"]["thresholds_m"]["value"]
    recorded = sources.comparison["config"].get("thresholds_m")
    if recorded != thresholds:
        mismatches.append(f"thresholds_m={thresholds!r} vs recorded comparison thresholds_m={recorded!r}")
    if mismatches:
        raise ValueError("robust_fusion config differs from the source comparison run: " + "; ".join(mismatches))


def _check_ratio(value, where="anchor_ratio"):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{where} must be a finite number > 0 or null, got {value!r}")
    return float(value)


def anchored_prediction(prediction: GeometryPrediction, anchor_ratio) -> GeometryPrediction:
    """z'_f = a_f * z_pred on a new in-memory prediction; mask, confidence, K and metadata unchanged.

    A null a_f (flag A1) leaves the frame uncorrected and returns the input object
    itself. NaN, infinite, zero, negative or boolean ratios are refused.
    """
    if anchor_ratio is None:
        return prediction
    ratio = _check_ratio(anchor_ratio)
    # float64 product, then the contract's float32; invalid pixels stay NaN.
    depth = (prediction.depth_m.astype(np.float64) * ratio).astype(np.float32)
    return dataclasses.replace(prediction, depth_m=depth)


def gate_decision(signals: dict, config: dict) -> dict:
    """Pre-registered rule: reject when any flag fires. A flag that cannot be evaluated is
    recorded as unavailable (None) with its reason and never fires; malformed inputs raise."""
    gate = gate_values(config)
    states, fired, unavailable = {}, [], []
    ratio = signals["anchor_ratio"]
    if ratio is None:
        reason = _text(signals.get("anchor_reason"), "anchor_reason for a null anchor_ratio")
        states.update(A1=True, A2=None)
        fired.append(f"A1 anchor ratio unavailable ({reason})")
        unavailable.append("A2 needs an anchor ratio")
    else:
        deviation = abs(math.log(_check_ratio(ratio)))
        states.update(A1=False, A2=deviation > math.log(gate["anchor_band"]))
        if states["A2"]:
            fired.append(f"A2 |log a_f|={deviation!r} > log({gate['anchor_band']!r})")
    count, withheld = _number(signals["n_withheld_pairs"], "n_withheld_pairs", integer=True), \
        signals["withheld_median_abs_residual_m"]
    if count < 0:
        raise ValueError("n_withheld_pairs must be >= 0")
    if count >= gate["min_withheld_pairs"]:
        if withheld is None or _number(withheld, "withheld_median_abs_residual_m") < 0:
            raise ValueError("withheld_median_abs_residual_m must be a finite number >= 0 when withheld pairs exist")
        states["A3"] = withheld > gate["residual_threshold_m"]
        if states["A3"]:
            fired.append(f"A3 withheld median |residual|={withheld!r} m > {gate['residual_threshold_m']!r} m")
    else:
        if withheld is not None:
            raise ValueError("withheld_median_abs_residual_m must be null without withheld pairs")
        states["A3"] = None
        unavailable.append(f"A3 needs >= {gate['min_withheld_pairs']} withheld pair(s), frame has {count}")
    coverage = _number(signals["coverage_bins_4x4"], "coverage_bins_4x4", integer=True)
    if not 0 <= coverage <= 16:
        raise ValueError("coverage_bins_4x4 must be in [0, 16]")
    states["A4"] = coverage < gate["min_coverage_bins"]
    if states["A4"]:
        fired.append(f"A4 coverage {coverage}/16 < {gate['min_coverage_bins']}/16 bins")
    tracking = signals["tracking_state"]
    if tracking is None:
        states["S1"] = None
        unavailable.append(f"S1 ({_text(signals.get('tracking_reason'), 'tracking_reason for a null state')})")
    else:
        if tracking not in STATES:
            raise ValueError(f"tracking_state must be one of {sorted(STATES)}, got {tracking!r}")
        states["S1"] = tracking != gate["tracking_ok_state"]
        if states["S1"]:
            fired.append(f"S1 tracking state {tracking} != {gate['tracking_ok_state']}")
    flags = tuple(name for name in FLAGS if states[name] is True)
    decision = "reject" if flags else "accept"
    reason = f"{decision}: " + ("; ".join(fired) if fired else "no flag fired")
    if unavailable:
        reason += "; unavailable: " + "; ".join(unavailable)
    return {"decision": decision, "accepted": not flags, "flags": flags, "flag_states": states, "reason": reason}


def _median(values):
    return float(np.median(values)) if len(values) else None


def anchor_gate_rows(sources, pairs, withheld, signals, config):
    """One auditable row per keyframe: decision inputs, applied correction, flags, decision and reason."""
    scale = float(sources.alignment["scale"])
    rows = []
    for signal in signals:
        decision = gate_decision(signal, config)
        u01 = {name: bool(signal[f"flag_{name}"]) for name in FLAGS}
        if u01 != {name: decision["flag_states"][name] is True for name in FLAGS}:
            raise ValueError(f"gate flags for frame {signal['frame_id']} differ from the U-01 signal flags")
        check = (pairs.frame_id == signal["frame_id"]) & withheld
        before = np.abs(scale * pairs.source_depth[check] - pairs.target_depth_m[check])
        if _median(before) != signal["withheld_median_abs_residual_m"]:
            raise ValueError(f"withheld residual for frame {signal['frame_id']} differs from the U-01 signal")
        applied = signal["anchor_ratio"] is not None
        factor = float(signal["anchor_ratio"]) if applied else 1.0
        after = np.abs(scale * pairs.source_depth[check] - factor * pairs.target_depth_m[check])
        state = lambda name: "unavailable" if decision["flag_states"][name] is None else decision["flag_states"][name]
        rows.append({**{key: signal[key] for key in (
            "frame_id", "timestamp_s", "n_calibration_pairs", "n_withheld_pairs", "anchor_ratio", "anchor_inliers",
            "abs_log_anchor_ratio", "anchor_reason", "withheld_reason", "coverage_bins_4x4", "tracking_state",
            "tracking_reason")},
            "anchor_applied": applied, "applied_scale": factor,
            "withheld_median_abs_residual_before_m": _median(before),
            "withheld_median_abs_residual_after_m": _median(after),
            **{f"flag_{name}": state(name) for name in FLAGS},
            "flags": ";".join(decision["flags"]), "decision": decision["decision"],
            "decision_reason": decision["reason"]})
    return rows


def summarize(rows, pairs, withheld, sources, config, config_sha256, residual_check, tracking_info):
    """Deterministic GT-free summary; the decisions list is what U-03 must reproduce exactly."""
    scale = float(sources.alignment["scale"])
    factors = {row["frame_id"]: row["applied_scale"] for row in rows}
    per_pair = np.array([factors[int(f)] for f in pairs.frame_id[withheld]])
    pooled_before = np.abs(scale * pairs.source_depth[withheld] - pairs.target_depth_m[withheld])
    pooled_after = np.abs(scale * pairs.source_depth[withheld] - per_pair * pairs.target_depth_m[withheld])
    evaluable = [r for r in rows if r["withheld_median_abs_residual_before_m"] is not None]
    applied = [r["anchor_ratio"] for r in rows if r["anchor_applied"]]
    accepted = sum(r["decision"] == "accept" for r in rows)
    return {
        "scope": "GT-free; offline final-snapshot anchors; no map built; no real-time claim",
        "config_schema": config["schema"], "config_sha256": config_sha256, "gate": gate_values(config),
        "keyframes": len(rows), "accepted": accepted, "rejected": len(rows) - accepted,
        "all_frames_rejected": accepted == 0,
        "flag_counts": {name: {state: sum(r[f"flag_{name}"] == value for r in rows)
                               for state, value in (("fired", True), ("clear", False), ("unavailable", "unavailable"))}
                        for name in FLAGS},
        "anchoring": {"applied": len(applied), "not_applied": len(rows) - len(applied),
                      "anchor_ratio_min": min(applied) if applied else None,
                      "anchor_ratio_max": max(applied) if applied else None,
                      "max_abs_log_anchor_ratio": max(abs(math.log(a)) for a in applied) if applied else None},
        "withheld_validation": {
            "note": "GT-free validation only; reported, never used for tuning",
            "frames_evaluable": len(evaluable),
            "frames_improved": sum(r["withheld_median_abs_residual_after_m"] < r["withheld_median_abs_residual_before_m"]
                                   for r in evaluable),
            "frames_worse": sum(r["withheld_median_abs_residual_after_m"] > r["withheld_median_abs_residual_before_m"]
                                for r in evaluable),
            "pooled_pairs": int(withheld.sum()),
            "pooled_median_abs_residual_before_m": _median(pooled_before),
            "pooled_median_abs_residual_after_m": _median(pooled_after),
            "median_of_frame_medians_before_m": _median([r["withheld_median_abs_residual_before_m"] for r in evaluable]),
            "median_of_frame_medians_after_m": _median([r["withheld_median_abs_residual_after_m"] for r in evaluable])},
        "decisions": [{"frame_id": r["frame_id"], "decision": r["decision"], "flags": r["flags"],
                       "applied_scale": r["applied_scale"]} for r in rows],
        "global_scale": scale, "tracking": tracking_info, "residuals_crosscheck": residual_check,
        "sources": sources.provenance}


def _git_state(repo_root):
    """HEAD and dirty flag, as runs.geometry_run.collect_git_state; kept local because that
    module imports evaluation code, which this GT-free layer must not load."""
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=True,
                                  timeout=30).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"git {' '.join(args)} failed: {exc}") from exc

    return git("rev-parse", "HEAD").strip(), bool(git("status", "--porcelain").strip())


def run_anchor_gate(repo_root, comparison_run, slam_run, geometry_run, config_path, *, run_id, output_root=None):
    """Preflight refusals write nothing; later failures leave a terminal run.json."""
    config, config_sha256 = load_config(config_path)
    sources = load_sources(comparison_run, slam_run, geometry_run)
    check_config_against_sources(config, sources)
    pairs, withheld = rebuild_pairs(sources.inputs, sources.mapping)
    residual_check = check_recorded_residuals(sources.global_dir / "residuals.csv", pairs, withheld)
    tracking, tracking_info = tracking_states(slam_run, sources.inputs.slam)
    commit, dirty = _git_state(repo_root)
    inputs = sources.inputs
    cpu = next((c.strip() for c in (platform.processor(), platform.machine(), platform.system()) if c and c.strip()),
               "unknown")
    record = dict(run_id=run_id, git_commit=commit, dirty_worktree=dirty, dataset=inputs.slam["dataset"],
                  method="P1-global", model=inputs.geometry["model"], slam=inputs.slam["slam"],
                  alignment={"method": sources.global_record["alignment"]["method"],
                             "thresholds": sources.global_record["alignment"]["thresholds"]},
                  config={"control_label": "per-keyframe sparse anchoring and gate decisions (GT-free); no new map",
                          "sources": sources.provenance, "mapping": sources.mapping, "robust_fusion": config,
                          "robust_fusion_sha256": config_sha256,
                          "scope": "offline retained-keyframe decisions; GT-free; recorded before any U-03 GT comparison"},
                  hardware={"gpu": None, "cpu": cpu, "ram_gb": None},
                  environment={"python": platform.python_version(), "numpy": np.__version__},
                  seed=sources.mapping["seed"], started_at=format_utc(datetime.now(timezone.utc)),
                  status="running", reason=None, artifacts={})
    build_run_manifest(**record)
    directory = Path(output_root or Path(repo_root) / "results/runs") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(build_run_manifest(**record), directory)
    try:
        signals = frame_signals(sources, pairs, withheld, tracking)
        write_csv(directory / "frame_signals.csv", SIGNAL_FIELDS, signals)
        rows = anchor_gate_rows(sources, pairs, withheld, signals, config)
        write_csv(directory / "anchor_gate.csv", ANCHOR_GATE_FIELDS, rows)
        write_json(directory / "anchor_gate.json",
                   summarize(rows, pairs, withheld, sources, config, config_sha256, residual_check, tracking_info))
        record["artifacts"].update(frame_signals="frame_signals.csv", anchor_gate="anchor_gate.csv",
                                   summary="anchor_gate.json")
        record.update(status="ok", reason=None)
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted: anchor gate stopped")
        raise
    except Exception as exc:
        record.update(status="failed", reason=f"anchor_gate_failed: {type(exc).__name__}: {exc}")
    finally:
        write_run_manifest(build_run_manifest(**record), directory, overwrite=True)
    return directory


__all__ = ["anchored_prediction", "check_config_against_sources", "gate_decision", "load_config", "run_anchor_gate",
           "validate_config"]
