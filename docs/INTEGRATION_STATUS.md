# Integration — 25 жовтня 2026

WP1 C1–C5 та WP2 sparse baseline інтегровані через [PR #6](https://github.com/Badabuba/ai-real-time-mapping/pull/6). WP3/WP4 core — [PR #7](https://github.com/Badabuba/ai-real-time-mapping/pull/7); runnable integration та real evidence — [PR #8](https://github.com/Badabuba/ai-real-time-mapping/pull/8).

## Перевірено

- CPU suite **472 passed, 1 native skip**; Ubuntu/Windows Python 3.11/3.12 CI. Installed-backend sparse API test окремо **1 passed**; dataset/source/runtime preflight **ok**.
- Full-stage run `yulian_tum_e2e_f200_20261025_01`, clean `4952e37`, all stages/methods **ok**. Config справді запускав CPU SLAM та CUDA DA3, не reuse mode.
- Linux/Docker SLAM: 200 frames / 198 final poses / 0 LOST за upstream counters; 1,277 landmarks / 22 keyframes / 8,893 observations. Historical macOS evidence Ярополка збережено.
- DA3: 200 predictions, frozen checkpoint hash збігається з Nazar evidence; mean AbsRel 0.092655, RMSE 0.177196 m. Новий GPU result відтворено на RTX 3070 Ti Laptop.
- Alignment scale 1.1920834, calibration inliers 76.76%, coverage 16/16; withheld median 3.88 cm. Fused cloud: 72,887 metric voxels.
- B0/B1/P1-global/raw та keyframe ablations записані в CSV/JSON/PNG. Real ATE/RPE незалежно відтворено через evo до floating-point precision.
- Raw data, checkpoints, environments і full runs залишаються локально/ignored. Finished run.json не редагувалися.

[Результати та tradeoffs](WP3_WP4_COMPLETION.md), [handoff/команди](YULIAN_HANDOFF.md), [small summary](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json).

## Залишок команди

| Owner | Залишок |
|---|---|
| Юліан | Primary WP3/WP4 завершені. Optional window/ICP/filtering experiments після development evidence; confidence ablation недоступна для цього checkpoint. |
| Ярополк | Normalized all-frame trajectory/states/timing, integration all-frame ATE/RPE, ширший baseline/performance benchmark. |
| Назар | Broader model selection/evaluation + fallback, resource profiling. Matching predictions цього smoke вже існують. |
| Команда | Freeze held-out protocol, wider benchmark, independent review, demo/presentation/rehearsal. |

Dense completeness/Chamfer кращі за sparse B0, але sparse accuracy краща. Global scale покращує trajectory ATE, не map Chamfer проти raw на цьому smoke. TUM reference має calibration approximation. RPE — matched retained-keyframe rows; all-frame tracking і real-time performance не підтверджені.
