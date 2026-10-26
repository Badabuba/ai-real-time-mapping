# Протокол експериментів

Мета протоколу — не дозволити команді ненавмисно покращити proposed method за рахунок іншого датасету, hardware, preprocessing або alignment з ground truth.

## 1. Гіпотези

- **H1:** predicted metric depth + SLAM poses дає повнішу карту, ніж sparse SLAM, зі збереженням прийнятної геометричної точності.
- **H2:** robust scale estimation на sparse observations зменшує metric depth/map error порівняно з використанням сирого scale моделі.
- **H3:** confidence filtering зменшує outliers та покращує F-score/Chamfer, хоча знижує completeness.
- **H4:** keyframe inference дає кращий accuracy–latency trade-off, ніж inference на кожному кадрі.

Для кожної гіпотези у фінальному звіті потрібні: метод порівняння, метрика, таблиця/графік, висновок і limitation.

## 2. Dataset protocol

Primary dataset: TUM RGB-D. Pipeline отримує лише monocular RGB та відомі camera intrinsics. Ground-truth depth/trajectory читає тільки evaluation code або явно позначений oracle B1.

Запропонований freeze (команда має підтвердити після download):

| Split | Sequence | Призначення |
|---|---|---|
| smoke | freiburg1_xyz, перші 200 асоційованих RGB-depth кадрів (data/manifests/tum_fr1_xyz.json) | setup, shapes, timestamps, швидкий CI-like run |
| development | freiburg1_desk | налагодження alignment/fusion і thresholds |
| selection | freiburg2_desk | вибір dense model/config; не для фінального headline |
| held-out evaluation | freiburg3_long_office_household | основний звіт після freeze |

Перед запуском перевірити точні офіційні IDs, availability і розмір. Якщо sequence замінено, записати причину в PROJECT_STATUS та не перераховувати старі результати як напряму порівнювані.

Другий dataset (KITTI Odometry) — stretch goal для outdoor generalization. Він не має затримувати TUM MVP.

## 3. Methods

| ID | Метод | Дозволене використання ground truth |
|---|---|---|
| B0 | pySLAM monocular, sparse map | evaluation only |
| B1 | pySLAM poses + TUM depth fusion | depth як oracle input; чітко позначити upper/control |
| P1-raw | pySLAM poses + raw predicted metric depth | evaluation only |
| P1-global | P1 + один robust scale із development/calibration window | scale estimation лише зі sparse/dense correspondences |
| P1-window | P1 + causal sliding-window scale | тільки минулі/поточні correspondences |
| P2 | DUSt3R або VGGT geometry | evaluation only; optional |

Ground-truth trajectory/depth не можна використовувати для tuning alignment P1 на held-out evaluation.

## 4. Метрики

### 4.1 Trajectory

- **ATE RMSE [m]:** absolute trajectory error після timestamp association.
- **RPE translation [m або %] і rotation [deg]:** локальний drift на фіксованому delta.
- **Tracking success [%]:** кадри зі станом OK / усі RGB frames.

Для B0/P1 звітувати:

1. Sim(3)-aligned ATE — pose shape незалежно від невідомого monocular scale;
2. SE(3)-aligned або no-scale ATE після нашого metric scale recovery — головна metric claim.

### 4.2 Per-frame depth

На спільній valid mask, після офіційного depth scaling TUM:

- AbsRel = mean(|d_pred - d_gt| / d_gt);
- RMSE [m];
- δ1 = fraction(max(d_pred/d_gt, d_gt/d_pred) < 1.25);
- valid coverage [%].

Raw metric depth оцінюємо без median scaling. Окремий scale-aligned score дозволений тільки як diagnostic і має так називатися.

Реалізація: `rt_mapping.evaluation.depth` (C4). GT-valid = finite і > 0; evaluated = GT-valid ∩ `prediction.valid_mask`; також MAE [m]; valid coverage = evaluated / GT-valid; кадр без evaluated pixels — помилка. Середнє по кадрах — незважене (`frame_mean`). GT до сітки prediction зводиться лише nearest-neighbour з цілими центрами pixels: x_src = ⌊(x' + 0.5)·W/W'⌋ (так само для рядків); на 20 кадрах fr1/xyz це побітово збігається з Pillow NEAREST, який використовував runner.

Timing (§4.4) — `rt_mapping.evaluation.timing`: окремо cold start (перший sample), warm-up samples виключені з mean/median/p95; p95 = `numpy.percentile(..., method="linear")`; FPS із per-stage latency не виводиться.

### 4.3 Map geometry

Після voxel downsample обох clouds до однакового voxel size:

- accuracy: mean/median distance estimate → reference;
- completeness: mean/median distance reference → estimate;
- symmetric Chamfer-L1;
- F-score на зафіксованих τ, наприклад 2 cm, 5 cm і 10 cm для indoor scenes;
- point count/coverage після filtering.

Порогові τ і crop volume фіксуємо до held-out run. Якщо повної ground-truth mesh/cloud немає, будуємо reference із TUM depth + ground-truth poses і чесно описуємо preprocessing.

### 4.4 Performance

- cold-start time;
- median та p95 latency окремо для SLAM, model, alignment, fusion і end-to-end;
- effective FPS = processed frames / wall-clock time;
- peak GPU VRAM, peak process RAM;
- input resolution, dtype, batch, keyframe interval, hardware.

Номінальне FPS = 1000 / mean latency недостатнє для async pipeline; додатково вимірюємо wall clock та backlog/lag.

## 5. Reproducibility record

Кожен run створює results/runs/<run_id>/run.json:

```json
{
  "schema": "rt_mapping.run_manifest/v1",
  "run_id": "2026-10-XX_tum_f1desk_p1_global_seed0",
  "git_commit": "<40 hex>",
  "dirty_worktree": false,
  "dataset": {"name": "TUM-RGBD", "sequence": "rgbd_dataset_freiburg1_desk", "split": "development",
              "checksum": "<64 lowercase hex, як archive_sha256 у data manifest>", "manifest": "data/manifests/<...>.json"},
  "method": "P1-global",
  "model": {"repo": "TODO", "revision": "TODO", "checkpoint": "TODO", "dtype": "float32"},
  "slam": {"repo": "TODO", "revision": "TODO", "config": "TODO", "pose_convention": "T_wc"},
  "alignment": {"method": "TODO", "thresholds": {}},
  "config": {"process_res": 384, "batch": 1, "keyframe_interval": 1},
  "hardware": {"gpu": "TODO", "cpu": "TODO", "ram_gb": null},
  "environment": {"python": "3.11.16"},
  "seed": 0,
  "started_at": "2026-10-XXT10:00:00Z",
  "status": "planned",
  "reason": null,
  "artifacts": {"metrics": "metrics.json"}
}
```

Контракт і валідація: `rt_mapping.contracts.run_manifest` (C4). Усі ключі обов'язкові, невідомі ключі відхиляються. `method` ∈ B0, B1, P1-raw, P1-global, P1-window, P2, model-spike; `split` ∈ smoke, development, selection, held-out; `status` ∈ planned, running, ok, degraded, failed, skipped. `model` = null лише для B0/B1; `slam` обов'язковий для B0/B1/P1-*, null для model-spike; `alignment` обов'язковий для P1-global/P1-window/P2, інакше null; `reason` обов'язковий для degraded/failed/skipped. Заборонені NaN/Inf, absolute paths і ключі на кшталт password/token/api_key.

Не редагувати finished run.json заднім числом; нова конфігурація = новий run_id. `write_run_manifest` відмовляється перезаписувати run.json зі статусом ok/degraded/failed/skipped.

### 5.1 Depth-only geometry run (C5)

`scripts/run_tum_da3_metric.py` → `rt_mapping.runs.geometry_run`. `method = model-spike` (model обов'язковий, slam/alignment = null). Порядок: preflight без запису (run dir уже існує → відмова, exit 2) → run.json `running` → перевірка датасету проти C2 manifest (SHA-256 rgb.txt/depth.txt, associations, кадри split; archive SHA-256, якщо не `--skip-archive-hash`) → модель завантажується один раз → для кожного кадру predict → NPZ → GT лише для evaluation → run.json `ok` або `failed` із reason (exit 1).

```text
results/runs/<run_id>/
├── run.json
├── predictions/frame_000000.npz   # C3 NPZ: depth_m, valid_mask, K_processed, meta.json; без GT і без confidence, якщо модель її не дає
├── metrics.json                   # протокол, per-frame DepthMetrics, frame_mean
└── timing.json                    # model_inference TimingSummary, per-frame ms, model_load_s, peak_vram_gb, finished_at, wall_clock_s
```

`inference_ms` = один виклик DA3 `inference()` (preprocess + forward + postprocess) з CUDA synchronize; декодування PNG — поза таймером. Усі кадри оцінюються; `--warmup N` лише виключає перші N samples зі warm statistics. run.json не має поля finished_at, тому воно в timing.json. `model.checkpoint` = `<файл ваг>@sha256:<hash>` з локального HF cache; downloads вимкнені.

## 6. Мінімальна матриця

| Experiment | Smoke | Dev | Selection | Held-out | Owner |
|---|---:|---:|---:|---:|---|
| B0 pySLAM | required | required | required | required | Ярополк |
| B1 oracle depth fusion | optional | required | optional | required | Ярополк + Юліан |
| model spike (2 candidates) | required | — | required | — | Назар |
| P1-raw | required | required | required | required | Назар + Юліан |
| P1-global | required | required | required | required | Юліан |
| P1-window | — | required | optional | required if dev improves | Юліан |
| confidence ablation | — | required | required | best config only | Назар + Юліан |
| keyframe interval ablation | — | required | — | best config only | Назар + Ярополк |
| P2 geometry | optional | optional | optional | optional | Назар |

Спочатку один seed/end-to-end run. Повтори додаємо після усунення deterministic bugs. Для stochastic component бажано 3 seeds із mean ± std.

## 7. Acceptance thresholds

Це engineering gates, не обіцянка scientific success:

- alignment: >=30 inliers, positive finite scale, inlier ratio >=0.5, spatial coverage не в одному малому image region;
- data contract: 100% frames мають timestamp та K; shape/intrinsics tests проходять;
- pipeline: smoke sequence завершується без manual intervention;
- reporting: жоден headline metric без sequence, units, alignment mode і hardware;
- real-time claim: робиться лише якщо p95 end-to-end latency вкладається у визначений frame budget без необмеженого backlog.

Якщо quality не покращується, це не технічний failure: зберігаємо negative result, робимо ablation і пояснюємо межі гіпотези.

## 8. Frozen held-out protocol (IC3, 25 жовтня 2026)

Held-out протокол заморожено до будь-якого доступу до fr3: `configs/benchmark_frozen.json` і `docs/EXPERIMENTS.md`. Значення механічно виведені за plan D-4 лише з development rows primary моделі (`docs/DEVELOPMENT_BENCHMARK.md` §7): DA3METRIC-LARGE `process_res` 504, keyframe interval 2, без P1-window, без confidence filter, merged alignment/fusion defaults, τ = {2, 5, 10} cm, crop none, GT association 20 ms з explicit exclusion policy, B0 `configs/wp2_pyslam_heldout.json`. Held-out runs мають `git_commit`, що містить freeze commit; кожна конфігурація запускається один раз.


<a id="protocols"></a>

## Консолідовані протоколи

Нижче збережено source protocols. Значення frozen JSON, manifests, model weights та run evidence не змінено. Дати та commits позначають preregistration, не поточні execution permissions. Повторний held-out run потребує окремого дозволу та дотримання D-5; cleanup нічого не запускає.


## Frozen datasets і calibration identity

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/DATASET_FREEZE.md). Історичні run IDs та результати збережено.

### Splits

Вибір split остаточний для поточної версії (план, рішення D-1). Зміна потребує нової ревізії плану. Перелік sequence із proposal (`EXPERIMENTS.md §2`) не змінено.

| Manifest | Роль | `splits` key | Кадри | Archive bytes | SHA-256 archive |
|---|---|---|---:|---:|---|
| tum_fr1_xyz.json | smoke | `smoke` | 200 із 792 associations | 448204271 | a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98 |
| tum_fr1_desk_development.json | development | `development` | усі 573 | 344011403 | e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c |
| tum_fr1_desk_spike50.json | development spike | `development` | перші 50 із 573 | 344011403 | e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c |
| tum_fr2_desk_selection50.json | selection | `selection` | перші 50 із 2893 | 1893351095 | 1a0756d72510a26e26e2a02bf0b6c69c2796619fca531e176fc2e5110173807c |
| tum_fr3_long_office_heldout.json | held-out | `held-out` | усі 2488 | 1483556251 | c7cd8e1afb87c80e5744a356214819b110fa09b4744fa4ba0cc2382f9ba59e9c |

Spike50 — це exact prefix (frame_id 0..49) development manifest; роль "spike" задана назвою файла і цією таблицею, а `splits` key лишається `development`.

`tum_fr3_long_office_heldout.json` має ~1.09 MB (1089987 bytes): це лише manifest з timestamps, repo-relative paths і SHA-256 файлів, не дані. Raw TUM дані, як і раніше, лежать тільки в ignored `data/raw/`.

Архіви отримано з офіційних TUM links: https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download . Source URL записаний у кожному manifest. Нові manifests додатково містять SHA-256 кожного вибраного RGB/depth файла та `rgb.txt`/`depth.txt`; timestamps та association rule походять із C1 loader (20 ms, greedy one-to-one). Усі paths — repo-relative POSIX; абсолютних або user-specific paths немає.

`docs/EXPERIMENTS.md §6` вимагає 50 development кадрів, тоді як `EXPERIMENTS.md §2` виділяє окрему selection sequence. Зберігаємо обидві вимоги: спочатку 50-frame spike на fr1/desk, потім підтвердження вибору на тих самих exact 50 fr2/desk кадрах для обох моделей.

### Held-out

Held-out лише заморожено: freezing читає тільки bytes файлів для SHA-256. До merge protocol freeze (IC3) на fr3 не запускається depth/map inference, P1 і не рахуються GT-based metrics; held-out ніколи не використовується для tuning або вибору (план, D-5).

Disclosure: run `wp2_heldout2488_4484fd7` (superseded альтернативний pySLAM v2.2.1 runner Назара, clean commit `4484fd7`; не merged baseline `96019cf`) спробував B0 на fr3 і **failed** всередині upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`). Він не дав trajectory і жодних metrics, і нічого за ним не налаштовувалось. Тому fr3 лишається valid held-out split.


## Model selection rubric

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/SELECTION_PROTOCOL.md). Історичні run IDs та результати збережено.

### Передреєстрований WP1 spike — 23 жовтня 2026

Назар. Цей protocol/scorecard code фіксується commit-ом до запуску порівняльних GPU experiments.

- Незмінні exact 50 prefix frames: `tum_fr1_desk_spike50.json` (development) і окремо `tum_fr2_desk_selection50.json` (selection confirmation). Dataset split identities не змінюються після результатів.
- Кожен кандидат: raw 640×480 RGB, batch 1, known calibrated K, seed 0, 10 окремих warm-up calls, потім усі 50 frames. DA3: process_res=504, native output 504×378; UniDepth: native resolution_level=0, internal близько 574×434, output 640×480. Це documented native modes, не однаковий internal compute; float16/bfloat16 визначені офіційними APIs.
- Збережені prediction NPZ лишаються на native grid без GT. Evaluation-only DA3 depth bilinear align_corners=False → raw 640×480; UniDepth output уже raw. GT не resample-иться. Той самий finite positive GT mask для обох; SHA-256 кожної mask пишеться в metrics.json.
- Mean metrics — C4 frame_mean (AbsRel/RMSE/MAE/δ1/coverage), без median scaling чи GT correction. `run.json` містить manifest hash, commit, dirty_worktree і config; source runs immutable.
- Score weights із MODEL_SELECTION §5: quality 35%, runtime 25%, memory 15%, integration 15%, license/reproducibility 10%.
- Scores 0–5: quality=2.5*(bestAbsRel/AbsRel + δ1/bestδ1); runtime=5*bestp95/p95; memory=5*bestVRAM/VRAM. Integration=4.5 для обох: DA3 без confidence, UniDepth потребує optional environment. License: Apache-2.0 DA3=5; UniDepth non-commercial code і без окремої license у checkpoint card=3. Це engineering utility rubric, не загальний scientific ranking.
- Hard gates: checkpoint hashes + pinned sources; successful clean commit runs; 50/50 finite positive output; full common evaluated masks; allocated VRAM <7.5 GiB на 8 GiB GPU. Наявність reference confidence не є hard gate.
- Переможець — maximum weighted score на selection confirmation. Development spike пояснює trade-off; held-out не використовується.


## Frozen benchmark protocol

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/BENCHMARK_PROTOCOL.md). Історичні run IDs та результати збережено.

### Frozen values

| Field | Value |
|---|---|
| Model | DA3METRIC-LARGE @ `4010e39f…bd594e`, checkpoint SHA-256 `bbea5b0b…324776`, bfloat16, 10 prewarm calls, seed 0 |
| `process_res` | 504 (D-3 fallback trigger; не переглядається) |
| P1 best config | keyframe interval 2; P1-window none; confidence none (DA3 без confidence) |
| Alignment/fusion | `configs/offline_mapping.json` (merged defaults), SHA-256 у JSON |
| Map evaluation | τ = {0.02, 0.05, 0.10} m, crop none, voxel 0.02 m |
| GT association | 20 ms; keyframes без GT pose виключаються і записуються (PR #21) |
| B0 | `configs/wp2_pyslam_heldout.json` (SHA-256 у JSON), pySLAM `96019cf`, Docker `rt-mapping-wp2:96019cf` |
| B0 evaluator | `scripts/evaluate_wp2_run.py` defaults (20 ms, RPE delta 1, warm-up 1) + `--plot` |
| Held-out input | `data/manifests/tum_fr3_long_office_heldout.json`, split `held-out`, 2488 frames |
| Methods | B0, B0-shared-scale, B1-oracle (labelled), P1-raw, P1-global, P1-keyframes-2 |
| Runtime guards | SLAM `--timeout 14400`, pipeline `timeout_s` 14400 (не algorithm parameters) |

### N-06 procedure

1. `configs/pipeline.nazar.heldout.json` = `benchmark_frozen.json` → `heldout.pipeline_config` байт-у-байт за JSON-значенням (test перевіряє рівність; scripted diff має бути порожнім).
2. З clean commit, що містить цей freeze: `scripts/run_pipeline.py --config configs/pipeline.nazar.heldout.json --run-id nazar_n06_heldout2488_da3_<sha7>_01` — **один раз**.
3. `scripts/evaluate_wp2_run.py --source-run <SLAM stage> --groundtruth <fr3>/groundtruth.txt --run-id nazar_n06_heldout2488_b0eval_<sha7>_01 --plot`.
4. Performance: SLAM track p50/p95, model p50/p95, alignment/fusion times, total wall clock, effective FPS = 2488 / wall, peak VRAM, peak RAM де виміряно; verdict за D-7.

### Правила

- Held-out результати нічого не вибирають і не змінюють (model, thresholds, SLAM, keyframes/window/confidence, alignment, evaluator).
- Rerun лише після documented code-bug fix, merged через PR власника, з новим run_id; обидва runs звітуються (D-5).
- Failure або negative result — фінальне evidence.
- Disclosure: superseded runner `wp2_heldout2488_4484fd7` failed (upstream `local_mapping.py`), без trajectory/metrics, нічого не tuned.


## Missing GT pose policy

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/GT_POSE_COVERAGE.md). Історичні run IDs та результати збережено.

### 1. Правило

1. Tolerance асоціації лишається **0.020 s** (`max_timestamp_delta_s` у `configs/mapping_comparison.json`, без змін).
2. Асоціація та сама, що й раніше (`evaluation/trajectory.associate_timestamps`): one-to-one, найближчий timestamp, межа включна (|Δt| ≤ 0.020 s у floating point). Інтерполяції немає, farther pose не використовується, tolerance не збільшується.
3. Keyframe **GT-eligible**, лише якщо йому дісталася окрема GT pose у межах tolerance.
4. Keyframe без такої pose **недоступний для GT evaluation**. Це не invalid SLAM/depth frame. Він лишається в SLAM export, у predicted depth, у кожній fused map і в non-GT runtime records.
5. Причини виключення:
   - `no_gt_pose_within_tolerance`: у межах tolerance немає жодної GT pose;
   - `gt_pose_within_tolerance_assigned_to_closer_keyframe`: one-to-one асоціація віддала єдину близьку pose ближчому keyframe.

### 2. Спільний eligible set

Один явний список `evaluated_frame_ids` діє для всіх методів (B0, B1, P1-global, P1-raw, P1-keyframes-*, P1-window, P1-confidence-*):

| Обчислення | Які keyframes |
|---|---|
| ATE/RPE для кожного методу, B0 Sim(3) diagnostic, P1 SE(3) evaluation transform | лише eligible, однакові для всіх |
| GT reference cloud (GT depth + GT pose) | лише eligible; одна reference для всіх методів |
| Estimate maps (P1-*, B1 GT-depth control) | усі retained keyframes, однакові для всіх. B1 бере GT depth і P1 poses, GT pose йому не потрібна |
| B0 sparse landmarks | без змін (не frame-based) |

Отже, виключений keyframe не може потрапити в один метод і бути виключеним з іншого. RPE рахується по сусідніх eligible keyframes (`rpe_delta_unit = matched_pose_rows`, як і раніше), тому пара може перекривати виключений keyframe.

### 3. Мінімум зразків і відмови

- 0 eligible keyframes: comparison `failed`, reason `no retained keyframe has a GT pose within 0.02 s; GT evaluation is unavailable`.
- 1–2 eligible: ATE/RPE і спільний SE(3) transform для map metrics математично потребують ≥ 3 точок. Comparison `failed` з reason `insufficient_gt_coverage: …` (кількість і excluded IDs). Coverage записується в `inputs.json` до відмови. Метрики не підставляються.
- В обох випадках P1-global child (`methods/<id>.global`) уже завершений і не змінюється.

### 4. Звітність coverage

Machine-readable, той самий об'єкт `gt_pose_coverage` (у `inputs.json` він називається `evaluation_only.gt_pose_eligibility`):

| Поле | Значення |
|---|---|
| `policy` | `exclude_keyframes_without_gt_pose_within_tolerance` |
| `max_timestamp_delta_s` | 0.02 (незмінна tolerance) |
| `association` | опис правила асоціації |
| `candidate_keyframes`, `evaluated_keyframes`, `excluded_keyframes` | кількості |
| `coverage_fraction` | evaluated / candidate |
| `evaluated_frame_ids`, `excluded_frame_ids` | у порядку timestamps keyframes |
| `excluded[]` | `frame_id`, `timestamp_s`, `nearest_gt_delta_s` (лише для діагностики, ця pose не використовується), `reason` |

Де записано: `inputs.json`, `trajectory_evaluation.json`, `metrics.json` (і в кожному row: `gt_evaluated_keyframes`, `gt_candidate_keyframes`, `gt_coverage_fraction`), `evaluation/<method>.json`, `comparison.csv` (ті самі три колонки). Human-readable: колонка `GT keyframes` у таблиці `report.md`, note і розділ `## GT pose coverage` з таблицею виключених keyframes.

### 5. Сумісність із попередніми результатами

- Якщо всі keyframes мають GT pose, eligible set дорівнює всім keyframes, і числа не змінюються. Додаються лише поля coverage, колонки CSV і рядки report.
- Перевірка на реальних даних цієї машини: comparison на stages `yulian_tum_e2e_f200_20261025_01` (22/22 keyframes eligible). Старий код (`ab80f42`) і новий код дали побітово однакові oracle arrays/reference і однакові числа в `metrics.json`, `trajectory_evaluation.json`, `evaluation/*.json` і child maps (timing не порівнювався). Відносна різниця з записаним run `4952e37` ≤ 2.5e-16. Причина — інше середовище (numpy 2.4.6/Python 3.11 проти 2.2.4/3.12), не цей fix. Вихід цієї перевірки не збережено в `results/`.
- `load_oracle_inputs` за замовчуванням лишається strict, як і раніше. Exclusion вмикає лише comparison (`exclude_missing_gt_poses=True`). U-01 `frame_diagnostics`, U-03 `robust_fusion_run` і `render_robust_fusion_figures.py` поводяться так само: на даних без повного GT coverage вони явно падають. Їх U-01…U-04 evidence не змінено.


## Recorded B0 evaluation: outputs, coverage та resources

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md). Історичні run IDs та результати збережено.

### Outputs і semantics

- **Partial GT coverage:** `metrics.json` і `inputs.json` містять `gt_coverage` для всіх frozen RGB inputs, навіть initialization / LOST frames. Поля: `total_rgb_frames`, `matched_gt_frames`, `unmatched_gt_frames`, `coverage_percent`, `matched_frame_ids`, `excluded_frame_ids` та `excluded[]` (ID, timestamp, diagnostic nearest-GT delta, reason). `tracking.gt_coverage` охоплює всі tracking rows; `final_trajectory.coverage.gt_coverage` / retained-keyframe equivalent окремо описують лише exported pose frames. Ці denominators явно позначені: наявність GT не означає наявність SLAM pose.
- Recorded WP2 evaluator приймає тільки frozen GT tolerance **рівно 0.02 s**; generic timestamp matcher та comparison/keyframe policy не змінено. Усі input rows лишаються в tracking-success / latency denominator. Лише GT-dependent ATE/RPE використовують matched poses; немає interpolation, farther matches, GT pose edits або filtering SLAM inputs. RPE delta/gap semantics лишаються попередніми. Якщо жоден input не має valid GT match, CLI повертає exit **2** з JSON `status=failed`, `no_valid_gt_overlap` та full coverage report до створення output directory. За 1–2 matches чи degenerate gauge GT metrics лишаються unavailable з причиною, без вигаданих чисел.
- Source run залишається незмінним; wrapper створює окремий `results/runs/<source_run_id>.resources.json`. Навіть child preflight failure зберігає exit code / reason, а FPS тоді `null`. Existing run/report ніколи не перезаписуються.
- Derived `results/runs/<eval_run_id>/`: validated `run.json`, `metrics.json`, `inputs.json`. `method=B0`, `model=null`, `alignment=null`: Sim(3) — виключно evaluation transform у metrics, не metric scale recovery.
- **Final trajectory**: `input_setup/trajectory/trajectory_final.txt`, optimized upstream snapshot. Це не causal all-frame history. Upstream final export може передувати останньому background mapping update.
- **Retained keyframes**: poses із того самого stopped sparse snapshot; окремий Sim(3) fit через той самий `trajectory_metrics(..., alignment="sim3")`, що й comparison `B0_sim3`. Ці два рядки не об'єднуються й не трактуються як одна trajectory.
- **ATE / RPE**: метри / degrees, greedy one-to-one GT association, default tolerance 20 ms; RPE delta=1 **matched pose row**, не RGB frame. RPE не gap-aware; це Y-03. Мало GT matches або degenerate gauge → metrics `null` з причиною.
- **Pose coverage**: poses / frozen associated RGB-depth frames, фактично переданих SLAM. Це не tracking success. GT-associated pose count звітується окремо.
- На historical Y-02 commit derived run завжди **degraded**: там не оцінювалися all-frame states, failure segments або gap-aware RPE, навіть якщо source містив Y-01 CSV. Y-03 extension нижче визначає поточні status rules. Exit 0 evaluator означає успішне створення звіту; status/reason слід читати з run.json.
- `inputs.json` містить source commit/dirty flag, source hardware/environment та SHA-256 input artifacts. Hardware/environment у derived `run.json` описують evaluation host, не приписують йому source performance.

### Resource scope

`wall_clock_s` — весь child runner: preflight, startup, initialization/tracking, sparse export та shutdown. `effective_fps` = validated input frames / цей wall clock; warm-up не виключається. Це не per-frame latency чи real-time proof.

Peak RSS: POSIX `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`; macOS bytes, Linux KiB → bytes. Це **максимум individual-process RSS**, як його повертає OS, не сума одночасного RAM усіх workers; облік descendants залежить від OS. Wrapper запускається окремим свіжим процесом. Якщо він уже reap-ив інші children, cumulative peak не можна відняти: поле стає `null` з причиною. Unsupported platform / недоступний RSS також дає `null`, не оцінку.

Cold start до першого tracked frame не instrumented: `cold_start_s=null` з причиною. Mapping latency, whole-loop per-frame latency та VRAM цим wrapper не вимірюються. `real_time_claim=false`.


## Causal tracking, failure accounting і gap-aware RPE

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md). Історичні run IDs та результати збережено.

#### Tracking і failures

- `read_tracking_log` перевіряє schema, CSV hashes, frame IDs / timestamps, metadata counts та pose validity проти frozen preparation. Advertised, але неповний або corrupt export відхиляється до створення output directory; він не стає silently absent.
- Denominator: **всі frozen associated RGB-depth input frames, фактично передані SLAM**, включно з initialization/LOST/UNKNOWN. Numerator: observed native `OK` count. Якщо немає UNKNOWN / track exceptions, `tracking_success=OK/all`; інакше success=`null` + reason, а `observed_ok_fraction` звітується окремо. Missing OK pose не підміняється; usable-pose coverage окрема від state success.
- Contiguous state segments містять first/last frame IDs, timestamps та row counts. `timestamp_span_s` — різниця timestamps першого й останнього спостереження, не оцінка того, скільки часу state тривав між samples.
- Failure table: initializing, LOST, relocalizing, UNKNOWN, OK-without-pose, track exceptions, keyframe observation errors, GT-unassociated usable poses. Counts можуть перекриватися. Відсутність GT association — evaluation limitation, не tracking loss.
- Online ATE — окремий global evaluation-only Sim(3) fit **causal** poses. Final optimized / stopped sparse rows із Y-02 збережені окремо. Online poses не використовуються для alignment/fusion sparse snapshot.

#### Gap-aware RPE

1. Використовуються лише causal OK rows із valid pose та без track exception; GT association — unchanged greedy one-to-one evaluator rule.
2. Один Sim(3) fit на всій associated causal trajectory через unchanged `trajectory_metrics`; той самий evaluation-only scale використано для всіх relative pairs. Немає per-segment scale fitting.
3. Candidate delta вимірюється в **matched causal pose rows до filtering**, default 1. Pair відхиляється, якщо хоча б один intervening frozen input не має OK + valid pose + no exception; також перевіряються endpoints. GT-unmatched, але observable OK rows самі по собі не створюють tracking gap.
4. Eligible / excluded input frame-ID pairs записуються явно. ATE лишається доступним, навіть коли великий delta не дає RPE pairs. No pairs, all LOST, недостатньо GT matches або degenerate gauge → відповідні metrics `null` з причиною, не нульова помилка.

Derived status **ok**, якщо source ok, verified tracking повний, final/causal metrics і gap-aware RPE доступні та latency summary визначена. Інакше **degraded** із конкретними причинами. Наявний tracking loss сам по собі не означає failed evaluation: failure statistics — валідний результат. Historical sources без Y-01 export підтримуються зі status degraded.


## D-1…D-9: registered decisions

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/TWO_PERSON_COMPLETION_PLAN.md). Історичні run IDs та результати збережено.

### 8. Technical decisions (resolved)

All decisions below are final for this version. They were made from repository evidence, choosing conservative options that keep the merged pipeline working. Changing any of them requires a new plan revision; no chunk waits for a human decision.

**D-1 — Data splits.**
- Decision:
  - smoke = fr1/xyz first 200 (unchanged);
  - development = fr1/desk all 573;
  - development spike = fr1/desk first 50;
  - selection = fr2/desk first 50;
  - held-out = fr3/long_office_household all 2488.
- Evidence: EXPERIMENTS §2 lists exactly these sequences; `docs/EXPERIMENTS.md` on `5e542d7` reproduces the manifests byte-for-byte. Selection is a 50-frame prefix, as fixed by MODEL_SELECTION §6.

**D-2 — Branch reuse and assisted work.**
- Superseded refs (§1.4) are never merged or cherry-picked wholesale.
- Nazar's WP1 work is ported file-by-file from `5e542d7` (N-01, N-03) and `047992e` (N-04).
- Nazar's WP2 assistance (`816b7f4`, `4484fd7`) is reference material for Y-01/Y-02. Yaropolk adapts it selectively, and adopted parts are credited "assisted by Nazar"; WP2 ownership stays with Yaropolk.
- Nazar's WP3 foundation `fd73d56` is not merged (superseded by Yulian's implementation).
- WP3/WP4 defects get a focused `fix/nazar-*` PR with tests; Yulian is notified, and the fix does not wait on him.

**D-3 — Primary dense model.**
- Decision: the primary is the winner of the pre-registered selection rubric (MODEL_SELECTION §5, `docs/EXPERIMENTS.md`) on the N-03 clean re-run.
  - With the current evidence that is **UniDepth V2 ViT-L** (`resolution_level` 0): weighted score 4.620 vs 4.299; selection AbsRel 0.0646 vs 0.1145.
  - The other model is the fallback: **DA3METRIC-LARGE** at `process_res` 504.
- **Fallback trigger** (technical, pre-registered): if the primary fails the N-04 pipeline gate (any child run not ok, OOM, model-ID/grid rejection by the unchanged mapping code), the fallback becomes primary for N-05/N-06 with no further decision.
- Both models run on dev/selection in N-05 (the "primary vs fallback" ablation).
- Why this is conservative: it follows the rule the project committed to before measuring. The DA3 path stays unchanged and working.
- Disclosed tradeoffs: UniDepth has a worse selection RMSE (0.450 vs 0.421 m) and higher VRAM (1.80 vs 1.54 GiB).
- Licence state: UniDepth code is CC-BY-NC-4.0 and the checkpoint card declares no separate licence; this is recorded as a limitation only (D-6).

**D-4 — Ablations and selection rules.**
- **In scope** (pre-registered grid for N-05):
  - keyframe interval {1, 2, 5};
  - P1-window `causal_window_frames` {60, 150}, plus 0 = P1-global;
  - confidence retain {100%, 75%, 50%}, with thresholds from dev50 UniDepth predictions only (DA3: skipped, no confidence output);
  - primary vs fallback model;
  - DA3 resolution 384 vs 504 (depth-only evidence ported in N-04).
- **Out of scope:**
  - ICP: not implemented; PLAN §6 Plan B allows dropping it, and adding it would be new WP3 scope;
  - P2 (DUSt3R/VGGT);
  - KITTI;
  - semantics.
- **Held-out configuration** (computed mechanically from dev results only):
  - Among the primary model's P1 variants, take the lowest dev Chamfer-L1.
  - Ties within 1 mm go to the simpler configuration: global over window, larger keyframe interval, no confidence filter.
  - P1-window is used on held-out only if it beats P1-global on **both** dev Chamfer-L1 and dev SE(3) ATE (EXPERIMENTS §6: "required if dev improves").
  - Selection-split rows are reported but not used to choose.
  - Alignment thresholds, voxel size, τ = {2, 5, 10} cm and crop = none stay at the merged defaults (`configs/mapping_comparison.json`, `configs/offline_mapping.json`).

**D-5 — Held-out protocol.**
- fr3 stays the held-out split.
- The failed superseded-runner attempt `wp2_heldout2488_4484fd7` is disclosed in DATASET_FREEZE, HELDOUT_BENCHMARK, WP2_BENCHMARK and FINAL_RESULTS. It produced no metrics and tuned nothing.
- No held-out access before the IC3 freeze is merged.
- Each held-out configuration runs once.
- A rerun is permitted only after a documented code-bug fix merged via its owner's PR, under a new run_id, with both runs reported. Parameters are never changed.
- Held-out results are never used to choose anything.

**D-6 — Licence and release metadata.**
- No project licence is chosen or invented. The current state is recorded in FINAL_RESULTS limitations:
  - the repository has no LICENSE file;
  - pySLAM is GPLv3 (not vendored);
  - DA3 is Apache-2.0;
  - UniDepth code is CC-BY-NC-4.0;
  - weights are not committed.
- Release tag name: `v1.0.0`.
- Demo video: stored in the ignored `results/runs/<demo_run_id>/` with its SHA-256 recorded; only small previews are committed.

**D-7 — Real-time criterion.**
- Input rate is the TUM 30 Hz camera, giving a 33.3 ms frame budget.
- "Real-time" may be claimed only if the measured p95 per-frame end-to-end latency ≤ 33.3 ms **and** effective FPS ≥ 30 with no unbounded backlog, on the stated hardware and resolution.
- Otherwise the system is labelled "offline". "Near-real-time" is not used.
- The current pipeline is sequential and offline, and the model p95 alone already exceeds 33.3 ms on the selection runs, so the expected verdict is "offline". This is not presented as a failure.

**D-8 — Execution model.**
- Every chunk self-merges after its required checks are green and its diff contains only allowed files.
- Owner review is requested for attribution and is non-blocking.
- Original WP ownership and attribution are preserved in docs and the contribution table.

**D-9 — B0 baseline configuration.**
- Frozen as merged: `configs/wp2_pyslam_baseline.json` (pySLAM `96019cf`, mono, ORB2 1000 features, DBOW3, Python core, `-O`, seed 0).
- The per-split configs change only dataset fields.
- If B0 loses tracking or fails on a split, that is recorded as a B0 result. The baseline is not retuned, because changing it would invalidate the B0/P1 shared-pose comparison.

**Removed from the dependency graph:** deadlines, scheduling, presentation duration, team availability, slide-format and storage preferences, and owner review. None of them gates any chunk.

---

Операційний D-8 вище — історична модель execution. Поточні дозволи на commit/push/PR/merge визначаються [CONTRIBUTING](../CONTRIBUTING.md) і прямою інструкцією користувача; історичний план не надає автоматичного дозволу.


## DA3 metric-depth / preprocessing facts

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/MODEL_SELECTION.md). Історичні run IDs та результати збережено.

### 8. DA3METRIC-LARGE adapter (C5): перевірені факти

Перевірено в коді `depth_anything_3` (git `3d835ec1`) і на локальному checkpoint; не є результатом selection spike.

- Checkpoint: `depth-anything/DA3METRIC-LARGE`, HF revision `4010e39f3634a45bc60553321fb49fb760bd594e`, файл `model.safetensors`, SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776`. Adapter визначає файл і hash із локального cache під час завантаження і пише їх у run.json.
- dtype: ваги float32; `DepthAnything3.forward` сам вмикає autocast bfloat16 (якщо GPU підтримує), інакше float16. Тому `--dtype` приймає лише bfloat16/float16 і має збігатися з тим, що вибере DA3; float32 inference без обходу API неможливий (поза C5).
- Config має лише backbone + DPT head, без camera encoder/decoder: input intrinsics ігноруються, API не повертає intrinsics, confidence (`conf = None`) і `is_metric`. Metric depth = raw · mean(fx, fy) / 300 з K_processed (DA3 README).
- Preprocessing `upper_bound_resize`: longest side → process_res, потім кожна сторона → найближче кратне 14 (два `cv2.resize`). K_processed — див. ARCHITECTURE §3 і D008.
- Hard gates із §4 для 20 кадрів fr1/xyz: NaN/Inf немає, shape стабільна (294×378), K_processed коректний, latency і peak VRAM збираються (run `c5_parity_f20_20261021`). На ~0.01% pixels окремих кадрів inference недетермінований між запусками (PROJECT_STATUS, failure log).
