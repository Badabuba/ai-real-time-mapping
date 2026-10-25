"""P1-robust modules keep GT-free signals separate from evaluation and load no native/model runtime."""
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE_OR_MODEL = ("pyslam", "torch", "depth_anything_3", "unidepth")
GT_FREE_FORBIDDEN = NATIVE_OR_MODEL + ("rt_mapping.evaluation", "rt_mapping.data.tum")
GT_FREE = {path: GT_FREE_FORBIDDEN for path in ("src/rt_mapping/alignment/frame_signals.py",
                                                "src/rt_mapping/alignment/anchoring.py", "scripts/run_anchor_gate.py")}
EVALUATION = {"src/rt_mapping/evaluation/frame_diagnostics.py": NATIVE_OR_MODEL}


def _imports(path):
    names = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_direct_imports_respect_the_gt_free_and_evaluation_boundaries():
    for path, forbidden in {**GT_FREE, **EVALUATION}.items():
        bad = {name for name in _imports(path) for prefix in forbidden if name == prefix or name.startswith(prefix + ".")}
        assert not bad, f"{path} imports {sorted(bad)}"


def test_modules_import_without_native_or_model_runtime():
    code = (f"import sys; sys.path.insert(0,{str(ROOT / 'src')!r}); "
            "import rt_mapping.alignment.frame_signals, rt_mapping.evaluation.frame_diagnostics; "
            f"loaded = [n for n in {NATIVE_OR_MODEL!r} if n in sys.modules]; assert not loaded, loaded")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_gt_free_anchoring_loads_no_evaluation_module():
    code = (f"import sys; sys.path.insert(0,{str(ROOT / 'src')!r}); import rt_mapping.alignment.anchoring; "
            f"loaded = [n for n in sys.modules if n.startswith('rt_mapping.evaluation') or n in {NATIVE_OR_MODEL!r}]; "
            "assert not loaded, loaded")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
