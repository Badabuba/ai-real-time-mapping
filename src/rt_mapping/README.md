# rt_mapping package plan

Заплановані модулі:

```text
rt_mapping/
├── data/         # FrameRecord, TUM loader, timestamp association
├── slam/         # pySLAM adapter and export normalization
├── geometry/     # common depth/point-map adapter interface
├── alignment/    # scalar scale, Sim(3), diagnostics
├── fusion/       # back-projection, filtering, voxel fusion
├── evaluation/   # trajectory, depth, map and runtime metrics
└── contracts/    # typed schemas and serialization
```

Реалізовано (C1, WP1):

- `contracts/frame.py` — `FrameRecord` (ARCHITECTURE §2), K як float64 3×3 для сирого RGB;
- `data/tum.py` — парсинг `rgb.txt`/`depth.txt`, greedy RGB↔depth association (≤20 ms), RGB intrinsics freiburg1/2/3, `load_sequence`. Depth paths повертаються лише для evaluation.

Реалізовано (C3, WP1):

- `contracts/geometry.py` — `GeometryPrediction` (ARCHITECTURE §2) з валідацією depth/mask/confidence/K; детермінований NPZ через `save_prediction`/`load_prediction`, без ground truth і absolute paths;
- `geometry/adapter.py` — protocol `GeometryAdapter.predict(frame: FrameRecord) -> GeometryPrediction`;
- `geometry/intrinsics.py` — `resize_intrinsics` (anisotropic) і `crop_intrinsics`, центри pixels мають цілі координати; distortion не моделюється.

Реалізовано (C4, WP1):

- `evaluation/depth.py` — `evaluate_depth` (AbsRel, RMSE, MAE, δ1, counts, valid coverage; GT передається окремо від `GeometryPrediction`), `mean_depth_metrics`, `resize_depth_nearest` (nearest-neighbour з цілими центрами pixels);
- `evaluation/timing.py` — `summarize_timings`: cold start окремо, warm-up виключено, median і p95 (`numpy` linear), без FPS;
- `contracts/run_manifest.py` — валідований `run.json` v1 (docs/EXPERIMENTS.md §5): build/validate/dump/load/write, захист finished run.json від перезапису;
- `contracts/_validation.py` — спільна перевірка JSON-значень і absolute paths для `geometry.py` та `run_manifest.py`.

Реалізовано (C5, WP1):

- `adapters/da3_metric.py` — `Da3MetricAdapter` (DA3METRIC-LARGE за `GeometryAdapter`): модель завантажується один раз, torch/DA3 імпортуються лише під час завантаження; K_processed через `geometry/intrinsics.py` на кожен resize DA3; confidence = None, якщо модель її не дає; NaN/Inf/≤0 → `GeometryAdapterError`. Пакет названо `adapters`, бо `.gitignore` ігнорує `models/` (ваги);
- `runs/geometry_run.py` — model-agnostic run: перевірка датасету проти C2 manifest, predict → C3 NPZ, оцінка C4, timing, run.json (`running` → `ok`/`failed`), наявний run dir ніколи не перезаписується;
- `evaluation/tum_depth.py` — читання TUM depth PNG у метрах (лише evaluation);
- `geometry/adapter.py` — додано `GeometryAdapterError(reason, message)`.

Реалізовано (WP2): `slam/setup.py`, `smoke.py`, `sparse.py`, `pyslam_export.py` — native setup/readiness, recorded baseline та validated retained-keyframe export. `slam/visualization.py` — existing trajectory plots. All-frame normalization та automated ATE/RPE ще planned.

Реалізовано (WP3/WP4, Юліан):

- `alignment/estimators.py`: robust median scalar scale та seeded RANSAC/Umeyama Sim(3), proper rotation, metric residual/inlier gates;
- `alignment/correspondences.py`: ID/timestamp/calibration/pixel-grid checks, bilinear depth sampling, reprojection/mask/confidence/range filtering;
- `geometry/projection.py`: camera-z projection/back-projection, Brown distortion та rigid T_wc validation;
- `fusion/voxel.py`: metric translation scaling, dense points, voxel centroids, capacity limit, optional statistical filtering, PLY;
- `runs/mapping_run.py`: offline artifact integration, landmark-disjoint validation/coverage, hashes, metric keyframe trajectory, plots/timing та terminal manifests;
- `runs/synthetic_mapping.py`: reproducible synthetic inputs, окремо від real data.

Real alignment/fusion та baseline/proposed benchmark ще не перевірені: full source runs у Git відсутні. Див. `docs/YULIAN_HANDOFF.md`.

Починати реалізацію слід із contracts і synthetic geometry tests. Не імпортувати pySLAM або конкретну foundation model у generic contracts/alignment modules.
