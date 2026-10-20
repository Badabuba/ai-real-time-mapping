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

Required run.json fields наведені в docs/EXPERIMENTS.md. Результат без git commit, dataset sequence, config, method, hardware і status не переноситься до порівняльної таблиці.
