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

Наявні:

- `check_wp1_environment.py` — звіт про Python/torch/CUDA/DA3;
- `build_tum_manifest.py` — побудова або `--check` dataset manifest (C2);
- `run_tum_da3_metric.py` — DA3 Metric на frozen TUM split → `results/runs/<run_id>/` (C5; логіка в `rt_mapping.adapters.da3_metric` і `rt_mapping.runs.geometry_run`);
- `run_da3_metric_smoke.py` — ранній synthetic smoke (до C5, не змінювався).

Business logic має бути у src/rt_mapping, а scripts лише парсить аргументи/config та викликає модулі. Команди додаються до root README тільки після smoke verification.
