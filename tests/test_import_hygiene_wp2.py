"""The WP2 observation/contract modules do not load native or model runtimes."""
from pathlib import Path
import subprocess
import sys


def test_tracking_modules_import_without_native_runtime():
    root = Path(__file__).resolve().parents[1]
    code = (f"import sys; sys.path.insert(0,{str(root/'src')!r}); "
            "import rt_mapping.contracts.slam, rt_mapping.slam.tracking_log, rt_mapping.slam.smoke; "
            "assert not any(n in sys.modules for n in ('cv2','torch','pyslam','g2o','PIL'))")
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stdout+done.stderr
