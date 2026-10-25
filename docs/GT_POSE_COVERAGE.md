# Keyframes без GT pose: політика GT evaluation

- **Власник:** Yulian (evaluation-код WP4: `evaluation/oracle.py`, `runs/comparison_run.py`).
- **Привід:** N-02, run `nazar_n02_e2e_smoke200_0fc564f_02` (PR #18). SLAM, DA3 depth, alignment і fusion завершилися `ok`. Comparison упав, бо keyframe `frame_id` 195 (t = 1305031108.876515) лежить у ~110 ms розриві `groundtruth.txt` fr1/xyz. Найближчий GT pose за 40.8 ms, а tolerance 20 ms.
- **Обсяг:** лише GT-dependent evaluation у comparison. SLAM, depth prediction, alignment, fusion, runtime gate, thresholds, scale/map rules, manifests і held-out policy не змінено.

## 1. Правило

1. Tolerance асоціації лишається **0.020 s** (`max_timestamp_delta_s` у `configs/mapping_comparison.json`, без змін).
2. Асоціація та сама, що й раніше (`evaluation/trajectory.associate_timestamps`): one-to-one, найближчий timestamp, межа включна (|Δt| ≤ 0.020 s у floating point). Інтерполяції немає, farther pose не використовується, tolerance не збільшується.
3. Keyframe **GT-eligible**, лише якщо йому дісталася окрема GT pose у межах tolerance.
4. Keyframe без такої pose **недоступний для GT evaluation**. Це не invalid SLAM/depth frame. Він лишається в SLAM export, у predicted depth, у кожній fused map і в non-GT runtime records.
5. Причини виключення:
   - `no_gt_pose_within_tolerance`: у межах tolerance немає жодної GT pose;
   - `gt_pose_within_tolerance_assigned_to_closer_keyframe`: one-to-one асоціація віддала єдину близьку pose ближчому keyframe.

## 2. Спільний eligible set

Один явний список `evaluated_frame_ids` діє для всіх методів (B0, B1, P1-global, P1-raw, P1-keyframes-*, P1-window, P1-confidence-*):

| Обчислення | Які keyframes |
|---|---|
| ATE/RPE для кожного методу, B0 Sim(3) diagnostic, P1 SE(3) evaluation transform | лише eligible, однакові для всіх |
| GT reference cloud (GT depth + GT pose) | лише eligible; одна reference для всіх методів |
| Estimate maps (P1-*, B1 GT-depth control) | усі retained keyframes, однакові для всіх. B1 бере GT depth і P1 poses, GT pose йому не потрібна |
| B0 sparse landmarks | без змін (не frame-based) |

Отже, виключений keyframe не може потрапити в один метод і бути виключеним з іншого. RPE рахується по сусідніх eligible keyframes (`rpe_delta_unit = matched_pose_rows`, як і раніше), тому пара може перекривати виключений keyframe.

## 3. Мінімум зразків і відмови

- 0 eligible keyframes: comparison `failed`, reason `no retained keyframe has a GT pose within 0.02 s; GT evaluation is unavailable`.
- 1–2 eligible: ATE/RPE і спільний SE(3) transform для map metrics математично потребують ≥ 3 точок. Comparison `failed` з reason `insufficient_gt_coverage: …` (кількість і excluded IDs). Coverage записується в `inputs.json` до відмови. Метрики не підставляються.
- В обох випадках P1-global child (`methods/<id>.global`) уже завершений і не змінюється.

## 4. Звітність coverage

Machine-readable, той самий об'єкт `gt_pose_coverage` (у `inputs.json` він називається `evaluation_only.gt_pose_eligibility`):

| Поле | Значення |
|---|---|
| `policy` | `exclude_keyframes_without_gt_pose_within_tolerance` |
| `max_timestamp_delta_s` | 0.02 (незмінна tolerance) |
| `association` | опис правила асоціації |
| `candidate_keyframes`, `evaluated_keyframes`, `excluded_keyframes` | кількості |
| `coverage_fraction` | evaluated / candidate |
| `evaluated_frame_ids`, `excluded_frame_ids` | у порядку timestamps keyframes |
| `excluded[]` | `frame_id`, `timestamp_s`, `nearest_gt_delta_s` (лише для діагностики, ця pose не використовується), `reason` |

Де записано: `inputs.json`, `trajectory_evaluation.json`, `metrics.json` (і в кожному row: `gt_evaluated_keyframes`, `gt_candidate_keyframes`, `gt_coverage_fraction`), `evaluation/<method>.json`, `comparison.csv` (ті самі три колонки). Human-readable: колонка `GT keyframes` у таблиці `report.md`, note і розділ `## GT pose coverage` з таблицею виключених keyframes.

## 5. Сумісність із попередніми результатами

- Якщо всі keyframes мають GT pose, eligible set дорівнює всім keyframes, і числа не змінюються. Додаються лише поля coverage, колонки CSV і рядки report.
- Перевірка на реальних даних цієї машини: comparison на stages `yulian_tum_e2e_f200_20261025_01` (22/22 keyframes eligible). Старий код (`ab80f42`) і новий код дали побітово однакові oracle arrays/reference і однакові числа в `metrics.json`, `trajectory_evaluation.json`, `evaluation/*.json` і child maps (timing не порівнювався). Відносна різниця з записаним run `4952e37` ≤ 2.5e-16. Причина — інше середовище (numpy 2.4.6/Python 3.11 проти 2.2.4/3.12), не цей fix. Вихід цієї перевірки не збережено в `results/`.
- `load_oracle_inputs` за замовчуванням лишається strict, як і раніше. Exclusion вмикає лише comparison (`exclude_missing_gt_poses=True`). U-01 `frame_diagnostics`, U-03 `robust_fusion_run` і `render_robust_fusion_figures.py` поводяться так само: на даних без повного GT coverage вони явно падають. Їх U-01…U-04 evidence не змінено.

## 6. N-02: supplemental comparison-only evaluation (handoff для Nazar)

Сирі виходи N-02 є лише на машині Nazar. Unit tests не доводять, що N-02 успішний. **N-02 завершений лише тоді, коли ця команда успішно відпрацює на локальних outputs Nazar.** SLAM і DA3 не перезапускаються. Comparison заново рахує лише CPU alignment/fusion children і GT evaluation у **новому** run ID. Оригінальний failed run не змінюється.

1. Clean checkout `develop` на merge commit цього fix (`git status` порожній). `<sha7>` — перші 7 символів `git rev-parse HEAD`.
2. До запуску перевірте SHA-256. Шляхи відносно `results/runs/nazar_n02_e2e_smoke200_0fc564f_02/`, `<P>` = `nazar_n02_e2e_smoke200_0fc564f_02`. Значення взято з `results/summaries/nazar_n02_e2e_smoke200_0fc564f.json` → `source_hashes`, крім `groundtruth.txt`: його хеш — з fr1/xyz archive, який перевіряє manifest.

   | Файл | SHA-256 |
   |---|---|
   | `run.json` | `3ec7a60790f4765b6cdb87a8ca0c36103647fdc7aa19131df58c68bdae9e8b48` |
   | `stages/<P>.slam/run.json` | `2e4afa27929392509e4ebe2403e7978ea6237d54f3921cccfff3a8d3cfa2943f` |
   | `stages/<P>.slam/sparse/export.json` | `fcfef9d27ea51ce3d985ae5e31d51844b75c53ccd8af411416fdc62ee9d829c7` |
   | `stages/<P>.slam/sparse/keyframes.npz` | `0a7d64c94f414eb97ad8f2ec06f334ce8f951fc3b058412f886aefb617a7f13c` |
   | `stages/<P>.geometry/run.json` | `c2e0a7a7ad452da2a65ac4d4cd379af84f37da27a56cc41c59b8c68d581a2967` |
   | `stages/<P>.geometry/metrics.json` | `b238569ccb861bf6e1b2b6fd34186fb80c12efce0b4c5dfa9284676476d7eb69` |
   | `stages/<P>.comparison/run.json` | `df0d719bc4f94507f5d3d8cc3c6a669cf353b16761fb16cbfd2d5d42d550e9ed` |
   | `stages/<P>.comparison/methods/<P>.comparison.global/alignment.json` | `d0c457c0af68afa5aaa373852fcc7b8527bb3840e70322c39c163608b7ea4f92` |
   | `data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz/groundtruth.txt` (від кореня repo) | `aac0319a6ef4e1cdf61e779d2152b95aa7e9f7b1749d6d18717b43ddabffede2` |

   Archive SHA-256 `a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98` збігається з manifest. Якщо щось не збігається — зупиніться.
3. Команда (PowerShell, корінь того clone, де лежить run):

   ```powershell
   $src = "results\runs\nazar_n02_e2e_smoke200_0fc564f_02\stages"
   .venv\Scripts\python.exe scripts\run_mapping_comparison.py `
     --slam-run "$src\nazar_n02_e2e_smoke200_0fc564f_02.slam" `
     --geometry-run "$src\nazar_n02_e2e_smoke200_0fc564f_02.geometry" `
     --sequence-dir data\raw\tum_rgbd\rgbd_dataset_freiburg1_xyz `
     --manifest data\manifests\tum_fr1_xyz.json `
     --config configs\mapping_comparison.json `
     --run-id nazar_n02_gt_coverage_eval_<sha7>_01
   ```

   `configs/mapping_comparison.json` дає ту саму effective comparison config, що й pipeline N-02 (`keyframe_intervals` [2, 5], `mapping.plot` true, решта — defaults, tolerance 0.02). Існуючий run ID CLI відхиляє.
4. Після запуску:
   - SHA-256 з кроку 2 не змінилися;
   - `run.json` нового run: `status` `ok`, `dirty_worktree` false;
   - `methods/<run_id>.global/alignment.json`: `scale`, `inlier_count` і `number_of_pairs` збігаються з оригінальним `comparison.global` (1.224085382515751, 3746, 5334). Якщо ні — зупиніться і повідомте;
   - `metrics.json` → `gt_pose_coverage` очікувано: `candidate_keyframes` 18, `evaluated_keyframes` 17, `excluded_frame_ids` [195], `excluded[0].reason` `no_gt_pose_within_tolerance`, `nearest_gt_delta_s` ≈ 0.0408, `max_timestamp_delta_s` 0.02, `coverage_fraction` 17/18 ≈ 0.944444.
5. Evidence: `run.json`, `metrics.json`, `comparison.csv`, `report.md`, `trajectory_evaluation.json`, `inputs.json`, `evaluation/*.json` нового run. Їх SHA-256 разом із coverage, rows і pre/post хешами з кроку 2 запишіть у **новий** `results/summaries/nazar_n02_gt_coverage_eval_<sha7>.json`. Існуючі N-02 summary і docs не редагуються.
6. Позначення: cross-machine reproduction, GT-eligible coverage 17/18 retained keyframes. Це не пряме порівняння з reference Yulian (22/22 keyframes): набори keyframes і eligible frames різні.
