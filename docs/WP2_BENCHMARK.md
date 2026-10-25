# WP2: B0 development/selection і held-out benchmark (Y-05 / Y-06)

Owner / реалізація: Ярополк (WP2/WP5). Branch `feature/yaropolk-b0-development`; source/base `422172a4cf821d4a838d43426e1acd31c27827f5` (merged Y-04, PR #19). Усі чотири source runs та derived evaluations мають `dirty_worktree=false`. Source/algorithm code у Y-05 не змінено.

**Висновок Y-05 для презентації:** baseline працює на ширших desk inputs, але development має тривалий relocalization gap і лише ~76% OK frames. Низька ATE на available poses не означає повне успішне tracking. Цей результат offline. Подальший Y-06 held-out run завершено: 98.67% OK frames, causal ATE 3.86 cm / final ATE 1.61 cm (evaluation-only Sim(3)); 1.80 FPS. Повний Y-06 result і startup failure disclosure — нижче.

[JSON із hashes/provenance](../results/summaries/yaropolk_y05_benchmark.json), [CSV](../results/summaries/yaropolk_y05_benchmark.csv), [comparison plot](../results/plots/yaropolk_y05_benchmark.png), [state timeline](../results/plots/yaropolk_y05_tracking_states.png).

## Фіксований протокол

- Development: `tum_fr1_desk_development.json`, усі 573 frozen associations, три repeats. Selection: `tum_fr2_desk_selection50.json`, рівно 50 frozen associations, один run. Порядок: selection, потім dev 01/02/03, послідовно без competing SLAM jobs.
- Unchanged pinned pySLAM `96019cf`, ORB2/1000, DBOW3, Python core, `-O`, seed 0. Camera calibration походить із Y-04. No retuning / frame extension / model swap.
- Host: Apple M1 Pro, macOS 26.6.2, 32 GiB RAM. Native Python 3.11.16, NumPy 1.26.4, torch 2.6.0, Python OpenCV 4.11.0. У summaries збережено фактичні source environment fields.
- GT лише evaluation. Denominator success = **усі frozen input frames**, включно з initialization, LOST та RELOCALIZE. Numerator = native OK states.
- Final optimized та causal trajectories — різні rows/gauges. У таблиці нижче ATE causal; обидві ATE є у CSV. Один global Sim(3) evaluation fit, не metric scale recovery. RPE виключає pairs через non-OK/missing-pose inputs.
- Timing: `Slam.track` wall time, warmup=1 input row; p50/p95 включають решту states, з waits/hook overhead. Whole-run FPS включає startup/preflight/export/shutdown. Peak RSS — maximum individual-process child usage, не sum RAM workers.

## Числа

| Run | OK / inputs | LOST | Relocalizing | Causal ATE [cm] | Gap-aware RPE trans [cm] | Track p50 / p95 [ms] | Whole-run FPS | Peak RSS [GiB] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Selection 50 | 45/50 (90.00%) | 0 | 0 | 1.635 | 0.793 | 119.7 / 475.5 | 1.240 | 1.259 |
| Dev 01 | 439/573 (76.61%) | 4 | 128 | 3.533 | 1.304 | 135.3 / 1339.5 | 2.851 | 2.938 |
| Dev 02 | 439/573 (76.61%) | 2 | 130 | 2.449 | 1.232 | 132.2 / 1311.5 | 2.914 | 1.892 |
| Dev 03 | 430/573 (75.04%) | 2 | 128 | 2.424 | 1.298 | 128.2 / 1221.6 | 3.157 | 1.998 |

Development mean ± **sample std** (`ddof=1`, n=3):
- OK fraction: **76.09% ± 0.91 percentage points**.
- Causal ATE: **2.802 ± 0.633 cm**; final ATE: **1.891 ± 0.270 cm**.
- Causal RPE translation: **1.278 ± 0.040 cm**; rotation **0.668 ± 0.026 deg**.
- Whole-run throughput **2.974 ± 0.161 FPS**; wall clock **193.04 ± 10.21 s**.

ATE comparisons cover each run's available/associated poses; coverage can differ. Same seed не гарантує deterministic upstream workers. Третій run ініціалізувався пізніше (13 initialization frames проти 2 у перших двох). Не вибираємо best run для headline.

## Failure accounting

Усі **process runs = ok**, але це означає завершення pipeline і валідні exports; tracking interruption явно залишається у state counts. Failed process runs / failed evaluations у Y-05: **0**. Не розширювали selection після результату.

| Run | State | Frozen frame range | Frames |
|---|---|---|---:|
| sel50_422172a_01 | NOT_INITIALIZED | 0–4 | 5 |
| dev573_422172a_01 | NOT_INITIALIZED | 0–1 | 2 |
| dev573_422172a_01 | LOST | 169–169 | 1 |
| dev573_422172a_01 | RELOCALIZE | 170–297 | 128 |
| dev573_422172a_01 | LOST | 299–299 | 1 |
| dev573_422172a_01 | LOST | 301–301 | 1 |
| dev573_422172a_01 | LOST | 303–303 | 1 |
| dev573_422172a_02 | NOT_INITIALIZED | 0–1 | 2 |
| dev573_422172a_02 | LOST | 169–169 | 1 |
| dev573_422172a_02 | RELOCALIZE | 170–298 | 129 |
| dev573_422172a_02 | LOST | 301–301 | 1 |
| dev573_422172a_02 | RELOCALIZE | 302–302 | 1 |
| dev573_422172a_03 | NOT_INITIALIZED | 0–12 | 13 |
| dev573_422172a_03 | LOST | 169–169 | 1 |
| dev573_422172a_03 | RELOCALIZE | 170–297 | 128 |
| dev573_422172a_03 | LOST | 299–299 | 1 |

**Доведено observations:** усі development runs мають довгий RELOCALIZE segment приблизно frames 170–299, потім повертаються до OK. UNKNOWN та observer exceptions відсутні. Gap-aware evaluator не зшиває RPE через цей segment.

**Гіпотеза, не доведена причина:** motion blur / погіршення correspondences / умови relocalization можуть пояснювати interruption. Native log сам позначає деякі frames як blurry (IDs у summary); це temporal correlation, не causal proof. У Y-05 немає debugger/source changes або tuning, тому root cause не заявляється встановленою.

## GT window і official duplicate

Official fr2 GT містить два різні poses із timestamp `1311868229.576`. Вони далеко поза selection window **1311868164.3431811–1311868166.019133**. Для evaluation створено новий ignored reference з усіх GT rows у fixed input time range ±20 ms. Raw GT не редагувався; reference не містить averaging/deduplication, його timestamps строго increasing. Позавіконні rows не можуть бути timestamp candidates за тією самою tolerance, тому clipping не змінює associated candidates для наших inputs. Original/ref hashes і row counts є в summary.

## Повторити

Після documented native setup і verified inputs. Нові run IDs обов'язкові:

```bash
python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_development.json --all-frames --export-sparse --timeout 600 --run-id new_unique_dev573
python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_selection.json --all-frames --export-sparse --timeout 600 --run-id new_unique_sel50
```

Для resources використано existing `measure_process` API у **fresh Python process на кожний run**, з explicit `--config` argv. Existing `measure_wp2_resources.py` є smoke-only CLI і не має `--config`; його default не підміняв wider config. Minimal resource invocation з repo root:

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "src")
from rt_mapping.evaluation.slam_run import measure_process
root = Path.cwd()
argv = [str(root / ".venv-wp2/bin/python"), "scripts/run_wp2_pyslam.py",
        "--config", "configs/wp2_pyslam_development.json", "--all-frames",
        "--export-sparse", "--timeout", "600", "--run-id", "new_unique_measured_dev"]
print(json.dumps(measure_process(argv, cwd=root), indent=2))
```

Фактичні local orchestration scripts збережені в ignored `outputs/wp2/y05_run_one.py` та `y05_run_matrix.py`; вони додають sidecar hashes/status до resource report. Source runner/evaluators не змінені. Для evaluation reference створюється за правилом вище, після чого:

```bash
python scripts/evaluate_wp2_run.py --source-run results/runs/<source_run_id> --groundtruth outputs/wp2/y05_evaluation_gt/<source_run_id>.txt --resources results/runs/<source_run_id>.resources.json --plot --run-id <new_eval_run_id>
```

Повні raw runs / resource sidecars / GT refs / large PLY/NPZ лишаються local ignored; summary hashes дозволяють ідентифікувати artifacts. У Git — лише ці маленькі summaries, CSV, plots і doc.

## Cross-platform evidence

[Committed N-02 summary](../results/summaries/nazar_n02_e2e_smoke200_0fc564f.json): Docker/Linux на Windows host (Ryzen 9 8940HX), той самий pySLAM revision, smoke fr1/xyz200 — SLAM stage ok, 198 final poses, 0 upstream LOST. N-02 full comparison/pipeline має **failed** у записаному evidence; не приписуємо йому trajectory benchmark, якого там немає. Разом із нашим prior clean macOS Y-02 smoke це підтверджує роботу B0 на двох platforms. Wider Y-05 desk sequences інші; paired cross-platform speed/accuracy comparison не заявляється.

## Verification і deadline limitations

- 4 source runs + 4 evaluations: clean source commit, status ok. Additional dev01 re-evaluation: metrics.json, inputs.json та PNG **byte-identical**; run_id/started_at закономірно нові.
- Full CPU suite на тому самому source перед evidence-only Y-05: **688 passed, 1 native skip**. Plot legends/state ranges перевірено візуально; source/evaluation hashes перевірені.
- Frozen configs, seed і frame counts незмінні; жодного install/download або source edit у Y-05.
- На момент Y-05 held-out input/Y-06 був skipped за deadline decision користувача; historical Y-05 summaries збережені. Подальший Y-06 виконано нижче. Y-05 не є held-out validation, повним WP5 чи real-time system. Dense B0/B1/P1 wider comparison лишається окремою роботою Назара / команди.
- Contribution: Ярополк — WP2/WP5 benchmark execution/evidence; незмінені evaluators Юліана та contracts команди reused. Shared status docs залишено для integration checkpoint.

## Y-06: initial startup failure (25 жовтня 2026)

**Первинна спроба: startup failure, zero tracked frames.** Run `yaropolk_y06_heldout2488_c08833f_01`, clean source `c08833f0b287cecbdb72953796cd0dcd253b296b`, містить IC3 freeze (PR #25, `4021a02`) та окремий preflight fix PR #27 (`bd0a17e`). Y-05 historical summaries не змінено; актуальний successful Y-06 retry наведено після цієї первинної failure disclosure.

- Archive: 1,483,556,251 bytes, SHA-256 `c7cd8e1afb87c80e5744a356214819b110fa09b4744fa4ba0cc2382f9ba59e9c`; усі 5,098 extracted files побайтово збігаються. Frozen inputs: 2,488 frames / 4,976 RGB-depth image hashes; index hashes та manifest збігаються.
- Config SHA-256 `3545878e88134b33caf89b3a5a879372381d98a08bd637260ca4e5dce23971eb` = IC3 hash; seed 0, pySLAM `96019cf`, ORB2/1000, DBOW3, Python core `-O`, native macOS arm64. Algorithm/config/source не змінено в Y-06; timeout 14,400 s — operational guard.
- До створення run: archive був відсутній, потім valid official GT boundary помилково блокував preflight. Окремий PR #27 виправив лише metadata validation: три initial RGB frames раніше GT range тепер записуються як limitation, всі inputs збережені. Full CPU suite: **698 passed, 1 native integration skipped**; чотири CI checks passed.
- Після запуску native worker видав `OMP: Error #179: Function Can't open SHM failed` під час initialization. Loop-closing readiness не настала; `trajectory_all.csv` та `timing.csv` містять нуль observations. **Гіпотеза:** shared-memory restriction execution sandbox; unrestricted retry на момент цієї первинної спроби ще не виконано; подальший результат нижче. Stalled upstream process зупинено SIGTERM, runner сам записав terminal `failed` (`upstream_exit: -15`). Finished `run.json` не редагувався.
- Wall clock до зупинки: 199.445 s; peak individual-process RSS: 743,489,536 bytes. Це startup-failure diagnostics; FPS, ATE/RPE, tracking success та p50/p95 **null**, не нульова якість і не performance benchmark. Cold start to first tracked frame не instrumented. Real-time claim відсутній.
- Evidence: [JSON](../results/summaries/yaropolk_y06_heldout.json), [CSV](../results/summaries/yaropolk_y06_heldout.csv), [startup-failure plot](../results/plots/yaropolk_y06_tracking_states.png). Full runs/logs локальні й ignored. Native launch/resource driver — локальний `outputs/wp2/` / temporary orchestration; resource schema та unchanged APIs ті самі, що Y-05.

**Disclosures.** Superseded runner `wp2_heldout2488_4484fd7` failed у upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`), без trajectory/metrics, нічого не tuned. Committed N-06 `nazar_n06_heldout2488_da3_e561d8c_01` failed на GT preflight з нулем SLAM frames; PR #27 виправив цей blocker. Поточна local startup failure також збережена; ця первинна спроба не містить retry чи tuning. Користувач згодом явно дозволив execution-environment exception до D-5: retry поза sandbox з незмінними параметрами та новим run ID (нижче). GT прочитано тільки для integrity/timestamp validation; evaluation не запускалось, жодна GT pose/depth не вплинула на SLAM.


## Y-06: authorized native retry — final held-out evidence

**Source process: ok; evaluation: ok.** Run `yaropolk_y06_heldout2488_9714957_02`, clean source `9714957c0b5925d8f2e756f143028a7f6309ffed`; він містить IC3 freeze та merged preflight fix PR #27. Користувач явно дозволив retry поза execution sandbox після zero-frame OpenMP failure. Config/source алгоритму, frame set, seed, GT та evaluator не змінювалися; це виправлення launch context, не tuning. Попередні run та failure summaries збережені.

| Metric | Held-out result |
|---|---|
| Frozen / observed frames | 2,488 / 2488 |
| OK-state tracking fraction | 98.67% (2455 frames) |
| Initialization / LOST / relocalizing / UNKNOWN | 33 / 0 / 0 / 0 |
| Causal poses / GT-associated | 2455 / 2455 |
| Final optimized poses / GT-associated | 2455 / 2455 |
| Causal Sim(3) ATE RMSE | 0.038586 m |
| Final optimized Sim(3) ATE RMSE | 0.016064 m |
| Gap-aware causal RPE translation / rotation | 0.006621 m / 0.2815 deg |
| Eligible RPE pairs / excluded gap pairs | 2454 / 0 |
| Warm tracking p50 / p95 | 244.162 / 1804.090 ms |
| Whole-run wall clock / throughput | 1385.355 s / 1.796 FPS |
| Peak individual-process RSS | 4583178240 bytes |

ATE оцінюється лише на доступних poses з GT association до 20 ms; tracking denominator — усі 2,488 frozen input frames. Evaluation-only Sim(3) не відновлює метричний scale. Causal та final optimized poses мають окремі global Sim(3) fits; final quality не є causal online quality. RPE не перетинає non-OK/missing-pose gaps. Whole-run throughput включає preflight/startup/export/shutdown; p50/p95 — лише `Slam.track`, warmup = один input frame. Peak RSS — OS maximum individual child process, не сума concurrent workers; cold-start-to-first-track не instrumented. **Offline; real-time claim відсутній.**

GT reference — повний незмінений official `groundtruth.txt`, SHA-256 `e255d5d9c5bab915132c7ac5ec4e23f9f1efe98f765b0c9b26ac74e40b02533f`; GT тільки для evaluation та metadata verification. Жодних averages/deduplication/cropping/pose edits. Initial RGB/GT boundary mismatch збережено, unmatched usable poses наведені у JSON failure table. Тільки одна completed benchmark attempt після startup failure; variance не оцінюється. Не робили parameter selection чи rerun через якість.

Відтворення (той самий source commit, новий run ID; повторне виконання held-out потребує дотримання протоколу):

```bash
.venv-wp2/bin/python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_heldout.json --all-frames --export-sparse --timeout 14400 --pyslam-root external/pyslam --pyslam-python .venv-pyslam/bin/python --run-id <new_run_id>
.venv-pyslam/bin/python scripts/evaluate_wp2_run.py --source-run results/runs/<new_run_id> --groundtruth data/raw/tum_rgbd/rgbd_dataset_freiburg3_long_office_household/groundtruth.txt --run-id <new_eval_id> --plot
```

Resource sidecar створено тим самим existing `measure_process` API в окремому fresh Python wrapper, як Y-05: CLI `measure_wp2_resources.py` не приймає split config. Для приєднання виміряного resource sidecar додати evaluator flag `--resources results/runs/<new_run_id>.resources.json`; без нього повторюються accuracy/tracking metrics, resources залишаються unavailable. Exact local drivers збережено в ignored `outputs/wp2/`; tracked source/config edits у Y-06 відсутні. Upstream shutdown містив warning про 46 leaked semaphore objects; source та evaluation завершилися зі status ok.

Evidence: [retry JSON](../results/summaries/yaropolk_y06_retry.json), [retry CSV](../results/summaries/yaropolk_y06_retry.csv), [tracking/latency plot](../results/plots/yaropolk_y06_retry_tracking_states.png). Initial failure: [JSON](../results/summaries/yaropolk_y06_heldout.json). All source/evaluation artifact hashes перевірені; plots візуально перевірені. Preflight fix validation: 698 passed / 1 native integration skipped; source/data/config hashes та `git diff --check` перевірено для цього evidence-only change. CI result — у PR.

Cross-platform: цей run — native macOS arm64 B0. Committed N-06 `nazar_n06_heldout2488_da3_e561d8c_01` зупинився до SLAM на preflight, тому paired Docker held-out accuracy/speed comparison поки неможливий. Попередня двоплатформна smoke validation лишається в Y-05; цей run сам по собі не доводить wider pipeline reproduction чи P1 quality.

Attribution: Ярополк — WP2 held-out execution/evidence та preflight correction; unchanged evaluators Юліана / team contracts reused. Disclosure `wp2_heldout2488_4484fd7` та N-06 failure вище лишаються чинними, нічого з них не tuned. Raw datasets, full logs/runs, sparse map та archives не включено в Git.
