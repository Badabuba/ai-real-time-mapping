# WP3/WP4 completion — 25 жовтня 2026

Юліан попросив завершити не лише code core, а й runnable integration та перевірку. Попередня реалізація PR #7 мала лише synthetic alignment/fusion evidence.

## Реалізований залишок

- `scripts/run_pipeline.py --config <json> --run-id <unique>` запускає WP2/WP1 CLI через explicit argv або повторно використовує completed runs; потім робить mapping чи comparison. Немає shell interpolation, downloads або installations у launcher. Див. `configs/pipeline.tum.example.json`.
- `scripts/run_mapping_comparison.py`: B0 sparse із shared P1 scale, P1-raw (явне scale=1 припущення), P1-global, B1 oracle зі **спільними P1 metric poses**, keyframe/confidence ablations. Oracle не підбирає scale за GT.
- `evaluation/trajectory.py`: one-to-one timestamp association, SE(3)/Sim(3) ATE та RPE. RPE delta — matched retained-keyframe rows, не всі RGB frames. Sim(3) diagnostic окремо від metric SE(3) result.
- `evaluation/map_geometry.py`: однаковий voxel/crop, accuracy/completeness, symmetric Chamfer-L1 = 0.5·(mean forward + mean backward), F-score@2/5/10 cm. Один trajectory-only SE(3) evaluation transform для всіх maps; per-map ICP/Sim(3) не використовується.
- `alignment/causal.py`: optional P1-window, лише поточне/минуле вікно, стабільний landmark-ID hash split. Не вистачає startup support — явна помилка, без майбутнього/global fallback. Вмикається `causal_window_frames>0` лише як development ablation.
- `run_comparison_smoke.py --plot`: повний synthetic reference/oracle/comparison fixture, явно позначений synthetic. Code suite: **470 passed, 1 native skip** на Windows Python 3.12.

## Дані та runtime

За явним дозволом Юліана завантажено frozen TUM fr1/xyz: SHA-256 `a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98`; `build_tum_manifest.py --check` пройшов. DA3METRIC-LARGE revision `4010e39f3634a45bc60553321fb49fb760bd594e`, weights SHA-256 `bbea5b0b3ee389849cffa7ddae89de064a90abd2b055fc5aa99aac68db324776` збігається з Nazar evidence.

DA3 isolated environment: `.local/da3-venv`, використовує наявний host torch 2.7.1+cu118, RTX 3070 Ti Laptop 8 GB; NumPy 1.26.4 та OpenCV 4.11 встановлені локально у venv. Host packages не замінювалися. Clean 200-frame run `yulian_da3_f200_b43c384` (`b43c384`, `dirty_worktree=false`) завершився: mean AbsRel **0.092655**, RMSE **0.177196 m**, δ1 **0.964949**; warm median **125.462 ms**, p95 **157.248 ms** (warmup=1). Усі 200 C3 predictions існують. [Summary із source hashes](../results/summaries/wp1_da3metric_yulian_tum_fr1_xyz_200.json). Це smoke inference evidence, не alignment або held-out benchmark.

Незалежна перевірка trajectory evaluator через `evo` на 60 TUM poses із заданим scale/noise дала ATE/RPE RMSE різницю ≤1.3e-16 для SE(3) та Sim(3). Це parity перевірка математичного evaluator, не accuracy самого SLAM.

Native pySLAM runtime зібрано в окремому Docker container `rt-mapping-wp2-yulian`, без system packages на Windows/Ubuntu host. Source pinned `96019cf`; контейнерна копія потрібна для коректних Unix symlinks. Opt-in test реальних Map/KeyFrame/MapPoint APIs та sparse export пройшов: **1 test, OK**. До завершення real pipeline run WP3/WP4 real validation не вважати done.

Linux recipe та compatibility flags: [WP2_LINUX_CONTAINER.md](WP2_LINUX_CONTAINER.md). Відповідний full-stage config: `configs/pipeline.tum.windows-docker.json`.

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
```

Приклад full pipeline потребує вже встановлених native SLAM/CUDA runtimes. Для іншого OS замінити stage `command` на відповідний Python/WSL/Docker argv. Для existing artifacts задати stage `{"reuse_run": "results/runs/<actual_run_id>"}`. Launcher додає власні `--run-id` і `--output-root`; не задавати їх у command.
