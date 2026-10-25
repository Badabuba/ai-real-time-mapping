# Передреєстрований WP1 spike — 23 жовтня 2026

Назар (бос). Цей protocol/scorecard code фіксується commit-ом до запуску порівняльних GPU experiments.

- Незмінні exact 50 prefix frames: `tum_fr1_desk_spike50.json` (development) і окремо `tum_fr2_desk_selection50.json` (selection confirmation). Dataset split identities не змінюються після результатів.
- Кожен кандидат: raw 640×480 RGB, batch 1, known calibrated K, seed 0, 10 окремих warm-up calls, потім усі 50 frames. DA3: process_res=504, native output 504×378; UniDepth: native resolution_level=0, internal близько 574×434, output 640×480. Це documented native modes, не однаковий internal compute; float16/bfloat16 визначені офіційними APIs.
- Збережені prediction NPZ лишаються на native grid без GT. Evaluation-only DA3 depth bilinear align_corners=False → raw 640×480; UniDepth output уже raw. GT не resample-иться. Той самий finite positive GT mask для обох; SHA-256 кожної mask пишеться в metrics.json.
- Mean metrics — C4 frame_mean (AbsRel/RMSE/MAE/δ1/coverage), без median scaling чи GT correction. `run.json` містить manifest hash, commit, dirty_worktree і config; source runs immutable.
- Score weights із MODEL_SELECTION §5: quality 35%, runtime 25%, memory 15%, integration 15%, license/reproducibility 10%.
- Scores 0–5: quality=2.5*(bestAbsRel/AbsRel + δ1/bestδ1); runtime=5*bestp95/p95; memory=5*bestVRAM/VRAM. Integration=4.5 для обох: DA3 без confidence, UniDepth потребує optional environment. License: Apache-2.0 DA3=5; UniDepth non-commercial code і без окремої license у checkpoint card=3. Це engineering utility rubric, не загальний scientific ranking.
- Hard gates: checkpoint hashes + pinned sources; successful clean commit runs; 50/50 finite positive output; full common evaluated masks; allocated VRAM <7.5 GiB на 8 GiB GPU. Наявність reference confidence не є hard gate.
- Переможець — maximum weighted score на selection confirmation. Development spike пояснює trade-off; held-out не використовується.

CLI після local integration C5/C6 + manifests:

```powershell
.venv/Scripts/python.exe scripts/run_geometry_benchmark.py --model da3 --manifest data/manifests/tum_fr1_desk_spike50.json --split development --frames 50 --prewarm 10 --run-id <new-id>
.venv/unidepth/Scripts/python.exe scripts/run_geometry_benchmark.py --model unidepth --manifest data/manifests/tum_fr1_desk_spike50.json --split development --frames 50 --prewarm 10 --run-id <new-id>
.venv/Scripts/python.exe scripts/compare_geometry_models.py results/runs/<da3-id> results/runs/<unidepth-id> --output results/summaries/<new-summary>.json
```

Для selection використати `tum_fr2_desk_selection50.json --split selection`. `--assets-root` дозволяє повторно використати локальні дані іншого checkout; абсолютний path не потрапляє у run.json. Повторний run або summary ніколи не перезаписує наявний.

Поточна integration branch базується на `develop@ce095fa`: C5 PR #4 та WP2 PR #5 вже merged. Generic runner і WP2 implementation збережені. Нові source commits/runs залишаються локальними до зовнішнього review.

З 24 жовтня scorecard перевіряє saved prediction contracts, per-frame identities, deterministic aggregation та timing recomputation; confidence availability читається з NPZ, не припускається з назви моделі. `verify_geometry_run.py --assets-root .` окремо повторно обчислює всі metrics/masks із GT. Scorecard додає output grids, intrinsics semantics та чесне обмеження repeatability: один run не доводить cross-run стабільність. UniDepth error зберігається як `-official_error`, DA3 confidence=None.
