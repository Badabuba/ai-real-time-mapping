# Real-time Mapping with Foundation Models

Навчальний дослідницький проєкт з побудови карти невідомого середовища за монокулярною RGB-послідовністю. Ми порівнюємо класичний feature-based SLAM із гібридним pipeline, у якому SLAM оцінює рух камери та sparse map, а foundation model прогнозує dense geometry/depth. Обидва представлення вирівнюються та об'єднуються в узгоджену 3D-карту.

> Статус на 25 жовтня 2026: WP1/WP2 інтегровані; WP3/WP4 alignment/fusion та one-config offline pipeline перевірені на real 200-frame TUM smoke (clean 4952e37). Є metric cloud, B0/B1/P1 comparisons та ATE/RPE/map reports. Full held-out benchmark і demo залишаються спільною роботою. [Результати](docs/WP3_WP4_COMPLETION.md), [handoff / remaining tasks](docs/YULIAN_HANDOFF.md).

## Дослідницьке питання

Чи може додавання foundation-моделі геометрії/метричної глибини до класичного монокулярного SLAM підвищити повноту й точність 3D-карти без неприйнятної втрати швидкості та стабільності трекінгу?

## Мінімальний результат (MVP)

1. Відтворюваний monocular baseline на pySLAM: траєкторія камери та sparse point cloud.
2. Dense depth/point cloud для тих самих кадрів від однієї обраної foundation model.
3. Вирівнювання sparse і dense представлень (scale або Sim(3), залежно від доступних координат).
4. Інтегрована point cloud щонайменше для однієї послідовності TUM RGB-D.
5. Порівняння baseline і запропонованого pipeline за точністю, швидкістю та пам'яттю.

## Pipeline

```text
RGB frames + intrinsics
        |
        +--> pySLAM ----------------> camera poses + sparse landmarks
        |
        +--> depth/geometry model --> dense depth / point maps + confidence
                                           |
sparse landmarks + shared pixels ----------+
        |
robust scale or Sim(3) alignment
        |
confidence filtering + multi-view fusion
        |
dense metric map + trajectory + benchmark report
```

Важливе уточнення: монокулярний SLAM сам по собі відновлює геометрію лише з точністю до невідомого масштабу. Якщо dense і sparse точки побудовані з тих самих поз та пікселів, спочатку оцінюємо robust scalar scale. Якщо вони приходять із різних систем координат, оцінюємо Sim(3) (scale, rotation, translation); ICP використовуємо лише як локальне уточнення після грубого вирівнювання.

## Початковий технічний вибір

- **Baseline:** [pySLAM](https://github.com/luigifreda/pyslam), monocular mode. Він уже містить засоби оцінювання SLAM та експорту карти, але залишається зовнішньою залежністю; код проєкту не копіюємо без перевірки GPLv3-сумісності.
- **Основний dense-кандидат:** [Depth Anything 3 Metric](https://github.com/ByteDance-Seed/Depth-Anything-3) як пряме джерело metric depth. Остаточний вибір робимо лише після однакового smoke benchmark.
- **Контрольний кандидат:** [UniDepth V2](https://github.com/lpiccinelli-eth/UniDepth) для незалежної перевірки metric depth.
- **Geometry-кандидат:** [DUSt3R](https://github.com/naver/dust3r) або [VGGT](https://github.com/facebookresearch/vggt) як альтернатива, що спільно оцінює багатовидову геометрію/пози. Через більшу складність і вимоги до GPU це не є обов'язковою частиною MVP.
- **Primary dataset:** [TUM RGB-D](https://cvg.cit.tum.de/data/datasets/rgbd-dataset) — RGB подаємо системі, depth і ground-truth trajectory використовуємо тільки для оцінювання.

Обґрунтування та критерії відсікання моделей описані в [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md).

## Метрики

| Група | Основні метрики | Навіщо |
|---|---|---|
| Траєкторія | ATE RMSE, RPE translation/rotation | точність і дрейф SLAM |
| Метрична глибина | AbsRel, RMSE, δ1 | чи модель справді дає коректний scale |
| Геометрія карти | accuracy, completeness, Chamfer-L1, F-score@τ | якість та повнота 3D-карти |
| Стабільність | tracking success rate, lost frames | надійність pipeline |
| Продуктивність | median/p95 latency, FPS, peak VRAM/RAM | перевірка вимоги real-time |

Для monocular trajectory звітуємо два режими: Sim(3)-aligned ATE (якість руху без урахування масштабу) і metric/SE(3)-aligned ATE після нашого scale recovery. Не можна показувати тільки Sim(3)-aligned результат і водночас стверджувати, що відновлено метричний масштаб.

## Репозиторій

```text
.
├── configs/                 # конфігурації dataset/model/experiment
├── data/                    # інструкція; датасети не комітяться
├── docs/                    # дизайн, експерименти, статус, проміжна перевірка
├── results/                 # формат малих відтворюваних результатів
├── scripts/                 # CLI entry points
├── src/rt_mapping/          # contracts, adapters, alignment, fusion, evaluation
└── tests/                   # unit та integration tests
```

## Документи

- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — структурований опис початкового proposal та уточнення scope.
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) — перевірений WP1 setup, hardware і відомі dependency issues.
- [PLAN.md](PLAN.md) — scope, ролі, календар, ризики, Plan B і критерії готовності.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — контракти модулів та alignment design.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) — датасети, протокол, метрики й матриця експериментів.
- [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md) — обґрунтування моделей і правила вибору.
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — чесний журнал фактичного прогресу та внеску Назара (бос), Ярополка (дубєнь) і Юліана (піндос).
- [docs/INTEGRATION_STATUS.md](docs/INTEGRATION_STATUS.md) — що вже інтегровано з WP1/WP2, що лишається кожному owner та які artifacts передати Юліану.
- [docs/YULIAN_HANDOFF.md](docs/YULIAN_HANDOFF.md) — аудит, WP3/WP4 реалізація, команди та remaining tasks Юліана.
- [docs/INTERIM_REVIEW.md](docs/INTERIM_REVIEW.md) — чекліст на 15 балів і каркас короткої презентації.
- [CONTRIBUTING.md](CONTRIBUTING.md) — Git workflow та Definition of Done.

## Перший відтворюваний WP1 запуск

WP2 (Ярополк): [native setup і запуск](docs/WP2_SETUP.md) перевірено на macOS arm64. [Sparse handoff](docs/WP2_SPARSE_EXPORT.md): 200 frames, 197 final poses, 0 LOST, 1,205 landmarks / 19 keyframes / 7,595 observations; [звіт](results/summaries/wp2_sparse_fr1_xyz_200_20261023.json), [preview](results/plots/wp2_sparse_map.png). Залишаються normalized all-frame states/timing, automated recorded ATE/RPE та ширший benchmark. PLY/NPZ/CSV повного run локальні, не передаються через Git.

Після setup з [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md):

```powershell
.venv\Scripts\python.exe scripts\check_wp1_environment.py
.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 20 --process-res 384
```

Кожен запуск пише новий `results/runs/<run_id>/` (run.json, predictions, metrics.json, timing.json; див. docs/EXPERIMENTS.md §5.1) і не перезаписує наявні runs.

Historical WP1 [20-frame result](results/summaries/wp1_da3metric_tum_fr1_xyz_20.json) збережено. Новий clean [200-frame full-pipeline summary](results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json) включає matching SLAM/DA3, real scale, fused map і controls. Великі artifacts залишаються поза Git.

## CPU alignment/fusion smoke (Юліан)

У Python environment із встановленими project dependencies:

```powershell
python -m pytest tests -q
python scripts/run_alignment_smoke.py
```

Synthetic scale 2.5 відновлюється з outliers; команда створює metric PLY/NPZ, keyframe trajectory, residual diagnostics і run.json. Для plots: встановити `.[plots]` та додати `--plot`. Це correctness fixture, не TUM benchmark. Real запуск `run_offline_mapping.py` та input runs описані у [handoff](docs/YULIAN_HANDOFF.md).

## Реальний one-config pipeline

Після [Linux/Docker setup](docs/WP2_LINUX_CONTAINER.md), CUDA environment та cached inputs:

```powershell
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id new_unique_real_run
```

Recorded smoke: 22 keyframes, 72,887 metric voxels; [map](results/plots/yulian_tum_map.png), [residuals](results/plots/yulian_tum_residuals.png), [comparison](results/plots/yulian_tum_comparison.png). Global scale покращив trajectory ATE, але map accuracy/completeness мають tradeoff. [Числа та scope](docs/WP3_WP4_COMPLETION.md). Це offline smoke, не real-time або full held-out study.
