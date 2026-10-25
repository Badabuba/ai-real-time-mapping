# N-06: held-out benchmark (fr3/long_office_household)

Назар (бос), 25 жовтня 2026. Chunk N-06 з `docs/TWO_PERSON_COMPLETION_PLAN.md`; frozen protocol — `docs/BENCHMARK_PROTOCOL.md`, `configs/benchmark_frozen.json`.

**Статус: disclosed failure.** Єдиний held-out run зупинився на WP2 preflight до першого SLAM frame. Held-out metrics і performance table відсутні. Нічого не tuned; rerun — лише за D-5 після fix власника коду.

## 1. Freeze до доступу

| Item | Значення |
|---|---|
| Freeze | `configs/benchmark_frozen.json`, commit `4021a02`, merged PR #25 → `develop` `847c662` |
| N-05 | PR #24, merge `ef5e682` |
| N-06 branch | `feature/nazar-heldout-benchmark` з `847c662` |
| Config | `configs/pipeline.nazar.heldout.json` = `benchmark_frozen.json` → `heldout.pipeline_config` (scripted diff 0 рядків; `tests/test_benchmark_frozen.py`) |
| Run commit | clean `e561d8c` (містить freeze) |
| Перший доступ до fr3 | копіювання fr3 у runtime clone після merge `847c662` |

## 2. Run

| Run ID | Commit | Status | Причина |
|---|---|---|---|
| `nazar_n06_heldout2488_da3_e561d8c_01` | `e561d8c` | **failed** | `pipeline_failed: slam adapter exited 2`; `logs/slam.log`: `Rejected: groundtruth time range does not cover associated RGB frames` |

Запущено один раз (start 2026-10-25T19:32:36Z, failure через ~387 s, з них preflight hashing). SLAM frames 0, DA3 inference 0, alignment/fusion/comparison не виконувались, B0 evaluation неможлива (немає SLAM stage). Evidence: `results/summaries/nazar_n06_heldout2488_e561d8c.json`.

## 3. Діагностика

- Check: `src/rt_mapping/slam/setup.py:155` (Track Y; рядок з `24b16e2`, збережений Y-04) вимагає, щоб GT time range покривав усі associated RGB frames.
- Official fr3 `groundtruth.txt` починається о 1341847980.79 s, перший RGB frame — 1341847980.722988 s: 3 з 2488 frames раніше за GT (після кінця — 0). Лише 2 frames не мають GT pose у межах 20 ms.
- B0 SLAM не використовує GT; merged policy PR #21 уже виключає keyframes без GT pose і записує coverage. Тому preflight відкидає валідний official recording ширше, ніж потрібно для evaluation. Це **гіпотеза щодо правильного fix**, не змінений код.
- Y-04 held-out real-data preflight був explicitly skipped (input недоступний на машині Ярополка), тому до IC3 це не виявилось.
- Fix належить Track Y (`slam/`); Track N не редагує SLAM code (plan §3). Тут нічого не змінено.

GT access: preflight прочитав GT timestamps; діагностика порівняла лише timestamps GT/RGB. Жодна GT pose/depth не використана для metric.

## 4. Performance і real-time verdict

Held-out performance table недоступна: жоден stage не виконався. Verdict за D-7: **offline**. Підстава — N-05 dev components уже перевищують 33.3 ms budget (`Slam.track` warm p95 2312 ms; DA3 504 p95 97.9 ms на RTX 5070 Laptop, 640×480 input, 30 Hz), а pipeline послідовний. Held-out p95/FPS не заявляються.

## 5. Наступний крок (D-5)

1. Ярополк: focused fix PR у `slam/setup.py` (наприклад, дозволити часткове GT coverage з явним звітом, як для duplicate timestamps у `7492ffa`), з regression test; held-out preflight на реальних даних.
2. Після merge: новий branch від `develop`, той самий frozen config (scripted diff порожній), новий run ID `nazar_n06_heldout2488_da3_<sha7>_01` з commit, що містить fix; B0 evaluation `nazar_n06_heldout2488_b0eval_<sha7>_01`; performance table. Обидва runs звітуються. Параметри не змінюються.

## 6. Disclosures

- Цей run: failed на preflight (вище).
- Superseded runner `wp2_heldout2488_4484fd7` (clean `4484fd7`) failed в upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`); без trajectory і metrics; нічого не tuned.
- Held-out результати нічого не вибирали і не змінювали. F-N1/F-N2 не розпочато.
