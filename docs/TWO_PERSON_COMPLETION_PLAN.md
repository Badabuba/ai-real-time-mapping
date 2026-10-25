# Two-person completion plan

- **Audit date:** 2026-10-25
- **Audited base:** `origin/develop` = `7b4b26e2e0f052ca950b0d1259f8594229f25036` (Merge PR #8). `origin/main` points to the same commit.
- **Prepared by:** Nazar (with Claude Code), as a proposal. Nothing here changes historical ownership, and nothing is approved until both people accept it in review.
- **Executors:** Nazar (Track N) and Yaropolk (Track Y). Yulian's merged WP3/WP4 implementation is a shared, stable, read-only component.
- **Scope:** finish the documented WP0–WP6 project (PLAN.md §2, EXPERIMENTS.md §6, INTERIM_REVIEW.md). No new phase, no P2/semantics, no new alignment implementation.

**Project definition of done.** The project is complete for the current version when all of the following hold:

1. A tagged commit on `main` reproduces the B0 baseline and the P1 pipeline from a fresh clone, using documented commands.
2. The pipeline has run on the frozen development, selection and held-out splits with one frozen protocol.
3. The results table reports trajectory, depth, map and performance metrics with units, alignment mode, hardware and the GT-use rule.
4. The required ablations are reported, or explicitly skipped with a reason.
5. Every real-time statement is backed by measured p95 latency and throughput, or the system is honestly labelled offline.
6. A prerecorded demo, the slides, a contribution table with evidence links, and a rehearsal within the time limit exist.

---

## 1. Current verified state

Verification performed for this plan: `git fetch --all --prune`; `gh pr list --state all` (8 PRs, all merged, none open); `gh run list` (CPU-correctness workflow green on `7b4b26e` for both `develop` and `main`, run `40191430426`); local CPU suite on a clean `origin/develop` worktree: **472 passed, 1 skipped** (30.6 s, Windows, Python 3.11 `.venv`). Branch contents were checked with `git log`/`git diff --stat` against their merge bases, plus `git merge-tree` conflict probes. No GPU, SLAM or Docker work was run for this audit.

### 1.1 Merged and complete

| Item | Evidence | Original owner |
|---|---|---|
| C1 TUM loader + `FrameRecord` | `src/rt_mapping/data/tum.py`, `src/rt_mapping/contracts/frame.py`; PR #6 | Nazar (WP1) |
| C2 fr1/xyz smoke manifest | `data/manifests/tum_fr1_xyz.json`, `scripts/build_tum_manifest.py`; PR #1 | Nazar (WP1) |
| C3 `GeometryPrediction`, adapter protocol, intrinsics | `src/rt_mapping/contracts/geometry.py`, `src/rt_mapping/geometry/{adapter,intrinsics}.py`; PR #2 | Nazar (WP1) |
| C4 depth eval, timing, `run.json` contract | `src/rt_mapping/evaluation/{depth,timing}.py`, `src/rt_mapping/contracts/run_manifest.py`; PR #3 | Nazar (WP1) |
| C5 DA3 Metric adapter + runner | `src/rt_mapping/adapters/da3_metric.py`, `src/rt_mapping/runs/geometry_run.py`, `scripts/run_tum_da3_metric.py`; PR #4 (`e4eb08d`) | Nazar (WP1) |
| WP2 native setup, B0 smoke, sparse export | `src/rt_mapping/slam/`, `scripts/run_wp2_pyslam.py`, `docs/WP2_SETUP.md`, `docs/WP2_SPARSE_EXPORT.md`, `results/summaries/wp2_sparse_fr1_xyz_200_20261023.json`; PR #5 (`e114490`) | Yaropolk (WP2) |
| WP3 robust scale/Sim(3), correspondences | `src/rt_mapping/alignment/`; PR #7 (`24b16e2`) | Yulian (WP3) |
| WP4 fusion, offline mapping, comparison, one-config launcher | `src/rt_mapping/fusion/voxel.py`, `src/rt_mapping/runs/{mapping_run,comparison_run,pipeline_run}.py`, `scripts/run_pipeline.py`; PR #7/#8 | Yulian (WP4 integration) |
| Real 200-frame smoke pipeline (B0/B1/P1-raw/P1-global, keyframes 2/5) | run `yulian_tum_e2e_f200_20261025_01`, clean `4952e37`; `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`; `docs/WP3_WP4_COMPLETION.md` | Yulian |
| Linux/Docker pySLAM runtime recipe | `containers/wp2.Dockerfile`, `scripts/build_wp2_linux_native.py`, `docs/WP2_LINUX_CONTAINER.md`; PR #8 | Yulian (assist on WP2 runtime) |
| Trajectory and map evaluators (+ evo parity) | `src/rt_mapping/evaluation/{trajectory,map_geometry,oracle}.py`; `results/summaries/wp3_wp4_yulian_real_evo_parity.json` | Yulian |
| CPU CI (Ubuntu/Windows × Python 3.11/3.12) | `.github/workflows/tests.yml` | Yulian |

### 1.2 Merged but insufficiently validated

- **B0 is only on smoke fr1/xyz.** The pose fraction is explicitly *not* tracking success. Historical macOS runs `_02`/`_03` have `dirty_worktree=true`. The merged runner records neither per-frame tracking states nor stage timing (`slam/pyslam_export.py` limitations: "Not all-frame tracking observations or timing").
- **Trajectory metrics cover retained keyframes only.** They come from the comparison run (`comparison_run.py`: "retained keyframes, not all-frame trajectory/tracking evaluation"). `evaluation/trajectory.py` has no gap or tracking-state handling.
- **The one-config pipeline has been reproduced on one machine only** (Yulian's RTX 3070 Ti + Docker). There is no second reproduction.
- **Smoke used DA3 at `process_res` 384** (C5 default). The model-selection spike used 504. The final protocol must pin one value.
- **Smoke ablations show tradeoffs only.** P1-global does not beat P1-raw on map Chamfer. Confidence ablation is skipped because DA3 returns no confidence. `alignment/causal.py` (P1-window) has never run on real data.
- **The WP2 dataset preflight is smoke-only.** `slam/setup.py` rebuilds the manifest with `build_tum_manifest(... smoke_frames=manifest["splits"]["smoke"]...)` and so cannot verify the wider split manifests.
- **Decisions D001–D004 and D008 are still "proposed"** (PROJECT_STATUS §7).

### 1.3 Complete locally but unmerged (not on any remote)

| Local branch @ commit | Useful content | Fate in this plan |
|---|---|---|
| `feature/nazar-wp1-integration` @ `5e542d7` (base `ce095fa`) | Four frozen split manifests + `scripts/freeze_tum_split.py`; UniDepth V2 adapter; paired selection protocol/scorecard; ADR001 (proposed: UniDepth primary, DA3 fallback); clean selection50 re-run evidence `wp1_integrated_selection50_{da3,unidepth}_463b446` | Port selectively onto `develop` in **N-01** (splits) and **N-03** (UniDepth/selection). Code files apply without conflicts; only CLAUDE.md, README.md, PROJECT_STATUS.md and `tests/test_import_hygiene.py` conflict, and those are not ported. |
| `feature/nazar-depth-ablations` @ `047992e` | DA3 resolution 384 vs 504 and UniDepth confidence-quantile depth-only ablations on dev50 | Port the evidence in **N-04**. The confidence mapping there (`1/(1+err)`) is rank-equivalent to the newer `-err` convention; re-verify retained counts. |
| `feature/nazar-assist-wp2-evaluation` @ `816b7f4` | Nazar's *assistance* in Yaropolk's WP2: a normalized all-frame CSV contract with truthful `UNKNOWN` states, and an evaluator CLI | **Reference only** for Y-01/Y-02/Y-03. It conflicts with `develop` in `slam/smoke.py`, `tests/test_wp2_setup.py` and `tests/test_import_hygiene.py`, and overlaps Yulian's `evaluation/trajectory.py`. Yaropolk decides what to adopt (TD-2). |

Local ignored runs on Nazar's machine (`results/runs/`, never committed): the WP1 selection/dev50 runs listed in `results/summaries/wp1_integration_verification_20261024.json` on the branch above; `c5_*`; and alternative-runner `wp2_*_4484fd7` runs (see the held-out note below). Under the independence rules, these may be cited only through committed summaries.

### 1.4 Superseded work (do not merge)

| Ref | Why superseded |
|---|---|
| local `main` @ `ed374e0` (ahead 45 / behind 14 of `origin/main`) | Old local consolidation; `origin/main` = `origin/develop` now. Never push or merge it. |
| `feature/nazar-assist-wp3-alignment-foundation` @ `fd73d56` | Synthetic alignment foundation, superseded by Yulian's merged `alignment/` (PR #7/#8). No replacement WP3 code. |
| `feature/nazar-assist-yaropolk-pyslam-independent` @ `f569efe`, `…-pyslam` @ `30a3cd4`, `…-trajectory` @ `30a3cd4`, `…-trajectory-independent` @ `7e8b135` | Alternative pySLAM v2.2.1 Docker runner and contracts. The merged baseline is pySLAM `96019cf` via `scripts/run_wp2_pyslam.py`. The causal keyframe-event technique may be read as reference only. |
| `feature/nazar-assist-yaropolk-wp4-handoff` @ `26541e0`, `…-wp5` @ `b66e925`, `…-wp6` @ `720db70` | Input-join audit, map metrics and keyframe scheduling, superseded by Yulian's `mapping_run`/`map_geometry`/`comparison_run`. The SLAM preview/outline (`wp6`) may be consulted for slides. |
| `feature/nazar-dataset-splits`, `feature/nazar-model-selection`, `feature/nazar-unidepth-v2`, `feature/nazar-wp1-evidence`, `verify/nazar-wp1-20261023`, `review/nazar-wp1-20261023` | Consolidated into `feature/nazar-wp1-integration`. |
| Worktree `wp5-keyframe-runs` (branch `feature/nazar-assist-yaropolk-keyframe-runs` @ `31cfd29`, dirty) | Uncommitted experiments. **Not touched, not a dependency.** |
| `stash@{0}` (WP2 runtime source in progress) | Preserved; not used. |
| Remote `yaropolk-wp1-wp2-integration`, `codex/yulian-*` | Already merged (PR #5, #7, #8). |

### 1.5 Held-out status (verified)

- `tum_fr3_long_office_heldout.json` is frozen (archive SHA-256 `c7cd8e1a…59e9c`) on the local WP1 branch. Freezing reads file hashes only.
- No depth or map inference, P1 run or GT-based metric has been computed on fr3.
- **Disclosure item:** run `wp2_heldout2488_4484fd7` (Nazar's superseded alternative v2.2.1 runner, clean commit `4484fd7`) attempted B0 on fr3 and **failed** inside upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`). It produced no trajectory and no metrics. It was not used to tune anything. The held-out split can still be called held-out for P1 if this is disclosed (TD-5).
- The same superseded runner ended `degraded` (`tracking_lost`) on fr1/desk 573. This is a *risk hypothesis* for wider-sequence B0, not evidence about the merged `96019cf` runner.

### 1.6 Missing work

1. Frozen dev/selection/held-out manifests on `develop`.
2. UniDepth adapter and selection evidence on `develop`.
3. A model-agnostic geometry stage usable by `run_pipeline.py`: `scripts/run_geometry_benchmark.py` on the local branch has no `--output-root`, which the launcher always appends.
4. All-frame tracking states, causal keyframe flags and per-frame SLAM timing.
5. A recorded B0 trajectory evaluation (Sim(3) ATE/RPE, tracking success, failure accounting).
6. SLAM peak RAM, cold start and throughput.
7. Split-manifest support and per-split configs in the WP2 runner.
8. Development + selection benchmark and ablations.
9. Protocol freeze.
10. Held-out benchmark.
11. End-to-end performance evidence.
12. Demo, slides, contribution table, reproducibility guide, assignment audit, release tag.

### 1.7 Blockers and gates

| Blocker | Affects | Type |
|---|---|---|
| WP2 preflight accepts only the C2 smoke manifest | All wider B0/P1 runs | Code (Y-04), after N-01 is merged |
| Yaropolk needs the dev/selection/held-out TUM archives on macOS (~3.7 GB) | Y-04…Y-06 | Download permission |
| Nazar needs a Docker build of the merged pySLAM image (downloads base image/sources, several GB, long compile) | N-02 onwards | Download/build permission |
| Primary model choice, optional ablations, held-out disclosure | N-05/N-06 | Team decisions (§8) |
| Presentation/final deadline and time limit unknown (PROJECT_STATUS §5) | Final chunks | Team decision |

### 1.8 Mandatory versus optional

- **Mandatory** (EXPERIMENTS.md §6 "required", PLAN.md §8, INTERIM_REVIEW.md):
  - B0 on smoke/dev/selection/held-out;
  - B1 on dev/held-out;
  - two-candidate model spike;
  - P1-raw and P1-global on all splits;
  - P1-window on dev;
  - confidence ablation on dev/selection (UniDepth only; DA3 is explicitly skipped);
  - keyframe-interval ablation on dev;
  - latency/memory evidence;
  - demo, slides, contribution table, tag.
- **Optional / out of scope:** P2 (DUSt3R/VGGT), ICP refinement (not implemented; TD-4), KITTI, semantics, streaming/async real-time implementation, P1-window on held-out unless dev improves.

---

## 2. Definition of done

Legend: **✔** already satisfied · **N** Track N · **Y** Track Y · **IC** integration checkpoint · **TD** team decision · **OPT** optional/out of scope.

**Integration**
- [x] ✔ C1–C5, WP2 sparse baseline and WP3/WP4 merged on `develop`, CI green (`7b4b26e`).
- [ ] IC IC1: frozen splits (N-01), UniDepth/selection (N-03), all-frame SLAM export (Y-01) and B0 evaluator (Y-02) merged; full suite green.
- [ ] IC IC2: WP2 split support (Y-04) and model-agnostic pipeline stage (N-04) merged.
- [ ] IC IC3: frozen benchmark protocol merged *before* any held-out run.

**Frozen data splits**
- [x] ✔ Smoke manifest `data/manifests/tum_fr1_xyz.json`.
- [ ] N Dev/spike50/selection50/held-out manifests merged and byte-reproducible (N-01).
- [ ] TD Team acceptance of the split freeze (TD-1, via the N-01 review).

**Model selection**
- [ ] N UniDepth adapter, selection protocol, scorecards and ADR001 (proposed) on `develop`, with a clean re-run (N-03).
- [ ] TD Primary model DA3 vs UniDepth (TD-3), recorded in ADR001 at IC3.

**SLAM baseline**
- [x] ✔ Native/Docker B0 smoke + sparse export.
- [ ] Y All-frame tracking states, causal keyframes, per-frame timing (Y-01).
- [ ] Y Recorded B0 Sim(3) ATE/RPE + resources on smoke (Y-02); tracking success + failure accounting (Y-03).
- [ ] Y Split-manifest support + per-split frozen B0 configs (Y-04).
- [ ] Y B0 dev/selection runs + failure analysis (Y-05); B0 held-out (Y-06).

**Alignment/fusion**
- [x] ✔ Global scale, correspondences, fusion, comparison (Yulian, PR #7/#8).
- [ ] N P1 with UniDepth predictions verified through the unchanged alignment/fusion (N-04).
- [ ] OPT ICP refinement (TD-4; proposed out of scope).

**Benchmark**
- [x] ✔ Smoke B0/B1/P1-raw/P1-global comparison (Yulian).
- [ ] N Development + selection benchmark (N-05).
- [ ] IC Protocol freeze (IC3).
- [ ] N Held-out benchmark (N-06).

**Required ablations**
- [x] ✔ Global vs raw scale on smoke; keyframes 2/5 on smoke; DA3 confidence explicitly unavailable.
- [ ] N Keyframe interval, P1-window, confidence (UniDepth), primary vs fallback on dev/selection (N-05).
- [ ] N DA3 resolution and UniDepth confidence depth-only evidence ported (N-04).
- [ ] OPT P2 geometry model.

**Latency and memory**
- [ ] Y SLAM per-frame p50/p95, peak RSS, cold start, throughput (Y-02/Y-03).
- [ ] N Model + alignment + fusion p50/p95, peak VRAM/RAM, wall-clock throughput; real-time verdict (N-06).

**Independent reproduction**
- [ ] N Second-machine reproduction of the merged smoke pipeline (N-02).
- [ ] Y B0 on a second platform (macOS native vs Nazar's Docker), compared in the final table (Y-05/Y-06 → F-N1).
- [ ] Y Fresh-clone CPU reproduction (F-Y2).

**Documentation**
- [ ] N Final results, limitations, reproducibility guide, status docs (F-N1).
- [ ] Y WP2 docs (Y-01…Y-06).

**Demo, presentation, contributions, release**
- [ ] N Prerecorded demo (F-N2).
- [ ] Y Slides + rehearsal (F-Y1); contribution table (F-Y1); assignment audit (F-Y2).
- [ ] TD Deadlines, time limit, slide format, demo storage, tag name (TD-6).
- [ ] IC Release PR `develop → main` + tag (F-0).

---

## 3. File and ownership boundaries

"Planned" or "(new)" = the file does not exist yet on `origin/develop`. Files that a chunk ports from a local branch exist at the cited local commit (`5e542d7` for N-01/N-03, `047992e` for N-04) and are planned on `develop`. Short paths such as `slam/setup.py` are relative to `src/rt_mapping/`. Before the final phase, **exactly one person edits each shared documentation file**. A person who needs a change in an area they don't own asks for it through the PR description or their own handoff doc.

| Area | Track N owner (may edit) | Track Y owner (may edit) | Shared read-only | Integration-only | Conflict-avoidance rule |
|---|---|---|---|---|---|
| `data/manifests/`, `src/rt_mapping/data/`, `scripts/{build_tum_manifest,freeze_tum_split(planned)}.py` | ✔ | — | Y reads | — | Y consumes only the merged manifests |
| `src/rt_mapping/adapters/`, `geometry/{adapter,intrinsics}.py`, `runs/geometry_run.py`, `evaluation/{depth,tum_depth,model_selection(planned),prediction_grid(planned),geometry_verification(planned),confidence_ablation(planned)}.py` | ✔ | — | Y reads | — | — |
| `contracts/{frame,geometry,run_manifest,_validation}.py`, `evaluation/timing.py` | ✔ (only if a contract bug blocks) | — | both read | — | Y requests changes via N; Y reuses `summarize_timings` unchanged |
| `src/rt_mapping/slam/`, `contracts/slam.py` (planned), `evaluation/slam_run.py` (planned) | — | ✔ | N reads | — | N never edits SLAM code (assist branches are reference only) |
| `scripts/{run_wp2_pyslam,prepare_wp2_baseline,check_wp2_environment,build_wp2_native,build_wp2_linux_native,visualize_wp2_trajectory}.py`, `scripts/{evaluate_wp2_run,measure_wp2_resources}.py` (planned), `containers/`, `requirements/wp2-*`, `configs/wp2_*.json` | — | ✔ | N runs them unchanged | — | N reports runtime problems to Y |
| `scripts/{run_tum_da3_metric,check_wp1_environment,run_da3_metric_smoke}.py`, `scripts/{run_geometry_benchmark,compare_geometry_models,verify_geometry_run,analyze_confidence,render_demo}.py` (planned), `requirements/wp1-*`, `configs/{model_assets,selected_geometry}.json` (planned) | ✔ | — | — | — | — |
| New pipeline/benchmark configs `configs/pipeline.nazar.*.json`, `configs/benchmark_frozen.json` (planned) | ✔ | — | Y reviews | — | Existing `configs/pipeline.tum.*.json` stay unchanged |
| Yulian WP3/WP4: `alignment/`, `fusion/`, `runs/{mapping_run,comparison_run,pipeline_run,synthetic_mapping,artifacts}.py`, `evaluation/{trajectory,map_geometry,oracle,synthetic_scene}.py`, `geometry/projection.py`, `scripts/run_{pipeline,mapping_comparison,offline_mapping,alignment_smoke,comparison_smoke}.py`, `configs/{mapping_comparison,offline_mapping}.json` | defect fixes only, focused `fix/nazar-*` PR, Yulian review | — | ✔ both | — | Y reports defects to N; no replacement implementations |
| Tests: `tests/test_{tum_*,geometry_*,da3_*,depth_*,timing,run_manifest,intrinsics}.py` + new N tests | ✔ | — | — | — | — |
| Tests: `tests/test_{slam_*,wp2_setup,pyslam_sparse_native}.py` + new Y tests | — | ✔ | — | — | — |
| `tests/test_import_hygiene.py`, `tests/conftest.py`, Yulian's tests | — | — | ✔ | final only | Each track adds its own `tests/test_import_hygiene_wp1.py` / `_wp2.py` (planned) instead |
| `results/summaries/nazar_*`, `results/plots/nazar_*`, `results/summaries/wp1_*` | ✔ | — | — | — | Never edit existing summaries |
| `results/summaries/yaropolk_*`, `results/plots/yaropolk_*` | — | ✔ | — | — | Never edit existing summaries |
| Historical `results/summaries/{wp2_*,wp3_wp4_yulian_*}`, `results/plots/{wp2_*,yulian_*}` | — | — | ✔ | — | Immutable |
| Track docs N: `docs/{DATASET_FREEZE,UNIDEPTH,SELECTION_PROTOCOL,WP1_HANDOFF,DEPTH_ABLATIONS,NAZAR_REPRODUCTION,DEVELOPMENT_BENCHMARK,HELDOUT_BENCHMARK,BENCHMARK_PROTOCOL,DEMO}.md`, `docs/decisions/ADR001_geometry_model.md` (all planned) | ✔ | — | — | — | — |
| Track docs Y: `docs/WP2_SETUP.md`, `docs/WP2_SPARSE_EXPORT.md`, `docs/WP2_LINUX_CONTAINER.md`, `docs/{WP2_TRACKING_EXPORT,WP2_EVALUATION,WP2_BENCHMARK}.md` (planned) | — | ✔ | — | — | — |
| `docs/ARCHITECTURE.md` | — | ✔ (SlamExport section) | N reads | — | N documents geometry semantics in `docs/UNIDEPTH.md` instead |
| `docs/EXPERIMENTS.md`, `docs/MODEL_SELECTION.md`, `docs/ENVIRONMENT.md` | ✔ | — | Y reads | — | EXPERIMENTS is edited only at IC3 (freeze) |
| `docs/INTERIM_REVIEW.md`, `docs/{CONTRIBUTIONS,PRESENTATION_OUTLINE,SUBMISSION_AUDIT}.md` (planned) | — | ✔ | — | — | — |
| `docs/PROJECT_STATUS.md`, `docs/INTEGRATION_STATUS.md` | ✔ at IC1/IC2/IC3/final only | — | — | ✔ | Y puts status rows in PR bodies; N copies them at the checkpoint |
| `README.md`, `CLAUDE.md`, `scripts/README.md`, `configs/README.md`, `results/README.md`, `tests/README.md`, `pyproject.toml`, `.gitignore` | — | — | — | ✔ N in F-N1 (`pyproject.toml` only if a dependency group is needed, announced first) | Nobody edits them during waves |
| `.github/workflows/` | — | — | — | ✔ Y in F-Y2 only if needed | — |
| `PLAN.md`, `CONTRIBUTING.md`, `docs/PROJECT_BRIEF.md`, `docs/YULIAN_HANDOFF.md`, `docs/WP3_WP4_COMPLETION.md`, this file | — | — | ✔ | — | Change only by a team decision |

**Naming:**
- Branches: N `feature/nazar-*`, Y `feature/yaropolk-*`.
- Run IDs: `nazar_<chunk>_<topic>_<sha7>_NN` and `yaropolk_<chunk>_<topic>_<sha7>_NN`.
- Docker container: Nazar `rt-mapping-wp2-nazar`; Yaropolk uses the native macOS `.venv-pyslam` (or, if needed, `rt-mapping-wp2-yaropolk`).
- Summaries/plots carry the person prefix.

---

## 4. Parallel work waves

```text
            Track N (Nazar)                         Track Y (Yaropolk)
Wave 1      N-01 frozen splits PR          ‖        Y-01 all-frame states/timing export
Wave 2      N-02 2nd-machine smoke repro   ‖        Y-02 B0 evaluation + resources
            N-03 UniDepth + selection      ‖        Y-03 tracking success + failure accounting
─────────── IC1: N-01, N-03, Y-01, Y-02 merged (Y-03, N-02 desirable) ──────────────
Wave 3      N-04 model-agnostic pipeline   ‖        Y-04 WP2 split-manifest support + configs
─────────── IC2: N-04 and Y-04 merged; TD-4 decided ────────────────────────────────
Wave 4      N-05 dev + selection benchmark ‖        Y-05 B0 dev/selection runs + failures
─────────── IC3: protocol freeze merged (TD-3, TD-5) ───────────────────────────────
Wave 5      N-06 held-out + performance    ‖        Y-06 held-out B0 (frozen config)
─────────── Final: F-N1 ‖ F-Y1 → F-N2 ‖ F-Y2 → F-0 release ─────────────────────────
```

| Wave | Nazar | Yaropolk | Why they don't collide |
|---|---|---|---|
| 1 | N-01 | Y-01 | `data/` + manifests vs `slam/` + `contracts/slam.py`; neither reads the other's outputs |
| 2 | N-02 (while N-01 is in review), then N-03 (after N-01 is merged) | Y-02 (while Y-01 is in review), then Y-03 (after Y-01 + Y-02 are merged) | N-02 only *runs* merged WP2 code from a new config file; Y never touches WP1 files |
| IC1 | Nazar runs the checkpoint (full suite, PROJECT_STATUS update) | Yaropolk reviews the checkpoint PR | — |
| 3 | N-04 | Y-04 | N edits WP1 scripts + new N configs; Y edits `slam/setup.py` + `configs/wp2_*` |
| 4 | N-05 (Nazar's machine, Docker + CUDA) | Y-05 (Yaropolk's machine, macOS native) | Separate run IDs, summaries and hardware; exchange only committed summaries |
| 5 | N-06 | Y-06 | Same frozen protocol, separate runs |

**Two checkpoints beyond IC1.** The requested structure has one checkpoint before Wave 3. Two more are genuinely needed:

- **IC2** exists because the dev/held-out pipeline needs Yaropolk's split-manifest support in `slam/setup.py`. That support in turn needs Nazar's merged manifests.
- **IC3** exists because the protocol must be frozen and merged before any held-out run.

**No chunk before IC1 requires anything from the other track** (checked in §10 by the dependency column).

---

## 5. Track N — Nazar chunks

**Standard rules block (pasted into every N and Y prompt as `STANDARD RULES`):**

> Read `CLAUDE.md` first. Run `git fetch --all --prune`, `gh pr list --state all --limit 30` and `gh run list --limit 5`, and report the exact `origin/develop` SHA. Base the work on that exact `origin/develop` unless the chunk says otherwise. Never use local `main`. Preserve every other worktree, branch, stash, ignored run and uncommitted file. Never touch the dirty `wp5-keyframe-runs` worktree. Create a new worktree for the chunk branch (`git worktree add --no-track -b <branch> ../<dir> origin/develop`). Modify only the allowed files. Never use files from the other person's ignored `results/runs/`. Ground truth only in evaluation/oracle code. Never overwrite a finished `run.json` (new config = new run_id). Never tune on held-out data. No installs, upgrades or downloads unless this prompt lists them, and ask before each one even then. This prompt authorizes commit (configured Git identity), push of this branch, and one PR to `develop`. It does **not** authorize merging, tagging, force-pushing or editing other PRs. If a stop condition occurs, stop and write a blocker report instead of improvising. End with an evidence report: base SHA, branch, commit SHA(s), PR URL, exact test counts, run IDs with status, summary paths, deviations from the brief, open questions.

---

### N-01 — Frozen development/selection/held-out manifests on `develop`

**Objective.** Merged-ready PR that adds the four frozen TUM split manifests and the split-freeze tool to `develop`, byte-reproducible from local data.

**Why it is required.** EXPERIMENTS.md §2 (frozen splits), PLAN WP0 ("frozen sequence list"). These manifests are the input contract for all wider B0/P1 runs (Y-04, N-05, N-06).

**Implementer and attribution.** Nazar implements. The original owner is Nazar (WP1/WP0 data). The code is ported from his own local commit `58f3e7a` as consolidated in `6fa2f55`.

**Prerequisites.**
- Base `origin/develop` (`7b4b26e` or newer).
- Source branch `feature/nazar-wp1-integration` @ `5e542d7` (local).
- Windows `.venv` (Python 3.11).
- Local archives/extractions of fr1/desk, fr2/desk and fr3/long_office_household under `data/raw/tum_rgbd/` (present; no download).
- No GPU or Docker.
- Review gate: Yaropolk review, which doubles as TD-1 split acceptance.

**Allowed scope.**
- `data/manifests/tum_fr1_desk_development.json`
- `data/manifests/tum_fr1_desk_spike50.json`
- `data/manifests/tum_fr2_desk_selection50.json`
- `data/manifests/tum_fr3_long_office_heldout.json`
- `scripts/freeze_tum_split.py`
- `src/rt_mapping/data/manifest.py`
- `tests/test_tum_split_manifest.py`
- `docs/DATASET_FREEZE.md`

**Forbidden scope.**
- `data/manifests/tum_fr1_xyz.json`
- PROJECT_STATUS.md, README.md, CLAUDE.md, EXPERIMENTS.md, `tests/test_import_hygiene.py`
- `slam/`, any UniDepth/selection files (N-03)
- held-out inference

**Git workflow.** Branch `feature/nazar-frozen-splits` from `origin/develop`. Independent PR → `develop`. Stop before merge. Yaropolk reviews.

**Work.**
1. `git diff ce095fa feature/nazar-wp1-integration -- <allowed files>`, then check out exactly those paths from `5e542d7`.
2. Confirm that `build_tum_manifest` output for fr1/xyz is unchanged.
3. Update `docs/DATASET_FREEZE.md`:
   - The base is now `7b4b26e`.
   - Held-out disclosure: the failed superseded-runner attempt `wp2_heldout2488_4484fd7` produced no metrics.
   - Team acceptance is pending review.
4. Note in the PR that `tum_fr3_long_office_heldout.json` is ~1.09 MB (a manifest, not data).

**Verification.**
- `pytest tests/test_tum_split_manifest.py tests/test_tum_manifest.py -q`, then the full suite (expect ≥ 472 + new tests passed, 1 skipped).
- `freeze_tum_split.py … --check` for all four manifests (byte-identical).
- `build_tum_manifest.py --check` for fr1/xyz.
- `git diff --check`.
- Grep for absolute paths (`C:/`, `/Users/`) in the new JSON/docs.

**Acceptance criteria.**
- [ ] 4 manifests byte-identical under `--check`.
- [ ] fr1/xyz manifest unchanged.
- [ ] Full CPU suite green; CI green on the PR.
- [ ] No absolute paths; no held-out runs.
- [ ] PR body lists archive SHA-256 per split and the disclosure line.

**Required output.** PR with manifests, tool, tests and DATASET_FREEZE.md.

**Failure and stop conditions.**
- Stop if any `--check` differs: report the diff and do not regenerate silently.
- Stop if the fr1/xyz manifest would change.
- Stop if a local archive hash mismatches its manifest.

**One-prompt execution brief.**
```text
Chunk N-01 (Track N, Nazar): port the frozen TUM split manifests to develop.
STANDARD RULES: <paste block from §5>.
Branch feature/nazar-frozen-splits from exact origin/develop. Source of truth: local branch
feature/nazar-wp1-integration @ 5e542d7 (base ce095fa). Port ONLY: data/manifests/tum_fr1_desk_development.json,
tum_fr1_desk_spike50.json, tum_fr2_desk_selection50.json, tum_fr3_long_office_heldout.json, scripts/freeze_tum_split.py,
the split-builder change in src/rt_mapping/data/manifest.py, tests/test_tum_split_manifest.py, docs/DATASET_FREEZE.md.
Do not touch tum_fr1_xyz.json, shared docs, test_import_hygiene.py, SLAM or UniDepth files.
Update DATASET_FREEZE.md: new base SHA; held-out disclosure (superseded runner run wp2_heldout2488_4484fd7 failed
in upstream local_mapping, no trajectory/metrics, nothing tuned); team acceptance pending Yaropolk review.
Verify: targeted + full pytest with .venv; freeze_tum_split.py --check for all 4 manifests using existing
data/raw/tum_rgbd (no downloads); build_tum_manifest.py --check for fr1/xyz; git diff --check; grep for absolute paths.
Open one PR to develop titled "feat(wp1): frozen development/selection/held-out TUM manifests", request Yaropolk
review, do not merge. Report the evidence.
```

---

### N-02 — Second-machine reproduction of the merged smoke pipeline

**Objective.** A clean new run of the merged one-config pipeline on fr1/xyz smoke-200 on Nazar's hardware (Docker pySLAM `96019cf` + CUDA DA3), compared against Yulian's committed summary.

**Why it is required.**
- PLAN WP4 reviewer rule ("reviewer має відтворити хоча б smoke run") and "independent reproduction".
- It also establishes Nazar's runtime for N-04…N-06 and a second-platform B0 data point.

**Implementer and attribution.** Nazar implements, as an independent reviewer of Yulian's WP4 and Yaropolk's WP2 runtime. No ownership change.

**Prerequisites.**
- `origin/develop`.
- Docker Desktop (Linux engine).
- **Permission** for the Docker build downloads (Python base image digest, pySLAM/GTSAM sources, pip freeze `requirements/wp2-linux-x86_64.txt`).
- Nazar's CUDA DA3 `.venv` with the pinned checkpoint already cached.
- fr1/xyz data (present).
- Independent of N-01.

**Allowed scope.**
- `configs/pipeline.nazar.smoke200.docker.json` (new)
- `results/summaries/nazar_n02_e2e_smoke200_<sha7>.json` (new)
- `docs/NAZAR_REPRODUCTION.md` (new)
- `results/plots/nazar_n02_*.png` (new, small)

**Forbidden scope.**
- Editing any WP2/WP3/WP4 source, `docs/WP2_LINUX_CONTAINER.md`, existing configs, Yulian's summaries
- Reusing Yulian's runs (not available, and forbidden)
- Container name `rt-mapping-wp2-yulian`

**Git workflow.** Branch `feature/nazar-pipeline-reproduction`. Independent PR → `develop`. Stop before merge. Yaropolk reviews (Yulian optional).

**Work.**
1. Build the image per `docs/WP2_LINUX_CONTAINER.md` with tag `rt-mapping-wp2:96019cf` (if absent) and start container `rt-mapping-wp2-nazar`.
2. Run the environment probe and the opt-in native sparse test.
3. Write a new pipeline config: a copy of `configs/pipeline.tum.windows-docker.json` with Nazar's container name and DA3 interpreter `.venv/Scripts/python.exe`. All other parameters stay identical.
4. Commit that config, then run `run_pipeline.py --run-id nazar_n02_e2e_smoke200_<sha7>_01` from the clean commit.
5. Compare against `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`: final poses, landmarks/keyframes, scale, inliers, voxel count, ATE, map metrics, DA3 metrics, timings.
6. Report differences as cross-machine variation, not parity.

**Verification.**
- `run.json` status ok for parent and all stages; `dirty_worktree=false`.
- Checkpoint SHA-256 matches `bbea5b0b…324776`.
- Full CPU suite.
- Summary contains source hashes.
- `git diff --check`; no absolute paths.

**Acceptance criteria.**
- [ ] Clean run with all stages ok, or a documented failure with logs.
- [ ] Comparison table with absolute and relative differences.
- [ ] Hardware, driver, Docker image ID and container limits recorded.
- [ ] No source changes.

**Required output.** Config, summary JSON, reproduction doc, PR. On failure: a blocker report in `docs/NAZAR_REPRODUCTION.md`.

**Failure and stop conditions.**
- Stop if the Docker build needs network access or packages not covered by the recipe.
- Stop if a WP3/WP4 defect appears. Report it; a fix would be a separate `fix/nazar-*` PR with Yulian review, not part of this chunk.
- Stop if the DA3 checkpoint is missing (no download).
- Do not tweak thresholds to "match" Yulian.

**One-prompt execution brief.**
```text
Chunk N-02 (Track N, Nazar): independently reproduce the merged one-config smoke pipeline on my machine.
STANDARD RULES: <paste block from §5>. This prompt additionally allows the Docker image build described in
docs/WP2_LINUX_CONTAINER.md (downloads base image/sources/packages) - ask me once before starting it.
Branch feature/nazar-pipeline-reproduction from exact origin/develop. Build image rt-mapping-wp2:96019cf if absent,
start container rt-mapping-wp2-nazar (never reuse/overwrite other containers), run check_wp2_environment.py
--probe-runtime and the opt-in native sparse unittest. Create configs/pipeline.nazar.smoke200.docker.json =
configs/pipeline.tum.windows-docker.json with only container name and DA3 interpreter (.venv/Scripts/python.exe)
changed. Commit it, then from the clean commit run scripts/run_pipeline.py --run-id nazar_n02_e2e_smoke200_<sha7>_01.
Do not edit any source. Compare with results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json and write
results/summaries/nazar_n02_e2e_smoke200_<sha7>.json (with source hashes) and docs/NAZAR_REPRODUCTION.md
(hardware, image ID, differences as cross-machine variation, no parity or real-time claims).
If a WP3/WP4 defect appears: stop and report, do not fix here. Full CPU pytest, git diff --check, absolute-path scan.
Open PR to develop, request Yaropolk review, do not merge.
```

---

### N-03 — UniDepth V2 adapter, paired selection protocol and ADR001 on `develop`

**Objective.** Merged-ready PR that brings the UniDepth adapter, generic geometry benchmark CLI, scorecard/verifier and ADR001 (status: *proposed*) to `develop`, with a clean re-run of the selection50 pair from the new commit.

**Why it is required.** MODEL_SELECTION.md §5–§7 (two-candidate spike, scorecard, ADR), EXPERIMENTS §6 "model spike (2 candidates) required", PLAN WP1 fallback model.

**Implementer and attribution.** Nazar implements; original owner Nazar (WP1). The code comes from his local `ccec264…e633faa`, `7f37d66`, `50c2805`, consolidated in `6fa2f55`/`463b446`.

**Prerequisites.**
- N-01 merged (same track).
- `.venv` (DA3) and the existing `.venv/unidepth` environment.
- Cached pinned checkpoints (no download).
- GPU, RTX 5070 Laptop.
- Data fr1/desk and fr2/desk (present).

**Allowed scope.** The WP1 files in `git diff --stat ce095fa 5e542d7` other than N-01's files and shared docs:
- `src/rt_mapping/adapters/unidepth_v2.py`, `src/rt_mapping/geometry/adapter.py`, `src/rt_mapping/runs/geometry_run.py`
- `src/rt_mapping/evaluation/{model_selection,prediction_grid,geometry_verification}.py`
- `scripts/{run_geometry_benchmark,compare_geometry_models,verify_geometry_run}.py`
- `requirements/wp1-{unidepth,unidepth-runtime,unidepth-lock,cpu}.txt`
- `configs/{model_assets,selected_geometry}.json`
- `docs/{UNIDEPTH,SELECTION_PROTOCOL,WP1_HANDOFF}.md`, `docs/decisions/ADR001_geometry_model.md`
- `results/summaries/wp1_{development50_final,selection50_final,integrated_selection50_20261024}_scorecard.json`, `results/summaries/wp1_integration_verification_20261024.json`
- tests `test_{unidepth_v2,model_selection,prediction_grid,spike_orchestration,geometry_verification}.py`
- new `tests/test_import_hygiene_wp1.py`
- new `results/summaries/nazar_n03_selection50_<sha7>_scorecard.json`

**Forbidden scope.**
- `tests/test_import_hygiene.py`, PROJECT_STATUS/README/CLAUDE/EXPERIMENTS/MODEL_SELECTION.md
- Superseded non-`_final` scorecards
- Depth ablations (N-04), WP2/WP3/WP4 files
- Changing the selection rubric after seeing results

**Git workflow.** Branch `feature/nazar-unidepth-selection` from `origin/develop` (after N-01 is merged). Independent PR. Stop before merge. Yaropolk reviews; Yulian is the PLAN WP1 reviewer and an optional second reviewer.

**Work.**
1. Port the files.
2. Put the import-hygiene additions into a new test file.
3. Keep C5 defaults byte-compatible: the DA3 CLI default stays 384; selection uses 504 explicitly.
4. Run clean selection50 for both models with new run IDs: `nazar_n03_sel50_da3_<sha7>_01`, `nazar_n03_sel50_unidepth_<sha7>_01`.
5. Run `verify_geometry_run.py` and the scorecard.
6. Compare depth with the historical `wp1_integrated_selection50_*_463b446` runs: expect bit-identical depth; the timing may differ.
7. ADR001 stays "proposed, team decision TD-3 pending".

**Verification.**
- Full CPU suite with the `.venv` CPU path.
- UniDepth unit tests use a fake backend.
- GPU runs complete with `dirty_worktree=false`.
- Verifier recomputes metrics and masks.
- Scorecard recomputation matches to 1e-12.
- Depth-identity check against the historical runs.
- `git diff --check`; absolute-path and secret scan.

**Acceptance criteria.**
- [ ] Full suite and CI green.
- [ ] Two new clean runs ok; weighted scores reported.
- [ ] Depth identical to historical runs on 50/50 frames, or the differences are quantified.
- [ ] ADR001 status is *proposed*, with the license limitation (CC-BY-NC-4.0) stated.
- [ ] No weights or sources vendored.

**Required output.** Code + tests + docs + scorecards + PR.

**Failure and stop conditions.**
- Stop on a checkpoint hash mismatch, on missing environments (no installs), or if the selection outcome would change only by altering the rubric.
- Stop if porting requires editing `contracts/*` in an incompatible way.

**One-prompt execution brief.**
```text
Chunk N-03 (Track N, Nazar): bring UniDepth V2 + paired model selection + ADR001 (proposed) onto develop.
STANDARD RULES: <paste block from §5>. Precondition: N-01 PR merged into origin/develop - verify, else stop.
Branch feature/nazar-unidepth-selection from exact origin/develop. Source: local feature/nazar-wp1-integration
@ 5e542d7. Port only the WP1 code/tests/docs/summaries listed in docs/TWO_PERSON_COMPLETION_PLAN.md N-03 "Allowed
scope" (excluding N-01 files and shared docs). Put import-hygiene additions in new tests/test_import_hygiene_wp1.py.
Keep the DA3 CLI default process_res 384 unchanged; selection uses explicit 504. Use existing .venv and .venv/unidepth
and cached checkpoints only. From the clean commit, run selection50 for both models with run IDs
nazar_n03_sel50_da3_<sha7>_01 and nazar_n03_sel50_unidepth_<sha7>_01 (manifest tum_fr2_desk_selection50.json,
--split selection --frames 50 --prewarm 10), run verify_geometry_run.py, compare_geometry_models.py ->
results/summaries/nazar_n03_selection50_<sha7>_scorecard.json, and check depth identity vs historical runs
wp1_integrated_selection50_{da3,unidepth}_463b446. ADR001 stays "proposed - TD-3 pending". Full pytest, git diff
--check, path/secret scan. PR to develop, request Yaropolk review, do not merge.
```

---

### N-04 — Model-agnostic pipeline geometry stage + UniDepth smoke P1 + depth-ablation evidence

**Objective.**
- `scripts/run_pipeline.py` can run the geometry stage with either model on any frozen manifest.
- A clean UniDepth smoke P1 run passes through the unchanged alignment/fusion/comparison, including a prediction-only confidence ablation.
- The dev50 depth-only ablation evidence is ported.

**Why it is required.**
- PLAN WP4: adapters by Nazar and Yaropolk.
- EXPERIMENTS §6: confidence ablation and primary-vs-fallback.
- This is the prerequisite for N-05.

**Implementer and attribution.** Nazar (WP1 adapter, WP5 models). Alignment/fusion stay Yulian's and are used unchanged.

**Prerequisites.**
- N-03 merged, and N-02's own SLAM smoke run present locally (Nazar's run, used via `reuse_run`).
- GPU.
- No Y artifacts.

**Allowed scope.**
- `scripts/run_geometry_benchmark.py` (add `--output-root`; accept launcher-appended args)
- `src/rt_mapping/runs/geometry_run.py`, `tests/test_spike_orchestration.py` or a new `tests/test_geometry_pipeline_stage.py`
- `configs/pipeline.nazar.smoke200.unidepth.json`, `configs/mapping_comparison.nazar.confidence.json` (new)
- `src/rt_mapping/evaluation/confidence_ablation.py`, `scripts/analyze_confidence.py`, `docs/DEPTH_ABLATIONS.md`
- `results/summaries/wp5_{da3_resolution_development50,unidepth_confidence_development50,da3_confidence_unavailable}.json` (ported from `047992e`)
- `results/summaries/nazar_n04_*.json`, `results/plots/nazar_n04_*.png`

**Forbidden scope.**
- Yulian's files (if the comparison rejects UniDepth predictions, stop and report)
- `slam/`, shared docs, existing pipeline configs

**Git workflow.** Branch `feature/nazar-model-agnostic-pipeline`. Independent PR. Stop before merge. Yaropolk reviews.

**Work.**
1. Add the stage-compatible CLI behaviour, with tests that use a fake adapter.
2. Pre-register confidence thresholds as prediction-only quantiles (e.g. retain 75%/50%), derived from **dev50 predictions only**, and write them into the new comparison config *before* running.
3. Run pipeline `nazar_n04_e2e_smoke200_unidepth_<sha7>_01` with `slam: {"reuse_run": <N-02 SLAM stage>}`.
4. Port the `047992e` evidence. State that the `1/(1+err)` → `-err` change is rank-equivalent, and re-verify the retained-pixel counts with the current code.

**Verification.**
- Full suite.
- New stage test.
- Clean run ok, all children ok.
- Model ID consistency check passes.
- Confidence child runs report thresholds and coverage.
- `git diff --check`.

**Acceptance criteria.**
- [ ] The launcher runs the geometry stage for `--model unidepth` and `--model da3`, proven by a test.
- [ ] UniDepth P1 smoke clean and ok.
- [ ] Confidence ablation reported with coverage.
- [ ] Ported ablation numbers re-verified.

**Required output.** Code, tests, configs, summaries, `docs/DEPTH_ABLATIONS.md`, PR.

**Failure and stop conditions.**
- Stop if `mapping_run`/`comparison_run` need changes.
- Stop if thresholds would have to be chosen from GT.
- Stop if the N-02 SLAM run is missing: rerun SLAM through the pipeline instead of borrowing anyone's run.

**One-prompt execution brief.**
```text
Chunk N-04 (Track N, Nazar): make the pipeline geometry stage model-agnostic and run UniDepth P1 on smoke.
STANDARD RULES: <paste block from §5>. Preconditions: N-03 merged; my own N-02 SLAM stage run exists locally.
Branch feature/nazar-model-agnostic-pipeline from exact origin/develop. Make scripts/run_geometry_benchmark.py work
as a run_pipeline.py stage (accept --run-id/--output-root appended by the launcher) with a fake-adapter test.
Do NOT edit alignment/fusion/mapping/comparison/pipeline_run code; if they reject UniDepth predictions, stop and
report. Pre-register UniDepth confidence thresholds as prediction-only quantiles computed from dev50 predictions
(no GT) in new configs/mapping_comparison.nazar.confidence.json before any run. Create
configs/pipeline.nazar.smoke200.unidepth.json reusing my N-02 SLAM stage and run
nazar_n04_e2e_smoke200_unidepth_<sha7>_01 from a clean commit. Port from local 047992e: confidence_ablation.py,
analyze_confidence.py, docs/DEPTH_ABLATIONS.md and the three wp5_* summaries; state the rank-equivalence of the
confidence mapping change and re-verify retained counts. Summaries -> results/summaries/nazar_n04_*.json.
Full pytest, git diff --check. PR to develop, request Yaropolk review, do not merge.
```

---

### N-05 — Development and selection benchmark with ablations

**Objective.** Pipeline results on fr1/desk development (573) and fr2/desk selection50:
- methods: B0-shared-scale, B1 oracle, P1-raw, P1-global, P1-window;
- ablations: keyframe intervals 2/5, confidence (UniDepth only), both models;
- plus B0 all-frame evaluation via Yaropolk's merged evaluator;
- and a proposed frozen protocol for held-out.

**Why it is required.** EXPERIMENTS §6 matrix (Dev/Selection columns), PLAN WP5, H1–H4.

**Implementer and attribution.** Nazar runs it (WP5 models + benchmark orchestration). The B0 metrics code is Yaropolk's; alignment is Yulian's. The summary credits each.

**Prerequisites.**
- IC2 passed: Y-04 merged (split support + `configs/wp2_pyslam_{development,selection}.json`) and N-04 merged.
- TD-4 decided.
- GPU + Docker.
- The `P1-window` `causal_window_frames` values pre-registered in the config before running.

**Allowed scope.**
- `configs/pipeline.nazar.{development,selection}.{da3,unidepth}.json`, `configs/mapping_comparison.nazar.development.json` (new)
- `results/summaries/nazar_n05_*.{json,csv}`, `results/plots/nazar_n05_*.png`
- `docs/DEVELOPMENT_BENCHMARK.md` (new)

**Forbidden scope.**
- Any source edits (bugs → separate fix PR in the owner's track)
- Held-out data
- `configs/wp2_*.json` (Yaropolk's)

**Git workflow.** Branch `feature/nazar-development-benchmark`. Independent PR. Stop before merge. Yaropolk reviews (the B0 part must be signed off by him).

**Work.**
1. Write and commit the configs.
2. Run `nazar_n05_dev573_{da3,unidepth}_<sha7>_01` and `nazar_n05_sel50_{da3,unidepth}_<sha7>_01`.
3. Run `scripts/evaluate_wp2_run.py` (Yaropolk's) on each SLAM stage.
4. Aggregate into one CSV/JSON. Tuning is allowed on dev only and is logged as a numbered list of configs tried.
5. Write the proposed frozen values for IC3: model, `process_res`, thresholds, τ, crop, voxel, keyframe interval, window yes/no.

**Verification.**
- Every run `dirty_worktree=false`, status ok, or failure recorded.
- GT used only in evaluation/oracle.
- Each headline number has sequence, units, alignment mode and hardware.
- Full suite unaffected.
- `git diff --check`.

**Acceptance criteria.**
- [ ] Dev + selection rows for all required methods, or explicit `skipped`/`failed` reasons.
- [ ] Tuning log present.
- [ ] Proposed freeze values listed.
- [ ] No held-out access.

**Required output.** Configs, summaries, plots, `docs/DEVELOPMENT_BENCHMARK.md`, PR.

**Failure and stop conditions.**
- Stop if B0 fails on dev. Record it; do not change the B0 config, because that is Yaropolk's call plus TD-9.
- Stop if a run needs code changes.
- Never read the fr3 data.

**One-prompt execution brief.**
```text
Chunk N-05 (Track N, Nazar): development + selection benchmark and required ablations.
STANDARD RULES: <paste block from §5>. Preconditions: IC2 passed (Y-04 and N-04 merged; configs/wp2_pyslam_development.json
and _selection.json exist on origin/develop); TD-4 decision recorded - verify, else stop.
Branch feature/nazar-development-benchmark. Create configs/pipeline.nazar.{development,selection}.{da3,unidepth}.json
and configs/mapping_comparison.nazar.development.json with pre-registered keyframe intervals, causal_window_frames and
prediction-only confidence quantiles BEFORE running. Commit, then run nazar_n05_dev573_{da3,unidepth}_<sha7>_01 and
nazar_n05_sel50_{da3,unidepth}_<sha7>_01; run scripts/evaluate_wp2_run.py on each SLAM stage. No source edits; never
touch fr3 held-out. Log every tuning attempt (dev only) with its run_id. Aggregate into
results/summaries/nazar_n05_benchmark.{json,csv}, plots results/plots/nazar_n05_*.png, and docs/DEVELOPMENT_BENCHMARK.md
with a "proposed frozen protocol" section (model, process_res, thresholds, tau, crop, voxel, keyframe interval,
window). PR to develop, request Yaropolk review (he signs off the B0 rows), do not merge.
```

---

### N-06 — Held-out benchmark and end-to-end performance evidence

**Objective.** One frozen-protocol pipeline run on fr3/long_office_household (2488 frames):
- methods: B0, B1, P1-raw, P1-global, plus P1-window only if dev improved (EXPERIMENTS §6);
- primary model + best config only;
- a performance table with per-stage p50/p95, wall-clock throughput, peak VRAM/RAM, hardware, resolution and input FPS;
- a real-time verdict.

**Why it is required.** EXPERIMENTS §4.4, §6 held-out column, §7 real-time rule; PLAN WP5 criterion.

**Implementer and attribution.** Nazar runs it. The B0 evaluator is Yaropolk's.

**Prerequisites.**
- IC3 passed: `configs/benchmark_frozen.json` merged and TD-3/TD-5 decided.
- `configs/wp2_pyslam_heldout.json` merged (Y-04).
- GPU + Docker.

**Allowed scope.**
- `configs/pipeline.nazar.heldout.json` (must reference the frozen values only)
- `results/summaries/nazar_n06_*.{json,csv}`, `results/plots/nazar_n06_*.png`
- `docs/HELDOUT_BENCHMARK.md`

**Forbidden scope.**
- Any change to frozen values, any source edit, any post-hoc reruns with new settings

**Git workflow.** Branch `feature/nazar-heldout-benchmark`. Independent PR. Stop before merge. Yaropolk reviews.

**Work.**
1. Commit the config and verify that it equals the frozen values (scripted diff).
2. Run `nazar_n06_heldout2488_<model>_<sha7>_01`.
3. Evaluate B0 with the Y evaluator.
4. Compute performance:
   - SLAM per-frame tracking p50/p95 from the Y export;
   - model inference p50/p95;
   - alignment and fusion times;
   - total wall clock;
   - effective FPS = frames / wall;
   - peak VRAM; peak RAM where measured.
5. Real-time verdict against the 30 Hz input (33.3 ms budget, TD-7): state "offline / not real-time" unless p95 end-to-end fits *and* there is no backlog.

**Verification.**
- Clean run; frozen-config diff empty.
- GT only in evaluation.
- Numbers traceable to `run.json`.
- Full suite unaffected.

**Acceptance criteria.**
- [ ] Held-out rows complete, or a failure recorded honestly.
- [ ] Performance table with hardware/resolution/scope labels.
- [ ] Explicit real-time verdict.
- [ ] Disclosure of `wp2_heldout2488_4484fd7` repeated.

**Required output.** Summaries, plots, `docs/HELDOUT_BENCHMARK.md`, PR.

**Failure and stop conditions.**
- If the run fails: record it, and only rerun under a new run_id after a documented *bug* fix merged via its owner's PR. No parameter changes.
- Never "improve" held-out numbers.

**One-prompt execution brief.**
```text
Chunk N-06 (Track N, Nazar): held-out benchmark with the frozen protocol + end-to-end performance evidence.
STANDARD RULES: <paste block from §5>. Preconditions: IC3 passed (configs/benchmark_frozen.json and
configs/wp2_pyslam_heldout.json on origin/develop; TD-3/TD-5 recorded) - verify, else stop.
Branch feature/nazar-heldout-benchmark. Create configs/pipeline.nazar.heldout.json using ONLY frozen values and prove it
with a scripted diff against benchmark_frozen.json. Commit, then run nazar_n06_heldout2488_<model>_<sha7>_01 once.
Evaluate B0 with scripts/evaluate_wp2_run.py. Build a performance table: per-stage p50/p95 (SLAM tracking from the
all-frame timing export, model inference, alignment, fusion), wall clock, effective FPS = frames/wall, peak VRAM/RAM,
hardware, resolution, 30 Hz input. Give an explicit real-time verdict (default "offline, not real-time" unless p95 fits
33.3 ms with no backlog). No tuning, no source edits; on failure record it and stop. Write
results/summaries/nazar_n06_*.{json,csv}, plots, docs/HELDOUT_BENCHMARK.md (repeat the wp2_heldout2488_4484fd7
disclosure). PR to develop, request Yaropolk review, do not merge.
```

---

## 6. Track Y — Yaropolk chunks

The standard rules block in §5 applies verbatim. Yaropolk's default environment is the macOS arm64 native pySLAM from `docs/WP2_SETUP.md` (`.venv-pyslam`, upstream `96019cf`). If it is unavailable, use the Linux Docker recipe with container `rt-mapping-wp2-yaropolk`.

### Y-01 — All-frame tracking states, causal keyframes and per-frame SLAM timing

**Objective.** The merged WP2 runner writes a normalized, validated per-input-frame export from a real clean run on smoke-200:
- `trajectory_all.csv`: frame_id, timestamp, upstream tracking state, causal pose `T_wc` or empty, `is_keyframe_created`;
- `timing.csv`: per-frame tracking_ms, plus mapping_ms where measurable, otherwise blank with a reason.

**Why it is required.**
- PLAN WP2 ("timestamped poses … timing", "зафіксувати tracking failures").
- EXPERIMENTS §4.1 tracking success, §4.4 SLAM p50/p95.
- Listed as incomplete in PROJECT_STATUS, YULIAN_HANDOFF and INTEGRATION_STATUS.

**Implementer and attribution.** Yaropolk implements; original owner Yaropolk (WP2). Nazar's local assistance (`816b7f4` contract and `UNKNOWN`-state rules; `4484fd7` causal keyframe events) may be used as reference. Any adopted code is credited as "assisted by Nazar".

**Prerequisites.**
- `origin/develop`.
- Native pySLAM environment.
- fr1/xyz data (already used for `_02`/`_03`).
- No GPU.
- Independent of Track N.

**Allowed scope.**
- `src/rt_mapping/slam/smoke.py` (bootstrap hook), `src/rt_mapping/slam/pyslam_export.py`
- `src/rt_mapping/slam/tracking_log.py` (new), `src/rt_mapping/contracts/slam.py` (new)
- `tests/test_slam_tracking_log.py` (new), `tests/test_slam_smoke.py`, `tests/test_import_hygiene_wp2.py` (new)
- `docs/WP2_TRACKING_EXPORT.md` (new), `docs/ARCHITECTURE.md` (SlamExport section only)
- `results/summaries/yaropolk_y01_tracking_smoke200_<sha7>.json`

**Forbidden scope.**
- Upstream pySLAM source/algorithm, `configs/wp2_pyslam_baseline.json` parameters
- `evaluation/trajectory.py` (Yulian's), WP1 files, shared status docs, `tests/test_import_hygiene.py`

**Git workflow.** Branch `feature/yaropolk-all-frame-export`. Independent PR. Stop before merge. Nazar reviews (PLAN WP2 reviewer).

**Work.**
1. Hook per-frame state, the causal pose and keyframe creation through the existing bootstrap injection, without patching upstream files.
2. Time the `track()` call. Measure mapping time only if it is serial and attributable; otherwise leave it blank with a reason.
3. Write the export deterministically (UTF-8/LF, 17 significant digits). Refuse to overwrite.
4. Validate on read-back (row count = frozen frames, monotonic timestamps, valid poses).
5. Clean run `yaropolk_y01_smoke200_<sha7>_01`.
6. Repeat once (`_02`) to report state determinism.

**Verification.**
- New unit tests with a fake SLAM object; full CPU suite.
- Opt-in native test.
- Real clean run with `dirty_worktree=false`.
- The sparse export from the same run still validates.
- `git diff --check`; path/secret scan.

**Acceptance criteria.**
- [ ] 200/200 rows with an explicit state; no interpolated or identity placeholder poses.
- [ ] Keyframe flags are causal events, kept distinct from retained-snapshot membership.
- [ ] Timing has scope labels.
- [ ] Two-run comparison reported.
- [ ] Full suite + CI green.

**Required output.** Code, tests, docs, summary, PR.

**Failure and stop conditions.**
- Stop if the state is unobservable without patching upstream: document it and propose options.
- Stop if export changes tracking behaviour (compare final pose counts with `_02`/`_03`; report any difference).
- Do not fabricate states. `UNKNOWN` with a reason is acceptable.

**One-prompt execution brief.**
```text
Chunk Y-01 (Track Y, Yaropolk): normalized all-frame tracking states, causal keyframes and per-frame SLAM timing.
STANDARD RULES: <paste block from §5>.
Branch feature/yaropolk-all-frame-export from exact origin/develop. Environment: my native macOS pySLAM (.venv-pyslam,
upstream 96019cf) per docs/WP2_SETUP.md; fr1/xyz smoke data already local; no GPU, no installs.
Without modifying upstream pySLAM source or B0 parameters, extend the bootstrap in src/rt_mapping/slam/smoke.py (+ new
slam/tracking_log.py and contracts/slam.py) to write, per frozen input frame: frame_id, timestamp_s, upstream tracking
state, causal pose T_wc (qx,qy,qz,qw) or empty, is_keyframe_created; and timing.csv with tracking_ms (and mapping_ms
only if attributable, else blank + reason). Deterministic serialization, refuse overwrite, read-back validation.
You may consult Nazar's local reference branches feature/nazar-assist-wp2-evaluation (816b7f4) and
feature/nazar-assist-yaropolk-pyslam-independent (4484fd7); adopt selectively and credit as assistance. Do not edit
evaluation/trajectory.py, WP1 files, shared status docs or tests/test_import_hygiene.py (use new
tests/test_import_hygiene_wp2.py). Document in docs/WP2_TRACKING_EXPORT.md and the ARCHITECTURE.md SlamExport section.
From the clean commit run yaropolk_y01_smoke200_<sha7>_01 and _02 (export on), compare states/pose counts, write
results/summaries/yaropolk_y01_tracking_smoke200_<sha7>.json. Full pytest, git diff --check. PR to develop, request
Nazar review, do not merge.
```

---

### Y-02 — Recorded B0 trajectory evaluation and SLAM resource measurement

**Objective.** A CLI that evaluates any finished merged B0 run with Yulian's evaluator:
- Sim(3) ATE/RPE (evaluation-only scale) on the final trajectory;
- a separately labelled retained-keyframe evaluation;
- pose coverage.

A wrapper measures peak RSS, cold start, wall clock and effective FPS of the SLAM child process. Both are recorded on a clean smoke run.

**Why it is required.** PLAN WP2 ("порахувати ATE/RPE"), EXPERIMENTS §4.1, §4.4 (peak RAM, cold start); INTERIM_REVIEW baseline slide.

**Implementer and attribution.** Yaropolk (WP2/WP5 metrics). It reuses `rt_mapping.evaluation.trajectory` (Yulian) unchanged. Nazar's `816b7f4` evaluator may be used as reference (credited if adopted).

**Prerequisites.**
- `origin/develop`; does **not** need Y-01.
- Native environment.
- POSIX `resource.getrusage(RUSAGE_CHILDREN)` (no psutil install).

**Allowed scope.**
- `src/rt_mapping/evaluation/slam_run.py` (new)
- `scripts/evaluate_wp2_run.py`, `scripts/measure_wp2_resources.py` (new)
- `tests/test_wp2_evaluation.py` (new)
- `docs/WP2_EVALUATION.md` (new)
- `results/summaries/yaropolk_y02_*.json`

**Forbidden scope.** `slam/*.py` (Y-01 owns those files in the same wave), `evaluation/trajectory.py`, WP1 files, shared docs.

**Git workflow.** Branch `feature/yaropolk-b0-evaluation`. Independent PR (no stacking on Y-01). Stop before merge. Nazar reviews.

**Work.**
1. Write the evaluator. It reads `run.json`, `input_setup/trajectory/trajectory_final.txt` and optionally `sparse/keyframes.npz`, plus the GT through evaluation code only.
2. Write a derived `run.json` (method B0, `alignment=null`; status `degraded` while states are unknown).
3. Write the resource wrapper. It runs `scripts/run_wp2_pyslam.py` as a child and records `ru_maxrss` (platform units normalized), start-to-first-frame time if observable, and wall clock.
4. Clean run `yaropolk_y02_smoke200_<sha7>_01` under the wrapper, then evaluation `yaropolk_y02_eval_smoke200_<sha7>_01`.

**Verification.**
- Unit tests on synthetic trajectories (exact, noise, Sim(3)).
- Parity of the B0 Sim(3) ATE on retained keyframes against the merged comparison semantics.
- Full suite; `git diff --check`.

**Acceptance criteria.**
- [ ] Recorded Sim(3) ATE/RPE on smoke with an evaluation-only scale label.
- [ ] Peak RSS/wall/FPS with scope labels.
- [ ] Missing telemetry is reported as null with a reason, never 0.
- [ ] Suite + CI green.

**Required output.** Code, tests, docs, summaries, PR.

**Failure and stop conditions.**
- Stop if the evaluator would require changing Yulian's functions. Wrap them, don't modify them.
- Stop if RSS is unavailable on the platform. Report it rather than estimating.

**One-prompt execution brief.**
```text
Chunk Y-02 (Track Y, Yaropolk): recorded B0 trajectory evaluation + SLAM resource measurement.
STANDARD RULES: <paste block from §5>.
Branch feature/yaropolk-b0-evaluation from exact origin/develop (do NOT stack on Y-01). Add
src/rt_mapping/evaluation/slam_run.py + scripts/evaluate_wp2_run.py: read a finished merged B0 run (run.json,
input_setup/trajectory/trajectory_final.txt, optional sparse/keyframes.npz), load TUM GT only in this evaluation code,
call rt_mapping.evaluation.trajectory unchanged for Sim(3) ATE/RPE (label scale as evaluation-only) and a separate
retained-keyframe row; write a derived run with valid run.json (method B0, status degraded while states unknown,
null+reason for missing telemetry). Add scripts/measure_wp2_resources.py: run scripts/run_wp2_pyslam.py as a child and
record peak RSS via resource.getrusage(RUSAGE_CHILDREN) (normalize macOS bytes vs Linux KiB), wall clock, effective
FPS; no psutil install. Do not edit slam/*.py, evaluation/trajectory.py or shared docs. Reference only: Nazar's local
816b7f4 (credit if adopted). Clean runs yaropolk_y02_smoke200_<sha7>_01 (under the wrapper) and
yaropolk_y02_eval_smoke200_<sha7>_01; summaries results/summaries/yaropolk_y02_*.json; docs/WP2_EVALUATION.md.
Tests + full pytest + git diff --check. PR to develop, request Nazar review, do not merge.
```

---

### Y-03 — Tracking success, gap-aware RPE, failure accounting and SLAM latency percentiles

**Objective.** Extend the evaluator to consume the Y-01 all-frame export:
- tracking success = OK / all frozen frames;
- lost/initializing segments;
- RPE pairs that never cross non-OK gaps;
- a failure taxonomy;
- tracking p50/p95 via `rt_mapping.evaluation.timing.summarize_timings`;
- a state timeline plot.

Recorded on the Y-01 smoke run.

**Why it is required.** EXPERIMENTS §4.1 (tracking success), §4.4 (SLAM median/p95); PLAN WP2 failures.

**Implementer and attribution.** Yaropolk (WP2/WP5).

**Prerequisites.** Y-01 and Y-02 merged (same track). The local Y-01 run exists on Yaropolk's machine.

**Allowed scope.**
- `src/rt_mapping/evaluation/slam_run.py`, `scripts/evaluate_wp2_run.py`, `tests/test_wp2_evaluation.py`
- `docs/WP2_EVALUATION.md`
- `results/summaries/yaropolk_y03_*.json`, `results/plots/yaropolk_y03_tracking_states_smoke200.png`

**Forbidden scope.** `slam/*.py` (unless a Y-01 bug, fixed as a separate `fix/yaropolk-*` PR), Yulian/WP1 files, shared docs.

**Git workflow.** Branch `feature/yaropolk-tracking-evaluation`. Independent PR. Stop before merge. Nazar reviews.

**Work.**
1. Implement the metrics. The denominator is named explicitly: frozen associated RGB-depth frames.
2. Evaluate `yaropolk_y01_smoke200_<sha7>_01` into `yaropolk_y03_eval_smoke200_<sha7>_01`.
3. Plot the timeline.

**Verification.** Unit tests (gaps, all-lost, no pairs → null + reason); full suite; determinism (re-evaluating gives byte-identical output).

**Acceptance criteria.**
- [ ] Tracking success with a named denominator.
- [ ] Gap-aware RPE.
- [ ] p50/p95 with warm-up policy stated.
- [ ] Failure table.
- [ ] Byte-identical re-evaluation.

**Required output.** Code, tests, docs, summary, plot, PR.

**Failure and stop conditions.** Stop if the Y-01 export lacks needed fields: fix in a separate PR first. Never impute states.

**One-prompt execution brief.**
```text
Chunk Y-03 (Track Y, Yaropolk): tracking success, gap-aware RPE, failure accounting and SLAM p50/p95.
STANDARD RULES: <paste block from §5>. Preconditions: Y-01 and Y-02 merged into origin/develop; my local run
yaropolk_y01_smoke200_<sha7>_01 exists - verify, else stop.
Branch feature/yaropolk-tracking-evaluation. Extend evaluation/slam_run.py + scripts/evaluate_wp2_run.py to read the
all-frame export: tracking success = OK / all frozen associated frames (name the denominator), lost/initializing
segments, RPE pairs not crossing non-OK gaps, failure taxonomy, tracking-time p50/p95 via
rt_mapping.evaluation.timing.summarize_timings (state warm-up policy). Never impute states; null+reason when undefined.
Evaluate into yaropolk_y03_eval_smoke200_<sha7>_01, write results/summaries/yaropolk_y03_eval_smoke200.json and
results/plots/yaropolk_y03_tracking_states_smoke200.png, update docs/WP2_EVALUATION.md. Unit tests incl. edge cases,
full pytest, re-evaluation byte-identical, git diff --check. PR to develop, request Nazar review, do not merge.
```

---

### Y-04 — Split-manifest support in the WP2 runner + frozen per-split B0 configs

**Objective.** `slam/setup.py` and `scripts/run_wp2_pyslam.py` verify and prepare any frozen split manifest (development, selection, held-out). Three B0 configs differ from `configs/wp2_pyslam_baseline.json` **only** in dataset fields. Preflight passes on dev/selection/held-out data **without running SLAM on held-out**.

**Why it is required.** EXPERIMENTS §6: B0 required on Dev/Selection/Held-out. This unblocks N-05/N-06 (IC2).

**Implementer and attribution.** Yaropolk (WP2).

**Prerequisites.**
- **IC1 passed** (N-01 manifests merged).
- **Permission to download** the fr1/desk, fr2/desk and fr3 archives from the official TUM links in the manifests, onto Yaropolk's machine (~3.7 GB).
- Native environment.

**Allowed scope.**
- `src/rt_mapping/slam/setup.py`, `scripts/run_wp2_pyslam.py`, `scripts/prepare_wp2_baseline.py`
- `configs/wp2_pyslam_{development,selection,heldout}.json` (new)
- `tests/test_wp2_setup.py`
- `docs/WP2_SETUP.md`
- `results/summaries/yaropolk_y04_preflight.json`

**Forbidden scope.**
- B0 algorithm parameters
- `data/manifests/*` and `data/manifest.py` (Nazar's; use the API read-only)
- SLAM runs on held-out
- shared docs

**Git workflow.** Branch `feature/yaropolk-split-support`. Independent PR. Stop before merge. Nazar reviews.

**Work.**
1. Generalize verification. Keep the C2 rebuild path for smoke, and for split manifests use `build_tum_split_manifest` or the per-file SHA-256 check.
2. Add "all frames of split" support (e.g. `--frames 0` = all, documented).
3. Make the run-ID default sequence-neutral.
4. Write the configs, plus a test that asserts that the non-dataset fields equal the baseline config.
5. Run preflight only (`prepare` + data verification) on the three splits.

**Verification.**
- Unit tests for both manifest kinds, plus negative tests (hash mismatch, wrong split).
- Full suite.
- Preflight summaries.
- Config-diff test.
- `git diff --check`.

**Acceptance criteria.**
- [ ] Smoke behaviour unchanged (existing tests pass).
- [ ] Three configs added; diff limited to dataset fields.
- [ ] Preflight ok on 3 splits.
- [ ] Zero SLAM frames processed on held-out.

**Required output.** Code, configs, tests, docs, summary, PR.

**Failure and stop conditions.**
- Stop if a manifest schema change is needed: ask Nazar, don't edit `data/`.
- Stop if the download is not permitted.
- Stop if any B0 parameter would change.

**One-prompt execution brief.**
```text
Chunk Y-04 (Track Y, Yaropolk): split-manifest support in the WP2 runner + frozen per-split B0 configs.
STANDARD RULES: <paste block from §5>. Preconditions: IC1 passed - data/manifests/tum_fr1_desk_development.json,
tum_fr2_desk_selection50.json, tum_fr3_long_office_heldout.json on origin/develop - verify, else stop. This prompt allows
downloading those three official TUM archives (URLs inside the manifests) after asking me once.
Branch feature/yaropolk-split-support. Generalize slam/setup.py dataset verification to accept split manifests (use the
merged rt_mapping.data.manifest API read-only; keep smoke behaviour identical), allow "all frames of the split", make
default run IDs sequence-neutral. Add configs/wp2_pyslam_{development,selection,heldout}.json that differ from
configs/wp2_pyslam_baseline.json only in dataset fields, with a test asserting that. Do not change B0 parameters or
data/ files. Run preflight/prepare only on the three splits (NO SLAM on held-out) and write
results/summaries/yaropolk_y04_preflight.json; document in docs/WP2_SETUP.md. Tests + full pytest + git diff --check.
PR to develop, request Nazar review, do not merge.
```

---

### Y-05 — B0 development/selection runs, repeatability and wider-sequence failure analysis

**Objective.**
- Clean B0 runs with all-frame export on dev-573 (three repeats with the same seed) and selection-50.
- Evaluation via Y-02/Y-03.
- A wider-sequence failure analysis (tracking loss, initialization), with causes labelled *гіпотеза* unless proven.

**Why it is required.** EXPERIMENTS §6 B0 on Dev/Selection; §6 note on repeats; PLAN WP2 "зафіксувати tracking failures". It also supplies the second-platform B0 for the final table.

**Implementer and attribution.** Yaropolk (WP2/WP5).

**Prerequisites.** IC2 passed (Y-04 merged). Data downloaded (Y-04). Native environment.

**Allowed scope.**
- `results/summaries/yaropolk_y05_*.{json,csv}`, `results/plots/yaropolk_y05_*.png`
- `docs/WP2_BENCHMARK.md` (new)

**Forbidden scope.**
- Source edits (bugs → separate `fix/yaropolk-*` PR)
- B0 parameter changes without TD-9
- Held-out runs

**Git workflow.** Branch `feature/yaropolk-b0-development`. Independent PR. Stop before merge. Nazar reviews.

**Work.**
1. Run `yaropolk_y05_dev573_<sha7>_{01,02,03}` and `yaropolk_y05_sel50_<sha7>_01`.
2. Evaluate them.
3. Report mean ± std across repeats.
4. Write a failure table with frame ranges and hypotheses.
5. Compare with Nazar's committed smoke B0 numbers (N-02) as a cross-platform note.

**Verification.** All runs `dirty_worktree=false`; evaluation reproducible; GT only in evaluation.

**Acceptance criteria.**
- [ ] Dev ×3 and selection ×1 recorded, including failed runs.
- [ ] Tracking success, Sim(3) ATE/RPE, p50/p95 and peak RSS per run.
- [ ] Failure analysis.
- [ ] No parameter change.

**Required output.** Summaries, plots, `docs/WP2_BENCHMARK.md`, PR. If B0 cannot track a split, add a blocker/decision request for TD-9.

**Failure and stop conditions.** Stop if B0 cannot initialize on selection-50: record it and do not extend frames. Do not retune ORB/thresholds.

**One-prompt execution brief.**
```text
Chunk Y-05 (Track Y, Yaropolk): B0 development/selection runs, repeatability and failure analysis.
STANDARD RULES: <paste block from §5>. Preconditions: IC2 passed (Y-04 merged; configs/wp2_pyslam_development.json and
_selection.json on origin/develop); dev/selection data local - verify, else stop.
Branch feature/yaropolk-b0-development. From a clean commit run yaropolk_y05_dev573_<sha7>_01/_02/_03 (same seed) and
yaropolk_y05_sel50_<sha7>_01 with the all-frame export; evaluate each with scripts/evaluate_wp2_run.py. Report tracking
success (named denominator), Sim(3) ATE/RPE (evaluation-only scale), tracking p50/p95, peak RSS, mean +- std over
repeats; failure table with frame ranges, causes labelled "гіпотеза" unless proven. Add a cross-platform note vs the
committed N-02 summary if merged (never use Nazar's ignored runs). No source edits, no B0 parameter changes, no
held-out. Write results/summaries/yaropolk_y05_*.{json,csv}, plots, docs/WP2_BENCHMARK.md. PR to develop, request
Nazar review, do not merge.
```

---

### Y-06 — Held-out B0 with the frozen config

**Objective.** One clean B0 run on fr3 held-out (2488 frames) with `configs/wp2_pyslam_heldout.json` exactly as frozen at IC3, evaluated with the merged evaluator. It serves as the second-platform B0 row for the final table.

**Why it is required.** EXPERIMENTS §6 B0 held-out required; independent reproduction across platforms.

**Implementer and attribution.** Yaropolk (WP2).

**Prerequisites.** IC3 passed (frozen protocol merged, TD-5 decided). Held-out data local.

**Allowed scope.**
- `results/summaries/yaropolk_y06_*.{json,csv}`, `results/plots/yaropolk_y06_*.png`
- `docs/WP2_BENCHMARK.md` (held-out section)

**Forbidden scope.** Any config/source change; reruns with changed settings.

**Git workflow.** Branch `feature/yaropolk-b0-heldout`. Independent PR. Stop before merge. Nazar reviews.

**Work.**
1. Verify the config hash equals the frozen one.
2. Run `yaropolk_y06_heldout2488_<sha7>_01` once.
3. Evaluate it.
4. Write the summary, repeating the `wp2_heldout2488_4484fd7` disclosure.

**Verification.** Clean run; config-hash check; GT only in evaluation.

**Acceptance criteria.**
- [ ] Run recorded (ok, degraded or failed) with full metrics or a failure reason.
- [ ] No tuning; disclosure present.

**Required output.** Summary, plot, doc section, PR.

**Failure and stop conditions.** On failure, record it and stop. A rerun is allowed only after a documented bug fix merged via a separate PR, under a new run_id.

**One-prompt execution brief.**
```text
Chunk Y-06 (Track Y, Yaropolk): held-out B0 with the frozen config.
STANDARD RULES: <paste block from §5>. Preconditions: IC3 passed (frozen protocol + configs/wp2_pyslam_heldout.json on
origin/develop; TD-5 recorded); fr3 data local - verify, else stop.
Branch feature/yaropolk-b0-heldout. Verify the held-out config hash equals the frozen one, then from a clean commit run
yaropolk_y06_heldout2488_<sha7>_01 exactly once and evaluate it with scripts/evaluate_wp2_run.py. No config/source
changes, no tuning; on failure record it and stop. Write results/summaries/yaropolk_y06_*.{json,csv}, a tracking-state
plot, and the held-out section of docs/WP2_BENCHMARK.md (repeat the wp2_heldout2488_4484fd7 disclosure). PR to develop,
request Nazar review, do not merge.
```

---

## 7. Integration checkpoints

### IC1 — Contracts and inputs ready

- **Must be merged:** N-01, N-03, Y-01, Y-02 (Y-03 and N-02 desirable but not blocking).
- **Tests green:** full CPU suite on the merged `develop`; CI on the merge commit.
- **Artifacts that must exist (committed):**
  - 4 split manifests;
  - `nazar_n03_selection50_<sha7>_scorecard.json`;
  - `yaropolk_y01_tracking_smoke200_<sha7>.json`;
  - `yaropolk_y02_*.json`;
  - the SlamExport contract in ARCHITECTURE.md.
- **Integration performed by:** Nazar, in one docs-only PR `feature/nazar-ic1-status`. It updates `docs/PROJECT_STATUS.md` and `docs/INTEGRATION_STATUS.md`, using Yaropolk's PR-body status rows verbatim. Yaropolk reviews.
- **Interface contract handed over:**
  - N → Y: manifest JSON schema + `rt_mapping.data.manifest` split API (read-only for Y).
  - Y → N: `contracts/slam.py` CSV schema + `scripts/evaluate_wp2_run.py` CLI (read-only for N).
- **If one track is blocked:**
  - Y blocked on Y-01 → IC1 proceeds with Y-02, and Y-04 still starts. Tracking success then becomes `null` with a reason until Y-01 lands.
  - N blocked on N-03 → Y-04 is unaffected (it needs only N-01).
- **Independent work meanwhile:** N continues N-02/N-04 prep; Y continues Y-03.

### IC2 — Development benchmark inputs ready

- **Must be merged:** Y-04 and N-04. TD-4 recorded in `docs/DEVELOPMENT_BENCHMARK.md` (planned, created by N-05) or the PR thread.
- **Tests green:** full suite.
- **Artifacts:** `configs/wp2_pyslam_{development,selection,heldout}.json`, `yaropolk_y04_preflight.json`, `nazar_n04_*.json`.
- **Integration performed by:** Nazar (status docs PR, Yaropolk review).
- **If Y-04 is blocked:** N-05 cannot run B0/P1 on dev. Fallback: N runs model-only dev50/selection50 ablations and waits. Y documents the blocker. No N edits to `slam/`.
- **If N-04 is blocked:** Y-05 proceeds unaffected.

### IC3 — Protocol freeze (before any held-out run)

- **Must be merged:** N-05, Y-05, and the freeze PR `feature/nazar-benchmark-freeze`. The freeze PR is written by Nazar and approved by Yaropolk. It adds:
  - `configs/benchmark_frozen.json`: model and checkpoint, `process_res`/`resolution_level`, alignment thresholds, voxel, τ, crop, keyframe interval, window yes/no, confidence threshold or none, WP2 held-out config hash;
  - `docs/BENCHMARK_PROTOCOL.md`;
  - the EXPERIMENTS.md freeze section;
  - the ADR001 decision (TD-3).
- **Decisions recorded:** TD-3, TD-5, TD-9 (if raised).
- **Rule:** the held-out runs in N-06/Y-06 must record a `git_commit` that contains the freeze commit.
- **If one track is blocked:** the freeze can proceed with the B0 config as merged. Y-06 can run later without affecting N-06, and vice versa.

### Final integration/submission checkpoint

- **Must be merged:** N-06, Y-06, F-N1, F-N2, F-Y1, F-Y2.
- **Tests green:** full suite + CI on `develop`; fresh-clone check (F-Y2).
- **Shared files finally updated** (single editor, Nazar in F-N1): README.md, CLAUDE.md, PROJECT_STATUS.md, INTEGRATION_STATUS.md, `scripts/README.md`, `configs/README.md`, `results/README.md`.
- **Release:** F-0, a `develop → main` PR plus tag after both approve (tagging requires explicit permission).
- **If one track is blocked:** submit with the blocked item listed as a documented failure (Plan B in PLAN §6 is an accepted academic outcome).

---

## 8. Team decisions

| ID | Decision | Who | Latest safe point | Default if undecided |
|---|---|---|---|---|
| TD-1 | Accept the frozen split freeze (fr1/desk dev, fr2/desk selection50, fr3 held-out, dev spike50) | Nazar + Yaropolk (Yulian informed) | N-01 merge | Keep EXPERIMENTS §2 sequences (no change) |
| TD-2 | Accept assisted work: (a) which of Nazar's local WP2 assistance pieces Yaropolk adopts (credited as assistance); (b) confirm Nazar's WP3 foundation `fd73d56` and the other superseded branches are **not** merged; (c) Nazar may submit focused WP3/WP4 defect fixes with Yulian's review | (a) Yaropolk; (b)(c) team | (a) Y-01/Y-02 PRs; (b)(c) IC1 | Nothing adopted silently; superseded branches stay local |
| TD-3 | Primary dense model DA3 vs UniDepth (ADR001 proposes UniDepth: better weighted score, but worse selection RMSE, more VRAM, CC-BY-NC-4.0 code) | Team | IC3 (dev runs both) | Undecided blocks N-06 |
| TD-4 | Optional ablations: ICP (not implemented → propose out of scope per PLAN §6 Plan B); P2 out; P1-window on held-out only if dev improves; confidence ablation only for UniDepth | Team | IC2 (before dev pre-registration) | ICP and P2 out of scope; matrix rules as written |
| TD-5 | Held-out use/disclosure: confirm fr3 remains valid held-out; disclose the failed superseded-runner B0 attempt `wp2_heldout2488_4484fd7`; one-shot policy with bug-fix-only reruns | Team | IC3 | Disclose; one-shot policy |
| TD-6 | Submission scope, interim/final dates, presentation time limit, slide format, demo video storage (outside Git), release tag name, code license | Team | Ask now; binding by the final checkpoint | Proposed tag `v1.0.0`; video outside Git |
| TD-7 | Real-time framing: input rate 30 Hz (33.3 ms budget) and wording "offline / near-real-time" | Team | F-N1 | "Offline; not real-time" unless measured otherwise |
| TD-8 | Yulian's role in the final phase: reviewer for WP3/WP4 fixes and a speaker (INTERIM_REVIEW requires all members to speak) | Team incl. Yulian | Final checkpoint | Yulian reviews and speaks to WP3/WP4 |
| TD-9 | Only if B0 fails on wider sequences: change the baseline config (e.g. relocalization), which would require new run IDs and a decision record | Team | IC3 | Keep B0 unchanged; report the failure |

---

## 9. Final integration and submission chunks

These run after N-06 and Y-06 are merged. The order is: F-N1 ‖ F-Y1, then F-N2 ‖ F-Y2, then F-0. File sets are disjoint.

### F-N1 (Nazar) — Final results table, limitations, reproducibility guide, status docs

- **Objective:** one complete experiment table and the final docs.
- **Scope:**
  - `docs/FINAL_RESULTS.md` (new)
  - `docs/REPRODUCE.md` (new)
  - `docs/PROJECT_STATUS.md`, `docs/INTEGRATION_STATUS.md`
  - `README.md`, `CLAUDE.md`
  - `scripts/README.md`, `configs/README.md`, `results/README.md`
  - `docs/MODEL_SELECTION.md` §7 outcome
  - `docs/EXPERIMENTS.md` results pointer
  - `results/summaries/final_results.{json,csv}` (new)
- **Work:**
  1. Aggregate **committed** summaries only (N-02…N-06, Y-02…Y-06, Yulian's smoke). Show both B0 platform rows with labels.
  2. Write the limitations section: map reference approximation, retained-keyframe vs all-frame, single seed, GPU nondeterminism, license, no real-time claim unless proven.
  3. Write the reproducibility guide: fresh clone → CPU tests → smoke pipeline → benchmark commands.
- **Verification:** every number traced to a `run_id` and summary; link check; `git diff --check`.
- **Branch:** `feature/nazar-final-results`. Yaropolk reviews.
- **One-prompt brief:**
  ```text
  Chunk F-N1 (Nazar): final results table, limitations, reproducibility guide and status docs.
  STANDARD RULES: <paste block from §5>. Preconditions: N-06 and Y-06 merged - verify, else stop.
  Branch feature/nazar-final-results. Using ONLY committed results/summaries (cite run_ids), build
  results/summaries/final_results.{json,csv} and docs/FINAL_RESULTS.md (trajectory, depth, map, performance; units,
  alignment mode, hardware, GT rule; both B0 platform rows labelled). Write limitations and an explicit real-time
  verdict (TD-7). Write docs/REPRODUCE.md. Update PROJECT_STATUS.md, INTEGRATION_STATUS.md, README.md, CLAUDE.md,
  scripts/configs/results READMEs and the MODEL_SELECTION.md §7 outcome. Do not touch Yaropolk's docs or slides files.
  Link check + git diff --check. PR to develop, request Yaropolk review, do not merge.
  ```

### F-Y1 (Yaropolk) — Presentation, contribution table, rehearsal

- **Objective:** slides and a contribution table backed by evidence.
- **Scope:**
  - `docs/PRESENTATION_OUTLINE.md` (new)
  - `docs/CONTRIBUTIONS.md` (new; all three members; each row → PR/commit/run; assisted work labelled as assistance with the original owner preserved)
  - `docs/INTERIM_REVIEW.md` checklist
  - slide file in the format chosen in TD-6, stored outside Git or as a small PDF
- **Work:**
  1. Slides follow the INTERIM_REVIEW §2 structure.
  2. All numbers are copied from committed summaries.
  3. Run two timed rehearsals with a margin of at least 60 s.
- **Verification:** each slide number traced; rehearsal times recorded.
- **Branch:** `feature/yaropolk-presentation`. Nazar reviews.
- **One-prompt brief:**
  ```text
  Chunk F-Y1 (Yaropolk): presentation outline, contribution table, rehearsal record.
  STANDARD RULES: <paste block from §5>. Preconditions: N-06 and Y-06 merged; TD-6 slide format/time limit known -
  verify, else stop and ask.
  Branch feature/yaropolk-presentation. Write docs/PRESENTATION_OUTLINE.md (INTERIM_REVIEW §2 structure; every number
  copied from a committed summary with its run_id; oracle B1 labelled; Sim(3) ATE not presented as metric scale; no
  real-time claim beyond F-N1/N-06 evidence) and docs/CONTRIBUTIONS.md (Nazar, Yaropolk, Yulian; each row links
  PR/commit/run; assisted work labelled with original owner). Update docs/INTERIM_REVIEW.md checklist and record two
  timed rehearsals. Do not edit README/PROJECT_STATUS/FINAL_RESULTS. PR to develop, request Nazar review, do not merge.
  ```

### F-N2 (Nazar) — Demo capture

- **Objective:** a prerecorded demo of the fused map and trajectory from the dev or held-out run (TD-6 storage), plus a small committed preview.
- **Scope:** `scripts/render_demo.py` (new; matplotlib/Pillow only, no installs), `docs/DEMO.md` (new), `results/plots/nazar_demo_*.png` (<1 MB). The video stays outside Git; its SHA-256 is recorded.
- **Verification:** the render is reproducible from the run ID; hashes recorded; the demo labels sequence, method and "offline".
- **Branch:** `feature/nazar-demo`. Yaropolk reviews.
- **One-prompt brief:**
  ```text
  Chunk F-N2 (Nazar): prerecorded demo capture.
  STANDARD RULES: <paste block from §5>. Preconditions: N-05 or N-06 merged; TD-6 demo storage decided - verify.
  Branch feature/nazar-demo. Add scripts/render_demo.py (thin CLI; matplotlib/Pillow only, no installs) that renders the
  fused cloud + trajectory of one of MY committed-summary runs into frames/GIF; store the video outside Git, record its
  SHA-256 and command in docs/DEMO.md; commit only small previews results/plots/nazar_demo_*.png (<1 MB). Label sequence,
  method, "offline". git diff --check. PR to develop, request Yaropolk review, do not merge.
  ```

### F-Y2 (Yaropolk) — Fresh-clone reproduction, CI, assignment audit

- **Objective:** an independent fresh-clone check on macOS and an audit against the requirements.
- **Scope:**
  - `docs/SUBMISSION_AUDIT.md` (new; PROJECT_BRIEF expected results, PLAN §8 DoD, INTERIM_REVIEW rubric/48-hour checklist → evidence or gap)
  - `.github/workflows/tests.yml` only if a verified gap exists
  - `tests/test_import_hygiene.py` consolidation (merging the `_wp1`/`_wp2` files), if desired
- **Work:**
  1. Fresh clone; `pip install -e ".[dev,plots,filtering]"` in a new venv (ask first).
  2. Run `pytest`, `run_alignment_smoke.py --plot` and `run_comparison_smoke.py --plot`.
  3. Execute every CPU command in `docs/REPRODUCE.md`.
- **Branch:** `feature/yaropolk-submission-audit`. Nazar reviews.
- **One-prompt brief:**
  ```text
  Chunk F-Y2 (Yaropolk): fresh-clone reproduction and assignment audit.
  STANDARD RULES: <paste block from §5>. This prompt allows creating a NEW venv and pip-installing the project extras in a
  fresh clone after asking me once. Preconditions: F-N1 merged - verify.
  Fresh-clone origin/develop into a new directory; run pytest, run_alignment_smoke.py --plot, run_comparison_smoke.py
  --plot and every CPU command in docs/REPRODUCE.md; record exact outputs. Branch feature/yaropolk-submission-audit: write
  docs/SUBMISSION_AUDIT.md mapping PROJECT_BRIEF expected results, PLAN §8 DoD and INTERIM_REVIEW rubric/48h checklist to
  evidence or gaps. Touch .github/workflows/tests.yml or consolidate tests/test_import_hygiene*.py only for a verified
  gap. git diff --check. PR to develop, request Nazar review, do not merge.
  ```

### F-0 (Nazar, integration gate) — Release

- **Scope:** a `develop → main` PR. After both approvals and explicit permission, tag (name from TD-6) on `main`.
- **Gate:** all final chunks merged, CI green, F-Y2 audit has no open mandatory gaps (or they are listed as known failures).
- **One-prompt brief:**
  ```text
  Chunk F-0 (Nazar, integration gate): release.
  STANDARD RULES: <paste block from §5> EXCEPT: this gate may open a develop->main PR and, only after Nazar and Yaropolk
  approvals and my explicit confirmation in this session, merge it and create the TD-6 tag on main. Verify all final
  chunks merged, CI green on develop, SUBMISSION_AUDIT has no open mandatory gap. Never force-push. Report the tag SHA.
  ```

---

## 10. Execution board

| Chunk | Person | Wave | Status | Dependencies | Effort | Branch | Output / PR | Parallel with | Review by |
|---|---|---|---|---|---|---|---|---|---|
| C1–C5, WP2 sparse, WP3/WP4 smoke | Nazar / Yaropolk / Yulian | — | DONE | — | — | merged | PR #1–#8 | — | done |
| WP3 foundation `fd73d56`, alt pySLAM runner, wp4/5/6 assists, local `main` | Nazar (assist) | — | SUPERSEDED | — | — | local only | not merged | — | — |
| N-01 | Nazar | 1 | READY | `origin/develop` | 1 h | `feature/nazar-frozen-splits` | manifests PR | Y-01, Y-02 | Yaropolk |
| N-02 | Nazar | 2 | READY (download permission) | `origin/develop` | 2–4 h (Docker build + 7 min run) | `feature/nazar-pipeline-reproduction` | repro summary PR | Y-01, Y-02, Y-03 | Yaropolk |
| N-03 | Nazar | 2 | BLOCKED | N-01 merged | 2 h incl. GPU | `feature/nazar-unidepth-selection` | UniDepth/selection PR | Y-02, Y-03 | Yaropolk (+Yulian optional) |
| IC1 | Nazar integrates | — | BLOCKED | N-01, N-03, Y-01, Y-02 | 0.5 h | `feature/nazar-ic1-status` | status PR | Y-03 | Yaropolk |
| N-04 | Nazar | 3 | BLOCKED | N-03 merged, N-02 run | 2 h | `feature/nazar-model-agnostic-pipeline` | pipeline-stage PR | Y-04 | Yaropolk |
| N-05 | Nazar | 4 | BLOCKED | IC2, TD-4 | 3–5 h GPU | `feature/nazar-development-benchmark` | dev benchmark PR | Y-05 | Yaropolk |
| IC3 freeze | Nazar writes, both approve | — | DECISION REQUIRED | N-05, Y-05, TD-3, TD-5 | 1 h | `feature/nazar-benchmark-freeze` | freeze PR | — | Yaropolk |
| N-06 | Nazar | 5 | DECISION REQUIRED | IC3 | 3–5 h GPU | `feature/nazar-heldout-benchmark` | held-out PR | Y-06 | Yaropolk |
| Y-01 | Yaropolk | 1 | READY | `origin/develop` | 2–3 h incl. 2 runs | `feature/yaropolk-all-frame-export` | export PR | N-01, N-02 | Nazar |
| Y-02 | Yaropolk | 2 | READY | `origin/develop` | 1.5–2 h | `feature/yaropolk-b0-evaluation` | evaluator PR | N-01, N-02, N-03 | Nazar |
| Y-03 | Yaropolk | 2 | BLOCKED | Y-01, Y-02 merged | 1.5 h | `feature/yaropolk-tracking-evaluation` | tracking-eval PR | N-02, N-03 | Nazar |
| Y-04 | Yaropolk | 3 | BLOCKED | IC1 (N-01 merged), download permission | 2 h + download | `feature/yaropolk-split-support` | split-support PR | N-04 | Nazar |
| Y-05 | Yaropolk | 4 | BLOCKED | IC2 | 3–4 h runs | `feature/yaropolk-b0-development` | B0 dev PR | N-05 | Nazar |
| Y-06 | Yaropolk | 5 | DECISION REQUIRED | IC3 | 2–3 h run | `feature/yaropolk-b0-heldout` | B0 held-out PR | N-06 | Nazar |
| F-N1 | Nazar | final | BLOCKED | N-06, Y-06 | 2 h | `feature/nazar-final-results` | final docs PR | F-Y1 | Yaropolk |
| F-Y1 | Yaropolk | final | BLOCKED | N-06, Y-06, TD-6 | 2–3 h | `feature/yaropolk-presentation` | slides/contributions PR | F-N1 | Nazar |
| F-N2 | Nazar | final | BLOCKED | N-05 or N-06, TD-6 | 1.5 h | `feature/nazar-demo` | demo PR | F-Y2 | Yaropolk |
| F-Y2 | Yaropolk | final | BLOCKED | F-N1 | 1.5 h | `feature/yaropolk-submission-audit` | audit PR | F-N2 | Nazar |
| F-0 | Nazar (gate) | final | BLOCKED | all final chunks, approvals | 0.5 h | `develop → main` | release PR + tag | — | Yaropolk |

**Independence check (performed for this plan):**

- **Pre-IC1 chunks** (N-01, N-02, N-03, Y-01, Y-02, Y-03) list only `origin/develop` or same-track predecessors as dependencies.
- **File sets of parallel pairs are disjoint:**
  - N-01 vs Y-01/Y-02: `data/…` vs `slam/…`, `evaluation/slam_run.py`.
  - N-02/N-03 vs Y-02/Y-03: new N configs and WP1 code vs Y evaluation files.
  - N-04 vs Y-04: WP1 scripts and N configs vs `slam/setup.py` and `configs/wp2_*`.
  - N-05/N-06 vs Y-05/Y-06: separate summaries and docs only.
- **Shared status docs** are edited only in Nazar's checkpoint PRs and in F-N1.
- **Shared test file:** `tests/test_import_hygiene.py` is not edited by either person before F-Y2.

---

## 11. Recommended starting pair

- **Nazar starts with N-01:** frozen development/selection/held-out manifests on `develop`.
- **Yaropolk starts with Y-01:** all-frame tracking states, causal keyframes and per-frame SLAM timing.

Why this pair gives the highest immediate value:

1. **Both sit on the critical path.**
   - N-01 is the only input Y-04 needs. Merging it early starts the dependency chain for every wider B0/P1 run (IC1 → Y-04 → IC2 → N-05 → IC3 → held-out).
   - Y-01 closes the largest open WP2 gap that every document lists (PROJECT_STATUS, YULIAN_HANDOFF, INTEGRATION_STATUS). It feeds tracking success and SLAM latency into every later benchmark.
2. **They are fully independent.**
   - N-01 touches only `data/manifests/`, `data/manifest.py`, `scripts/freeze_tum_split.py`, one new test and `docs/DATASET_FREEZE.md`.
   - Y-01 touches only `slam/`, `contracts/slam.py`, its own tests and docs, and the ARCHITECTURE.md SlamExport section.
   - Neither reads the other's outputs, and each runs on its own machine and data.
3. **Review never stalls either person.**
   - N-01 is small and quick for Yaropolk to review; its review also settles TD-1. While it is in review, Nazar moves on to N-02.
   - While Y-01 is in review, Yaropolk moves on to Y-02, which deliberately does not depend on Y-01.
