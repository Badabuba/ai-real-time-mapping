# Архітектура та контракти pipeline

Цей документ фіксує межі модулів до реалізації. Мета — щоб Назар, Ярополк і Юліан могли працювати незалежно та з'єднати результати без ручного перейменування полів або неоднозначних coordinate frames.

## 1. Компоненти

```text
DatasetReader
  ├─> SlamAdapter ─────────────> SlamExport
  └─> GeometryAdapter ─────────> GeometryPrediction
                                      │
SlamExport + GeometryPrediction ─> Alignment
                                      │
                                AlignmentResult
                                      │
                                   Fusion
                                      │
                                   MapArtifact
                                      │
                                  Evaluation
```

1. **DatasetReader** синхронізує RGB, intrinsics, а в evaluation mode — ground truth pose/depth.
2. **SlamAdapter** запускає pySLAM і експортує poses, sparse landmarks та observations.
3. **GeometryAdapter** запускає рівно одну модель через спільний інтерфейс.
4. **Alignment** оцінює scale або Sim(3) і повертає diagnostics.
5. **Fusion** переносить валідні dense points у world frame та агрегує їх.
6. **Evaluation** читає артефакти, а не внутрішній стан конкретної моделі.

## 2. Обов'язкові data contracts

Формат на диску може бути NPZ/JSON/CSV/PLY, але поля й одиниці мають бути стабільними.

### FrameRecord

| Поле | Тип | Значення |
|---|---|---|
| sequence_id | string | незмінний ID sequence |
| frame_id | integer | порядковий номер |
| timestamp_s | float64 | timestamp датасету, секунди |
| image_path | string | шлях від data root |
| width, height | integer | розмір сирого RGB |
| K | 3×3 float64 | intrinsics для сирого RGB |

### GeometryPrediction

| Поле | Тип | Значення |
|---|---|---|
| frame_id | integer | frame_id відповідного FrameRecord |
| timestamp_s | float64 | timestamp відповідного FrameRecord, секунди |
| depth_m | H×W float32 | глибина в метрах; NaN для invalid |
| confidence | H×W float32 або null | більше = надійніше; діапазон документується adapter-ом |
| K_processed | 3×3 float64 | intrinsics після resize/crop |
| valid_mask | H×W bool | геометрично валідні pixels |
| model_id | string | repo + checkpoint + revision |
| preprocess | object | resize/crop/normalization/dtype |
| inference_ms | float | тільки model call після warm-up |

Перша реалізація — `rt_mapping.adapters.da3_metric.Da3MetricAdapter` (C5): модель завантажується один раз; torch/DA3 імпортуються лише під час завантаження; `confidence=None`, бо DA3METRIC-LARGE її не повертає (одиниці не підставляються); depth із NaN/Inf/≤0 або несподіваною shape → помилка, а не тиха маска. На диску prediction — детермінований NPZ (`save_prediction`) без ground truth.

Якщо модель видає relative depth, adapter не має називати поле depth_m. Використовується окреме поле inverse_depth_relative, а metric conversion стає явним кроком alignment.

### SlamExport

| Артефакт | Мінімальні поля |
|---|---|
| trajectory.csv | timestamp_s, frame_id, tx, ty, tz, qx, qy, qz, qw, tracking_state |
| landmarks.npz | point_id, xyz_slam, observation_count |
| observations.parquet/csv | frame_id, point_id, u, v, reprojection_error_px |
| timing.csv | frame_id, tracking_ms, mapping_ms, total_ms |
| run.json | config, code revision, environment, transform convention |

Y-01 runtime export: `trajectory_all.csv` має один causal observation на **кожний** frozen input frame, explicit native state та порожній pose з reason для initialization/LOST/unobservable frames. `is_keyframe_created` і source frame IDs є insertion events під час track call, не final retained membership. `timing.csv::tracking_ms` вимірює `Slam.track` wall time; unattributed `mapping_ms` та unmeasured whole-loop `total_ms` порожні з reasons. UTF-8/LF, float17, checksum/read-back validation: `contracts/slam.py`, `slam/tracking_log.py`, [docs/ARCHITECTURE.md](ARCHITECTURE.md#slam-exports). Online poses мають upstream world/SLAM units; не змішувати їх із normalized stopped sparse snapshot. Existing optimized `input_setup/trajectory/trajectory_final.txt` зберігається окремо.

### AlignmentResult

Мінімум: source_frame, target_frame, scale, R, t, transform_direction, method, number_of_pairs, inlier_count, inlier_ratio, median_residual_m, p95_residual_m, thresholds, failure_reason. Матриця без явно записаного напрямку перетворення не приймається.

### MapArtifact

- map.ply або map.npz з xyz у метрах та, за можливості, RGB/confidence;
- trajectory_metric.csv;
- run.json із посиланнями на input manifests;
- metrics.json;
- visualization.png для швидкої перевірки, але не замість числових метрик.

## 3. Coordinate conventions

- Метрична одиниця після alignment: метр.
- Pixel convention: u праворуч, v вниз, origin у верхньому лівому куті; центри pixels мають цілі координати (як у OpenCV/TUM calibration), тож W×H image займає [−0.5, W−0.5] × [−0.5, H−0.5]. Resize: cx' = (cx + 0.5)·sx − 0.5 (див. `rt_mapping/geometry/intrinsics.py`).
- Camera frame: x праворуч, y вниз, z вперед, якщо конкретний backend не вимагає іншого; conversion записується явно.
- Основне представлення pose: T_wc, перетворення точки з camera frame у world frame. Якщо backend повертає T_cw, adapter інвертує його і зберігає обидві назви в metadata.
- Quaternion order у CSV: qx, qy, qz, qw.
- Resize/crop завжди оновлює K_processed; не можна back-project depth зі старими intrinsics.
- DA3 (`upper_bound_resize`, process_res 384): два `cv2.resize` (640×480 → 384×288 → 378×294); adapter застосовує `resize_intrinsics` на кожен крок, тож K_processed описує сітку збереженої depth. Власне оновлення K у DA3 (cx·sx) і historical run відрізняються на −0.205 / −0.194 px (decision D008 у PROJECT_STATUS).

Unit test має перевіряти, що projection(back_projection(pixel, depth)) повертає той самий pixel із похибкою < 1e-4 у synthetic case.

## 4. Стратегія alignment

### Case A: спільні poses/pixels, різний scale

Це основний MVP. Для sparse landmark, який спостерігається в кадрі i:

1. переносимо landmark у camera frame за pose SLAM;
2. беремо його positive z_slam та predicted z_dense в тому самому pixel;
3. відкидаємо invalid/confidence-low/border pixels і великі reprojection errors;
4. оцінюємо scale s ≈ z_dense / z_slam robust median або RANSAC;
5. перевіряємо estimate на withheld correspondences;
6. масштабуємо translation та sparse geometry, але не rotation.

Оцінюємо global scale як baseline, а sliding-window scale — тільки як ablation. Надто вільний per-frame scale може приховувати temporal inconsistency моделі.

### Case B: незалежні coordinate frames

Якщо geometry model повертає власні cameras/point maps:

1. будуємо 3D–3D correspondences через спільні pixels/tracks;
2. оцінюємо Sim(3) методом Umeyama всередині RANSAC;
3. перевіряємо positive scale, det(R)=+1, inlier coverage та residual;
4. застосовуємо multi-scale point-to-plane ICP тільки як refinement;
5. приймаємо transform, лише якщо validation residual зменшився.

### Чому не просто ICP

ICP потребує достатньо близької ініціалізації, може зійтися до локального мінімуму, а часткове overlap і різна density створюють хибні correspondences. Тому sparse observations дають coarse alignment, а ICP — необов'язкове уточнення.

## 5. Fusion

MVP fusion:

1. depth → camera-frame point cloud через K_processed;
2. depth/confidence/range filtering;
3. перетворення через metric T_wc;
4. voxel downsampling;
5. агрегація keyframes і видалення statistical outliers.

TSDF або Gaussian representation — розширення. Спочатку потрібна проста fused point cloud, бо її легше налагоджувати й оцінювати.

## 6. Offline і streaming режими

- **Offline reference:** детермінований послідовний запуск; використовується для correctness і benchmark.
- **Streaming target:** SLAM обробляє всі кадри; geometry model — keyframes або async queue; fusion не блокує tracking.

Слово real-time вживаємо лише разом із hardware, resolution, input FPS і p95 latency. Якщо pipeline обробляє запис повільніше за його тривалість, називаємо його offline. Якщо відстає, але працює інкрементально, — near-real-time із зазначеним lag.

## 7. Failure states

Кожен модуль повертає машинозчитуваний status: ok, skipped, degraded або failed, а також reason. Обов'язкові причини: tracking_lost, insufficient_correspondences, invalid_scale, model_oom, timestamp_mismatch, missing_intrinsics та non_finite_output. Silent fallback заборонений.

## 8. Реалізований offline alignment/fusion (25 жовтня)

`scripts/run_offline_mapping.py` споживає completed B0/model-spike runs і виконує Case A без GT. Resize/crop replay перевіряє K_processed; raw distorted pixels лишаються raw для depth sampling, а Brown distortion інвертується для dense rays. Scale recovery множить SLAM translation/landmarks, не depth або rotation. Calibration та withheld split розділено за landmark ID; acceptance перевіряє inlier count/ratio і pooled 4×4 image coverage.

Sim(3) Case B реалізовано окремим API `estimate_sim3` із synthetic outlier/degeneracy tests. DA3 CLI використовує scalar Case A. ICP/sliding-window ще не ввімкнено. Fusion повертає equal-weight voxel centroids у метрах; optional statistical filtering задається явно. Observation count — pixel contributions, не distinct views. Export trajectory має лише retained keyframes того самого snapshot. Деталі: [docs/REPRODUCIBILITY.md](REPRODUCIBILITY.md#runtime).

Geometry adapters кидають `GeometryAdapterError(reason, message)` (`rt_mapping.geometry.adapter`); додаткові reasons: missing_input, unexpected_input, unsupported_config, cuda_unavailable, model_load_failed, unexpected_model_output. Runner (`rt_mapping.runs.geometry_run`) записує їх у run.json як `status=failed`, `reason="<code>: <message>"`; власні reasons runner-а — dataset_mismatch, evaluation_failed, internal_error.


<a id="slam-exports"></a>

## Sparse SLAM export

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SPARSE_EXPORT.md). Історичні run IDs та результати збережено.

### Файли `results/runs/<run_id>/sparse/`

| Файл | Поля / призначення |
|---|---|
| `landmarks.npz` | `point_id`: int64[N]; `xyz_slam`: float64[N,3]; `observation_count`: int64[N]. Count дорівнює кількості **експортованих** observations, а не всіх historical matches. |
| `keyframes.npz` | `frame_id`, `keyframe_id`, `upstream_frame_id`: int64[K]; `timestamp_s`: float64[K]; `T_wc`: float64[K,4,4]; `K`: float64[K,3,3]; `distortion`: float64[K,5] у порядку OpenCV k1,k2,p1,p2,k3; `image_size_wh`: int64[K,2]. |
| `observations.csv` | `frame_id,keyframe_id,point_id,keypoint_index,u,v,u_undistorted,v_undistorted,reprojection_error_px,depth_slam`. |
| `sparse_map.ply` | ASCII point cloud із xyz, без RGB. Порядок vertices збігається з `landmarks.npz`. Це sparse geometry, не dense reconstruction. |
| `export.json` | Schema `rt_mapping.sparse_export/v1`, status, counts, SHA-256, units, conventions, source→export transform, snapshot stage, skip counters та limitations. Записується останнім як completion marker. |

`run.json` посилається на всі sparse artifacts; `metrics.json` додає перевірені counts. Runner перевіряє hashes, foreign keys, poses, depth, observation counts та reprojection residuals після завершення child process. Відсутній/некоректний export не дозволяє run отримати `ok`.

### IDs та coordinates

- `frame_id` — shared ID із frozen dataset manifest. Він відновлюється через унікальний RGB timestamp (tolerance 1e-6 s), а не через припущення `frame_id == pySLAM.id`.
- `keyframe_id` — pySLAM `kf.kid`, окремий counter. `upstream_frame_id` — `kf.id`, тільки для diagnostics.
- Export містить **лише retained keyframes та їхні landmark observations**. Це не all-frame observation history.
- Poses мають convention `T_wc`: `p_world = R_wc @ p_camera + t_wc`.
- World frame нормалізовано до camera frame першого upstream keyframe на момент snapshot. `export.json` містить `T_export_world_from_upstream_world`.
- Landmark coordinates, keyframe translations та `depth_slam` мають **довільні monocular SLAM units, не метри**. GT не використовується exporter-ом.
- `u,v` — original **distorted** RGB pixel coordinates (`kf.kps`), origin зверху зліва, u вправо, v вниз, integer pixel centers. Саме цей grid відповідає оригінальному RGB.
- `u_undistorted,v_undistorted` — `kf.kpsu`. `reprojection_error_px` = Euclidean norm між ними та pinhole projection `K @ p_camera`, без scale weighting чи octave normalization.
- `depth_slam` = positive camera-frame z landmark, не Euclidean distance до camera.

Для predicted depth після resize/crop не можна індексувати map просто через raw `u,v`: спочатку застосувати preprocessing transform моделі та користуватися відповідним `K_processed`/pixel convention. Distortion та resize — різні операції. Intrinsics і distortion збережені окремо.

### Snapshot і shutdown

Pinned headless `main_slam.py` завершується через `os._exit`; export після `runpy.run_path(...)` ніколи не виконався б. Opt-in bootstrap імпортує `pyslam.config` перед core (щоб зареєструвати native lib paths) і встановлює runtime wrapper **лише** на `Slam.quit`.

Wrapper спочатку викликає оригінальний `quit`, потім перевіряє, що mapping/loop/GBA workers не активні, і читає map під `map.update_lock`. Повторний quit не перезаписує export. Upstream forced-exit cleanup зберігається. Активний worker, broken backlink, неоднозначний timestamp або invalid geometry спричиняє явну помилку.

Це snapshot після shutdown, **не гарантія повної convergence чи обробки кожного queued mapping job**. Upstream `trajectory_final.txt` пишеться раніше; його optimization state може відрізнятись. Для alignment цих landmarks використовувати **`keyframes.npz::T_wc` з того самого export**, а не змішувати snapshots.

Bad points та views відсутніх/culled keyframes не експортуються. Observations із nonpositive z пропускаються; points без retained positive-depth observations також пропускаються. Причини/кількості записуються у `skipped`. Порогів residual/inlier filtering exporter не підбирає: це майбутня відповідальність alignment.

Ці artifacts не є reloadable pySLAM system state: `main_map_viewer.py` потребує іншого `map.json` та companion state. PLY придатний для перегляду geometry незалежно від native viewer.

### Як читати handoff

```python
from pathlib import Path
import csv
import numpy as np
from rt_mapping.slam.sparse import check_sparse_export

directory = Path("results/runs/<run_id>/sparse")
metadata = check_sparse_export(directory)  # no pySLAM dependency
with np.load(directory / "landmarks.npz", allow_pickle=False) as data:
    points = dict(data)
with np.load(directory / "keyframes.npz", allow_pickle=False) as data:
    cameras = dict(data)
with (directory / "observations.csv").open() as stream:
    observations = list(csv.DictReader(stream))  # CSV values are strings
```

У Python tools environment запускати з `PYTHONPATH=src`, якщо project package не встановлений. Join через явні `point_id` / `keyframe_id`, не array row number. Pixel→camera→world round trip та residual перевіряються synthetic tests.


## Causal all-frame tracking export

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_TRACKING_EXPORT.md). Історичні run IDs та результати збережено.

### Артефакти

Новий `run_wp2_pyslam.py` run автоматично записує в корені run directory:

- `trajectory_all.csv`: **один рядок на кожний frozen input frame**, включно з initialization/LOST; frame_id, timestamp_s, tracking_state, state_reason, tx/ty/tz/qx/qy/qz/qw, pose_reason, is_keyframe_created, created_keyframe_frame_ids, keyframe_reason, error.
- `timing.csv`: frame_id, timestamp_s, tracking_ms, mapping_ms, mapping_reason, total_ms, total_reason.
- `tracking_export.json`: schema `rt_mapping.slam_tracking_export/v1`, counts, SHA-256 обох CSV та precise pose/timing/keyframe semantics.

Serialization: UTF-8, LF, floats із 17 significant digits, fixed columns, canonical quaternion sign. Existing files не перезаписуються. Після normal shutdown CSV перечитуються, hashes/counts/IDs/timestamps/poses перевіряються проти frozen frames. Неповне покриття або malformed artifact означають failed run. `UNKNOWN`, observer errors або missing OK pose означають degraded run із причиною. Часткові CSV зберігаються при failure.

### Що саме спостерігається

Bootstrap обгортає pinned Python-core `Slam.track`, `Map.add_keyframe` та `Slam.quit`, викликаючи original methods і зберігаючи їхні return values/exceptions. GT не читається observer-ом. Запис flush-иться після кожного кадру, бо upstream завершує процес через `os._exit`.

- **State:** native `tracking.state.name` після track call; стандартні NO_IMAGES_YET / NOT_INITIALIZED / OK / LOST / RELOCALIZE / INIT_RELOCALIZE. Якщо state не спостерігається — UNKNOWN + reason, не припущення OK.
- **Pose:** `tracking.f_cur.Twc()` копіюється безпосередньо після успішного OK call з matching timestamp. Missing/non-OK/stale/invalid pose → сім порожніх полів і reason. Немає interpolation, identity placeholders або підстановки final poses.
- **World/units:** online upstream world, monocular SLAM units. Це causal pose у момент спостереження, **не** optimized final trajectory і **не** normalized world stopped sparse snapshot. Після наступних BA/loop closure log не переписується. Для alignment/fusion як і раніше використовувати stopped `sparse/keyframes.npz` разом із його landmarks.
- **Keyframes:** successful `Map.add_keyframe` calls під час поточного track call; background threads не приписуються цьому call. Boolean означає creation event під час call, не membership у final retained snapshot. Initialization може вставити reference frame 0 та current frame 2 у call 2: у рядку 2 events `[0,2]`, у рядку 0 нічого не backfill-иться. Подальше culling не змінює історію.
- **Tracking time:** wall time original track invocation, включно з waits і невеликим in-call keyframe-hook overhead; post-call pose collection/CSV I/O виключено. Це не image decode, whole input loop або end-to-end latency.
- **Mapping/total:** порожні; mapping асинхронний і не атрибутується окремому input frame. Whole-loop timer не встановлюється. `0 ms` не підставляється.


## Sparse anchoring і frame gate (GT-free)

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 3.1 Метод (GT-free)

Код: `src/rt_mapping/alignment/anchoring.py`, CLI `scripts/run_anchor_gate.py`, конфіг `configs/robust_fusion.json`.

1. Preflight без запису run dir: валідація конфігу (точні ключі на кожному рівні, у кожного порогу є `source`), provenance і `residuals.csv` cross-check з U-01 (`load_sources`, `rebuild_pairs`, `check_recorded_residuals`).
2. Конфіг має збігатися з порогами, з якими записано source comparison run (`residual_threshold_m`, `min_inliers`, `min_inlier_ratio`, `min_coverage_bins`, `voxel_size_m`, `thresholds_m`) і з U-01 `ANCHOR_BAND`. Інакше — відмова.
3. Сигнали рахує незмінений U-01 `frame_signals` (без дублювання коду).
4. **Anchoring:** `anchored_prediction(prediction, a_f)` повертає нову in-memory prediction з `z' = a_f · z_pred` (float64 добуток → float32 контракту); `valid_mask`, confidence, K і metadata без змін; файли не пишуться. Якщо `a_f` = null (A1), кадр лишається некоригованим. NaN/Inf/≤ 0 відхиляються з помилкою. SLAM poses зберігають global scale `s`.
5. **Gate:** `gate_decision(signals, config)` відкидає кадр, якщо спрацював будь-який flag (правила з §2.2, строгі нерівності як у плані). Flag, який неможливо оцінити, записується як `unavailable` з причиною і не спрацьовує: A2 без `a_f`, A3 без withheld pair, S1 без tracking export. Некоректні входи (NaN, від'ємні значення, неузгоджені null) викликають помилку, а не default.
6. **GT-free валідація:** withheld median |residual| кадру до (`|s·z_slam − z_pred|`) і після (`|s·z_slam − a_f·z_pred|`) корекції на тих самих withheld pairs. Лише звітується, для підбору не використовується.
7. Артефакти: `frame_signals.csv`, `anchor_gate.csv` (по рядку на keyframe: входи рішення, `applied_scale`, flags `true/false/unavailable`, `decision`, `decision_reason`), `anchor_gate.json` (лічильники, withheld до/після, список рішень для U-03, sha256 конфігу) і `run.json`.

**Розділення GT:** модуль і CLI не імпортують `rt_mapping.evaluation.*` і `data.tum` (AST-тест). Subprocess-тест перевіряє, що під час запуску CLI не завантажено жодного модуля `rt_mapping.evaluation`. Ще один тест видаляє всі GT/evaluation-only матеріали fixture і перевіряє, що рішення побайтово ті самі.

Конфіг заморожується після merge U-02. U-03 відмовляється працювати, якщо sha256 `configs/robust_fusion.json` відрізняється від записаного в summary U-02.


## Fusion control / anchored variants

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 4.1 Метод

Код: `src/rt_mapping/runs/robust_fusion_run.py`, CLI `scripts/run_robust_fusion.py`.

**Preflight (без run dir, без GT):**
- sha256 `configs/robust_fusion.json` має дорівнювати hash у committed U-02 summary, інакше відмова;
- provenance source runs має дорівнювати записаній у U-02 summary;
- `residuals.csv` cross-check з U-01;
- рішення gate перераховуються незміненими U-01/U-02 функціями і мають точно збігатися з committed рішеннями U-02.

**Фаза A, GT-free:**
1. Control: незмінений публічний `run_mapping` із записаним mapping config; відрізняється лише `plot`. Перевірка §3.5 плану: `map.npz` побайтово тотожний записаному P1-global, інакше voxel keys/counts і межа похибки float64.
2. Цикл fusion для варіантів спершу відтворює control map побайтово на некоригованій depth. Тому варіанти відрізняються від control лише anchored depth і gating.
3. `P1-anchored`: `z' = a_f · z_pred` для кожного кадру з `a_f`. `P1-anchored+gate`: ті самі кадри без rejected. Пози — незмінений global scale `s`.
4. `phase_a.json`, усі карти й `run.json` записуються **до** відкриття GT (тест ordering).

**Фаза B, evaluation only:** незмінений `evaluate_map` для кожного варіанта, з тим самим voxel size 0.02 m, τ = {2, 5, 10} cm, crop, записаним SE(3) transform і `reference_evaluation_only.npz`. Метрики control мають дорівнювати записаному рядку P1-global. Рядки B0/B1/P1-raw копіюються після перевірки, що вони мають той самий evaluation transform. Per-frame AbsRel/RMSE/δ1 і map contribution рахуються до і після anchoring на oracle GT grid.


## Per-keyframe diagnostic signals і registered thresholds

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 2.1 Метод

**Фаза A, GT-free** (`src/rt_mapping/alignment/frame_signals.py`):

1. Перевірити provenance: sha256 slam/geometry `run.json` має збігатися з `inputs.json` comparison run; P1-global child run має статус `ok`.
2. Повторити merged correspondences і landmark holdout split з `runs/mapping_run.py`. Перевірити їх проти записаного `residuals.csv`: `frame_id`, `point_id` і `withheld` мають збігатися точно.
3. Для кожного retained keyframe порахувати:
   - кількість pairs (усі / calibration / withheld);
   - inlier ratio і median |residual| за global scale `s`;
   - withheld median |residual|;
   - coverage calibration inliers у 4×4 bins;
   - статистики predicted depth;
   - tracking state (null + причина, якщо export відсутній).
4. **Anchor ratio `a_f`:** merged `estimate_scale` у зворотному напрямку (`z_pred` → `s·z_slam`), лише на calibration pairs цього кадру.
5. Записати `frame_signals.csv`, `signals.json` і `run.json` **до** будь-якого читання GT. Це перевіряє тест.

**Фаза B, evaluation only** (`src/rt_mapping/evaluation/frame_diagnostics.py`):

- per-frame AbsRel/RMSE/δ1 з `metrics.json` geometry run, з повторним обчисленням через oracle GT для перевірки;
- per-keyframe map contribution: точки кадру з metric pose, записаний SE(3) evaluation transform, cKDTree-відстань до `reference_evaluation_only.npz`;
- Spearman ρ (average ranks);
- failure table.

#### 2.2 Пороги (pre-registered, не підбиралися за GT)

| Flag | Правило | Джерело |
|---|---|---|
| A1 | `a_f` = null: < 30 anchors або inlier ratio < 0.5 | merged `min_inliers`, `min_inlier_ratio` |
| A2 | \|log a_f\| > log 1.25 | δ1-смуга depth metric (EXPERIMENTS §4.2) |
| A3 | withheld median \|residual\| > 0.10 m (лише якщо є ≥ 1 withheld pair) | merged `residual_threshold_m`, правило `alignment/causal.py` |
| A4 | coverage calibration inliers < 4/16 bins | merged `min_coverage_bins` |
| S1 | tracking state відомий і ≠ OK | контракт Y-01 (`contracts/slam.py`) |

У U-01 flags лише звітуються; gating не застосовується.
