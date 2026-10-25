# Alignment/fusion comparison

- GT depth/poses are evaluation-only except the explicitly labeled B1 control.
- All maps use the same voxel size, crop and P1 trajectory SE(3) world transform; no per-map alignment.
- B0-shared-scale reuses P1 scale only for a fair sparse/dense map comparison; B0 Sim(3) ATE is separate.
- RPE delta=1 matched retained-keyframe pair; full-frame tracking/timing are not evaluated.
- Fusion timing excludes model and SLAM inference. No real-time claim.

| Method | Points | Accuracy [m] | Completeness [m] | Chamfer-L1 [m] | ATE SE(3) [m] |
|---|---:|---:|---:|---:|---:|
| B0-shared-scale | 1038 | 0.049372 | 0.226104 | 0.137738 | 0.022377 |
| P1-global | 58569 | 0.092388 | 0.084930 | 0.088659 | 0.022377 |
| P1-raw | 62944 | 0.091324 | 0.083866 | 0.087595 | 0.048900 |
| B1-oracle | 39122 | 0.032308 | 0.033493 | 0.032900 | 0.022377 |
| P1-keyframes-2 | 39079 | 0.081805 | 0.094028 | 0.087916 | 0.022377 |
| P1-keyframes-5 | 24007 | 0.074640 | 0.104930 | 0.089785 | 0.022377 |
