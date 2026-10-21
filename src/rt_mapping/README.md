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

Решта модулів — planned.

Починати реалізацію слід із contracts і synthetic geometry tests. Не імпортувати pySLAM або конкретну foundation model у generic contracts/alignment modules.
