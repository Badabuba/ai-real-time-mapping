# Юліан — завершений WP3/WP4 handoff

Оновлено: 25 жовтня 2026. Primary alignment/fusion та offline integration завершені й перевірені на реальних даних. [Результати, таблиця та limitations](WP3_WP4_COMPLETION.md).

## Що інтегровано

- Усі попередні WP1/WP2 PR #1–#5 перенесено з develop у main через [PR #6](https://github.com/Badabuba/ai-real-time-mapping/pull/6). Окремих незлитих teammate commits або open issues під час аудиту не було.
- [PR #7](https://github.com/Badabuba/ai-real-time-mapping/pull/7): robust scalar/Sim(3), pixel correspondences, Brown-distortion geometry, voxel fusion, artifact runner та synthetic tests.
- [PR #8](https://github.com/Badabuba/ai-real-time-mapping/pull/8): one-config launcher, comparison/evaluation, optional causal scale, Linux runtime recipe та real clean-run evidence.

| Deliverable Юліана | Статус / evidence |
|---|---|
| Synthetic scale/Sim(3) | Done: known scale 2.5, seeded outliers, degeneracies; synthetic summaries у results/summaries/ |
| Correspondences | Done: IDs/timestamps, resize/crop, raw/undistorted grids, depth/confidence/reprojection filters |
| Real scale + diagnostics | Done: scale 1.1920834; calibration inliers 76.76%, coverage 16/16; withheld median 3.88 cm, p95 31.32 cm |
| Real fused cloud | Done: 22 keyframes, 611,226 input samples, 72,887 metric voxels; PLY/NPZ та preview |
| One-config integration | Done: native SLAM + fresh DA3 + alignment/fusion/comparison; 200 frames, clean 4952e37, all stages ok |
| Smoke ablations/evaluation | Done: B0-shared-scale, P1-raw/global, B1 oracle, every-2/every-5 keyframes; ATE/RPE, map metrics, CSV/JSON/PNG |
| Causal-window code | Implemented/tested; conditional development ablation, disabled in recorded global MVP |
| Confidence ablation | Explicitly skipped: checkpoint returns no confidence; fake values are not created |

CPU suite: **472 passed, 1 native skip**; CI Ubuntu/Windows Python 3.11/3.12. Installed-backend sparse API check separately **1 passed**. Dataset/source/entry-point preflight **ok**. Baseline працює в Linux Docker на Windows host; native Windows SLAM support не заявляється.

## Реальні артефакти

Run: `results/runs/yulian_tum_e2e_f200_20261025_01/`. Parent, source stages та mapping methods мають `git_commit=4952e37dd773925c4c7aa069c4d6aaf10f489120`, `dirty_worktree=false`, `status=ok`.

- [Summary + source hashes](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json), [CSV](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.csv), [report](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200_report.md)
- [Map preview](../results/plots/yulian_tum_map.png), [residual plot](../results/plots/yulian_tum_residuals.png), [comparison plot](../results/plots/yulian_tum_comparison.png)
- [Independent real evo parity](../results/summaries/wp3_wp4_yulian_real_evo_parity.json)

Source stages: `stages/<run_id>.slam/` (1,277 landmarks / 22 keyframes / 8,893 observations) та `.geometry/` (200 C3 NPZs). Fused PLY/NPZ і trajectory: `stages/<run_id>.comparison/methods/<run_id>.comparison.global/`. GT reference/controls знаходяться лише у comparison/evaluation outputs. Великі raw data, weights та runs ignored і не передаються через Git.

Conventions: `metric = s R slam + t`; scalar mode R=I,t=0. Масштабуються SLAM translations/landmarks, metric depth і rotations не масштабуються. Poses T_wc, quaternion qx/qy/qz/qw. Trajectory — retained keyframes того самого stopped snapshot, не all-frame history. Voxel observation count — pixel samples, не незалежні views.

P1 SE(3) ATE **2.24 cm** проти raw **4.89 cm**. Completeness **8.49 cm** проти sparse **22.61 cm**; Chamfer **8.87 cm** проти **13.77 cm**. Sparse accuracy краща (**4.94 cm** проти **9.24 cm**); global map Chamfer трохи гірший за raw control (**8.76 cm**). Універсального accuracy improvement не заявляємо. Map reference має documented registered-depth calibration approximation.

## Як запустити

Після [Linux runtime setup](WP2_LINUX_CONTAINER.md), CUDA DA3 environment та cached inputs:

```powershell
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id new_unique_real_run
```

Config запускає обидва adapters. Для completed artifacts замінити stage на `{"reuse_run":"results/runs/<actual_run>"}`; inference у reuse timing не включено. Для іншого OS змінити argv у `configs/pipeline.tum.example.json`. Launcher не робить installations/downloads і сам додає --run-id/--output-root. Finished run IDs не використовувати повторно; source manifests не редагувати.

CPU correctness: `python -m pytest tests -q`, `python scripts/run_alignment_smoke.py --plot`, `python scripts/run_comparison_smoke.py --plot`.

## Залишок проєкту

| Owner | Наступна робота |
|---|---|
| Назар | Broader model-selection split + fallback comparison та resource profiling; matching 200-frame coverage цього smoke вже відтворено |
| Ярополк | Normalized all-frame trajectory/tracking states/per-stage timing; підключити evaluator до all-frame export; ширший baseline benchmark |
| Команда | Freeze held-out sequences/protocol, wider B0/B1/P1; external review, demo capture, slides, rehearsal |
| Юліан, умовно | Window scale/ICP/filtering experiments після development evidence; це розширення global MVP, не blocker завершеного WP3/WP4 |

Presentation/submission dates, time limit та final licensing decision потребують командного узгодження. Завершено offline smoke integration; full held-out study та real-time system не оголошені готовими.
