# Results

Generated runs зберігаються локально в results/runs/<run_id>/ і ігноруються Git. До repo можна додавати лише невеликі агреговані CSV/JSON, plots та previews, потрібні для звіту.

Очікуваний run layout:

```text
results/runs/<run_id>/
├── run.json
├── metrics.json
├── trajectory.csv
├── timing.csv
├── alignment.json
├── map.ply
└── preview.png
```

Depth-only geometry run (C5, `scripts/run_tum_da3_metric.py`) пише `run.json`, `predictions/frame_XXXXXX.npz` (без GT), `metrics.json`, `timing.json` — див. docs/EXPERIMENTS.md §5.1. Historical `results/runs/tum_fr1_xyz_da3metric/` створений до C5 (старий формат, K через cx·sx) і не змінюється.

Required run.json fields наведені в docs/EXPERIMENTS.md. Результат без git commit, dataset sequence, config, method, hardware і status не переноситься до порівняльної таблиці.
