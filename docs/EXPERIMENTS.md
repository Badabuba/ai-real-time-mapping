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

## 6. Мінімальна матриця

| Experiment | Smoke | Dev | Selection | Held-out | Owner |
|---|---:|---:|---:|---:|---|
| B0 pySLAM | required | required | required | required | Ярополк (дубєнь) |
| B1 oracle depth fusion | optional | required | optional | required | Ярополк (дубєнь) + Юліан (піндос) |
| model spike (2 candidates) | required | — | required | — | Назар (бос) |
| P1-raw | required | required | required | required | Назар (бос) + Юліан (піндос) |
| P1-global | required | required | required | required | Юліан (піндос) |
| P1-window | — | required | optional | required if dev improves | Юліан (піндос) |
| confidence ablation | — | required | required | best config only | Назар (бос) + Юліан (піндос) |
| keyframe interval ablation | — | required | — | best config only | Назар (бос) + Ярополк (дубєнь) |
| P2 geometry | optional | optional | optional | optional | Назар (бос) |

Спочатку один seed/end-to-end run. Повтори додаємо після усунення deterministic bugs. Для stochastic component бажано 3 seeds із mean ± std.

## 7. Acceptance thresholds

Це engineering gates, не обіцянка scientific success:

- alignment: >=30 inliers, positive finite scale, inlier ratio >=0.5, spatial coverage не в одному малому image region;
- data contract: 100% frames мають timestamp та K; shape/intrinsics tests проходять;
- pipeline: smoke sequence завершується без manual intervention;
- reporting: жоден headline metric без sequence, units, alignment mode і hardware;
- real-time claim: робиться лише якщо p95 end-to-end latency вкладається у визначений frame budget без необмеженого backlog.

Якщо quality не покращується, це не технічний failure: зберігаємо negative result, робимо ablation і пояснюємо межі гіпотези.
