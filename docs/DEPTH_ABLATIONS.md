# WP5: незалежні depth-only ablations

Назар (бос), 23 жовтня 2026. Ці результати не є map/completeness/end-to-end benchmark.

**N-04 update (25 жовтня 2026).** Файли й три `wp5_*` summaries перенесено з local `047992e` без змін і повторно перевірено (§N-04 нижче). Додано pooled prediction-only thresholds для map ablation і UniDepth smoke P1 з D-3 pipeline gate. Історичні секції нижче описують стан 23 жовтня.

## DA3 resolution

Ті самі 50 frozen development frames fr1/desk, raw metric depth, однакові 640×480 evaluation masks, seed 0, 10 prewarm calls:

| process_res | native grid | AbsRel ↓ | RMSE m ↓ | δ1 ↑ | warm p95 ms ↓ | peak allocated GiB ↓ |
|---:|---|---:|---:|---:|---:|---:|
| 504 | 504×378 | 0.094060 | 0.188398 | 0.964910 | 95.15 | 1.5449 |
| 384 | 378×294 | 0.096122 | 0.212253 | 0.947197 | 84.74 | 1.4244 |

Evidence: `results/summaries/wp5_da3_resolution_development50.json`, source runs `wp1_dev50_da3_a9ccd5d` та `wp5_dev50_da3_r384_a9ccd5d`. Менша resolution зменшила p95/VRAM, але погіршила quality; один run на конфіг, GPU latency має outliers. Це не підстава для зміни зафіксованого selection protocol заднім числом.

Відтворення 384: generic geometry CLI, `--model da3 --manifest data/manifests/tum_fr1_desk_spike50.json --split development --frames 50 --prewarm 10 --process-res 384 --run-id <new-id>`; 504 — default process_res. Числа беруться з metrics/timing; summary перевіряє ті самі frame identities і SHA masks.

## UniDepth confidence

Пороги — prediction-only quantiles (100/75/50%), обрані до GT-scoring. Higher confidence = 1/(1+native error). Quality рахується на retained GT-valid pixels; coverage відносно всіх GT-valid, тому expected trade-off явний.

| Retain requested | GT-valid coverage | AbsRel ↓ | RMSE m ↓ | δ1 ↑ |
|---:|---:|---:|---:|---:|
| 100% | 100% | 0.041152 | 0.124743 | 0.984960 |
| 75% | 80.81% | 0.036673 | 0.094141 | 0.988356 |
| 50% | 54.65% | 0.034753 | 0.080510 | 0.989739 |

Evidence: `wp5_unidepth_confidence_development50.json`. Source `wp1_dev50_unidepth_a9ccd5d` — clean successful early run; його nullable RAM metadata не використовуються для paired selection (цей run не змінений). Threshold ties залишаються; фактичний pixel count записаний.

DA3 не повертає confidence: diagnostic має `status=skipped`, без синтетичної confidence (`wp5_da3_confidence_unavailable.json`).

```powershell
.venv/cpu/Scripts/python.exe scripts/analyze_confidence.py --run results/runs/<source> --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk --output results/summaries/<new-summary>.json
```

## Що потребує WP2/WP3

Keyframe interval у реальному tracking/fusion; P1-raw/global/window; map F-score/completeness і temporal drift. Очікувані artifacts — WP1_HANDOFF.md. Не підмінюємо їх depth-only score і не робимо real-time claim.

## N-04: re-verification, thresholds і UniDepth smoke P1 (25 жовтня 2026)

Branch `feature/nazar-n03-n04`. Implementation commit `5d11ce6`, configs/thresholds commit `8378365`. Усі runs з clean commit (`dirty_worktree=false`), RTX 5070 Laptop.

### Перевірка перенесених чисел

Evidence: `results/summaries/nazar_n04_ported_evidence_check_5d11ce6.json`.

- **DA3 resolution 384/504:** metrics, counts, warm p95 і VRAM у `wp5_da3_resolution_development50.json` збігаються з immutable source runs з різницею 0.0, SHA-256 `run.json` збігаються, paired masks однакові.
- **DA3 confidence:** у всіх predictions `wp1_dev50_da3_a9ccd5d` `confidence=None`; `status=skipped` правильний.
- **UniDepth confidence, rank-equivalence.** Старий run зберігав `c = 1/(1+e)`, поточний adapter зберігає `c = −e`. Функція `−e = 1 − 1/c` строго зростає, тому ранжування pixels однакове, а quantile masks відрізняються лише через float32 ties. Новий clean run `nazar_n04_dev50_unidepth_5d11ce6_01` дає bit-identical depth/valid masks з `wp1_dev50_unidepth_a9ccd5d` на 50/50 кадрах. `analyze_confidence.py` на новому run (`nazar_n04_unidepth_confidence_development50_5d11ce6.json`):

| Retain | `n_pred_valid` ported → rerun | `n_evaluated` ported → rerun | max \|Δ metric\| |
|---:|---:|---:|---:|
| 100% | 15360000 → 15360000 | 11738990 → 11738990 | 0 |
| 75% | 11520012 → 11520008 (−4) | 9486781 → 9486777 (−4) | 3.4e-7 |
| 50% | 7680022 → 7680010 (−12) | 6415175 → 6415164 (−11) | 9.4e-7 |

Старий mapping має менше унікальних значень (12.89 M проти 14.18 M на 50 кадрах), тому на межі quantile лишається більше ties, а ties зберігаються. Висновки таблиці 23 жовтня не змінюються.

### Pre-registered confidence thresholds (D-4)

Джерело — лише predictions dev50 UniDepth (`nazar_n04_dev50_unidepth_5d11ce6_01`, fr1/desk spike50). GT не відкривався. Значення pooled по всіх valid pixels 50 кадрів, `numpy.quantile` linear; fusion зберігає pixels з `confidence >= threshold`:

| Retain | Quantile | Threshold (`−error`) | Retained on dev50 |
|---:|---:|---:|---:|
| 75% | 0.25 | −0.6916478276252747 | 75.00003% |
| 50% | 0.50 | −0.6456854343414307 | 50.00003% |

`analyze_confidence.py --pooled-thresholds --run <run> --output <json>` → `results/summaries/nazar_n04_confidence_thresholds_5d11ce6.json`. Пороги записано в `configs/mapping_comparison.nazar.confidence.json` і `configs/pipeline.nazar.smoke200.unidepth.json` до будь-якого P1 run (commit `8378365`).

### UniDepth smoke P1 і D-3 pipeline gate — **FAIL**

Run `nazar_n04_e2e_smoke200_unidepth_8378365_01`, запущений один раз з окремого runtime clone (layout з N-02). SLAM stage reused: `nazar_n02_e2e_smoke200_0fc564f_02.slam` без копіювання, SHA-256 `run.json` `2e4afa27…` збігається з N-02 summary, усі 21 файли stage byte-identical до і після run.

| Stage | Status |
|---|---|
| SLAM (reused N-02) | ok |
| Geometry UniDepth V2, 200 frames | ok: AbsRel 0.0409, RMSE 0.121 m, δ1 0.985 (raw metric, evaluation-only GT); warm median/p95 78.5/87.7 ms; peak VRAM 1.80 GiB |
| Alignment/fusion/comparison | **не стартували** |
| Pipeline | **failed**: `unsupported_preprocess: prediction must declare its pixel grid` |

- **Gate (plan D-3):** model-ID check 18/18 keyframes ok, OOM немає, але незмінний `alignment/correspondences.py:prediction_grid` відхилив grid усіх 18 keyframes. UniDepth adapter не декларує `pixel_grid`/`intrinsics_convention`; `raw_distorted` виводиться лише для `library=depth_anything_3`. Це "grid rejection by the unchanged mapping code", тобто **gate fail**.
- **Рішення (механічне, D-3):** fallback trigger спрацював. **Primary для N-05/N-06 — DA3METRIC-LARGE `process_res=504`**, без окремого рішення. UniDepth лишається другою моделлю в N-05 primary-vs-fallback ablation.
- **Rerun не робився.** Навіть з виправленим metadata gate на цьому SLAM stage не пройшов би: keyframe 16 (frame 195) не має GT pose у межах 20 ms (найближчий за 40.8 ms). Comparison впав би так само, як у N-02, незалежно від моделі. Tolerance не змінено, keyframes не відкидались.
- **Confidence ablation:** map children не запускались. Coverage порогів на smoke predictions (GT-free): 73.7% / 43.9% valid pixels на 18 keyframes, 71.2% / 40.6% на всіх 200 кадрах.
- **Наступний крок (не в цьому PR, гіпотеза щодо обсягу):** окремий focused fix у `adapters/unidepth_v2.py` (Nazar), щоб declare `pixel_grid="raw_distorted"` та `intrinsics_convention="pixel_centers_integer"`, з regression test через `prediction_grid`. Без нього UniDepth rows у N-05 впадуть так само.

Evidence: `results/summaries/nazar_n04_e2e_smoke200_unidepth_8378365.json`. Real-time claim немає: це component latency, UniDepth p95 > 33.3 ms (D-7).
