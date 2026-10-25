# P1-robust: failure-aware sparse-anchored dense fusion

План і межі: [P1_ROBUST_EXTENSION_PLAN.md](P1_ROBUST_EXTENSION_PLAN.md). Цей документ веде лише Юліан; кожен chunk U-01…U-04 додає свій розділ.

## 1. Мета і гіпотеза

На real smoke (`yulian_tum_e2e_f200_20261025_01`) P1-global має map accuracy 0.0924 m проти 0.0323 m у B1-oracle, а Chamfer-L1 — 0.0887 проти 0.0329 m. B1 використовує ті самі P1 pose і scale, тому розрив пояснює помилка dense depth, а не scale чи trajectory.

**Гіпотеза:** GT-free per-frame сигнали зі sparse SLAM map (anchor ratio, residuals, tracking state) дозволяють виявити та скоригувати або відкинути ненадійні depth frames і так зменшити помилку P1-global.

Закрити розрив P1→B1 — це гіпотеза, а не вимога завершення. Коректно виміряний негативний результат зберігається й публікується. Real-time не заявляється.

## 2. U-01 — діагностика по keyframe

### 2.1 Метод

**Фаза A, GT-free** (`src/rt_mapping/alignment/frame_signals.py`):

1. Перевірити provenance: sha256 slam/geometry `run.json` має збігатися з `inputs.json` comparison run; P1-global child run має статус `ok`.
2. Повторити merged correspondences і landmark holdout split з `runs/mapping_run.py`. Перевірити їх проти записаного `residuals.csv`: `frame_id`, `point_id` і `withheld` мають збігатися точно.
3. Для кожного retained keyframe порахувати:
   - кількість pairs (усі / calibration / withheld);
   - inlier ratio і median |residual| за global scale `s`;
   - withheld median |residual|;
   - coverage calibration inliers у 4×4 bins;
   - статистики predicted depth;
   - tracking state (null + причина, якщо export відсутній).
4. **Anchor ratio `a_f`:** merged `estimate_scale` у зворотному напрямку (`z_pred` → `s·z_slam`), лише на calibration pairs цього кадру.
5. Записати `frame_signals.csv`, `signals.json` і `run.json` **до** будь-якого читання GT. Це перевіряє тест.

**Фаза B, evaluation only** (`src/rt_mapping/evaluation/frame_diagnostics.py`):

- per-frame AbsRel/RMSE/δ1 з `metrics.json` geometry run, з повторним обчисленням через oracle GT для перевірки;
- per-keyframe map contribution: точки кадру з metric pose, записаний SE(3) evaluation transform, cKDTree-відстань до `reference_evaluation_only.npz`;
- Spearman ρ (average ranks);
- failure table.

### 2.2 Пороги (pre-registered, не підбиралися за GT)

| Flag | Правило | Джерело |
|---|---|---|
| A1 | `a_f` = null: < 30 anchors або inlier ratio < 0.5 | merged `min_inliers`, `min_inlier_ratio` |
| A2 | \|log a_f\| > log 1.25 | δ1-смуга depth metric (EXPERIMENTS §4.2) |
| A3 | withheld median \|residual\| > 0.10 m (лише якщо є ≥ 1 withheld pair) | merged `residual_threshold_m`, правило `alignment/causal.py` |
| A4 | coverage calibration inliers < 4/16 bins | merged `min_coverage_bins` |
| S1 | tracking state відомий і ≠ OK | контракт Y-01 (`contracts/slam.py`) |

У U-01 flags лише звітуються; gating не застосовується.

### 2.3 Результати (run `yulian_u01_diag_smoke200_8b5b8a7_01`)

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

### 2.4 Висновки для U-02 (без зміни порогів)

- На fr1/xyz per-frame metric scale DA3 вже узгоджений зі sparse SLAM map у межах ±6%. Сигнал |log a_f| не корелює з map error (ρ = −0.20).
- Отже, per-frame anchoring (U-02/U-03) на цьому run, ймовірно, дасть малий ефект. Pre-registered gate з порогами з §2.2 не відкине жодного кадру.
- Це буде виміряно в U-03 і записано як є. Пороги не змінюються після перегляду GT.
- Найпомітніший описовий зв'язок із map error мають низький inlier ratio та далека сцена (ρ ≈ 0.32–0.33). Це вказує на локальні помилки depth (D2), а не на per-frame scale (D1).
- Pixel-level фільтрація (stretch U-S1) — природний наступний крок, якщо U-03 підтвердить нульовий ефект anchoring.

### 2.5 Обмеження

- Одна проста послідовність; n = 22.
- Anchors беруться з фінального BA snapshot, тобто метод offline і non-causal.
- GT reference побудована з тих самих keyframes зі спільною RGB calibration (задокументоване наближення).
- Tracking telemetry недоступна для historical run.
- U-01 не будує нової карти й не робить gating. Немає real-time claims.

### 2.6 Команда

```powershell
python scripts/run_frame_diagnostics.py `
  --comparison-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.comparison `
  --slam-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.slam `
  --geometry-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.geometry `
  --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz --manifest data/manifests/tum_fr1_xyz.json `
  --run-id <new_unique_run_id> --plot
```

Потрібні: `numpy`, `scipy`, `matplotlib`, `Pillow` (extras `.[dev,benchmark]`). Без GPU, Docker чи pySLAM. CPU-тести:

```powershell
python -m pytest tests/test_frame_diagnostics.py tests/test_import_hygiene_robust.py -q
```

## 3. U-02 — per-frame sparse anchoring і frame gate

### 3.1 Метод (GT-free)

Код: `src/rt_mapping/alignment/anchoring.py`, CLI `scripts/run_anchor_gate.py`, конфіг `configs/robust_fusion.json`.

1. Preflight без запису run dir: валідація конфігу (точні ключі на кожному рівні, у кожного порогу є `source`), provenance і `residuals.csv` cross-check з U-01 (`load_sources`, `rebuild_pairs`, `check_recorded_residuals`).
2. Конфіг має збігатися з порогами, з якими записано source comparison run (`residual_threshold_m`, `min_inliers`, `min_inlier_ratio`, `min_coverage_bins`, `voxel_size_m`, `thresholds_m`) і з U-01 `ANCHOR_BAND`. Інакше — відмова.
3. Сигнали рахує незмінений U-01 `frame_signals` (без дублювання коду).
4. **Anchoring:** `anchored_prediction(prediction, a_f)` повертає нову in-memory prediction з `z' = a_f · z_pred` (float64 добуток → float32 контракту); `valid_mask`, confidence, K і metadata без змін; файли не пишуться. Якщо `a_f` = null (A1), кадр лишається некоригованим. NaN/Inf/≤ 0 відхиляються з помилкою. SLAM poses зберігають global scale `s`.
5. **Gate:** `gate_decision(signals, config)` відкидає кадр, якщо спрацював будь-який flag (правила з §2.2, строгі нерівності як у плані). Flag, який неможливо оцінити, записується як `unavailable` з причиною і не спрацьовує: A2 без `a_f`, A3 без withheld pair, S1 без tracking export. Некоректні входи (NaN, від'ємні значення, неузгоджені null) викликають помилку, а не default.
6. **GT-free валідація:** withheld median |residual| кадру до (`|s·z_slam − z_pred|`) і після (`|s·z_slam − a_f·z_pred|`) корекції на тих самих withheld pairs. Лише звітується, для підбору не використовується.
7. Артефакти: `frame_signals.csv`, `anchor_gate.csv` (по рядку на keyframe: входи рішення, `applied_scale`, flags `true/false/unavailable`, `decision`, `decision_reason`), `anchor_gate.json` (лічильники, withheld до/після, список рішень для U-03, sha256 конфігу) і `run.json`.

**Розділення GT:** модуль і CLI не імпортують `rt_mapping.evaluation.*` і `data.tum` (AST-тест). Subprocess-тест перевіряє, що під час запуску CLI не завантажено жодного модуля `rt_mapping.evaluation`. Ще один тест видаляє всі GT/evaluation-only матеріали fixture і перевіряє, що рішення побайтово ті самі.

Конфіг заморожується після merge U-02. U-03 відмовляється працювати, якщо sha256 `configs/robust_fusion.json` відрізняється від записаного в summary U-02.

### 3.2 Результати (run `yulian_u02_anchor_gate_smoke200_2e6fad5_01`)

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

### 3.3 Обмеження

- Одна проста послідовність; 22 keyframes. Anchors із фінального BA snapshot — offline і non-causal.
- Withheld residual до/після — GT-free перевірка узгодженості, не метрика точності.
- S1 недоступний для historical run; gated variant на цьому run збігається з anchored.
- U-02 не будує карту. Немає real-time claims.

### 3.4 Команда

```powershell
python scripts/run_anchor_gate.py `
  --comparison-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.comparison `
  --slam-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.slam `
  --geometry-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.geometry `
  --run-id <new_unique_run_id>
```

`--config` за замовчуванням `configs/robust_fusion.json`. Без GPU, Docker, pySLAM і без GT. CPU-тести:

```powershell
python -m pytest tests/test_anchoring.py tests/test_import_hygiene_robust.py -q
```

## 4. U-03 — real smoke: control, P1-anchored, P1-anchored+gate

### 4.1 Метод

Код: `src/rt_mapping/runs/robust_fusion_run.py`, CLI `scripts/run_robust_fusion.py`.

**Preflight (без run dir, без GT):**
- sha256 `configs/robust_fusion.json` має дорівнювати hash у committed U-02 summary, інакше відмова;
- provenance source runs має дорівнювати записаній у U-02 summary;
- `residuals.csv` cross-check з U-01;
- рішення gate перераховуються незміненими U-01/U-02 функціями і мають точно збігатися з committed рішеннями U-02.

**Фаза A, GT-free:**
1. Control: незмінений публічний `run_mapping` із записаним mapping config; відрізняється лише `plot`. Перевірка §3.5 плану: `map.npz` побайтово тотожний записаному P1-global, інакше voxel keys/counts і межа похибки float64.
2. Цикл fusion для варіантів спершу відтворює control map побайтово на некоригованій depth. Тому варіанти відрізняються від control лише anchored depth і gating.
3. `P1-anchored`: `z' = a_f · z_pred` для кожного кадру з `a_f`. `P1-anchored+gate`: ті самі кадри без rejected. Пози — незмінений global scale `s`.
4. `phase_a.json`, усі карти й `run.json` записуються **до** відкриття GT (тест ordering).

**Фаза B, evaluation only:** незмінений `evaluate_map` для кожного варіанта, з тим самим voxel size 0.02 m, τ = {2, 5, 10} cm, crop, записаним SE(3) transform і `reference_evaluation_only.npz`. Метрики control мають дорівнювати записаному рядку P1-global. Рядки B0/B1/P1-raw копіюються після перевірки, що вони мають той самий evaluation transform. Per-frame AbsRel/RMSE/δ1 і map contribution рахуються до і після anchoring на oracle GT grid.

### 4.2 Результати (run `yulian_u03_robust_smoke200_cc7a4d9_01`)

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

### 4.3 Обмеження

- Одна проста послідовність, 22 keyframes. Anchors із фінального BA snapshot — offline і non-causal.
- S1 не оцінювався (немає tracking export). Gate не відкинув жодного кадру, тому на реальних збоях він не перевірений.
- GT reference — наближення; per-frame depth рахується через oracle grid (до 6.24e-4 AbsRel від geometry metrics, U-01).
- Пороги не змінювалися після перегляду GT; повторних запусків не було. Held-out (fr3) не використовувався. Немає real-time claims.

### 4.4 Команда

```powershell
python scripts/run_robust_fusion.py `
  --comparison-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.comparison `
  --slam-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.slam `
  --geometry-run results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.geometry `
  --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz --manifest data/manifests/tum_fr1_xyz.json `
  --u02-summary results/summaries/yulian_u02_anchor_gate_smoke200_2e6fad5.json `
  --run-id <new_unique_run_id> --plot
```

CPU-тести: `python -m pytest tests/test_robust_fusion_run.py -q`.
