# Integration — 25 жовтня 2026

Назарів DA3 Metric adapter/runner (C5, PR #4) та Ярополків pySLAM baseline/sparse export (PR #5) merged у `develop`; [PR #6](https://github.com/Badabuba/ai-real-time-mapping/pull/6) переніс усю історію в `main` (`36ed781`). WP3/WP4 тепер мають synthetic-verified alignment/fusion та offline artifact CLI. Real-data benchmark і запуск усіх native/GPU adapters однією командою ще не завершені. Аудит і поточні команди: [YULIAN_HANDOFF.md](YULIAN_HANDOFF.md).

## Перевірено

- Combined CPU suite: **385 passed, 1 skipped** (`.venv-wp2/bin/python -m pytest tests -q`). Native-only sparse API check окремо пройшов раніше у `.venv-pyslam`; GPU DA3 inference на Mac не запускався.
- WP1: DA3 adapter, frozen manifest, C3 prediction NPZ, C4 depth evaluation/timing та run.json; Назар повідомив clean GPU 1/20-frame runs із commit `721909f`, деталі у PROJECT_STATUS. Це evidence автора, не повторний GPU benchmark integration session.
- WP2: реальний 200-frame RGB-only run, sparse geometry + keyframe poses/calibration + pixel links; 1,205 landmarks / 19 keyframes / 7,595 observations. Звіт: `results/summaries/wp2_sparse_fr1_xyz_200_20261023.json`.
- README/status merge conflicts вирішено зі збереженням evidence обох авторів. Усі generated runs, weights, environments та external checkout лишаються поза Git. Старі finished run.json не редагувалися.

## Що ще лишається

| Owner | Залишок |
|---|---|
| Ярополк | Normalized all-frame trajectory/tracking states/timing; automatic timestamp-associated ATE/RPE із numeric reports; ширший baseline/performance benchmark. Наявні manual Sim(3) diagnostics не замінюють evaluator. |
| Назар | DA3 predictions на matching SLAM frames/keyframes (нинішній доказ — лише 20 frames, SLAM — 200); ширша selection/evaluation перевірка, resource profiling та integration support. CUDA/checkpoint потрібні на його машині. |
| Юліан | Код scale/Sim(3), correspondences, diagnostics, metric fusion/PLY та artifact runner реалізовано й перевірено synthetic tests. Потрібні full real source runs для реального alignment/residual plot/fused cloud, потім WP5 ablations. |
| Команда | Єдина end-to-end команда/config; B0/B1/P1 на однаковому frozen split; accuracy/latency/memory report; review, demo та presentation. |

## Handoff Юліану

1. Отримати актуальний `main` із WP1/WP2 (PR #6) та WP3/WP4 implementation без перезапису власних змін.
2. Прочитати `docs/WP2_SPARSE_EXPORT.md` та `docs/ARCHITECTURE.md`.
3. Отримати **повну** папку `results/runs/yaropolk_b0_fr1_xyz_200_sparse_20261023_03/` від Ярополка або відтворити новий run. Git містить summaries/previews, але **не** NPZ/CSV/PLY цього run. Повний run дає manifest/config provenance, а папка `sparse/` — handoff artifacts.
4. Використовувати `keyframes.npz::T_wc` із того самого snapshot, що й landmarks. Не підставляти раніший `trajectory_final.txt`. Coordinates поки що в SLAM units, не метрах.
5. Отримати matching DA3 `GeometryPrediction` NPZ від Назара. Поточні 19 SLAM keyframes мають frame IDs `0,3,4,7,9,11,14,17,20,77,80,84,170,178,182,186,190,194,199`; 20-frame DA3 run не покриває їх усі.
6. Join через `frame_id` / timestamps та `point_id`, врахувати DA3 resize/crop, integer pixel centres і raw distorted vs undistorted pixel grids. GT дозволений лише для evaluation або явно позначеного oracle.

Назар може отримати повне smoke покриття через існуючий CUDA runner з **новим унікальним run ID**, наприклад:

```powershell
.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 200 --warmup 1 --run-id nazar_da3metric_f1_200_for_wp3_unique
```

Команду наведено як наступну роботу на CUDA machine; під час Git integration вона не виконувалася.

Preview: `results/plots/wp2_sparse_map.png`. PLY містить sparse XYZ без RGB/mesh; завершену dense metric map має створити alignment/fusion, не baseline exporter.
