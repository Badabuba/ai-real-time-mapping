# Two-person completion plan

- **Audit date:** 2026-10-25
- **Audited base:** `origin/develop` = `7b4b26e2e0f052ca950b0d1259f8594229f25036` (Merge PR #8). `origin/main` points to the same commit.
- **Prepared by:** Nazar (with Claude Code).
- **Executors:** Nazar (Track N) and Yaropolk (Track Y). Yulian's merged WP3/WP4 implementation is a shared, stable, read-only component.
- **Scope:** finish the documented WP0–WP6 project (PLAN.md §2, EXPERIMENTS.md §6, INTERIM_REVIEW.md). No new phase, no P2/semantics, no new alignment implementation.
- **Decisions:** all technical decisions are resolved in §8 from repository evidence.
- **No administrative gates:** no chunk waits for deadlines, presentation length, team availability or owner review.
- **Attribution:** original WP ownership is preserved. Work done in another person's WP is labelled "assistance".

**Project definition of done.** The project is complete for the current version when all of the following hold:

1. A tagged commit on `main` reproduces the B0 baseline and the P1 pipeline from a fresh clone, using documented commands.
2. The pipeline has run on the frozen development, selection and held-out splits with one frozen protocol.
3. The results table reports trajectory, depth, map and performance metrics with units, alignment mode, hardware and the GT-use rule.
4. The required ablations are reported, or explicitly skipped with a reason.
5. Every real-time statement is backed by measured p95 latency and throughput, or the system is labelled offline.
6. A demo capture, presentation materials and an evidence-linked contribution table exist.

---

## 1. Current verified state

Verification performed for this plan:
- `git fetch --all --prune`;
- `gh pr list --state all`: 8 PRs, all merged, none open before this one;
- `gh run list`: the CPU-correctness workflow is green on `7b4b26e` for `develop` and `main` (run `40191430426`);
- local CPU suite on a clean `origin/develop` worktree: **472 passed, 1 skipped** (30.6 s, Windows, Python 3.11 `.venv`);
- branch contents checked with `git log`/`git diff --stat` against their merge bases, plus `git merge-tree` conflict probes.

No GPU, SLAM or Docker work was run for this audit.

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
| Linux/Docker pySLAM runtime recipe | `containers/wp2.Dockerfile`, `scripts/build_wp2_linux_native.py`, `docs/WP2_LINUX_CONTAINER.md`; PR #8 | Yulian (assistance on the WP2 runtime) |
| Trajectory and map evaluators (+ evo parity) | `src/rt_mapping/evaluation/{trajectory,map_geometry,oracle}.py`; `results/summaries/wp3_wp4_yulian_real_evo_parity.json` | Yulian |
| CPU CI (Ubuntu/Windows × Python 3.11/3.12) | `.github/workflows/tests.yml` | Yulian |

### 1.2 Merged but insufficiently validated

- **B0 is only on smoke fr1/xyz.** The pose fraction is not tracking success. Historical macOS runs `_02`/`_03` have `dirty_worktree=true`. The merged runner records neither per-frame tracking states nor stage timing (`slam/pyslam_export.py` limitations: "Not all-frame tracking observations or timing").
- **Trajectory metrics cover retained keyframes only.** They come from the comparison run (`comparison_run.py`: "retained keyframes, not all-frame trajectory/tracking evaluation"). `evaluation/trajectory.py` has no gap or tracking-state handling.
- **The one-config pipeline has been reproduced on one machine only** (Yulian's RTX 3070 Ti + Docker).
- **Smoke used DA3 at `process_res` 384** (C5 default). The model-selection spike used 504.
- **Smoke ablations show tradeoffs only.** P1-global does not beat P1-raw on map Chamfer. Confidence ablation is skipped because DA3 returns no confidence. `alignment/causal.py` (P1-window) has never run on real data.
- **The WP2 dataset preflight is smoke-only.** `slam/setup.py` rebuilds the manifest with `build_tum_manifest(... smoke_frames=manifest["splits"]["smoke"]...)` and cannot verify the wider split manifests.
- **Decisions D001–D004 and D008 are marked "proposed"** in PROJECT_STATUS §7. §8 of this plan resolves the remaining technical choices.

### 1.3 Complete locally but unmerged (not on any remote)

| Local branch @ commit | Useful content | Fate in this plan |
|---|---|---|
| `feature/nazar-wp1-integration` @ `5e542d7` (base `ce095fa`) | Four frozen split manifests + `scripts/freeze_tum_split.py`; UniDepth V2 adapter; paired selection protocol/scorecard; ADR001 (UniDepth primary, DA3 fallback); clean selection50 re-run evidence `wp1_integrated_selection50_{da3,unidepth}_463b446` | Port selectively onto `develop` in **N-01** (splits) and **N-03** (UniDepth/selection). Code files apply without conflicts; only CLAUDE.md, README.md, PROJECT_STATUS.md and `tests/test_import_hygiene.py` conflict, and those are not ported. |
| `feature/nazar-depth-ablations` @ `047992e` | DA3 resolution 384 vs 504 and UniDepth confidence-quantile depth-only ablations on dev50 | Port the evidence in **N-04**. The old confidence mapping (`1/(1+err)`) is rank-equivalent to the newer `-err` convention; re-verify retained counts. |
| `feature/nazar-assist-wp2-evaluation` @ `816b7f4` | Nazar's *assistance* in Yaropolk's WP2: a normalized all-frame CSV contract with truthful `UNKNOWN` states, and an evaluator CLI | **Reference only** for Y-01/Y-02/Y-03 (D-2). It conflicts with `develop` in `slam/smoke.py`, `tests/test_wp2_setup.py` and `tests/test_import_hygiene.py`, and overlaps Yulian's `evaluation/trajectory.py`. |

Local ignored runs on Nazar's machine (`results/runs/`, never committed): the WP1 selection/dev50 runs listed in `results/summaries/wp1_integration_verification_20261024.json` on the branch above; `c5_*`; and alternative-runner `wp2_*_4484fd7` runs (§1.5). Under the independence rules, these may be cited only through committed summaries.

### 1.4 Superseded work (never merged)

| Ref | Why superseded |
|---|---|
| local `main` @ `ed374e0` (ahead 45 / behind 14 of `origin/main`) | Old local consolidation; `origin/main` = `origin/develop`. Never push or merge it. |
| `feature/nazar-assist-wp3-alignment-foundation` @ `fd73d56` | Synthetic alignment foundation, superseded by Yulian's merged `alignment/` (PR #7/#8). No replacement WP3 code. |
| `feature/nazar-assist-yaropolk-pyslam-independent` @ `f569efe`, `…-pyslam` @ `30a3cd4`, `…-trajectory` @ `30a3cd4`, `…-trajectory-independent` @ `7e8b135` | Alternative pySLAM v2.2.1 Docker runner and contracts. The merged baseline is pySLAM `96019cf` via `scripts/run_wp2_pyslam.py`. Causal keyframe-event ideas may be read as reference only. |
| `feature/nazar-assist-yaropolk-wp4-handoff` @ `26541e0`, `…-wp5` @ `b66e925`, `…-wp6` @ `720db70` | Input-join audit, map metrics and keyframe scheduling, superseded by Yulian's `mapping_run`/`map_geometry`/`comparison_run`. The `wp6` SLAM preview may be consulted for presentation material. |
| `feature/nazar-dataset-splits`, `feature/nazar-model-selection`, `feature/nazar-unidepth-v2`, `feature/nazar-wp1-evidence`, `verify/nazar-wp1-20261023`, `review/nazar-wp1-20261023` | Consolidated into `feature/nazar-wp1-integration`. |
| Worktree `wp5-keyframe-runs` (branch `feature/nazar-assist-yaropolk-keyframe-runs` @ `31cfd29`, dirty) | Uncommitted experiments. Not touched, not a dependency. |
| `stash@{0}` (WP2 runtime source in progress) | Preserved; not used. |
| Remote `yaropolk-wp1-wp2-integration`, `codex/yulian-*` | Already merged (PR #5, #7, #8). |

### 1.5 Held-out status and disclosed failures

- `tum_fr3_long_office_heldout.json` is frozen (archive SHA-256 `c7cd8e1a…59e9c`) on the local WP1 branch. Freezing reads file hashes only.
- No depth or map inference, P1 run or GT-based metric has been computed on fr3.
- **Disclosed failed experiment:** run `wp2_heldout2488_4484fd7` (Nazar's superseded v2.2.1 runner, clean commit `4484fd7`) attempted B0 on fr3 and **failed** inside upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`). It produced no trajectory and no metrics, and nothing was tuned from it. Under D-5 this is disclosed and fr3 stays a valid held-out split.
- **Other disclosed failures of the superseded runner:**
  - `wp2_development573_4484fd7` ended `degraded` (`tracking_lost`) on fr1/desk;
  - `wp2_selection50_4484fd7` failed (`TUM pose timestamps must strictly increase`);
  - `wp2_development50_events_4484fd7` was `degraded` (fewer than 3 associated poses).

  These are risk hypotheses for wider-sequence B0, not evidence about the merged `96019cf` runner.
- Earlier disclosed failures (PROJECT_STATUS §4, `wp1_integrated_unidepth_f1_6fa2f55`) remain as recorded.

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
12. Demo capture, presentation materials, contribution table, reproducibility guide, requirements audit, release tag.

### 1.7 Technical blockers (the only gates)

| Blocker | Affects | Resolution |
|---|---|---|
| WP2 preflight accepts only the C2 smoke manifest | All wider B0/P1 runs | Code in Y-04, after N-01 is merged |
| Yaropolk needs the dev/selection/held-out TUM archives (~3.7 GB) | Y-04…Y-06 | The Y-04 prompt authorizes downloads from the official URLs recorded in the manifests |
| Nazar needs a Docker build of the merged pySLAM image (base image, sources, pip freeze; several GB, long compile) | N-02 onwards | The N-02 prompt authorizes this build |
| CUDA GPU required for DA3/UniDepth | N-02…N-06 | Nazar's RTX 5070 Laptop. Track Y needs no GPU |

A chunk stops only if credentials, hardware or data are physically unavailable.

### 1.8 Mandatory versus optional

- **Mandatory** (EXPERIMENTS.md §6 "required", PLAN.md §8):
  - B0 on smoke/dev/selection/held-out;
  - B1 on dev/held-out;
  - two-candidate model spike;
  - P1-raw and P1-global on all splits;
  - P1-window on dev;
  - confidence ablation on dev/selection (UniDepth only; DA3 explicitly skipped);
  - keyframe-interval ablation on dev;
  - latency/memory evidence;
  - demo capture, presentation materials, contribution table, tag.
- **Out of scope** (D-4): P2 (DUSt3R/VGGT), ICP refinement (not implemented), KITTI, semantics, a streaming/async real-time implementation, and P1-window on held-out unless it passes the D-4 dev criterion.

---

## 2. Definition of done

Legend: **✔** already satisfied or resolved · **N** Track N · **Y** Track Y · **IC** integration checkpoint (a technical gate executed by one person) · **OUT** out of scope.

**Integration**
- [x] ✔ C1–C5, WP2 sparse baseline and WP3/WP4 merged on `develop`, CI green (`7b4b26e`).
- [ ] IC IC1: N-01, N-03, Y-01, Y-02 merged; full suite green.
- [ ] IC IC2: Y-04 and N-04 merged.
- [ ] IC IC3: frozen benchmark protocol merged *before* any held-out run.

**Frozen data splits**
- [x] ✔ Smoke manifest `data/manifests/tum_fr1_xyz.json`.
- [x] ✔ Split choice resolved (D-1): fr1/desk dev, fr1/desk spike50, fr2/desk selection50, fr3/long_office_household held-out.
- [ ] N Manifests merged and byte-reproducible (N-01).

**Model selection**
- [x] ✔ Primary/fallback rule resolved (D-3): UniDepth V2 primary per the pre-registered rubric, with DA3 at 504 as the gate-based fallback.
- [ ] N UniDepth adapter, protocol, scorecards and ADR001 on `develop`, with a clean re-run (N-03).

**SLAM baseline**
- [x] ✔ Native/Docker B0 smoke + sparse export.
- [x] ✔ B0 configuration frozen as merged (D-9).
- [ ] Y All-frame tracking states, causal keyframes, per-frame timing (Y-01).
- [ ] Y Recorded B0 Sim(3) ATE/RPE + resources (Y-02); tracking success + failure accounting (Y-03).
- [ ] Y Split-manifest support + per-split B0 configs (Y-04).
- [ ] Y B0 dev/selection runs + failure analysis (Y-05); B0 held-out (Y-06).

**Alignment/fusion**
- [x] ✔ Global scale, correspondences, fusion, comparison (Yulian, PR #7/#8).
- [ ] N P1 with UniDepth predictions verified through the unchanged alignment/fusion (N-04).
- [ ] OUT ICP refinement (D-4).

**Benchmark**
- [x] ✔ Smoke B0/B1/P1-raw/P1-global comparison (Yulian).
- [ ] N Development + selection benchmark (N-05).
- [ ] IC Protocol freeze, mechanically derived from N-05 by the D-4 rules (IC3).
- [ ] N Held-out benchmark (N-06).

**Required ablations**
- [x] ✔ Global vs raw scale on smoke; keyframes 2/5 on smoke; DA3 confidence explicitly unavailable.
- [ ] N Keyframe interval, P1-window, confidence (UniDepth), primary vs fallback on dev/selection (N-05).
- [ ] N DA3 resolution and UniDepth confidence depth-only evidence ported (N-04).
- [ ] OUT P2 geometry model.

**Latency and memory**
- [ ] Y SLAM per-frame p50/p95, peak RSS, cold start, throughput (Y-02/Y-03).
- [ ] N Model + alignment + fusion p50/p95, peak VRAM/RAM, wall-clock throughput; real-time verdict per D-7 (N-06).

**Independent reproduction**
- [ ] N Second-machine reproduction of the merged smoke pipeline (N-02).
- [ ] Y B0 on a second platform (macOS native vs Nazar's Docker), compared in the final table (Y-05/Y-06 → F-N1).
- [ ] Y Fresh-clone CPU reproduction (F-Y2).

**Documentation**
- [ ] N Final results, limitations (including the licence state, D-6), reproducibility guide, status docs (F-N1).
- [ ] Y WP2 docs (Y-01…Y-06).

**Demo, presentation materials, contributions, release**
- [ ] N Demo capture (F-N2).
- [ ] Y Presentation materials + contribution table (F-Y1); requirements audit (F-Y2).
- [ ] IC Release: `develop → main` merge + tag `v1.0.0` (F-0).

---

## 3. File and ownership boundaries

- **Planned / (new):** the file does not exist yet on `origin/develop`.
- **Ported files:** these exist at the cited local commit (`5e542d7` for N-01/N-03, `047992e` for N-04) and are planned on `develop`.
- **Short paths** such as `slam/setup.py` are relative to `src/rt_mapping/`.
- **Single editor:** before the final phase, exactly one person edits each shared documentation file. A person who needs a change outside their area writes it in their PR body or handoff doc; the owner applies it.

| Area | Track N may edit | Track Y may edit | Shared read-only | Integration-only | Conflict-avoidance rule |
|---|---|---|---|---|---|
| `data/manifests/`, `src/rt_mapping/data/`, `scripts/{build_tum_manifest,freeze_tum_split(planned)}.py` | ✔ | — | Y reads | — | Y consumes only the merged manifests |
| `src/rt_mapping/adapters/`, `geometry/{adapter,intrinsics}.py`, `runs/geometry_run.py`, `evaluation/{depth,tum_depth,model_selection(planned),prediction_grid(planned),geometry_verification(planned),confidence_ablation(planned)}.py` | ✔ | — | Y reads | — | — |
| `contracts/{frame,geometry,run_manifest,_validation}.py`, `evaluation/timing.py` | ✔ (only if a contract bug blocks) | — | both read | — | Y reuses `summarize_timings` unchanged |
| `src/rt_mapping/slam/`, `contracts/slam.py` (planned), `evaluation/slam_run.py` (planned) | — | ✔ | N reads | — | N never edits SLAM code |
| `scripts/{run_wp2_pyslam,prepare_wp2_baseline,check_wp2_environment,build_wp2_native,build_wp2_linux_native,visualize_wp2_trajectory}.py`, `scripts/{evaluate_wp2_run,measure_wp2_resources}.py` (planned), `containers/`, `requirements/wp2-*`, `configs/wp2_*.json` | — | ✔ | N runs them unchanged | — | N reports runtime problems in PR bodies |
| `scripts/{run_tum_da3_metric,check_wp1_environment,run_da3_metric_smoke}.py`, `scripts/{run_geometry_benchmark,compare_geometry_models,verify_geometry_run,analyze_confidence,render_demo}.py` (planned), `requirements/wp1-*`, `configs/{model_assets,selected_geometry}.json` (planned) | ✔ | — | — | — | — |
| New configs `configs/pipeline.nazar.*.json`, `configs/mapping_comparison.nazar.*.json`, `configs/benchmark_frozen.json` (planned) | ✔ | — | Y reads | — | Existing `configs/pipeline.tum.*.json` stay unchanged |
| Yulian WP3/WP4: `alignment/`, `fusion/`, `runs/{mapping_run,comparison_run,pipeline_run,synthetic_mapping,artifacts}.py`, `evaluation/{trajectory,map_geometry,oracle,synthetic_scene}.py`, `geometry/projection.py`, `scripts/run_{pipeline,mapping_comparison,offline_mapping,alignment_smoke,comparison_smoke}.py`, `configs/{mapping_comparison,offline_mapping}.json` | defect fixes only, focused `fix/nazar-*` PR, Yulian notified | — | ✔ both | — | Y reports defects; no replacement implementations |
| Tests `tests/test_{tum_*,geometry_*,da3_*,depth_*,timing,run_manifest,intrinsics}.py` + new N tests | ✔ | — | — | — | — |
| Tests `tests/test_{slam_*,wp2_setup,pyslam_sparse_native}.py` + new Y tests | — | ✔ | — | — | — |
| `tests/test_import_hygiene.py`, `tests/conftest.py`, Yulian's tests | — | — | ✔ | F-Y2 only | Each track adds `tests/test_import_hygiene_wp1.py` / `_wp2.py` (planned) |
| `results/summaries/nazar_*`, `results/plots/nazar_*`, `results/summaries/wp1_*` | ✔ | — | — | — | Never edit existing summaries |
| `results/summaries/yaropolk_*`, `results/plots/yaropolk_*` | — | ✔ | — | — | Never edit existing summaries |
| Historical `results/summaries/{wp2_*,wp3_wp4_yulian_*}`, `results/plots/{wp2_*,yulian_*}` | — | — | ✔ | — | Immutable |
| Track docs N: `docs/{DATASET_FREEZE,UNIDEPTH,SELECTION_PROTOCOL,WP1_HANDOFF,DEPTH_ABLATIONS,NAZAR_REPRODUCTION,DEVELOPMENT_BENCHMARK,HELDOUT_BENCHMARK,BENCHMARK_PROTOCOL,DEMO}.md`, `docs/decisions/ADR001_geometry_model.md` (all planned) | ✔ | — | — | — | — |
| Track docs Y: `docs/WP2_SETUP.md`, `docs/WP2_SPARSE_EXPORT.md`, `docs/WP2_LINUX_CONTAINER.md`, `docs/{WP2_TRACKING_EXPORT,WP2_EVALUATION,WP2_BENCHMARK}.md` (planned) | — | ✔ | — | — | — |
| `docs/ARCHITECTURE.md` | — | ✔ (SlamExport section) | N reads | — | N documents geometry semantics in `docs/UNIDEPTH.md` |
| `docs/EXPERIMENTS.md`, `docs/MODEL_SELECTION.md`, `docs/ENVIRONMENT.md` | ✔ | — | Y reads | — | EXPERIMENTS is edited only at IC3 and F-N1 |
| `docs/INTERIM_REVIEW.md`, `docs/{CONTRIBUTIONS,PRESENTATION_OUTLINE,SUBMISSION_AUDIT}.md` (planned) | — | ✔ | — | — | — |
| `docs/PROJECT_STATUS.md`, `docs/INTEGRATION_STATUS.md` | ✔ at IC1/IC2/IC3/F-N1 only | — | — | ✔ | Y puts status rows in PR bodies; N copies them verbatim |
| `README.md`, `CLAUDE.md`, `scripts/README.md`, `configs/README.md`, `results/README.md`, `tests/README.md`, `pyproject.toml`, `.gitignore` | — | — | — | ✔ N in F-N1 | Nobody edits them during waves |
| `.github/workflows/` | — | — | — | ✔ Y in F-Y2, only for a verified gap | — |
| `PLAN.md`, `CONTRIBUTING.md`, `docs/PROJECT_BRIEF.md`, `docs/YULIAN_HANDOFF.md`, `docs/WP3_WP4_COMPLETION.md`, this file | — | — | ✔ | — | Not edited by chunks |

**Naming:**
- Branches: N `feature/nazar-*`, Y `feature/yaropolk-*`.
- Run IDs: `nazar_<chunk>_<topic>_<sha7>_NN` and `yaropolk_<chunk>_<topic>_<sha7>_NN`.
- Docker container: Nazar `rt-mapping-wp2-nazar`; Yaropolk uses the native macOS `.venv-pyslam` (fallback: `rt-mapping-wp2-yaropolk`).
- Summaries and plots carry the person prefix.

---

## 4. Parallel work waves

```text
            Track N (Nazar)                         Track Y (Yaropolk)
Wave 1      N-01 frozen splits PR          ‖        Y-01 all-frame states/timing export
Wave 2      N-02 2nd-machine smoke repro   ‖        Y-02 B0 evaluation + resources
            N-03 UniDepth + selection      ‖        Y-03 tracking success + failure accounting
─────────── IC1: N-01, N-03, Y-01, Y-02 merged ─────────────────────────────────────
Wave 3      N-04 model-agnostic pipeline   ‖        Y-04 WP2 split-manifest support + configs
─────────── IC2: N-04 and Y-04 merged ──────────────────────────────────────────────
Wave 4      N-05 dev + selection benchmark ‖        Y-05 B0 dev/selection runs + failures
─────────── IC3: protocol freeze merged (mechanical, D-3/D-4 rules) ────────────────
Wave 5      N-06 held-out + performance    ‖        Y-06 held-out B0 (frozen config)
─────────── Final: F-N1 ‖ F-Y1 → F-N2 ‖ F-Y2 → F-0 release ─────────────────────────
```

| Wave | Nazar | Yaropolk | Why they don't collide |
|---|---|---|---|
| 1 | N-01 | Y-01 | `data/` + manifests vs `slam/` + `contracts/slam.py`; neither reads the other's outputs |
| 2 | N-02 (independent of N-01), N-03 (after N-01 merged) | Y-02 (independent of Y-01), Y-03 (after Y-01 + Y-02 merged) | N-02 only *runs* merged WP2 code from a new config file; Y never touches WP1 files |
| IC1 | Nazar executes the checkpoint | Yaropolk continues Y-03 | — |
| 3 | N-04 | Y-04 | N edits WP1 scripts + new N configs; Y edits `slam/setup.py` + `configs/wp2_*` |
| 4 | N-05 (Nazar's machine, Docker + CUDA) | Y-05 (Yaropolk's machine, macOS native) | Separate run IDs, summaries and hardware; exchange only committed summaries |
| 5 | N-06 | Y-06 | Same frozen protocol, separate runs |

**Why there are three checkpoints:**
- **IC2** exists because the dev/held-out pipeline needs Yaropolk's split support in `slam/setup.py`, which in turn needs Nazar's merged manifests.
- **IC3** exists because the protocol must be merged before any held-out run.
- No chunk before IC1 needs anything from the other track.

**Merging:** each chunk merges its own PR once the required checks are green (§5 standard rules), so waiting for review never blocks the next chunk.

---

## 5. Track N — Nazar chunks

**Standard rules block (pasted into every N and Y prompt as `STANDARD RULES`):**

> Read `CLAUDE.md` first. Run `git fetch --all --prune`, `gh pr list --state all --limit 30` and `gh run list --limit 5`, and report the exact `origin/develop` SHA. Base the work on that exact `origin/develop`. Never use local `main`.
>
> Preserve every other worktree, branch, stash, ignored run and uncommitted file. Never touch the dirty `wp5-keyframe-runs` worktree. Never merge or cherry-pick a branch listed as superseded in `docs/TWO_PERSON_COMPLETION_PLAN.md` §1.4; port only the files this chunk names. Create a new worktree for the chunk branch (`git worktree add --no-track -b <branch> ../<dir> origin/develop`). Modify only the allowed files. Never use files from the other person's ignored `results/runs/`.
>
> Ground truth only in evaluation/oracle code. Never overwrite a finished `run.json` (new config = new run_id). Never tune on held-out data. Disclose every failed run in the chunk's summary/doc. No installs, upgrades or downloads except those this prompt explicitly authorizes; this prompt is the authorization for those.
>
> This prompt authorizes: commit (configured Git identity), push of this branch, one PR to `develop`, waiting for the required checks, and — when all required checks pass and `gh pr diff --name-only` lists only allowed files — merging that PR with a merge commit and updating local `develop` (fast-forward only). Request a non-blocking review from the original WP owner for attribution. It does not authorize tagging, force-pushing or editing other PRs.
>
> If a stop condition occurs, do not merge: write a blocker report in the PR (or the chunk doc) instead of improvising. End with an evidence report: base SHA, branch, commit SHA(s), PR URL, merge SHA, exact test counts, run IDs with status (including failures), summary paths, deviations from the brief.

---

### N-01 — Frozen development/selection/held-out manifests on `develop`

**Objective.** Merge the four frozen TUM split manifests and the split-freeze tool into `develop`, byte-reproducible from local data.

**Why it is required.** EXPERIMENTS.md §2 (frozen splits), PLAN WP0 ("frozen sequence list"). These manifests are the input contract for all wider B0/P1 runs (Y-04, N-05, N-06).

**Implementer and attribution.** Nazar implements; original owner Nazar (WP1/WP0 data). The code is ported from his local commit `58f3e7a` as consolidated in `6fa2f55`.

**Prerequisites.**
- `origin/develop` (`7b4b26e` or newer).
- Source branch `feature/nazar-wp1-integration` @ `5e542d7` (local).
- Windows `.venv` (Python 3.11).
- Local archives/extractions of fr1/desk, fr2/desk and fr3 under `data/raw/tum_rgbd/` (present; no download).
- No GPU, Docker or cross-track input.

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
- `slam/`, UniDepth/selection files (N-03)
- Held-out inference

**Git workflow.** Branch `feature/nazar-frozen-splits` from `origin/develop`. Independent PR → `develop`. Self-merge after green checks. Non-blocking review request to Yaropolk.

**Work.**
1. Diff the allowed files between `ce095fa` and `5e542d7`; check out exactly those paths from `5e542d7`.
2. Confirm that `build_tum_manifest` output for fr1/xyz is unchanged.
3. Update `docs/DATASET_FREEZE.md`:
   - the base is now `origin/develop`;
   - the split choice is final per D-1;
   - held-out disclosure (§1.5).
4. Note that the held-out manifest is ~1.09 MB (a manifest, not data).

**Verification.**
- `pytest tests/test_tum_split_manifest.py tests/test_tum_manifest.py -q`, then the full suite (≥ 472 + new tests passed, 1 skipped).
- `freeze_tum_split.py … --check` for all four manifests (byte-identical).
- `build_tum_manifest.py --check` for fr1/xyz.
- `git diff --check`.
- Grep the new JSON/docs for absolute-path markers.

**Acceptance criteria.**
- [ ] 4 manifests byte-identical under `--check`.
- [ ] fr1/xyz manifest unchanged.
- [ ] Full suite + CI green.
- [ ] No absolute paths; no held-out runs.
- [ ] DATASET_FREEZE lists the archive SHA-256 per split and the disclosure.

**Required output.** Merged PR with manifests, tool, tests and DATASET_FREEZE.md.

**Failure and stop conditions.**
- Stop if any `--check` differs (report the diff; no silent regeneration).
- Stop if the fr1/xyz manifest would change.
- Stop if a local archive hash mismatches its manifest.

**One-prompt execution brief.**
```text
Chunk N-01 (Track N, Nazar): port the frozen TUM split manifests to develop and merge.
STANDARD RULES: <paste block from §5>. No downloads are needed or authorized.
Branch feature/nazar-frozen-splits from exact origin/develop. Source of truth: local branch
feature/nazar-wp1-integration @ 5e542d7 (base ce095fa). Port ONLY: data/manifests/tum_fr1_desk_development.json,
tum_fr1_desk_spike50.json, tum_fr2_desk_selection50.json, tum_fr3_long_office_heldout.json, scripts/freeze_tum_split.py,
the split-builder change in src/rt_mapping/data/manifest.py, tests/test_tum_split_manifest.py, docs/DATASET_FREEZE.md.
Do not touch tum_fr1_xyz.json, shared docs, test_import_hygiene.py, SLAM or UniDepth files.
Update DATASET_FREEZE.md: new base SHA; split choice final (plan D-1); held-out disclosure (superseded runner run
wp2_heldout2488_4484fd7 failed in upstream local_mapping, no trajectory/metrics, nothing tuned).
Verify: targeted + full pytest with .venv; freeze_tum_split.py --check for all 4 manifests using existing
data/raw/tum_rgbd; build_tum_manifest.py --check for fr1/xyz; git diff --check; absolute-path scan.
Open the PR "feat(wp1): frozen development/selection/held-out TUM manifests", wait for required checks, verify the PR
diff lists only allowed files, merge, fast-forward local develop. Report the evidence.
```

---

### N-02 — Second-machine reproduction of the merged smoke pipeline

**Objective.** A clean new run of the merged one-config pipeline on fr1/xyz smoke-200 on Nazar's hardware (Docker pySLAM `96019cf` + CUDA DA3), compared against Yulian's committed summary.

**Why it is required.**
- PLAN WP4 reviewer rule ("reviewer має відтворити хоча б smoke run") and the independent-reproduction requirement.
- It establishes Nazar's runtime for N-04…N-06 and a second-platform B0 data point.

**Implementer and attribution.** Nazar, as an independent reproducer of Yulian's WP4 and Yaropolk's WP2 runtime. No ownership change.

**Prerequisites.**
- `origin/develop`; Docker Desktop (Linux engine).
- Nazar's CUDA DA3 `.venv` with the pinned checkpoint cached.
- fr1/xyz data (present).
- Independent of N-01 and of Track Y.
- Authorized download: the Docker build in `docs/WP2_LINUX_CONTAINER.md` (base image digest, pySLAM/GTSAM sources, `requirements/wp2-linux-x86_64.txt`).

**Allowed scope.**
- `configs/pipeline.nazar.smoke200.docker.json` (new)
- `results/summaries/nazar_n02_e2e_smoke200_<sha7>.json` (new)
- `docs/NAZAR_REPRODUCTION.md` (new)
- `results/plots/nazar_n02_*.png` (new, small)

**Forbidden scope.**
- Any WP2/WP3/WP4 source, `docs/WP2_LINUX_CONTAINER.md`, existing configs, Yulian's summaries
- Container name `rt-mapping-wp2-yulian`
- Downloading checkpoints

**Git workflow.** Branch `feature/nazar-pipeline-reproduction`. Independent PR. Self-merge after green checks. Non-blocking review request to Yaropolk.

**Work.**
1. Build `rt-mapping-wp2:96019cf` if absent and start container `rt-mapping-wp2-nazar`.
2. Run the environment probe and the opt-in native sparse test.
3. Write a new config: a copy of `configs/pipeline.tum.windows-docker.json` with only the container name and the DA3 interpreter (`.venv/Scripts/python.exe`) changed.
4. Commit it, then run `run_pipeline.py --run-id nazar_n02_e2e_smoke200_<sha7>_01` from the clean commit.
5. Compare against `results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json`: poses, landmarks/keyframes, scale, inliers, voxels, ATE, map metrics, DA3 metrics, timings.
6. Report the differences as cross-machine variation.

**Verification.**
- `run.json` status for parent and stages; `dirty_worktree=false`.
- Checkpoint SHA-256 matches `bbea5b0b…324776`.
- Full CPU suite.
- Summary contains source hashes.
- `git diff --check`; absolute-path scan.

**Acceptance criteria.**
- [ ] Clean run with all stages ok, or a disclosed failure with logs.
- [ ] Comparison table with absolute and relative differences.
- [ ] Hardware, driver, Docker image ID and container limits recorded.
- [ ] No source changes.

**Required output.** Merged PR with config, summary JSON and reproduction doc (or a blocker report).

**Failure and stop conditions.**
- If the Docker build fails, disclose it and stop.
- If a WP3/WP4 defect appears, stop. The fix is a separate focused `fix/nazar-*` PR.
- If the checkpoint is missing, stop.
- Never tweak thresholds to match Yulian.

**One-prompt execution brief.**
```text
Chunk N-02 (Track N, Nazar): independently reproduce the merged one-config smoke pipeline on my machine.
STANDARD RULES: <paste block from §5>. Authorized downloads: the Docker image build described in
docs/WP2_LINUX_CONTAINER.md (base image, pinned sources, pinned pip freeze). Nothing else.
Branch feature/nazar-pipeline-reproduction from exact origin/develop. Build image rt-mapping-wp2:96019cf if absent,
start container rt-mapping-wp2-nazar (never reuse/overwrite other containers), run check_wp2_environment.py
--probe-runtime and the opt-in native sparse unittest. Create configs/pipeline.nazar.smoke200.docker.json =
configs/pipeline.tum.windows-docker.json with only container name and DA3 interpreter (.venv/Scripts/python.exe)
changed. Commit it, then from the clean commit run scripts/run_pipeline.py --run-id nazar_n02_e2e_smoke200_<sha7>_01.
Do not edit any source. Compare with results/summaries/wp3_wp4_yulian_tum_fr1_xyz_200.json and write
results/summaries/nazar_n02_e2e_smoke200_<sha7>.json (with source hashes) and docs/NAZAR_REPRODUCTION.md
(hardware, image ID, differences as cross-machine variation, no parity or real-time claims, all failed attempts).
If a WP3/WP4 defect appears: stop and report, do not fix here. Full CPU pytest, git diff --check, path scan.
Open PR, wait for required checks, verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### N-03 — UniDepth V2 adapter, paired selection protocol and ADR001 on `develop`

**Objective.** Merge the UniDepth adapter, generic geometry benchmark CLI, scorecard/verifier and ADR001 (recording the D-3 rule) into `develop`, with a clean re-run of the selection50 pair from the new commit.

**Why it is required.** MODEL_SELECTION.md §5–§7 (two-candidate spike, scorecard, ADR), EXPERIMENTS §6 "model spike (2 candidates) required", PLAN WP1 fallback model.

**Implementer and attribution.** Nazar; original owner Nazar (WP1). The code comes from his local `ccec264…e633faa`, `7f37d66`, `50c2805`, consolidated in `6fa2f55`/`463b446`.

**Prerequisites.**
- N-01 merged (same track).
- `.venv` (DA3) and the existing `.venv/unidepth`.
- Cached pinned checkpoints.
- RTX 5070 Laptop.
- fr1/desk and fr2/desk data (present).

**Allowed scope.**
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
- Changing the rubric after seeing results

**Git workflow.** Branch `feature/nazar-unidepth-selection`. Independent PR. Self-merge after green checks.

**Work.**
1. Port the files; put the import-hygiene additions into the new test file.
2. Keep the C5 default (`process_res` 384) byte-compatible; selection uses 504 explicitly.
3. Run clean selection50 for both models: `nazar_n03_sel50_da3_<sha7>_01` and `nazar_n03_sel50_unidepth_<sha7>_01`.
4. Run `verify_geometry_run.py` and the scorecard.
5. Compare depth with the historical `wp1_integrated_selection50_*_463b446` runs (expect bit-identical depth; timing may differ).
6. Set ADR001 status to "accepted by pre-registered rubric (plan D-3)", with the fallback trigger and the licence state recorded as a limitation (D-6).

**Verification.**
- Full CPU suite; UniDepth unit tests with a fake backend.
- GPU runs with `dirty_worktree=false`.
- Verifier recomputes metrics and masks; scorecard recomputation matches to 1e-12.
- Depth-identity check.
- `git diff --check`; path/secret scan.

**Acceptance criteria.**
- [ ] Suite + CI green.
- [ ] Two new clean runs ok.
- [ ] Depth identical on 50/50 frames, or the differences are quantified.
- [ ] ADR001 records D-3 and the licence state.
- [ ] No weights or sources vendored.

**Required output.** Merged PR with code, tests, docs and scorecards.

**Failure and stop conditions.**
- Stop on a checkpoint hash mismatch or a missing environment.
- Stop if `contracts/*` would need incompatible changes.
- If the new scorecard reverses the winner, record it. D-3 then selects DA3 automatically (rubric winner on the re-run); do not adjust the rubric.

**One-prompt execution brief.**
```text
Chunk N-03 (Track N, Nazar): bring UniDepth V2 + paired model selection + ADR001 onto develop and merge.
STANDARD RULES: <paste block from §5>. No downloads authorized. Precondition: N-01 merged into origin/develop - verify,
else stop.
Branch feature/nazar-unidepth-selection from exact origin/develop. Source: local feature/nazar-wp1-integration
@ 5e542d7. Port only the files in docs/TWO_PERSON_COMPLETION_PLAN.md N-03 "Allowed scope". Put import-hygiene additions
in new tests/test_import_hygiene_wp1.py. Keep the DA3 CLI default process_res 384; selection uses explicit 504.
Use existing .venv and .venv/unidepth and cached checkpoints only. From the clean commit, run selection50 for both
models (run IDs nazar_n03_sel50_da3_<sha7>_01, nazar_n03_sel50_unidepth_<sha7>_01; manifest
tum_fr2_desk_selection50.json, --split selection --frames 50 --prewarm 10), run verify_geometry_run.py,
compare_geometry_models.py -> results/summaries/nazar_n03_selection50_<sha7>_scorecard.json, and check depth identity vs
wp1_integrated_selection50_{da3,unidepth}_463b446. Update ADR001: primary = rubric winner of this re-run (plan D-3),
fallback DA3METRIC-LARGE process_res 504 (or UniDepth if DA3 wins), fallback trigger as in D-3, licence state recorded as
a limitation only. Full pytest, git diff --check, path/secret scan. Open PR, wait for checks, verify allowed-files-only
diff, merge, fast-forward local develop.
```

---

### N-04 — Model-agnostic pipeline geometry stage + UniDepth smoke P1 + depth-ablation evidence

**Objective.**
- `scripts/run_pipeline.py` runs the geometry stage with either model on any frozen manifest.
- A clean UniDepth smoke P1 run passes through the unchanged alignment/fusion/comparison, including the pre-registered confidence ablation.
- The dev50 depth-only ablation evidence is ported.

**Why it is required.**
- PLAN WP4 (adapters by Nazar/Yaropolk); EXPERIMENTS §6 (confidence ablation, primary vs fallback).
- It is the prerequisite for N-05 and supplies the D-3 fallback-trigger evidence.

**Implementer and attribution.** Nazar (WP1 adapter, WP5 models). Alignment/fusion stay Yulian's and are used unchanged.

**Prerequisites.**
- N-03 merged.
- Nazar's own N-02 SLAM smoke stage run (local, reused via `reuse_run`).
- GPU.
- No Track Y artifacts.

**Allowed scope.**
- `scripts/run_geometry_benchmark.py` (accept the launcher-appended `--run-id`/`--output-root`)
- `src/rt_mapping/runs/geometry_run.py`, new `tests/test_geometry_pipeline_stage.py`
- `configs/pipeline.nazar.smoke200.unidepth.json`, `configs/mapping_comparison.nazar.confidence.json` (new)
- `src/rt_mapping/evaluation/confidence_ablation.py`, `scripts/analyze_confidence.py`, `docs/DEPTH_ABLATIONS.md`
- `results/summaries/wp5_{da3_resolution_development50,unidepth_confidence_development50,da3_confidence_unavailable}.json` (ported from `047992e`)
- `results/summaries/nazar_n04_*.json`, `results/plots/nazar_n04_*.png`

**Forbidden scope.** Yulian's files, `slam/`, shared docs, existing pipeline configs.

**Git workflow.** Branch `feature/nazar-model-agnostic-pipeline`. Independent PR. Self-merge after green checks.

**Work.**
1. Make the CLI stage-compatible and test it with a fake adapter.
2. Compute the D-4 confidence thresholds from **dev50 UniDepth predictions only**: the per-pixel confidence values at the retain-75% and retain-50% quantiles, pooled over the 50 frames. Write them into the new comparison config before any P1 run.
3. Run `nazar_n04_e2e_smoke200_unidepth_<sha7>_01` with `slam: {"reuse_run": <N-02 SLAM stage>}`.
4. Evaluate the D-3 pipeline gate for UniDepth: all children ok, no OOM, model-ID check passes. Record pass/fail in the summary.
5. Port the `047992e` evidence. State the rank-equivalence of the confidence mapping and re-verify the retained counts.

**Verification.**
- Full suite + new stage test.
- Clean run; all children ok, or failures disclosed.
- Confidence children report thresholds and coverage.
- `git diff --check`.

**Acceptance criteria.**
- [ ] The launcher runs the geometry stage for `--model unidepth` and `--model da3` (test).
- [ ] UniDepth P1 smoke recorded, with an explicit D-3 gate result.
- [ ] Confidence ablation with coverage.
- [ ] Ported numbers re-verified.

**Required output.** Merged PR with code, tests, configs, summaries and `docs/DEPTH_ABLATIONS.md`.

**Failure and stop conditions.**
- If `mapping_run`/`comparison_run` reject UniDepth predictions: that is a D-3 gate failure. Record it, merge the evidence, and N-05 then uses the DA3 fallback. Do not edit Yulian's code in this chunk.
- Never derive thresholds from GT.
- If the N-02 SLAM run is missing, rerun SLAM through the pipeline.

**One-prompt execution brief.**
```text
Chunk N-04 (Track N, Nazar): model-agnostic pipeline geometry stage, UniDepth smoke P1, depth-ablation evidence.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: N-03 merged; my N-02 SLAM stage run exists
locally (else rerun SLAM through the pipeline).
Branch feature/nazar-model-agnostic-pipeline from exact origin/develop. Make scripts/run_geometry_benchmark.py work as a
run_pipeline.py stage (accept --run-id/--output-root appended by the launcher) with a fake-adapter test. Do NOT edit
alignment/fusion/mapping/comparison/pipeline_run code. Compute UniDepth confidence thresholds at retain-75% and
retain-50% quantiles from dev50 predictions only (no GT) and write them into new
configs/mapping_comparison.nazar.confidence.json BEFORE any run. Create configs/pipeline.nazar.smoke200.unidepth.json
reusing my N-02 SLAM stage, run nazar_n04_e2e_smoke200_unidepth_<sha7>_01 from a clean commit, and record the plan D-3
pipeline gate (all children ok, no OOM, model-ID check) as pass/fail. Port from local 047992e: confidence_ablation.py,
analyze_confidence.py, docs/DEPTH_ABLATIONS.md, the three wp5_* summaries; state rank-equivalence of the confidence
mapping and re-verify retained counts. Summaries -> results/summaries/nazar_n04_*.json. Disclose failures. Full pytest,
git diff --check. Open PR, wait for checks, verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### N-05 — Development and selection benchmark with ablations

**Objective.** Pipeline results on fr1/desk development (573) and fr2/desk selection50:
- both models: B0-shared-scale, B1 oracle, P1-raw, P1-global;
- P1-window (2 pre-registered windows);
- keyframe intervals 1/2/5;
- confidence (UniDepth only, 2 thresholds);
- B0 all-frame evaluation via Yaropolk's merged evaluator;
- the frozen held-out configuration, derived mechanically by the D-4 rules.

**Why it is required.** EXPERIMENTS §6 matrix (Dev/Selection), PLAN WP5, H1–H4.

**Implementer and attribution.** Nazar runs it (WP5 models + benchmark orchestration). The B0 metrics code is Yaropolk's and alignment is Yulian's; each is credited in the summary.

**Prerequisites.**
- IC2 passed: Y-04 merged (`configs/wp2_pyslam_{development,selection}.json`) and N-04 merged.
- GPU + Docker.

**Allowed scope.**
- `configs/pipeline.nazar.{development,selection}.{da3,unidepth}.json`, `configs/mapping_comparison.nazar.development*.json` (new)
- `results/summaries/nazar_n05_*.{json,csv}`, `results/plots/nazar_n05_*.png`
- `docs/DEVELOPMENT_BENCHMARK.md` (new)

**Forbidden scope.** Any source edits (bugs → separate focused fix PR by the code owner's track), held-out data, `configs/wp2_*.json`.

**Git workflow.** Branch `feature/nazar-development-benchmark`. Independent PR. Self-merge after green checks. Non-blocking review request to Yaropolk for the B0 rows.

**Work.**
1. Write the configs with the pre-registered D-4 values:
   - keyframe intervals {1, 2, 5};
   - `causal_window_frames` ∈ {60, 150} (one comparison config per value; `comparison_run` takes a single value);
   - UniDepth confidence thresholds from N-04;
   - DA3 at `process_res` 504, UniDepth at `resolution_level` 0.
2. Commit, then run `nazar_n05_{dev573,sel50}_{da3,unidepth}_<sha7>_01` (+ window variants).
3. Run `scripts/evaluate_wp2_run.py` on each SLAM stage.
4. Aggregate into a CSV/JSON. Tuning is limited to the pre-registered grid, and every run is listed.
5. Apply the D-4 selection rules mechanically and write the resulting held-out configuration into `docs/DEVELOPMENT_BENCHMARK.md` → "Derived freeze".

**Verification.**
- Every run `dirty_worktree=false`; status recorded (failures included).
- GT only in evaluation/oracle.
- Each number has sequence, units, alignment mode and hardware.
- Full suite unaffected; `git diff --check`.

**Acceptance criteria.**
- [ ] Dev + selection rows for all required methods, or explicit skipped/failed reasons.
- [ ] Complete run list.
- [ ] Derived freeze computed by the D-4 rules.
- [ ] No held-out access.

**Required output.** Merged PR with configs, summaries, plots and `docs/DEVELOPMENT_BENCHMARK.md`.

**Failure and stop conditions.**
- If B0 fails on dev: record it (D-9 forbids changing the B0 config). P1 rows for that split become failed/degraded with a reason.
- If a run needs code changes, stop.
- Never read the fr3 data.

**One-prompt execution brief.**
```text
Chunk N-05 (Track N, Nazar): development + selection benchmark and required ablations.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: Y-04 and N-04 merged
(configs/wp2_pyslam_development.json and _selection.json exist on origin/develop) - verify, else stop.
Branch feature/nazar-development-benchmark. Create configs/pipeline.nazar.{development,selection}.{da3,unidepth}.json and
configs/mapping_comparison.nazar.development*.json with the plan D-4 grid pre-registered: keyframe intervals {1,2,5},
causal_window_frames {60,150} (one config each), UniDepth confidence thresholds from N-04, DA3 process_res 504, UniDepth
resolution_level 0. Commit, then run nazar_n05_{dev573,sel50}_{da3,unidepth}_<sha7>_01 (+ window variants); run
scripts/evaluate_wp2_run.py on each SLAM stage. No source edits; never touch fr3. Aggregate into
results/summaries/nazar_n05_benchmark.{json,csv}, plots results/plots/nazar_n05_*.png, docs/DEVELOPMENT_BENCHMARK.md
with all runs (incl. failures) and a "Derived freeze" section computed mechanically by the plan D-3/D-4 rules. Open PR,
wait for checks, verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### N-06 — Held-out benchmark and end-to-end performance evidence

**Objective.** One frozen-protocol pipeline run on fr3/long_office_household (2488 frames):
- methods: B0, B1, P1-raw, P1-global, plus P1-window only if D-4 selected it;
- the primary model and the frozen best config;
- a performance table: per-stage p50/p95, wall-clock throughput, peak VRAM/RAM, hardware, resolution, input FPS;
- the D-7 real-time verdict.

**Why it is required.** EXPERIMENTS §4.4, §6 held-out column, §7 real-time rule; PLAN WP5.

**Implementer and attribution.** Nazar runs it; the B0 evaluator is Yaropolk's.

**Prerequisites.** IC3 passed (`configs/benchmark_frozen.json` merged; `configs/wp2_pyslam_heldout.json` from Y-04). GPU + Docker.

**Allowed scope.**
- `configs/pipeline.nazar.heldout.json` (frozen values only)
- `results/summaries/nazar_n06_*.{json,csv}`, `results/plots/nazar_n06_*.png`
- `docs/HELDOUT_BENCHMARK.md`

**Forbidden scope.** Changes to frozen values, source edits, reruns with new settings.

**Git workflow.** Branch `feature/nazar-heldout-benchmark`. Independent PR. Self-merge after green checks.

**Work.**
1. Commit the config; a scripted diff against `benchmark_frozen.json` must be empty.
2. Run `nazar_n06_heldout2488_<model>_<sha7>_01` once.
3. Evaluate B0 with the Y evaluator.
4. Compute the performance metrics:
   - SLAM tracking p50/p95 (Y export);
   - model inference p50/p95;
   - alignment and fusion times;
   - total wall clock;
   - effective FPS = frames / wall;
   - peak VRAM; peak RAM where measured.
5. Apply the D-7 verdict.

**Verification.** Clean run; empty frozen diff; GT only in evaluation; numbers traceable to `run.json`; full suite unaffected.

**Acceptance criteria.**
- [ ] Held-out rows complete, or the failure disclosed.
- [ ] Performance table with labels.
- [ ] Explicit real-time verdict.
- [ ] `wp2_heldout2488_4484fd7` disclosure repeated.

**Required output.** Merged PR with summaries, plots and `docs/HELDOUT_BENCHMARK.md`.

**Failure and stop conditions.**
- If the run fails, record it and merge the disclosure.
- Per D-5, a rerun is allowed only after a documented *bug* fix (merged via its owner's focused PR), under a new run_id. Both runs are reported. No parameter changes.

**One-prompt execution brief.**
```text
Chunk N-06 (Track N, Nazar): held-out benchmark with the frozen protocol + end-to-end performance evidence.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: configs/benchmark_frozen.json and
configs/wp2_pyslam_heldout.json on origin/develop - verify, else stop.
Branch feature/nazar-heldout-benchmark. Create configs/pipeline.nazar.heldout.json using ONLY frozen values and prove it
with an empty scripted diff against benchmark_frozen.json. Commit, then run nazar_n06_heldout2488_<model>_<sha7>_01 once.
Evaluate B0 with scripts/evaluate_wp2_run.py. Performance table: per-stage p50/p95 (SLAM tracking from the all-frame
timing export, model inference, alignment, fusion), wall clock, effective FPS = frames/wall, peak VRAM/RAM, hardware,
resolution, 30 Hz input. Real-time verdict per plan D-7. No tuning, no source edits; on failure disclose it (D-5 rerun
rule). Write results/summaries/nazar_n06_*.{json,csv}, plots, docs/HELDOUT_BENCHMARK.md (repeat the
wp2_heldout2488_4484fd7 disclosure). Open PR, wait for checks, verify allowed-files-only diff, merge, fast-forward local
develop.
```

---

## 6. Track Y — Yaropolk chunks

The standard rules block in §5 applies verbatim. Yaropolk's default environment is the macOS arm64 native pySLAM from `docs/WP2_SETUP.md` (`.venv-pyslam`, upstream `96019cf`). If it is unavailable, use the Linux Docker recipe with container `rt-mapping-wp2-yaropolk`; the chunk prompt then authorizes that image build.

### Y-01 — All-frame tracking states, causal keyframes and per-frame SLAM timing

**Objective.** The merged WP2 runner writes a normalized, validated per-input-frame export from a real clean smoke-200 run:
- `trajectory_all.csv`: frame_id, timestamp, upstream tracking state, causal pose `T_wc` or empty, `is_keyframe_created`;
- `timing.csv`: per-frame tracking_ms, plus mapping_ms where attributable, otherwise blank with a reason.

**Why it is required.**
- PLAN WP2 ("timestamped poses … timing", tracking failures).
- EXPERIMENTS §4.1 tracking success, §4.4 SLAM p50/p95.
- Listed as incomplete in PROJECT_STATUS, YULIAN_HANDOFF and INTEGRATION_STATUS.

**Implementer and attribution.** Yaropolk; original owner Yaropolk (WP2). Per D-2, Nazar's local `816b7f4` (`UNKNOWN`-state rules) and `4484fd7` (causal keyframe events) may be read and adapted selectively. Adopted code is credited as "assisted by Nazar" in the commit message and doc.

**Prerequisites.** `origin/develop`; native pySLAM environment; fr1/xyz data; no GPU; independent of Track N.

**Allowed scope.**
- `src/rt_mapping/slam/smoke.py`, `src/rt_mapping/slam/pyslam_export.py`
- `src/rt_mapping/slam/tracking_log.py` (new), `src/rt_mapping/contracts/slam.py` (new)
- `tests/test_slam_tracking_log.py` (new), `tests/test_slam_smoke.py`, `tests/test_import_hygiene_wp2.py` (new)
- `docs/WP2_TRACKING_EXPORT.md` (new), `docs/ARCHITECTURE.md` (SlamExport section)
- `results/summaries/yaropolk_y01_tracking_smoke200_<sha7>.json`

**Forbidden scope.**
- Upstream pySLAM source/algorithm, `configs/wp2_pyslam_baseline.json` parameters (D-9)
- `evaluation/trajectory.py`, WP1 files, shared status docs, `tests/test_import_hygiene.py`

**Git workflow.** Branch `feature/yaropolk-all-frame-export`. Independent PR. Self-merge after green checks. Non-blocking review request to Nazar (PLAN WP2 reviewer).

**Work.**
1. Hook per-frame state, causal pose and keyframe creation via the existing bootstrap injection, without patching upstream files.
2. Time `track()`. Measure mapping time only if serial and attributable.
3. Deterministic serialization (UTF-8/LF, 17 significant digits); refuse overwrite.
4. Read-back validation (row count = frozen frames, monotonic timestamps, valid poses).
5. Clean runs `yaropolk_y01_smoke200_<sha7>_01` and `_02` (state determinism).

**Verification.** Unit tests with a fake SLAM object; full suite; opt-in native test; real clean runs; the sparse export from the same run still validates; `git diff --check`; path/secret scan.

**Acceptance criteria.**
- [ ] 200/200 rows with an explicit state; no interpolated or identity placeholder poses.
- [ ] Causal keyframe flags kept distinct from retained-snapshot membership.
- [ ] Timing has scope labels.
- [ ] Two-run comparison reported.
- [ ] Suite + CI green.

**Required output.** Merged PR with code, tests, docs and summary.

**Failure and stop conditions.**
- If the state is unobservable without patching upstream: write `UNKNOWN` with a reason and document it. Never fabricate states.
- If export changes tracking behaviour (compare pose counts with `_02`/`_03`), stop and report.

**One-prompt execution brief.**
```text
Chunk Y-01 (Track Y, Yaropolk): normalized all-frame tracking states, causal keyframes and per-frame SLAM timing.
STANDARD RULES: <paste block from §5>. No downloads authorized.
Branch feature/yaropolk-all-frame-export from exact origin/develop. Environment: my native macOS pySLAM (.venv-pyslam,
upstream 96019cf) per docs/WP2_SETUP.md; fr1/xyz smoke data already local; no GPU.
Without modifying upstream pySLAM source or B0 parameters, extend the bootstrap in src/rt_mapping/slam/smoke.py (+ new
slam/tracking_log.py and contracts/slam.py) to write, per frozen input frame: frame_id, timestamp_s, upstream tracking
state, causal pose T_wc (qx,qy,qz,qw) or empty, is_keyframe_created; and timing.csv with tracking_ms (mapping_ms only
if attributable, else blank + reason). Deterministic serialization, refuse overwrite, read-back validation. You may
adapt ideas from Nazar's local reference branches feature/nazar-assist-wp2-evaluation (816b7f4) and
feature/nazar-assist-yaropolk-pyslam-independent (4484fd7) - never merge them; credit adopted parts as assistance.
Do not edit evaluation/trajectory.py, WP1 files, shared status docs or tests/test_import_hygiene.py (use new
tests/test_import_hygiene_wp2.py). Document in docs/WP2_TRACKING_EXPORT.md and the ARCHITECTURE.md SlamExport section.
From the clean commit run yaropolk_y01_smoke200_<sha7>_01 and _02, compare states/pose counts, write
results/summaries/yaropolk_y01_tracking_smoke200_<sha7>.json. Full pytest, git diff --check. Open PR, wait for checks,
verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### Y-02 — Recorded B0 trajectory evaluation and SLAM resource measurement

**Objective.** A CLI that evaluates any finished merged B0 run with Yulian's evaluator:
- Sim(3) ATE/RPE on the final trajectory (scale labelled evaluation-only);
- a separate retained-keyframe row;
- pose coverage.

A wrapper measures peak RSS, wall clock and effective FPS of the SLAM child process. Both are recorded on a clean smoke run.

**Why it is required.** PLAN WP2 (ATE/RPE), EXPERIMENTS §4.1, §4.4 (peak RAM, cold start).

**Implementer and attribution.** Yaropolk (WP2/WP5 metrics). It reuses `rt_mapping.evaluation.trajectory` (Yulian) unchanged. Nazar's `816b7f4` evaluator is a reference (D-2), credited if adopted.

**Prerequisites.** `origin/develop` (does not need Y-01); native environment; POSIX `resource.getrusage(RUSAGE_CHILDREN)` (no psutil).

**Allowed scope.**
- `src/rt_mapping/evaluation/slam_run.py` (new)
- `scripts/evaluate_wp2_run.py`, `scripts/measure_wp2_resources.py` (new)
- `tests/test_wp2_evaluation.py` (new)
- `docs/WP2_EVALUATION.md` (new)
- `results/summaries/yaropolk_y02_*.json`

**Forbidden scope.** `slam/*.py` (Y-01 owns them in the same wave), `evaluation/trajectory.py`, WP1 files, shared docs.

**Git workflow.** Branch `feature/yaropolk-b0-evaluation`. Independent PR (not stacked on Y-01). Self-merge after green checks.

**Work.**
1. Write the evaluator: read `run.json`, `input_setup/trajectory/trajectory_final.txt` and optionally `sparse/keyframes.npz`; load GT only in evaluation code.
2. Write a derived `run.json` (method B0, `alignment=null`; status `degraded` while states are unknown).
3. Write the resource wrapper: run `scripts/run_wp2_pyslam.py` as a child and record `ru_maxrss` (macOS bytes vs Linux KiB normalized) and wall clock.
4. Runs: `yaropolk_y02_smoke200_<sha7>_01` (under the wrapper) and `yaropolk_y02_eval_smoke200_<sha7>_01`.

**Verification.** Unit tests (exact, noise, Sim(3)); retained-keyframe parity with the merged comparison semantics; full suite; `git diff --check`.

**Acceptance criteria.**
- [ ] Recorded Sim(3) ATE/RPE with an evaluation-only scale label.
- [ ] Peak RSS/wall/FPS with scope labels.
- [ ] Missing telemetry = null + reason, never 0.
- [ ] Suite + CI green.

**Required output.** Merged PR with code, tests, docs and summaries.

**Failure and stop conditions.**
- Wrap Yulian's functions; never modify them.
- If RSS is unavailable, report null + reason; never estimate it.

**One-prompt execution brief.**
```text
Chunk Y-02 (Track Y, Yaropolk): recorded B0 trajectory evaluation + SLAM resource measurement.
STANDARD RULES: <paste block from §5>. No downloads or installs authorized.
Branch feature/yaropolk-b0-evaluation from exact origin/develop (do NOT stack on Y-01). Add
src/rt_mapping/evaluation/slam_run.py + scripts/evaluate_wp2_run.py: read a finished merged B0 run (run.json,
input_setup/trajectory/trajectory_final.txt, optional sparse/keyframes.npz), load TUM GT only in this evaluation code,
call rt_mapping.evaluation.trajectory unchanged for Sim(3) ATE/RPE (scale labelled evaluation-only) plus a separate
retained-keyframe row; write a derived run with a valid run.json (method B0, status degraded while states unknown,
null+reason for missing telemetry). Add scripts/measure_wp2_resources.py: run scripts/run_wp2_pyslam.py as a child and
record peak RSS via resource.getrusage(RUSAGE_CHILDREN) (normalize macOS bytes vs Linux KiB), wall clock, effective FPS.
Do not edit slam/*.py, evaluation/trajectory.py or shared docs. Reference only: Nazar's local 816b7f4 (credit if
adopted; never merge it). Clean runs yaropolk_y02_smoke200_<sha7>_01 (under the wrapper) and
yaropolk_y02_eval_smoke200_<sha7>_01; summaries results/summaries/yaropolk_y02_*.json; docs/WP2_EVALUATION.md.
Tests + full pytest + git diff --check. Open PR, wait for checks, verify allowed-files-only diff, merge, fast-forward
local develop.
```

---

### Y-03 — Tracking success, gap-aware RPE, failure accounting and SLAM latency percentiles

**Objective.** Extend the evaluator to consume the Y-01 export:
- tracking success = OK / all frozen frames;
- lost/initializing segments;
- RPE pairs that do not cross non-OK gaps;
- a failure taxonomy;
- tracking p50/p95 via `rt_mapping.evaluation.timing.summarize_timings`;
- a state timeline plot.

**Why it is required.** EXPERIMENTS §4.1, §4.4; PLAN WP2 failures.

**Implementer and attribution.** Yaropolk (WP2/WP5).

**Prerequisites.** Y-01 and Y-02 merged; Yaropolk's local Y-01 run.

**Allowed scope.**
- `src/rt_mapping/evaluation/slam_run.py`, `scripts/evaluate_wp2_run.py`, `tests/test_wp2_evaluation.py`
- `docs/WP2_EVALUATION.md`
- `results/summaries/yaropolk_y03_*.json`, `results/plots/yaropolk_y03_tracking_states_smoke200.png`

**Forbidden scope.** `slam/*.py` (a Y-01 bug gets a separate `fix/yaropolk-*` PR), Yulian/WP1 files, shared docs.

**Git workflow.** Branch `feature/yaropolk-tracking-evaluation`. Independent PR. Self-merge after green checks.

**Work.** Implement the metrics with the denominator named explicitly (frozen associated RGB-depth frames). Evaluate `yaropolk_y01_smoke200_<sha7>_01` → `yaropolk_y03_eval_smoke200_<sha7>_01`. Plot the timeline.

**Verification.** Unit tests (gaps, all-lost, no pairs → null + reason); full suite; byte-identical re-evaluation.

**Acceptance criteria.**
- [ ] Tracking success with a named denominator.
- [ ] Gap-aware RPE.
- [ ] p50/p95 with the warm-up policy stated.
- [ ] Failure table.
- [ ] Deterministic output.

**Required output.** Merged PR with code, tests, docs, summary and plot.

**Failure and stop conditions.** If the Y-01 export lacks needed fields, fix that first in a separate PR. Never impute states.

**One-prompt execution brief.**
```text
Chunk Y-03 (Track Y, Yaropolk): tracking success, gap-aware RPE, failure accounting and SLAM p50/p95.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: Y-01 and Y-02 merged into origin/develop;
my local run yaropolk_y01_smoke200_<sha7>_01 exists - verify, else stop.
Branch feature/yaropolk-tracking-evaluation. Extend evaluation/slam_run.py + scripts/evaluate_wp2_run.py to read the
all-frame export: tracking success = OK / all frozen associated frames (name the denominator), lost/initializing
segments, RPE pairs not crossing non-OK gaps, failure taxonomy, tracking-time p50/p95 via
rt_mapping.evaluation.timing.summarize_timings (state warm-up policy). Never impute states; null+reason when undefined.
Evaluate into yaropolk_y03_eval_smoke200_<sha7>_01, write results/summaries/yaropolk_y03_eval_smoke200.json and
results/plots/yaropolk_y03_tracking_states_smoke200.png, update docs/WP2_EVALUATION.md. Unit tests incl. edge cases,
full pytest, byte-identical re-evaluation, git diff --check. Open PR, wait for checks, verify allowed-files-only diff,
merge, fast-forward local develop.
```

---

### Y-04 — Split-manifest support in the WP2 runner + frozen per-split B0 configs

**Objective.**
- `slam/setup.py` and `scripts/run_wp2_pyslam.py` verify and prepare any frozen split manifest.
- Three B0 configs differ from `configs/wp2_pyslam_baseline.json` **only** in dataset fields.
- Preflight passes on dev/selection/held-out data **without running SLAM on held-out**.

**Why it is required.** EXPERIMENTS §6 B0 on Dev/Selection/Held-out. It unblocks N-05/N-06 (IC2).

**Implementer and attribution.** Yaropolk (WP2).

**Prerequisites.**
- IC1 passed (N-01 manifests merged).
- Native environment.
- Authorized downloads: the fr1/desk, fr2/desk and fr3 archives from the official TUM URLs recorded in the manifests (~3.7 GB), verified against the manifest SHA-256.

**Allowed scope.**
- `src/rt_mapping/slam/setup.py`, `scripts/run_wp2_pyslam.py`, `scripts/prepare_wp2_baseline.py`
- `configs/wp2_pyslam_{development,selection,heldout}.json` (new)
- `tests/test_wp2_setup.py`
- `docs/WP2_SETUP.md`
- `results/summaries/yaropolk_y04_preflight.json`

**Forbidden scope.** B0 algorithm parameters (D-9), `data/manifests/*` and `data/manifest.py` (use the API read-only), SLAM on held-out, shared docs.

**Git workflow.** Branch `feature/yaropolk-split-support`. Independent PR. Self-merge after green checks.

**Work.**
1. Generalize verification: the C2 rebuild path for smoke; `build_tum_split_manifest` or per-file SHA-256 checks for split manifests.
2. Support "all frames of the split" (documented flag).
3. Make the default run ID sequence-neutral.
4. Write the configs, with a test asserting that the non-dataset fields equal the baseline config.
5. Download and verify the archives; run preflight/prepare only.

**Verification.** Unit tests for both manifest kinds + negative tests; full suite; preflight summaries; config-diff test; `git diff --check`.

**Acceptance criteria.**
- [ ] Smoke behaviour unchanged.
- [ ] Three configs with a dataset-only diff.
- [ ] Preflight ok on 3 splits.
- [ ] Zero SLAM frames on held-out.

**Required output.** Merged PR with code, configs, tests, docs and summary.

**Failure and stop conditions.**
- If a manifest schema change is needed, stop and report; don't edit `data/`.
- If an archive hash mismatches, stop.
- Never change any B0 parameter.

**One-prompt execution brief.**
```text
Chunk Y-04 (Track Y, Yaropolk): split-manifest support in the WP2 runner + frozen per-split B0 configs.
STANDARD RULES: <paste block from §5>. Authorized downloads: the official TUM archives for fr1/desk, fr2/desk and
fr3/long_office_household from the URLs recorded in the frozen manifests, verified against their SHA-256. Nothing else.
Preconditions: data/manifests/tum_fr1_desk_development.json, tum_fr2_desk_selection50.json and
tum_fr3_long_office_heldout.json on origin/develop - verify, else stop.
Branch feature/yaropolk-split-support. Generalize slam/setup.py dataset verification to accept split manifests (use the
merged rt_mapping.data.manifest API read-only; keep smoke behaviour identical), allow "all frames of the split", make
default run IDs sequence-neutral. Add configs/wp2_pyslam_{development,selection,heldout}.json that differ from
configs/wp2_pyslam_baseline.json only in dataset fields, with a test asserting that. Do not change B0 parameters or
data/ files. Run preflight/prepare only on the three splits (NO SLAM on held-out) and write
results/summaries/yaropolk_y04_preflight.json; document in docs/WP2_SETUP.md. Tests + full pytest + git diff --check.
Open PR, wait for checks, verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### Y-05 — B0 development/selection runs, repeatability and wider-sequence failure analysis

**Objective.**
- Clean B0 runs with the all-frame export: dev-573 three times (same seed) and selection-50 once.
- Evaluation via Y-02/Y-03.
- A failure analysis, with causes labelled *гіпотеза* unless proven.

**Why it is required.** EXPERIMENTS §6 B0 on Dev/Selection; repeats; PLAN WP2 tracking failures. It also supplies the second-platform B0 rows.

**Implementer and attribution.** Yaropolk (WP2/WP5).

**Prerequisites.** IC2 passed (Y-04 merged); data local (Y-04); native environment.

**Allowed scope.**
- `results/summaries/yaropolk_y05_*.{json,csv}`, `results/plots/yaropolk_y05_*.png`
- `docs/WP2_BENCHMARK.md` (new)

**Forbidden scope.** Source edits (bugs → separate `fix/yaropolk-*` PR), B0 parameter changes (D-9), held-out runs.

**Git workflow.** Branch `feature/yaropolk-b0-development`. Independent PR. Self-merge after green checks.

**Work.**
1. Run `yaropolk_y05_dev573_<sha7>_{01,02,03}` and `yaropolk_y05_sel50_<sha7>_01`.
2. Evaluate them; report mean ± std across repeats.
3. Write the failure table (frame ranges, hypotheses).
4. Add a cross-platform note against the committed N-02 summary, if merged.

**Verification.** All runs `dirty_worktree=false`; reproducible evaluation; GT only in evaluation.

**Acceptance criteria.**
- [ ] Dev ×3 and selection ×1 recorded, including failures.
- [ ] Per-run tracking success, Sim(3) ATE/RPE, p50/p95 and peak RSS.
- [ ] Failure analysis.
- [ ] No parameter change.

**Required output.** Merged PR with summaries, plots and `docs/WP2_BENCHMARK.md`.

**Failure and stop conditions.** If B0 cannot initialize on selection-50, record it as failed. Do not extend frames or retune.

**One-prompt execution brief.**
```text
Chunk Y-05 (Track Y, Yaropolk): B0 development/selection runs, repeatability and failure analysis.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: Y-04 merged (configs/wp2_pyslam_development
.json and _selection.json on origin/develop); dev/selection data local - verify, else stop.
Branch feature/yaropolk-b0-development. From a clean commit run yaropolk_y05_dev573_<sha7>_01/_02/_03 (same seed) and
yaropolk_y05_sel50_<sha7>_01 with the all-frame export; evaluate each with scripts/evaluate_wp2_run.py. Report tracking
success (named denominator), Sim(3) ATE/RPE (evaluation-only scale), tracking p50/p95, peak RSS, mean +- std over
repeats; failure table with frame ranges, causes labelled "гіпотеза" unless proven. Cross-platform note vs the committed
N-02 summary if merged (never use Nazar's ignored runs). No source edits, no B0 parameter changes (plan D-9), no
held-out. Write results/summaries/yaropolk_y05_*.{json,csv}, plots, docs/WP2_BENCHMARK.md. Open PR, wait for checks,
verify allowed-files-only diff, merge, fast-forward local develop.
```

---

### Y-06 — Held-out B0 with the frozen config

**Objective.** One clean B0 run on fr3 held-out (2488 frames) with `configs/wp2_pyslam_heldout.json` exactly as frozen at IC3, evaluated with the merged evaluator. It is the second-platform B0 row.

**Why it is required.** EXPERIMENTS §6 B0 held-out; cross-platform reproduction.

**Implementer and attribution.** Yaropolk (WP2).

**Prerequisites.** IC3 passed; held-out data local.

**Allowed scope.**
- `results/summaries/yaropolk_y06_*.{json,csv}`, `results/plots/yaropolk_y06_*.png`
- `docs/WP2_BENCHMARK.md` (held-out section)

**Forbidden scope.** Config/source changes; reruns with changed settings.

**Git workflow.** Branch `feature/yaropolk-b0-heldout`. Independent PR. Self-merge after green checks.

**Work.** Verify the config hash equals the frozen hash; run `yaropolk_y06_heldout2488_<sha7>_01` once; evaluate; write the summary, repeating the §1.5 disclosure.

**Verification.** Clean run; hash check; GT only in evaluation.

**Acceptance criteria.**
- [ ] Run recorded (ok/degraded/failed) with metrics or a reason.
- [ ] No tuning; disclosure present.

**Required output.** Merged PR with summary, plot and doc section.

**Failure and stop conditions.** On failure, record and merge the disclosure. A D-5 rerun is allowed only after a documented bug fix, under a new run_id.

**One-prompt execution brief.**
```text
Chunk Y-06 (Track Y, Yaropolk): held-out B0 with the frozen config.
STANDARD RULES: <paste block from §5>. No downloads authorized. Preconditions: configs/benchmark_frozen.json and
configs/wp2_pyslam_heldout.json on origin/develop; fr3 data local - verify, else stop.
Branch feature/yaropolk-b0-heldout. Verify the held-out config hash equals the one recorded in benchmark_frozen.json,
then from a clean commit run yaropolk_y06_heldout2488_<sha7>_01 exactly once and evaluate it with
scripts/evaluate_wp2_run.py. No config/source changes, no tuning; on failure disclose it (plan D-5 rerun rule). Write
results/summaries/yaropolk_y06_*.{json,csv}, a tracking-state plot, and the held-out section of docs/WP2_BENCHMARK.md
(repeat the wp2_heldout2488_4484fd7 disclosure). Open PR, wait for checks, verify allowed-files-only diff, merge,
fast-forward local develop.
```

---

## 7. Integration checkpoints

Each checkpoint is a small technical chunk executed by Nazar with one prompt. It does not wait for anyone's availability: when the listed PRs are merged, it runs.

### IC1 — Contracts and inputs ready

- **Requires merged:** N-01, N-03, Y-01, Y-02.
- **Tests:** full CPU suite on the merged `develop`; CI on the merge commit.
- **Committed artifacts that must exist:**
  - the 4 split manifests;
  - `nazar_n03_selection50_<sha7>_scorecard.json`;
  - `yaropolk_y01_tracking_smoke200_<sha7>.json`, `yaropolk_y02_*.json`;
  - the ARCHITECTURE.md SlamExport contract.
- **Interface contract:**
  - N → Y: manifest schema + `rt_mapping.data.manifest` split API (read-only for Y).
  - Y → N: `contracts/slam.py` CSV schema + `scripts/evaluate_wp2_run.py` CLI (read-only for N).
- **Shared files updated:** `docs/PROJECT_STATUS.md` and `docs/INTEGRATION_STATUS.md`, by Nazar only. Yaropolk's PR-body status rows are copied verbatim.
- **If one track is blocked:**
  - Y-01 blocked → IC1 proceeds with Y-02, and Y-04 still starts. Tracking success is null with a reason until Y-01 lands.
  - N-03 blocked → Y-04 still starts (it needs only N-01).
- **Brief:**
  ```text
  IC1 (Nazar): integration checkpoint 1. STANDARD RULES: <paste block from §5>. Verify N-01, N-03, Y-01, Y-02 are merged
  into origin/develop, else stop. Branch feature/nazar-ic1-status. Run the full CPU suite on origin/develop and record the
  counts and CI run ID. Update only docs/PROJECT_STATUS.md and docs/INTEGRATION_STATUS.md with evidence (commits, PRs,
  run IDs, summaries; Yaropolk's status rows verbatim from his PR bodies; assistance labelled). Open PR, wait for checks,
  verify the diff touches only those two files, merge, fast-forward local develop.
  ```

### IC2 — Development benchmark inputs ready

- **Requires merged:** Y-04 and N-04.
- **Artifacts:** `configs/wp2_pyslam_{development,selection,heldout}.json`, `yaropolk_y04_preflight.json`, `nazar_n04_*.json` (including the D-3 gate result).
- **Shared files:** PROJECT_STATUS/INTEGRATION_STATUS (Nazar).
- **If one track is blocked:**
  - Y-04 blocked → N-05 cannot run B0/P1 on dev; N runs model-only dev50/selection50 rows meanwhile, without editing `slam/`.
  - N-04 blocked → Y-05 proceeds.
- **Brief:**
  ```text
  IC2 (Nazar): integration checkpoint 2. STANDARD RULES: <paste block from §5>. Verify Y-04 and N-04 are merged, else stop.
  Branch feature/nazar-ic2-status. Full CPU suite; record the D-3 gate result from nazar_n04_* and the Y-04 preflight.
  Update only docs/PROJECT_STATUS.md and docs/INTEGRATION_STATUS.md. Open PR, wait for checks, verify the two-file diff,
  merge, fast-forward local develop.
  ```

### IC3 — Protocol freeze (before any held-out run)

- **Requires merged:** N-05 and Y-05.
- **Freeze PR** `feature/nazar-benchmark-freeze` adds:
  - `configs/benchmark_frozen.json`, holding the "Derived freeze" from `docs/DEVELOPMENT_BENCHMARK.md`: model + checkpoint, `process_res`/`resolution_level`, alignment thresholds (unchanged merged defaults), voxel, τ = {0.02, 0.05, 0.10} m, crop = none (as in merged `configs/mapping_comparison.json`), keyframe interval, window or none, confidence threshold or none, SHA-256 of `configs/wp2_pyslam_heldout.json`;
  - `docs/BENCHMARK_PROTOCOL.md`;
  - an EXPERIMENTS.md freeze section;
  - the ADR001 final line.
- **Rule:** N-06/Y-06 runs must record a `git_commit` that contains the freeze commit.
- **If Y-05 is blocked:** freeze with the B0 config as merged (D-9); Y-06 can run later.
- **Brief:**
  ```text
  IC3 (Nazar): held-out protocol freeze. STANDARD RULES: <paste block from §5>. Verify N-05 and Y-05 are merged, else stop
  (if only Y-05 is blocked, proceed with the merged B0 config and note it). Branch feature/nazar-benchmark-freeze. Copy the
  mechanically derived values from docs/DEVELOPMENT_BENCHMARK.md "Derived freeze" into configs/benchmark_frozen.json
  (add the SHA-256 of configs/wp2_pyslam_heldout.json), write docs/BENCHMARK_PROTOCOL.md, add a freeze section to
  docs/EXPERIMENTS.md, and append the final model line to ADR001. No new runs, no fr3 access. Add a test that loads
  benchmark_frozen.json and checks that the referenced configs exist and the hash matches. Full pytest. Open PR, wait for
  checks, verify allowed-files-only diff, merge, fast-forward local develop.
  ```

### Final integration/submission checkpoint

- **Requires merged:** N-06, Y-06, F-N1, F-N2, F-Y1, F-Y2.
- **Tests:** full suite + CI on `develop`; fresh-clone check (F-Y2).
- **Shared files** (Nazar in F-N1): README.md, CLAUDE.md, PROJECT_STATUS.md, INTEGRATION_STATUS.md, `scripts/`, `configs/` and `results/` READMEs.
- **Release:** F-0.
- **If one track is blocked:** the blocked item is listed as a disclosed failure, following the PLAN §6 Plan B rule.

---

## 8. Technical decisions (resolved)

All decisions below are final for this version. They were made from repository evidence, choosing conservative options that keep the merged pipeline working. Changing any of them requires a new plan revision; no chunk waits for a human decision.

**D-1 — Data splits.**
- Decision:
  - smoke = fr1/xyz first 200 (unchanged);
  - development = fr1/desk all 573;
  - development spike = fr1/desk first 50;
  - selection = fr2/desk first 50;
  - held-out = fr3/long_office_household all 2488.
- Evidence: EXPERIMENTS §2 lists exactly these sequences; `docs/DATASET_FREEZE.md` on `5e542d7` reproduces the manifests byte-for-byte. Selection is a 50-frame prefix, as fixed by MODEL_SELECTION §6.

**D-2 — Branch reuse and assisted work.**
- Superseded refs (§1.4) are never merged or cherry-picked wholesale.
- Nazar's WP1 work is ported file-by-file from `5e542d7` (N-01, N-03) and `047992e` (N-04).
- Nazar's WP2 assistance (`816b7f4`, `4484fd7`) is reference material for Y-01/Y-02. Yaropolk adapts it selectively, and adopted parts are credited "assisted by Nazar"; WP2 ownership stays with Yaropolk.
- Nazar's WP3 foundation `fd73d56` is not merged (superseded by Yulian's implementation).
- WP3/WP4 defects get a focused `fix/nazar-*` PR with tests; Yulian is notified, and the fix does not wait on him.

**D-3 — Primary dense model.**
- Decision: the primary is the winner of the pre-registered selection rubric (MODEL_SELECTION §5, `docs/SELECTION_PROTOCOL.md`) on the N-03 clean re-run.
  - With the current evidence that is **UniDepth V2 ViT-L** (`resolution_level` 0): weighted score 4.620 vs 4.299; selection AbsRel 0.0646 vs 0.1145.
  - The other model is the fallback: **DA3METRIC-LARGE** at `process_res` 504.
- **Fallback trigger** (technical, pre-registered): if the primary fails the N-04 pipeline gate (any child run not ok, OOM, model-ID/grid rejection by the unchanged mapping code), the fallback becomes primary for N-05/N-06 with no further decision.
- Both models run on dev/selection in N-05 (the "primary vs fallback" ablation).
- Why this is conservative: it follows the rule the project committed to before measuring. The DA3 path stays unchanged and working.
- Disclosed tradeoffs: UniDepth has a worse selection RMSE (0.450 vs 0.421 m) and higher VRAM (1.80 vs 1.54 GiB).
- Licence state: UniDepth code is CC-BY-NC-4.0 and the checkpoint card declares no separate licence; this is recorded as a limitation only (D-6).

**D-4 — Ablations and selection rules.**
- **In scope** (pre-registered grid for N-05):
  - keyframe interval {1, 2, 5};
  - P1-window `causal_window_frames` {60, 150}, plus 0 = P1-global;
  - confidence retain {100%, 75%, 50%}, with thresholds from dev50 UniDepth predictions only (DA3: skipped, no confidence output);
  - primary vs fallback model;
  - DA3 resolution 384 vs 504 (depth-only evidence ported in N-04).
- **Out of scope:**
  - ICP: not implemented; PLAN §6 Plan B allows dropping it, and adding it would be new WP3 scope;
  - P2 (DUSt3R/VGGT);
  - KITTI;
  - semantics.
- **Held-out configuration** (computed mechanically from dev results only):
  - Among the primary model's P1 variants, take the lowest dev Chamfer-L1.
  - Ties within 1 mm go to the simpler configuration: global over window, larger keyframe interval, no confidence filter.
  - P1-window is used on held-out only if it beats P1-global on **both** dev Chamfer-L1 and dev SE(3) ATE (EXPERIMENTS §6: "required if dev improves").
  - Selection-split rows are reported but not used to choose.
  - Alignment thresholds, voxel size, τ = {2, 5, 10} cm and crop = none stay at the merged defaults (`configs/mapping_comparison.json`, `configs/offline_mapping.json`).

**D-5 — Held-out protocol.**
- fr3 stays the held-out split.
- The failed superseded-runner attempt `wp2_heldout2488_4484fd7` is disclosed in DATASET_FREEZE, HELDOUT_BENCHMARK, WP2_BENCHMARK and FINAL_RESULTS. It produced no metrics and tuned nothing.
- No held-out access before the IC3 freeze is merged.
- Each held-out configuration runs once.
- A rerun is permitted only after a documented code-bug fix merged via its owner's PR, under a new run_id, with both runs reported. Parameters are never changed.
- Held-out results are never used to choose anything.

**D-6 — Licence and release metadata.**
- No project licence is chosen or invented. The current state is recorded in FINAL_RESULTS limitations:
  - the repository has no LICENSE file;
  - pySLAM is GPLv3 (not vendored);
  - DA3 is Apache-2.0;
  - UniDepth code is CC-BY-NC-4.0;
  - weights are not committed.
- Release tag name: `v1.0.0`.
- Demo video: stored in the ignored `results/runs/<demo_run_id>/` with its SHA-256 recorded; only small previews are committed.

**D-7 — Real-time criterion.**
- Input rate is the TUM 30 Hz camera, giving a 33.3 ms frame budget.
- "Real-time" may be claimed only if the measured p95 per-frame end-to-end latency ≤ 33.3 ms **and** effective FPS ≥ 30 with no unbounded backlog, on the stated hardware and resolution.
- Otherwise the system is labelled "offline". "Near-real-time" is not used.
- The current pipeline is sequential and offline, and the model p95 alone already exceeds 33.3 ms on the selection runs, so the expected verdict is "offline". This is not presented as a failure.

**D-8 — Execution model.**
- Every chunk self-merges after its required checks are green and its diff contains only allowed files.
- Owner review is requested for attribution and is non-blocking.
- Original WP ownership and attribution are preserved in docs and the contribution table.

**D-9 — B0 baseline configuration.**
- Frozen as merged: `configs/wp2_pyslam_baseline.json` (pySLAM `96019cf`, mono, ORB2 1000 features, DBOW3, Python core, `-O`, seed 0).
- The per-split configs change only dataset fields.
- If B0 loses tracking or fails on a split, that is recorded as a B0 result. The baseline is not retuned, because changing it would invalidate the B0/P1 shared-pose comparison.

**Removed from the dependency graph:** deadlines, scheduling, presentation duration, team availability, slide-format and storage preferences, and owner review. None of them gates any chunk.

---

## 9. Final integration and submission chunks

These start after N-06 and Y-06 are merged. Order: F-N1 ‖ F-Y1, then F-N2 ‖ F-Y2, then F-0. File sets are disjoint, and each chunk self-merges after green checks.

### F-N1 (Nazar) — Final results table, limitations, reproducibility guide, status docs

- **Scope:**
  - `docs/FINAL_RESULTS.md` (new), `docs/REPRODUCE.md` (new)
  - `results/summaries/final_results.{json,csv}` (new)
  - `docs/PROJECT_STATUS.md`, `docs/INTEGRATION_STATUS.md`
  - `README.md`, `CLAUDE.md`
  - `scripts/README.md`, `configs/README.md`, `results/README.md`
  - `docs/MODEL_SELECTION.md` §7, `docs/EXPERIMENTS.md` results pointer
- **Work:**
  1. Aggregate **committed** summaries only (N-02…N-06, Y-02…Y-06, Yulian's smoke), with both B0 platform rows labelled.
  2. Limitations: map reference approximation, retained-keyframe vs all-frame metrics, repeat count, GPU nondeterminism, the D-6 licence state, the D-7 verdict, every disclosed failure.
  3. Reproducibility guide: fresh clone → CPU tests → smoke pipeline → benchmark commands.
- **Verification:** every number traced to a `run_id`; link check; `git diff --check`.
- **Brief:**
  ```text
  Chunk F-N1 (Nazar): final results table, limitations, reproducibility guide and status docs.
  STANDARD RULES: <paste block from §5>. No downloads. Preconditions: N-06 and Y-06 merged - verify, else stop.
  Branch feature/nazar-final-results. Using ONLY committed results/summaries (cite run_ids), build
  results/summaries/final_results.{json,csv} and docs/FINAL_RESULTS.md (trajectory, depth, map, performance; units,
  alignment mode, hardware, GT rule; both B0 platform rows labelled; all disclosed failures). Limitations incl. plan
  D-6 licence state and the D-7 real-time verdict. Write docs/REPRODUCE.md. Update PROJECT_STATUS.md,
  INTEGRATION_STATUS.md, README.md, CLAUDE.md, scripts/configs/results READMEs and MODEL_SELECTION.md §7. Do not touch
  Yaropolk's docs. Link check + git diff --check. Open PR, wait for checks, verify allowed-files-only diff, merge,
  fast-forward local develop.
  ```

### F-Y1 (Yaropolk) — Presentation materials and contribution table

- **Scope:**
  - `docs/PRESENTATION_OUTLINE.md` (new; INTERIM_REVIEW §2 structure)
  - `docs/CONTRIBUTIONS.md` (new; all three members; each row → PR/commit/run; assisted work labelled with the original owner preserved)
  - `docs/INTERIM_REVIEW.md` checklist
  - `results/plots/yaropolk_slides_*.png` (small)
- **Rules:** every number is copied from a committed summary; B1 is labelled oracle; Sim(3) ATE is not presented as metric scale; no real-time claim beyond D-7.
- **Brief:**
  ```text
  Chunk F-Y1 (Yaropolk): presentation materials and contribution table.
  STANDARD RULES: <paste block from §5>. No downloads. Preconditions: N-06 and Y-06 merged - verify, else stop.
  Branch feature/yaropolk-presentation. Write docs/PRESENTATION_OUTLINE.md (INTERIM_REVIEW §2 structure; every number
  copied from a committed summary with its run_id; oracle B1 labelled; Sim(3) ATE not presented as metric scale; real-time
  wording per plan D-7) with small figures results/plots/yaropolk_slides_*.png, and docs/CONTRIBUTIONS.md (Nazar,
  Yaropolk, Yulian; each row links PR/commit/run; assisted work labelled with original owner). Update the
  docs/INTERIM_REVIEW.md checklist. Do not edit README/PROJECT_STATUS/FINAL_RESULTS. Open PR, wait for checks, verify
  allowed-files-only diff, merge, fast-forward local develop.
  ```

### F-N2 (Nazar) — Demo capture

- **Scope:** `scripts/render_demo.py` (new; matplotlib/Pillow only), `docs/DEMO.md` (new), `results/plots/nazar_demo_*.png` (<1 MB in total). The video/GIF goes in the ignored `results/runs/<demo_run_id>/`, with its SHA-256 and command recorded (D-6).
- **Verification:** reproducible from the run ID; labelled with sequence, method and "offline".
- **Brief:**
  ```text
  Chunk F-N2 (Nazar): demo capture.
  STANDARD RULES: <paste block from §5>. No downloads or installs. Preconditions: N-06 merged (else N-05) - verify.
  Branch feature/nazar-demo. Add scripts/render_demo.py (thin CLI; matplotlib/Pillow only) that renders the fused cloud +
  trajectory of one of MY committed-summary runs into frames and an animation inside a new ignored
  results/runs/<demo_run_id>/; record command and SHA-256 in docs/DEMO.md; commit only small previews
  results/plots/nazar_demo_*.png (<1 MB total). Label sequence, method, "offline". git diff --check. Open PR, wait for
  checks, verify allowed-files-only diff, merge, fast-forward local develop.
  ```

### F-Y2 (Yaropolk) — Fresh-clone reproduction, CI, requirements audit

- **Scope:**
  - `docs/SUBMISSION_AUDIT.md` (new; PROJECT_BRIEF expected results, PLAN §8 DoD and the technical rows of the INTERIM_REVIEW rubric → evidence or gap)
  - `.github/workflows/tests.yml`, only for a verified gap
  - optional consolidation of `tests/test_import_hygiene*.py`
- **Brief:**
  ```text
  Chunk F-Y2 (Yaropolk): fresh-clone reproduction and requirements audit.
  STANDARD RULES: <paste block from §5>. Authorized: creating a NEW venv in a fresh clone and pip-installing the project
  extras ".[dev,plots,filtering]". Preconditions: F-N1 merged - verify, else stop.
  Fresh-clone origin/develop into a new directory; run pytest, run_alignment_smoke.py --plot, run_comparison_smoke.py
  --plot and every CPU command in docs/REPRODUCE.md; record exact outputs. Branch feature/yaropolk-submission-audit: write
  docs/SUBMISSION_AUDIT.md mapping PROJECT_BRIEF expected results, PLAN §8 DoD and the technical INTERIM_REVIEW rubric rows
  to evidence or gaps. Touch .github/workflows/tests.yml or consolidate tests/test_import_hygiene*.py only for a verified
  gap. git diff --check. Open PR, wait for checks, verify allowed-files-only diff, merge, fast-forward local develop.
  ```

### F-0 (Nazar, integration gate) — Release

- **Scope:** a `develop → main` PR plus annotated tag `v1.0.0` on the resulting `main` commit (D-6).
- **Gate:** all final chunks merged, CI green, and every mandatory gap in SUBMISSION_AUDIT either closed or listed as a disclosed failure.
- **Brief:**
  ```text
  Chunk F-0 (Nazar): release. STANDARD RULES: <paste block from §5> PLUS: this prompt authorizes a develop->main PR, merging
  it after required checks pass, and creating and pushing the annotated tag v1.0.0 on the resulting main commit. Verify all
  final chunks merged, CI green on develop, and docs/SUBMISSION_AUDIT.md has no open mandatory gap (or lists it as a
  disclosed failure). Never force-push. Report the merge and tag SHAs.
  ```

---

## 10. Execution board

| Chunk | Person | Wave | Status | Dependencies | Effort | Branch | Output / PR | May run in parallel with | Owner review |
|---|---|---|---|---|---|---|---|---|---|
| C1–C5, WP2 sparse, WP3/WP4 smoke | Nazar / Yaropolk / Yulian | — | DONE | — | — | merged | PR #1–#8 | — | done |
| WP3 foundation `fd73d56`, alt pySLAM runner, wp4/5/6 assists, local `main` | Nazar (assistance) | — | SUPERSEDED | — | — | local only | never merged | — | — |
| N-01 | Nazar | 1 | READY | `origin/develop` | 1 h | `feature/nazar-frozen-splits` | manifests PR | Y-01, Y-02 | non-blocking (Yaropolk) |
| N-02 | Nazar | 2 | READY | `origin/develop` | 2–4 h (Docker build + ~7 min run) | `feature/nazar-pipeline-reproduction` | reproduction PR | Y-01, Y-02, Y-03 | non-blocking |
| N-03 | Nazar | 2 | BLOCKED | N-01 merged | 2 h incl. GPU | `feature/nazar-unidepth-selection` | UniDepth/selection PR | Y-02, Y-03 | non-blocking |
| IC1 | Nazar | — | BLOCKED | N-01, N-03, Y-01, Y-02 merged | 0.5 h | `feature/nazar-ic1-status` | status PR | Y-03 | — |
| N-04 | Nazar | 3 | BLOCKED | N-03 merged, N-02 run | 2 h | `feature/nazar-model-agnostic-pipeline` | pipeline-stage PR | Y-04 | non-blocking |
| IC2 | Nazar | — | BLOCKED | N-04, Y-04 merged | 0.5 h | `feature/nazar-ic2-status` | status PR | — | — |
| N-05 | Nazar | 4 | BLOCKED | IC2 | 3–5 h GPU | `feature/nazar-development-benchmark` | dev benchmark PR | Y-05 | non-blocking (Yaropolk for B0 rows) |
| IC3 freeze | Nazar | — | BLOCKED | N-05 (+ Y-05 or the merged B0 config) | 1 h | `feature/nazar-benchmark-freeze` | freeze PR | — | — |
| N-06 | Nazar | 5 | BLOCKED | IC3 | 3–5 h GPU | `feature/nazar-heldout-benchmark` | held-out PR | Y-06 | non-blocking |
| Y-01 | Yaropolk | 1 | READY | `origin/develop` | 2–3 h incl. 2 runs | `feature/yaropolk-all-frame-export` | export PR | N-01, N-02 | non-blocking (Nazar) |
| Y-02 | Yaropolk | 2 | READY | `origin/develop` | 1.5–2 h | `feature/yaropolk-b0-evaluation` | evaluator PR | N-01, N-02, N-03 | non-blocking |
| Y-03 | Yaropolk | 2 | BLOCKED | Y-01, Y-02 merged | 1.5 h | `feature/yaropolk-tracking-evaluation` | tracking-eval PR | N-02, N-03, IC1 | non-blocking |
| Y-04 | Yaropolk | 3 | BLOCKED | IC1 (N-01 merged) | 2 h + ~3.7 GB download | `feature/yaropolk-split-support` | split-support PR | N-04 | non-blocking |
| Y-05 | Yaropolk | 4 | BLOCKED | IC2 | 3–4 h runs | `feature/yaropolk-b0-development` | B0 dev PR | N-05 | non-blocking |
| Y-06 | Yaropolk | 5 | BLOCKED | IC3 | 2–3 h run | `feature/yaropolk-b0-heldout` | B0 held-out PR | N-06 | non-blocking |
| F-N1 | Nazar | final | BLOCKED | N-06, Y-06 | 2 h | `feature/nazar-final-results` | final docs PR | F-Y1 | non-blocking |
| F-Y1 | Yaropolk | final | BLOCKED | N-06, Y-06 | 2–3 h | `feature/yaropolk-presentation` | presentation/contributions PR | F-N1 | non-blocking |
| F-N2 | Nazar | final | BLOCKED | N-06 (or N-05) | 1.5 h | `feature/nazar-demo` | demo PR | F-Y2 | non-blocking |
| F-Y2 | Yaropolk | final | BLOCKED | F-N1 | 1.5 h | `feature/yaropolk-submission-audit` | audit PR | F-N2 | non-blocking |
| F-0 | Nazar | final | BLOCKED | all final chunks | 0.5 h | `develop → main` | release PR + tag `v1.0.0` | — | — |

**BLOCKED** means technical dependencies only; no row waits for a decision or for administrative information.

**Independence check:**
- Pre-IC1 chunks (N-01, N-02, N-03, Y-01, Y-02, Y-03) depend only on `origin/develop` or same-track predecessors.
- File sets of parallel pairs are disjoint:
  - N-01 vs Y-01/Y-02: `data/…` vs `slam/…`, `evaluation/slam_run.py`.
  - N-02/N-03 vs Y-02/Y-03: new N configs and WP1 code vs Y evaluation files.
  - N-04 vs Y-04: WP1 scripts and N configs vs `slam/setup.py` and `configs/wp2_*`.
  - N-05/N-06 vs Y-05/Y-06: separate summaries and docs.
- Shared status docs are edited only in Nazar's IC chunks and F-N1.
- `tests/test_import_hygiene.py` is not edited before F-Y2.

---

## 11. Recommended starting pair

- **Nazar starts with N-01:** frozen development/selection/held-out manifests on `develop`.
- **Yaropolk starts with Y-01:** all-frame tracking states, causal keyframes and per-frame SLAM timing.

Why this pair gives the highest immediate value:

1. **Both are on the critical path.**
   - N-01 is the only input Y-04 needs, so merging it unblocks every wider B0/P1 run (IC1 → Y-04 → IC2 → N-05 → IC3 → held-out).
   - Y-01 closes the largest open WP2 gap that every status document lists. It feeds tracking success and SLAM latency into every later benchmark.
2. **They are fully independent and can start right now.**
   - Both are READY on `origin/develop` and need no downloads, decisions or the other person's artifacts.
   - N-01 touches only `data/manifests/`, `data/manifest.py`, `scripts/freeze_tum_split.py`, one new test and `docs/DATASET_FREEZE.md`.
   - Y-01 touches only `slam/`, `contracts/slam.py`, its own tests and docs, and the ARCHITECTURE.md SlamExport section.
3. **Nothing stalls.** Each self-merges after green checks. Next, Nazar moves to N-02 (independent of N-01) and Yaropolk to Y-02 (independent of Y-01).
