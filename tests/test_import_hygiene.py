"""Importing rt_mapping (and the DA3 runner CLI module) must not import heavy model frameworks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HEAVY = ("torch", "torchvision", "depth_anything_3", "cv2", "huggingface_hub", "PIL")

SNIPPET = f"""
import importlib, importlib.util, sys
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
for name in ["rt_mapping", "rt_mapping.contracts", "rt_mapping.data", "rt_mapping.data.tum",
             "rt_mapping.data.manifest", "rt_mapping.geometry", "rt_mapping.evaluation",
             "rt_mapping.runs", "rt_mapping.runs.geometry_run", "rt_mapping.adapters",
             "rt_mapping.adapters.da3_metric", "rt_mapping.alignment",
             "rt_mapping.alignment.correspondences", "rt_mapping.fusion",
             "rt_mapping.runs.mapping_run"]:
    importlib.import_module(name)
spec = importlib.util.spec_from_file_location("run_tum_da3_metric", {str(REPO_ROOT / "scripts" / "run_tum_da3_metric.py")!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
loaded = sorted(m for m in {HEAVY!r} if m in sys.modules)
print(",".join(loaded))
"""


def test_no_source_file_is_git_ignored() -> None:
    """A broad ignore rule (e.g. 'models/' for weights) must not hide package code."""
    import shutil

    import pytest

    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("git checkout not available")
    files = [p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "src").rglob("*.py")]
    done = subprocess.run(
        ["git", "check-ignore", "--no-index", *files], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    assert done.stdout.strip() == "", f"git-ignored source files: {done.stdout.split()}"


def test_package_and_runner_imports_stay_light() -> None:
    done = subprocess.run([sys.executable, "-c", SNIPPET], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "", f"heavy modules imported: {done.stdout.strip()}"
