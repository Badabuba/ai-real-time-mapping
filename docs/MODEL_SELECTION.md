# Вибір моделей і baseline

Документ описує рішення до benchmark. Таблиця не містить вигаданих результатів: фактичні latency, VRAM і accuracy треба внести після однакового запуску на hardware команди.

## 1. Що саме ми вибираємо

Для MVP потрібні два різні компоненти:

1. **Pose/sparse baseline:** класичний monocular SLAM.
2. **Dense geometry:** одна foundation model, яка повертає metric depth або багатовидову point map.

pySLAM не є конкурентом depth model: він дає baseline trajectory/sparse map і може бути контейнером інтеграції. Proposed method має бути описаний як конкретна комбінація, а не просто «pySLAM + AI».

## 2. Baseline: pySLAM

Причини вибору:

- підтримує monocular, stereo і RGB-D та набір класичних/сучасних features;
- має evaluation та map export сценарії;
- відповідає початковому розподілу роботи команди;
- дозволяє отримати baseline швидше, ніж писати SLAM з нуля.

Ризики:

- Python/C++/CUDA/OpenGL залежності можуть ускладнити setup, особливо на Windows;
- проєкт має GPLv3, а вкладені компоненти можуть мати власні ліцензії;
- велика кількість опцій робить легкою нечесну зміну baseline між експериментами.

Рішення: зафіксувати upstream revision, environment і один baseline config; не vendor-ити код/ваги без окремої перевірки license.

Офіційне джерело: https://github.com/luigifreda/pyslam

## 3. Dense candidates

| Candidate | Вихід | Сильна сторона для проєкту | Основний ризик | Роль |
|---|---|---|---|---|
| Depth Anything 3 Metric | metric depth; залежно від variant — multi-view geometry | прямий зв'язок із metric scale; актуальний офіційний codebase | hardware/variant complexity, треба чітко зафіксувати checkpoint | primary candidate |
| UniDepth V2 | single-image metric depth + confidence/camera support | простий modular fallback, confidence корисний для filtering | single-view temporal inconsistency | fallback/control |
| DUSt3R | pair/multi-view point maps і camera geometry | природний міст між двома/кількома views без класичного matching | global alignment і runtime; окрема система координат | optional geometry comparison |
| MASt3R | 3D matching + metric pointmaps | сильні correspondences для alignment | додатковий scope і залежність від DUSt3R | stretch only |
| VGGT | cameras, depth, point maps, tracks із багатьох views | один feed-forward geometry stack | велика модель/VRAM; pose output може дублювати SLAM | optional P2 |

Офіційні джерела:

- https://github.com/ByteDance-Seed/Depth-Anything-3
- https://github.com/lpiccinelli-eth/UniDepth
- https://github.com/naver/dust3r
- https://github.com/naver/mast3r
- https://github.com/facebookresearch/vggt

## 4. Hard gates

Кандидат не інтегруємо, якщо хоча б одна умова не виконана:

- офіційний checkpoint доступний команді та дозволений для academic use;
- inference запускається на доступному GPU без ручної зміни source;
- output semantics і units можна однозначно задокументувати;
- для 20 послідовних кадрів немає NaN/Inf або silent shape changes;
- preprocessing повертає коректний K_processed;
- можна зібрати latency й peak memory;
- залежність не змушує публікувати несумісний код або ваги.

## 5. Selection scorecard

На одному frozen selection set кожен життєздатний кандидат отримує 0–5 за кожним пунктом:

| Критерій | Вага | Як вимірюємо |
|---|---:|---|
| depth/geometry quality | 35% | AbsRel, δ1, valid pixels; для multi-view також consistency |
| runtime | 25% | median та p95 inference latency після warm-up |
| memory | 15% | peak VRAM на однаковій resolution/batch |
| integration reliability | 15% | setup, stable shapes/units, confidence, export complexity |
| license/reproducibility | 10% | official source, pinned checkpoint, redistribution constraints |

Підсумковий score = weighted mean, але hard gates мають пріоритет. Якщо найточніша модель не вкладається в ресурсний бюджет, вона стає offline upper bound, а не primary model.

## 6. Однаковий spike protocol

- data: перші 50 валідних кадрів frozen development sequence;
- однаковий RGB resolution або documented native mode;
- batch size 1;
- 10 warm-up calls, потім timing кожного кадру з GPU synchronization;
- quality рахується тільки на валідних TUM depth pixels;
- логуються model revision, checkpoint hash/name, dtype, GPU, driver/CUDA, preprocessing;
- окремо зберігаються cold-start time і steady-state latency.

## 7. Початкове рішення

До отримання чисел робоча гіпотеза така:

- primary P1: pySLAM poses + Depth Anything 3 Metric depth + robust scale validation + point-cloud fusion;
- fallback: pySLAM poses + UniDepth V2;
- optional P2: DUSt3R або VGGT як окремий end-to-end geometry comparison;
- MASt3R і semantics не входять у MVP.

Це не остаточний «переможець». Назар оновлює цей розділ таблицею результатів і ADR після spike; commit із числовими доказами фіксує вибір.
