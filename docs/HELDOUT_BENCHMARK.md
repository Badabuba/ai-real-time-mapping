# N-06: held-out benchmark (fr3/long_office_household)

Назар (бос), 25 жовтня 2026. Chunk N-06 з `docs/TWO_PERSON_COMPLETION_PLAN.md`; frozen protocol — `docs/BENCHMARK_PROTOCOL.md`, `configs/benchmark_frozen.json`.

**Статус (оновлено 26 жовтня): disclosed failure, partial evidence.** Перший run (`e561d8c_01`) зупинився на WP2 preflight (§1–§6, текст збережено). Дозволений D-5 rerun `nazar_n06_heldout2488_da3_48ddd4c_01` після fix Ярополка (§7) пройшов SLAM, DA3 і P1-global alignment/fusion, але comparison упав з **новою** причиною: P1-raw ablation перевищив frozen `max_voxels` (§8). Depth, trajectory (B0, P1-global) і performance є. Map metrics B0/B1/P1 відсутні. Нового rerun немає, нічого не tuned.

## 1. Freeze до доступу

| Item | Значення |
|---|---|
| Freeze | `configs/benchmark_frozen.json`, commit `4021a02`, merged PR #25 → `develop` `847c662` |
| N-05 | PR #24, merge `ef5e682` |
| N-06 branch | `feature/nazar-heldout-benchmark` з `847c662` |
| Config | `configs/pipeline.nazar.heldout.json` = `benchmark_frozen.json` → `heldout.pipeline_config` (scripted diff 0 рядків; `tests/test_benchmark_frozen.py`) |
| Run commit | clean `e561d8c` (містить freeze) |
| Перший доступ до fr3 | копіювання fr3 у runtime clone після merge `847c662` |

## 2. Run

| Run ID | Commit | Status | Причина |
|---|---|---|---|
| `nazar_n06_heldout2488_da3_e561d8c_01` | `e561d8c` | **failed** | `pipeline_failed: slam adapter exited 2`; `logs/slam.log`: `Rejected: groundtruth time range does not cover associated RGB frames` |

Запущено один раз (start 2026-10-25T19:32:36Z, failure через ~387 s, з них preflight hashing). SLAM frames 0, DA3 inference 0, alignment/fusion/comparison не виконувались, B0 evaluation неможлива (немає SLAM stage). Evidence: `results/summaries/nazar_n06_heldout2488_e561d8c.json`.

## 3. Діагностика

- Check: `src/rt_mapping/slam/setup.py:155` (Track Y; рядок з `24b16e2`, збережений Y-04) вимагає, щоб GT time range покривав усі associated RGB frames.
- Official fr3 `groundtruth.txt` починається о 1341847980.79 s, перший RGB frame — 1341847980.722988 s: 3 з 2488 frames раніше за GT (після кінця — 0). Лише 2 frames не мають GT pose у межах 20 ms.
- B0 SLAM не використовує GT; merged policy PR #21 уже виключає keyframes без GT pose і записує coverage. Тому preflight відкидає валідний official recording ширше, ніж потрібно для evaluation. Це **гіпотеза щодо правильного fix**, не змінений код.
- Y-04 held-out real-data preflight був explicitly skipped (input недоступний на машині Ярополка), тому до IC3 це не виявилось.
- Fix належить Track Y (`slam/`); Track N не редагує SLAM code (plan §3). Тут нічого не змінено.

GT access: preflight прочитав GT timestamps; діагностика порівняла лише timestamps GT/RGB. Жодна GT pose/depth не використана для metric.

## 4. Performance і real-time verdict

Held-out performance table недоступна: жоден stage не виконався. Verdict за D-7: **offline**. Підстава — N-05 dev components уже перевищують 33.3 ms budget (`Slam.track` warm p95 2312 ms; DA3 504 p95 97.9 ms на RTX 5070 Laptop, 640×480 input, 30 Hz), а pipeline послідовний. Held-out p95/FPS не заявляються.

## 5. Наступний крок (D-5)

1. Ярополк: focused fix PR у `slam/setup.py` (наприклад, дозволити часткове GT coverage з явним звітом, як для duplicate timestamps у `7492ffa`), з regression test; held-out preflight на реальних даних.
2. Після merge: новий branch від `develop`, той самий frozen config (scripted diff порожній), новий run ID `nazar_n06_heldout2488_da3_<sha7>_01` з commit, що містить fix; B0 evaluation `nazar_n06_heldout2488_b0eval_<sha7>_01`; performance table. Обидва runs звітуються. Параметри не змінюються.

## 6. Disclosures

- Цей run: failed на preflight (вище).
- Superseded runner `wp2_heldout2488_4484fd7` (clean `4484fd7`) failed в upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`); без trajectory і metrics; нічого не tuned.
- Held-out результати нічого не вибирали і не змінювали. F-N1/F-N2 не розпочато.

## 7. D-5 rerun authorization (записано до запуску)

- **Bug fix власника коду:** Ярополк, PR #27 (`bd0a17e`, merge `c08833f`) і PR #29 (`78ecfe5`, merge `242c0cb`). `slam/setup.py` більше не вимагає повного покриття RGB time range GT: усі frozen RGB inputs лишаються в SLAM, coverage у межах 20 ms звітується явно (matched/unmatched, excluded frame IDs, reasons). Нуль GT overlap і далі дає failure (`NoGroundTruthOverlap`). Tolerance зафіксовано на 0.02 s (`GT_MATCH_TOLERANCE_S`). CI 4/4 green в обох PR.
- **Аудит Nazar:** diff `e561d8c..242c0cb` у `src/`, `scripts/`, `configs/`, `containers/` зачіпає лише `slam/setup.py`, `evaluation/trajectory.py` (coverage helper), `evaluation/slam_run.py` і два WP2 CLI (звіт coverage, 20 ms enforced). Geometry, alignment, fusion і comparison code не змінено.
- **Frozen protocol без змін:** SHA-256 `configs/benchmark_frozen.json` `bf990a4a…213407` = freeze `4021a02`. `configs/pipeline.nazar.heldout.json` `9cf9a0d7…0b97` = версія run `e561d8c`. `wp2_pyslam_heldout.json` `3545878e…71eb`, `offline_mapping.json` `93c0c363…f9fb`, `mapping_comparison.json` `06c4d5f5…e3aa2`, held-out manifest `42b1149d…0ee3`. Checkpoint `bbea5b0b…324776`, Docker image `sha256:f975805a…f5f6`, fr3 archive `c7cd8e1a…e9c`, `groundtruth.txt` `e255d5d9…533f` (= archive member і Y-06).
- **Rerun:** один запуск з commit цього branch, новий run ID `nazar_n06_heldout2488_da3_<sha7>_01`; failed run `nazar_n06_heldout2488_da3_e561d8c_01` не змінюється. Модель, `process_res`, keyframe interval, window, confidence, thresholds і tolerance не змінюються. Held-out результат нічого не вибирає.

## 8. D-5 rerun: результат

| Item | Значення |
|---|---|
| Run ID | `nazar_n06_heldout2488_da3_48ddd4c_01` (новий; `e561d8c_01` не змінено, SHA-256 `run.json` той самий) |
| B0 evaluation | `nazar_n06_heldout2488_b0eval_48ddd4c_01` (frozen evaluator defaults + `--plot`), status `ok` |
| Commit | clean `48ddd4c` (містить freeze `4021a02`, fix `242c0cb` і §7), `dirty_worktree` false у всіх stages |
| Запуск | один раз, 2026-10-25T20:54:31Z, standalone runtime clone на `48ddd4c` |
| Status | **failed**: `comparison_failed: fusion_failed: map_capacity_exceeded: voxel limit exceeded; increase size/limit explicitly` |

### 8.1 Stages

| Stage | Status | Elapsed |
|---|---|---|
| SLAM preflight + SLAM (Docker, pySLAM `96019cf`) | ok | 5316 s |
| Geometry (DA3METRIC-LARGE @504, 2488 frames) | ok | 620 s |
| comparison.global (P1-global alignment + fusion) | ok | ~34 s alignment/input + fusion 282 keyframes |
| comparison.raw (P1-raw ablation, scale 1) | **failed**: `map_capacity_exceeded` | — |
| comparison.k2 (P1-keyframes-2), oracle (B1), map evaluation | не запускались | — |

### 8.2 Діагностика failure

- Check: `src/rt_mapping/fusion/voxel.py:66` (WP4, Юліан). Ліміт `max_voxels` 2,000,000 при voxel 0.02 m з `configs/offline_mapping.json` (frozen, SHA-256 у `benchmark_frozen.json`).
- P1-global map уже має 1,818,552 voxels (282 keyframes, 13.4 M input points). Recovered scale 2.193. P1-raw лишає pose scale 1, тому metric depth fuse'иться на в ~2.2 раза коротших translations, і поверхні різних keyframes не перекриваються. Це **гіпотеза**: кількість voxels P1-raw у момент failure не записана.
- Comparison обриває всі rows, коли падає один child. Тому немає map metrics навіть для P1-global, B0-shared-scale і B1.
- Обхід потребує або збільшити frozen `max_voxels` (заборонено D-5: параметри не змінюються), або змінити WP4 code (робота власника). Тому rerun не виконувався. За протоколом цей failure — фінальне evidence.

### 8.3 GT coverage (tolerance 0.02 s без змін)

| Scope | Coverage | Excluded |
|---|---|---|
| Усі frozen RGB inputs (preflight, B0 evaluator) | 2486/2488 (99.92%) | frame 0 (t 1341847980.722988, nearest GT 67.0 ms), frame 1 (t 1341847980.754743, 35.3 ms); `no_gt_pose_within_tolerance` |
| B0 final poses | 2458/2458 | — (frames 0–29 NOT_INITIALIZED, без pose) |
| Retained keyframes (comparison, усі методи) | 282/282 | — |

Усі 2488 RGB frames оброблені SLAM. Exclusion діє лише на GT-dependent metrics.

### 8.4 Depth (DA3, 2488 frames, raw metric, без scale alignment)

AbsRel **0.0788**, RMSE **0.344 m**, MAE 0.177 m, δ1 **0.951**, 637,196,001 evaluated pixels. Незалежний перерахунок середніх по per-frame values збігається.

### 8.5 Trajectory і tracking

| Method / scope | Poses | ATE RMSE m | ATE median m | RPE trans m | RPE rot ° | Alignment |
|---|---:|---:|---:|---:|---:|---|
| B0 final trajectory | 2458 | 0.03713 | 0.02270 | 0.00615 | 0.283 | Sim(3) eval-only (scale 2.268) |
| B0 online causal trajectory | 2458 | 0.03994 | 0.02814 | — | — | Sim(3) eval-only |
| B0 gap-aware RPE | 2457 pairs | — | — | 0.00599 | 0.277 | — |
| B0 retained keyframes | 282 | 0.02882 | 0.01636 | 0.00641 | 0.354 | Sim(3) eval-only |
| **P1-global** retained keyframes | 282 | **0.07289** | 0.05790 | 0.00831 | 0.354 | SE(3), recovered scale 2.193 |

- Tracking success 0.9879 (2458/2488): OK 2458, NOT_INITIALIZED 30 (frames 0–29), LOST/RELOCALIZE 0.
- Незалежний numpy Umeyama Sim(3) на `trajectory_final.txt` дає ту саму ATE 0.037131 m на 2458 poses. Keyframe ATE B0 evaluator і comparison `B0_sim3` збігаються точно.
- P1-global alignment: 47,084 inliers з 76,996 pairs (ratio 0.612).
- Sim(3) ATE не доводить metric scale. P1-global ATE (метрична scale з DA3) у 2.5 раза гірша за B0 Sim(3) keyframe ATE: scale із DA3 depth на held-out має помилку. Це негативний результат, а не підстава щось змінювати.

### 8.6 Performance (RTX 5070 Laptop 8 GiB, Ryzen 9 8940HX, 31.2 GB; 640×480 input, 30 Hz; DA3 process_res 504)

| Component | p50 | p95 | Notes |
|---|---:|---:|---|
| `Slam.track` (Docker, 4 CPU) | 1212 ms | 4578 ms | 2487 warm samples, max 7192 ms |
| DA3 inference | 92.3 ms | 130.3 ms | 2488 frames; torch peak VRAM 1.54 GB; model load 5.0 s |
| Alignment + input loading (P1-global) | 34.0 s total | — | одноразово |
| Fusion per keyframe (P1-global, CPU) | 154.9 ms | 223.6 ms | 282 keyframes |
| Wall clock до failure | 6143 s | — | effective 0.405 FPS (2488 / wall) |

- Sampled кожні 5 s (917 samples): SLAM container peak 3.65 GiB / 10 GiB, мінімум вільної host RAM 1.79 GB.
- **Disclosure:** приблизно з 22:27Z, під час DA3 stage, паралельно працювала гра користувача (`cs2`), що ділила GPU і RAM (загальна GPU memory усіх процесів до 7083 MiB). DA3 p95 130 ms vs 97.9 ms на dev може бути завищений цим (**гіпотеза**).
- **Real-time verdict (D-7): offline.** `Slam.track` p95 4578 ms і DA3 p95 130 ms кожен окремо перевищують budget 33.3 ms. Throughput 0.405 FPS < 30. End-to-end per-frame p95 не вимірювався (послідовний offline pipeline).

### 8.7 Evidence і disclosures

- `results/summaries/nazar_n06_heldout2488_48ddd4c.{json,csv}`: hashes, provenance, coverage, metrics, performance, 14 consistency checks (усі true). Plots: `results/plots/nazar_n06_b0_tracking_states.png`, `nazar_n06_p1_global_residuals.png`, `nazar_n06_p1_global_map.png`.
- Обидва runs звітуються: `e561d8c_01` (preflight failure, §2) і `48ddd4c_01` (comparison failure, тут). Superseded runner `wp2_heldout2488_4484fd7` failed в upstream `local_mapping.py`, без metrics.
- Claude Code під memory pressure зупинив idle background wait loop. Detached pipeline process це не зачепило.
- **Held-out результати нічого не вибирали і не змінювали:** модель, `process_res`, keyframe interval, window, confidence, alignment/fusion config, `max_voxels`, evaluator і tolerance 20 ms без змін. F-N1/F-N2 не розпочато.
