# WP3/WP4 completion — 25 жовтня 2026

WP3/WP4 Юліана завершені: code core, runnable integration, реальна пара sparse/dense, residual plot, fused cloud та smoke comparison. Попередній PR #7 мав лише synthetic evidence; [PR #8](https://github.com/Badabuba/ai-real-time-mapping/pull/8) додає завершення. Повний held-out benchmark і demo лишаються спільними задачами команди.

## Реалізований залишок

- `scripts/run_pipeline.py --config <json> --run-id <unique>` запускає WP2/WP1 CLI через explicit argv або повторно використовує completed runs; потім робить mapping чи comparison. Немає shell interpolation, downloads або installations у launcher. Див. `configs/pipeline.tum.example.json`.
- `scripts/run_mapping_comparison.py`: B0 sparse із shared P1 scale, P1-raw (явне scale=1 припущення), P1-global, B1 oracle зі **спільними P1 metric poses**, keyframe/confidence ablations. Oracle не підбирає scale за GT.
- `evaluation/trajectory.py`: one-to-one timestamp association, SE(3)/Sim(3) ATE та RPE. RPE delta — matched retained-keyframe rows, не всі RGB frames. Sim(3) diagnostic окремо від metric SE(3) result.
- `evaluation/map_geometry.py`: однаковий voxel/crop, accuracy/completeness, symmetric Chamfer-L1 = 0.5·(mean forward + mean backward), F-score@2/5/10 cm. Один trajectory-only SE(3) evaluation transform для всіх maps; per-map ICP/Sim(3) не використовується.
- `alignment/causal.py`: optional P1-window, лише поточне/минуле вікно, стабільний landmark-ID hash split. Не вистачає startup support — явна помилка, без майбутнього/global fallback. Вмикається `causal_window_frames>0` лише як development ablation.
- `run_comparison_smoke.py --plot`: повний synthetic reference/oracle/comparison fixture, явно позначений synthetic. CPU suite: **472 passed, 1 native skip**; Ubuntu/Windows Python 3.11/3.12 CI. Окремо installed-backend sparse API test: **1 passed**.

## Дані та runtime

За явним дозволом Юліана завантажено frozen TUM fr1/xyz: SHA-256 `a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98`; `build_tum_manifest.py --check` пройшов. DA3METRIC-LARGE revision `4010e39f3634a45bc60553321fb49fb760bd594e`, weights SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776` збігається з Nazar evidence.

DA3 isolated environment: `.local/da3-venv`, використовує наявний host torch 2.7.1+cu118, RTX 3070 Ti Laptop 8 GB; NumPy 1.26.4 та OpenCV 4.11 встановлені локально у venv. Host packages не замінювалися. Clean 200-frame run `yulian_da3_f200_b43c384` (`b43c384`, `dirty_worktree=false`) завершився: mean AbsRel **0.092655**, RMSE **0.177196 m**, δ1 **0.964949**; warm median **125.462 ms**, p95 **157.248 ms** (warmup=1). Усі 200 C3 predictions існують. [Summary із source hashes](../results/summaries/wp1_da3metric_yulian_tum_fr1_xyz_200.json). Це smoke inference evidence, не alignment або held-out benchmark.

Незалежна перевірка trajectory evaluator через `evo` на 60 TUM poses із заданим scale/noise дала ATE/RPE RMSE різницю ≤1.3e-16 для SE(3) та Sim(3). Це parity перевірка математичного evaluator, не accuracy самого SLAM.

Native pySLAM runtime зібрано в окремому Docker container `rt-mapping-wp2-yulian`, без system packages на Windows/Ubuntu host. Source pinned `96019cf`; контейнерна копія потрібна для коректних Unix symlinks. Opt-in test реальних Map/KeyFrame/MapPoint APIs та sparse export пройшов: **1 test, OK**. Dataset/source/entry-point preflight: **ok**. Це Linux runtime на Windows/Docker host, не native Windows SLAM support.

Linux recipe та compatibility flags: [WP2_LINUX_CONTAINER.md](WP2_LINUX_CONTAINER.md). Відповідний full-stage config: `configs/pipeline.tum.windows-docker.json`.

## Реальний end-to-end результат

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

## Обмеження evaluation

- GT доступний лише evaluation/oracle code. P1-global завершується до читання GT; інші P1 controls не отримують GT як input.
- Усі методи використовують frozen RGB calibration. Реєстрована TUM depth має нетривіальну rectification; shared RGB K/Brown reference є задокументованим наближенням. [Офіційний формат TUM](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats) рекомендує ROS-default intrinsics для прямої побудови depth cloud. Під час цієї роботи frozen calibration мовчки не змінюється.
- Confidence ablation пропускається з explicit reason, якщо DA3 не повертає confidence. Fake confidence не створюється.
- Stage reuse не вимірює SLAM/model inference заново. CPU fusion timing не є end-to-end FPS. Повний held-out benchmark та tracking normalization лишаються shared/adapter work packages.

## Команди

```powershell
python -m pip install -e ".[dev,benchmark]"
python -m pytest tests -q
python scripts/run_comparison_smoke.py --plot
python scripts/run_pipeline.py --config configs/pipeline.tum.example.json --run-id unique_tum_pipeline
# Перевірений Windows/Docker + CUDA шлях:
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id unique_real_pipeline
```

Приклад full pipeline потребує вже встановлених native SLAM/CUDA runtimes. Для іншого OS замінити stage `command` на відповідний Python/WSL/Docker argv. Для existing artifacts задати stage `{"reuse_run": "results/runs/<actual_run_id>"}`. Launcher додає власні `--run-id` і `--output-root`; не задавати їх у command.
