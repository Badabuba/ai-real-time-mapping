# Підготовка до проміжної перевірки (15 балів)

Документ перетворює rubric на список доказів. Слайди створюємо тільки після появи baseline artifacts і чисел. Repo без презентації або презентація без repo означає 0 за умовами курсу.

## 1. Rubric → evidence

### Технічна частина — 5 балів

| Критерій | Що показати | Evidence у repo | Готово? |
|---|---|---|---|
| GitHub-репозиторій | URL, структура, останній release/tag | README, commit history | repo є; release ще немає |
| Baseline | pySLAM config, sequence, trajectory/sparse map, одна команда | config + run manifest + artifact | ні |
| Метрики | таблиця з units/alignment mode; ATE/RPE + speed, за можливості depth/map | metrics.json/CSV + plot script | протокол є; чисел немає |
| Обґрунтованість моделей | candidates, hard gates, однаковий spike, license/hardware trade-off | MODEL_SELECTION.md + selection results | дизайн є; spike немає |
| Pipeline | схема входів/виходів і що реально працює виділено кольором/статусом | ARCHITECTURE.md + demo artifact | дизайн є; реалізації немає |

### Прогрес — 5 балів

| Питання | Доказ |
|---|---|
| Що з proposal виконано? | status table: done/in progress/blocked/planned + посилання |
| Хто що робив? | contribution table для Назара, Ярополка і Юліана з PR/commit/run, а не лише майбутні ролі |
| Що не вийшло? | 1–3 конкретні failures із командою/log/симптомом |
| Чому не вийшло? | root cause або чітко позначена гіпотеза + перевірка |
| Чи зрозуміло з презентації? | один progress slide; однакова легенда статусів |

### Подальший план — 5 балів

| Критерій | Доказ |
|---|---|
| Чіткий реалістичний план | календар із owner, deliverable, gate і buffer |
| Дизайн експериментів | B0/B1/P1, frozen splits, метрики, ablations, hardware |
| Plan B | trigger → simplified method → що все одно вимірюємо |
| Якщо все вийде | ordered stretch goals без розмивання MVP |

## 2. Каркас презентації

Рекомендовано 8 основних слайдів; appendix не презентується без питання.

1. **Проблема й research question** — один абзац, один очікуваний результат.
2. **Pipeline** — baseline path і foundation path; кольором показати done/in progress/planned.
3. **Baseline** — dataset/config, sparse map/trajectory, ATE/RPE/FPS. Потрібні реальні числа.
4. **Dense model selection** — candidates, критерії, виміряний trade-off і остаточний вибір.
5. **Поточний результат** — aligned/fused visualization + quantitative diagnostics; якщо інтеграції ще немає, чесно показати окремі модулі.
6. **Прогрес і внесок** — proposal → status; Назар/Ярополк/Юліан → evidence.
7. **Що не вийшло / lessons** — симптом, причина/гіпотеза, вже спробоване, рішення.
8. **План до фіналу** — календар, experiment matrix, Plan B, stretch goal.

Appendix: metric definitions, additional qualitative examples, environment/license table, detailed failure logs.

## 3. Таймінг

Точний ліміт ще невідомий. Після отримання позначити його T. Планувати spoken content на 0.8–0.85T, а не рівно T, тому що кожна додаткова хвилина коштує 1 бал.

Орієнтовний розподіл:

- проблема + pipeline: 20%;
- baseline + models + current result: 45%;
- progress/failures: 15%;
- plan/Plan B: 15%;
- buffer: 5% плюс свідомо скорочений текст.

Провести щонайменше дві репетиції з таймером. Усі троє мають говорити, бо відсутній учасник отримує 0.

## 4. Правила чесного слайда

- Planned diagram не позначати як implemented.
- Скриншот без sequence/config/metric не є benchmark.
- Qualitative «виглядає краще» не замінює accuracy/completeness.
- Sim(3)-aligned monocular ATE не доводить metric scale recovery.
- Oracle B1 завжди підписувати як oracle/control.
- FPS завжди супроводжувати hardware, resolution і тим, що входило в timing.
- Failure не приховувати: він дає бали за прогрес, якщо є evidence і обґрунтований next step.

## 5. За 48 годин до здачі

- [ ] викладач має доступ до GitHub;
- [ ] презентація створена й перевірена на іншому пристрої;
- [ ] посилання/файл здані до дедлайну (прострочення = -50%);
- [ ] commit/tag у slides відповідає repo;
- [ ] baseline command відтворено з чистого environment або другим учасником;
- [ ] усі числа мають units, dataset, config й alignment mode;
- [ ] внесок Назара, Ярополка і Юліана підтверджений evidence;
- [ ] known failures і Plan B сформульовані конкретно;
- [ ] live demo має prerecorded fallback;
- [ ] кожен учасник підтвердив присутність;
- [ ] репетиція має запас часу.

## 6. Мінімум до проміжної перевірки

Якщо часу мало, порядок незмінний:

1. B0 baseline з ATE/RPE/timing;
2. один dense inference artifact + depth metrics;
3. synthetic alignment test і хоча б одна реальна aligned pair/cloud;
4. pipeline diagram із чесними статусами;
5. contribution/failure/next-plan slides;
6. стабільний prerecorded demo замість ризикового live run.
