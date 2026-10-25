# P1-robust extension plan: failure-aware, sparse-anchored dense fusion (one-day MVP)

- **Track:** Yulian (third, mostly independent track next to Track N — Nazar and Track Y — Yaropolk from `docs/TWO_PERSON_COMPLETION_PLAN.md`).
- **Planning base:** `origin/develop` = `d3071f1` (Merge PR #11), 2026-10-25.
- **Status:** plan only. Every file marked **(planned)** below does not exist yet on `origin/develop`.
- **Scope rule:** this extension does not replace, redesign or duplicate any N-track or Y-track chunk, and it does not enter the D-4/IC3 held-out freeze.

## 0. Summary of the plan

- Selected direction: **Failure-aware, sparse-anchored dense fusion (P1-robust)**, limited to a strict one-day MVP.
- Stretch only (after U-03 is verified): multi-view consistency, pixel masks, τ sweeps, fault-injection campaign, ROC-style plots, gallery, dev/held-out extension runs.
- Four chunks: U-01 diagnostics, U-02 anchoring + gate, U-03 real smoke comparison, U-04 figures, conclusions and integration.
- **No new thresholds.** Every threshold is an existing merged default, a contract value or a standard metric definition (§3.4). None is tuned on real ground truth (GT).
- GT-free signals and GT evaluation live in separate modules; an import test enforces this.
- P1-global control: bit-identical reproduction is expected; if that fails, an analytically justified float64 tolerance applies (§3.5).
- **Closing the P1→B1 gap is the hypothesis, not a completion requirement.** A correctly measured negative result counts as done.

## 1. Verified project state (at `origin/develop` = `d3071f1`)

Verification for this plan: `git fetch --all --prune`, `gh pr list --state all`, `gh run list`, and reading the merged code, docs, summaries and local run artifacts. No GPU, Docker or pySLAM run was performed for planning.

- PRs #1–#11 are merged; no PR was open at planning time. CI "CPU correctness" is green on `d3071f1` (run `40207421436`). PR #11 reports **496 passed, 1 skipped** on all four matrix legs.
- PR #10 (N-01): four frozen split manifests and `scripts/freeze_tum_split.py` are merged.
- PR #11 (Y-01, implemented by Yulian as WP2 assistance; owner Yaropolk): `slam/tracking_log.py`, `contracts/slam.py`, export of `trajectory_all.csv`, `timing.csv`, `tracking_export.json`. Evidence: `results/summaries/yaropolk_y01_tracking_smoke200_be9bff2.json`.
- Remaining active work: N-02…N-06 (Nazar), Y-02…Y-06 (Yaropolk).
- Local (ignored) inputs on Yulian's machine: fr1/xyz under `data/raw/tum_rgbd/`; run `yulian_tum_e2e_f200_20261025_01` (SLAM + DA3 + comparison, clean `4952e37`).

| Section | Implemented | Real-data evidence | Synthetic only | N/Y currently improving | Weak for mentors |
|---|---|---|---|---|---|
| Dense depth | DA3 adapter, `runs/geometry_run.py`, depth eval, C3 NPZ contract | DA3 fr1/xyz 200 frames: AbsRel 0.0927, δ1 0.965 (`results/summaries/wp1_da3metric_yulian_tum_fr1_xyz_200.json`) | — | N-03 UniDepth/selection, N-04 ablations, N-05 dev/sel | One model on one easy sequence. DA3 has no confidence output. Depth error is never linked to map error |
| SLAM | Runner, sparse export, Y-01 all-frame states/timing (PR #11) | Smoke: 198/200 poses, 0 LOST, 22 retained keyframes; Y-01 runs at `be9bff2` | — | Y-02 ATE/RPE + RSS, Y-03 tracking success, Y-04…06 splits | No failures appear on fr1/xyz. SLAM state is not linked to map quality |
| Alignment + fusion | Global robust scale, Sim(3), causal window, voxel fusion, B0/B1/P1 comparison | `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`: scale 1.192, withheld p95 residual 0.313 m. Chamfer: P1-global 0.0887, P1-raw 0.0876, B1 0.0329, B0 0.1377 m | `scripts/run_comparison_smoke.py` fixture | Used **unchanged** by N-04/N-05/N-06 | One global scale. Global scale hardly changes the map (P1-raw ≈ P1-global). The P1→B1 gap is dense-depth error, and nothing acts on the residual tail |

Main gap: no stage uses the SLAM sparse geometry to judge or correct dense depth per frame.

## 2. Motivation and selected extension

Mentor feedback asked for more of the working pipeline, properly compared baselines, failure analysis, conclusions and first improvement steps across all three sections (dense depth, SLAM, sparse-to-dense alignment/fusion).

Candidates evaluated (scores 1–5 for technical value, mentor/demo value, independence, one-day feasibility, evidence quality, implementation risk where 5 = lowest risk):

| Candidate | Total | Reason not chosen / chosen |
|---|---|---|
| **A — failure-aware sparse-anchored fusion (P1-robust)** | **27/30** | Chosen: failure analysis + improvement step + baseline comparison, CPU-only on existing artifacts, new files only |
| B — real-data P1-window study | 17 | Duplicates N-05 (pre-registered windows {60,150}) |
| C — incremental/online mapping | 17 | Too risky for one day; muddies the D-7 real-time story |
| D — results dashboard/demo | 20 | Duplicates F-N2/F-Y1 |
| E — diagnostics only | 25 | No improvement step (it is contained in A as U-01) |

The MVP covers all three sections:

1. Depth error is diagnosed per frame.
2. SLAM provides the anchors and, when available, the tracking state.
3. Alignment and fusion apply per-frame correction and a gate.
4. Map metrics measure the outcome against B0/B1.

## 3. MVP technical design

### 3.1 Inputs (read-only, existing local artifacts)

Root: `results/runs/yulian_tum_e2e_f200_20261025_01/stages/` (ignored, local).

- `…slam/`: sparse snapshot, loaded via `runs.artifacts.load_mapping_inputs`. There is no tracking export, because the run predates Y-01.
- `…geometry/`: predictions, plus `metrics.json` `per_frame` (GT-derived, evaluation only).
- `…comparison/`:
  - `run.json`, which holds the recorded mapping config;
  - `inputs.json`, with run.json sha256 provenance;
  - `methods/*.global/{alignment.json,residuals.csv,map.npz}`;
  - `trajectory_evaluation.json`, the shared SE(3) evaluation transform;
  - `reference_evaluation_only.npz`;
  - `evaluation/*.json`, with the B0/B1/P1-raw rows.
- Evaluation only: `data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz` and `data/manifests/tum_fr1_xyz.json`, read through `evaluation.oracle.load_oracle_inputs`.

### 3.2 Two strictly separated layers (GT-free vs evaluation)

| Layer | Module | May import | Must not import |
|---|---|---|---|
| GT-free runtime signals | `src/rt_mapping/alignment/frame_signals.py` (planned, U-01), `src/rt_mapping/alignment/anchoring.py` (planned, U-02) | `alignment.{estimators,correspondences}`, `fusion`, `contracts`, `runs.artifacts`, `slam.tracking_log` | `rt_mapping.evaluation.*`, `data.tum`, pySLAM, torch, model packages |
| GT-only evaluation | `src/rt_mapping/evaluation/frame_diagnostics.py` (planned, U-01), evaluation part of `src/rt_mapping/runs/robust_fusion_run.py` (planned, U-03) | anything above, plus `evaluation.{oracle,map_geometry,depth,trajectory}` | pySLAM, torch, model packages |

`tests/test_import_hygiene_robust.py` (planned) checks these import rules with an AST scan.

### 3.3 Algorithm

**Per-frame signals (U-01, GT-free).**

1. Rebuild the correspondence pairs with `build_correspondences`, using the recorded mapping config.
2. Rebuild the withheld landmark split exactly as `runs/mapping_run.py` does: `default_rng(seed).permutation(unique point_ids)`, with the first `ceil(n·validation_fraction)` withheld.
3. Check the rebuilt pairs and split against the recorded `residuals.csv`: `frame_id`, `point_id` and `withheld` must match exactly. Any mismatch stops the chunk.
4. Read the global scale `s` from `alignment.json`.
5. Record per keyframe:
   - pair counts (all, calibration, withheld);
   - frame inlier ratio and median |residual| under `s`;
   - withheld median |residual| under `s`;
   - calibration inlier coverage in 4×4 bins (`Correspondences.coverage_bins`);
   - predicted-depth median and p95;
   - tracking state, or null with a reason.
6. **Anchor ratio `a_f`:** the merged robust estimator applied per frame in the inverse direction, using calibration pairs only:
   `estimate_scale(source=z_pred, target=s·z_slam, threshold_m=0.10, min_inliers=30, min_ratio=0.5)`.
   If it raises `AlignmentError`, record `a_f = null` and the estimator's reason.

**Per-frame anchoring (U-02, GT-free).**

- Corrected depth: `z'_f = a_f · z_pred`.
- Applied to an in-memory copy of the prediction. Input files are never written.
- Frames with `a_f = null` stay uncorrected and are flagged.
- GT-free validation: withheld median |residual| per frame before and after correction. Reported, not used for tuning.
- SLAM poses keep the unchanged global scale `s`, so P1-global remains a clean control.

**Frame gate (U-02, GT-free, pre-registered).** A frame is rejected if any flag fires:

| Flag | Rule |
|---|---|
| A1 | `a_f` is null: fewer than 30 calibration inliers, or the inlier ratio fails |
| A2 | \|log a_f\| > log 1.25 |
| A3 | withheld median \|residual\| > 0.10 m (checked only when the frame has at least one withheld pair, as in `alignment/causal.py`) |
| A4 | calibration-inlier coverage < 4 of 16 bins |
| S1 | tracking state ≠ OK, when the state is known; otherwise the flag is "unavailable" |

Gate decisions are written and committed in U-02 **before** any GT is opened in U-03.

**Variants (U-03).**

- **P1-global control:** produced by the unchanged public `run_mapping` with the recorded mapping config (only `plot` may differ).
- **P1-anchored:** every frame corrected where `a_f` exists.
- **P1-anchored+gate:** corrected frames, with rejected frames left out of fusion.
- **Reference rows:** B0-shared-scale, B1-oracle and P1-raw from the recorded comparison, after checking that the evaluation transform is identical.

All variants are evaluated with the unchanged `evaluate_map`: same voxel size, τ = {0.02, 0.05, 0.10} m, crop, shared transform and reference.

### 3.4 Thresholds and their justification (none tuned on GT)

| Threshold | Value | Source |
|---|---|---|
| Residual threshold | 0.10 m | Merged `mapping_run.DEFAULT_CONFIG["residual_threshold_m"]` (the global gate) |
| Minimum anchors | 30 | Merged `min_inliers` |
| Minimum inlier ratio | 0.5 | Merged `min_inlier_ratio` |
| Minimum coverage | 4/16 bins | Merged `min_coverage_bins` |
| Withheld evaluable | ≥ 1 pair | Same rule as merged `alignment/causal.py` (`check.any()`) |
| Anchor band | \|log a_f\| ≤ log 1.25 | The δ1 accuracy band of the project depth metric (EXPERIMENTS §4.2). A frame whose depth disagrees with the SLAM anchors by more than the accepted-accuracy band is unreliable |
| Tracking | state == OK | Y-01 contract (`contracts/slam.py`) |
| Map τ, voxel size | {2, 5, 10} cm, 0.02 m | Merged comparison defaults (D-4) |

Synthetic tests check each rule on known inputs (KNOWN_SCALE 2.5, injected scale bias, too few anchors). Thresholds are never changed after the real U-03 metrics are seen.

### 3.5 P1-global reproduction check

1. **Primary:** the control `map.npz` is byte-identical to the recorded `methods/*.global/map.npz` (`np.array_equal` on `xyz_m` and `observation_count`). The same code runs on the same inputs, seed and machine, so the output is deterministic.
2. **If not byte-identical:** voxel key sets and observation counts must still be identical. Per-voxel centroid differences must stay within the float64 summation error bound `|Δ| ≤ γ_n · max|x|`, where `γ_n = n·2⁻⁵³/(1 − n·2⁻⁵³)` and `n` is that voxel's observation count. This covers a numpy/BLAS summation-order difference. Record both numpy versions and the maximum observed |Δ|.
3. **Anything else** (different voxel keys or counts, or the bound exceeded) is a defect: stop.

The control's evaluated metrics must then equal the recorded P1-global row within the same tolerance.

### 3.6 Metrics

- **Map:** accuracy, completeness and Chamfer-L1 (means and medians), plus F, precision and recall at 2, 5 and 10 cm.
- **Retention:** frames and points kept vs rejected, per variant.
- **Per-frame depth (GT, evaluation only):** AbsRel, RMSE and δ1 before and after anchoring, and per-keyframe map-contribution accuracy.
- **Signal vs error:** Spearman ρ between each GT-free signal and per-frame GT error. With n = 22 this is descriptive only; no significance claim.
- **CPU overhead:** p50/p95 ms per keyframe for signals, anchoring and fusion, compared with the control's fusion timing. Labelled "CPU artifact processing only; excludes SLAM and model inference; not real-time".

### 3.7 Failure categories

Causes are labelled "гіпотеза" unless shown.

| Section | Code | Failure |
|---|---|---|
| Depth | D1 | per-frame metric-scale error (measured `a_f`) |
| Depth | D2 | local depth artifacts (residual spread with a nominal `a_f`) |
| SLAM | S1 | tracking not OK (only when telemetry exists) |
| Alignment | A1–A4 | the flags above |
| Map | M1 | completeness loss from rejected frames |
| Map | M2 | ghosting from frames that disagree |

### 3.8 Stopping conditions and honesty rules

- Stop if provenance or the `residuals.csv` cross-check fails.
- Stop if the control check in §3.5 fails.
- Stop if any frozen file would need editing.
- Stop if Phase A would need GT.
- No retuning after GT is seen. Negative results, failed variants and an over-aggressive gate are all reported as found.
- No real-time claim.

## 4. Experiment configuration (pre-registered)

`configs/robust_fusion.json` (planned) is created in U-02 and frozen once U-02 merges. It holds:

- every value in §3.4;
- the variant list: control, anchored, anchored+gate;
- the input artifact contract.

U-03 refuses to run if the config's sha256 differs from the hash recorded in the U-02 summary.

## 5. File ownership and independence

All files in the "Yulian may create" rows are **planned**.

| Category | Exact files |
|---|---|
| **Yulian may create: U-01** | `src/rt_mapping/alignment/frame_signals.py`, `src/rt_mapping/evaluation/frame_diagnostics.py`, `scripts/run_frame_diagnostics.py`, `tests/test_frame_diagnostics.py`, `tests/test_import_hygiene_robust.py`, `docs/ROBUST_FUSION.md`, `results/summaries/yulian_u01_diag_smoke200_<sha7>.{json,csv}`, `results/plots/yulian_u01_{timeline,signal_vs_error}.png` |
| **Yulian may create: U-02** | `src/rt_mapping/alignment/anchoring.py`, `configs/robust_fusion.json`, `scripts/run_anchor_gate.py`, `tests/test_anchoring.py`; extend `tests/test_import_hygiene_robust.py` and `docs/ROBUST_FUSION.md`; `results/summaries/yulian_u02_anchor_gate_smoke200_<sha7>.{json,csv}` |
| **Yulian may create: U-03** | `src/rt_mapping/runs/robust_fusion_run.py`, `scripts/run_robust_fusion.py`, `tests/test_robust_fusion_run.py`, `docs/ROBUST_FUSION.md`, `results/summaries/yulian_u03_robust_smoke200_<sha7>.{json,csv}`, `results/plots/yulian_u03_comparison.png` |
| **Yulian may create: U-04** | `scripts/render_robust_fusion_figures.py`, `docs/ROBUST_FUSION.md`, `results/plots/yulian_u04_{pointcloud_before_after,failure_cases}.png` |
| **Yulian's merged files: frozen, import only** | `alignment/{estimators,correspondences,causal}.py`, `fusion/voxel.py`, `runs/{mapping_run,comparison_run,pipeline_run,artifacts,synthetic_mapping}.py`, `evaluation/{map_geometry,trajectory,oracle,synthetic_scene}.py`, `geometry/projection.py`, `configs/{mapping_comparison,offline_mapping,pipeline.tum.example,pipeline.tum.windows-docker}.json`, existing tests. Reason: N-04/N-05/N-06 and the IC3 freeze rely on these being bit-stable |
| **Reserved for Nazar** | `data/**`, `src/rt_mapping/data/**`, `adapters/**`, `geometry/{adapter,intrinsics}.py`, `runs/geometry_run.py`, `evaluation/{depth,tum_depth,model_selection,prediction_grid,geometry_verification,confidence_ablation}.py`, `contracts/{frame,geometry,run_manifest,_validation}.py`, `evaluation/timing.py`, `scripts/{build_tum_manifest,freeze_tum_split,run_tum_da3_metric,check_wp1_environment,run_da3_metric_smoke,run_geometry_benchmark,compare_geometry_models,verify_geometry_run,analyze_confidence,render_demo}.py`, `requirements/wp1-*`, `configs/{pipeline.nazar.*,mapping_comparison.nazar.*,benchmark_frozen,model_assets,selected_geometry}.json`, `docs/{DATASET_FREEZE,UNIDEPTH,SELECTION_PROTOCOL,WP1_HANDOFF,DEPTH_ABLATIONS,NAZAR_REPRODUCTION,DEVELOPMENT_BENCHMARK,HELDOUT_BENCHMARK,BENCHMARK_PROTOCOL,DEMO,EXPERIMENTS,MODEL_SELECTION,ENVIRONMENT}.md`, `docs/decisions/**`, `results/{summaries,plots}/nazar_*`, `wp1_*` (several of these are themselves planned by the N track) |
| **Reserved for Yaropolk** | `src/rt_mapping/slam/**`, `contracts/slam.py`, `evaluation/slam_run.py`, `scripts/{run_wp2_pyslam,prepare_wp2_baseline,check_wp2_environment,build_wp2_native,build_wp2_linux_native,visualize_wp2_trajectory,evaluate_wp2_run,measure_wp2_resources}.py`, `configs/wp2_*.json`, `containers/**`, `requirements/wp2-*`, `docs/{WP2_SETUP,WP2_SPARSE_EXPORT,WP2_LINUX_CONTAINER,WP2_TRACKING_EXPORT,WP2_EVALUATION,WP2_BENCHMARK,ARCHITECTURE,INTERIM_REVIEW,CONTRIBUTIONS,PRESENTATION_OUTLINE,SUBMISSION_AUDIT}.md`, `tests/test_{slam_*,wp2_*,pyslam_sparse_native,import_hygiene_wp2}.py`, `results/{summaries,plots}/yaropolk_*` (several of these are themselves planned by the Y track) |
| **Shared, read-only for everyone** | `README.md`, `CLAUDE.md`, `PLAN.md`, `CONTRIBUTING.md`, `pyproject.toml`, `.gitignore`, `.github/workflows/**`, `tests/test_import_hygiene.py`, `tests/conftest.py`, `docs/{TWO_PERSON_COMPLETION_PLAN,PROJECT_BRIEF,YULIAN_HANDOFF,WP3_WP4_COMPLETION}.md`, this file after merge, all historical `results/summaries/*` and `results/plots/*` |
| **Delayed to final integration** | Status rows in `docs/{PROJECT_STATUS,INTEGRATION_STATUS}.md` (Nazar at the next IC or F-N1, copied verbatim from the U PR bodies); a pointer in `docs/EXPERIMENTS.md` and `README.md` (Nazar, F-N1); the extension slide and contribution rows (Yaropolk, F-Y1); dev-split robust runs (§7) |
| **Read-only interfaces used now** | `load_mapping_inputs`, `build_correspondences`, `Correspondences.coverage_bins`, `prediction_grid`, `estimate_scale`, `AlignmentError`, `run_mapping`, `metric_pose`, `depth_points`, `VoxelFusion`, `write_ply`, `evaluate_map`, `load_oracle_inputs`, `evaluate_depth`, `summarize_timings` (read-only use of a Nazar file), `read_tracking_log` (merged in PR #11), `build_run_manifest`/`write_run_manifest`/`load_run_manifest`, `collect_git_state`, `create_synthetic_inputs`, `create_synthetic_reference`, `run_comparison` |

U-01 through U-04 need nothing unmerged from Nazar or Yaropolk. The extension stays out of the D-4/IC3 held-out freeze and never touches fr3.

## 6. Chunk plan

Rules common to every chunk:

- Read `CLAUDE.md`.
- Run `git fetch`, `gh pr list` and `gh run list`, and report the `origin/develop` SHA.
- Create a new worktree from that exact `origin/develop` and work only on allowed files.
- Use the main checkout's `.venv` and existing ignored runs, read-only, passed as explicit paths.
- Create a new `run_id` from a clean commit. Never overwrite a finished run.
- Self-merge with a merge commit only after the required CI is green and `gh pr diff --name-only` lists only allowed files.
- Request a non-blocking review from Nazar (and from Yaropolk wherever tracking semantics are touched).
- Put a status row in the PR body. Never edit status docs.
- No installs, downloads, GPU, Docker or pySLAM runs in U-01…U-04.

### U-01: Frame diagnostics and failure-analysis foundation

| Item | Detail |
|---|---|
| Objective | GT-free per-keyframe signals, then a GT-only evaluation join (depth error, map contribution) and a failure table, on the historical smoke run |
| Prerequisites | `origin/develop` ≥ `d3071f1`; local `yulian_tum_e2e_f200_20261025_01`; fr1/xyz data |
| Branch | `feature/yulian-frame-diagnostics` |
| Allowed | The U-01 row in §5 |
| Forbidden | Everything else, especially the frozen, N, Y and shared files |
| Steps | (1) `frame_signals.py`: provenance check, rebuilt pairs and split, `residuals.csv` cross-check, per-frame signals including `a_f` via `estimate_scale`, flags A1–A4 and S1 (computed and reported here, not acted on). (2) Tracking: read `trajectory_all.csv` via `read_tracking_log` only if the SLAM `run.json` lists the tracking export; otherwise null with reason "source SLAM run predates Y-01 tracking export (be9bff2)". (3) Write `frame_signals.csv`, `signals.json` and `run.json` **before** Phase B. (4) `frame_diagnostics.py`: per-frame AbsRel/RMSE/δ1 from the geometry `metrics.json` (cross-check one frame with `evaluate_depth` against oracle GT); per-keyframe map-contribution accuracy (that frame's `depth_points` under `metric_pose(T_wc, s)` and the recorded evaluation transform, then cKDTree distance to the reference: mean, median, p90); Spearman ρ; failure table. (5) CLI plus two plots |
| Tests | Synthetic comparison fixture: `a_f` matches the known consistent value on clean frames; the 1.7× patch raises the median residual of the affected frame; ordering (monkeypatched `load_oracle_inputs` asserts that `frame_signals.csv` already exists); missing tracking export gives null + reason; provenance mismatch is refused with no run directory created; a `residuals.csv` mismatch is refused; the data files of a second run are byte-identical; Spearman with ties checked against a hand example; import hygiene; full suite |
| Real evidence | `yulian_u01_diag_smoke200_<sha7>_01`: status ok, `dirty_worktree=false`, 22 rows |
| Acceptance | 22/22 rows with explicit nulls and reasons; GT-free phase before any GT read (tested); correlations and failure table present; two plots inspected; CI green; diff limited to allowed files |
| Duration | 2.5–3 h |
| Outputs | Run directory (ignored); summary JSON/CSV; `yulian_u01_timeline.png`, `yulian_u01_signal_vs_error.png`; `docs/ROBUST_FUSION.md` §1–2 |
| Stop | Provenance or cross-check failure; a frozen-file edit needed; GT needed in Phase A |
| PR | Own PR to `develop`, self-merge after green checks |
| Independent | Yes |

### U-02: Sparse per-frame anchoring and frame gate

| Item | Detail |
|---|---|
| Objective | GT-free correction plus gate decisions, recorded and committed before any GT comparison |
| Prerequisites | U-01 merged |
| Branch | `feature/yulian-anchor-gate` |
| Allowed | The U-02 row in §5 |
| Forbidden | U-01's committed summaries and plots, frozen files, N/Y/shared files |
| Steps | (1) `anchoring.py`: `anchored_prediction(prediction, a_f)` returns a copy (`dataclasses.replace` or the contract constructor), with `valid_mask` and K unchanged; `gate_decision(signals, config)` returns accept or reject plus the list of flags. (2) `configs/robust_fusion.json`, with §3.4 values and their source citations. (3) `run_anchor_gate.py`: reuses `frame_signals`, writes per-frame `a_f`, decision, flags, and withheld residual before and after anchoring, plus the config sha256. **No GT imports.** (4) Docs §3 |
| Tests | A known per-frame bias (×1.2 on one synthetic frame) is recovered and flagged correctly; each flag fires on a constructed case and the gate rejects; null `a_f` leaves the frame uncorrected; the input prediction object and file are unchanged; an unknown config key is rejected; hygiene test (no `rt_mapping.evaluation` imports); full suite |
| Real evidence | `yulian_u02_anchor_gate_smoke200_<sha7>_01` (GT-free) |
| Acceptance | Decisions for 22/22 frames; withheld before/after table; config hash recorded in the committed summary; CI green |
| Duration | 2–2.5 h |
| Outputs | Summary JSON/CSV with the frozen decisions; config file |
| Stop | Any GT access needed; a frozen-file edit needed; the gate rejects every frame (record it, merge the evidence, and U-03 reports the gated variant as failed with a reason) |
| PR | Own PR, self-merge |
| Independent | Yes |

### U-03: Real smoke experiment and baseline comparison

| Item | Detail |
|---|---|
| Objective | Control reproduction, then P1-anchored and P1-anchored+gate maps, then GT evaluation against the B0/B1/P1-raw rows |
| Prerequisites | U-02 merged; the config hash matches the U-02 summary |
| Branch | `feature/yulian-robust-smoke` |
| Allowed | The U-03 row in §5 |
| Forbidden | `configs/robust_fusion.json` (frozen), earlier U summaries, frozen/N/Y/shared files |
| Steps | (1) **Phase A, no GT:** run the control with `run_mapping` into `<run>/methods/`; perform the §3.5 check; fuse the two variants with the U-02 decisions recomputed and asserted equal to the committed ones; record timing; write maps and `run.json`. (2) **Phase B, evaluation:** `evaluate_map` for every variant with the recorded reference and transform; the control's row must equal the recorded P1-global row; copy and verify the B0/B1/P1-raw rows; per-frame AbsRel before and after anchoring; retained/rejected frames and points; CPU overhead. (3) Comparison CSV/JSON, `yulian_u03_comparison.png`, docs §4 with the measured result, whatever its sign |
| Tests | Fixture: the control equals `run_comparison`'s global map byte-for-byte; anchoring removes an injected per-frame bias and improves fixture accuracy; the gated variant drops exactly the flagged frames; GT is read only after the maps exist (ordering test); a config hash mismatch is refused; full suite |
| Real evidence | `yulian_u03_robust_smoke200_<sha7>_01`, clean |
| Acceptance | Control reproduced (byte-identical, or within the justified bound with the evidence recorded); every variant ok or failed with a reason; full table with all metrics; tradeoff and any negative result stated plainly; no real-time wording |
| Duration | 2–2.5 h |
| Outputs | Summary, comparison plot, docs section |
| Stop | Control mismatch beyond §3.5; any post-GT parameter change requested |
| PR | Own PR, self-merge |
| Independent | Yes (needs only U-01 and U-02) |

### U-04: Figures, conclusions and integration handoff

| Item | Detail |
|---|---|
| Objective | The final small evidence set, conclusions, limitations, and integration instructions for Nazar and Yaropolk |
| Prerequisites | U-03 merged |
| Branch | `feature/yulian-robust-evidence` |
| Allowed | The U-04 row in §5 |
| Forbidden | `scripts/render_demo.py` (F-N2, planned by Nazar), presentation and status docs, everything else |
| Steps | (1) Before/after point cloud: P1-global vs P1-anchored+gate on the same axes and view, coloured by evaluation-only distance to the reference, labelled "offline". (2) At most three failure cases: the worst map-contribution keyframes, each showing RGB, predicted depth, GT absolute error, flags and `a_f`. (3) Docs §5–7: conclusions per section, limitations, the exact §7 integration commands, the stretch list. (4) The status row and copy-ready slide numbers in the PR body |
| Tests | The render script runs on the synthetic fixture (smoke test); total plot size < 1 MB; full suite |
| Real evidence | Figures rendered from the U-01/U-03 runs, with source run IDs recorded in the docs |
| Acceptance | Five presentation artifacts exist (timeline, signal vs error, comparison, point cloud, failure cases); every number traced to a run ID; limitations complete |
| Duration | 1.5–2 h |
| Outputs | Two plots; final docs sections |
| Stop | A figure would need GT in a non-evaluation label; size limit exceeded |
| PR | Own PR, self-merge |
| Independent | Yes |

**Total:** about 8.5–10 hours, sequential, done by Yulian alone.

### Stretch sub-chunks (only after U-03 is verified)

| Sub-chunk | Content | Needs |
|---|---|---|
| U-S1 | Multi-view consistency mask (pixel level), single τ = 0.05 | CPU |
| U-S2 | Small fault-injection run: depth scale ×0.8/×1.25 on 3 frames, seeds 0–2; gate detection rate | CPU |
| U-S3 | Fresh joined pipeline run at `develop` ≥ PR #11 using the unchanged `configs/pipeline.tum.windows-docker.json`, so S1 is live; rerun U-01…U-03 | Yulian's GPU + Docker; separate prompt and authorization |
| U-S4 | τ sweep, ROC-style plots, larger gallery | CPU |

## 7. Later three-person integration

These start after each person finishes their current track. None of their present assignments change.

| Person | Contribution | Inputs | Output |
|---|---|---|---|
| **Nazar: dense depth** | Run `run_frame_diagnostics.py`, `run_anchor_gate.py` and `run_robust_fusion.py` (planned) with the **unchanged** committed `configs/robust_fusion.json` on his own N-05 dev573 and sel50 runs, for both DA3 and UniDepth. Development data only, never held-out. These runs are made at `develop` ≥ PR #11, so tracking export and S1 are live. Optional: compare the gate with UniDepth's native confidence | His own ignored N-05 runs | `feature/nazar-robust-fusion-dev`: `results/summaries/nazar_u05_*`, `docs/ROBUST_FUSION_DEVELOPMENT.md` (planned) |
| **Yaropolk: SLAM** | (1) Independent CPU reproduction of U-01…U-03 on the synthetic fixture from a fresh clone. (2) Review the S1 join semantics against his Y-03 definitions (state names, denominators, initialization frames). (3) The S rows of the final failure table, from his committed Y-03/Y-05 summaries. (4) The extension slide inside his existing F-Y1 | Committed summaries; synthetic fixture | `feature/yaropolk-robust-fusion-review`: `results/summaries/yaropolk_u05_review.json` (planned); F-Y1 slide |
| **Yulian: alignment and fusion** | Aggregate Nazar's and Yaropolk's committed summaries into the final cross-split table and failure table; give Nazar the status rows (IC/F-N1) and Yaropolk the slide figures | Committed summaries only | `feature/yulian-robust-fusion-final`: final section of `docs/ROBUST_FUSION.md`, `results/summaries/yulian_u05_final.{json,csv}` (planned) |

Nobody reads another person's ignored runs; everything is exchanged through committed summaries.

## 8. Presentation evidence

| Artifact | Dense depth | SLAM | Alignment / fusion | Chunk |
|---|---|---|---|---|
| Comparison table: control / anchored / anchored+gate / B0 / B1 / P1-raw, with accuracy, completeness, Chamfer, F at 2/5/10 cm, frames and points kept, CPU ms | B1 shows the depth-error bound | B0 sparse row | Main result | U-03 |
| Per-frame AbsRel before/after anchoring | ✔ | — | Correction effect | U-03 |
| Failure timeline: `a_f`, inlier ratio, withheld residual, AbsRel, map-contribution accuracy, gate decisions, tracking state | ✔ | Tracking state (or "unavailable") | ✔ | U-01 (+ U-02 decisions) |
| Signal-vs-error plot and Spearman table | GT error axis | Anchor counts come from SLAM | GT-free signals | U-01 |
| Baseline / anchored / gated comparison plot | — | B0 bar | ✔ | U-03 |
| Before/after point cloud | Raw depth errors visible | Same metric poses | Fused result | U-04 |
| Failure-case table (≤ 3 cases): RGB, depth, GT error, flags | D1/D2 | S1 if known | A1–A4, M1/M2 | U-01 table, U-04 figure |
| Conclusions and limitations | ✔ | ✔ | ✔ | U-04 |
| Dev-split rows (expected result) | DA3 vs UniDepth | Live S1 | ✔ | §7 |

Limitations always stated:

- one easy sequence with 22 keyframes;
- final-snapshot anchors make the method offline and non-causal;
- the GT reference is an approximation;
- n = 22 correlations are descriptive only;
- no real-time claim;
- the extension is not part of the held-out freeze.

## 9. Fallback results

| Situation | What is still presented |
|---|---|
| Anchoring does not improve Chamfer | A measured negative result plus a mechanism: per-frame AbsRel before/after, withheld residuals before/after, and whether `a_f` deviations are small (DA3 per-frame scale already consistent on fr1/xyz, so error is local, D2) or large and wrongly signed. Conclusion: per-frame scale is not the bottleneck, which points to pixel-level filtering (U-S1) as the next step |
| The gate loses too much completeness | The accuracy-vs-completeness tradeoff with exact frames and points lost and which flag dominated. Because thresholds are pre-registered, there is no retuning; this is reported as a finding about those thresholds, with a dev-split check proposed |
| Tracking telemetry unavailable for the historical run | S1 shown as "unavailable: run predates Y-01 (be9bff2)"; the gate runs on A1–A4 only. S1 goes live in §7 dev runs or U-S3 |
| U-03 cannot complete | U-01 diagnostics (failure timeline, signal-vs-error, failure table) plus U-02 frozen GT-free decisions and withheld-residual before/after evidence, with the blocker disclosed. That is still failure analysis across all three sections plus a pre-registered improvement step |

Drop order if time runs short:

1. U-04 failure-case figure (keep the table);
2. point-cloud figure (keep the comparison plot);
3. per-frame AbsRel before/after;
4. never drop the control check, the GT separation or the honest reporting.

## 10. Final recommendation

- **Extension:** Failure-aware, sparse-anchored dense fusion (P1-robust), one-day MVP.
- **Question (hypothesis, not a requirement):** can GT-free per-frame signals from the SLAM sparse map detect and correct or reject unreliable dense-depth frames, and so reduce the P1-global map error? Accuracy is 0.092 m vs B1's 0.032 m, at a completeness cost that is reported honestly.
- **Why it fits one day:** CPU only; existing local artifacts; about five small new files; every merged interface reused unchanged; no new thresholds or dependencies; no unmerged N/Y work.
- **Start first:** U-01.
- **Waits for Nazar:** dev573/sel50 DA3 and UniDepth runs (N-05) for the cross-split confirmation.
- **Waits for Yaropolk:** Y-03/Y-05 tracking semantics and summaries for the S1 review and failure rows, plus the F-Y1 slide.
- **Expected gain for the project:** linked depth → SLAM → alignment → map failure analysis, the first concrete pre-registered improvement step with a controlled baseline comparison, and visual before/after evidence.
- **Major risks:** small or no gain on easy fr1/xyz (mitigated by honest reporting and dev runs); anchors are offline and non-causal; n = 22 is small; the historical run has no S1 telemetry.

---

## 11. U-01 execution prompt

`<main>` denotes the main checkout of the repository on the executor's machine.

```text
Chunk U-01 (Yulian extension track "P1-robust", WP3/WP4 owner): per-keyframe frame diagnostics and failure-analysis
foundation. Do NOT start U-02 or any later chunk.

STANDARD RULES
- Read CLAUDE.md first. Run: git fetch --all --prune; gh pr list --state all --limit 30; gh run list --limit 5. Report
  the exact origin/develop SHA (expected d3071f1 or newer).
- Create a new worktree from that exact SHA:
  git worktree add --no-track -b feature/yulian-frame-diagnostics ../ai-rtm-u01 <origin/develop SHA>
  Never use local main. Preserve every other worktree, branch, stash, ignored run and uncommitted file.
- Use the main checkout's .venv (Python 3.11) by absolute path. No installs, upgrades, downloads, GPU, Docker or pySLAM.
- Existing artifacts are READ-ONLY inputs, passed as explicit CLI paths (main checkout):
  results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.slam
  results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.geometry
  results/runs/yulian_tum_e2e_f200_20261025_01/stages/yulian_tum_e2e_f200_20261025_01.comparison
  data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz ; data/manifests/tum_fr1_xyz.json
  Write the new run under the main checkout's results/runs/. Never overwrite any run; refuse an existing run dir.
- Ground truth only in evaluation code, strictly after the GT-free phase is written. No held-out data. No real-time claims.
- Authorized: commit (configured identity), push this branch, open ONE PR to develop, wait for required checks, and merge
  with a merge commit ONLY if all required checks are green AND `gh pr diff --name-only` lists only allowed files; then
  fast-forward local develop. Request a non-blocking review from Nazar and from Yaropolk (tracking-state join).
  Not authorized: tagging, force-push, editing other PRs or branches.

ALLOWED FILES (create only these)
  src/rt_mapping/alignment/frame_signals.py        (GT-free runtime signals)
  src/rt_mapping/evaluation/frame_diagnostics.py   (GT-only evaluation join)
  scripts/run_frame_diagnostics.py                 (thin CLI)
  tests/test_frame_diagnostics.py
  tests/test_import_hygiene_robust.py
  docs/ROBUST_FUSION.md                            (Ukrainian; sections 1-2 only)
  results/summaries/yulian_u01_diag_smoke200_<sha7>.json
  results/summaries/yulian_u01_diag_smoke200_<sha7>.csv
  results/plots/yulian_u01_timeline.png
  results/plots/yulian_u01_signal_vs_error.png    (both plots < 600 KB total)
FORBIDDEN: every existing file. In particular alignment/{estimators,correspondences,causal}.py, fusion/*, runs/*,
evaluation/{map_geometry,trajectory,oracle,depth,tum_depth,timing,synthetic_scene}.py, contracts/*, slam/*, data/*,
configs/*, adapters/*, geometry/*, existing scripts/tests (incl. tests/test_import_hygiene.py, conftest.py), README,
CLAUDE, PLAN, all docs except the new ROBUST_FUSION.md, historical results. Reuse by import only. If a defect in a
frozen file blocks you: stop, do not fix it here, report it.

DESIGN (thresholds are pre-registered merged defaults; never tune them on GT)
Module separation (enforced by tests/test_import_hygiene_robust.py via AST): frame_signals.py must not import
rt_mapping.evaluation.*, rt_mapping.data.tum, pyslam, torch, depth_anything_3, unidepth. frame_diagnostics.py must not
import pyslam, torch, depth_anything_3, unidepth.

Phase A — GT-free (frame_signals.py)
1. Provenance: load the comparison run.json (status ok), its inputs.json "pipeline" provenance, and verify sha256 of the
   slam and geometry run.json files match; verify methods/*.global/run.json status ok. Load inputs via
   rt_mapping.runs.artifacts.load_mapping_inputs(slam, geometry). Take the mapping config from the comparison run.json
   config["mapping"] and the global scale s from methods/*.global/alignment.json. Refuse (no run dir) on any mismatch.
2. Rebuild pairs with rt_mapping.alignment.correspondences.build_correspondences using that mapping config. Rebuild the
   withheld landmark split exactly as runs/mapping_run.py does (np.random.default_rng(seed).permutation(np.unique(
   point_id)); first ceil(n*validation_fraction) withheld). Cross-check against the recorded residuals.csv: frame_id,
   point_id and withheld columns must match exactly (same order); otherwise stop.
3. Per retained keyframe (ordered by timestamp) compute: frame_id, timestamp_s, n_pairs, n_calibration_pairs,
   n_withheld_pairs, frame_inlier_ratio and median_abs_residual_m under s (residual = |s*z_slam - z_pred|, inlier <=
   residual_threshold_m), withheld_median_abs_residual_m (null+reason if no withheld pair), calibration-inlier
   coverage_bins_4x4 (Correspondences.coverage_bins), predicted depth median/p95 over valid pixels in
   [min_depth_m, max_depth_m], and the anchor ratio a_f = estimate_scale(source=z_pred[cal_f], target=s*z_slam[cal_f],
   threshold_m=residual_threshold_m, min_inliers=min_inliers, min_ratio=min_inlier_ratio).scale using calibration
   (non-withheld) pairs of that frame only; on AlignmentError record a_f=null and the estimator reason.
4. Tracking: if the SLAM run.json lists the Y-01 tracking export artifact (check the key written by
   src/rt_mapping/slam/smoke.py), read it with rt_mapping.slam.tracking_log.read_tracking_log and record the keyframe's
   state; otherwise tracking_state=null, reason "source SLAM run predates Y-01 tracking export (be9bff2)".
5. Flags (computed and reported only; no gating in U-01), all from merged defaults or contracts:
   A1 a_f null (fewer than min_inliers=30 anchors or inlier ratio < 0.5);
   A2 |log a_f| > log(1.25)  (delta1 accuracy band of the project depth metric);
   A3 withheld median > residual_threshold_m=0.10 (only if >=1 withheld pair, as in alignment/causal.py);
   A4 coverage_bins_4x4 < min_coverage_bins=4;
   S1 tracking_state known and != OK.
   Cite each source in the docs table.
6. Write frame_signals.csv, signals.json and run.json (build_run_manifest: method "P1-global", alignment copied from the
   source global run's alignment method/thresholds, config.control_label "per-keyframe diagnostics; no new map",
   source run IDs and sha256s) BEFORE Phase B starts.

Phase B — evaluation only (frame_diagnostics.py; label every output field/file "evaluation_only")
7. Per-keyframe AbsRel/RMSE/delta1 from the geometry run's metrics.json per_frame. Cross-check one keyframe by recomputing
   with rt_mapping.evaluation.depth.evaluate_depth on GT depth from rt_mapping.evaluation.oracle.load_oracle_inputs
   (same mapping config); record the absolute difference.
8. Per-keyframe map contribution: depth_points(prediction, metric_pose(T_wc, s), distortion per prediction_grid,
   same depth range/stride/confidence settings), transformed by trajectory_evaluation.json P1_global_se3
   evaluation_transform, nearest-neighbour distance (scipy cKDTree) to reference_evaluation_only.npz -> mean/median/p90.
9. Spearman rho (numpy average-rank implementation) between each GT-free signal (|log a_f|, 1-frame_inlier_ratio,
   median_abs_residual_m, withheld_median_abs_residual_m, predicted median depth) and per-keyframe AbsRel and
   map-contribution mean accuracy; report n and nulls excluded; descriptive only, no significance claims (n=22).
10. failure_table.csv: keyframes ranked by map-contribution mean accuracy with flags, a_f, AbsRel and a category
    (D1 per-frame scale / D2 local depth / A1-A4 / S1 / unknown); causes labelled "гіпотеза" unless shown.
11. Plots (Agg): yulian_u01_timeline.png (per keyframe: a_f, frame_inlier_ratio, withheld residual, AbsRel,
    map-contribution accuracy, flag markers, tracking state or "unavailable"); yulian_u01_signal_vs_error.png (the
    highest-|rho| GT-free signal vs map-contribution accuracy, annotated with rho and n).
Deterministic outputs: sorted keys, LF, fixed float formatting (repr-precision or 17 significant digits).

CLI: scripts/run_frame_diagnostics.py --comparison-run --slam-run --geometry-run --sequence-dir --manifest --run-id
[--output-root] [--plot]; validate run_id like scripts/run_comparison_smoke.py; thin wrapper only.

TESTS (CPU only)
Build a complete synthetic comparison run in tmp_path with create_synthetic_inputs(non_collinear=True) +
create_synthetic_reference + run_comparison (as scripts/run_comparison_smoke.py does). Assert:
- a_f on the synthetic frames is consistent with the recorded scale (a_f ~= 1 when depth and s*z_slam agree) within a
  tolerance justified in the test docstring by float32 prediction precision;
- the frame containing the injected 1.7x depth patch has a higher median_abs_residual_m than clean frames;
- ordering: monkeypatch load_oracle_inputs to assert frame_signals.csv and run.json already exist when it is called;
- missing tracking export -> tracking_state null + exact reason; S1 not raised;
- provenance sha256 mismatch and residuals.csv mismatch -> refusal and no run dir created;
- rerun into a second run_id produces byte-identical frame_signals.csv / frame_evaluation.csv / correlations.json;
- spearman helper matches a hand-computed example with ties;
- import hygiene for both modules.
Then full suite: <main>\.venv\Scripts\python.exe -m pytest tests -q (expect >= 496 passed + new tests, 1 skipped).

REAL EVIDENCE
Commit code + tests + docs skeleton. From the CLEAN commit run:
  <main>\.venv\Scripts\python.exe scripts\run_frame_diagnostics.py --comparison-run <...comparison> --slam-run <...slam>
  --geometry-run <...geometry> --sequence-dir <main>\data\raw\tum_rgbd\rgbd_dataset_freiburg1_xyz
  --manifest data\manifests\tum_fr1_xyz.json --output-root <main>\results\runs
  --run-id yulian_u01_diag_smoke200_<sha7>_01 --plot
Require run.json status ok and dirty_worktree=false. Copy small outputs into results/summaries/yulian_u01_diag_smoke200_
<sha7>.{json,csv} (source run IDs + sha256, commit, 22 rows, flag counts, correlations, depth cross-check difference,
tracking availability, limitations: one easy sequence, n=22, final-snapshot anchors are offline/non-causal, GT reference
approximation, no real-time claim) and the two plots. Inspect plots visually. Write docs/ROBUST_FUSION.md (Ukrainian):
§1 goal and hypothesis of P1-robust (closing the P1->B1 gap is a hypothesis; negative results are reported), §2 U-01
method, GT separation, threshold-source table, results, which signals correlate with error, implications for U-02,
limitations, commands. Commit these as a second commit (code unchanged; the run's git_commit is the first commit).

ACCEPTANCE
22/22 rows with explicit nulls+reasons; GT-free phase written before any GT read (tested); residuals.csv cross-check
passed; correlations + failure table present; full suite and CI green on all legs; PR diff only allowed files;
git diff --check clean; no absolute paths, drive letters, home paths or secrets in committed files.

STOP CONDITIONS (do not merge; write a blocker report in the PR)
Provenance/sha256 or residuals.csv mismatch; source runs not ok; any frozen/N/Y/shared file would need changes; GT
needed in Phase A; size limits exceeded; CI red.

PR
Title: "feat(wp3): per-keyframe frame diagnostics for P1-robust (U-01)". Body: goal, design, GT separation, evidence,
limitations, and this status row for Nazar to copy at the next IC:
| U-01 | done | <PR>, clean <sha7>, run yulian_u01_diag_smoke200_<sha7>_01, results/summaries/yulian_u01_diag_smoke200_<sha7>.json | next: U-02 |
Append the commit/PR attribution lines required by the session.

FINAL REPORT
Base SHA, branch, commit SHAs, PR URL, merge SHA, exact test counts (local + CI), run ID + status, summary/plot paths,
per-signal Spearman values, flag counts, tracking availability, any deviation from this brief. Then stop; do not start U-02.
```
