# Real-Time Mapping with Foundation Models

Навчальний дослідницький проєкт: монокулярні RGB кадри → класичний pySLAM і foundation-model depth → вирівнювання масштабу → dense 3D point cloud. Порівнюємо точність, повноту карти, стабільність tracking та вартість обчислень. **Поточна реалізація — offline pipeline; real-time роботу не підтверджено.**

## Що реалізовано

- **WP1:** DA3 Metric та UniDepth V2 adapters, calibrated intrinsics, deterministic prediction artifacts і depth evaluation.
- **WP2:** pinned pySLAM monocular integration, sparse landmarks/observations, causal all-frame tracking і timing, ATE/RPE/resources, frozen split support та partial-GT reporting.
- **WP3:** robust scalar scale / Sim(3), sparse–dense correspondences, distortion-aware projection і voxel fusion.
- **WP4:** B0/B1/P1 comparison, GT coverage policy, map metrics, pipeline orchestration і CPU CI.
- Окреме P1-robust розширення: sparse per-frame anchoring та frame gate. Smoke дав негативний результат; воно не замінює P1-global.

Монокулярний SLAM має довільний scale. Метричний scale P1 оцінюється через predicted depth; evaluation-only Sim(3) ATE сам по собі не доводить відновлення метричного масштабу. GT trajectory/depth не використовуються для SLAM чи P1 fitting — тільки для evaluation або явно позначеного B1 oracle.

## Архітектура

```text
RGB + camera calibration
  ├─ pySLAM ── poses + sparse landmarks + pixel observations
  └─ DA3 / UniDepth ── depth + valid mask + K_processed
                    ↓
       robust scale / Sim(3) alignment
                    ↓
             voxel point-cloud fusion
                    ↓
    depth / trajectory / map / runtime evaluation
```

Poses — `T_wc`, quaternions — `qx,qy,qz,qw`, depth — camera-z у метрах; sparse SLAM coordinates — довільні monocular units. Resize/crop змінюють intrinsics. Contracts і точні export schemas: [ARCHITECTURE](docs/ARCHITECTURE.md).

## Швидкий CPU запуск

Python **3.11 або 3.12** — перевірені в CI; package підтримує `>=3.11,<3.14`. CPU tests і synthetic smoke не потребують TUM, GPU, weights або встановленого pySLAM.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,benchmark,filtering]"
python -m pytest tests -q
python scripts/run_alignment_smoke.py --plot
python scripts/run_comparison_smoke.py --plot
```

Windows PowerShell: створити environment через `py -3.11 -m venv .venv`, активувати `.venv\Scripts\Activate.ps1`; подальші `python` команди ті самі. У вже налаштованому environment перевстановлення не потрібне. Smoke створює нові ignored runs із synthetic data, це correctness check, а не TUM benchmark.

`.github/workflows/tests.yml` виконує повну CPU suite та обидва synthetic smokes на Ubuntu/Windows × Python 3.11/3.12. Native integration test opt-in і за замовчуванням skipped.

## Дані та моделі

TUM archive та extraction мають лежати поруч у `data/raw/tum_rgbd/`. **Архів потрібен verifier-у**, навіть якщо зображення вже розпаковані. Official source URL, archive checksum, indices, selected image hashes та calibration — у `data/manifests/*.json`. Downloads не виконуються автоматично під час pipeline inference.

| Manifest | Роль | Frozen RGB inputs |
|---|---|---:|
| `tum_fr1_xyz.json` | smoke: fr1/xyz | 200 |
| `tum_fr1_desk_development.json` | development: fr1/desk | 573 |
| `tum_fr1_desk_spike50.json` | development spike | 50 |
| `tum_fr2_desk_selection50.json` | selection: fr2/desk | 50 |
| `tum_fr3_long_office_heldout.json` | held-out: fr3/long_office_household | 2,488 |

Frames — frozen RGB/depth associations; depth path існує для evaluation, SLAM отримує лише RGB. `--all-frames` означає весь **configured split**, а не весь original recording. Split identities, calibration та **20 ms** GT tolerance не змінюються заради результату.

Поточний frozen dense model для N-05/N-06 — **DA3METRIC-LARGE @504**. UniDepth виграв selection rubric, але до IC3 спрацював заздалегідь визначений fallback trigger через failed N-04 pipeline gate; пізніші результати не змінюють freeze. UniDepth adapter залишається доступним. Pinned code/model revisions, hashes і licensing metadata: `configs/model_assets.json`, `configs/selected_geometry.json` та [ADR001](docs/decisions/ADR001_geometry_model.md).

DA3 і UniDepth потребують окремих перевірених CUDA environments та cached checkpoints. macOS environment тут перевіряє classical B0, не CUDA depth inference. Точні installation/build commands: [REPRODUCIBILITY](docs/REPRODUCIBILITY.md).

## Основні команди

Команди нижче виконуються після відповідного setup. Для кожного нового run потрібен новий `--run-id`; finished runs не перезаписуються. Слова в `<…>` — placeholders, які треба замінити локальними paths/IDs. Held-out inference або повторний benchmark виконувати лише за явним дозволом і [протоколом](docs/EXPERIMENTS.md#protocols).

**WP1 depth** — DA3 historical TUM CLI або generic model runner:

```bash
python scripts/check_wp1_environment.py
python scripts/run_tum_da3_metric.py --frames 20 --process-res 384 --run-id unique_da3_smoke
python scripts/run_geometry_benchmark.py --model da3 --manifest data/manifests/tum_fr1_desk_spike50.json --split development --frames 50 --prewarm 10 --run-id unique_depth_spike
```

Для UniDepth використати `--model unidepth` у його окремому environment. Generic CLI також приймає `--assets-root`, `--output-root`, `--resolution-level`, `--process-res`. DA3-specific runner лишається для compatibility існуючих configs; ці CLI не є повними дублями.

**WP2 preflight** — читає integrity/timestamps, не запускає SLAM:

```bash
python scripts/check_wp2_environment.py --config configs/wp2_pyslam_development.json --dataset-only --full
python scripts/prepare_wp2_baseline.py --config configs/wp2_pyslam_development.json --all-frames --output outputs/wp2/unique_preparation
```

**WP2 native macOS B0** — у вже зібраному runtime:

```bash
.venv-wp2/bin/python scripts/run_wp2_pyslam.py --config configs/wp2_pyslam_baseline.json --pyslam-python .venv-pyslam/bin/python --frames 200 --export-sparse --run-id unique_b0_smoke
```

Для development/selection використовувати відповідний `configs/wp2_pyslam_*.json` і `--all-frames`. Windows host запускає pySLAM через Linux/Docker, не native Windows. Native workers потребують shared-memory access; startup failure не підміняти успішним tracking.

**WP2 trajectory evaluation** — без нового SLAM:

```bash
python scripts/evaluate_wp2_run.py --source-run results/runs/<source_run_id> --groundtruth data/raw/tum_rgbd/<sequence>/groundtruth.txt --run-id unique_b0_eval --plot
```

За наявності matching resource sidecar додати `--resources <report.json>`. All-frame states, causal/final gauges, gap-aware RPE, GT exclusion та RSS accounting описано в [EXPERIMENTS](docs/EXPERIMENTS.md). `measure_wp2_resources.py` — smoke-only CLI; wider split measurement використовує documented `measure_process` wrapper.

**WP3/WP4 mapping і comparison** — на готових SLAM/depth artifacts:

```bash
python scripts/run_offline_mapping.py --slam-run <slam_run> --geometry-run <geometry_run> --run-id unique_mapping
python scripts/run_mapping_comparison.py --slam-run <slam_run> --geometry-run <geometry_run> --sequence-dir data/raw/tum_rgbd/<sequence> --manifest data/manifests/<manifest>.json --run-id unique_comparison
```

**One-config pipeline** — перевірений Windows/CUDA + Linux/Docker layout:

```bash
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id unique_full_pipeline
```

Перед запуском перевірити container name, interpreter paths, data і cached model assets у config. Приклади configs містять machine-specific runtime argv; це не автоматична установка dependencies. Frozen configs не редагуються для нового benchmark. Для іншої машини потрібна власна явно перевірена runtime configuration.

Інші збережені tools: `freeze_tum_split.py`, `build_tum_manifest.py`, `verify_geometry_run.py`, `compare_geometry_models.py`, `analyze_confidence.py`, native builders, `visualize_wp2_trajectory.py`, robust diagnostics/gate/fusion/figure tools. Вони обслуговують різні interfaces, integrity checks та recorded experiments. `run_da3_metric_smoke.py` — legacy standalone image probe, не основний reproducible benchmark runner.

## Оцінювання та результати

| Група | Метрики |
|---|---|
| Trajectory | ATE RMSE, translation/rotation RPE; causal, final та retained poses окремо |
| Depth | AbsRel, RMSE, MAE, δ1, valid coverage |
| Map | accuracy, completeness, Chamfer-L1, F-score@2/5/10 cm |
| Tracking | native OK fraction, initialization/LOST/relocalization/UNKNOWN і failure segments |
| Performance | p50/p95, whole-run FPS, peak RAM/VRAM із documented scope |

Partial GT coverage не видаляє RGB frames зі SLAM. На fr3 frozen input 2,488; GT matches 2,486, unmatched IDs 0/1, coverage 99.9196%. Frame 2 перед GT start, але має valid match у 20 ms. GT-unmatched frames виключаються тільки з GT-dependent metrics; tracking/latency denominator лишається повним. Zero valid overlap дає explicit failure і structured coverage report.

| Recorded experiment | Підсумок |
|---|---|
| WP3/WP4 real smoke, fr1/xyz 200 | Matching SLAM/depth, metric cloud та B0/B1/P1 comparison завершені; 72,887 metric voxels |
| Y-05, fr1/desk 573 ×3 | Tracking 76.09% ±0.91 percentage points; causal ATE 2.80±0.63 cm; тривалий relocalization gap |
| Y-06 native Mac, fr3 2,488 | Tracking 98.67%; causal/final aligned ATE 3.86/1.61 cm; 1.80 FPS |
| N-02 supplemental evaluation | Comparison ok, 17/18 GT-eligible retained keyframes; source stages незмінні |
| N-06 GPU/Docker rerun | SLAM, DA3, P1-global ok; comparison failed на P1-raw voxel cap. Full held-out map metrics відсутні |
| P1-robust smoke | Sparse consistency покращилась, GT geometry погіршилась; gate не відкинув кадрів |

Pose-aligned ATE стосується тільки evaluable poses. Hardware, gauges, repetitions, failure records, contribution table та числові summaries: [RESULTS](docs/RESULTS.md). Повні source artifacts — локальні; маленькі tracked summaries/plots — у `results/`. Проєкт не заявляє universal improvement або real-time: критерій вимагає end-to-end p95 ≤33.3 ms і ≥30 FPS.

<a id="repository"></a>

## Репозиторій та документація

```text
configs/             executable і frozen benchmark configurations
containers/          Linux pySLAM runtime recipe
requirements/        окремі model/platform dependency snapshots
data/manifests/      frozen inputs, timestamps, hashes, calibration
src/rt_mapping/      adapters, contracts, data, SLAM, alignment, fusion, evaluation, runs
scripts/             thin CLI entry points і native builders
tests/               CPU regression tests, synthetic fixtures, opt-in native test
results/             small versioned summaries/plots; full runs ignored
docs/                technical reference, reproduction та evidence
```

- [ARCHITECTURE](docs/ARCHITECTURE.md): schemas, units, coordinate/pixel conventions, sparse/causal export formats.
- [EXPERIMENTS](docs/EXPERIMENTS.md): metrics, datasets, frozen decisions, GT policy та no-tuning rules.
- [REPRODUCIBILITY](docs/REPRODUCIBILITY.md): detailed platform setup, runtime caveats і reproduction commands.
- [RESULTS](docs/RESULTS.md): evidence, failures, contribution table та remaining deliverables.
- [CONTRIBUTING](CONTRIBUTING.md): team workflow, verification і publication rules.
- Retained source records: [N-05 benchmark](docs/DEVELOPMENT_BENCHMARK.md), [model ADR](docs/decisions/ADR001_geometry_model.md), [P1-robust preregistration](docs/P1_ROBUST_EXTENSION_PLAN.md), [submission rubric](docs/INTERIM_REVIEW.md).

Raw datasets/archives, model weights, environments, native dependencies, full `results/runs/`, logs і point clouds не комітяться. Run records містять git commit, config/model/data provenance, hardware та status; failure теж є evidence. Нові run IDs обов'язкові. Project licence не оголошено; pySLAM GPLv3, DA3 Apache-2.0 та UniDepth CC-BY-NC-4.0 constraints лишаються обмеженнями, описаними в ADR/protocol. Upstream code та weights не vendored.

Cleanup не змінює алгоритми, configs, datasets, benchmark evidence чи presentation PR. Історичні документи доступні через pinned Git links у RESULTS; їхні immutable provenance paths трактуються в context original source commit.
