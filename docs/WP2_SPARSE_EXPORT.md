# WP2: sparse landmarks та observations для alignment

Owner: Ярополк. Branch: `yaropolk-sparse-observation-export` (local/uncommitted).

Цей крок додає opt-in export до Python-core B0 runner. Він не змінює feature matching, tracking, optimization чи upstream source files. Він не завершує весь `SlamExport`: all-frame tracking states, normalized trajectory та stage timing лишаються окремою роботою.

## Фактичний результат — 23 жовтня 2026

- Run `yaropolk_b0_fr1_xyz_200_sparse_20261023_03`, status `ok`, 200 processed / 0 LOST; 197 final trajectory poses, 82.0695 s wall clock зі startup/export.
- Export: **1,205 landmarks, 19 retained keyframes, 7,595 observations**. `skipped={}`. Це інший run, ніж попередній `_02` з 198 poses; threaded execution не гарантує ідентичного результату.
- Median undistorted reprojection residual: 0.9303 px, p95: 3.1680 px, max: 8.7526 px. Це consistency diagnostic, не GT trajectory accuracy.
- Read-back validation пройшла; усі task-owned workers завершились. Upstream tracked source чистий. Усі 15 artifacts попереднього успішного run залишились byte-identical.
- CPU suite: **325 passed, 1 skipped**; skipped native check окремо пройшов у `.venv-pyslam` через unittest. Native check log: `.local/wp2/sparse-native-api.log`.
- Малий evidence summary: `results/summaries/wp2_sparse_fr1_xyz_200_20261023.json`.
- Preview: `results/visualizations/yaropolk_b0_fr1_xyz_200_sparse_20261023_03/20261023T142031_442564Z/sparse_map_preview.png`.
- Versioned preview для teammates: [results/plots/wp2_sparse_map.png](../results/plots/wp2_sparse_map.png). Повні NPZ/CSV/PLY залишаються локально в ignored `results/runs/`; для реального alignment їх треба передати Юліану окремо або відтворити run. Git merge передає code та evidence summaries, а не ці великі artifacts.
- Attempts `_01` (launcher NameError до upstream start; виправлено, додано runner regression tests) та `_02` (sandbox denied OpenMP shared memory до tracking; stopped only own process group) збережені як failed. `_03` запущено з необхідним local-process доступом.
- Новий run не має GT ATE/RPE; попередні manual diagnostic scores стосуються старого run, їх не переносимо сюди. Немає real-time claim.

## Запуск

Із root course repository, у вже встановленому environment:

```bash
.venv-wp2/bin/python scripts/run_wp2_pyslam.py \
  --frames 200 --export-sparse --run-id yaropolk_b0_sparse_new_unique_id
```

Це **новий SLAM run**, а не перетворення старої trajectory. Старий run `_02` не зберіг landmarks, тому відновити їх без повторного processing неможливо. Run ID має бути новим. Без `--export-sparse` попередній режим runner зберігається.

## Файли `results/runs/<run_id>/sparse/`

| Файл | Поля / призначення |
|---|---|
| `landmarks.npz` | `point_id`: int64[N]; `xyz_slam`: float64[N,3]; `observation_count`: int64[N]. Count дорівнює кількості **експортованих** observations, а не всіх historical matches. |
| `keyframes.npz` | `frame_id`, `keyframe_id`, `upstream_frame_id`: int64[K]; `timestamp_s`: float64[K]; `T_wc`: float64[K,4,4]; `K`: float64[K,3,3]; `distortion`: float64[K,5] у порядку OpenCV k1,k2,p1,p2,k3; `image_size_wh`: int64[K,2]. |
| `observations.csv` | `frame_id,keyframe_id,point_id,keypoint_index,u,v,u_undistorted,v_undistorted,reprojection_error_px,depth_slam`. |
| `sparse_map.ply` | ASCII point cloud із xyz, без RGB. Порядок vertices збігається з `landmarks.npz`. Це sparse geometry, не dense reconstruction. |
| `export.json` | Schema `rt_mapping.sparse_export/v1`, status, counts, SHA-256, units, conventions, source→export transform, snapshot stage, skip counters та limitations. Записується останнім як completion marker. |

`run.json` посилається на всі sparse artifacts; `metrics.json` додає перевірені counts. Runner перевіряє hashes, foreign keys, poses, depth, observation counts та reprojection residuals після завершення child process. Відсутній/некоректний export не дозволяє run отримати `ok`.

## IDs та coordinates

- `frame_id` — shared ID із frozen dataset manifest. Він відновлюється через унікальний RGB timestamp (tolerance 1e-6 s), а не через припущення `frame_id == pySLAM.id`.
- `keyframe_id` — pySLAM `kf.kid`, окремий counter. `upstream_frame_id` — `kf.id`, тільки для diagnostics.
- Export містить **лише retained keyframes та їхні landmark observations**. Це не all-frame observation history.
- Poses мають convention `T_wc`: `p_world = R_wc @ p_camera + t_wc`.
- World frame нормалізовано до camera frame першого upstream keyframe на момент snapshot. `export.json` містить `T_export_world_from_upstream_world`.
- Landmark coordinates, keyframe translations та `depth_slam` мають **довільні monocular SLAM units, не метри**. GT не використовується exporter-ом.
- `u,v` — original **distorted** RGB pixel coordinates (`kf.kps`), origin зверху зліва, u вправо, v вниз, integer pixel centers. Саме цей grid відповідає оригінальному RGB.
- `u_undistorted,v_undistorted` — `kf.kpsu`. `reprojection_error_px` = Euclidean norm між ними та pinhole projection `K @ p_camera`, без scale weighting чи octave normalization.
- `depth_slam` = positive camera-frame z landmark, не Euclidean distance до camera.

Для predicted depth після resize/crop не можна індексувати map просто через raw `u,v`: спочатку застосувати preprocessing transform моделі та користуватися відповідним `K_processed`/pixel convention. Distortion та resize — різні операції. Intrinsics і distortion збережені окремо.

## Snapshot і shutdown

Pinned headless `main_slam.py` завершується через `os._exit`; export після `runpy.run_path(...)` ніколи не виконався б. Opt-in bootstrap імпортує `pyslam.config` перед core (щоб зареєструвати native lib paths) і встановлює runtime wrapper **лише** на `Slam.quit`.

Wrapper спочатку викликає оригінальний `quit`, потім перевіряє, що mapping/loop/GBA workers не активні, і читає map під `map.update_lock`. Повторний quit не перезаписує export. Upstream forced-exit cleanup зберігається. Активний worker, broken backlink, неоднозначний timestamp або invalid geometry спричиняє явну помилку.

Це snapshot після shutdown, **не гарантія повної convergence чи обробки кожного queued mapping job**. Upstream `trajectory_final.txt` пишеться раніше; його optimization state може відрізнятись. Для alignment цих landmarks використовувати **`keyframes.npz::T_wc` з того самого export**, а не змішувати snapshots.

Bad points та views відсутніх/culled keyframes не експортуються. Observations із nonpositive z пропускаються; points без retained positive-depth observations також пропускаються. Причини/кількості записуються у `skipped`. Порогів residual/inlier filtering exporter не підбирає: це майбутня відповідальність alignment.

Ці artifacts не є reloadable pySLAM system state: `main_map_viewer.py` потребує іншого `map.json` та companion state. PLY придатний для перегляду geometry незалежно від native viewer.

## Як читати handoff

```python
from pathlib import Path
import csv
import numpy as np
from rt_mapping.slam.sparse import check_sparse_export

directory = Path("results/runs/<run_id>/sparse")
metadata = check_sparse_export(directory)  # no pySLAM dependency
with np.load(directory / "landmarks.npz", allow_pickle=False) as data:
    points = dict(data)
with np.load(directory / "keyframes.npz", allow_pickle=False) as data:
    cameras = dict(data)
with (directory / "observations.csv").open() as stream:
    observations = list(csv.DictReader(stream))  # CSV values are strings
```

У Python tools environment запускати з `PYTHONPATH=src`, якщо project package не встановлений. Join через явні `point_id` / `keyframe_id`, не array row number. Pixel→camera→world round trip та residual перевіряються synthetic tests.

## Перевірка

```bash
.venv-wp2/bin/python -m pytest tests -q
WP2_NATIVE_SPARSE_TEST=1 MPLCONFIGDIR="$PWD/.local/wp2/matplotlib" \
  XDG_CACHE_HOME="$PWD/.local/wp2/cache" \
  .venv-pyslam/bin/python -O -m unittest discover \
  -s tests -p test_pyslam_sparse_native.py -v
```

Default CPU suite не імпортує native backend. Opt-in native check створює synthetic `Map`, `Frame`, `KeyFrame`, `MapPoint` installed revision, експортує 2 landmarks / 2 keyframes / 4 observations, читає/валідує файли та не запускає tracking чи workers. Subprocess test окремо перевіряє shutdown hook до реального `os._exit`.

Implementation: `src/rt_mapping/slam/sparse.py`, `pyslam_export.py`, opt-in integration у `smoke.py`; CLI `scripts/run_wp2_pyslam.py --export-sparse`.
