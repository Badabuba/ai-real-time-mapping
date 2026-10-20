# План проєкту

Оновлено: 20 жовтня 2026
Горизонт плану: 20 жовтня — 30 листопада 2026. Якщо дедлайн курсу інший, змінюємо дати, але зберігаємо порядок залежностей.

## 1. Scope

### In scope для семестрового результату

- монокулярний RGB input із відомими intrinsics;
- класичний visual SLAM baseline;
- inference однієї metric-depth або multi-view geometry foundation model;
- узгодження scale/coordinate frame між sparse та dense geometry;
- інкрементальна або батчева fusion point cloud;
- відтворюване оцінювання accuracy, speed і memory;
- коротке demo на заздалегідь зафіксованій послідовності.

### Не входить у MVP

- тренування foundation model з нуля;
- повноцінний semantic/open-vocabulary map;
- гарантія real-time на будь-якому hardware;
- production mobile deployment;
- одночасна інтеграція всіх DUSt3R/MASt3R/VGGT/Depth Anything/UniDepth.

Семантику та другу foundation model беремо лише після завершення MVP і основного benchmark.

## 2. Work packages і відповідальність

### Команда

| Учасник | Основна зона | Додаткова відповідальність |
|---|---|---|
| **Назар (бос)** | dataset + foundation-model inference | координатор, scope/release, інтеграція model adapter |
| **Ярополк (дубєнь)** | pySLAM baseline + trajectory metrics | reproducible environment, performance logging |
| **Юліан (піндос)** | sparse–dense alignment + fusion | coordinate contracts, synthetic geometry tests |

Owner відповідає за результат і документацію; reviewer має відтворити хоча б smoke run. Назар (бос) координує, але integration PR не вважається готовим без review Ярополка (дубєнь) або Юліана (піндос).

| WP | Owner | Reviewer | Deliverable | Критерій готовності |
|---|---|---|---|---|
| WP0. Репозиторій і протокол | усі; координатор Назар (бос) | Ярополк (дубєнь) | структура, конфіги, frozen sequence list | новий клон відтворює setup |
| WP1. Dataset + foundation inference | Назар (бос) | Юліан (піндос) | loader, inference adapter, depth/point-map export, timing | 20+ кадрів, валідні units/shapes, збережені метрики |
| WP2. SLAM baseline | Ярополк (дубєнь) | Назар (бос) | pySLAM config, trajectory, sparse PLY, timing, ATE/RPE | одна TUM sequence завершується й має числовий звіт |
| WP3. Sparse-dense alignment | Юліан (піндос) | Ярополк (дубєнь) | correspondence builder, robust scale/Sim(3), diagnostics | synthetic test + одна реальна пара з residual plot |
| WP4. Fusion та інтеграція | Юліан (піндос) — integration; Назар (бос) і Ярополк (дубєнь) — adapters | усі | end-to-end command, fused cloud | один конфіг створює всі артефакти без ручних кроків |
| WP5. Benchmark і ablations | Ярополк (дубєнь) — metrics; Назар (бос) — models; Юліан (піндос) — alignment | усі | CSV/JSON + таблиці/графіки | baseline і proposed на тому самому split/hardware |
| WP6. Demo і презентація | усі | усі | demo capture, slides, contribution table | rehearsal вкладається в ліміт часу |

### Конкретний розподіл

**Назар (бос) — foundation model, дані та координація**

- завантажити тільки зафіксований піднабір TUM RGB-D;
- зробити однаковий inference adapter для Depth Anything 3 Metric та одного fallback-кандидата;
- експортувати depth у метрах, confidence mask, intrinsics після resize і latency;
- провести model-selection spike, а не інтегрувати всі моделі;
- описати checkpoint, commit/tag, license, VRAM і preprocessing.

**Ярополк (дубєнь) — SLAM baseline**

- підняти pySLAM в окремому environment/container;
- зафіксувати monocular configuration і seed, де можливо;
- експортувати timestamped poses, sparse landmarks, observation/pixel links і timing;
- порахувати ATE/RPE; зафіксувати tracking failures;
- не змінювати SLAM і модель одночасно до отримання baseline.

**Юліан (піндос) — alignment і fusion**

- спочатку реалізувати synthetic scale/Sim(3) test;
- будувати 2D-3D correspondences через пікселі sparse feature observations;
- оцінювати scale robust median/RANSAC, а для різних coordinate frames — Umeyama Sim(3) + outlier rejection;
- ICP застосовувати тільки після початкового alignment;
- додати confidence/depth-range filtering та voxel downsampling/fusion.

**Спільна робота**

- кожен PR має іншого reviewer;
- кожен учасник веде фактичний внесок у docs/PROJECT_STATUS.md;
- усі троє можуть пояснити pipeline, baseline, метрики й failure modes;
- презентація не приписує людині роботу лише тому, що вона була запланована.

## 3. Перші 72 години

Це kickoff gate, а не повний milestone. Мета — якомога раніше перевірити три найбільші технічні ризики незалежно.

| До коли | Назар (бос) | Ярополк (дубєнь) | Юліан (піндос) | Спільний gate |
|---|---|---|---|---|
| День 1 | записує hardware; фіксує TUM smoke sequence і manifest | записує hardware; обирає Linux/WSL2/Docker шлях для pySLAM | створює synthetic inputs і conventions для scale/Sim(3) | погоджені paths, K, T_wc, units і run_id |
| День 2 | запускає один офіційний metric-depth checkpoint на 20 кадрах | отримує першу trajectory або documented setup blocker | відновлює known scale та Sim(3) у synthetic test | три окремі artifacts або три відтворювані blocker logs |
| День 3 | додає depth sample, timing і environment note | додає trajectory/sparse export, timing і config | додає residual/inlier diagnostics та tests | 30-хвилинний integration review і рішення go/Plan B |

Якщо хтось блокується понад один день, він не продовжує хаотично змінювати dependencies: створює issue з exact command/log, просить reviewer відтворити і переходить до fallback із таблиці ризиків.

## 4. Календар

| Період | Технічна ціль | Доказ у репозиторії | Gate |
|---|---|---|---|
| 20–23 жовтня | setup, hardware report, frozen TUM smoke sequence, interfaces | configs + environment notes | усі бачать однакові timestamps/intrinsics |
| 24–30 жовтня | незалежно: pySLAM baseline, model inference, synthetic alignment | trajectory/sparse map; depth sample; unit tests | кожен із трьох модулів працює окремо |
| 31 жовтня – 6 листопада | alignment на реальних кадрах, перша fused cloud | PLY + alignment JSON + visualization | scale estimate стабільний на вікні кадрів |
| 7–13 листопада | end-to-end offline pipeline, logging, primary benchmark | одна команда/конфіг + result manifest | baseline і proposed порівнювані |
| 14–20 листопада | ablations, performance profiling, Plan B if needed | aggregate CSV + plots + failure log | є чесна відповідь на research question |
| 21–26 листопада | demo hardening, documentation, presentation | tagged release candidate | fresh-clone rehearsal пройдено |
| 27–30 листопада | buffer, rehearsal, submission | release/tag + final slides | вклалися в часовий ліміт |

Критичний шлях: dataset timestamps/intrinsics → SLAM poses та observations → dense predictions → alignment → fusion → benchmark. Model selection і synthetic alignment можна робити паралельно.

## 5. Design експериментів

Головне порівняння:

- **B0:** pySLAM monocular — trajectory + sparse map;
- **B1 (oracle control):** ті самі оцінені poses + ground-truth TUM depth; показує верхню межу fusion за наявності правильного depth;
- **P1:** ті самі оцінені poses + predicted metric depth + robust scale correction/fusion;
- **P2 (optional):** multi-view geometry model (DUSt3R/VGGT) як окремий метод, не як прихована заміна частини P1.

Основні ablations:

1. без scale correction vs один global scale vs sliding-window scale;
2. без confidence filtering vs confidence threshold;
3. every frame vs keyframes;
4. без ICP vs ICP refinement після Sim(3);
5. primary depth model vs один fallback на малому selection split.

Перед основним benchmark заморожуємо sequence list, model checkpoint, preprocessing, thresholds та hardware. Деталі — у docs/EXPERIMENTS.md.

## 6. Ризики, тригери і Plan B

| Ризик | Ранній сигнал | Мітигація | Plan B / мінімальний результат |
|---|---|---|---|
| pySLAM не збирається на Windows | >1 робочого дня без smoke run | WSL2/Linux або офіційний Docker-підхід; зафіксувати помилку | запустити готовий baseline в Linux; власний код лишається platform-neutral |
| Модель не вміщується у VRAM | OOM на 20 кадрах | менша resolution/model, keyframes, fp16/bf16 | UniDepth/менший depth checkpoint; offline inference |
| Metric depth має систематичний scale bias | median scale далеко від 1 або дрейфує | robust window calibration зі sparse landmarks | relative depth + scale від SLAM/GT лише як окремо позначений ablation |
| Замало correspondences | <30 inliers або погане spatial coverage | keyframe aggregation, confidence mask, wider window | align depth-to-sparse per keyframe scalar, без full Sim(3) |
| ICP сходиться до хибного мінімуму | residual росте/transform неприродний | грубий Sim(3), bounds, multi-scale, validation holdout | відмовитися від ICP; використовувати лише robust correspondence alignment |
| Немає real-time | p95 latency перевищує frame budget | keyframe inference, async queue, менша resolution | чесно назвати near-real-time/offline; показати accuracy–latency curve |
| Scope розростається | кілька моделей без end-to-end run | freeze MVP, WIP limit = 1 на людину | прибрати semantics і P2 |

Plan B вважається успішним академічним результатом, якщо команда має відтворюваний baseline, працююче offline вирівнювання, кількісне порівняння та пояснення, чому streaming/real-time вимога не виконана.

## 7. Якщо все працює раніше

Пріоритет розширень:

1. streaming/keyframe scheduling і latency optimization;
2. друга dataset domain (KITTI outdoor) для перевірки generalization;
3. loop-closure-aware reintegration карти;
4. semantic/open-vocabulary labels (DINO/SAM/CLIP) як окремий шар;
5. порівняння з DUSt3R/VGGT або Gaussian/TSDF representation.

Не починаємо пункт N+1, поки результати попереднього не відтворені з чистого clone.

## 8. Definition of Done для проміжної перевірки

- GitHub repo доступний викладачу; default branch не порожня.
- Є commit/tag, який відповідає презентації.
- Baseline реально запускався; у слайдах є команда/config, sequence і числові метрики.
- Є хоча б один end-to-end або clearly bounded partial pipeline artifact.
- Вибір моделі пояснений однаковими критеріями, а не популярністю.
- Таблиця прогресу розрізняє done / in progress / blocked / planned.
- Для кожного failure є симптом, evidence, причина/гіпотеза і наступна дія.
- На слайді contribution видно роботу Назара (бос), Ярополка (дубєнь) і Юліана (піндос) з посиланнями на PR/commit/artifact.
- Є календар, Plan B і next steps after success.
- Репетиція має запас щонайменше 60 секунд до ліміту виступу.
