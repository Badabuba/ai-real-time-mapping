# Real-time Mapping with Foundation Models

Навчальний дослідницький проєкт з побудови карти невідомого середовища за монокулярною RGB-послідовністю. Ми порівнюємо класичний feature-based SLAM із гібридним pipeline, у якому SLAM оцінює рух камери та sparse map, а foundation model прогнозує dense geometry/depth. Обидва представлення вирівнюються та об'єднуються в узгоджену 3D-карту.

> Статус на 20 жовтня 2026: підготовлено дизайн системи й експериментів; WP1 має відтворюваний DA3 Metric smoke benchmark на 20 TUM кадрах. pySLAM baseline, alignment та end-to-end pipeline ще не реалізовані.

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
├── scripts/                 # майбутні CLI entry points
├── src/rt_mapping/          # майбутні модулі pipeline
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
- [docs/INTERIM_REVIEW.md](docs/INTERIM_REVIEW.md) — чекліст на 15 балів і каркас короткої презентації.
- [CONTRIBUTING.md](CONTRIBUTING.md) — Git workflow та Definition of Done.

## Перший відтворюваний WP1 запуск

Після setup з [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md):

```powershell
.venv\Scripts\python.exe scripts\check_wp1_environment.py
.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 20 --process-res 384
```

Короткий versioned результат є в [results/summaries/wp1_da3metric_tum_fr1_xyz_20.json](results/summaries/wp1_da3metric_tum_fr1_xyz_20.json); великі per-frame artifacts залишаються поза Git. Наступний integration milestone — та сама TUM sequence проходить через pySLAM baseline та offline alignment.
