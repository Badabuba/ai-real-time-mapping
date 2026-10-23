# CLAUDE.md

UCU course project "Real-time Mapping with Foundation Models": monocular RGB → pySLAM poses/sparse map + Depth Anything 3 Metric dense depth → scale/Sim(3) alignment → fused point cloud → benchmark vs classical baseline on TUM RGB-D. Team docs are in Ukrainian; keep that language when editing them.

## Read before working
- `docs/PROJECT_STATUS.md` — single source of truth for what is done, by whom, failures, decisions. "Planned" is not "done".
- `PLAN.md` — scope, work packages/owners (WP1 Nazar, WP2 Yaropolk, WP3 Yulian), calendar, Plan B.
- `docs/ARCHITECTURE.md` — data contracts, units, coordinate conventions, failure states.
- `docs/EXPERIMENTS.md` — splits, methods, metrics, required `run.json` fields, ground-truth rules.
- `docs/MODEL_SELECTION.md`, `docs/ENVIRONMENT.md`, `CONTRIBUTING.md`, per-directory READMEs.

## Current state (verify in PROJECT_STATUS before relying on this)
- Merged in `develop`: C1 TUM loader + FrameRecord, C2 dataset manifest, C3 GeometryPrediction/adapter protocol/intrinsics, C4 depth eval + timing + run.json contract.
- C5 DA3 adapter/runner (PR #4 merged into develop) and WP2 baseline/sparse export are combined on `yaropolk-wp1-wp2-integration`. `scripts/run_tum_da3_metric.py` is a thin CLI; historical GPU results remain unchanged. GPU evidence is Nazar's; CPU integration checks run locally on macOS.
- WP2 native setup/smoke/export is implemented: `src/rt_mapping/slam/`, `docs/WP2_SETUP.md`, `docs/WP2_SPARSE_EXPORT.md`. The new 200-frame run exported 1,205 landmarks / 19 keyframes / 7,595 observations. Full artifacts remain local/ignored; previews and summaries are versioned.
- Still incomplete: WP2 normalized all-frame states/timing and automated trajectory evaluation; WP1 broader selection/benchmark; alignment/fusion, end-to-end pipeline, CI, lint config. Do not claim only WP3 remains.
- `.gitignore` ignores any `models/` directory: never name a source package `models`.

## Environment (Windows, PowerShell, from repo root)
- Python 3.11 `.venv` via uv; do not use system Python 3.14. Setup commands: `docs/ENVIRONMENT.md`.
- `.venv\Scripts\python.exe scripts\check_wp1_environment.py`
- `.venv\Scripts\python.exe scripts\run_tum_da3_metric.py --frames 20 --warmup 1` (CUDA + cached checkpoint required, never downloads; writes a new `results/runs/<run_id>/`, refuses an existing one)
- Tests (CPU only): `.venv\Scripts\python.exe -m pytest tests -q`. No lint or format command exists yet.

## Rules
- Ground-truth depth/trajectory only in evaluation code or an explicitly labeled oracle (B1); never for tuning P1 on held-out data.
- Depth in metres; poses T_wc; quaternion order qx,qy,qz,qw; any resize/crop must update K_processed.
- Every run writes `results/runs/<run_id>/run.json`; never edit a finished run.json — new config = new run_id.
- Do not claim "real-time" without hardware, resolution, input FPS and p95 latency. Sim(3)-aligned ATE does not prove metric scale.
- Business logic goes in `src/rt_mapping/`; scripts stay thin CLIs. Generic modules must not import pySLAM or a specific model.
- Never commit `data/raw/`, `checkpoints/`, `results/runs/`, `.venv/`, large PLY/NPZ/video, or secrets. Only small JSON/CSV summaries go in `results/summaries/`.
- One PR = one verifiable change; branch names like `feature/<name>-<topic>`; update `docs/PROJECT_STATUS.md` with evidence.
- Record a contribution or "done" status only with evidence (commit/run/file). Unproven causes are labeled "гіпотеза".

## Ask before
- Committing, pushing, opening PRs, tagging, or force-pushing.
- Installing/upgrading packages or changing `.venv`.
- Downloading datasets or checkpoints.
- Changing baseline, dataset split, metrics, MVP scope, or another work package's area.
- Deleting or overwriting local runs, data, or checkpoints.
