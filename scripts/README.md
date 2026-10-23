# Scripts

WP2 (Ярополк), реалізовано: `check_wp2_environment.py` (dataset/source/runtime checks), `build_wp2_native.py` (macOS native build), `prepare_wp2_baseline.py` (RGB-only view/config), `run_wp2_pyslam.py` (recorded B0 smoke). Відтворення і фактичний 200-frame результат: [docs/WP2_SETUP.md](../docs/WP2_SETUP.md).

`run_wp2_pyslam.py --export-sparse` додає post-shutdown landmarks, keyframe poses/calibration, raw/undistorted pixel links та PLY у **новому run**. Формат і обмеження: [docs/WP2_SPARSE_EXPORT.md](../docs/WP2_SPARSE_EXPORT.md). `visualize_wp2_trajectory.py` читає вже збережені poses без запуску SLAM.

Майбутні тонкі CLI entry points:

- download/verify dataset manifest;
- run SLAM baseline;
- run geometry inference;
- align and fuse artifacts;
- evaluate one run;
- aggregate benchmark runs.

Business logic має бути у src/rt_mapping, а scripts лише парсить аргументи/config та викликає модулі. Команди додаються до root README тільки після smoke verification.
