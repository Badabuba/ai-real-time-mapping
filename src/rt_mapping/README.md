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

Починати реалізацію слід із contracts і synthetic geometry tests. Не імпортувати pySLAM або конкретну foundation model у generic contracts/alignment modules.
