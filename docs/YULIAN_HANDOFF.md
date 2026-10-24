# WP3/WP4: Юліан — alignment та fusion

Оновлено: 25 жовтня 2026. Це перевірка фактичного коду та план завершення, а не твердження про готовий real-data benchmark.

## Аудит репозиторію

- Усі п'ять попередніх PR були merged у `develop`. Окремих незлитих feature commits, відкритих PR або GitHub issues під час перевірки не знайдено.
- `main` містив лише ранній DA3 smoke. [PR #6](https://github.com/Badabuba/ai-real-time-mapping/pull/6) переніс історію `develop` у `main` (`36ed781`).
- WP1 C1–C5 реалізовані: TUM loader/manifest, geometry contracts, depth evaluation/timing, DA3 adapter та recorded runner. Є авторський CUDA smoke на 20 кадрах. Fallback/model selection і ширший evaluation ще не завершені.
- WP2 має native macOS baseline і sparse handoff: 200 кадрів, 197 final poses, 1,205 landmarks, 19 keyframes, 7,595 observations. All-frame states/timing та automated ATE/RPE ще відсутні. `0 LOST` за upstream counters не доводить 100% tracking success.
- До цієї роботи пакетів `alignment/` і `fusion/` не було. `experiment.example.yaml` лишається design example із TODO; він не є executable end-to-end pipeline.
- У цьому checkout відсутні `data/raw/`, cached checkpoints та повні real run folders. Versioned summaries/PNG не замінюють NPZ/CSV.
- Перший Windows CPU audit: 382 passed, 2 skipped, 2 failed. Знайдено POSIX-only `os.killpg` і privileged symlinks. Helper fixes додано; native Windows pySLAM setup не перевірявся.

## Що реалізовано для Юліана

| Частина | Доказ | Межа перевірки |
|---|---|---|
| Robust scalar scale | `alignment/estimators.py::estimate_scale` | median ratios, metric residuals, count/ratio gates; tests із 30% gross outliers |
| Independent-frame Sim(3) | `alignment/estimators.py::estimate_sim3` | seeded RANSAC + Umeyama, proper rotation; planar/collinear/reflection/noise tests; окремий API, не режим DA3 CLI |
| Correspondences | `alignment/correspondences.py` | ID/timestamp join; raw vs undistorted grids; replay resize/crop; bilinear sampling; masks/range/confidence/reprojection filters |
| Coordinates | `geometry/projection.py` | T_wc, camera z, Brown k1/k2/p1/p2/k3; resize/crop + distortion round trips |
| Незалежна validation | `runs/mapping_run.py` | seeded split за **landmark ID**; landmark не потрапляє і в calibration, і в validation; 4×4 spatial coverage gate |
| Dense map | `fusion/voxel.py` | metric poses, filtering, incremental voxel centroids, capacity gate, optional scipy statistical filter, PLY/NPZ |
| Offline integration | `scripts/run_offline_mapping.py` + `configs/offline_mapping.json` | completed WP1/WP2 artifacts → input hashes, alignment/residuals, metric keyframe trajectory, map, timing, terminal run.json |
| Synthetic smoke | `scripts/run_alignment_smoke.py` | translated/rotated cameras, resized depth, depth outliers; known scale 2.5; без downloads/GPU |
| CPU CI | `.github/workflows/tests.yml` | Ubuntu/Windows, Python 3.11/3.12; tests + synthetic smoke; CI результат перевіряти окремо від локального |

Локальний suite після основної реалізації: **441 passed, 1 skipped** (native pySLAM API check). Synthetic development run `yulian_synthetic_dev_20261025`: scale `2.500000160469811`, absolute error `1.60e-7`; 168/171 calibration inliers, 45 withheld pairs / 15 landmarks, 900 fused samples. Це synthetic correctness evidence; не TUM accuracy або real-time результат. Остаточний clean-commit run записується окремим summary у `results/summaries/`.

## Відтворення без GPU

У власному Python 3.11/3.12 environment:

```powershell
python -m pip install -e ".[dev,plots,filtering]"
python -m pytest tests -q
python scripts/run_alignment_smoke.py --plot
```

Кожний smoke створює унікальний run ID. Inputs позначені `synthetic`; очікуваний scale використовується лише generator-ом та зовнішньою correctness перевіркою, не estimator-ом. Існуючі runs не перезаписуються.

## Реальний handoff

1. Від Ярополка: **повну** `results/runs/yaropolk_b0_fr1_xyz_200_sparse_20261023_03/`, включно з `run.json` і `sparse/{export.json,landmarks.npz,keyframes.npz,observations.csv,sparse_map.ply}`. Або новий відтворений B0 run з `--export-sparse`.
2. Від Назара: completed DA3 run того самого frozen dataset/checksum/split, з `run.json` та C3 predictions для **всіх** SLAM keyframes. IDs поточного export: `0,3,4,7,9,11,14,17,20,77,80,84,170,178,182,186,190,194,199`. Перші 20 DA3 кадрів не дають повного покриття. Existing CUDA CLI може створити новий 200-frame run.
3. Input manifests: `status=ok`, методи `B0` і `model-spike`, однаковий dataset block. Runner перевіряє sparse hashes, model ID, calibration і timestamps; зберігає hashes source manifests та всіх спожитих NPZ.

```powershell
python scripts/run_offline_mapping.py `
  --slam-run results/runs/yaropolk_b0_fr1_xyz_200_sparse_20261023_03 `
  --geometry-run results/runs/NAZAR_MATCHING_200_FRAME_RUN `
  --config configs/offline_mapping.json `
  --run-id yulian_real_f1_global_unique
```

Placeholder `NAZAR_MATCHING_200_FRAME_RUN` замінити фактичним переданим run. Real-data команду тут **не запускали**: input artifacts відсутні. GT depth/trajectory runner не читає.

## Вихід та conventions

- `alignment.json`: `metric = s R slam + t`; scalar CLI має R=I,t=0. SLAM landmarks і translations множаться на s; metric depth та rotations не масштабуються.
- `trajectory_metric.csv`: timestamp, frame_id, translation у метрах, qx/qy/qz/qw; `tracking_state=keyframe_snapshot`. Це retained keyframes із того самого snapshot, не normalized all-frame export.
- `map.ply`, `map.npz::xyz_m`, `observation_count`: equal-weight voxel centroids. Count — кількість **pixel samples**, не незалежних frames; `min_voxel_observations` не є multi-view consistency test.
- `residuals.csv`: camera-z residual у метрах, calibration/withheld та inlier flags. JSON median/p95 по calibration **inliers**; all-pairs median та withheld median/p95 записані окремо.
- `inputs.json`, `metrics.json`, `timing.json`, `run.json`: provenance/counts/CPU integration timing; SLAM/model inference latency сюди не входить.
- `plot=true` додає residual/map PNG (plots extra). `statistical_neighbors>0` потребує filtering extra. Для DA3 без confidence поріг має лишатися `null`; інакше явна помилка `missing_confidence`.
- Missing prediction, invalid calibration, low inlier count/coverage, bad holdout, empty map або capacity overflow дають failed run із причиною. Preflight rejection не створює run.

## Що ще лишається Юліану

| Пріоритет | Завдання | Залежність / критерій готовності |
|---|---|---|
| 1 | Real scalar alignment + residual plot | Отримати обидва full runs; пройти inlier/coverage/withheld gates без підбору за GT |
| 2 | Перевірити real fused metric cloud | Оглянути depth/voxel artifacts і trajectory; не змішувати poses різних snapshots |
| 3 | WP5 alignment/fusion ablations | B1 oracle, P1-raw/global; confidence лише з реальною confidence; однаковий split/hardware |
| 4 | Спільний benchmark та input-to-output launcher | Nazar/Yaropolk adapters на доступному hardware; ATE/RPE, map accuracy/completeness, latency/memory |
| 5 | Demo та presentation | Real artifact + review + rehearsal; не показувати synthetic cloud як результат TUM |
| Умовно | Sliding-window scale / ICP | Після development comparison; ICP після coarse alignment і лише за покращення withheld residual; не вимога першого scalar MVP |

Організаційно треба підтвердити дати/ліміт презентації та submission, hardware усіх учасників і ліцензію. Репозиторій public; координатор scope/release за PLAN — Назар. GitHub issues та повідомлень teammates від імені Юліана не створювали.
