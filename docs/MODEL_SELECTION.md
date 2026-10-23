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

Це не остаточний «переможець». Назар (бос) оновлює цей розділ таблицею результатів і ADR після spike; commit із числовими доказами фіксує вибір.

## 8. DA3METRIC-LARGE adapter (C5): перевірені факти

Перевірено в коді `depth_anything_3` (git `3d835ec1`) і на локальному checkpoint; не є результатом selection spike.

- Checkpoint: `depth-anything/DA3METRIC-LARGE`, HF revision `4010e39f3634a45bc60553321fb49fb760bd594e`, файл `model.safetensors`, SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776`. Adapter визначає файл і hash із локального cache під час завантаження і пише їх у run.json.
- dtype: ваги float32; `DepthAnything3.forward` сам вмикає autocast bfloat16 (якщо GPU підтримує), інакше float16. Тому `--dtype` приймає лише bfloat16/float16 і має збігатися з тим, що вибере DA3; float32 inference без обходу API неможливий (поза C5).
- Config має лише backbone + DPT head, без camera encoder/decoder: input intrinsics ігноруються, API не повертає intrinsics, confidence (`conf = None`) і `is_metric`. Metric depth = raw · mean(fx, fy) / 300 з K_processed (DA3 README).
- Preprocessing `upper_bound_resize`: longest side → process_res, потім кожна сторона → найближче кратне 14 (два `cv2.resize`). K_processed — див. ARCHITECTURE §3 і D008.
- Hard gates із §4 для 20 кадрів fr1/xyz: NaN/Inf немає, shape стабільна (294×378), K_processed коректний, latency і peak VRAM збираються (run `c5_parity_f20_20261021`). На ~0.01% pixels окремих кадрів inference недетермінований між запусками (PROJECT_STATUS, failure log).
