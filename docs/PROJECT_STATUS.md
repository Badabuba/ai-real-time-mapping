# Статус і журнал прогресу

Це single source of truth для відповідей «що зроблено?», «хто робив?» і «що не вийшло?». Оновлювати наприкінці кожного робочого session/PR. Planned не дорівнює done.

Останнє оновлення: 25 жовтня 2026.

Історичний integration update (23 жовтня): Назарів C5 [PR #4](https://github.com/Badabuba/ai-real-time-mapping/pull/4) merged у `develop` (`e4eb08d`); WP2 code зафіксовано commit `e114490` і поєднано з C5 на `yaropolk-wp1-wp2-integration`. Combined CPU suite: **385 passed, 1 skipped**; source/data contracts сумісні на цій перевірці, GPU inference не повторювали. Готовність окремих adapters не означає завершення WP1/WP2: точний залишок і передача artifacts Юліану — [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md). Historical `dirty_worktree=true` у smoke evidence збережено чесно.

WP2 sparse handoff (historical run із dirty worktree; code merged через PR #5): реальний run `yaropolk_b0_fr1_xyz_200_sparse_20261023_03` завершив 200 frames / 197 final poses / 0 LOST і зберіг **1,205 landmarks, 19 retained keyframes, 7,595 pixel observations**. `--export-sparse` додає NPZ, CSV, PLY та metadata/checksums після original `Slam.quit`; upstream source/algorithm не змінювали. Read-back validation, native API check і CPU suite (325 passed, 1 skipped; native skipped check окремо пройшов) успішні. Evidence: [WP2_SPARSE_EXPORT.md](WP2_SPARSE_EXPORT.md), `results/summaries/wp2_sparse_fr1_xyz_200_20261023.json`. Для alignment використовувати poses із `keyframes.npz` того самого snapshot; units ще не metric. Next: normalized all-frame states/timing, automated recorded ATE/RPE та ширший benchmark. Failed attempts `_01` (launcher variable, fixed) / `_02` (sandbox OpenMP SHM, own workers stopped) збережено; попередні результати не перезаписували.

Візуальна перевірка WP2 (historical run; code merged через PR #5): `scripts/visualize_wp2_trajectory.py` читає наявний успішний run `_02` без повторного SLAM. 3D trajectory, camera axes та XY/XZ/YZ plots перевірено візуально; guide і SHA-256 вихідних artifacts — `results/visualizations/yaropolk_b0_fr1_xyz_200_20261023_02/20261023T131917_285206Z/`. 198 poses / 6.735943 s, monocular scale невідомий; accuracy не оцінювалася. Sparse map був у пам'яті, але координати/system state не збережені. Native map viewer додатково потребує відсутній `pypangolin`; GUI не перевірено.

Аудит та WP3/WP4 (25 жовтня): усі попередні PR #1–#5 були merged у develop; [PR #6](https://github.com/Badabuba/ai-real-time-mapping/pull/6) переніс їх у main (`36ed781`). Нових GitHub issues або незлитих feature commits не знайдено. Реалізовано robust scalar/Sim(3), calibrated correspondences, distortion-aware fusion, offline artifact runner та synthetic smoke. Локально **441 passed, 1 skipped**; synthetic known scale 2.5 → 2.500000160469811. Два Windows helper failures виправлено. Повних real input runs у цьому checkout немає; real validation, wider benchmark та demo не оголошені done. Команди, точні blockers і задачі Юліана: [YULIAN_HANDOFF.md](YULIAN_HANDOFF.md).

## 1. Snapshot

| Deliverable | Статус | Evidence | Owner | Наступний крок |
|---|---|---|---|---|
| GitHub repository | public; WP1/WP2 merged у main | PR #6, merge 36ed781 | команда | підтримувати main/develop узгодженими |
| Project scope / architecture / plan | draft done | README, PLAN, docs/* | Назар (бос) | Ярополк (дубєнь) і Юліан (піндос) переглядають і погоджують |
| Dataset downloaded/frozen | smoke subset done | TUM fr1/xyz; SHA-256 у docs/ENVIRONMENT.md; manifest data/manifests/tum_fr1_xyz.json | Назар (бос) | заморозити ширший evaluation split після smoke |
| pySLAM baseline | native setup + real smoke + sparse handoff done; full WP2 incomplete | docs/WP2_SETUP.md; docs/WP2_SPARSE_EXPORT.md; scripts/run_wp2_pyslam.py. Initial run `_02`: 200 frames / 198 poses / 0 LOST. New `yaropolk_b0_fr1_xyz_200_sparse_20261023_03`: 200 frames / 197 poses / 0 LOST; 1,205 landmarks / 19 retained keyframes / 7,595 observations. Evidence: results/summaries/wp2_sparse_fr1_xyz_200_20261023.json. Native macOS arm64, upstream 96019cf, Python core, ORB2/DBOW3, -O; no GT input; code merged PR #5; historical run dirty=true | Ярополк (дубєнь) | normalized all-frame trajectory/states/timing; automated recorded ATE/RPE; wider benchmark |
| WP1 environment + DA3 import | done | docs/ENVIRONMENT.md; scripts/check_wp1_environment.py | Назар (бос) | model-load та one-frame inference smoke |
| Dense model inference | smoke done | scripts/run_tum_da3_metric.py; results/summaries/wp1_da3metric_tum_fr1_xyz_20.json | Назар (бос) | selection split із часовим stride + fallback model |
| TUM loader + FrameRecord (WP1 C1) | merged через develop → main (PR #6; original 8abb331) | src/rt_mapping/data/tum.py; src/rt_mapping/contracts/frame.py; tests/test_tum_data.py — 12 passed; association збігається з runner на 792/792 кадрах fr1/xyz | Назар (бос) | review |
| TUM fr1/xyz dataset manifest (WP1 C2) | merged у develop і перенесено в main через PR #6 (PR #1, dc39c87, merge 0d4e213) | src/rt_mapping/data/manifest.py; scripts/build_tum_manifest.py; data/manifests/tum_fr1_xyz.json — SHA-256 збігається з docs/ENVIRONMENT.md, 792 associations, smoke = перші 200; `--check` відтворює файл байт-у-байт; tests/test_tum_manifest.py — 5 passed. Archive URL не перевірено онлайн (TUM server 503 під час перевірки) | Назар (бос) | review; підтвердити archive URL |
| GeometryPrediction + GeometryAdapter + intrinsics helpers (WP1 C3) | merged PR #2 → develop → main (PR #6) | src/rt_mapping/contracts/geometry.py; src/rt_mapping/geometry/{adapter,intrinsics}.py; tests/test_geometry_contract.py, tests/test_intrinsics.py — повний suite 89 passed (CPU). Resize з цілими центрами pixels дає той самий focal, що й DA3 run, але principal point на 0.5·(s−1) px інший (−0.205 / −0.194 px для 640×480→378×294) | Назар (бос) | D008 реалізовано в C5; real-data integration |
| Depth evaluation + timing summary + run.json contract (WP1 C4) | merged у develop і перенесено в main через PR #6 (PR #3, d2dad61, merge 31cfd29) | src/rt_mapping/evaluation/{depth,timing}.py; src/rt_mapping/contracts/{run_manifest,_validation}.py; tests/test_depth_evaluation.py, tests/test_timing.py, tests/test_run_manifest.py — повний suite 290 passed (CPU). Read-only parity з локальним 20-frame DA3 run: δ1 збігається точно, AbsRel/RMSE/MAE — до 2e-8 (float64 замість float32); nearest resize GT побітово = Pillow NEAREST на 20/20; cold 853.86 ms, warm mean 97.95 / median 85.28 ms (warmup=1) і p95 336.16 ms (warmup=0) відтворені; warm p95 (warmup=1) = 118.72 ms | Назар (бос) | D008 реалізовано в C5; ширший benchmark |
| DA3 Metric adapter + runner integration (WP1 C5) | merged у develop і перенесено в main через PR #6 (PR #4, merge e4eb08d; original code 721909f) | src/rt_mapping/adapters/da3_metric.py (`Da3MetricAdapter`, lazy torch/DA3); src/rt_mapping/runs/geometry_run.py (manifest check → load once → predict → C3 NPZ → C4 eval/timing → run.json); src/rt_mapping/evaluation/tum_depth.py; scripts/run_tum_da3_metric.py — тонкий CLI. Tests: повний suite 350 passed (CPU, fake backend, без torch). Definitive GPU runs із чистого commit 721909f (`dirty_worktree=false`, `git_commit`=721909f2f6ea32a0db54886a81e196e9cfc7b8c0): `c5_clean_smoke_f1_721909f` і `c5_clean_parity_f20_721909f` — status ok, run.json валідні; checkpoint `model.safetensors@sha256:bbea5b0b…324776` збігається з незалежно порахованим SHA-256 cached файлу; NPZ містять лише depth_m/valid_mask/K_processed/meta.json (`has_confidence=false`, без GT). Parity з historical 20-frame run: mean AbsRel 0.105064 / RMSE 0.175151 m / MAE 0.129873 m / δ1 0.967453 — збіг (per-frame |Δ| ≤ 1.5e-7, δ1 і кількість evaluated pixels ідентичні); depth на 18/20 кадрах відрізняється лише float32 округленням (≤ 4.8e-7 m), на кадрах 4 і 16 — до 0.8 / 3.5 mm (див. failure log); K: fx/fy ті самі (≤ 4.3e-5), cx −0.2047 px, cy −0.1938 px (D008). Timing (warmup=1, RTX 5070 Laptop, 378×294): cold 783.7 ms, warm mean 88.1 / median 78.6 / p95 101.2 ms (historical: 853.9 / 97.9 / 85.3 / 118.7; GPU timing між запусками коливається, не є критерієм parity); peak VRAM 1.424 GB (historical 1.425); model load 3.60 s. Попередні dev runs до commit (`c5_smoke_f1_20261021`, `c5_parity_f20_20261021`, `c5_smoke_f1_final_20261021`, dirty worktree) дали ті самі метрики. Historical runs і summaries не змінені (SHA-256 24 файлів до/після) | Назар (бос) | matching 200-frame predictions для WP3; ширший evaluation/benchmark |
| Synthetic alignment test | implemented + CPU verified | alignment/estimators.py; test_alignment_estimators.py; synthetic smoke scale 2.50000016 vs 2.5 | Юліан (піндос) | реальний handoff |
| Real sparse–dense alignment | code implemented; real validation blocked on artifacts | alignment/correspondences.py; runs/mapping_run.py; docs/YULIAN_HANDOFF.md | Юліан (піндос) | full SLAM run + matching DA3 predictions усіх keyframes |
| Offline metric fusion | synthetic verified; real validation pending | fusion/voxel.py; scripts/run_offline_mapping.py; run_alignment_smoke.py | Юліан (піндос) | real fused PLY, residual plot, review |
| End-to-end pipeline | offline artifact stage implemented; input-to-output launcher pending | scripts/run_offline_mapping.py | Назар (бос) + Ярополк (дубєнь) + Юліан (піндос) | після окремих smoke runs |
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
- WP2 (23 жовтня): pySLAM native macOS setup та реальний RGB-only monocular smoke на 200 кадрах; 198 final poses, 0 LOST за upstream counters. Details і limitations — docs/WP2_SETUP.md; це не ATE/RPE benchmark або real-time claim.

Ще **не виконано**: повний model-selection benchmark, normalized SLAM exports/ATE/RPE, real-data alignment/fusion validation, input-to-output launcher, end-to-end benchmark і demo. 20 послідовних DA3 кадрів є smoke-перевіркою, а не достатнім evaluation split; 10.2 warm FPS не дає підстав називати весь pipeline real-time.

## 3. Внесок учасників

Додавати тільки merged/reproducible work. Розподілене завдання ще не є фактичним внеском.

| Учасник | Фактичний внесок | Evidence (PR/commit/file/run) | Дата |
|---|---|---|---|
| Назар (бос) | постановка вимог і координування; documentation scaffold; WP1 Windows/CUDA environment; TUM fr1/xyz data verification; DA3 Metric 20-frame smoke benchmark | README, PLAN, docs/*, scripts/run_tum_da3_metric.py, results/summaries/* | 2026-10-20 |
| Ярополк (дубєнь) | Dataset verification; isolated native runtime/build recipe; recorded B0 smoke; trajectory visualization; retained sparse landmarks/poses/pixel links + PLY; validation tests і docs | commit e114490, PR #5 merged у develop; PR #6 переніс у main; docs/WP2_SETUP.md, docs/WP2_SPARSE_EXPORT.md; results/summaries/wp2_sparse_fr1_xyz_200_20261023.json; tests/test_wp2_setup.py, tests/test_slam_smoke.py, tests/test_slam_sparse.py, tests/test_pyslam_sparse_native.py | 2026-10-23 |
| Юліан (піндос) | integration audit і promotion WP1/WP2; WP3 robust scale/Sim(3), pixel correspondences та geometry tests; WP4 offline fusion/runner; Windows helper fixes та CPU CI | PR #6; alignment/, fusion/, geometry/projection.py, runs/mapping_run.py; tests/test_mapping*.py; docs/YULIAN_HANDOFF.md | 2026-10-25 |

Після review записати, хто перевірив і змінив кожне рішення. Авторство технічних результатів підтверджується PR/commit/run, а не лише цією таблицею.

## 4. Failure / blocker log

| Дата | Owner | Симптом / команда | Evidence | Причина або гіпотеза | Що вже спробували | Рішення / наступний експеримент | Статус |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | Назар (бос) | перший synthetic runner падав під час читання `prediction.is_metric` | local traceback; виправлення у runner | DA3 повертає auto-created empty Addict Dict для відсутнього поля | додано safe scalar conversion | пройдено synthetic і real TUM run | resolved |
| 2026-10-20 | Назар (бос) | DA3 standalone metric output не повернув intrinsics | run manifest/API inspection | API додає processed K до prediction лише в окремих pose-alignment умовах | K передано в model; transformed K отримано власним DA3 preprocessor | використовувати processed mean focal у формулі DA3 | resolved |
| 2026-10-20 | Назар (бос) | `prediction.conf` дорівнює None | first TUM frame traceback | цей checkpoint не повертає confidence map | fallback mask із одиниць | confidence ablation відкласти або взяти іншу confidence proxy | resolved with limitation |
| 2026-10-23 | Ярополк (дубєнь) | runtime probe втрачав venv packages | src/rt_mapping/slam/setup.py; regression test test_runtime_probe_preserves_virtual_environment_interpreter | resolve() на Python symlink запускав base interpreter | probe зберігає absolute venv path без dereference | native imports реально пройшли у .venv-pyslam | resolved |
| 2026-10-23 | Ярополк (дубєнь) | B0 run `_01`: assertion на frame 3, remove_frame_view | results/runs/yaropolk_b0_fr1_xyz_200_20261023_01/upstream.log; docs/WP2_SETUP.md | launcher не відтворював shebang upstream python3 -O; underlying debug assertion condition не виправлено | stopped only own failed process group; new run ID, explicit python_optimization=1 | `_02` завершив 200 frames; debug-mode issue лишається upstream limitation | accepted with limitation |
| 2026-10-21 | Назар (бос) | historical runner записував confidence з одиниць і GT depth у prediction NPZ | results/runs/tum_fr1_xyz_da3metric/frame_*.npz | fallback із першої версії runner | — | C5: `confidence=None` (`has_confidence=false`), GT лише в evaluation; historical files не змінювались | resolved (C5) |
| 2026-10-21 | Назар (бос) | `src/rt_mapping/models/` не з'являвся у `git status` | `git check-ignore -v` → `.gitignore:27:models/` | правило для ваг моделей зачіпало й Python package | — | package перейменовано на `rt_mapping/adapters/`; додано test, що жоден файл у `src/` не git-ignored | resolved |
| 2026-10-21 | Назар (бос) | depth C5 vs historical на кадрах 4 і 16 відрізняється до 0.8 / 3.5 mm | scratch probe: той самий виклик DA3 тричі в одному процесі на кадрі 16 дає різні результати на ~0.01% pixels; raw output кадру 0 побітово однаковий для path/array input з K і без K | run-to-run недетермінізм DA3 inference на GPU; конкретний kernel — гіпотеза (bf16 autocast / attention) | порівняння path vs array input, з K і без K | прийнято: метрики збігаються до 1.5e-7; clean run `c5_clean_parity_f20_721909f` дає ту саму різницю з historical, а його кадр 16 побітово = попередньому C5 run (між окремими запусками C5 різниці не видно, у межах одного процесу повтори відрізнялись) | accepted limitation |

Правило: якщо причина не доведена, писати «гіпотеза», а не подавати її як факт. Log/trace зберігати текстом або посиланням на issue; screenshot alone недостатній.

## 5. Відкриті організаційні питання

- [x] команда: Назар (бос), Ярополк (дубєнь), Юліан (піндос);
- [ ] дата та точний часовий ліміт проміжної презентації;
- [ ] дата фінального дедлайну;
- [ ] hardware кожного учасника (OS, GPU, VRAM, RAM);
- [x] repo public (GitHub metadata перевірено); доступність конкретному викладачу не перевіряли;
- [ ] допустима ліцензія фінального коду;
- [x] Назар координує scope/release за PLAN; Юліан виконує WP4 integration;
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
| D008 | 2026-10-21 | K_processed нових DA3 runs: C3 `resize_intrinsics` (цілі центри pixels) на кожен resize DA3 (640×480 → 384×288 → 378×294); intrinsics від DA3 не використовуються (DA3METRIC-LARGE їх не повертає). Historical runner мав cx·sx, cy·sy: різниця −0.2047 / −0.1938 px, focal і depth не змінюються | proposed (C5) | cv2.resize, яким DA3 робить resize, вирівнює центри pixels; tests/test_da3_metric_adapter.py; definitive parity run c5_clean_parity_f20_721909f (commit 721909f). Historical results не перераховуються |
