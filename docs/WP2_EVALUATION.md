# WP2: recorded B0 evaluation і ресурси (Y-02)

Owner / реалізація: Ярополк (WP2/WP5). Base: `origin/develop` = `1f1f979fd01a23525d262086825534d2ca69955f`. Branch: `feature/yaropolk-b0-evaluation`.

Використано незмінений evaluator Юліана `rt_mapping.evaluation.trajectory`. Альтернативні branches / evaluator Назара не переносились. SLAM parameters, upstream source, WP1 та WP3/WP4 code не змінено. Статус для IC1: Y-02 implementation додає final-trajectory B0 evaluation та окремий retained-keyframe результат; all-frame tracking/gaps залишаються Y-03.

## Команди

Після existing native setup із [WP2_SETUP.md](WP2_SETUP.md), з кореня repo. Кожен запуск — новий ID. Обидва CLI мають `--help`; встановлення / downloads не виконують.

```bash
.venv-wp2/bin/python scripts/measure_wp2_resources.py \
  --run-id yaropolk_y02_smoke200_<sha7>_01 --frames 200

.venv-wp2/bin/python scripts/evaluate_wp2_run.py \
  --source-run results/runs/yaropolk_y02_smoke200_<sha7>_01 \
  --groundtruth data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz/groundtruth.txt \
  --resources results/runs/yaropolk_y02_smoke200_<sha7>_01.resources.json \
  --run-id yaropolk_y02_eval_smoke200_<sha7>_01
```

Resource wrapper за замовчуванням передає `--export-sparse`; `--no-export-sparse` дозволяє final-only run. Додатково: `--pyslam-root`, `--pyslam-python`, `--output-root`, `--timeout`. Для worktree можна передати абсолютні paths на existing runtime/source. Raw dataset мусить лишатися всередині worktree через existing verifier; локальна APFS copy-on-write копія дозволяє не завантажувати його повторно.

Evaluator підтримує historical completed merged B0 runs (`ok` / `degraded`), якщо є preparation та final trajectory. Retained export і resources необов'язкові. Відсутня telemetry → `null` + reason. Failed/incomplete source manifest, malformed poses, off-grid timestamps, підміна source hash у resource report або artifact path поза run directory відхиляються. GT передається явно й використовується тільки evaluator-ом; SHA-256 reference записується у `inputs.json`.

## Outputs і semantics

- Source run залишається незмінним; wrapper створює окремий `results/runs/<source_run_id>.resources.json`. Навіть child preflight failure зберігає exit code / reason, а FPS тоді `null`. Existing run/report ніколи не перезаписуються.
- Derived `results/runs/<eval_run_id>/`: validated `run.json`, `metrics.json`, `inputs.json`. `method=B0`, `model=null`, `alignment=null`: Sim(3) — виключно evaluation transform у metrics, не metric scale recovery.
- **Final trajectory**: `input_setup/trajectory/trajectory_final.txt`, optimized upstream snapshot. Це не causal all-frame history. Upstream final export може передувати останньому background mapping update.
- **Retained keyframes**: poses із того самого stopped sparse snapshot; окремий Sim(3) fit через той самий `trajectory_metrics(..., alignment="sim3")`, що й comparison `B0_sim3`. Ці два рядки не об'єднуються й не трактуються як одна trajectory.
- **ATE / RPE**: метри / degrees, greedy one-to-one GT association, default tolerance 20 ms; RPE delta=1 **matched pose row**, не RGB frame. RPE не gap-aware; це Y-03. Мало GT matches або degenerate gauge → metrics `null` з причиною.
- **Pose coverage**: poses / frozen associated RGB-depth frames, фактично переданих SLAM. Це не tracking success. GT-associated pose count звітується окремо.
- Derived run завжди **degraded**: Y-02 не оцінює all-frame states, failure segments або gap-aware RPE, навіть якщо source містить Y-01 CSV. Exit 0 evaluator означає успішне створення чесно обмеженого звіту.
- `inputs.json` містить source commit/dirty flag, source hardware/environment та SHA-256 input artifacts. Hardware/environment у derived `run.json` описують evaluation host, не приписують йому source performance.

## Resource scope

`wall_clock_s` — весь child runner: preflight, startup, initialization/tracking, sparse export та shutdown. `effective_fps` = validated input frames / цей wall clock; warm-up не виключається. Це не per-frame latency чи real-time proof.

Peak RSS: POSIX `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`; macOS bytes, Linux KiB → bytes. Це **максимум individual-process RSS**, як його повертає OS, не сума одночасного RAM усіх workers; облік descendants залежить від OS. Wrapper запускається окремим свіжим процесом. Якщо він уже reap-ив інші children, cumulative peak не можна відняти: поле стає `null` з причиною. Unsupported platform / недоступний RSS також дає `null`, не оцінку.

Cold start до першого tracked frame не instrumented: `cold_start_s=null` з причиною. Mapping latency, whole-loop per-frame latency та VRAM цим wrapper не вимірюються. `real_time_claim=false`.

## Перевірка і evidence

Unit tests: exact/noisy/Sim(3) trajectory, partial pose coverage, відсутні GT matches, degenerate gauge, off-grid rejection, retained-keyframe parity, immutable outputs/sources, exact resource-source hash, RSS units, prior-child attribution, failed child/preflight, import hygiene.

Локальні environments не змінювались. У `.venv-wp2` немає scipy, у native `.venv-pyslam` немає pytest. Для full CPU suite використано native interpreter із scipy та тимчасовий `PYTHONPATH`, який відкриває лише вже встановлені pytest/support modules із tools environment (без install/upgrade). Перша спроба передавала pytest лише parent process, тому п'ять existing child-process tests не бачили pytest; після успадкованого `PYTHONPATH` це усунуто без змін source tests.

Перший worktree preflight із symlink на raw data відхилений existing verifier як outside repository; жодного SLAM run не створено. Після APFS clone dataset/source/runtime preflight — **ok**.

## Clean macOS smoke — 25 жовтня 2026

Implementation commit: `9bc4ee3be7bbf208a6ffa38b5e60d204f4c30bb9`. Source та evaluation мають `dirty_worktree=false`. [Versioned summary з hashes](../results/summaries/yaropolk_y02_smoke200_9bc4ee3.json).

- Source `yaropolk_y02_smoke200_9bc4ee3_01`: **ok**; 200 processed, 198 final poses, 0 LOST за upstream counters. Y-01 export: 198 OK / 2 NOT_INITIALIZED; 1,282 landmarks / 20 retained keyframes / 8,351 observations. Жодного failed real run у Y-02.
- Evaluation `yaropolk_y02_eval_smoke200_9bc4ee3_01`: **degraded** за documented Y-02 scope; metrics успішно обчислені.

| Scope | Poses / GT matches | Sim(3) ATE RMSE [m] | RPE translation RMSE [m] | RPE rotation RMSE [deg] |
|---|---:|---:|---:|---:|
| Upstream final | 198 / 196 | 0.01107299 | 0.00664144 | 0.39953597 |
| Stopped retained keyframes | 20 / 19 | 0.00677629 | 0.01421978 | 0.78512081 |

Pose coverage final = 198/200 = 0.99; це не tracking success. Independent fits: evaluation scale 1.38005506 (final) та 1.37637537 (retained). GT association one-to-one, тому GT matches може бути менше за pose count. RPE pairs: 195 final / 18 retained.

Whole-run wall clock **89.682126 s**, effective throughput **2.230099 FPS** (startup/export включено). OS-reported peak individual-process RSS **1,703,723,008 bytes** (~1.587 GiB); не сумарний RAM workers. Cold start — `null` з причиною. macOS 26.6.2 / arm64, 32 GiB RAM, native runtime Python 3.11.16, NumPy 1.26.4, torch 2.6.0, OpenCV 4.11.0; native pySLAM source `96019cf`.

Verification: full local CPU suite **523 passed, 1 native skip**; Y-02 tests **16 passed**. Source run.json hash до evaluator (resource report) і після evaluator збігається. Sparse read-back/checksums validated existing runner-ом. Historical runs не змінювались. Shared status docs за file boundaries плану оновлюються на IC1; цей документ і PR надають status row/evidence.
