# WP1: локальна інтеграція поверх develop — 24 жовтня 2026

Owner: Назар. Base `ce095fa` включає merged PR #4 (C5) і PR #5 (WP2 Ярополка).
UniDepth/frozen splits/selection — локальна робота для review, не team-approved merge.

## Контракти

- `FrameRecord`: raw RGB, integer-centre calibrated K, exact timestamp/frame_id.
- Обидва adapters повертають C3 `GeometryPrediction`, camera-z depth у метрах, без GT.
- DA3 native output має resize K; UniDepth повертає raw grid, `K_processed=FrameRecord.K`; predicted camera-head K лише diagnostic.
- UniDepth official confidence — estimated scale-invariant log error. Зберігаємо `-error` для higher=better, без probability/heuristic normalization; absent output → None. Historical runs з reciprocal mapping лишаються immutable.
- Runner C5 повторно використано, додано optional prewarm і raw-grid evaluation. Historical CLI/defaults DA3 збережені.

## Перевірка на наявних environments

```powershell
.venv/cpu/Scripts/python.exe -m pytest tests -q
.venv/unidepth/Scripts/python.exe scripts/run_geometry_benchmark.py --model unidepth --manifest data/manifests/tum_fr2_desk_selection50.json --split selection --frames 50 --prewarm 10 --run-id <new-unidepth-id>
.venv/Scripts/python.exe scripts/run_geometry_benchmark.py --model da3 --manifest data/manifests/tum_fr2_desk_selection50.json --split selection --frames 50 --prewarm 10 --run-id <new-da3-id>
.venv/cpu/Scripts/python.exe scripts/verify_geometry_run.py results/runs/<new-unidepth-id> --assets-root .
.venv/cpu/Scripts/python.exe scripts/verify_geometry_run.py results/runs/<new-da3-id> --assets-root .
.venv/cpu/Scripts/python.exe scripts/compare_geometry_models.py results/runs/<new-da3-id> results/runs/<new-unidepth-id> --output results/summaries/<new-scorecard>.json
```

Перед GPU experiments потрібні clean commit і чистий worktree. Run dirs/summary ніколи не перезаписуються.
UniDepth setup/source/license: UNIDEPTH.md. Data freeze: DATASET_FREEZE.md. Exact evaluation/rubric: SELECTION_PROTOCOL.md.
Fresh CPU dependencies: requirements/wp1-cpu.txt; DA3 environment не змінювати.

## Перевірено 24 жовтня

Implementation commits `6fa2f55`, namespace-source fix `463b446`. Clean smoke і paired selection50 на `463b446` успішні; IDs та hashes — `results/summaries/wp1_integration_verification_20261024.json`. 4 manifests byte-identical; per-frame metrics/masks і scorecard independently recomputed. Historical DA3 та merged WP2 files збережені.
Full documented CPU command: 418 passed, 2 skipped, 2 failures у незміненому WP2 на Windows (`os.killpg`, symlink privilege). Це відомий upstream integration prerequisite; WP1 tests passed, але full suite не позначаємо green. Dependencies не встановлювали.

## Передача WP2/WP3

Повна папка sparse run Ярополка не входить до Git: див. WP2_SPARSE_EXPORT.md.
Потрібні matching depth NPZ для його keyframes, poses з того самого `keyframes.npz` snapshot та явне зіставлення distorted/undistorted pixels.
Поточний paired50 benchmark перевіряє лише depth models. AlignmentResult, fusion, map metrics та end-to-end p95 він не доводить.
Review: Ярополк або Юліан мають відтворити smoke та записати sign-off; самопогодження немає.
