# N-05: development + selection benchmark

Назар (бос), 25 жовтня 2026. Chunk N-05 з `docs/TWO_PERSON_COMPLETION_PLAN.md`.

**Статус: частково виконано (blocked).** Виконано pre-registration grid, UniDepth pixel-grid fix і model-only rows (IC2 fallback плану). B0/P1 rows на dev/selection і "Derived freeze" **заблоковані**: Y-04 (PR #19, `feature/yaropolk-split-support`) ще не merged, тому на `develop` немає `configs/wp2_pyslam_{development,selection}.json` і split-manifest support у `slam/setup.py`. Код з unmerged гілки не використовувався.

## 1. Base і sync

| Item | Значення |
|---|---|
| Base `origin/develop` | `71a703a` (Merge PR #20) |
| Fix commit | `b8204b2` UniDepth pixel grid |
| Grid commit | `d0ca0f1` pre-registered comparison configs |
| Sync | `0dc5f7f` = merge `origin/develop` `9617bc4` (PR #21, Yulian, missing-GT evaluator fix), до будь-якого real run |
| Evidence commit | усі runs нижче з clean `0dc5f7f` (`dirty_worktree=false`) |
| Hardware | NVIDIA GeForce RTX 5070 Laptop GPU (8 GiB), driver 610.74, AMD64 CPU, 31.2 GB RAM, Windows 11, Python 3.11, torch 2.11.0+cu128 |

PR #21: tolerance **20 ms не змінено** (`max_timestamp_delta_s` = 0.02 у merged default і в усіх N-05 configs). Policy `exclude_keyframes_without_gt_pose_within_tolerance`: keyframes без GT pose виключаються з GT evaluation і записуються, без interpolation.

GT coverage check (evaluation-only, нічого не tuned): усі 573 dev frames (fr1/desk) і 50 selection frames (fr2/desk) мають GT pose у межах 20 ms (max Δ 13.1 ms і 1.4 ms). Отже N-02 failure (smoke frames 195–196, Δ 40.8 ms) на dev/selection не очікується; PR #21 для N-05 не є blocker.

## 2. Primary model

DA3METRIC-LARGE, `process_res` 504 — primary для N-05/N-06 за механічним fallback trigger D-3 (N-04 gate fail, `configs/selected_geometry.json` `effective_primary_for_n05_n06 = fallback`). Рішення не переглядається; кращий standalone AbsRel UniDepth на selection не є підставою.

UniDepth V2 ViT-L (`resolution_level` 0) — обов'язковий у N-05 як "primary vs fallback" ablation і єдина модель для confidence ablation (план §5 N-05, D-4).

## 3. Pre-registered grid (до будь-якого N-05 run)

Configs (commit `d0ca0f1`):

| Config | `causal_window_frames` | `keyframe_intervals` | confidence thresholds |
|---|---:|---|---|
| `configs/mapping_comparison.nazar.development.json` | 0 (P1-global) | [2, 5] | [−0.6916478276252747, −0.6456854343414307] |
| `configs/mapping_comparison.nazar.development.window60.json` | 60 | [2, 5] | те саме |
| `configs/mapping_comparison.nazar.development.window150.json` | 150 | [2, 5] | те саме |

- Keyframe interval {1, 2, 5}: merged `comparison_config` приймає лише intervals > 1. Interval 1 = P1-global (усі retained keyframes), тому grid реалізовано як P1-global + children 2 і 5. Нових значень не додано.
- Confidence thresholds — retain-75% і retain-50% quantiles з dev50 UniDepth predictions (N-04, `nazar_n04_confidence_thresholds_5d11ce6.json`), без GT. Для DA3 comparison автоматично пише `skipped: model_supplies_no_confidence`.
- Map thresholds τ = {0.02, 0.05, 0.10} m, crop = none, alignment/voxel — merged defaults.

## 4. UniDepth pixel-grid fix

N-04 run `nazar_n04_e2e_smoke200_unidepth_8378365_01` впав у незміненій alignment перевірці: `unsupported_preprocess: prediction must declare its pixel grid` (run не змінено).

Fix (`b8204b2`, `src/rt_mapping/adapters/unidepth_v2.py`): adapter подає raw RGB без rectification, `infer()` повертає depth на тому самому input grid з input integer-centre K. Тому prediction декларує `pixel_grid = raw_distorted`, `intrinsics_convention = pixel_centers_integer`, `steps = []` (та сама семантика, що в DA3). Validation не послаблено; test перевіряє прийняття і відмову для неправильного K/size.

Відхилення від brief: N-05 забороняє source edits; fix — окремий focused commit у WP1 файлі власника (Назар), відокремлений від N-05 evidence. Його можна винести в окремий PR без змін.

Перевірка на реальному stage (`results/summaries/nazar_n05_unidepth_grid_fix_0dc5f7f.json`):

| Run | Status | Результат |
|---|---|---|
| `nazar_n05_smoke200_geom_unidepth_0dc5f7f_01` | ok | 200 frames fr1/xyz; AbsRel 0.0409, RMSE 0.121 m |
| `nazar_n05_smoke200_mapcheck_unidepth_0dc5f7f_01` | ok | offline mapping (merged `configs/offline_mapping.json`) з reused N-02 SLAM stage: scale 1.3067, 3987/5334 inliers (0.747), coverage 16/16 bins, 18/18 keyframes, 93,131 voxels. GT evaluation не виконувалась |

Depth не змінився: sel50 predictions обох моделей bit-identical з N-03 runs на 50/50 frames (§5).

## 5. Model-only rows (IC2 fallback)

Raw metric depth vs TUM GT depth на raw RGB grid, frame-mean, без scale fitting; GT лише в evaluation. Timing — warm per-frame model inference (CUDA-synchronized, image decode excluded), 10 prewarm calls, seed 0. Evidence: `results/summaries/nazar_n05_model_only_0dc5f7f.{json,csv}`.

| Split | Frames | Model | AbsRel ↓ | RMSE m ↓ | MAE m ↓ | δ1 ↑ | p50 ms | p95 ms | Peak VRAM GiB |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| dev fr1/desk | 573 | DA3 504 (primary) | 0.0819 | 0.1626 | 0.1153 | 0.9669 | 86.5 | 97.9 | 1.545 |
| dev fr1/desk | 573 | UniDepth rl0 | 0.0827 | 0.1374 | 0.0880 | 0.9744 | 74.8 | 86.4 | 1.797 |
| selection fr2/desk | 50 | DA3 504 (primary) | 0.1145 | 0.4211 | 0.2316 | 0.9570 | 79.3 | 86.6 | 1.545 |
| selection fr2/desk | 50 | UniDepth rl0 | 0.0646 | 0.4499 | 0.1409 | 0.9671 | 73.6 | 74.6 | 1.797 |

- На dev573 AbsRel майже однаковий (UniDepth +0.0008), а RMSE/MAE/δ1 кращі в UniDepth. На selection — навпаки за RMSE (як у N-03). Це tradeoff, а не універсальна перевага; selection rows не використовуються для вибору (D-4).
- Перевірки: frame-mean перераховано з per-frame rows (max |Δ| = 0), p50/p95 перераховано з per-frame timings (max |Δ| = 0), sel50 depth/valid masks bit-identical з `nazar_n03_sel50_{da3,unidepth}_c130626_01` (50/50, max |Δ| = 0 m).
- Model p95 (74.6–97.9 ms) перевищує 33.3 ms frame budget; це лише model stage, не end-to-end. Real-time claim немає (D-7).

## 6. Обов'язкові rows і їх статус

| Row (план N-05) | Dev 573 | Selection 50 | Причина |
|---|---|---|---|
| Model-only depth, обидві моделі | ✔ done | ✔ done | §5 |
| B0 (+ `evaluate_wp2_run.py`) | blocked | blocked | Y-04 не merged: немає per-split B0 configs/split support |
| B0-shared-scale, B1 oracle, P1-raw, P1-global (DA3, UniDepth) | blocked | blocked | потребують B0 SLAM stage на split |
| P1-window 60/150 | blocked | — (optional) | те саме; configs pre-registered |
| Keyframe interval 1/2/5 | blocked | — | те саме; configs pre-registered |
| Confidence 75/50% (UniDepth) | blocked | blocked | те саме; DA3 skipped (no confidence) |
| Derived freeze | pending | — | потребує dev P1 Chamfer-L1/ATE |

Жодних failed runs у N-05 немає. Жодного held-out access.

## 7. Derived freeze

**Ще не обчислено.** Правило D-4 (механічне, лише з dev rows primary моделі): найменший dev Chamfer-L1 серед P1 variants DA3; tie ≤ 1 mm → простіша конфігурація (global > window, більший keyframe interval, без confidence filter); P1-window лише якщо краще за P1-global і за dev Chamfer-L1, і за dev SE(3) ATE. Значення буде записано тут після dev P1 runs.

## 8. Що залишилось після merge Y-04

1. Merge `origin/develop` (без запущених experiments), targeted tests.
2. Configs `configs/pipeline.nazar.{development,selection}.{da3,unidepth}.json`: SLAM через `configs/wp2_pyslam_{development,selection}.json`; geometry — `reuse_run` model-only runs з §5 (ті самі frames/checksum); comparison — §3 configs.
3. Runs `nazar_n05_{dev573,sel50}_{da3,unidepth}_<sha7>_01` + window60/150 variants; `scripts/evaluate_wp2_run.py` на кожному SLAM stage.
4. Aggregation `results/summaries/nazar_n05_benchmark.{json,csv}`, plots, Derived freeze.

Runtime note: Docker SLAM потребує fr1/desk і fr2/desk усередині repo checkout (WP2 preflight відхиляє `data/raw` поза repo root; див. `docs/NAZAR_REPRODUCTION.md`).

## 9. N-06

**Не розпочато.** Prerequisite IC3 (`configs/benchmark_frozen.json` merged) відсутній; IC3 потребує merged N-05 з Derived freeze. За D-5 до merge freeze held-out fr3 не відкривався (жодного читання fr3 RGB/depth/GT, inference чи metrics). Disclosure `wp2_heldout2488_4484fd7` (superseded runner, failed, no metrics) залишається в силі.

## 10. Run list

| Run ID | Commit | Status |
|---|---|---|
| `nazar_n05_smoke200_geom_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_smoke200_mapcheck_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_dev573_geom_da3_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_dev573_geom_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_sel50_geom_da3_0dc5f7f_01` | `0dc5f7f` | ok |
| `nazar_n05_sel50_geom_unidepth_0dc5f7f_01` | `0dc5f7f` | ok |

Raw runs ignored (`results/runs/`), committed лише summaries. Reruns: жодних.
