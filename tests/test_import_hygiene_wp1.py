"""WP1 model-selection modules and CLIs import without heavy model frameworks (N-03, N-04)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HEAVY = ("torch", "torchvision", "depth_anything_3", "unidepth", "cv2", "huggingface_hub", "PIL")
MODULES = ("rt_mapping.adapters.unidepth_v2", "rt_mapping.runs.geometry_run",
           "rt_mapping.evaluation.geometry_verification", "rt_mapping.evaluation.model_selection",
           "rt_mapping.evaluation.prediction_grid", "rt_mapping.evaluation.confidence_ablation")
SCRIPTS = ("run_geometry_benchmark", "compare_geometry_models", "verify_geometry_run", "analyze_confidence")

SNIPPET = f"""
import importlib, importlib.util, sys
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
for name in {MODULES!r}:
    importlib.import_module(name)
for script in {SCRIPTS!r}:
    spec = importlib.util.spec_from_file_location(script, {str(REPO_ROOT / "scripts")!r} + "/" + script + ".py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
print(",".join(sorted(m for m in {HEAVY!r} if m in sys.modules)))
"""


def test_wp1_selection_modules_and_clis_stay_light() -> None:
    done = subprocess.run([sys.executable, "-c", SNIPPET], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "", f"heavy modules imported: {done.stdout.strip()}"
