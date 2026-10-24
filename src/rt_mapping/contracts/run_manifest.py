"""run.json contract: the reproducibility record of one run (docs/EXPERIMENTS.md §5).

Every key is required at every level and unknown keys are rejected; null is
allowed only where documented below. Values must be JSON-compatible and finite,
with no absolute paths and no secret-like keys. The caller supplies git,
hardware, environment and model values; this module never inspects the host
or imports model frameworks.

Method-dependent blocks:
    model      null iff method is B0 or B1
    slam       required for B0, B1, P1-*; null for model-spike; optional for P2
    alignment  required for P1-global, P1-window, P2; null otherwise
    reason     required for degraded/failed/skipped; null otherwise
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rt_mapping.contracts._validation import check_json_value, is_absolute_path

SCHEMA = "rt_mapping.run_manifest/v1"
RUN_JSON = "run.json"

METHODS = ("B0", "B1", "P1-raw", "P1-global", "P1-window", "P2", "model-spike")
SPLITS = ("smoke", "development", "selection", "held-out")
STATUSES = ("planned", "running", "ok", "degraded", "failed", "skipped")
TERMINAL_STATUSES = frozenset({"ok", "degraded", "failed", "skipped"})
_REASON_STATUSES = frozenset({"degraded", "failed", "skipped"})

_MODEL_NULL_METHODS = frozenset({"B0", "B1"})
_SLAM_REQUIRED_METHODS = frozenset({"B0", "B1", "P1-raw", "P1-global", "P1-window"})
_SLAM_NULL_METHODS = frozenset({"model-spike"})
_ALIGNMENT_REQUIRED_METHODS = frozenset({"P1-global", "P1-window", "P2"})

TOP_LEVEL_KEYS = frozenset(
    {
        "schema", "run_id", "git_commit", "dirty_worktree", "dataset", "method", "model", "slam",
        "alignment", "config", "hardware", "environment", "seed", "started_at", "status", "reason",
        "artifacts",
    }
)
DATASET_KEYS = frozenset({"name", "sequence", "split", "checksum", "manifest"})
MODEL_KEYS = frozenset({"repo", "revision", "checkpoint", "dtype"})
SLAM_KEYS = frozenset({"repo", "revision", "config", "pose_convention"})
ALIGNMENT_KEYS = frozenset({"method", "thresholds"})
HARDWARE_KEYS = frozenset({"gpu", "cpu", "ram_gb"})

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")

# Secret detection works on key components, so "tokenizer" or "max_tokens" pass.
_SECRET_COMPONENTS = frozenset(
    {"password", "passwd", "passphrase", "secret", "token", "credential", "credentials", "apikey"}
)
_SECRET_PAIRS = frozenset({("api", "key"), ("access", "key"), ("private", "key"), ("secret", "key")})


def _key_components(key: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [part for part in re.split(r"[_\-.\s]+", spaced.lower()) if part]


def is_secret_key(key: str) -> bool:
    """True if a dict key names a credential (by whole component, not substring)."""
    parts = _key_components(key)
    if any(part in _SECRET_COMPONENTS for part in parts):
        return True
    return any(pair in _SECRET_PAIRS for pair in zip(parts, parts[1:]))


def _check_no_secret_keys(value: Any, where: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if is_secret_key(key):
                raise ValueError(f"{where} must not contain secret-like key {key!r}")
            _check_no_secret_keys(item, f"{where}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _check_no_secret_keys(item, f"{where}[{i}]")


def _exact_keys(value: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object, got {type(value).__name__}")
    missing = sorted(keys - value.keys())
    extra = sorted(str(key) for key in value.keys() - keys)
    if missing:
        raise ValueError(f"{where} is missing required keys {missing}")
    if extra:
        raise ValueError(f"{where} has unknown keys {extra}")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where} must be a non-empty string, got {value!r}")
    return value


def _choice(value: Any, choices: tuple[str, ...], where: str) -> str:
    if value not in choices:
        raise ValueError(f"{where} must be one of {list(choices)}, got {value!r}")
    return value


def _relative_path(value: Any, where: str) -> str:
    text = _text(value, where)
    if is_absolute_path(text) or "\\" in text:
        raise ValueError(f"{where} must be a relative POSIX path, got {text!r}")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"{where} must not contain empty, '.' or '..' components, got {text!r}")
    return text


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _object_or_null(value: Any, required: bool, forbidden: bool, method: str, where: str) -> bool:
    """Return True if value is a non-null block that must be validated."""
    if value is None:
        if required:
            raise ValueError(f"{where} is required for method {method!r}")
        return False
    if forbidden:
        raise ValueError(f"{where} must be null for method {method!r}")
    return True


def _validate_utc(value: Any) -> None:
    if not isinstance(value, str) or not _UTC_RE.match(value):
        raise ValueError(f"started_at must be UTC 'YYYY-MM-DDTHH:MM:SS[.ffffff]Z', got {value!r}")
    stamp = value[:-1]
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in stamp else "%Y-%m-%dT%H:%M:%S"
    try:
        datetime.strptime(stamp, fmt)
    except ValueError:
        raise ValueError(f"started_at is not a valid date/time, got {value!r}") from None


def format_utc(moment: datetime) -> str:
    """Format a timezone-aware datetime as the UTC string used by started_at."""
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("format_utc needs a timezone-aware datetime")
    utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds") + "Z"


def validate_run_manifest(data: Any) -> dict[str, Any]:
    """Validate a run manifest and return a normalised deep copy. Invalid input raises ValueError."""
    manifest = _exact_keys(data, TOP_LEVEL_KEYS, "run manifest")
    check_json_value(manifest, "run manifest")
    _check_no_secret_keys(manifest, "run manifest")

    if manifest["schema"] != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA!r}, got {manifest['schema']!r}")
    if not isinstance(manifest["run_id"], str) or not _RUN_ID_RE.match(manifest["run_id"]):
        raise ValueError(f"run_id must match {_RUN_ID_RE.pattern}, got {manifest['run_id']!r}")
    if not isinstance(manifest["git_commit"], str) or not _GIT_COMMIT_RE.match(manifest["git_commit"]):
        raise ValueError(f"git_commit must be a full 40-char lowercase hex SHA, got {manifest['git_commit']!r}")
    if not isinstance(manifest["dirty_worktree"], bool):
        raise ValueError(f"dirty_worktree must be a bool, got {manifest['dirty_worktree']!r}")

    dataset = _exact_keys(manifest["dataset"], DATASET_KEYS, "dataset")
    _text(dataset["name"], "dataset.name")
    _text(dataset["sequence"], "dataset.sequence")
    _choice(dataset["split"], SPLITS, "dataset.split")
    if not isinstance(dataset["checksum"], str) or not _SHA256_RE.match(dataset["checksum"]):
        raise ValueError(f"dataset.checksum must be 64 lowercase hex chars (SHA-256), got {dataset['checksum']!r}")
    if dataset["manifest"] is not None:
        _relative_path(dataset["manifest"], "dataset.manifest")

    method = _choice(manifest["method"], METHODS, "method")

    if _object_or_null(
        manifest["model"], method not in _MODEL_NULL_METHODS, method in _MODEL_NULL_METHODS, method, "model"
    ):
        model = _exact_keys(manifest["model"], MODEL_KEYS, "model")
        for key in sorted(MODEL_KEYS):
            _text(model[key], f"model.{key}")

    if _object_or_null(
        manifest["slam"], method in _SLAM_REQUIRED_METHODS, method in _SLAM_NULL_METHODS, method, "slam"
    ):
        slam = _exact_keys(manifest["slam"], SLAM_KEYS, "slam")
        _text(slam["repo"], "slam.repo")
        _text(slam["revision"], "slam.revision")
        _relative_path(slam["config"], "slam.config")
        _text(slam["pose_convention"], "slam.pose_convention")

    alignment_required = method in _ALIGNMENT_REQUIRED_METHODS
    if _object_or_null(manifest["alignment"], alignment_required, not alignment_required, method, "alignment"):
        alignment = _exact_keys(manifest["alignment"], ALIGNMENT_KEYS, "alignment")
        _text(alignment["method"], "alignment.method")
        thresholds = alignment["thresholds"]
        if not isinstance(thresholds, dict):
            raise ValueError("alignment.thresholds must be an object")
        for key, value in thresholds.items():
            if not _is_number(value):
                raise ValueError(f"alignment.thresholds[{key!r}] must be a number, got {value!r}")

    if not isinstance(manifest["config"], dict):
        raise ValueError(f"config must be an object, got {type(manifest['config']).__name__}")

    hardware = _exact_keys(manifest["hardware"], HARDWARE_KEYS, "hardware")
    if hardware["gpu"] is not None:
        _text(hardware["gpu"], "hardware.gpu")
    _text(hardware["cpu"], "hardware.cpu")
    ram = hardware["ram_gb"]
    if ram is not None and (not _is_number(ram) or ram <= 0):
        raise ValueError(f"hardware.ram_gb must be a number > 0 or null, got {ram!r}")

    environment = manifest["environment"]
    if not isinstance(environment, dict) or "python" not in environment:
        raise ValueError("environment must be an object containing at least 'python'")
    for key, value in environment.items():
        _text(value, f"environment[{key!r}]")

    seed = manifest["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed must be an integer >= 0, got {seed!r}")

    _validate_utc(manifest["started_at"])

    status = _choice(manifest["status"], STATUSES, "status")
    if status in _REASON_STATUSES:
        _text(manifest["reason"], "reason")
    elif manifest["reason"] is not None:
        raise ValueError(f"reason must be null for status {status!r}")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict):
        raise ValueError("artifacts must be an object mapping names to run-relative paths")
    for name, path in artifacts.items():
        _text(name, "artifacts key")
        _relative_path(path, f"artifacts[{name!r}]")

    # JSON round trip = deep copy with plain Python types.
    return json.loads(json.dumps(manifest, allow_nan=False))


def build_run_manifest(**fields: Any) -> dict[str, Any]:
    """Build and validate a manifest; schema is filled in. Returns a new dict."""
    if "schema" in fields and fields["schema"] != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA!r}, got {fields['schema']!r}")
    return validate_run_manifest({**fields, "schema": SCHEMA})


def dump_run_manifest(manifest: dict[str, Any]) -> str:
    """Validate and serialise to stable JSON text (sorted keys, newline at end)."""
    valid = validate_run_manifest(manifest)
    return json.dumps(valid, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _reject_constant(name: str) -> None:
    raise ValueError(f"run.json must not contain {name}")


def load_run_manifest(path: str | Path) -> dict[str, Any]:
    """Read and validate a run.json file."""
    text = Path(path).read_text(encoding="utf-8")
    return validate_run_manifest(json.loads(text, parse_constant=_reject_constant))


def write_run_manifest(manifest: dict[str, Any], run_dir: str | Path, *, overwrite: bool = False) -> Path:
    """Write <run_dir>/run.json; run_dir's name must equal run_id.

    A run.json whose status is finished (ok/degraded/failed/skipped), or that
    cannot be read, is never replaced. A planned/running one is replaced only
    with overwrite=True.
    """
    text = dump_run_manifest(manifest)
    run_dir = Path(run_dir)
    if run_dir.name != manifest["run_id"]:
        raise ValueError(f"run directory name {run_dir.name!r} differs from run_id {manifest['run_id']!r}")
    path = run_dir / RUN_JSON
    if path.exists():
        try:
            existing_status = json.loads(path.read_text(encoding="utf-8")).get("status")
        except (ValueError, AttributeError):
            raise ValueError(f"{path} exists and cannot be read; refusing to replace it") from None
        if existing_status not in ("planned", "running"):
            raise ValueError(f"{path} has status {existing_status!r}; a finished run.json is never edited")
        if not overwrite:
            raise ValueError(f"{path} exists (status {existing_status!r}); pass overwrite=True to update it")
    run_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path
