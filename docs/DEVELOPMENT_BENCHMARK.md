# N-05: development + selection benchmark

Назар, 25 жовтня 2026. Chunk N-05 з `docs/EXPERIMENTS.md`. B0 метрики — evaluator Ярополка (`scripts/evaluate_wp2_run.py`, Y-02/Y-03), split support — Y-04 (PR #19); alignment/fusion/comparison і missing-GT policy — Юліан (PR #7/#8/#21). Усе використано без змін.

**Статус: виконано.** Development rows для всіх обов'язкових methods/ablations є; selection rows — **disclosed failure** GT evaluation (§6). Derived freeze обчислено механічно (§7). Held-out не відкривався.

## 1. Base, commits, sync

| Item | Значення |
|---|---|
| Branch | `feature/nazar-n05-n06` (base `origin/develop` `71a703a`) |
| Grid (до runs) | `d0ca0f1` — pre-registered comparison configs |
| Model-only evidence | clean `0dc5f7f` (містить PR #21) |
| Y-04 sync | `6f24423` = merge `origin/develop` `422172a` (PR #19) |
| DA3 pipeline configs | `cd64251` (runs з цього clean commit) |
| UniDepth configs + PR #22 sync | `580bba1` (runs з цього clean commit; develop `6440a0d` містить PR #22 = `b8204b2`) |
| Hardware | NVIDIA GeForce RTX 5070 Laptop GPU (8 GiB), driver 610.74, AMD64 CPU, 31.2 GB RAM, Windows 11; B0 у Linux Docker `rt-mapping-wp2:96019cf`, container `rt-mapping-wp2-nazar` |

Runs запускались зі standalone clone того самого branch (container mount, `docs/RESULTS.md`); fr1/desk і fr2/desk скопійовано в ignored `data/raw/` clone, SLAM preflight перевіряє archive/input SHA-256 проти frozen manifests. Model-only runs скопійовано в clone і перевірено побайтово (SHA-256 усіх 576/576/53/53 files збігаються); не перезапускались.

PR #21: tolerance **20 ms не змінено** (`max_timestamp_delta_s` = 0.02 у всіх configs і в evaluator defaults).

## 2. Primary model

DA3METRIC-LARGE `process_res` 504 — primary за механічним D-3 fallback trigger (N-04 gate fail). Рішення не переглядається (див. §5 щодо результату UniDepth). UniDepth V2 ViT-L `resolution_level` 0 — обов'язковий "primary vs fallback" ablation і confidence ablation.

## 3. Pre-registered grid (commit `d0ca0f1`, до будь-якого run)

| Config | `causal_window_frames` | `keyframe_intervals` | confidence thresholds |
|---|---:|---|---|
| `configs/mapping_comparison.nazar.development.json` | 0 (P1-global) | [2, 5] | [−0.6916478276252747, −0.6456854343414307] |
| `…development.window60.json` | 60 | [2, 5] | те саме |
| `…development.window150.json` | 150 | [2, 5] | те саме |

- Keyframe interval {1, 2, 5}: merged `comparison_config` приймає лише intervals > 1; interval 1 = P1-global (усі retained keyframes).
- Confidence thresholds — retain-75%/50% quantiles з dev50 UniDepth predictions (N-04), без GT. DA3: `skipped: model_supplies_no_confidence`.
- τ = {0.02, 0.05, 0.10} m, crop none, alignment/voxel — merged defaults.

Pipeline configs: `configs/pipeline.nazar.{development,selection}.da3.json` (B0 через `configs/wp2_pyslam_{development,selection}.json --all-frames`, geometry `reuse_run` model-only DA3 run) і `…{development,selection}.unidepth.json` (той самий B0 SLAM stage DA3 run — один спільний B0 на split; geometry `reuse_run` model-only UniDepth run). Window variants — `scripts/run_mapping_comparison.py` на тих самих DA3 SLAM + geometry stages.

## 4. B0 development (evaluator Y-02/Y-03, defaults: 20 ms, RPE delta 1, warm-up 1)

`nazar_n05_dev573_b0eval_cd64251_01` на SLAM stage `nazar_n05_dev573_da3_cd64251_01.slam`:

| Metric | Value |
|---|---|
| Tracking success (OK / 573 frozen inputs) | **0.7504** (430/573) |
| States | OK 430, RELOCALIZE 126 (frames 170–293 + ще 2), NOT_INITIALIZED 13 (0–12), LOST 4 |
| Final trajectory Sim(3) ATE RMSE / median | 0.01953 m / 0.01163 m (430 poses) |
| Final trajectory RPE trans / rot | 0.01307 m / 0.714° |
| Gap-aware RPE (425 pairs, 4 gap pairs excluded) | 0.01216 m / 0.644° |
| Retained keyframes Sim(3) ATE | 0.016014 m (71 poses) — **збігається** з comparison `B0_sim3` |
| `Slam.track` warm p50 / p95 | 611.4 ms / 2312.5 ms (572 samples; Python core у Docker) |
| Peak RSS | null — `measure_wp2_resources.py` не підтримує `--config/--all-frames` split runs |

Sim(3) scale — evaluation-only, не metric scale.

## 5. Development results (fr1/desk 573, GT coverage 71/71 retained keyframes, 0 excluded)

Map metrics після спільного SE(3) transform P1-global trajectory; ATE — retained keyframes, SE(3) на P1 metric poses. Повні rows: `results/summaries/nazar_n05_benchmark.{json,csv}`; plot `results/plots/nazar_n05_development_benchmark.png`.

| Method | DA3 504 Chamfer-L1 m | DA3 ATE m | UniDepth Chamfer-L1 m | UniDepth ATE m |
|---|---:|---:|---:|---:|
| B1-oracle (GT depth, labelled) | 0.01661 | 0.0466 | 0.01463 | 0.0168 |
| P1-global (keyframe 1) | 0.10574 | 0.0466 | **0.04467** | 0.0168 |
| P1-keyframes-2 | **0.10567** | 0.0466 | 0.04484 | 0.0168 |
| P1-keyframes-5 | 0.12232 | 0.0466 | 0.05327 | 0.0168 |
| P1-window 60 | 0.10581 | 0.0629 | — | — |
| P1-window 150 | 0.10582 | 0.0629 | — | — |
| P1-confidence retain 75% | skipped (no confidence) | — | 0.04973 | 0.0168 |
| P1-confidence retain 50% | skipped | — | 0.05828 | 0.0168 |
| P1-raw (scale 1) | 0.09895 | 0.2148 | 0.06061 | 0.2148 |
| B0-shared-scale | 0.14349 | 0.0466 | 0.12348 | 0.0168 |

Fusion p95 (CPU, per keyframe, DA3 P1-global) 178.7 ms. Model inference p95: DA3 97.9 ms, UniDepth 86.4 ms (§8).

Висновки (лише dev, один run на config):
- **Найважливіший negative result:** fallback DA3 значно гірший за UniDepth на dev: P1-global Chamfer-L1 0.1057 проти 0.0447 m; scale з DA3 depth дає ATE 0.0466 проти 0.0168 m. Механічний D-3 все одно фіксує DA3 primary (UniDepth не пройшов N-04 gate до pixel-grid fix); рішення не змінюється після результатів. Це обмеження протоколу, не підстава для заміни.
- Keyframe 2 ≈ keyframe 1 (Δ 0.07 mm), keyframe 5 гірший; confidence filtering для UniDepth погіршує Chamfer (менше completeness); P1-window гірший за P1-global за ATE і не кращий за Chamfer.
- P1-raw має нижчий Chamfer DA3, ніж P1-global, але ATE 0.215 m: scale 1 не відновлює metric scale; це ablation, не freezable configuration.

Перевірки: rows перечитано з `evaluation/<method>.json`; B0/B1/P1-raw/P1-global/keyframe rows у window runs ідентичні base run; однаковий GT-eligible frame set (71 IDs) у всіх dev comparisons; B0 Sim(3) ATE comparison = evaluator Ярополка.

## 6. Selection (fr2/desk 50) — disclosed failure

| Run | Status | Причина |
|---|---|---|
| `nazar_n05_sel50_da3_cd64251_01` | failed | SLAM stage ok, geometry reused ok; comparison: `trajectory needs finite strictly ordered timestamp tx ty tz qx qy qz qw` |
| `nazar_n05_sel50_unidepth_580bba1_01` | failed | те саме |
| `nazar_n05_sel50_b0eval_cd64251_01` | rejected before run directory | те саме повідомлення |

Причина: official fr2/desk `groundtruth.txt` має одну пару однакових timestamps (1311868229.576, rows 10858/10859, поза sel50 window; зафіксовано в Y-04 `yaropolk_y04_preflight.json`). Merged `rt_mapping.evaluation.trajectory.read_tum_trajectory` вимагає strictly increasing timestamps для всього файлу. Це не tolerance issue. Виправлення змінює evaluation rule у файлі Юліана → окремий focused `fix/*` PR (D-2); у N-05 не робилось (stop condition "run needs code changes"), без reruns.

GT-free факти з selection: B0 export 50/50 rows — OK 40, NOT_INITIALIZED 10; model-only depth rows (§8) ok. Selection rows не використовуються для вибору (D-4), тому Derived freeze не залежить від цього failure.

Note для Ярополка: SLAM `run.json` field `slam.config` hard-coded як `configs/wp2_pyslam_baseline.json` (`slam/smoke.py:155`); фактичний split config вбудовано в `config.baseline` (manifest/split/frames правильні).

## 7. Derived freeze (D-4, механічно, лише dev rows primary DA3)

Кандидати — P1 configurations, які фіксує IC3 (keyframe interval / window / confidence): P1-global (k1), P1-keyframes-2, P1-keyframes-5, P1-window 60, P1-window 150. P1-raw — scale-mode ablation, на held-out звітується завжди.

1. P1-window 60/150 не кращі за P1-global і за Chamfer (0.10581/0.10582 > 0.10574), і за ATE (0.0629 > 0.0466) → не eligible; **P1-window на held-out не запускається**.
2. Найменший Chamfer-L1: P1-keyframes-2 = 0.105671 m; tie ≤ 1 mm: P1-global 0.105739 m. Simpler rule (більший keyframe interval) → **keyframe interval 2**.
3. Confidence: DA3 без confidence → none.

**Derived freeze:**

| Field | Value |
|---|---|
| Model | `depth-anything/DA3METRIC-LARGE` @ `4010e39f3634a45bc60553321fb49fb760bd594e`, checkpoint SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776`, bfloat16 |
| `process_res` | 504 |
| Keyframe interval (best config) | 2 |
| P1-window | none (`causal_window_frames` 0) |
| Confidence filter | none |
| Alignment / fusion | merged defaults (`configs/offline_mapping.json`: residual 0.10 m, ≥30 inliers, ratio ≥0.5, ≥4 bins, voxel 0.02 m) |
| Map τ / crop | {0.02, 0.05, 0.10} m / none |
| GT association | 20 ms, `exclude_keyframes_without_gt_pose_within_tolerance` |
| B0 | `configs/wp2_pyslam_heldout.json` as merged (D-9) |

Held-out methods: B0, B1, P1-raw, P1-global, P1-keyframes-2 (best config). Точні значення переносяться в `configs/benchmark_frozen.json` в IC3.

## 8. Model-only rows і latency (clean `0dc5f7f`)

| Split | Frames | Model | AbsRel | RMSE m | δ1 | p50 ms | p95 ms | VRAM GiB |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| dev | 573 | DA3 504 | 0.0819 | 0.1626 | 0.9669 | 86.5 | 97.9 | 1.545 |
| dev | 573 | UniDepth | 0.0827 | 0.1374 | 0.9744 | 74.8 | 86.4 | 1.797 |
| selection | 50 | DA3 504 | 0.1145 | 0.4211 | 0.9570 | 79.3 | 86.6 | 1.545 |
| selection | 50 | UniDepth | 0.0646 | 0.4499 | 0.9671 | 73.6 | 74.6 | 1.797 |

Evidence `results/summaries/nazar_n05_model_only_0dc5f7f.{json,csv}`; UniDepth pixel-grid fix перевірено на real mapping stage (`nazar_n05_unidepth_grid_fix_0dc5f7f.json`); sel50 depth bit-identical з N-03.

Real-time: SLAM `track` p95 2312 ms і model p95 86–98 ms вже перевищують 33.3 ms (D-7) → **offline**. End-to-end p95 тут не вимірювався; повний performance table — N-06.

## 9. Run list

| Run ID | Commit | Status |
|---|---|---|
| `nazar_n05_smoke200_geom_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_smoke200_mapcheck_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_{dev573,sel50}_geom_{da3,unidepth}_0dc5f7f_01` (4) | `0dc5f7f` | ok |
| `nazar_n05_dev573_da3_cd64251_01` | `cd64251` | ok |
| `nazar_n05_sel50_da3_cd64251_01` | `cd64251` | failed (selection GT, §6) |
| `nazar_n05_dev573_b0eval_cd64251_01` | `cd64251` | ok |
| `nazar_n05_sel50_b0eval_cd64251_01` | `cd64251` | rejected (no run dir, §6) |
| `nazar_n05_dev573_unidepth_580bba1_01` | `580bba1` | ok |
| `nazar_n05_sel50_unidepth_580bba1_01` | `580bba1` | failed (selection GT, §6) |
| `nazar_n05_dev573_da3_window{60,150}_580bba1_01` | `580bba1` | ok |

Усі `dirty_worktree=false`. Reruns: жодних. Raw runs ignored; committed лише summaries/plot. Held-out fr3 не відкривався. Ablations ICP/P2/sweeps не запускались.
