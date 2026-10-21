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

Решта модулів — planned.

Починати реалізацію слід із contracts і synthetic geometry tests. Не імпортувати pySLAM або конкретну foundation model у generic contracts/alignment modules.
