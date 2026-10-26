"""Build pinned pySLAM's classical native dependencies on Apple Silicon.

Run after installing Homebrew/Python dependencies (docs/REPRODUCIBILITY.md). Does not
install system packages or fetch learned models. Each command has a separate
log; a failed configure/build stops immediately. Jobs default to 2.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REVISION = "96019cfafcfc099ac9866884d7143a9ed1451a0d"
GTSAM_REVISION = "c57988fe554e7213c77fe379c1d7c483de26ad33"
COMPONENTS = ("g2o", "cpp", "orb", "dbow3", "dbow2", "ibow", "gtsam")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=(*COMPONENTS, "all"), default="all")
    parser.add_argument("--source", type=Path, default=ROOT / "external/pyslam")
    parser.add_argument("--python", type=Path, default=ROOT / ".venv-pyslam/bin/python")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if sys.platform != "darwin" or args.jobs < 1:
        parser.error("this build recipe is for macOS, with jobs >= 1")
    source, python = args.source.absolute(), args.python.absolute()
    logs = ROOT / "logs/wp2/native"
    logs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
           "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(ROOT / ".local/wp2/uv-cache"))}

    def run(label, command, cwd=None):
        print(f"{label} -> {logs / (label + '.log')}", flush=True)
        with (logs / (label + ".log")).open("w", encoding="utf-8") as output:
            subprocess.run(command, cwd=cwd or ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)

    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != UPSTREAM_REVISION:
        parser.error(f"source revision must be {UPSTREAM_REVISION}, got {actual}")
    brew = Path(subprocess.check_output(["brew", "--prefix"], text=True).strip())
    base = ["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={python.parent / 'ninja'}",
            "-DCMAKE_C_COMPILER=/usr/bin/clang", "-DCMAKE_CXX_COMPILER=/usr/bin/clang++",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
            f"-DPYTHON_EXECUTABLE={python}", f"-DPython3_EXECUTABLE={python}", f"-DPython_EXECUTABLE={python}",
            f"-DOpenCV_DIR={brew}/opt/opencv@4/lib/cmake/opencv4",
            f"-DEigen3_DIR={brew}/opt/eigen/share/eigen3/cmake"]

    def build(label, relative, targets=(), options=(), build_dir="build-wp2"):
        path = source / relative
        directory = path / build_dir
        run(label + "-configure", ["cmake", "-S", str(path), "-B", str(directory), *base, *options])
        command = ["cmake", "--build", str(directory), "--parallel", str(args.jobs)]
        if targets:
            command += ["--target", *targets]
        run(label + "-build", command)

    selected = COMPONENTS if args.component == "all" else (args.component,)
    try:
        for component in selected:
            if component == "g2o":
                suite = brew / "opt/suite-sparse"
                build("g2o", "thirdparty/g2opy", ("g2o",), [
                    f"-DCHOLMOD_INCLUDE_DIR={suite}/include/suitesparse", f"-DCHOLMOD_LIBRARY={suite}/lib/libcholmod.dylib",
                    f"-DCSPARSE_INCLUDE_DIR={suite}/include/suitesparse", f"-DCSPARSE_LIBRARY={suite}/lib/libcxsparse.dylib",
                    "-DG2O_BUILD_APPS=OFF", "-DG2O_BUILD_EXAMPLES=OFF"])
            elif component == "cpp":
                build("cpp", "cpp")
            elif component == "orb":
                build("orb", "thirdparty/orbslam2_features", ("orbslam2_features",))
            elif component == "dbow3":
                prefix = source / "thirdparty/pydbow3/modules/dbow3/install"
                build("dbow3", "thirdparty/pydbow3/modules/dbow3", ("install",), [f"-DCMAKE_INSTALL_PREFIX={prefix}"])
                build("pydbow3", "thirdparty/pydbow3", ("pydbow3",))
            elif component == "dbow2":
                build("dbow2", "thirdparty/pydbow2/modules/dbow2")
                build("pydbow2", "thirdparty/pydbow2", ("pydbow2",))
            elif component == "ibow":
                # Its parent CMakeLists expects these libraries in build/, not build-wp2/.
                build("obindex2", "thirdparty/pyibow/modules/obindex2/lib", build_dir="build")
                build("ibow-lcd", "thirdparty/pyibow/modules/ibow-lcd", build_dir="build")
                build("pyibow", "thirdparty/pyibow", ("pyibow", "pyobindex2"))
            elif component == "gtsam":
                path = source / "thirdparty/gtsam_local"
                if not path.exists():
                    run("gtsam-clone", ["git", "clone", "--depth", "1", "--branch", "4.2a9", "https://github.com/borglab/gtsam.git", str(path)])
                revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
                if revision != GTSAM_REVISION:
                    raise ValueError(f"GTSAM revision mismatch: {revision}")
                patch = source / "thirdparty/gtsam.patch"
                probe = subprocess.run(["git", "apply", "--check", str(patch)], cwd=path, capture_output=True)
                if probe.returncode == 0:
                    run("gtsam-upstream-patch", ["git", "apply", str(patch)], cwd=path)
                else:
                    subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=path, check=True)
                build("gtsam", "thirdparty/gtsam_local", ("gtsam_py", "CppUnitLite"), [
                    f"-DCMAKE_INSTALL_PREFIX={path}/install", "-DGTSAM_USE_SYSTEM_EIGEN=ON",
                    "-DGTSAM_BUILD_WITH_MARCH_NATIVE=OFF", "-DGTSAM_WITH_TBB=OFF", "-DGTSAM_BUILD_PYTHON=ON",
                    "-DGTSAM_BUILD_TESTS=OFF", "-DGTSAM_BUILD_EXAMPLES_ALWAYS=OFF", "-DGTSAM_BUILD_UNSTABLE=OFF",
                    "-DGTSAM_THROW_CHEIRALITY_EXCEPTION=OFF", "-DGTSAM_PYTHON_VERSION=3.11"])
                run("gtsam-install", ["cmake", "--install", str(path / "build-wp2")])
                run("gtsam-python-install", ["uv", "pip", "install", "--python", str(python), "--no-build-isolation", "--no-deps", str(path / "build-wp2/python")])
                build("gtsam-factors", "thirdparty/gtsam_factors", ("gtsam_factors",))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Native build failed: {exc}. See {logs}", file=sys.stderr)
        return 1
    print("Native targets built. Run the entry-point import probe, then a real smoke run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
