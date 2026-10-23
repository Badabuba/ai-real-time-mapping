# Архітектура та контракти pipeline

Цей документ фіксує межі модулів до реалізації. Мета — щоб Назар (бос), Ярополк (дубєнь) і Юліан (піндос) могли працювати незалежно та з'єднати результати без ручного перейменування полів або неоднозначних coordinate frames.

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

Geometry adapters кидають `GeometryAdapterError(reason, message)` (`rt_mapping.geometry.adapter`); додаткові reasons: missing_input, unexpected_input, unsupported_config, cuda_unavailable, model_load_failed, unexpected_model_output. Runner (`rt_mapping.runs.geometry_run`) записує їх у run.json як `status=failed`, `reason="<code>: <message>"`; власні reasons runner-а — dataset_mismatch, evaluation_failed, internal_error.
