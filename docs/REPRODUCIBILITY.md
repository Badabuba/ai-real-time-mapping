# Відтворення та середовища

<a id="runtime"></a>

Це довідник до [README](../README.md). Команди setup/build/download змінюють локальне середовище; наведені для явного виконання користувачем. Під час cleanup вони не запускалися. GPU inference і native SLAM — окремі optional environments, CPU correctness suite не потребує weights або TUM.

## Яке середовище обрати

| Завдання | Середовище |
|---|---|
| CPU tests / synthetic mapping / evaluation | Python 3.11/3.12, `pip install -e ".[dev,benchmark,filtering]" |
| DA3 inference | CUDA PyTorch + pinned `requirements/wp1-da3.txt` |
| UniDepth inference | окремий NumPy 2 environment, pinned UniDepth source/runtime lock |
| pySLAM на macOS arm64 | `.venv-wp2`, `.venv-pyslam`, native builders |
| pySLAM на Windows host | Linux Docker image, не native Windows |

`requirements/wp1-cpu.txt` і `wp2-tools.txt` — обмежені task environments, не повний benchmark stack. Mac native GTSAM встановлює builder, не довільний binary wheel. Наявні environments не видаляти і не змішувати DA3 NumPy 1.26 та UniDepth NumPy 2 dependencies.


## DA3: перевірений Windows/CUDA setup

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ENVIRONMENT.md). Історичні run IDs та результати збережено.

### Hardware і система

| Компонент | Значення |
|---|---|
| OS | Windows 11 Pro 64-bit, build 10.0.26300 |
| RAM | 31.2 GB |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU |
| VRAM | 8151 MiB |
| NVIDIA driver | 610.74 |
| Compute capability | 12.0 |
| Вільний диск під час setup | приблизно 181 GB на C: |
| WSL | WSL2 доступний, але встановлена лише службова distribution docker-desktop |

### Перевірений stack

| Компонент | Версія |
|---|---|
| Python | 3.11.16, isolated .venv через uv |
| PyTorch | 2.11.0+cu128 |
| torchvision | 0.26.0+cu128 |
| xformers | 0.0.35 |
| Depth Anything 3 | upstream commit 3d835ec1a5802d64a8b8b15f817a1ab54809bfe4 |
| addict | 2.4.0 |

CUDA Toolkit/nvcc у системі не встановлений. Для prebuilt PyTorch wheel це не потрібно: CUDA 12.8 runtime входить до wheel. GPU smoke test пройшов: torch.cuda.is_available() == True та matrix multiplication виконався на RTX 5070.

### Відтворення environment

PowerShell із кореня repository:

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements\wp1-da3.txt
.venv\Scripts\python.exe scripts\check_wp1_environment.py
```

### Тести

CPU-тести пакета `src/rt_mapping` (GPU і датасет не потрібні). pytest 9.1.1 встановлено 21 жовтня 2026:

```powershell
uv pip install --python .venv\Scripts\python.exe pytest
.venv\Scripts\python.exe -m pytest tests -q
```

`pyproject.toml` додає `src` у `pythonpath` для pytest, тому editable install пакета поки не потрібен.

### Відомі особливості

1. Системний Python 3.14 не використовуємо: офіційний DA3 package декларує Python <=3.13.
2. Upstream commit використовує package addict, але не декларує його в dependencies. Тому він явно pinned у requirements.
3. Warning про відсутність gsplat очікуваний і не блокує monocular metric-depth inference. Не встановлюємо Gaussian head до завершення MVP.
4. Перший import PyTorch/DA3 на Windows може тривати понад хвилину через завантаження великих CUDA DLL; наступні процеси теж мають cold-start overhead, який слід вимірювати окремо.
5. Для RTX 5070/Blackwell потрібна CUDA wheel 12.8 або новіша; перевірений варіант — cu128.

### Обрана модель для першого smoke run

`depth-anything/DA3METRIC-LARGE`: 0.35B parameters, monocular metric-depth checkpoint. Починаємо з batch size 1 і process_res 384 через 8 GB VRAM. Важкий nested checkpoint 1.4B не входить у перший smoke run.

За офіційним DA3 FAQ standalone metric checkpoint потребує перетворення `depth_m = focal_px * raw_depth / 300`. Adapter робить це явно, коли API не позначає output як уже метричний, і записує спосіб перетворення в `preprocess` кожного prediction.

### Зафіксований smoke dataset

- Sequence: `rgbd_dataset_freiburg1_xyz` з офіційного TUM RGB-D benchmark.
- Local archive: `data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz.tgz` (не комітиться).
- Size: 448204271 bytes.
- SHA-256: `A0236D97B8C30CD93B653656D2B6C293FF7C982A4130EF2A1A8BEECDB124EF98`.
- RGB calibration: fx=517.3, fy=516.5, cx=318.6, cy=255.3.
- Ground-truth PNG depth factor: 5000 units per meter.

`scripts/run_tum_da3_metric.py` (з C5) — тонкий CLI: кадри бере C1 loader і перевіряє проти `data/manifests/tum_fr1_xyz.json`, модель працює через `Da3MetricAdapter`, метрики/timing/run.json — C4. Модель береться лише з локального cache `checkpoints/huggingface` на зафіксованій revision `4010e39f3634a45bc60553321fb49fb760bd594e` (downloads вимкнені). Ground-truth depth використовується лише для оцінювання, не подається моделі.

```powershell
# one-frame GPU smoke
.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 1 --warmup 0 --run-id <new_run_id>
# 20-frame run; default run_id = <UTC time>_freiburg1_xyz_da3metric_f20_r384
.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 20 --warmup 1
```

Ключі: `--device cuda[:N]` (CPU fallback немає), `--dtype bfloat16|float16` (має збігатися з autocast DA3 на цьому GPU), `--process-res`, `--seed`, `--output-root`, `--skip-archive-hash`. Наявний run dir ніколи не перезаписується. Exit codes: 0 ok, 1 failed (причина в run.json), 2 відмова до запису. Torch/DA3 друкують попередження про triton/gsplat — вони не впливають на depth inference.


## UniDepth: pinned identity, environment і pixel grid

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/UNIDEPTH.md). Історичні run IDs та результати збережено.

### Джерела й identity

- Official code: https://github.com/lpiccinelli-eth/UniDepth/tree/8d8cfe4c7ee15297099983607febf0d4f32eb3d6
- Code license: CC-BY-NC-4.0; academic non-commercial use. Не переносимо upstream-код або ваги до repo; checkpoint card не має окремої license declaration, тому зберігаємо це обмеження й attribution upstream.
- Official model: `lpiccinelli/unidepth-v2-vitl14`, ungated, revision `52b349b514bd8b47642f67ac78cb7b5dc5c51dd9`.
- `model.safetensors`: 1415383604 bytes (~1.42 GB), SHA-256 `ba73d3de735302ccc64a50f1e557122050c4b1893e6060b28dba05d6af3e67c6`.
- `config.json`: 3848 bytes, SHA-256 `09eb0ea8de53a6c9a1d428ac98c79847fe2602ea417701261f3f628099a30816`.
- Config має `pixel_encoder.pretrained=null`; додаткові backbone downloads заборонені. Backend перевіряє config/weights hashes, створює модель і робить strict safetensors load.

### Ізольоване environment

UniDepth декларує NumPy >=2, DA3 використовує NumPy 1.26.4. `.venv` DA3 не змінюється; optional environment усередині ignored `.venv/unidepth`:

```powershell
uv venv --python 3.11 .venv/unidepth
uv pip install --python .venv/unidepth/Scripts/python.exe torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/unidepth/Scripts/python.exe --no-deps -r requirements/wp1-unidepth.txt
uv pip install --python .venv/unidepth/Scripts/python.exe -r requirements/wp1-unidepth-lock.txt
```

Training packages, Linux-only Triton, KNN/patch CUDA extensions не потрібні для `infer`. Warnings про KNN/NystromAttention стосуються evaluation upstream / V1; проєкт оцінює depth власним C4 evaluator. Wandb імпортується upstream для visualization, але adapter не викликає init/login чи telemetry APIs.

Top-level dependencies наведені у wp1-unidepth-runtime.txt, повний перевірений dependency snapshot — wp1-unidepth-lock.txt. Psutil 7.2.2 потрібен для однакових non-null RAM metadata з DA3. На sandboxed Windows за потреби задати TEMP/TMP у власну ignored writable directory перед import (upstream Wandb створює temp-папки навіть без login).

Weights завантажуються явно перед inference: base URL `https://huggingface.co/lpiccinelli/unidepth-v2-vitl14/resolve/52b349b514bd8b47642f67ac78cb7b5dc5c51dd9/`, файли `config.json` і `model.safetensors` у `checkpoints/unidepth-v2-vitl14-52b349b/`. Перевірити hashes з таблиці вище. Inference не має Hub/download викликів.

### Output semantics та K_processed

Підтверджено в official `unidepthv2.py`, `decoder.py`, `utils/camera.py`, `utils/coordinate.py` і `assets/docs/V2_README.md`:

1. `infer` повертає `depth=points[:, -1:]`: camera-z у метрах, не Euclidean radius. Output grid відновлюється bilinear resize і видаленням padding до розміру raw RGB.
2. Camera input — відомий calibrated pinhole, без GT depth/pose. `coords_grid` upstream має half-integer centres; adapter додає 0.5 до cx/cy. `camera.resize` множить K на nominal scalar, хоча image dimensions округлюються вгору до /14. Adapter компенсує camera input так, щоб після цих upstream-операцій K дорівнювала actual per-axis image transform. Геометрію перевіряють CPU-тести для landscape/portrait/padding.
3. `K_processed=FrameRecord.K`: depth повертається на raw grid із calibrated rays. `out['intrinsics']` — незалежний camera-head prediction навіть у calibrated mode. Він зберігається лише як diagnostic metadata, не підміняє K, що використана для rays.
4. Upstream `confidence` — estimated scale-invariant log error, ranking тільки всередині кадру. Для контракту higher=more reliable змінюємо лише знак: `-error`, діапазон (-inf,0]. Це офіційний error output зі зворотним напрямком, без евристичної нормалізації або probability. Якщо output відсутній, confidence=None. Historical runs до 24 жовтня мали reciprocal mapping; їх не змінюємо.
5. Ваги float32, official infer() autocast float16; resolution_level=0, native mode (200k–240k pixels до округлення). Немає median scaling, GT correction чи silent fallback.

PR #4 C5 і PR #5 WP2 merged у develop; поточна local integration повторно використовує їхні contracts/runner. Перед load backend порівнює всі installed UniDepth Python files з pinned Git tree `checkpoints/upstream/UniDepth@8d8cfe4c`; source SHA-256 записується в environment. Missing/mismatched source завершує run помилкою, без downloads. Code checkout потрібен лише для цієї read-only verification. Effective infer dtype — upstream float16 autocast, weights float32.


## pySLAM: macOS native setup та запуск

Повну CPU suite запускати в CPU environment із `.[dev,benchmark,filtering]` з README; `.venv-wp2` — лише lightweight tools, без усього benchmark stack.

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SETUP.md). Історичні run IDs та результати збережено.

### Середовища і hardware

- `.venv-wp2`: lightweight verification/configuration/tests, Python 3.11.16.
- `.venv-pyslam`: окремий native runtime, Python 3.11.16. Не змінюємо environment Назара.
- Host: macOS 26.6.2 / arm64, 32 GiB RAM, 10 logical CPUs. Після installation лишилося близько 12 GiB free.
- CUDA не потрібна для classical B0; DA3 CUDA runner на цьому Mac не працюватиме.
- Runtime: NumPy 1.26.4, PyTorch 2.6.0, Python OpenCV 4.11.0; native OpenCV 4.14.0 (`opencv@4`). Full Python package versions: `requirements/wp2-pyslam-macos-arm64.txt`.
- Native source: pySLAM 2.10.8, commit `96019cfafcfc099ac9866884d7143a9ed1451a0d`.
- GTSAM: tag 4.2a9, commit `c57988fe554e7213c77fe379c1d7c483de26ad33` + **supplied upstream** `thirdparty/gtsam.patch`. SHA-256 patch/vocabulary та Homebrew versions є у summary.

### Відтворення installation на Apple Silicon

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
python -m pytest tests -q
```

Runtime probe пройшов (`logs/wp2/runtime-probe-08.json`). Він імпортує реальний upstream entry point, але сам по собі не запускає tracking. Probe зберігає шлях до venv interpreter: `.resolve()` на Python symlink втрачав venv site-packages, це виправлено і перевірено regression test.

### Повторити реальний B0 smoke

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


## Linux/Docker runtime

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_LINUX_CONTAINER.md). Історичні run IDs та результати збережено.

### Зафіксовані inputs

- Python 3.11 Debian bookworm image digest: `18d373e126e39c29c6d38e71e2f19ca66636568318fc95c7849c462b7f9d3d64`.
- pySLAM: `96019cfafcfc099ac9866884d7143a9ed1451a0d`, Python core (`PYSLAM_USE_CPP=false`), ORB2/DBOW3, upstream `python -O`.
- GTSAM 4.2a9: `c57988fe554e7213c77fe379c1d7c483de26ad33`, лише patch із pinned pySLAM tree.
- Python package freeze: `requirements/wp2-linux-x86_64.txt`; CPU torch 2.6.0, NumPy 1.26.4, pybind11 2.13.1.
- ORB vocabulary: `ORBvoc.dbow3`, 105381669 bytes, SHA-256 `49b1deee2331aa0897aec95b0fdf0fb07eda4a608ed5b92c54186e9cf6d500ea`.

`scripts/build_wp2_linux_native.py` перевіряє source revisions та збирає native modules. Debian Qhull 8.0 headers несумісні з C++20; CMake hook компілює лише `bounding_boxes_2d.cpp` і `bounding_boxes_3d.cpp` як C++17. Решта solvers/core зберігає upstream C++20. pySLAM sources та baseline config не змінюються. Build потребує кількох GB і може бути тривалим; `--jobs 2` обмежує parallel compile.

Hamming binding upstream використовує SSSE3/SSE4.1 intrinsics навіть у SSE2 branch. Для x86_64 йому явно задається `-msse4.1` без host-specific `-march=native`; CPU повинен підтримувати SSE4.1.

Великий `volumetric` binding та його static utility library збираються Clang 14 в окремому build directory; `volumetric_module.cpp` має `-O0 -fno-lto`. GCC 12 був надто тривалим із `-O3`, досяг 9.35 GiB RSS із `-O1` та лишався memory-intensive з `-O0`. Clang діагностує upstream int→float binding conversion як narrowing error; `-Wno-error=c++11-narrowing` зберігає warning і GCC-compatible conversion без source patch. Frozen classical baseline не вмикає upstream volumetric mapping. Solvers/core зберігають GCC Release optimization; власний WP4 fusion знаходиться у `rt_mapping.fusion`. Це runtime для frozen headless baseline, не перевірка upstream volumetric/GUI modes.

CMake hook також явно додає `Qhull::qhullcpp` до binding: upstream helper не передає цю C++ library у parent scope, через що import мав undefined RTTI symbol `orgQhull::RoadError`. System Qt5 Core/Gui/Widgets preloaded через `LD_PRELOAD`, щоб PyQt wheel не підміняв private ABI Debian OpenCV/Qt5OpenGL. Цей environment задано в Dockerfile та explicit Docker argv pipeline config.

### Побудова і запуск

Команди нижче завантажують image, source і packages. Виконувати у власному environment після дозволу на setup/downloads.

```powershell
docker build -f containers/wp2.Dockerfile -t rt-mapping-wp2:96019cf .
docker run -d --name rt-mapping-wp2-yulian --shm-size=1g --memory=10g --cpus=4 --mount "type=bind,source=$((Get-Location).Path),target=/workspace" rt-mapping-wp2:96019cf
docker exec rt-mapping-wp2-yulian python scripts/check_wp2_environment.py --pyslam-root /opt/pyslam --pyslam-python /usr/local/bin/python --probe-runtime
docker exec --env WP2_NATIVE_SPARSE_TEST=1 --env WP2_PYSLAM_ROOT=/opt/pyslam rt-mapping-wp2-yulian python -O -m unittest discover -s tests -p test_pyslam_sparse_native.py -v
```

Native source має знаходитися на Linux filesystem усередині container: Windows checkout може містити symlink як text file. `/workspace` — shared repository mount; pipeline CLI використовує relative POSIX output paths, тому host і container бачать ті самі immutable run folders. Використовувати container лише цього проєкту; existing containers не перезаписувати.

### One-config pipeline

`configs/pipeline.tum.windows-docker.json` очікує running container вище, frozen TUM archive/extraction та cached pinned DA3 checkpoint. DA3 environment `.local/da3-venv` використовує host CUDA torch 2.7.1+cu118, Python 3.12, DA3 source `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`, NumPy 1.26.4 і OpenCV 4.11.0.86. Це local environment, не зміна host packages. На іншій машині замінити interpreter argv на власний перевірений environment.

```powershell
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id unique_real_pipeline
```

Launcher запускає SLAM, DA3, alignment/fusion та B0/B1/P1 evaluation. Він не встановлює dependencies і не завантажує inputs. Кожний adapter зберігає власний manifest і log. Не використовувати finished run ID повторно. `results/runs/` залишається ignored; передавати full artifacts окремо від маленьких versioned summaries.


## Frozen split configs, frame IDs і calibration

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SETUP.md). Історичні run IDs та результати збережено.

#### Dataset configs

| Config | Sequence | Frozen split | Frames |
|---|---|---|---:|
| `configs/wp2_pyslam_baseline.json` | fr1/xyz | smoke | 200 |
| `configs/wp2_pyslam_development.json` | fr1/desk | development | 573 |
| `configs/wp2_pyslam_selection.json` | fr2/desk | selection | 50 |
| `configs/wp2_pyslam_heldout.json` | fr3/long_office_household | held-out | 2488 |

Нові configs відрізняються від baseline **лише** `dataset_manifest`, `sequence_dir`, `archive`, `split`; це перевіряє unit test. ORB2/1000, DBOW3, Python core, optimization, seed та всі інші algorithm fields незмінні. Notes baseline збережено як historical text, не як поточну заяву про validation.

`verify_dataset` відтворює legacy C2 smoke через незмінений `build_tum_manifest`, а wider frozen manifests — через незмінений `build_tum_split_manifest`. Порівнюються archive/index hashes, identities та SHA-256 кожного selected RGB/depth файла; PNG headers і timestamps перевіряються для всього source recording. Ground truth читається лише як metadata для структурної перевірки, не для fitting або metrics. `--full` додатково порівнює всі extracted files із archive bytes.

#### Frame selection і calibration

Обидва CLI (`prepare_wp2_baseline.py`, `run_wp2_pyslam.py`) підтримують mutually exclusive `--frames N` або **`--all-frames`**. Без flags лишається historical default 200. `--all-frames` означає саме configured frozen split: selection = 50, а не всі 2893 associations fr2/desk. Preparation API приймає `frames=None` із тією ж семантикою. New default run ID — `yaropolk_b0_<UTC>`, без hard-coded fr1/xyz.

Camera intrinsics беруться з shared manifest. Common upstream TUM1 baseline settings збережено; **тільки distortion calibration** береться з pinned `settings/TUM2.yaml` або `TUM3.yaml` для відповідної камери. Відсутній TUM3 k3 явно стає 0, а не успадковує TUM1 k3. Algorithm/viewer/depth defaults не копіюються з іншого camera template. FolderDataset читає BGR, тому `Camera.RGB=0` як і раніше. Для RGB-only B0 GT depth scale не використовується.

#### Preflight і preparation (без SLAM)

Кожного разу новий output directory; нічого не перезаписується. Приклад development; для selection/heldout замінити config та output name:

```bash
.venv-wp2/bin/python scripts/check_wp2_environment.py \
  --config configs/wp2_pyslam_development.json --dataset-only --full

.venv-wp2/bin/python scripts/prepare_wp2_baseline.py \
  --config configs/wp2_pyslam_development.json --all-frames \
  --output outputs/wp2/y04_development_<unique_id>
```

Preparation створює RGB-only view, timestamps, camera config та setup.json. У input view немає GT/depth; upstream SLAM не запускається. Source metadata/hashes лишаються в preparation для provenance. **На held-out у Y-04 не запускати `run_wp2_pyslam.py`**; лише перевірка bytes та підготовка input. Held-out benchmark лишається після IC3 freeze. Actual development/selection SLAM runs — Y-05.


## Перевірка manifest без запису

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/DATASET_FREEZE.md). Історичні run IDs та результати збережено.

### Відтворення

Команда для перевірки одного manifest після download/extraction із кореня repo:

```powershell
.venv/Scripts/python.exe scripts/freeze_tum_split.py --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk --archive data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk.tgz --archive-url https://webshare.cvg.cit.tum.de/g/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_desk.tgz --split development --frames 50 --output data/manifests/tum_fr1_desk_spike50.json --check
```

Для інших manifests: sequence/archive/source з відповідного JSON, `--split` із колонки `splits` key; `--frames 50` лише для двох prefix50. Без `--frames` — уся sequence. `--check` порівнює bytes і нічого не пише; створення через `open('x')` відмовляється перезаписувати існуючий manifest. `--data-repo-root` дозволяє читати наявні дані з іншого локального checkout (наприклад, з git worktree без `data/raw/`), не записуючи абсолютні paths у manifest.

Перевірка N-01 (25 жовтня 2026): `--check` byte-identical для всіх чотирьох manifests; повторна генерація в окремий каталог дала ті самі SHA-256; `build_tum_manifest.py --check` для fr1/xyz без змін.


## Evaluation commands і resource sidecar

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md). Історичні run IDs та результати збережено.

### Команди

Після existing native setup із [docs/REPRODUCIBILITY.md](REPRODUCIBILITY.md#runtime), з кореня repo. Кожен запуск — новий ID. Обидва CLI мають `--help`; встановлення / downloads не виконують.

```bash
.venv-wp2/bin/python scripts/measure_wp2_resources.py \
  --run-id yaropolk_y02_smoke200_<sha7>_01 --frames 200

.venv-wp2/bin/python scripts/evaluate_wp2_run.py \
  --source-run results/runs/yaropolk_y02_smoke200_<sha7>_01 \
  --groundtruth data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz/groundtruth.txt \
  --resources results/runs/yaropolk_y02_smoke200_<sha7>_01.resources.json \
  --run-id yaropolk_y02_eval_smoke200_<sha7>_01
```

Resource wrapper за замовчуванням передає `--export-sparse`; `--no-export-sparse` дозволяє final-only run. Додатково: `--pyslam-root`, `--pyslam-python`, `--output-root`, `--timeout`. Для worktree можна передати абсолютні paths на existing runtime/source. Raw dataset мусить лишатися всередині worktree через existing verifier; локальна APFS copy-on-write копія дозволяє не завантажувати його повторно.

Evaluator підтримує historical completed merged B0 runs (`ok` / `degraded`), якщо є preparation та final trajectory. Retained export і resources необов'язкові. Відсутня telemetry → `null` + reason. Failed/incomplete source manifest, malformed poses, off-grid timestamps, підміна source hash у resource report або artifact path поза run directory відхиляються. GT передається явно й використовується тільки evaluator-ом; SHA-256 reference записується у `inputs.json`.


## Wider B0 reproduction і GT window

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_BENCHMARK.md). Історичні run IDs та результати збережено.

### GT window і official duplicate

Official fr2 GT містить два різні poses із timestamp `1311868229.576`. Вони далеко поза selection window **1311868164.3431811–1311868166.019133**. Для evaluation створено новий ignored reference з усіх GT rows у fixed input time range ±20 ms. Raw GT не редагувався; reference не містить averaging/deduplication, його timestamps строго increasing. Позавіконні rows не можуть бути timestamp candidates за тією самою tolerance, тому clipping не змінює associated candidates для наших inputs. Original/ref hashes і row counts є в summary.

### Повторити

Після documented native setup і verified inputs. Нові run IDs обов'язкові:

```bash
python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_development.json --all-frames --export-sparse --timeout 600 --run-id new_unique_dev573
python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_selection.json --all-frames --export-sparse --timeout 600 --run-id new_unique_sel50
```

Для resources використано existing `measure_process` API у **fresh Python process на кожний run**, з explicit `--config` argv. Existing `measure_wp2_resources.py` є smoke-only CLI і не має `--config`; його default не підміняв wider config. Minimal resource invocation з repo root:

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "src")
from rt_mapping.evaluation.slam_run import measure_process
root = Path.cwd()
argv = [str(root / ".venv-wp2/bin/python"), "scripts/run_wp2_pyslam.py",
        "--config", "configs/wp2_pyslam_development.json", "--all-frames",
        "--export-sparse", "--timeout", "600", "--run-id", "new_unique_measured_dev"]
print(json.dumps(measure_process(argv, cwd=root), indent=2))
```

Фактичні local orchestration scripts збережені в ignored `outputs/wp2/y05_run_one.py` та `y05_run_matrix.py`; вони додають sidecar hashes/status до resource report. Source runner/evaluators не змінені. Для evaluation reference створюється за правилом вище, після чого:

```bash
python scripts/evaluate_wp2_run.py --source-run results/runs/<source_run_id> --groundtruth outputs/wp2/y05_evaluation_gt/<source_run_id>.txt --resources results/runs/<source_run_id>.resources.json --plot --run-id <new_eval_run_id>
```

Повні raw runs / resource sidecars / GT refs / large PLY/NPZ лишаються local ignored; summary hashes дозволяють ідентифікувати artifacts. У Git — лише ці маленькі summaries, CSV, plots і doc.


## Recorded real pipeline commands

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP3_WP4_COMPLETION.md). Історичні run IDs та результати збережено.

### Команди

```powershell
python -m pip install -e ".[dev,benchmark]"
python -m pytest tests -q
python scripts/run_comparison_smoke.py --plot
python scripts/run_pipeline.py --config configs/pipeline.tum.example.json --run-id unique_tum_pipeline
# Перевірений Windows/Docker + CUDA шлях:
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id unique_real_pipeline
```

Приклад full pipeline потребує вже встановлених native SLAM/CUDA runtimes. Для іншого OS замінити stage `command` на відповідний Python/WSL/Docker argv. Для existing artifacts задати stage `{"reuse_run": "results/runs/<actual_run_id>"}`. Launcher додає власні `--run-id` і `--output-root`; не задавати їх у command.


## P1-robust commands / artifact provenance

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

### 7. Інтеграційний handoff для Nazar і Yaropolk

Цей handoff не змінює поточні N/Y chunks. Обмін іде лише через committed summaries; чужі ignored runs ніхто не читає.

`configs/robust_fusion.json` використовується **без змін**, його sha256 має бути `90567529160ec9913ba2cd756980046ba28f19c547180482358e2e906a395486`:

```powershell
(Get-FileHash configs/robust_fusion.json -Algorithm SHA256).Hash.ToLower()
```

#### 7.1 Nazar — dense depth

Splits dev573 / sel50, моделі DA3 і UniDepth. Лише development data, ніколи held-out.

Для кожного свого comparison run (`<cmp>`, `<slam>`, `<geo>` — stages із N-05):

```powershell
python scripts/run_frame_diagnostics.py --comparison-run <cmp> --slam-run <slam> --geometry-run <geo> `
  --sequence-dir <dev sequence dir> --manifest <dev manifest> --run-id nazar_u05_diag_<split>_<model>_<sha7>_01 --plot
python scripts/run_anchor_gate.py --comparison-run <cmp> --slam-run <slam> --geometry-run <geo> `
  --run-id nazar_u05_gate_<split>_<model>_<sha7>_01
python scripts/run_robust_fusion.py --comparison-run <cmp> --slam-run <slam> --geometry-run <geo> `
  --sequence-dir <dev sequence dir> --manifest <dev manifest> `
  --u02-summary results/runs/nazar_u05_gate_<split>_<model>_<sha7>_01/anchor_gate.json `
  --run-id nazar_u05_robust_<split>_<model>_<sha7>_01 --plot
```

Примітки:
- `run_anchor_gate.py` відмовить, якщо mapping config comparison run відрізняється від заморожених порогів (`residual_threshold_m`, `min_inliers`, `min_inlier_ratio`, `min_coverage_bins`, `voxel_size_m`, `thresholds_m`). Так задумано: пороги не підбираються.
- `--u02-summary` — це `anchor_gate.json` з власного gate run на тому самому comparison. `run_robust_fusion.py` звіряє з ним provenance, рішення і sha256 конфігу.
- Runs на `develop` ≥ PR #11 мають tracking export, тож S1 стане live. Кількість спрацювань S1 звітувати окремо.

Результат: `results/summaries/nazar_u05_*` і `docs/ROBUST_FUSION_DEVELOPMENT.md` (гілка `feature/nazar-robust-fusion-dev`).

## Поточні local prerequisites (audit 26 жовтня)

У цьому Mac checkout є всі selected RGB/depth files для п'яти manifests, але `.tgz` fr1/xyz та fr1/desk відсутні. Їхні verifier-команди потребують original archives; наявність extraction не замінює archive checksum. fr2/desk і fr3 archives наявні. Cleanup дані не змінює і нічого не завантажує. Дані teammates можуть відрізнятися.

OpenMP `Can't open SHM` перед tracking означає runtime/shared-memory startup failure. Для native workers потрібен доступ до shared memory; не підміняти failure успішним benchmark і не робити silent retry. Історичний authorized Y-06 retry описаний у RESULTS.

Frozen selection50 fr2 не містить ambiguous GT duplicate 1311868229.576 (rows 10858/10859). Повний `read_tum_trajectory` вимагає strictly increasing timestamps; windowed reference Y-05 і disclosed selection failure N-05 — різні записані procedures. Не deduplicate/average GT і не змінювати tolerance заради проходження run.
