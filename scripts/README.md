# Scripts

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
