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

- **Partial GT coverage:** `metrics.json` і `inputs.json` містять `gt_coverage` для всіх frozen RGB inputs, навіть initialization / LOST frames. Поля: `total_rgb_frames`, `matched_gt_frames`, `unmatched_gt_frames`, `coverage_percent`, `matched_frame_ids`, `excluded_frame_ids` та `excluded[]` (ID, timestamp, diagnostic nearest-GT delta, reason). `tracking.gt_coverage` охоплює всі tracking rows; `final_trajectory.coverage.gt_coverage` / retained-keyframe equivalent окремо описують лише exported pose frames. Ці denominators явно позначені: наявність GT не означає наявність SLAM pose.
- Recorded WP2 evaluator приймає тільки frozen GT tolerance **рівно 0.02 s**; generic timestamp matcher та comparison/keyframe policy не змінено. Усі input rows лишаються в tracking-success / latency denominator. Лише GT-dependent ATE/RPE використовують matched poses; немає interpolation, farther matches, GT pose edits або filtering SLAM inputs. RPE delta/gap semantics лишаються попередніми. Якщо жоден input не має valid GT match, CLI повертає exit **2** з JSON `status=failed`, `no_valid_gt_overlap` та full coverage report до створення output directory. За 1–2 matches чи degenerate gauge GT metrics лишаються unavailable з причиною, без вигаданих чисел.
- Source run залишається незмінним; wrapper створює окремий `results/runs/<source_run_id>.resources.json`. Навіть child preflight failure зберігає exit code / reason, а FPS тоді `null`. Existing run/report ніколи не перезаписуються.
- Derived `results/runs/<eval_run_id>/`: validated `run.json`, `metrics.json`, `inputs.json`. `method=B0`, `model=null`, `alignment=null`: Sim(3) — виключно evaluation transform у metrics, не metric scale recovery.
- **Final trajectory**: `input_setup/trajectory/trajectory_final.txt`, optimized upstream snapshot. Це не causal all-frame history. Upstream final export може передувати останньому background mapping update.
- **Retained keyframes**: poses із того самого stopped sparse snapshot; окремий Sim(3) fit через той самий `trajectory_metrics(..., alignment="sim3")`, що й comparison `B0_sim3`. Ці два рядки не об'єднуються й не трактуються як одна trajectory.
- **ATE / RPE**: метри / degrees, greedy one-to-one GT association, default tolerance 20 ms; RPE delta=1 **matched pose row**, не RGB frame. RPE не gap-aware; це Y-03. Мало GT matches або degenerate gauge → metrics `null` з причиною.
- **Pose coverage**: poses / frozen associated RGB-depth frames, фактично переданих SLAM. Це не tracking success. GT-associated pose count звітується окремо.
- На historical Y-02 commit derived run завжди **degraded**: там не оцінювалися all-frame states, failure segments або gap-aware RPE, навіть якщо source містив Y-01 CSV. Y-03 extension нижче визначає поточні status rules. Exit 0 evaluator означає успішне створення звіту; status/reason слід читати з run.json.
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


## Y-03: causal states, gap-aware RPE і latency

Branch: `feature/yaropolk-tracking-evaluation`. Локальна implementation base — completed Y-02 `2dd1498`; observed `origin/develop` на початку Y-03 — `060eef75b3e16eff58617faf3b40efe58c897881`. Y-03 спочатку підготовлено окремою локальною branch поверх Y-02, поки automatic approval review блокував публікацію. Після explicit дозволу користувача Y-02 merged через [PR #15](https://github.com/Badabuba/ai-real-time-mapping/pull/15), merge `fd48549c540ea07612d3ede461f5589df831374d`; усі чотири CI jobs пройшли. Y-03 синхронізовано з цим develop merge без переписування implementation/evidence commits. Актуальний CI/merge status Y-03 доступний у GitHub PR.

Input evidence — **власний clean macOS Y-02 run** `yaropolk_y02_smoke200_9bc4ee3_01`, який уже містить повний verified Y-01 export. Це свідома відмінність від запланованої назви `yaropolk_y01_*`: алгоритм / config / exporter той самий merged; повторний SLAM не потрібний. Інші учасники ignored runs не використовувались, source не редагувався.

```bash
.venv-pyslam/bin/python scripts/evaluate_wp2_run.py \
  --source-run results/runs/yaropolk_y02_smoke200_9bc4ee3_01 \
  --groundtruth data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz/groundtruth.txt \
  --resources results/runs/yaropolk_y02_smoke200_9bc4ee3_01.resources.json \
  --tracking-warmup 1 --plot \
  --run-id yaropolk_y03_eval_smoke200_<sha7>_01
```

Без `--plot` matplotlib не потрібний. `--tracking-warmup N` виключає перші N **frozen input rows**, незалежно від state. За замовчуванням N=1; решта initialization/LOST rows включені. `summarize_timings` використано без змін: p50 = median, p95 = NumPy linear percentile. First sample `cold_start_ms` означає лише перший `Slam.track`, не startup процесу. Whole-loop/mapping timing лишаються `null` з причинами. FPS із tracking latency не виводиться.

### Tracking і failures

- `read_tracking_log` перевіряє schema, CSV hashes, frame IDs / timestamps, metadata counts та pose validity проти frozen preparation. Advertised, але неповний або corrupt export відхиляється до створення output directory; він не стає silently absent.
- Denominator: **всі frozen associated RGB-depth input frames, фактично передані SLAM**, включно з initialization/LOST/UNKNOWN. Numerator: observed native `OK` count. Якщо немає UNKNOWN / track exceptions, `tracking_success=OK/all`; інакше success=`null` + reason, а `observed_ok_fraction` звітується окремо. Missing OK pose не підміняється; usable-pose coverage окрема від state success.
- Contiguous state segments містять first/last frame IDs, timestamps та row counts. `timestamp_span_s` — різниця timestamps першого й останнього спостереження, не оцінка того, скільки часу state тривав між samples.
- Failure table: initializing, LOST, relocalizing, UNKNOWN, OK-without-pose, track exceptions, keyframe observation errors, GT-unassociated usable poses. Counts можуть перекриватися. Відсутність GT association — evaluation limitation, не tracking loss.
- Online ATE — окремий global evaluation-only Sim(3) fit **causal** poses. Final optimized / stopped sparse rows із Y-02 збережені окремо. Online poses не використовуються для alignment/fusion sparse snapshot.

### Gap-aware RPE

1. Використовуються лише causal OK rows із valid pose та без track exception; GT association — unchanged greedy one-to-one evaluator rule.
2. Один Sim(3) fit на всій associated causal trajectory через unchanged `trajectory_metrics`; той самий evaluation-only scale використано для всіх relative pairs. Немає per-segment scale fitting.
3. Candidate delta вимірюється в **matched causal pose rows до filtering**, default 1. Pair відхиляється, якщо хоча б один intervening frozen input не має OK + valid pose + no exception; також перевіряються endpoints. GT-unmatched, але observable OK rows самі по собі не створюють tracking gap.
4. Eligible / excluded input frame-ID pairs записуються явно. ATE лишається доступним, навіть коли великий delta не дає RPE pairs. No pairs, all LOST, недостатньо GT matches або degenerate gauge → відповідні metrics `null` з причиною, не нульова помилка.

Derived status **ok**, якщо source ok, verified tracking повний, final/causal metrics і gap-aware RPE доступні та latency summary визначена. Інакше **degraded** із конкретними причинами. Наявний tracking loss сам по собі не означає failed evaluation: failure statistics — валідний результат. Historical sources без Y-01 export підтримуються зі status degraded.

### Verification Y-03

Tests охоплюють gap-free parity з unchanged evaluator, LOST та multi-frame gaps, missing poses / exceptions, UNKNOWN без imputation, all-lost, no GT / no pairs, warmup exhaustion, state segments, corrupt export, immutable source та byte-identical `metrics.json`, `inputs.json`, PNG при повторному evaluation. `run.json` має нові run_id / started_at, тому ці provenance поля не порівнюються побітово.

Real numeric evidence, source hashes і test counts записуються окремо в `results/summaries/yaropolk_y03_eval_smoke200.json`; timeline — `results/plots/yaropolk_y03_tracking_states_smoke200.png`. Install / download / baseline tuning не виконувались. Shared status docs лишаються для IC1 за file boundaries плану.


### Recorded Y-03 result — 25 жовтня 2026

Implementation `f7245ff58f90b4e9e9572724d2db520728a841b2`; runs `yaropolk_y03_eval_smoke200_f7245ff_01` і `_02`: **ok**, `dirty_worktree=false`. [Summary](../results/summaries/yaropolk_y03_eval_smoke200.json), [state/latency timeline](../results/plots/yaropolk_y03_tracking_states_smoke200.png).

- Tracking success **198/200 = 0.99**. Frames 0–1: NOT_INITIALIZED; frames 2–199: OK. LOST / UNKNOWN / relocalization / observer exceptions / missing OK poses — 0.
- Causal trajectory: 198 usable poses, 196 GT associations, Sim(3) ATE RMSE **0.01103932 m**. Два GT-unassociated poses не рахуються як tracking loss.
- Gap-aware RPE: 195 candidate / 195 eligible / 0 excluded-gap pairs; translation RMSE **0.00554435 m**, rotation RMSE **0.37072596 deg**. Scale **1.37765435**, evaluation-only.
- Tracking warm-up=1, 199 samples: p50 **168.414083 ms**, p95 **909.267971 ms**, mean **293.951464 ms**. First-call sample **284.602 ms**; це не process cold start. `real_time_claim=false`.
- Full local CPU suite **535 passed, 1 native skip**; WP2 evaluation tests **28 passed**. `metrics.json`, `inputs.json`, `tracking_states.png` побітово однакові в обох evaluations. Всі раніше recorded Y-02 artifact hashes залишилися незмінними; timeline візуально перевірено.
- Failed real Y-03 evaluations: **немає**. Matplotlib створив temporary cache, бо default user cache недоступний у sandbox; це не вплинуло на output, детермінізм або status. Existing environments не змінювались.

Після merge актуального `develop` (включно з Yulian U-02) повторна combined local CPU suite: **602 passed, 1 native skip**; `git diff --check` пройшов. Зміни Y-03 відносно merged Y-02 залишаються у шести дозволених files.
