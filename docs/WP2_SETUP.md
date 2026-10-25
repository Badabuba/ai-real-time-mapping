# WP2: pySLAM baseline — Ярополк

## Поточний результат (23 жовтня 2026)

**Native runtime встановлений. Перший реальний monocular B0 smoke пройдено.**

- Поточний branch: `yaropolk-sparse-observation-export`; перший smoke був на `yaropolk-pyslam-smoke-run`, setup починався на `yaropolk-pyslam-baseline` від `origin/develop` (`31cfd29`). На момент історичного run зміни були uncommitted (`dirty_worktree=true`); code тепер merged через PR #5 та PR #6. Native setup перевірено на macOS; Windows helper fixes не є native Windows validation.
- Run: `yaropolk_b0_fr1_xyz_200_20261023_02`, status `ok`.
- 200 RGB frames оброблено; 198 final poses; 0 frames зі станом LOST за upstream counters. Перші два кадри — initialization.
- Wall clock із startup: 86.6969 s. Це **не** real-time claim або stage-latency benchmark.
- Raw trajectory: `results/runs/yaropolk_b0_fr1_xyz_200_20261023_02/input_setup/trajectory/trajectory_final.txt`.
- Малий versioned звіт: `results/summaries/wp2_b0_fr1_xyz_200_20261023.json`.
- Масштаб trajectory — умовні monocular SLAM units. ATE/RPE ще не пораховані.

Наступний WP2 крок також реалізовано й перевірено: opt-in `--export-sparse`, новий run `yaropolk_b0_fr1_xyz_200_sparse_20261023_03` — 1,205 landmarks / 19 retained keyframes / 7,595 observations. 200 processed, 197 final poses, 0 LOST. Формат, pixel conventions, handoff для Юліана та evidence: [WP2_SPARSE_EXPORT.md](WP2_SPARSE_EXPORT.md). Export не додається заднім числом до старих runs. Manual Sim(3)-aligned ATE/RPE diagnostic старого run зроблено окремо; автоматичний recorded evaluator ще не реалізований.

## Dataset verification

TUM `rgbd_dataset_freiburg1_xyz` лежить у `data/raw/tum_rgbd/` разом із `.tgz` archive. Raw data не змінювалися.

- Archive: 448204271 bytes, SHA-256 збігається з manifest Назара.
- Усі 1600 extracted files побайтово збігаються з archive.
- 798 RGB PNG (8 bit), 798 depth PNG (16 bit), усі 640×480, timestamps зростають.
- C1 loader дає 792 associations; frozen smoke = перші 200.
- `build_tum_manifest.py --check` відтворює versioned manifest.
- 3000 finite GT poses; timestamps зростають і покривають RGB time range.
- GT quaternion components округлені: squared norm tolerance = 5e-4. Evaluation має нормалізувати quaternion перед побудовою rotation.

Історичний звіт першої перевірки (до native installation): `results/summaries/wp2_setup_fr1_xyz_20261023.json`. Його статус не описує поточний runtime; актуальний звіт — `wp2_b0_fr1_xyz_200_20261023.json`.

## Середовища і hardware

- `.venv-wp2`: lightweight verification/configuration/tests, Python 3.11.16.
- `.venv-pyslam`: окремий native runtime, Python 3.11.16. Не змінюємо environment Назара.
- Host: macOS 26.6.2 / arm64, 32 GiB RAM, 10 logical CPUs. Після installation лишилося близько 12 GiB free.
- CUDA не потрібна для classical B0; DA3 CUDA runner на цьому Mac не працюватиме.
- Runtime: NumPy 1.26.4, PyTorch 2.6.0, Python OpenCV 4.11.0; native OpenCV 4.14.0 (`opencv@4`). Full Python package versions: `requirements/wp2-pyslam-macos-arm64.txt`.
- Native source: pySLAM 2.10.8, commit `96019cfafcfc099ac9866884d7143a9ed1451a0d`.
- GTSAM: tag 4.2a9, commit `c57988fe554e7213c77fe379c1d7c483de26ad33` + **supplied upstream** `thirdparty/gtsam.patch`. SHA-256 patch/vocabulary та Homebrew versions є у summary.

## Відтворення installation на Apple Silicon

Це перевірений classical/headless шлях, а не весь `install_all.sh`. All-in-one installer також завантажує багато depth/semantic models; для B0 вони не потрібні. Login shell через `chsh` не змінювали, `~/.python/venvs/pyslam` не використовували і не видаляли.

Запускати з root course repository. Системні dependencies через Homebrew (це змінює system packages):

```bash
HOMEBREW_NO_AUTO_UPDATE=1 brew install eigen suite-sparse glew pkg-config libomp glfw flann catch2 openblas protobuf opencv@4 libusb
```

Default `opencv` зараз є version 5; pinned pySLAM потребує **OpenCV 4**, тому явно `opencv@4`.

Створити environments (якщо вже існують — активувати/перевикористати, не видаляти):

```bash
UV_PYTHON_INSTALL_DIR="$PWD/.local/wp2/python" uv python install 3.11.16
UV_PYTHON_INSTALL_DIR="$PWD/.local/wp2/python" uv venv --python 3.11.16 .venv-wp2
UV_PYTHON_INSTALL_DIR="$PWD/.local/wp2/python" uv venv --python 3.11.16 .venv-pyslam
uv pip install --python .venv-wp2/bin/python -r requirements/wp2-tools.txt
uv pip install --python .venv-pyslam/bin/python -r requirements/wp2-pyslam-macos-arm64.txt
```

Source checkout поза versioned project code:

```bash
git clone --filter=blob:none --no-checkout https://github.com/luigifreda/pyslam.git external/pyslam
git -C external/pyslam checkout --detach 96019cfafcfc099ac9866884d7143a9ed1451a0d
# Якщо раніше створено sparse inspection checkout:
git -C external/pyslam sparse-checkout disable
```

Не встановлювати інший `pyslam` з PyPI. Для нашого runtime не потрібні всі learned-feature git submodules/checkpoints.

Native builds (CMake + Ninja, правильний venv interpreter, два jobs за замовчуванням):

```bash
.venv-wp2/bin/python scripts/build_wp2_native.py
```

Script збирає g2o, utils/solvers/volumetric bindings, ORB2, DBOW2/3, iBoW, GTSAM та `gtsam_factors`. GTSAM має окремий pinned clone; native script встановлює його Python package, тому його навмисно виключено з Python requirements file. Логи — `logs/wp2/native/`. Помилка configure/build зупиняє script; можна повторити один stage: `--component gtsam` (або `g2o`, `cpp`, `orb`, `dbow2`, `dbow3`, `ibow`).

ORB vocabulary, потрібний DBOW3 на macOS, завантажено з URL у pinned upstream:

```bash
.venv-pyslam/bin/gdown 'https://drive.google.com/uc?id=1-4qDFENJvswRd1c-8koqt3_5u1jMR4aF' -O external/pyslam/data/ORBvoc.txt
```

Після installation:

```bash
.venv-wp2/bin/python scripts/check_wp2_environment.py --dataset-only --full
.venv-wp2/bin/python scripts/build_tum_manifest.py --check
.venv-wp2/bin/python scripts/check_wp2_environment.py --pyslam-python .venv-pyslam/bin/python --probe-runtime
UV_CACHE_DIR="$PWD/.local/wp2/uv-cache" uv pip check --python .venv-pyslam/bin/python
.venv-wp2/bin/python -m pytest tests -q
```

Runtime probe пройшов (`logs/wp2/runtime-probe-08.json`). Він імпортує реальний upstream entry point, але сам по собі не запускає tracking. Probe зберігає шлях до venv interpreter: `.resolve()` на Python symlink втрачав venv site-packages, це виправлено і перевірено regression test.

## Повторити реальний B0 smoke

Кожного разу новий run ID, finished runs не перезаписуються:

```bash
.venv-wp2/bin/python scripts/run_wp2_pyslam.py --frames 200 --run-id yaropolk_b0_fr1_xyz_200_new_id
```

Runner: dataset verification → pinned source check → validated `run.json=running` → isolated RGB-only view/config → upstream headless process → artifact validation → `ok` або `failed` з reason. Timeout/interrupt прибирає worker process group. Додаткові CLI keys: `--pyslam-python`, `--pyslam-root`, `--timeout`.

```text
results/runs/<run_id>/
├── run.json
├── upstream.log
├── metrics.json
└── input_setup/
    ├── input/000000.png ... 000199.png  # symlinks лише на RGB + times.txt
    ├── camera.yaml
    ├── pyslam.yaml
    ├── setup.json                      # preparation record, не run status
    └── trajectory/
        ├── trajectory_online.txt
        ├── trajectory_final.txt        # timestamp tx ty tz qx qy qz qw; T_wc
        └── other_metrics_info.txt
```

`metrics.json` зараз перевіряє finite poses, quaternion norms, timestamps на frozen input grid та повноту frame counters. Zero exit code без валідних output artifacts не вважається успіхом. Pose fraction не видається за tracking success. ATE/RPE і stage latency не вигадуються.

Input — frozen 200 TUM associations через upstream `FolderDataset` із оригінальними timestamps і shared frame IDs у setup.json. У view **немає depth або GT**. Так не потрібен generated associations file у raw dataset; upstream не може автоматично прочитати GT для fitting/evaluation.

K — із shared WP1 manifest; distortion — з pinned TUM1 camera settings; resize немає. `Camera.RGB=0`, бо input читається як BGR через `cv2.imread`. Observation exporter надалі має врахувати raw distorted pixels vs undistorted keypoints.

Configuration: ORB2/1000, DBOW3, Python sparse core, g2o optimization, depth/semantics/volumetric integration вимкнено. Python запускається з **`-O`**, як у shebang офіційного `main_slam.py`; це явно записано у versioned config. Parent Python/NumPy/OpenCV RNG seeded; threaded/worker determinism не гарантується.

## Failure evidence і обмеження

- Run `_01` без `-O` initialized tracking, але впав на frame 3: `map_point.py::remove_frame_view`, assertion `self == frame.get_point_match(idx)`. Upstream workers після exception залишилися активними; зупинено лише process group цього run. Finished record залишено `failed`; причина assertion збережена в log.
- Run `_02` відповідає офіційному optimized launch mode (`python -O`) і завершився. Це не доказ виправлення underlying assertion condition: debug-mode Python-core behavior лишається upstream limitation.
- macOS друкує duplicate Objective-C classes для Python OpenCV wheel + Homebrew OpenCV. На успішному headless run вони не призвели до crash; не заявляємо загальної GUI stability.
- Після успішного shutdown `resource_tracker` повідомив про cleanup 46 leaked semaphore objects. Exit 0; не приховуємо warning.
- Upstream експортує final trajectory **до** `slam.quit()`, коли останній local-mapping job ще може завершуватись. Це його snapshot; для наступного строгого benchmark/exporter треба синхронізувати mapping перед final export.
- Запуск був із uncommitted code. Native install, verification і smoke — реальні локальні результати; це не clean-commit benchmark.

## Залишок WP2 після historical macOS smoke (23 жовтня)

- [x] dataset + archive/member verification;
- [x] separate Python tools/runtime environments;
- [x] pinned native build recipe + Python dependency versions;
- [x] real entry-point imports;
- [x] 200-frame monocular smoke, trajectory і frame counters;
- [ ] normalized per-frame `trajectory.csv`, tracking states і timing;
- [x] sparse landmarks + retained-keyframe observation/pixel links для Юліана (див. WP2_SPARSE_EXPORT.md; не all-frame history);
- [ ] автоматизовані GT timestamp association, ATE/RPE та збереження numeric evaluation artifacts (manual diagnostic старого run уже виконано);
- [ ] clean reviewed commit та ширший baseline/evaluation run.

## Integration update — 25 жовтня

Додатковий [Linux container runtime](WP2_LINUX_CONTAINER.md) зібрано без змін pinned pySLAM source/baseline config. Native API check і entry-point preflight пройшли. Clean `4952e37` run відтворив 200 frames / 198 final poses / 0 LOST, 1,277 landmarks / 22 keyframes / 8,893 observations. [Summary](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json).

Automated timestamp association, SE(3)/Sim(3) ATE/RPE тепер реалізовані для **retained keyframes** у comparison runner; real metrics незалежно збігаються з evo. Normalized all-frame states/timing та all-frame evaluator integration у верхньому historical checklist усе ще лишаються WP2 work. Це Linux-on-Windows Docker evidence, не native Windows SLAM або GUI support.


## Y-04 — ширші frozen splits (25 жовтня 2026)

Owner: Ярополк (WP2). Branch `feature/yaropolk-split-support`, base `origin/develop` = `523cfa75a571fc14f7a35c475ad0e2fcdca707cf`. N-01 manifests та Y-01/Y-02/Y-03 уже merged; відсутність N-03 не блокує split support за technical dependency rule IC1. Цей chunk робить **preflight / preparation only**, не benchmark.

### Dataset configs

| Config | Sequence | Frozen split | Frames |
|---|---|---|---:|
| `configs/wp2_pyslam_baseline.json` | fr1/xyz | smoke | 200 |
| `configs/wp2_pyslam_development.json` | fr1/desk | development | 573 |
| `configs/wp2_pyslam_selection.json` | fr2/desk | selection | 50 |
| `configs/wp2_pyslam_heldout.json` | fr3/long_office_household | held-out | 2488 |

Нові configs відрізняються від baseline **лише** `dataset_manifest`, `sequence_dir`, `archive`, `split`; це перевіряє unit test. ORB2/1000, DBOW3, Python core, optimization, seed та всі інші algorithm fields незмінні. Notes baseline збережено як historical text, не як поточну заяву про validation.

`verify_dataset` відтворює legacy C2 smoke через незмінений `build_tum_manifest`, а wider frozen manifests — через незмінений `build_tum_split_manifest`. Порівнюються archive/index hashes, identities та SHA-256 кожного selected RGB/depth файла; PNG headers і timestamps перевіряються для всього source recording. Ground truth читається лише як metadata для структурної перевірки, не для fitting або metrics. `--full` додатково порівнює всі extracted files із archive bytes.

### Frame selection і calibration

Обидва CLI (`prepare_wp2_baseline.py`, `run_wp2_pyslam.py`) підтримують mutually exclusive `--frames N` або **`--all-frames`**. Без flags лишається historical default 200. `--all-frames` означає саме configured frozen split: selection = 50, а не всі 2893 associations fr2/desk. Preparation API приймає `frames=None` із тією ж семантикою. New default run ID — `yaropolk_b0_<UTC>`, без hard-coded fr1/xyz.

Camera intrinsics беруться з shared manifest. Common upstream TUM1 baseline settings збережено; **тільки distortion calibration** береться з pinned `settings/TUM2.yaml` або `TUM3.yaml` для відповідної камери. Відсутній TUM3 k3 явно стає 0, а не успадковує TUM1 k3. Algorithm/viewer/depth defaults не копіюються з іншого camera template. FolderDataset читає BGR, тому `Camera.RGB=0` як і раніше. Для RGB-only B0 GT depth scale не використовується.

### Preflight і preparation (без SLAM)

Кожного разу новий output directory; нічого не перезаписується. Приклад development; для selection/heldout замінити config та output name:

```bash
.venv-wp2/bin/python scripts/check_wp2_environment.py \
  --config configs/wp2_pyslam_development.json --dataset-only --full

.venv-wp2/bin/python scripts/prepare_wp2_baseline.py \
  --config configs/wp2_pyslam_development.json --all-frames \
  --output outputs/wp2/y04_development_<unique_id>
```

Preparation створює RGB-only view, timestamps, camera config та setup.json. У input view немає GT/depth; upstream SLAM не запускається. Source metadata/hashes лишаються в preparation для provenance. **На held-out у Y-04 не запускати `run_wp2_pyslam.py`**; лише перевірка bytes та підготовка input. Held-out benchmark лишається після IC3 freeze. Actual development/selection SLAM runs — Y-05.

### Локальні inputs і перевірка

Початково був лише fr1/xyz. Y-04 authorization дозволяє завантажити рівно три official archives із URLs у frozen manifests (~3.72 GB сумарно), перевірити recorded SHA-256 і безпечно extract. Raw data / archives залишаються ignored у `data/raw/tum_rgbd/`, не потрапляють у PR. Existing fr1/xyz та recorded runs не змінюються.

Serial download fr1/desk був навмисно зупинений через низьку швидкість; partial bytes збережено й повторно використано в ranged download із 8 bounded workers на тих самих URLs. Повний SHA-256 має збігатися перед final archive rename/extraction. Links / unsafe archive paths відхиляються, disk headroom перевіряється перед extraction. Packages не встановлювались і не оновлювались.

Tests: legacy smoke regression, wider manifests і per-file corruption, invalid split/count/IDs/sequence/hash, whole-split vs whole-recording selection, per-camera distortion без algorithm changes, immutable output, CLI flag exclusivity / historical default / neutral run ID. Full local CPU suite: **620 passed, 1 native skip**; setup tests: **26 passed**. Final real preflight evidence із paths/hashes/config provenance — `results/summaries/yaropolk_y04_preflight.json` після завершення input verification. Shared status docs лишаються для integration checkpoint за file boundaries плану.

Проміжна real-data перевірка: fr1/desk archive SHA-256 збігся з frozen manifest; full preflight **ok** (перевірено 1212 extracted files), підготовлено **573 RGB frames**, виконано **0 SLAM frames**. Preparation: `outputs/wp2/y04_development_early_03bb672` у feature worktree. Selection/held-out archives ще завантажуються; background verifier автоматично зробить повну перевірку і preparation трьох splits після downloads. До цього wider-input acceptance / merge не оголошується завершеним.


### Deadline scope і official fr2 ground truth

За останнім рішенням користувача (залишилося ~3.5 h) Y-04/Y-05 виконуються на development + selection, **без нового download held-out**. Held-out config/code залишається, але його real-data preflight і Y-06 explicitly skipped: input unavailable / deadline. Це не full held-out validation; user-authorized scope adjustment supersedes the original three-input acceptance gate.

Manual fr2/desk archive має exact frozen SHA-256; усі **5933 extracted files** побайтово збігаються з archive. First preflight rejected official groundtruth через пару різних poses з однаковим timestamp **1311868229.576**, rows 10858/10859 (zero-based), поза first-50 selection interval. Preflight тепер приймає nondecreasing GT timestamps, **явно звітує duplicates**, як metadata limitation; decreasing stamps / invalid poses все ще rejected. Це не GT fitting або зміна raw data. У Y-05 selection evaluation reference обмежується input time window ± association tolerance; ambiguous pair далеко за межами window не використовується. Full-recording evaluation потребуватиме окремого documented ambiguity rule.
