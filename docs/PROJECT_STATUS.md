# Статус і журнал прогресу

Це single source of truth для відповідей «що зроблено?», «хто робив?» і «що не вийшло?». Оновлювати наприкінці кожного робочого session/PR. Planned не дорівнює done.

Останнє оновлення: 20 жовтня 2026.

## 1. Snapshot

| Deliverable | Статус | Evidence | Owner | Наступний крок |
|---|---|---|---|---|
| GitHub repository | done | origin налаштований; initial commit існує | команда | надати викладачу доступ, якщо repo private |
| Project scope / architecture / plan | draft done | README, PLAN, docs/* | Назар (бос) | Ярополк (дубєнь) і Юліан (піндос) переглядають і погоджують |
| Dataset downloaded/frozen | planned | — | Назар (бос) | підтвердити sequences, checksums, storage |
| pySLAM baseline | planned | — | Ярополк (дубєнь) | environment + smoke run |
| Dense model inference | planned | — | Назар (бос) | two-candidate spike |
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

Ще **не виконано**: завантаження датасету, inference, запуск pySLAM, alignment, fusion, benchmark і demo. Поки немає чисел, скриншотів карти або заяв про real-time.

## 3. Внесок учасників

Додавати тільки merged/reproducible work. Розподілене завдання ще не є фактичним внеском.

| Учасник | Фактичний внесок | Evidence (PR/commit/file/run) | Дата |
|---|---|---|---|
| Назар (бос) | постановка вимог і координування; стартовий documentation scaffold підготовлено з Codex та передано команді на review | README, PLAN, docs/* | 2026-10-20 |
| Ярополк (дубєнь) | розподілено WP2; фактичний технічний внесок ще не записаний | — | — |
| Юліан (піндос) | розподілено WP3; фактичний технічний внесок ще не записаний | — | — |

Після review записати, хто перевірив і змінив кожне рішення. Авторство технічних результатів підтверджується PR/commit/run, а не лише цією таблицею.

## 4. Failure / blocker log

Технічних запусків ще не було, тому технічних failures не зафіксовано. Відсутність спроби не записуємо як «не вийшло».

| Дата | Owner | Симптом / команда | Evidence | Причина або гіпотеза | Що вже спробували | Рішення / наступний експеримент | Статус |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — |

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
