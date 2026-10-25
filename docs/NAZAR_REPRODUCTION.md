# N-02: незалежне відтворення smoke-pipeline на другій машині

- **Chunk:** N-02 (`docs/TWO_PERSON_COMPLETION_PLAN.md` §5).
- **Виконавець:** Nazar, як незалежний reproducer WP4 (Yulian) і WP2 runtime (Yaropolk). Ownership не змінюється.
- **Reference:** `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`, run `yulian_tum_e2e_f200_20261025_01`, clean `4952e37`.
- **Підсумок:** **disclosed failure.** SLAM, DA3 geometry і global alignment/fusion завершилися `ok` з clean commit. GT-based comparison stage (B0/B1/P1 rows, ATE/RPE, map metrics) впав, тому pipeline run має status `failed`. Зміна evaluation rules виходить за межі N-02, а повторні запуски заради іншого набору keyframes заборонені, тож PR містить evidence і blocker report.
- **Evidence:** `results/summaries/nazar_n02_e2e_smoke200_0fc564f.json` (з source hashes), `results/plots/nazar_n02_residuals.png`, config `configs/pipeline.nazar.smoke200.docker.json`.

## 1. Середовище

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

## 2. Runtime-налаштування (без змін source/protocol)

1. **Config:** копія `configs/pipeline.tum.windows-docker.json`. Змінено лише container name і DA3 interpreter (`.venv\Scripts\python.exe`).
2. **Standalone clone замість git worktree.** У worktree файл `.git` вказує на Windows path, і `git rev-parse` всередині Linux container не працює (attempt 1). Тому run запускався з окремого clone того самого branch/commit.
3. **Dataset усередині repository.** WP2 preflight відхиляє `data/raw`, якщо resolved path виходить за межі repo root, тому junction не підходить. fr1/xyz archive і extraction скопійовано в ignored `data/raw/`. SHA-256 archive `a0236d97…` збігається з manifest.
4. **`.venv` і `checkpoints` як junctions** на перевірені локальні environment/cache. Усередині container вони видимі як symlinks, а `.gitignore` патерни з `/` на кінці їх не покривають. Тому в локальний `.git/info/exclude` clone додано `/.venv` і `/checkpoints` (не tracked). Host і container показують clean tree; `dirty_worktree=false` у всіх stages.
5. **Пам'ять.** Перед фінальним run зупинено (не видалено) два сторонні compose-контейнери `pandora-postgres-1` і `pandora-redis-1` (project `pandora`). Після цього вільно 16.6 GB, тому restart Docker Desktop не знадобився. Під час run free RAM була 12.8–15.9 GB (84 samples по 5 s).

## 3. Усі спроби

| Run ID | Commit | Status | Причина |
|---|---|---|---|
| `nazar_n02_e2e_smoke200_65571cc_01` | `65571cc` | failed | SLAM adapter exit 2: `git rev-parse` усередині container (worktree `.git` → Windows path). Збережено в N-02 worktree. |
| `nazar_n02_e2e_smoke200_65571cc_02` | `65571cc` | failed | SLAM stage ok. Geometry launch `[WinError 2]`: на цьому host `CreateProcess` не знаходить відносний executable `.venv/Scripts/python.exe` з `/` (відтворено поза pipeline, також у main checkout). Виправлено лише в config (backslashes), commit `0fc564f`. Чому forward-slash path працював у Yulian — гіпотеза: інший host interpreter або спосіб запуску. |
| `nazar_n02_e2e_smoke200_0fc564f_01` | `0fc564f` | interrupted | SLAM stage ok. Launcher зупинено під час DA3 inference memory-pressure reaper'ом Claude Code. `run.json` лишився зі status `running` і **не редагувався**. |
| `nazar_n02_e2e_smoke200_0fc564f_02` | `0fc564f` | failed | SLAM ok, geometry ok, global alignment/fusion ok. Comparison: `all retained keyframes need distinct associated GT poses for a shared comparison`. |

Усі run directories збережено byte-for-byte; SHA-256 до і після фінального run збігаються. SHA-256 `run.json` кожної спроби є в summary.

## 4. Результат по stages (`nazar_n02_e2e_smoke200_0fc564f_02`)

| Stage | Status | Elapsed |
|---|---|---|
| SLAM (Docker, pySLAM `96019cf`) | ok | 376.9 s (у reference 303.5 s) |
| Geometry (DA3METRIC-LARGE, CUDA) | ok | 53.4 s (у reference 71.1 s) |
| comparison.global (alignment + fusion) | ok | 6.8 s wall |
| comparison (B0/B1/P1, GT evaluation) | **failed** | — |
| pipeline | **failed** | — |

## 5. Діагностика failure

- `src/rt_mapping/evaluation/oracle.py` (`load_oracle_inputs`, код Yulian без змін) вимагає GT pose у межах 20 ms для **кожного** retained keyframe.
- У цьому run SLAM утримав 18 keyframes (reference: 22). Keyframe 16 (frame 195, t = 1305031108.876515) лежить у ~110 ms розриві `groundtruth.txt` fr1/xyz (між 1305031108.8357 і 1305031108.9458); найближчий GT pose за 40.8 ms. 17 з 18 keyframes associated.
- Набір keyframes у reference run цей розрив не зачепив. Вибір keyframes у upstream pySLAM недетермінований між машинами (seed policy у SLAM `run.json`).
- **Класифікація:** обмеження robustness WP4 evaluation, а не помилка N-02 runtime. Виправлення (виключати unmatched keyframes з GT evaluation, інтерполювати GT або змінити tolerance) змінює evaluation rules. За планом (D-2, stop conditions N-02) це окремий focused `fix/nazar-*` PR з regression test, з повідомленням Yulian. У N-02 нічого не виправлено, thresholds не змінено, повторних запусків для іншого набору keyframes не було.

## 6. Порівняння з reference (cross-machine variation, не parity)

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

## 7. Команди

```powershell
docker build -f containers/wp2.Dockerfile -t rt-mapping-wp2:96019cf .
docker run -d --name rt-mapping-wp2-nazar --shm-size=1g --memory=10g --cpus=4 --mount "type=bind,source=$((Get-Location).Path),target=/workspace" rt-mapping-wp2:96019cf
docker exec rt-mapping-wp2-nazar python scripts/check_wp2_environment.py --pyslam-root /opt/pyslam --pyslam-python /usr/local/bin/python --probe-runtime
docker exec --env WP2_NATIVE_SPARSE_TEST=1 --env WP2_PYSLAM_ROOT=/opt/pyslam rt-mapping-wp2-nazar python -O -m unittest discover -s tests -p test_pyslam_sparse_native.py -v
.venv\Scripts\python.exe scripts\run_pipeline.py --config configs\pipeline.nazar.smoke200.docker.json --run-id nazar_n02_e2e_smoke200_0fc564f_02
```

Docker команди з `--env /opt/...` треба запускати з PowerShell: Git Bash (MSYS) переписує `/opt/pyslam` у Windows path, і тоді `pyslam` не імпортується.

## 8. Blocker і наступний крок

- **Blocker:** повний B0/B1/P1 comparison не можна відтворити на цьому run без зміни WP4 evaluation (обробка keyframes без GT у розривах `groundtruth.txt`).
- **Рекомендація:** окремий `fix/nazar-*` PR в `evaluation/oracle.py`/`comparison_run.py` з явно задокументованим правилом для keyframes без GT і regression test, з повідомленням Yulian. Після merge — новий run_id за D-5-подібним правилом (обидва runs звітуються). Порядок N-04 це не блокує: SLAM stage `nazar_n02_e2e_smoke200_0fc564f_02.slam` має status `ok`, і його можна reuse.

## 9. Обмеження

- Pipeline run має status `failed`. Trajectory і map metrics не відтворено.
- Один run; повтори для оцінки variance не проводились.
- Інше DA3 environment (torch 2.11+cu128), ніж у reference.
- GT використовується лише в evaluation code; на результатах нічого не тюнилось.
- Немає real-time claim і немає metric-scale claim з alignment.
