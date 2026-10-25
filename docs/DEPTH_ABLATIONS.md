# WP5: незалежні depth-only ablations

Назар (бос), 23 жовтня 2026. Ці результати не є map/completeness/end-to-end benchmark.

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
