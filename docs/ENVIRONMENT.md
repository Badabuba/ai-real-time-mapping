# WP1 environment

Перевірено 20 жовтня 2026 на машині Назара (бос).

## Hardware і система

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

## Перевірений stack

| Компонент | Версія |
|---|---|
| Python | 3.11.16, isolated .venv через uv |
| PyTorch | 2.11.0+cu128 |
| torchvision | 0.26.0+cu128 |
| xformers | 0.0.35 |
| Depth Anything 3 | upstream commit 3d835ec1a5802d64a8b8b15f817a1ab54809bfe4 |
| addict | 2.4.0 |

CUDA Toolkit/nvcc у системі не встановлений. Для prebuilt PyTorch wheel це не потрібно: CUDA 12.8 runtime входить до wheel. GPU smoke test пройшов: torch.cuda.is_available() == True та matrix multiplication виконався на RTX 5070.

## Відтворення environment

PowerShell із кореня repository:

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements\wp1-da3.txt
.venv\Scripts\python.exe scripts\check_wp1_environment.py
```

## Тести

CPU-тести пакета `src/rt_mapping` (GPU і датасет не потрібні). pytest 9.1.1 встановлено 21 жовтня 2026:

```powershell
uv pip install --python .venv\Scripts\python.exe pytest
.venv\Scripts\python.exe -m pytest tests -q
```

`pyproject.toml` додає `src` у `pythonpath` для pytest, тому editable install пакета поки не потрібен.

## Відомі особливості

1. Системний Python 3.14 не використовуємо: офіційний DA3 package декларує Python <=3.13.
2. Upstream commit використовує package addict, але не декларує його в dependencies. Тому він явно pinned у requirements.
3. Warning про відсутність gsplat очікуваний і не блокує monocular metric-depth inference. Не встановлюємо Gaussian head до завершення MVP.
4. Перший import PyTorch/DA3 на Windows може тривати понад хвилину через завантаження великих CUDA DLL; наступні процеси теж мають cold-start overhead, який слід вимірювати окремо.
5. Для RTX 5070/Blackwell потрібна CUDA wheel 12.8 або новіша; перевірений варіант — cu128.

## Обрана модель для першого smoke run

`depth-anything/DA3METRIC-LARGE`: 0.35B parameters, monocular metric-depth checkpoint. Починаємо з batch size 1 і process_res 384 через 8 GB VRAM. Важкий nested checkpoint 1.4B не входить у перший smoke run.

За офіційним DA3 FAQ standalone metric checkpoint потребує перетворення `depth_m = focal_px * raw_depth / 300`. Smoke runner робить це явно, коли API не позначає output як уже метричний, і записує джерело scale в manifest.

## Зафіксований smoke dataset

- Sequence: `rgbd_dataset_freiburg1_xyz` з офіційного TUM RGB-D benchmark.
- Local archive: `data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz.tgz` (не комітиться).
- Size: 448204271 bytes.
- SHA-256: `A0236D97B8C30CD93B653656D2B6C293FF7C982A4130EF2A1A8BEECDB124EF98`.
- RGB calibration: fx=517.3, fy=516.5, cx=318.6, cy=255.3.
- Ground-truth PNG depth factor: 5000 units per meter.

`scripts/run_tum_da3_metric.py` асоціює RGB/depth timestamps у межах 20 ms, передає raw intrinsics у DA3 і використовує DA3 preprocessor для точного перерахунку focal length після resize. Ground-truth depth використовується лише для оцінювання, не подається моделі.
