# Статус і журнал прогресу

Це single source of truth для відповідей «що зроблено?», «хто робив?» і «що не вийшло?». Оновлювати наприкінці кожного робочого session/PR. Planned не дорівнює done.

Останнє оновлення: 20 жовтня 2026.

## 1. Snapshot

| Deliverable | Статус | Evidence | Owner | Наступний крок |
|---|---|---|---|---|
| GitHub repository | done | origin налаштований; initial commit існує | команда | надати викладачу доступ, якщо repo private |
| Project scope / architecture / plan | draft done | README, PLAN, docs/* | Назар (бос) | Ярополк (дубєнь) і Юліан (піндос) переглядають і погоджують |
| Dataset downloaded/frozen | smoke subset done | TUM fr1/xyz; SHA-256 у docs/ENVIRONMENT.md | Назар (бос) | заморозити ширший evaluation split після smoke |
| pySLAM baseline | planned | — | Ярополк (дубєнь) | environment + smoke run |
| WP1 environment + DA3 import | done | docs/ENVIRONMENT.md; scripts/check_wp1_environment.py | Назар (бос) | model-load та one-frame inference smoke |
| Dense model inference | smoke done | scripts/run_tum_da3_metric.py; results/summaries/wp1_da3metric_tum_fr1_xyz_20.json | Назар (бос) | selection split із часовим stride + fallback model |
| Synthetic alignment test | planned | — | Юліан (піндос) | scale + Sim(3) unit tests |
| Real sparse–dense alignment | planned | — | Юліан (піндос) | потребує WP1 і WP2 artifacts |
| End-to-end pipeline | planned | — | Назар (бос) + Ярополк (дубєнь) + Юліан (піндос) | після окремих smoke runs |
| Quantitative benchmark | planned | — | Назар (бос) + Ярополк (дубєнь) + Юліан (піндос) | freeze protocol, run B0/B1/P1 |
| Demo | planned | — | команда | після стабільного end-to-end run |
| Interim presentation | planned | — | команда | створити з evidence, не з обіцянок |

## 2. Що з proposal вже виконано

- Репозиторій створений і підключений до GitHub.
- Сформульовано MVP, modular pipeline, data contracts і coordinate conventions.
- Визначено baseline, candidate models, primary dataset, метрики та experiment matrix.
- Роботу розкладено між Назаром (бос), Ярополком (дубєнь) і Юліаном (піндос) з integration gates.
- Завантажено й перевірено TUM `freiburg1_xyz`; запущено DA3METRIC-LARGE на 20 асоційованих RGB-D кадрах.
- Перший smoke результат: AbsRel 0.1051, RMSE 0.1752 m, δ1 0.9675; warm mean 0.098 s/frame (10.2 FPS), peak VRAM 1.425 GB.

Ще **не виконано**: повний model-selection benchmark, запуск pySLAM, alignment, fusion, end-to-end benchmark і demo. 20 послідовних кадрів є smoke-перевіркою, а не достатнім evaluation split; 10.2 warm FPS не дає підстав називати весь pipeline real-time.

## 3. Внесок учасників

Додавати тільки merged/reproducible work. Розподілене завдання ще не є фактичним внеском.

| Учасник | Фактичний внесок | Evidence (PR/commit/file/run) | Дата |
|---|---|---|---|
| Назар (бос) | постановка вимог і координування; documentation scaffold; WP1 Windows/CUDA environment; TUM fr1/xyz data verification; DA3 Metric 20-frame smoke benchmark | README, PLAN, docs/*, scripts/run_tum_da3_metric.py, results/summaries/* | 2026-10-20 |
| Ярополк (дубєнь) | розподілено WP2; фактичний технічний внесок ще не записаний | — | — |
| Юліан (піндос) | розподілено WP3; фактичний технічний внесок ще не записаний | — | — |

Після review записати, хто перевірив і змінив кожне рішення. Авторство технічних результатів підтверджується PR/commit/run, а не лише цією таблицею.

## 4. Failure / blocker log

| Дата | Owner | Симптом / команда | Evidence | Причина або гіпотеза | Що вже спробували | Рішення / наступний експеримент | Статус |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | Назар (бос) | перший synthetic runner падав під час читання `prediction.is_metric` | local traceback; виправлення у runner | DA3 повертає auto-created empty Addict Dict для відсутнього поля | додано safe scalar conversion | пройдено synthetic і real TUM run | resolved |
| 2026-10-20 | Назар (бос) | DA3 standalone metric output не повернув intrinsics | run manifest/API inspection | API додає processed K до prediction лише в окремих pose-alignment умовах | K передано в model; transformed K отримано власним DA3 preprocessor | використовувати processed mean focal у формулі DA3 | resolved |
| 2026-10-20 | Назар (бос) | `prediction.conf` дорівнює None | first TUM frame traceback | цей checkpoint не повертає confidence map | fallback mask із одиниць | confidence ablation відкласти або взяти іншу confidence proxy | resolved with limitation |

Правило: якщо причина не доведена, писати «гіпотеза», а не подавати її як факт. Log/trace зберігати текстом або посиланням на issue; screenshot alone недостатній.

## 5. Відкриті організаційні питання

- [x] команда: Назар (бос), Ярополк (дубєнь), Юліан (піндос);
- [ ] дата та точний часовий ліміт проміжної презентації;
- [ ] дата фінального дедлайну;
- [ ] hardware кожного учасника (OS, GPU, VRAM, RAM);
- [ ] чи GitHub repo public/private і чи має викладач доступ;
- [ ] допустима ліцензія фінального коду;
- [ ] хто координує інтеграцію та release/tag;
- [ ] чи дозволено використовувати WSL2/remote GPU/Colab.

## 6. Weekly update template

```markdown
### YYYY-MM-DD — week N

- Done (з PR/run links):
- In progress:
- Blocked (симптом + evidence):
- Decision made:
- Metrics changed:
- Next week owner-by-owner:
- Scope/deadline risk:
```

## 7. Decision log

| ID | Дата | Рішення | Статус | Evidence / умова перегляду |
|---|---|---|---|---|
| D001 | 2026-10-20 | TUM RGB-D — primary dataset | proposed | підтвердити доступність і smoke run |
| D002 | 2026-10-20 | pySLAM monocular — classical baseline | proposed | переглянути лише після documented setup failure |
| D003 | 2026-10-20 | Depth Anything 3 Metric — primary dense candidate; UniDepth V2 — fallback | proposed | selection spike |
| D004 | 2026-10-20 | scalar scale для shared-frame MVP; Sim(3) для independent frames; ICP only refinement | proposed | synthetic і real residual tests |
| D005 | 2026-10-20 | semantics поза MVP | accepted | повернути після benchmark P1 |
| D006 | 2026-10-20 | WP1: Windows + uv Python 3.11 + PyTorch 2.11 cu128 | accepted | CUDA tensor та DA3 import smoke пройдені на RTX 5070 8 GB |
| D007 | 2026-10-20 | перший checkpoint: DA3METRIC-LARGE, process_res 384, batch 1 | accepted for WP1 smoke | 20 TUM frames: AbsRel 0.1051, δ1 0.9675, peak VRAM 1.425 GB |
