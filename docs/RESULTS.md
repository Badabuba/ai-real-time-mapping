# Результати, обмеження та внесок

<a id="evidence"></a>

## Поточний стан (26 жовтня 2026)

- WP1 depth adapters, WP2 SLAM/causal exports/evaluation, WP3 alignment/fusion і WP4 comparison працюють через спільні contracts.
- B0 Y-06 native macOS: 2,455/2,488 OK (98.67%), causal Sim(3) ATE 3.86 cm, final ATE 1.61 cm; 1.80 FPS. Initial zero-frame startup failure і дозволений retry збережені.
- N-02 comparison-only reproduction після GT coverage fix — ok (17/18 eligible keyframes).
- N-06 D-5 rerun: SLAM, DA3 та P1-global — ok; comparison failed на P1-raw frozen voxel cap. Held-out map comparison не завершено. Це final disclosed evidence, не підстава змінювати frozen settings.
- P1-robust smoke дає негативний результат: anchoring не покращив геометрію; gate не відкинув кадрів. Не оголошувати його кращою заміною P1-global.
- Усі наведені результати offline. End-to-end real-time не підтверджено.

Історичні секції нижче відображають стан на source commit; актуальний підсумок — у цьому вступі.

## Внесок команди

| Учасник | Внесок | Evidence |
|---|---|---|
| Назар | WP1 DA3 / UniDepth, data freeze, model selection, depth ablations; Docker reproduction N-02, development N-05, held-out N-06 | summaries `nazar_n02_*`, `nazar_n03_*`, `nazar_n04_*`, `nazar_n05_*`, `nazar_n06_*`; ADR001; PR #24–#26, #31 |
| Ярополк | WP2 native runtime, sparse exports, Y-02/Y-03 metrics, split configs Y-04, Y-05 repeats, Y-06; partial GT preflight fix | `wp2_sparse_fr1_xyz_200_20261023.json`, `yaropolk_y02_*`…`yaropolk_y06_*`; PR #15, #16, #19, #23, #27–#29 |
| Юліан | WP3 robust scale/Sim(3), WP4 fusion/evaluation/pipeline; missing-GT comparison policy, CI; P1-robust U-01…U-04; Y-01 causal export assistance у WP2 Ярополка | `wp3_wp4_yulian_*`, `yulian_u01_*`…`yulian_u03_*`, `yaropolk_y01_tracking_smoke200_be9bff2.json`; PR #7/#8, #11, #21 |

WP ownership та assistance не взаємозамінні. Зокрема, оригінальний WP2 owner — Ярополк; Y-01 реалізував Юліан як assistance. Подальші таблиці зберігають original commits/run IDs, hardware, failures та limitations; повні source histories доступні через pinned links.

## Що лишається до подання

Presentation/demo work у PR #30 не змінено cleanup-ом. Фінальна перевірка fresh-clone reproduction, submission audit, вимоги rubric і release — окремі deliverables; cleanup не оголошує їх виконаними. Full held-out B0/B1/P1 map table недоступна через N-06 comparison failure. Optional robust-development/live S1/fault-injection experiments не виконуються автоматично. Main/release і публікація вимагають окремого дозволу.


## WP3/WP4 real pipeline smoke

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP3_WP4_COMPLETION.md). Історичні run IDs та результати збережено.

### Реалізований залишок

- `scripts/run_pipeline.py --config <json> --run-id <unique>` запускає WP2/WP1 CLI через explicit argv або повторно використовує completed runs; потім робить mapping чи comparison. Немає shell interpolation, downloads або installations у launcher. Див. `configs/pipeline.tum.example.json`.
- `scripts/run_mapping_comparison.py`: B0 sparse із shared P1 scale, P1-raw (явне scale=1 припущення), P1-global, B1 oracle зі **спільними P1 metric poses**, keyframe/confidence ablations. Oracle не підбирає scale за GT.
- `evaluation/trajectory.py`: one-to-one timestamp association, SE(3)/Sim(3) ATE та RPE. RPE delta — matched retained-keyframe rows, не всі RGB frames. Sim(3) diagnostic окремо від metric SE(3) result.
- `evaluation/map_geometry.py`: однаковий voxel/crop, accuracy/completeness, symmetric Chamfer-L1 = 0.5·(mean forward + mean backward), F-score@2/5/10 cm. Один trajectory-only SE(3) evaluation transform для всіх maps; per-map ICP/Sim(3) не використовується.
- `alignment/causal.py`: optional P1-window, лише поточне/минуле вікно, стабільний landmark-ID hash split. Не вистачає startup support — явна помилка, без майбутнього/global fallback. Вмикається `causal_window_frames>0` лише як development ablation.
- `run_comparison_smoke.py --plot`: повний synthetic reference/oracle/comparison fixture, явно позначений synthetic. CPU suite: **472 passed, 1 native skip**; Ubuntu/Windows Python 3.11/3.12 CI. Окремо installed-backend sparse API test: **1 passed**.

### Дані та runtime

За явним дозволом Юліана завантажено frozen TUM fr1/xyz: SHA-256 `a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98`; `build_tum_manifest.py --check` пройшов. DA3METRIC-LARGE revision `4010e39f3634a45bc60553321fb49fb760bd594e`, weights SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776` збігається з Nazar evidence.

DA3 isolated environment: `.local/da3-venv`, використовує наявний host torch 2.7.1+cu118, RTX 3070 Ti Laptop 8 GB; NumPy 1.26.4 та OpenCV 4.11 встановлені локально у venv. Host packages не замінювалися. Clean 200-frame run `yulian_da3_f200_b43c384` (`b43c384`, `dirty_worktree=false`) завершився: mean AbsRel **0.092655**, RMSE **0.177196 m**, δ1 **0.964949**; warm median **125.462 ms**, p95 **157.248 ms** (warmup=1). Усі 200 C3 predictions існують. [Summary із source hashes](../results/summaries/wp1_da3metric_yulian_tum_fr1_xyz_200.json). Це smoke inference evidence, не alignment або held-out benchmark.

Незалежна перевірка trajectory evaluator через `evo` на 60 TUM poses із заданим scale/noise дала ATE/RPE RMSE різницю ≤1.3e-16 для SE(3) та Sim(3). Це parity перевірка математичного evaluator, не accuracy самого SLAM.

Native pySLAM runtime зібрано в окремому Docker container `rt-mapping-wp2-yulian`, без system packages на Windows/Ubuntu host. Source pinned `96019cf`; контейнерна копія потрібна для коректних Unix symlinks. Opt-in test реальних Map/KeyFrame/MapPoint APIs та sparse export пройшов: **1 test, OK**. Dataset/source/entry-point preflight: **ok**. Це Linux runtime на Windows/Docker host, не native Windows SLAM support.

Linux recipe та compatibility flags: [docs/REPRODUCIBILITY.md](REPRODUCIBILITY.md#runtime). Відповідний full-stage config: `configs/pipeline.tum.windows-docker.json`.

### Реальний end-to-end результат

Run `yulian_tum_e2e_f200_20261025_01`: **ok**, усі stages та methods із clean commit `4952e37dd773925c4c7aa069c4d6aaf10f489120`, `dirty_worktree=false`. Один config справді запускав обидва adapters; це не reuse mode. Full artifacts локально у `results/runs/<run_id>/`; [малий summary із hashes](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json), [CSV](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.csv), [звіт](../results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200_report.md).

- SLAM: 200/200 frames, 198 final poses, 0 LOST за upstream counters; **1,277 landmarks / 22 retained keyframes / 8,893 observations**. Pose fraction не називаємо tracking success.
- Alignment: scale **1.1920834**; 5,044/6,571 calibration inliers (**76.76%**), 16/16 coverage bins. Незмінний residual threshold **0.1 m**. Withheld: 256 landmarks / 1,737 pairs, inlier ratio **77.43%**, median **0.03877 m**, p95 **0.31322 m**. Великий outlier tail не приховується.
- Fusion: 611,226 pixel samples → **72,887 metric voxels** до evaluation transform; common evaluation voxelization має **58,569** P1 points. [Map preview](../results/plots/yulian_tum_map.png), [residuals](../results/plots/yulian_tum_residuals.png), [comparison](../results/plots/yulian_tum_comparison.png) оглянуто візуально.
- P1 retained-keyframe SE(3) ATE **0.022377 m**, RPE translation **0.016288 m**, rotation **0.837401°**. B0 Sim(3) ATE **0.012187 m** — окремий scale-fitted diagnostic. Незалежні TUM reader, association та `evo` ATE/RPE відтворили P1 result до 9.1e-14: [parity](../results/summaries/wp3_wp4_yulian_real_evo_parity.json).
- Pipeline DA3: mean AbsRel **0.092655**, RMSE **0.177196 m**, δ1 **0.964949**; warm median **119.691 ms**, p95 **134.057 ms**. CPU fusion median **71.947 ms**, p95 **121.059 ms**. Wall clock усього launcher **400.02 s**; inference включено. Це offline smoke, не real-time.

| Method | Accuracy mean [m] ↓ | Completeness mean [m] ↓ | Chamfer-L1 [m] ↓ | SE(3) ATE [m] ↓ |
|---|---:|---:|---:|---:|
| B0-shared-scale | 0.04937 | 0.22610 | 0.13774 | 0.02238 |
| P1-global | 0.09239 | 0.08493 | 0.08866 | 0.02238 |
| P1-raw | 0.09132 | 0.08387 | 0.08760 | 0.04890 |
| B1-oracle | 0.03231 | 0.03349 | 0.03290 | 0.02238 |
| P1-keyframes-2 | 0.08180 | 0.09403 | 0.08792 | 0.02238 |
| P1-keyframes-5 | 0.07464 | 0.10493 | 0.08979 | 0.02238 |

P1 покращує completeness та combined Chamfer проти sparse B0, але sparse points точніші в середньому. Scale recovery покращує metric trajectory проти unit-scale control, проте **global map Chamfer не кращий за P1-raw** на цьому smoke. Це tradeoff, не універсальне покращення. B1 показує помітний залишковий depth-error gap. Global threshold не підбирали за GT; input runs і finished manifests не змінювали.

### Обмеження evaluation

- GT доступний лише evaluation/oracle code. P1-global завершується до читання GT; інші P1 controls не отримують GT як input.
- Усі методи використовують frozen RGB calibration. Реєстрована TUM depth має нетривіальну rectification; shared RGB K/Brown reference є задокументованим наближенням. [Офіційний формат TUM](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats) рекомендує ROS-default intrinsics для прямої побудови depth cloud. Під час цієї роботи frozen calibration мовчки не змінюється.
- Confidence ablation пропускається з explicit reason, якщо DA3 не повертає confidence. Fake confidence не створюється.
- Stage reuse не вимірює SLAM/model inference заново. CPU fusion timing не є end-to-end FPS. Повний held-out benchmark та tracking normalization лишаються shared/adapter work packages.


## WP2 sparse export: historical evidence

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SPARSE_EXPORT.md). Історичні run IDs та результати збережено.

### Фактичний результат — 23 жовтня 2026

- Run `yaropolk_b0_fr1_xyz_200_sparse_20261023_03`, status `ok`, 200 processed / 0 LOST; 197 final trajectory poses, 82.0695 s wall clock зі startup/export.
- Export: **1,205 landmarks, 19 retained keyframes, 7,595 observations**. `skipped={}`. Це інший run, ніж попередній `_02` з 198 poses; threaded execution не гарантує ідентичного результату.
- Median undistorted reprojection residual: 0.9303 px, p95: 3.1680 px, max: 8.7526 px. Це consistency diagnostic, не GT trajectory accuracy.
- Read-back validation пройшла; усі task-owned workers завершились. Upstream tracked source чистий. Усі 15 artifacts попереднього успішного run залишились byte-identical.
- CPU suite: **325 passed, 1 skipped**; skipped native check окремо пройшов у `.venv-pyslam` через unittest. Native check log: `.local/wp2/sparse-native-api.log`.
- Малий evidence summary: `results/summaries/wp2_sparse_fr1_xyz_200_20261023.json`.
- Preview: `results/visualizations/yaropolk_b0_fr1_xyz_200_sparse_20261023_03/20261023T142031_442564Z/sparse_map_preview.png`.
- Versioned preview для teammates: [results/plots/wp2_sparse_map.png](../results/plots/wp2_sparse_map.png). Повні NPZ/CSV/PLY залишаються локально в ignored `results/runs/`; для реального alignment їх треба передати Юліану окремо або відтворити run. Git merge передає code та evidence summaries, а не ці великі artifacts.
- Attempts `_01` (launcher NameError до upstream start; виправлено, додано runner regression tests) та `_02` (sandbox denied OpenMP shared memory до tracking; stopped only own process group) збережені як failed. `_03` запущено з необхідним local-process доступом.
- Новий run не має GT ATE/RPE; попередні manual diagnostic scores стосуються старого run, їх не переносимо сюди. Немає real-time claim.


## Y-01 causal exports: clean evidence

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_TRACKING_EXPORT.md). Історичні run IDs та результати збережено.

### Clean real-run evidence

Обидва native runs мають clean `be9bff24eb2a54ea7927078c7cfc48969fd6d45a`, `dirty_worktree=false`, status **ok**. [Small summary із hashes](../results/summaries/yaropolk_y01_tracking_smoke200_be9bff2.json).

| Run suffix | Rows | States | Online poses | Creation events | Retained keyframes | Final poses |
|---|---:|---|---:|---:|---:|---:|
| `_01` | 200 | 198 OK / 2 NOT_INITIALIZED | 198 | 62 | 20 | 198 |
| `_02` | 200 | 198 OK / 2 NOT_INITIALIZED | 198 | 55 | 24 | 198 |

Full IDs: `yaropolk_y01_smoke200_be9bff2_01` та `_02`. State vectors збігаються на всіх 200 frames; unposed frames лише 0/1. UNKNOWN/observation errors — 0. Обидва final pose counts збігаються з prior clean baseline (198); upstream LOST counter також 0. Sparse read-back валідний: `_01` 1,254 landmarks / 8,097 observations; `_02` 1,375 / 10,140.

Keyframe event sequences відрізняються між runs. Це спостережувана nondeterminism upstream workers; identical states/pose counts не доводять byte-identical geometry. Retained frame IDs в обох runs є підмножиною recorded creation events. Initialization events `[0,2]` записані під час input frame 2, без backfill рядка 0. Mapping/whole-loop timing порожні в усіх 200 рядках кожного run.

CI Ubuntu/Windows × Python 3.11/3.12: **489 passed, 1 native skip**. Installed-backend sparse API check окремо **1 passed**. Historical pipeline: перевірено, що 13 hashes source artifacts не змінилися. Baseline config, upstream sources, existing summaries та WP3/WP4 code не змінювалися.

Automated ATE/RPE/resources і gap-aware success reporting належать наступним Y-02/Y-03; existing evaluators тут не змінюються. Shared status docs лишаються для IC1 за file boundaries поточного team plan; status row та evidence надано в PR.


## Y-02 recorded evaluation: clean smoke

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md). Історичні run IDs та результати збережено.

### Clean macOS smoke — 25 жовтня 2026

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


## Y-03 causal tracking result

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md). Історичні run IDs та результати збережено.

#### Recorded Y-03 result — 25 жовтня 2026

Implementation `f7245ff58f90b4e9e9572724d2db520728a841b2`; runs `yaropolk_y03_eval_smoke200_f7245ff_01` і `_02`: **ok**, `dirty_worktree=false`. [Summary](../results/summaries/yaropolk_y03_eval_smoke200.json), [state/latency timeline](../results/plots/yaropolk_y03_tracking_states_smoke200.png).

- Tracking success **198/200 = 0.99**. Frames 0–1: NOT_INITIALIZED; frames 2–199: OK. LOST / UNKNOWN / relocalization / observer exceptions / missing OK poses — 0.
- Causal trajectory: 198 usable poses, 196 GT associations, Sim(3) ATE RMSE **0.01103932 m**. Два GT-unassociated poses не рахуються як tracking loss.
- Gap-aware RPE: 195 candidate / 195 eligible / 0 excluded-gap pairs; translation RMSE **0.00554435 m**, rotation RMSE **0.37072596 deg**. Scale **1.37765435**, evaluation-only.
- Tracking warm-up=1, 199 samples: p50 **168.414083 ms**, p95 **909.267971 ms**, mean **293.951464 ms**. First-call sample **284.602 ms**; це не process cold start. `real_time_claim=false`.
- Full local CPU suite **535 passed, 1 native skip**; WP2 evaluation tests **28 passed**. `metrics.json`, `inputs.json`, `tracking_states.png` побітово однакові в обох evaluations. Всі раніше recorded Y-02 artifact hashes залишилися незмінними; timeline візуально перевірено.
- Failed real Y-03 evaluations: **немає**. Matplotlib створив temporary cache, бо default user cache недоступний у sandbox; це не вплинуло на output, детермінізм або status. Existing environments не змінювались.

Після merge актуального `develop` (включно з Yulian U-02) повторна combined local CPU suite: **602 passed, 1 native skip**; `git diff --check` пройшов. Зміни Y-03 відносно merged Y-02 залишаються у шести дозволених files.


## Y-05 / Y-06: B0 benchmarks і всі failures

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_BENCHMARK.md). Історичні run IDs та результати збережено.

### WP2: B0 development/selection і held-out benchmark (Y-05 / Y-06)

Owner / реалізація: Ярополк (WP2/WP5). Branch `feature/yaropolk-b0-development`; source/base `422172a4cf821d4a838d43426e1acd31c27827f5` (merged Y-04, PR #19). Усі чотири source runs та derived evaluations мають `dirty_worktree=false`. Source/algorithm code у Y-05 не змінено.

**Висновок Y-05 для презентації:** baseline працює на ширших desk inputs, але development має тривалий relocalization gap і лише ~76% OK frames. Низька ATE на available poses не означає повне успішне tracking. Цей результат offline. Подальший Y-06 held-out run завершено: 98.67% OK frames, causal ATE 3.86 cm / final ATE 1.61 cm (evaluation-only Sim(3)); 1.80 FPS. Повний Y-06 result і startup failure disclosure — нижче.

[JSON із hashes/provenance](../results/summaries/yaropolk_y05_benchmark.json), [CSV](../results/summaries/yaropolk_y05_benchmark.csv), [comparison plot](../results/plots/yaropolk_y05_benchmark.png), [state timeline](../results/plots/yaropolk_y05_tracking_states.png).

### Фіксований протокол

- Development: `tum_fr1_desk_development.json`, усі 573 frozen associations, три repeats. Selection: `tum_fr2_desk_selection50.json`, рівно 50 frozen associations, один run. Порядок: selection, потім dev 01/02/03, послідовно без competing SLAM jobs.
- Unchanged pinned pySLAM `96019cf`, ORB2/1000, DBOW3, Python core, `-O`, seed 0. Camera calibration походить із Y-04. No retuning / frame extension / model swap.
- Host: Apple M1 Pro, macOS 26.6.2, 32 GiB RAM. Native Python 3.11.16, NumPy 1.26.4, torch 2.6.0, Python OpenCV 4.11.0. У summaries збережено фактичні source environment fields.
- GT лише evaluation. Denominator success = **усі frozen input frames**, включно з initialization, LOST та RELOCALIZE. Numerator = native OK states.
- Final optimized та causal trajectories — різні rows/gauges. У таблиці нижче ATE causal; обидві ATE є у CSV. Один global Sim(3) evaluation fit, не metric scale recovery. RPE виключає pairs через non-OK/missing-pose inputs.
- Timing: `Slam.track` wall time, warmup=1 input row; p50/p95 включають решту states, з waits/hook overhead. Whole-run FPS включає startup/preflight/export/shutdown. Peak RSS — maximum individual-process child usage, не sum RAM workers.

### Числа

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

### Failure accounting

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

### GT window і official duplicate

Official fr2 GT містить два різні poses із timestamp `1311868229.576`. Вони далеко поза selection window **1311868164.3431811–1311868166.019133**. Для evaluation створено новий ignored reference з усіх GT rows у fixed input time range ±20 ms. Raw GT не редагувався; reference не містить averaging/deduplication, його timestamps строго increasing. Позавіконні rows не можуть бути timestamp candidates за тією самою tolerance, тому clipping не змінює associated candidates для наших inputs. Original/ref hashes і row counts є в summary.

### Повторити

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

### Cross-platform evidence

[Committed N-02 summary](../results/summaries/nazar_n02_e2e_smoke200_0fc564f.json): Docker/Linux на Windows host (Ryzen 9 8940HX), той самий pySLAM revision, smoke fr1/xyz200 — SLAM stage ok, 198 final poses, 0 upstream LOST. N-02 full comparison/pipeline має **failed** у записаному evidence; не приписуємо йому trajectory benchmark, якого там немає. Разом із нашим prior clean macOS Y-02 smoke це підтверджує роботу B0 на двох platforms. Wider Y-05 desk sequences інші; paired cross-platform speed/accuracy comparison не заявляється.

### Verification і deadline limitations

- 4 source runs + 4 evaluations: clean source commit, status ok. Additional dev01 re-evaluation: metrics.json, inputs.json та PNG **byte-identical**; run_id/started_at закономірно нові.
- Full CPU suite на тому самому source перед evidence-only Y-05: **688 passed, 1 native skip**. Plot legends/state ranges перевірено візуально; source/evaluation hashes перевірені.
- Frozen configs, seed і frame counts незмінні; жодного install/download або source edit у Y-05.
- На момент Y-05 held-out input/Y-06 був skipped за deadline decision користувача; historical Y-05 summaries збережені. Подальший Y-06 виконано нижче. Y-05 не є held-out validation, повним WP5 чи real-time system. Dense B0/B1/P1 wider comparison лишається окремою роботою Назара / команди.
- Contribution: Ярополк — WP2/WP5 benchmark execution/evidence; незмінені evaluators Юліана та contracts команди reused. Shared status docs залишено для integration checkpoint.

### Y-06: initial startup failure (25 жовтня 2026)

**Первинна спроба: startup failure, zero tracked frames.** Run `yaropolk_y06_heldout2488_c08833f_01`, clean source `c08833f0b287cecbdb72953796cd0dcd253b296b`, містить IC3 freeze (PR #25, `4021a02`) та окремий preflight fix PR #27 (`bd0a17e`). Y-05 historical summaries не змінено; актуальний successful Y-06 retry наведено після цієї первинної failure disclosure.

- Archive: 1,483,556,251 bytes, SHA-256 `c7cd8e1afb87c80e5744a356214819b110fa09b4744fa4ba0cc2382f9ba59e9c`; усі 5,098 extracted files побайтово збігаються. Frozen inputs: 2,488 frames / 4,976 RGB-depth image hashes; index hashes та manifest збігаються.
- Config SHA-256 `3545878e88134b33caf89b3a5a879372381d98a08bd637260ca4e5dce23971eb` = IC3 hash; seed 0, pySLAM `96019cf`, ORB2/1000, DBOW3, Python core `-O`, native macOS arm64. Algorithm/config/source не змінено в Y-06; timeout 14,400 s — operational guard.
- До створення run: archive був відсутній, потім valid official GT boundary помилково блокував preflight. Окремий PR #27 виправив лише metadata validation: три initial RGB frames раніше GT range тепер записуються як limitation, всі inputs збережені. Full CPU suite: **698 passed, 1 native integration skipped**; чотири CI checks passed.
- Після запуску native worker видав `OMP: Error #179: Function Can't open SHM failed` під час initialization. Loop-closing readiness не настала; `trajectory_all.csv` та `timing.csv` містять нуль observations. **Гіпотеза:** shared-memory restriction execution sandbox; unrestricted retry на момент цієї первинної спроби ще не виконано; подальший результат нижче. Stalled upstream process зупинено SIGTERM, runner сам записав terminal `failed` (`upstream_exit: -15`). Finished `run.json` не редагувався.
- Wall clock до зупинки: 199.445 s; peak individual-process RSS: 743,489,536 bytes. Це startup-failure diagnostics; FPS, ATE/RPE, tracking success та p50/p95 **null**, не нульова якість і не performance benchmark. Cold start to first tracked frame не instrumented. Real-time claim відсутній.
- Evidence: [JSON](../results/summaries/yaropolk_y06_heldout.json), [CSV](../results/summaries/yaropolk_y06_heldout.csv), [startup-failure plot](../results/plots/yaropolk_y06_tracking_states.png). Full runs/logs локальні й ignored. Native launch/resource driver — локальний `outputs/wp2/` / temporary orchestration; resource schema та unchanged APIs ті самі, що Y-05.

**Disclosures.** Superseded runner `wp2_heldout2488_4484fd7` failed у upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`), без trajectory/metrics, нічого не tuned. Committed N-06 `nazar_n06_heldout2488_da3_e561d8c_01` failed на GT preflight з нулем SLAM frames; PR #27 виправив цей blocker. Поточна local startup failure також збережена; ця первинна спроба не містить retry чи tuning. Користувач згодом явно дозволив execution-environment exception до D-5: retry поза sandbox з незмінними параметрами та новим run ID (нижче). GT прочитано тільки для integrity/timestamp validation; evaluation не запускалось, жодна GT pose/depth не вплинула на SLAM.


### Y-06: authorized native retry — final held-out evidence

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

## N-05 development / selection

Повний preregistered grid, selection failure, model-only rows і derived freeze збережено в [DEVELOPMENT_BENCHMARK](DEVELOPMENT_BENCHMARK.md); machine-readable evidence — `results/summaries/nazar_n05_*.{json,csv}`. Цей файл лишається на original path, оскільки його вимагає frozen config/test.


## Depth-only ablations і N-04 gate

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/DEPTH_ABLATIONS.md). Історичні run IDs та результати збережено.

### WP5: незалежні depth-only ablations

Назар, 23 жовтня 2026. Ці результати не є map/completeness/end-to-end benchmark.

**N-04 update (25 жовтня 2026).** Файли й три `wp5_*` summaries перенесено з local `047992e` без змін і повторно перевірено (§N-04 нижче). Додано pooled prediction-only thresholds для map ablation і UniDepth smoke P1 з D-3 pipeline gate. Історичні секції нижче описують стан 23 жовтня.

### DA3 resolution

Ті самі 50 frozen development frames fr1/desk, raw metric depth, однакові 640×480 evaluation masks, seed 0, 10 prewarm calls:

| process_res | native grid | AbsRel ↓ | RMSE m ↓ | δ1 ↑ | warm p95 ms ↓ | peak allocated GiB ↓ |
|---:|---|---:|---:|---:|---:|---:|
| 504 | 504×378 | 0.094060 | 0.188398 | 0.964910 | 95.15 | 1.5449 |
| 384 | 378×294 | 0.096122 | 0.212253 | 0.947197 | 84.74 | 1.4244 |

Evidence: `results/summaries/wp5_da3_resolution_development50.json`, source runs `wp1_dev50_da3_a9ccd5d` та `wp5_dev50_da3_r384_a9ccd5d`. Менша resolution зменшила p95/VRAM, але погіршила quality; один run на конфіг, GPU latency має outliers. Це не підстава для зміни зафіксованого selection protocol заднім числом.

Відтворення 384: generic geometry CLI, `--model da3 --manifest data/manifests/tum_fr1_desk_spike50.json --split development --frames 50 --prewarm 10 --process-res 384 --run-id <new-id>`; 504 — default process_res. Числа беруться з metrics/timing; summary перевіряє ті самі frame identities і SHA masks.

### UniDepth confidence

Пороги — prediction-only quantiles (100/75/50%), обрані до GT-scoring. Higher confidence = 1/(1+native error). Quality рахується на retained GT-valid pixels; coverage відносно всіх GT-valid, тому expected trade-off явний.

| Retain requested | GT-valid coverage | AbsRel ↓ | RMSE m ↓ | δ1 ↑ |
|---:|---:|---:|---:|---:|
| 100% | 100% | 0.041152 | 0.124743 | 0.984960 |
| 75% | 80.81% | 0.036673 | 0.094141 | 0.988356 |
| 50% | 54.65% | 0.034753 | 0.080510 | 0.989739 |

Evidence: `wp5_unidepth_confidence_development50.json`. Source `wp1_dev50_unidepth_a9ccd5d` — clean successful early run; його nullable RAM metadata не використовуються для paired selection (цей run не змінений). Threshold ties залишаються; фактичний pixel count записаний.

DA3 не повертає confidence: diagnostic має `status=skipped`, без синтетичної confidence (`wp5_da3_confidence_unavailable.json`).

```powershell
.venv/cpu/Scripts/python.exe scripts/analyze_confidence.py --run results/runs/<source> --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk --output results/summaries/<new-summary>.json
```

### Що потребує WP2/WP3

Keyframe interval у реальному tracking/fusion; P1-raw/global/window; map F-score/completeness і temporal drift. Очікувані artifacts — docs/REPRODUCIBILITY.md. Не підмінюємо їх depth-only score і не робимо real-time claim.

### N-04: re-verification, thresholds і UniDepth smoke P1 (25 жовтня 2026)

Branch `feature/nazar-n03-n04`. Implementation commit `5d11ce6`, configs/thresholds commit `8378365`. Усі runs з clean commit (`dirty_worktree=false`), RTX 5070 Laptop.

#### Перевірка перенесених чисел

Evidence: `results/summaries/nazar_n04_ported_evidence_check_5d11ce6.json`.

- **DA3 resolution 384/504:** metrics, counts, warm p95 і VRAM у `wp5_da3_resolution_development50.json` збігаються з immutable source runs з різницею 0.0, SHA-256 `run.json` збігаються, paired masks однакові.
- **DA3 confidence:** у всіх predictions `wp1_dev50_da3_a9ccd5d` `confidence=None`; `status=skipped` правильний.
- **UniDepth confidence, rank-equivalence.** Старий run зберігав `c = 1/(1+e)`, поточний adapter зберігає `c = −e`. Функція `−e = 1 − 1/c` строго зростає, тому ранжування pixels однакове, а quantile masks відрізняються лише через float32 ties. Новий clean run `nazar_n04_dev50_unidepth_5d11ce6_01` дає bit-identical depth/valid masks з `wp1_dev50_unidepth_a9ccd5d` на 50/50 кадрах. `analyze_confidence.py` на новому run (`nazar_n04_unidepth_confidence_development50_5d11ce6.json`):

| Retain | `n_pred_valid` ported → rerun | `n_evaluated` ported → rerun | max \|Δ metric\| |
|---:|---:|---:|---:|
| 100% | 15360000 → 15360000 | 11738990 → 11738990 | 0 |
| 75% | 11520012 → 11520008 (−4) | 9486781 → 9486777 (−4) | 3.4e-7 |
| 50% | 7680022 → 7680010 (−12) | 6415175 → 6415164 (−11) | 9.4e-7 |

Старий mapping має менше унікальних значень (12.89 M проти 14.18 M на 50 кадрах), тому на межі quantile лишається більше ties, а ties зберігаються. Висновки таблиці 23 жовтня не змінюються.

#### Pre-registered confidence thresholds (D-4)

Джерело — лише predictions dev50 UniDepth (`nazar_n04_dev50_unidepth_5d11ce6_01`, fr1/desk spike50). GT не відкривався. Значення pooled по всіх valid pixels 50 кадрів, `numpy.quantile` linear; fusion зберігає pixels з `confidence >= threshold`:

| Retain | Quantile | Threshold (`−error`) | Retained on dev50 |
|---:|---:|---:|---:|
| 75% | 0.25 | −0.6916478276252747 | 75.00003% |
| 50% | 0.50 | −0.6456854343414307 | 50.00003% |

`analyze_confidence.py --pooled-thresholds --run <run> --output <json>` → `results/summaries/nazar_n04_confidence_thresholds_5d11ce6.json`. Пороги записано в `configs/mapping_comparison.nazar.confidence.json` і `configs/pipeline.nazar.smoke200.unidepth.json` до будь-якого P1 run (commit `8378365`).

#### UniDepth smoke P1 і D-3 pipeline gate — **FAIL**

Run `nazar_n04_e2e_smoke200_unidepth_8378365_01`, запущений один раз з окремого runtime clone (layout з N-02). SLAM stage reused: `nazar_n02_e2e_smoke200_0fc564f_02.slam` без копіювання, SHA-256 `run.json` `2e4afa27…` збігається з N-02 summary, усі 21 файли stage byte-identical до і після run.

| Stage | Status |
|---|---|
| SLAM (reused N-02) | ok |
| Geometry UniDepth V2, 200 frames | ok: AbsRel 0.0409, RMSE 0.121 m, δ1 0.985 (raw metric, evaluation-only GT); warm median/p95 78.5/87.7 ms; peak VRAM 1.80 GiB |
| Alignment/fusion/comparison | **не стартували** |
| Pipeline | **failed**: `unsupported_preprocess: prediction must declare its pixel grid` |

- **Gate (plan D-3):** model-ID check 18/18 keyframes ok, OOM немає, але незмінний `alignment/correspondences.py:prediction_grid` відхилив grid усіх 18 keyframes. UniDepth adapter не декларує `pixel_grid`/`intrinsics_convention`; `raw_distorted` виводиться лише для `library=depth_anything_3`. Це "grid rejection by the unchanged mapping code", тобто **gate fail**.
- **Рішення (механічне, D-3):** fallback trigger спрацював. **Primary для N-05/N-06 — DA3METRIC-LARGE `process_res=504`**, без окремого рішення. UniDepth лишається другою моделлю в N-05 primary-vs-fallback ablation.
- **Rerun не робився.** Навіть з виправленим metadata gate на цьому SLAM stage не пройшов би: keyframe 16 (frame 195) не має GT pose у межах 20 ms (найближчий за 40.8 ms). Comparison впав би так само, як у N-02, незалежно від моделі. Tolerance не змінено, keyframes не відкидались.
- **Confidence ablation:** map children не запускались. Coverage порогів на smoke predictions (GT-free): 73.7% / 43.9% valid pixels на 18 keyframes, 71.2% / 40.6% на всіх 200 кадрах.
- **Наступний крок (не в цьому PR, гіпотеза щодо обсягу):** окремий focused fix у `adapters/unidepth_v2.py` (Nazar), щоб declare `pixel_grid="raw_distorted"` та `intrinsics_convention="pixel_centers_integer"`, з regression test через `prediction_grid`. Без нього UniDepth rows у N-05 впадуть так само.

Evidence: `results/summaries/nazar_n04_e2e_smoke200_unidepth_8378365.json`. Real-time claim немає: це component latency, UniDepth p95 > 33.3 ms (D-7).


## N-02: independent reproduction і supplemental comparison

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/NAZAR_REPRODUCTION.md). Історичні run IDs та результати збережено.

### N-02: незалежне відтворення smoke-pipeline на другій машині

- **Chunk:** N-02 (`docs/EXPERIMENTS.md` §5).
- **Виконавець:** Nazar, як незалежний reproducer WP4 (Yulian) і WP2 runtime (Yaropolk). Ownership не змінюється.
- **Reference:** `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`, run `yulian_tum_e2e_f200_20261025_01`, clean `4952e37`.
- **Підсумок:** **disclosed failure.** SLAM, DA3 geometry і global alignment/fusion завершилися `ok` з clean commit. GT-based comparison stage (B0/B1/P1 rows, ATE/RPE, map metrics) впав, тому pipeline run має status `failed`. Зміна evaluation rules виходить за межі N-02, а повторні запуски заради іншого набору keyframes заборонені, тож PR містить evidence і blocker report.
- **Evidence:** `results/summaries/nazar_n02_e2e_smoke200_0fc564f.json` (з source hashes), `results/plots/nazar_n02_residuals.png`, config `configs/pipeline.nazar.smoke200.docker.json`.
- **Оновлення (supplemental, §10):** після окремого evaluator fix Юліана (PR #21, `9617bc4`) comparison-only run `nazar_n02_gt_coverage_eval_9617bc4_01` завершився `ok` на тих самих незмінених outputs. GT coverage 17/18 retained keyframes. Оригінальний failed run і текст вище не змінено.

### 1. Середовище

| Компонент | Nazar (N-02) | Yulian (reference) |
|---|---|---|
| CPU | AMD Ryzen 9 8940HX | Intel64 Family 6 Model 154 |
| GPU / VRAM | RTX 5070 Laptop, 8151 MiB | RTX 3070 Ti Laptop, 8192 MiB |
| NVIDIA driver | 610.74 | 617.14 |
| RAM | 31.2 GB | 39.7 GB |
| Docker | Desktop 29.8.2, WSL2 6.18.54.1, VM 32 vCPU / 15.2 GiB | WSL2 6.18.54.1 |
| SLAM container | `rt-mapping-wp2-nazar`, `--memory=10g --cpus=4 --shm-size=1g` | `rt-mapping-wp2-yulian`, ті самі limits |
| SLAM env | Python 3.11.17, NumPy 1.26.4, torch 2.6.0+cpu, OpenCV 4.11.0.86 | те саме |
| DA3 env | `.venv`: Python 3.11.16, torch 2.11.0+cu128, CUDA 12.8, DA3 `3d835ec` | `.local/da3-venv`: Python 3.12, torch 2.7.1+cu118 |
| Checkpoint | `model.safetensors@sha256:bbea5b0b…324776` (перевірено) | те саме |

**Docker image.** `rt-mapping-wp2:96019cf` зібрано заново з `containers/wp2.Dockerfile` (base digest `18d373e1…`), exit 0. Native compile тривав 3129 s, ORB vocabulary SHA-256 check пройшов. Image ID `sha256:f975805a9c6cc4be3d4741053d5b2150dd4578a3f7b254bc28807acfd5e7b5f6`, 13.1 GB. Preflight `check_wp2_environment.py --probe-runtime`: `ok` (dataset, source revision, runtime). Opt-in native sparse test: 1 passed.

### 2. Runtime-налаштування (без змін source/protocol)

1. **Config:** копія `configs/pipeline.tum.windows-docker.json`. Змінено лише container name і DA3 interpreter (`.venv\Scripts\python.exe`).
2. **Standalone clone замість git worktree.** У worktree файл `.git` вказує на Windows path, і `git rev-parse` всередині Linux container не працює (attempt 1). Тому run запускався з окремого clone того самого branch/commit.
3. **Dataset усередині repository.** WP2 preflight відхиляє `data/raw`, якщо resolved path виходить за межі repo root, тому junction не підходить. fr1/xyz archive і extraction скопійовано в ignored `data/raw/`. SHA-256 archive `a0236d97…` збігається з manifest.
4. **`.venv` і `checkpoints` як junctions** на перевірені локальні environment/cache. Усередині container вони видимі як symlinks, а `.gitignore` патерни з `/` на кінці їх не покривають. Тому в локальний `.git/info/exclude` clone додано `/.venv` і `/checkpoints` (не tracked). Host і container показують clean tree; `dirty_worktree=false` у всіх stages.
5. **Пам'ять.** Перед фінальним run зупинено (не видалено) два сторонні compose-контейнери `pandora-postgres-1` і `pandora-redis-1` (project `pandora`). Після цього вільно 16.6 GB, тому restart Docker Desktop не знадобився. Під час run free RAM була 12.8–15.9 GB (84 samples по 5 s).

### 3. Усі спроби

| Run ID | Commit | Status | Причина |
|---|---|---|---|
| `nazar_n02_e2e_smoke200_65571cc_01` | `65571cc` | failed | SLAM adapter exit 2: `git rev-parse` усередині container (worktree `.git` → Windows path). Збережено в N-02 worktree. |
| `nazar_n02_e2e_smoke200_65571cc_02` | `65571cc` | failed | SLAM stage ok. Geometry launch `[WinError 2]`: на цьому host `CreateProcess` не знаходить відносний executable `.venv/Scripts/python.exe` з `/` (відтворено поза pipeline, також у main checkout). Виправлено лише в config (backslashes), commit `0fc564f`. Чому forward-slash path працював у Yulian — гіпотеза: інший host interpreter або спосіб запуску. |
| `nazar_n02_e2e_smoke200_0fc564f_01` | `0fc564f` | interrupted | SLAM stage ok. Launcher зупинено під час DA3 inference memory-pressure reaper'ом Claude Code. `run.json` лишився зі status `running` і **не редагувався**. |
| `nazar_n02_e2e_smoke200_0fc564f_02` | `0fc564f` | failed | SLAM ok, geometry ok, global alignment/fusion ok. Comparison: `all retained keyframes need distinct associated GT poses for a shared comparison`. |

Усі run directories збережено byte-for-byte; SHA-256 до і після фінального run збігаються. SHA-256 `run.json` кожної спроби є в summary.

### 4. Результат по stages (`nazar_n02_e2e_smoke200_0fc564f_02`)

| Stage | Status | Elapsed |
|---|---|---|
| SLAM (Docker, pySLAM `96019cf`) | ok | 376.9 s (у reference 303.5 s) |
| Geometry (DA3METRIC-LARGE, CUDA) | ok | 53.4 s (у reference 71.1 s) |
| comparison.global (alignment + fusion) | ok | 6.8 s wall |
| comparison (B0/B1/P1, GT evaluation) | **failed** | — |
| pipeline | **failed** | — |

### 5. Діагностика failure

- `src/rt_mapping/evaluation/oracle.py` (`load_oracle_inputs`, код Yulian без змін) вимагає GT pose у межах 20 ms для **кожного** retained keyframe.
- У цьому run SLAM утримав 18 keyframes (reference: 22). Keyframe 16 (frame 195, t = 1305031108.876515) лежить у ~110 ms розриві `groundtruth.txt` fr1/xyz (між 1305031108.8357 і 1305031108.9458); найближчий GT pose за 40.8 ms. 17 з 18 keyframes associated.
- Набір keyframes у reference run цей розрив не зачепив. Вибір keyframes у upstream pySLAM недетермінований між машинами (seed policy у SLAM `run.json`).
- **Класифікація:** обмеження robustness WP4 evaluation, а не помилка N-02 runtime. Виправлення (виключати unmatched keyframes з GT evaluation, інтерполювати GT або змінити tolerance) змінює evaluation rules. За планом (D-2, stop conditions N-02) це окремий focused `fix/nazar-*` PR з regression test, з повідомленням Yulian. У N-02 нічого не виправлено, thresholds не змінено, повторних запусків для іншого набору keyframes не було.

### 6. Порівняння з reference (cross-machine variation, не parity)

Повна таблиця з абсолютною і відносною різницею — у summary (`comparison_with_reference.rows`).

| Метрика | Yulian | Nazar | Rel. diff |
|---|---|---|---|
| SLAM processed / lost frames | 200 / 0 | 200 / 0 | 0 |
| SLAM final poses | 198 | 198 | 0 |
| First / last pose timestamp | 1305031102.275326 / …109.011269 | ті самі | 0 |
| Sparse landmarks | 1277 | 1130 | −11.5% |
| Keyframes | 22 | 18 | −18.2% |
| Observations | 8893 | 7035 | −20.9% |
| Depth AbsRel | 0.092655 | 0.092649 | −0.007% |
| Depth RMSE, m | 0.177196 | 0.177157 | −0.022% |
| Depth δ1 | 0.964949 | 0.965018 | +0.007% |
| Evaluated pixels | 16730870 | 16730870 | 0 |
| Alignment scale | 1.1921 | 1.2241 | +2.7% |
| Inliers / pairs | 5044 / 6571 | 3746 / 5334 | −25.7% / −18.8% |
| Inlier ratio | 0.768 | 0.702 | −8.5% |
| Median / p95 residual, m | 0.0309 / 0.0873 | 0.0313 / 0.0869 | +1.5% / −0.5% |
| Withheld median / p95 residual, m | 0.0388 / 0.313 | 0.0501 / 0.503 | +29% / +61% |
| Fused voxels (map points) | 72887 | 72115 | −1.1% |
| DA3 warm median / p95, ms | 119.7 / 134.1 | 73.0 / 83.1 | −39% / −38% |
| Fusion median / p95 per keyframe, ms | 71.9 / 121.1 | 85.9 / 114.2 | +19% / −6% |

**Не відтворено:** B0 Sim(3) і P1 SE(3) ATE/RPE та всі comparison rows (B0-shared-scale, B1-oracle, P1-global, P1-raw, P1-keyframes-2/5), бо comparison stage зупинився до trajectory evaluation.

Висновки:
- DA3 depth відтворюється майже ідентично: однакові кількості pixels, різниця метрик ≤ 0.03% (інший torch/CUDA і GPU).
- Різниця SLAM sparse map і alignment inputs пояснюється іншим набором keyframes. Scale відрізняється на 2.7%.
- Timing стосується окремих компонентів на іншому залізі. Це **не** real-time claim (plan D-7): DA3 warm p95 = 83.1 ms > 33.3 ms frame budget.

### 7. Команди

```powershell
docker build -f containers/wp2.Dockerfile -t rt-mapping-wp2:96019cf .
docker run -d --name rt-mapping-wp2-nazar --shm-size=1g --memory=10g --cpus=4 --mount "type=bind,source=$((Get-Location).Path),target=/workspace" rt-mapping-wp2:96019cf
docker exec rt-mapping-wp2-nazar python scripts/check_wp2_environment.py --pyslam-root /opt/pyslam --pyslam-python /usr/local/bin/python --probe-runtime
docker exec --env WP2_NATIVE_SPARSE_TEST=1 --env WP2_PYSLAM_ROOT=/opt/pyslam rt-mapping-wp2-nazar python -O -m unittest discover -s tests -p test_pyslam_sparse_native.py -v
.venv\Scripts\python.exe scripts\run_pipeline.py --config configs\pipeline.nazar.smoke200.docker.json --run-id nazar_n02_e2e_smoke200_0fc564f_02
```

Docker команди з `--env /opt/...` треба запускати з PowerShell: Git Bash (MSYS) переписує `/opt/pyslam` у Windows path, і тоді `pyslam` не імпортується.

### 8. Blocker і наступний крок

- **Blocker:** повний B0/B1/P1 comparison не можна відтворити на цьому run без зміни WP4 evaluation (обробка keyframes без GT у розривах `groundtruth.txt`).
- **Рекомендація:** окремий `fix/nazar-*` PR в `evaluation/oracle.py`/`comparison_run.py` з явно задокументованим правилом для keyframes без GT і regression test, з повідомленням Yulian. Після merge — новий run_id за D-5-подібним правилом (обидва runs звітуються). Порядок N-04 це не блокує: SLAM stage `nazar_n02_e2e_smoke200_0fc564f_02.slam` має status `ok`, і його можна reuse.

### 9. Обмеження

- Pipeline run має status `failed`. Trajectory і map metrics не відтворено.
- Один run; повтори для оцінки variance не проводились.
- Інше DA3 environment (torch 2.11+cu128), ніж у reference.
- GT використовується лише в evaluation code; на результатах нічого не тюнилось.
- Немає real-time claim і немає metric-scale claim з alignment.

### 10. Supplemental comparison-only evaluation (після PR #21)

- **Підстава:** `docs/EXPERIMENTS.md` §6 (handoff Юліана). N-02 завершений лише після окремого missing-GT evaluator fix (PR #21, merge `9617bc4`), а не через зміну N-02 runtime.
- **Run:** `nazar_n02_gt_coverage_eval_9617bc4_01`, status **`ok`**, `git_commit` `9617bc4`, `dirty_worktree` false. Запущено один раз з окремого clean detached worktree на `9617bc4`. Run directory локальний і ignored.
- **Що виконано:** лише `scripts/run_mapping_comparison.py` (CPU alignment/fusion children + GT evaluation) на SLAM і geometry stages run `nazar_n02_e2e_smoke200_0fc564f_02`. SLAM, DA3 і оригінальний alignment/fusion не перезапускались. Config `configs/mapping_comparison.json` (tolerance 0.02 s без змін).
- **Незмінність source:** 10 SHA-256 з §6 (run, SLAM stage, sparse export, keyframes, geometry run/metrics, comparison run, `alignment.json`, `groundtruth.txt`, fr1/xyz archive) збіглися до і після run. Хеші всіх 240 файлів source run directory до і після побайтово однакові.
- **Alignment:** scale 1.224085382515751, inliers 3746 / 5334 pairs. Збігається з оригінальним `comparison.global`.
- **GT coverage:** 17/18 retained keyframes (0.944444). Виключено frame 195 (t = 1305031108.876515), reason `no_gt_pose_within_tolerance`, nearest GT pose за 0.040815 s. Незалежна перевірка по `groundtruth.txt`: розрив 110.1 ms між 1305031108.8357 і 1305031108.9458. Той самий eligible set для всіх методів.

| Method | Points | Accuracy, m | Completeness, m | Chamfer-L1, m | F@5cm | ATE SE(3), m | RPE trans, m |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0-shared-scale | 982 | 0.0619 | 0.2322 | 0.1470 | 0.249 | 0.0177 | 0.0148 |
| P1-global | 57837 | 0.0976 | 0.0794 | 0.0885 | 0.479 | 0.0177 | 0.0148 |
| P1-raw | 61209 | 0.0985 | 0.0810 | 0.0897 | 0.456 | 0.0418 | 0.0292 |
| B1-oracle (GT depth) | 33939 | 0.0244 | 0.0258 | 0.0251 | 0.876 | 0.0177 | 0.0148 |
| P1-keyframes-2 | 38358 | 0.0946 | 0.0934 | 0.0940 | 0.446 | 0.0177 | 0.0148 |
| P1-keyframes-5 | 26400 | 0.0938 | 0.0996 | 0.0967 | 0.447 | 0.0177 | 0.0148 |

B0 Sim(3) diagnostic (evaluation-only scale 1.3535): ATE RMSE 0.00966 m, RPE translation 0.01320 m, rotation 0.765°, 17 poses / 16 pairs. Scope: retained keyframes, не all-frame tracking.

- **Evidence:** `results/summaries/nazar_n02_gt_coverage_eval_9617bc4.json` (pre/post source hashes, SHA-256 `run.json`, `metrics.json`, `comparison.csv`, `report.md`, `trajectory_evaluation.json`, `inputs.json`, `evaluation/*.json`, coverage, rows).
- **Позначення:** cross-machine reproduction на машині Nazar. Це не пряма рівність із reference Юліана (`yulian_tum_e2e_f200_20261025_01`, 22/22 keyframes): набори keyframes і eligible frames різні. Sim(3) ATE не доводить metric scale. B1 — oracle control. Real-time claim немає. Нічого не тюнилось.


## N-06: original failure, authorization і final rerun evidence

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/HELDOUT_BENCHMARK.md). Історичні run IDs та результати збережено.

### N-06: held-out benchmark (fr3/long_office_household)

Назар, 25 жовтня 2026. Chunk N-06 з `docs/EXPERIMENTS.md`; frozen protocol — `docs/EXPERIMENTS.md`, `configs/benchmark_frozen.json`.

**Статус (оновлено 26 жовтня): disclosed failure, partial evidence.** Перший run (`e561d8c_01`) зупинився на WP2 preflight (§1–§6, текст збережено). Дозволений D-5 rerun `nazar_n06_heldout2488_da3_48ddd4c_01` після fix Ярополка (§7) пройшов SLAM, DA3 і P1-global alignment/fusion, але comparison упав з **новою** причиною: P1-raw ablation перевищив frozen `max_voxels` (§8). Depth, trajectory (B0, P1-global) і performance є. Map metrics B0/B1/P1 відсутні. Нового rerun немає, нічого не tuned.

### 1. Freeze до доступу

| Item | Значення |
|---|---|
| Freeze | `configs/benchmark_frozen.json`, commit `4021a02`, merged PR #25 → `develop` `847c662` |
| N-05 | PR #24, merge `ef5e682` |
| N-06 branch | `feature/nazar-heldout-benchmark` з `847c662` |
| Config | `configs/pipeline.nazar.heldout.json` = `benchmark_frozen.json` → `heldout.pipeline_config` (scripted diff 0 рядків; `tests/test_benchmark_frozen.py`) |
| Run commit | clean `e561d8c` (містить freeze) |
| Перший доступ до fr3 | копіювання fr3 у runtime clone після merge `847c662` |

### 2. Run

| Run ID | Commit | Status | Причина |
|---|---|---|---|
| `nazar_n06_heldout2488_da3_e561d8c_01` | `e561d8c` | **failed** | `pipeline_failed: slam adapter exited 2`; `logs/slam.log`: `Rejected: groundtruth time range does not cover associated RGB frames` |

Запущено один раз (start 2026-10-25T19:32:36Z, failure через ~387 s, з них preflight hashing). SLAM frames 0, DA3 inference 0, alignment/fusion/comparison не виконувались, B0 evaluation неможлива (немає SLAM stage). Evidence: `results/summaries/nazar_n06_heldout2488_e561d8c.json`.

### 3. Діагностика

- Check: `src/rt_mapping/slam/setup.py:155` (Track Y; рядок з `24b16e2`, збережений Y-04) вимагає, щоб GT time range покривав усі associated RGB frames.
- Official fr3 `groundtruth.txt` починається о 1341847980.79 s, перший RGB frame — 1341847980.722988 s: 3 з 2488 frames раніше за GT (після кінця — 0). Лише 2 frames не мають GT pose у межах 20 ms.
- B0 SLAM не використовує GT; merged policy PR #21 уже виключає keyframes без GT pose і записує coverage. Тому preflight відкидає валідний official recording ширше, ніж потрібно для evaluation. Це **гіпотеза щодо правильного fix**, не змінений код.
- Y-04 held-out real-data preflight був explicitly skipped (input недоступний на машині Ярополка), тому до IC3 це не виявилось.
- Fix належить Track Y (`slam/`); Track N не редагує SLAM code (plan §3). Тут нічого не змінено.

GT access: preflight прочитав GT timestamps; діагностика порівняла лише timestamps GT/RGB. Жодна GT pose/depth не використана для metric.

### 4. Performance і real-time verdict

Held-out performance table недоступна: жоден stage не виконався. Verdict за D-7: **offline**. Підстава — N-05 dev components уже перевищують 33.3 ms budget (`Slam.track` warm p95 2312 ms; DA3 504 p95 97.9 ms на RTX 5070 Laptop, 640×480 input, 30 Hz), а pipeline послідовний. Held-out p95/FPS не заявляються.

### 5. Наступний крок (D-5)

1. Ярополк: focused fix PR у `slam/setup.py` (наприклад, дозволити часткове GT coverage з явним звітом, як для duplicate timestamps у `7492ffa`), з regression test; held-out preflight на реальних даних.
2. Після merge: новий branch від `develop`, той самий frozen config (scripted diff порожній), новий run ID `nazar_n06_heldout2488_da3_<sha7>_01` з commit, що містить fix; B0 evaluation `nazar_n06_heldout2488_b0eval_<sha7>_01`; performance table. Обидва runs звітуються. Параметри не змінюються.

### 6. Disclosures

- Цей run: failed на preflight (вище).
- Superseded runner `wp2_heldout2488_4484fd7` (clean `4484fd7`) failed в upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`); без trajectory і metrics; нічого не tuned.
- Held-out результати нічого не вибирали і не змінювали. F-N1/F-N2 не розпочато.

### 7. D-5 rerun authorization (записано до запуску)

- **Bug fix власника коду:** Ярополк, PR #27 (`bd0a17e`, merge `c08833f`) і PR #29 (`78ecfe5`, merge `242c0cb`). `slam/setup.py` більше не вимагає повного покриття RGB time range GT: усі frozen RGB inputs лишаються в SLAM, coverage у межах 20 ms звітується явно (matched/unmatched, excluded frame IDs, reasons). Нуль GT overlap і далі дає failure (`NoGroundTruthOverlap`). Tolerance зафіксовано на 0.02 s (`GT_MATCH_TOLERANCE_S`). CI 4/4 green в обох PR.
- **Аудит Nazar:** diff `e561d8c..242c0cb` у `src/`, `scripts/`, `configs/`, `containers/` зачіпає лише `slam/setup.py`, `evaluation/trajectory.py` (coverage helper), `evaluation/slam_run.py` і два WP2 CLI (звіт coverage, 20 ms enforced). Geometry, alignment, fusion і comparison code не змінено.
- **Frozen protocol без змін:** SHA-256 `configs/benchmark_frozen.json` `bf990a4a…213407` = freeze `4021a02`. `configs/pipeline.nazar.heldout.json` `9cf9a0d7…0b97` = версія run `e561d8c`. `wp2_pyslam_heldout.json` `3545878e…71eb`, `offline_mapping.json` `93c0c363…f9fb`, `mapping_comparison.json` `06c4d5f5…e3aa2`, held-out manifest `42b1149d…0ee3`. Checkpoint `bbea5b0b…324776`, Docker image `sha256:f975805a…f5f6`, fr3 archive `c7cd8e1a…e9c`, `groundtruth.txt` `e255d5d9…533f` (= archive member і Y-06).
- **Rerun:** один запуск з commit цього branch, новий run ID `nazar_n06_heldout2488_da3_<sha7>_01`; failed run `nazar_n06_heldout2488_da3_e561d8c_01` не змінюється. Модель, `process_res`, keyframe interval, window, confidence, thresholds і tolerance не змінюються. Held-out результат нічого не вибирає.

### 8. D-5 rerun: результат

| Item | Значення |
|---|---|
| Run ID | `nazar_n06_heldout2488_da3_48ddd4c_01` (новий; `e561d8c_01` не змінено, SHA-256 `run.json` той самий) |
| B0 evaluation | `nazar_n06_heldout2488_b0eval_48ddd4c_01` (frozen evaluator defaults + `--plot`), status `ok` |
| Commit | clean `48ddd4c` (містить freeze `4021a02`, fix `242c0cb` і §7), `dirty_worktree` false у всіх stages |
| Запуск | один раз, 2026-10-25T20:54:31Z, standalone runtime clone на `48ddd4c` |
| Status | **failed**: `comparison_failed: fusion_failed: map_capacity_exceeded: voxel limit exceeded; increase size/limit explicitly` |

#### 8.1 Stages

| Stage | Status | Elapsed |
|---|---|---|
| SLAM preflight + SLAM (Docker, pySLAM `96019cf`) | ok | 5316 s |
| Geometry (DA3METRIC-LARGE @504, 2488 frames) | ok | 620 s |
| comparison.global (P1-global alignment + fusion) | ok | ~34 s alignment/input + fusion 282 keyframes |
| comparison.raw (P1-raw ablation, scale 1) | **failed**: `map_capacity_exceeded` | — |
| comparison.k2 (P1-keyframes-2), oracle (B1), map evaluation | не запускались | — |

#### 8.2 Діагностика failure

- Check: `src/rt_mapping/fusion/voxel.py:66` (WP4, Юліан). Ліміт `max_voxels` 2,000,000 при voxel 0.02 m з `configs/offline_mapping.json` (frozen, SHA-256 у `benchmark_frozen.json`).
- P1-global map уже має 1,818,552 voxels (282 keyframes, 13.4 M input points). Recovered scale 2.193. P1-raw лишає pose scale 1, тому metric depth fuse'иться на в ~2.2 раза коротших translations, і поверхні різних keyframes не перекриваються. Це **гіпотеза**: кількість voxels P1-raw у момент failure не записана.
- Comparison обриває всі rows, коли падає один child. Тому немає map metrics навіть для P1-global, B0-shared-scale і B1.
- Обхід потребує або збільшити frozen `max_voxels` (заборонено D-5: параметри не змінюються), або змінити WP4 code (робота власника). Тому rerun не виконувався. За протоколом цей failure — фінальне evidence.

#### 8.3 GT coverage (tolerance 0.02 s без змін)

| Scope | Coverage | Excluded |
|---|---|---|
| Усі frozen RGB inputs (preflight, B0 evaluator) | 2486/2488 (99.92%) | frame 0 (t 1341847980.722988, nearest GT 67.0 ms), frame 1 (t 1341847980.754743, 35.3 ms); `no_gt_pose_within_tolerance` |
| B0 final poses | 2458/2458 | — (frames 0–29 NOT_INITIALIZED, без pose) |
| Retained keyframes (comparison, усі методи) | 282/282 | — |

Усі 2488 RGB frames оброблені SLAM. Exclusion діє лише на GT-dependent metrics.

#### 8.4 Depth (DA3, 2488 frames, raw metric, без scale alignment)

AbsRel **0.0788**, RMSE **0.344 m**, MAE 0.177 m, δ1 **0.951**, 637,196,001 evaluated pixels. Незалежний перерахунок середніх по per-frame values збігається.

#### 8.5 Trajectory і tracking

| Method / scope | Poses | ATE RMSE m | ATE median m | RPE trans m | RPE rot ° | Alignment |
|---|---:|---:|---:|---:|---:|---|
| B0 final trajectory | 2458 | 0.03713 | 0.02270 | 0.00615 | 0.283 | Sim(3) eval-only (scale 2.268) |
| B0 online causal trajectory | 2458 | 0.03994 | 0.02814 | — | — | Sim(3) eval-only |
| B0 gap-aware RPE | 2457 pairs | — | — | 0.00599 | 0.277 | — |
| B0 retained keyframes | 282 | 0.02882 | 0.01636 | 0.00641 | 0.354 | Sim(3) eval-only |
| **P1-global** retained keyframes | 282 | **0.07289** | 0.05790 | 0.00831 | 0.354 | SE(3), recovered scale 2.193 |

- Tracking success 0.9879 (2458/2488): OK 2458, NOT_INITIALIZED 30 (frames 0–29), LOST/RELOCALIZE 0.
- Незалежний numpy Umeyama Sim(3) на `trajectory_final.txt` дає ту саму ATE 0.037131 m на 2458 poses. Keyframe ATE B0 evaluator і comparison `B0_sim3` збігаються точно.
- P1-global alignment: 47,084 inliers з 76,996 pairs (ratio 0.612).
- Sim(3) ATE не доводить metric scale. P1-global ATE (метрична scale з DA3) у 2.5 раза гірша за B0 Sim(3) keyframe ATE: scale із DA3 depth на held-out має помилку. Це негативний результат, а не підстава щось змінювати.

#### 8.6 Performance (RTX 5070 Laptop 8 GiB, Ryzen 9 8940HX, 31.2 GB; 640×480 input, 30 Hz; DA3 process_res 504)

| Component | p50 | p95 | Notes |
|---|---:|---:|---|
| `Slam.track` (Docker, 4 CPU) | 1212 ms | 4578 ms | 2487 warm samples, max 7192 ms |
| DA3 inference | 92.3 ms | 130.3 ms | 2488 frames; torch peak VRAM 1.54 GB; model load 5.0 s |
| Alignment + input loading (P1-global) | 34.0 s total | — | одноразово |
| Fusion per keyframe (P1-global, CPU) | 154.9 ms | 223.6 ms | 282 keyframes |
| Wall clock до failure | 6143 s | — | effective 0.405 FPS (2488 / wall) |

- Sampled кожні 5 s (917 samples): SLAM container peak 3.65 GiB / 10 GiB, мінімум вільної host RAM 1.79 GB.
- **Disclosure:** приблизно з 22:27Z, під час DA3 stage, паралельно працювала гра користувача (`cs2`), що ділила GPU і RAM (загальна GPU memory усіх процесів до 7083 MiB). DA3 p95 130 ms vs 97.9 ms на dev може бути завищений цим (**гіпотеза**).
- **Real-time verdict (D-7): offline.** `Slam.track` p95 4578 ms і DA3 p95 130 ms кожен окремо перевищують budget 33.3 ms. Throughput 0.405 FPS < 30. End-to-end per-frame p95 не вимірювався (послідовний offline pipeline).

#### 8.7 Evidence і disclosures

- `results/summaries/nazar_n06_heldout2488_48ddd4c.{json,csv}`: hashes, provenance, coverage, metrics, performance, 14 consistency checks (усі true). Plots: `results/plots/nazar_n06_b0_tracking_states.png`, `nazar_n06_p1_global_residuals.png`, `nazar_n06_p1_global_map.png`.
- Обидва runs звітуються: `e561d8c_01` (preflight failure, §2) і `48ddd4c_01` (comparison failure, тут). Superseded runner `wp2_heldout2488_4484fd7` failed в upstream `local_mapping.py`, без metrics.
- Claude Code під memory pressure зупинив idle background wait loop. Detached pipeline process це не зачепило.
- **Held-out результати нічого не вибирали і не змінювали:** модель, `process_res`, keyframe interval, window, confidence, alignment/fusion config, `max_voxels`, evaluator і tolerance 20 ms без змін. F-N1/F-N2 не розпочато.


## U-01 diagnostics

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 2.3 Результати (run `yulian_u01_diag_smoke200_8b5b8a7_01`)

**Вхід і перевірки:**
- статус `ok`, clean commit `8b5b8a7`, `dirty_worktree=false`; TUM fr1/xyz smoke-200, 22 retained keyframes;
- `residuals.csv` cross-check: 8,308 pairs збігаються, max |Δz| = 0;
- global scale 1.1920834.

**Flags:** A1 = 0, A2 = 0, A3 = 0, A4 = 0, S1 = недоступний. Historical SLAM run передує Y-01 export (`be9bff2`), тому tracking state = null з причиною.

**Per-frame anchor ratio:** `a_f` ∈ [0.947, 1.059], тобто max \|log a_f\| = 0.057, далеко в межах δ1-смуги (0.223).

**Spearman ρ, n = 22** (описово, без тверджень про значущість):

| GT-free сигнал | vs AbsRel | vs map-contribution accuracy |
|---|---:|---:|
| \|log a_f\| | −0.100 | −0.203 |
| 1 − frame inlier ratio | −0.353 | 0.322 |
| median \|residual\| | −0.450 | 0.162 |
| withheld median \|residual\| | −0.532 | 0.072 |
| predicted depth median | −0.328 | 0.331 |

**Найгірші keyframes за map contribution:** 80 (0.083 m), 72 (0.081 m), 84 (0.064 m). Для всіх трьох:
- inlier ratio найнижчий у run (0.57–0.64), хоча вище порогу 0.5;
- predicted depth median найбільший (1.33–1.65 m);
- `a_f` ≈ 0.97–1.00.

Жоден flag їх не позначає. Категорія: «unflagged; гіпотеза: D2 локальна помилка depth».

**Перевірка depth:** AbsRel із geometry run і перерахунок через oracle grid відрізняються не більше ніж на 6.24e-4. Причина — гіпотеза: шлях підготовки GT grid відрізняється в деталях.

Графіки:
- [timeline](../results/plots/yulian_u01_timeline.png)
- [signal vs error](../results/plots/yulian_u01_signal_vs_error.png)

Дані:
- [summary](../results/summaries/yulian_u01_diag_smoke200_8b5b8a7.json)
- [per-keyframe CSV](../results/summaries/yulian_u01_diag_smoke200_8b5b8a7.csv)

#### 2.4 Висновки для U-02 (без зміни порогів)

- На fr1/xyz per-frame metric scale DA3 вже узгоджений зі sparse SLAM map у межах ±6%. Сигнал |log a_f| не корелює з map error (ρ = −0.20).
- Отже, per-frame anchoring (U-02/U-03) на цьому run, ймовірно, дасть малий ефект. Pre-registered gate з порогами з §2.2 не відкине жодного кадру.
- Це буде виміряно в U-03 і записано як є. Пороги не змінюються після перегляду GT.
- Найпомітніший описовий зв'язок із map error мають низький inlier ratio та далека сцена (ρ ≈ 0.32–0.33). Це вказує на локальні помилки depth (D2), а не на per-frame scale (D1).
- Pixel-level фільтрація (stretch U-S1) — природний наступний крок, якщо U-03 підтвердить нульовий ефект anchoring.

#### 2.5 Обмеження

- Одна проста послідовність; n = 22.
- Anchors беруться з фінального BA snapshot, тобто метод offline і non-causal.
- GT reference побудована з тих самих keyframes зі спільною RGB calibration (задокументоване наближення).
- Tracking telemetry недоступна для historical run.
- U-01 не будує нової карти й не робить gating. Немає real-time claims.


## U-02 gate

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 3.2 Результати (run `yulian_u02_anchor_gate_smoke200_2e6fad5_01`)

- статус `ok`, clean commit `2e6fad5`, `dirty_worktree=false`; GT не відкривався;
- `frame_signals.csv` побайтово ідентичний U-01 run `yulian_u01_diag_smoke200_8b5b8a7_01`;
- sha256 `configs/robust_fusion.json`: `90567529160ec9913ba2cd756980046ba28f19c547180482358e2e906a395486`.

**Рішення gate:** 22/22 accept, 0 reject. A1 = A2 = A3 = A4 = 0 спрацювань; S1 `unavailable` для всіх 22 кадрів (historical run передує Y-01 export, `be9bff2`), тож gate фактично працював на A1–A4. Це очікуваний нульовий результат з U-01 (§2.4); пороги не змінювалися.

**Anchoring:** `a_f` застосовано до 22/22 кадрів, `a_f` ∈ [0.947, 1.059], max |log a_f| = 0.057.

**Withheld |residual| до/після корекції (GT-free, лише звіт):**

| Показник | До | Після |
|---|---:|---:|
| pooled median, 1,737 withheld pairs | 0.0388 m | 0.0301 m |
| median із per-frame medians, 22 кадри | 0.0407 m | 0.0317 m |

Покращилося 18 кадрів, погіршилося 4 (31, 35, 38, 72; +0.0005…+0.0031 m). Це узгодженість зі sparse SLAM map, а не точність depth чи карти: `a_f` і withheld residual міряються відносно того самого `s·z_slam`. Чи зменшує anchoring помилку карти, вимірює U-03.

Дані:
- [summary](../results/summaries/yulian_u02_anchor_gate_smoke200_2e6fad5.json) (містить список рішень, який U-03 має відтворити)
- [per-keyframe CSV](../results/summaries/yulian_u02_anchor_gate_smoke200_2e6fad5.csv)

#### 3.3 Обмеження

- Одна проста послідовність; 22 keyframes. Anchors із фінального BA snapshot — offline і non-causal.
- Withheld residual до/після — GT-free перевірка узгодженості, не метрика точності.
- S1 недоступний для historical run; gated variant на цьому run збігається з anchored.
- U-02 не будує карту. Немає real-time claims.


## U-03 comparison

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

#### 4.2 Результати (run `yulian_u03_robust_smoke200_cc7a4d9_01`)

**Перевірки:**
- статус `ok`, clean commit `cc7a4d9`, `dirty_worktree=false`; Python 3.12.8, numpy 2.2.4;
- config sha256 `90567529160ec9913ba2cd756980046ba28f19c547180482358e2e906a395486` = U-02 summary; рішення = U-02 (22 accept, 0 reject);
- control map **побайтово тотожний** записаному P1-global (72,887 voxels), `residuals.csv` теж тотожний; метрики control точно дорівнюють записаним; reference, перебудована з GT, тотожна записаній;
- усі три варіанти мають однаковий набір із 22 keyframes, ті самі пози, reference і правила оцінки.

**Карти (evaluation only, менше — краще для відстаней):**

| Метод | Кадри | Accuracy mean [m] | Completeness mean [m] | Chamfer-L1 [m] | F@2 cm | F@5 cm | F@10 cm |
|---|---:|---:|---:|---:|---:|---:|---:|
| P1-global control | 22 | 0.0924 | 0.0849 | 0.0887 | 0.240 | 0.480 | 0.694 |
| P1-anchored | 22 | 0.1068 | 0.1035 | 0.1051 | 0.187 | 0.407 | 0.613 |
| P1-anchored+gate | 22 (0 rejected) | 0.1068 | 0.1035 | 0.1051 | 0.187 | 0.407 | 0.613 |
| B0-shared-scale (sparse) | — | 0.0494 | 0.2261 | 0.1377 | 0.043 | 0.265 | 0.499 |
| B1-oracle (GT depth) | 22 | 0.0323 | 0.0335 | 0.0329 | 0.465 | 0.790 | 0.953 |
| P1-raw | 22 | 0.0913 | 0.0839 | 0.0876 | 0.242 | 0.475 | 0.700 |

**Негативний результат.** Per-frame anchoring **погіршив** карту: Chamfer-L1 +0.0165 m (0.0887 → 0.1051), accuracy +0.0144 m, completeness +0.0185 m, F-score нижчий на всіх τ. Gate не відкинув жодного кадру (A1–A4 не спрацювали, S1 недоступний), тому gated variant — та сама карта, що й anchored (sha256 `map.npz` однаковий). Retention: 22/22 кадри, 0 відкинутих точок.

**Depth (per-frame, evaluation only):** median AbsRel 0.0902 → 0.0948; AbsRel покращився у 9/22 кадрах. Знак чіткий (описово, n = 22):
- усі 9 кадрів з `a_f > 1` покращилися і за AbsRel, і за map contribution;
- усі 13 кадрів з `a_f < 1` погіршилися за обома.

**Три різні речі, три різні відповіді:**
1. *Узгодженість зі SLAM map* покращилася (U-02: withheld median |residual| 0.0388 → 0.0301 m).
2. *Точність depth* погіршилася (median AbsRel +0.0046).
3. *Точність злитої карти* погіршилася (Chamfer +0.0165 m).

Отже, менший sparse residual тут **не** означає кращої геометрії. Причина — гіпотеза: `s` оцінено так, що `s·z_slam` у середньому збігається з DA3, тож `a_f` лише перерозподіляє кадри навколо спільного зміщення DA3/SLAM, а не наближає їх до GT; anchors також несуть власну per-frame похибку SLAM depth.

**CPU overhead** (CPU artifact processing only; excludes SLAM and model inference; not real-time): signals + gate 42.4 ms на 22 кадри (1.9 ms/кадр у середньому, batch); anchoring p50/p95 0.56/1.19 ms; fusion per keyframe p50/p95 37.6/49.0 ms (anchored) проти 37.9/50.1 ms (control).

Графік: [comparison](../results/plots/yulian_u03_comparison.png). Дані: [summary](../results/summaries/yulian_u03_robust_smoke200_cc7a4d9.json) (включно з per-frame до/після), [comparison CSV](../results/summaries/yulian_u03_robust_smoke200_cc7a4d9.csv).

#### 4.3 Обмеження

- Одна проста послідовність, 22 keyframes. Anchors із фінального BA snapshot — offline і non-causal.
- S1 не оцінювався (немає tracking export). Gate не відкинув жодного кадру, тому на реальних збоях він не перевірений.
- GT reference — наближення; per-frame depth рахується через oracle grid (до 6.24e-4 AbsRel від geometry metrics, U-01).
- Пороги не змінювалися після перегляду GT; повторних запусків не було. Held-out (fr3) не використовувався. Немає real-time claims.


## U-04 figures і висновки

Джерело / авторство: [запис на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md). Історичні run IDs та результати збережено.

### 5. U-04 — фігури для презентації

Скрипт `scripts/render_robust_fusion_figures.py`:
- читає лише завершені runs і ніколи не перезаписує фігури;
- сумарний розмір фігур має бути < 1 MB (зараз 0.78 MB);
- відстань до GT reference і GT-помилка depth позначені «evaluation only».

Усі фігури offline.

| Артефакт | Файл | Джерело (run ID) |
|---|---|---|
| Failure timeline | [yulian_u01_timeline.png](../results/plots/yulian_u01_timeline.png) | `yulian_u01_diag_smoke200_8b5b8a7_01` |
| Signal vs error | [yulian_u01_signal_vs_error.png](../results/plots/yulian_u01_signal_vs_error.png) | `yulian_u01_diag_smoke200_8b5b8a7_01` |
| Порівняння control / anchored / gated / B0 / B1 / P1-raw | [yulian_u03_comparison.png](../results/plots/yulian_u03_comparison.png) | `yulian_u03_robust_smoke200_cc7a4d9_01` |
| Point cloud до/після (P1-global vs P1-anchored+gate, однаковий вигляд і шкала) | [yulian_u04_pointcloud_before_after.png](../results/plots/yulian_u04_pointcloud_before_after.png) | `yulian_u03_robust_smoke200_cc7a4d9_01` |
| Failure cases (3 найгірші keyframes: RGB, depth, GT \|error\|, flags, `a_f`) | [yulian_u04_failure_cases.png](../results/plots/yulian_u04_failure_cases.png) | `yulian_u01_diag_smoke200_8b5b8a7_01` + `yulian_u03_robust_smoke200_cc7a4d9_01` |

У заголовках point cloud стоїть середня відстань fused voxels до reference **до** re-voxelization в `evaluate_map` (0.0901 / 0.1044 m). Офіційні метрики карти наведено в таблиці §4.2 (0.0924 / 0.1068 m).

**Failure cases (keyframes 80, 72, 84):**
- жоден flag не спрацював, `a_f` ≈ 0.97–1.00;
- найбільша GT-помилка зосереджена на людині, краях монітора і далекому фоні, тобто помилки локальні, а не в scale;
- у кадрі 84 anchoring погіршив AbsRel з 0.090 до 0.119 (`a_f` = 0.967).

Категорія: «гіпотеза: D2 локальна помилка depth».

Команда (шляхи вказують на ignored local runs):

```powershell
python scripts/render_robust_fusion_figures.py `
  --u01-run results/runs/yulian_u01_diag_smoke200_8b5b8a7_01 `
  --u03-run results/runs/yulian_u03_robust_smoke200_cc7a4d9_01 `
  --comparison-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.comparison `
  --slam-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.slam `
  --geometry-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.geometry `
  --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz --manifest data/manifests/tum_fr1_xyz.json
```

### 6. Висновки і обмеження P1-robust MVP

#### 6.1 Що реалізовано, а що лише запропоновано

| Реалізовано й виміряно | Запропоновано, не виконано |
|---|---|
| GT-free per-keyframe signals і flags A1–A4 (U-01) | Live S1 на runs із Y-01 tracking export (§7, U-S3) |
| Per-frame anchoring `a_f` і pre-registered gate (U-02) | Pixel-level фільтрація / multi-view consistency (U-S1) |
| Control reproduction, карти P1-anchored і P1-anchored+gate з GT-оцінкою (U-03) | Fault injection, τ sweep, ROC, gallery (U-S2, U-S4) |
| Фігури до/після і failure cases (U-04) | Dev-split runs DA3/UniDepth (Nazar, §7) |

#### 6.2 Висновки за секціями

**Dense depth:**
- На fr1/xyz per-frame metric scale DA3 узгоджений зі sparse SLAM map у межах ±6% (`a_f` ∈ [0.947, 1.059]).
- Per-frame scale не пояснює розрив P1→B1 (Chamfer 0.0887 проти 0.0329 m): anchoring його не зменшив, а збільшив (0.1051 m).
- У найгірших кадрах помилки локальні (людина, краї, далекий фон), а `a_f` ≈ 1.
- Наступний крок — корекція на рівні пікселів, а не кадрів (U-S1).

**SLAM:**
- Sparse map дає достатньо anchors: A1 і A4 не спрацювали на жодному з 22 кадрів.
- `s·z_slam` не кращий за DA3 як per-frame оцінка metric depth. Корекція до нього погіршила AbsRel у 13/22 кадрів, і це саме ті кадри, де `a_f < 1`.
- Причина — гіпотеза: global scale `s` підігнано до DA3, тож `a_f` центрується навколо спільного зміщення, а не навколо GT. До того ж anchors мають власну похибку SLAM depth.
- S1 (tracking state) **не оцінювався**: historical run передує Y-01 export.

**Alignment і fusion:**
- Control відтворено побайтово. Варіанти контрольовані: ті самі 22 кадри, пози, reference, transform і voxel grid.
- Pre-registered gate на цьому run не відкинув жодного кадру. Це коректний нульовий результат, а не перевірка gate на реальних збоях.
- **Менший sparse residual ≠ краща геометрія.** Узгодженість зі SLAM map зросла (withheld median 0.0388 → 0.0301 m), а точність depth і карти впала.
- Пороги не змінювалися. P1-anchored не рекомендується як заміна P1-global.

**Гіпотеза P1-robust на цьому run не підтверджена.** Це виміряний негативний результат, а не збій виконання.

#### 6.3 Обмеження (повний перелік)

- Одна проста послідовність (TUM fr1/xyz smoke-200), 22 retained keyframes. При n = 22 кореляції лише описові.
- Anchors беруться з фінального BA snapshot, тому метод **offline і non-causal**. Для online-версії потрібні causal anchors.
- S1 не оцінювався. Gate працював лише на A1–A4 і не відкинув жодного кадру.
- GT reference — наближення (спільна RGB calibration, ті самі keyframes).
- Per-frame depth до/після рахується через oracle grid; від geometry metrics він відрізняється до 6.24e-4 AbsRel.
- CPU timing охоплює лише обробку артефактів, без SLAM і inference моделі. **Немає real-time claim.**
- Розширення не входить у held-out freeze; fr3 не використовувався.

## Provenance та історичні references

Усі existing `results/summaries/`, `results/plots/`, configs, manifests і raw runs залишаються незмінними. Paths у старих JSON — provenance на original `git_commit`, а не актуальні navigation links. Їх не переписували заради нового layout: оригінальний документ можна відкрити у Git tree відповідного source commit. Нижче є pinned джерело кожного об'єднаного документа; старі schedules, execution prompts та weekly templates не є поточним планом.

- `PLAN.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/PLAN.md)
- `configs/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/configs/README.md)
- `data/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/data/README.md)
- `docs/BENCHMARK_PROTOCOL.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/BENCHMARK_PROTOCOL.md)
- `docs/DATASET_FREEZE.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/DATASET_FREEZE.md)
- `docs/DEPTH_ABLATIONS.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/DEPTH_ABLATIONS.md)
- `docs/ENVIRONMENT.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ENVIRONMENT.md)
- `docs/GT_POSE_COVERAGE.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/GT_POSE_COVERAGE.md)
- `docs/HELDOUT_BENCHMARK.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/HELDOUT_BENCHMARK.md)
- `docs/INTEGRATION_STATUS.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/INTEGRATION_STATUS.md)
- `docs/MODEL_SELECTION.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/MODEL_SELECTION.md)
- `docs/NAZAR_REPRODUCTION.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/NAZAR_REPRODUCTION.md)
- `docs/PROJECT_BRIEF.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/PROJECT_BRIEF.md)
- `docs/PROJECT_STATUS.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/PROJECT_STATUS.md)
- `docs/ROBUST_FUSION.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/ROBUST_FUSION.md)
- `docs/SELECTION_PROTOCOL.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/SELECTION_PROTOCOL.md)
- `docs/TWO_PERSON_COMPLETION_PLAN.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/TWO_PERSON_COMPLETION_PLAN.md)
- `docs/UNIDEPTH.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/UNIDEPTH.md)
- `docs/WP1_HANDOFF.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP1_HANDOFF.md)
- `docs/WP2_BENCHMARK.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_BENCHMARK.md)
- `docs/WP2_EVALUATION.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_EVALUATION.md)
- `docs/WP2_LINUX_CONTAINER.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_LINUX_CONTAINER.md)
- `docs/WP2_SETUP.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SETUP.md)
- `docs/WP2_SPARSE_EXPORT.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_SPARSE_EXPORT.md)
- `docs/WP2_TRACKING_EXPORT.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP2_TRACKING_EXPORT.md)
- `docs/WP3_WP4_COMPLETION.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/WP3_WP4_COMPLETION.md)
- `docs/YULIAN_HANDOFF.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/docs/YULIAN_HANDOFF.md)
- `results/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/results/README.md)
- `scripts/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/scripts/README.md)
- `src/rt_mapping/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/src/rt_mapping/README.md)
- `tests/README.md` → [оригінал на `f42bc9c`](https://github.com/Badabuba/ai-real-time-mapping/blob/f42bc9ce30700299016e765714a2655e300e2377/tests/README.md)
