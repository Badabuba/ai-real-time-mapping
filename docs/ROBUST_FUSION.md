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
