# Frozen held-out benchmark protocol (IC3)

Назар (бос), 25 жовтня 2026. Integration checkpoint IC3 з `docs/TWO_PERSON_COMPLETION_PLAN.md` §7. Machine-readable джерело: `configs/benchmark_frozen.json`; test `tests/test_benchmark_frozen.py` перевіряє hashes і узгодженість.

## Передумови

- N-05 merged: PR #24, merge `ef5e682` (Derived freeze у `docs/DEVELOPMENT_BENCHMARK.md` §7).
- Y-05 merged: PR #23 (`f649e34`). B0 config не змінювався (D-9).
- Y-04 merged: PR #19 (`422172a`), `configs/wp2_pyslam_heldout.json`. Held-out preflight у Y-04 був explicitly skipped (дані на машині Ярополка відсутні); preflight виконує SLAM stage у N-06 на машині Назара.
- До merge цього freeze fr3 не відкривався: жодного inference, SLAM, GT reading чи metric.

## Frozen values

| Field | Value |
|---|---|
| Model | DA3METRIC-LARGE @ `4010e39f…bd594e`, checkpoint SHA-256 `bbea5b0b…324776`, bfloat16, 10 prewarm calls, seed 0 |
| `process_res` | 504 (D-3 fallback trigger; не переглядається) |
| P1 best config | keyframe interval 2; P1-window none; confidence none (DA3 без confidence) |
| Alignment/fusion | `configs/offline_mapping.json` (merged defaults), SHA-256 у JSON |
| Map evaluation | τ = {0.02, 0.05, 0.10} m, crop none, voxel 0.02 m |
| GT association | 20 ms; keyframes без GT pose виключаються і записуються (PR #21) |
| B0 | `configs/wp2_pyslam_heldout.json` (SHA-256 у JSON), pySLAM `96019cf`, Docker `rt-mapping-wp2:96019cf` |
| B0 evaluator | `scripts/evaluate_wp2_run.py` defaults (20 ms, RPE delta 1, warm-up 1) + `--plot` |
| Held-out input | `data/manifests/tum_fr3_long_office_heldout.json`, split `held-out`, 2488 frames |
| Methods | B0, B0-shared-scale, B1-oracle (labelled), P1-raw, P1-global, P1-keyframes-2 |
| Runtime guards | SLAM `--timeout 14400`, pipeline `timeout_s` 14400 (не algorithm parameters) |

## N-06 procedure

1. `configs/pipeline.nazar.heldout.json` = `benchmark_frozen.json` → `heldout.pipeline_config` байт-у-байт за JSON-значенням (test перевіряє рівність; scripted diff має бути порожнім).
2. З clean commit, що містить цей freeze: `scripts/run_pipeline.py --config configs/pipeline.nazar.heldout.json --run-id nazar_n06_heldout2488_da3_<sha7>_01` — **один раз**.
3. `scripts/evaluate_wp2_run.py --source-run <SLAM stage> --groundtruth <fr3>/groundtruth.txt --run-id nazar_n06_heldout2488_b0eval_<sha7>_01 --plot`.
4. Performance: SLAM track p50/p95, model p50/p95, alignment/fusion times, total wall clock, effective FPS = 2488 / wall, peak VRAM, peak RAM де виміряно; verdict за D-7.

## Правила

- Held-out результати нічого не вибирають і не змінюють (model, thresholds, SLAM, keyframes/window/confidence, alignment, evaluator).
- Rerun лише після documented code-bug fix, merged через PR власника, з новим run_id; обидва runs звітуються (D-5).
- Failure або negative result — фінальне evidence.
- Disclosure: superseded runner `wp2_heldout2488_4484fd7` failed (upstream `local_mapping.py`), без trajectory/metrics, нічого не tuned.
