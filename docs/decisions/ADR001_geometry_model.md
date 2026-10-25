# ADR001 — UniDepth V2 для non-commercial course MVP

Дата: 23 жовтня 2026; integration update 24 жовтня. Owner: Назар (бос). **Локальне рішення реалізації; proposed for team review, external reproduction pending.** Team approval не записане.

## Докази

Frozen protocol commit `7f37d66`, виконаний у clean local integration commits a9ccd5d / f9c181a. 50 exact development кадрів fr1/desk + окремі 50 exact selection кадрів fr2/desk; 10 warm-up calls перед кожним run. Немає median scaling або GT-assisted correction. Per-frame mask hashes та frame identities збігаються для обох кандидатів.

Hardware: RTX 5070 Laptop, 8151 MiB, driver 610.74; Python 3.11.16 / Torch 2.11.0+cu128. DA3 process_res=504, bf16 API; UniDepth native resolution_level=0, fp16 API. Обидва отримують raw RGB640×480 і calibrated K; evaluation на спільній raw сітці. Timer включає необхідний CPU export результату; decode/camera-plan виключені.

| Selection fr2/desk (50) | DA3METRIC-LARGE | UniDepth V2 ViT-L |
|---|---:|---:|
| AbsRel ↓ | 0.114524 | 0.064587 |
| RMSE m ↓ | 0.421077 | 0.449941 |
| MAE m ↓ | 0.231596 | 0.140899 |
| δ1 ↑ | 0.956997 | 0.967088 |
| Warm mean / median ms | 88.02 / 83.19 | 76.68 / 76.45 |
| Warm p95 ms ↓ | 91.49 | 78.30 |
| Peak allocated VRAM GiB ↓ | 1.5449 | 1.7969 |
| Confidence | None | error-derived relative ranking |
| Stability | 50/50 valid | 50/50 valid |
| Weighted score /5 ↑ | 4.3541 | 4.6198 |

Development independently supports the decision: AbsRel 0.094060 vs 0.041152; RMSE 0.188398 vs 0.124743; δ1 0.964910 vs 0.984960; final p95 95.15 vs 78.86 ms; score 4.2010 vs 4.6198.

Машинозчитувані джерела: `results/summaries/wp1_development50_final_scorecard.json`, `wp1_selection50_final_scorecard.json`. Вони містять model/checkpoint identities, configs, full metrics/timing, hardware, environment і SHA-256 source run/metrics/timing. Раніші `*_scorecard.json` без `_final` зберігають попередній timer (без CPU export UniDepth) і superseded цими final summaries.

## Рішення

### Clean integration повтор 24 жовтня

Commit `463b446`, обидві моделі clean на identical selection50:

| Метрика | DA3 | UniDepth |
|---|---:|---:|
| AbsRel / RMSE m / MAE m | 0.114524 / 0.421077 / 0.231596 | 0.064587 / 0.449941 / 0.140899 |
| δ1 | 0.956997 | 0.967088 |
| Warm median / p95 ms | 85.15 / 98.55 | 76.73 / 80.03 |
| First inference ms | 1149.07 | 1087.29 |
| Model load s | 5.63 | 6.57 |
| Peak allocated VRAM GiB | 1.5449 | 1.7969 |

Exact values, weighted score та source hashes: `results/summaries/wp1_integrated_selection50_20261024_scorecard.json`.
Depth bit-identical historical runs на 50/50 кадрах обох models. Warm p95 змінився; це GPU variation, а не improvement від integration. Окремий NumPy audit підтвердив per-frame metrics, mask hashes та weighted scores до 1e-12. First inference не включає Python import/source/hash validation; model load наведено окремо. Висновок незмінний: UniDepth primary, DA3 fallback; external team review pending.

- Primary implementation: `UniDepthV2Adapter`, official `lpiccinelli/unidepth-v2-vitl14@52b349b…`, resolution_level=0, known calibrated pinhole, raw metric depth. Exact assets — configs/model_assets.json.
- Fallback: DA3METRIC-LARGE process_res=504. Він має менше VRAM, кращий selection RMSE і permissive Apache-2.0. Depth-only ablations з local `047992e` не входять у цю integration.
- Confidence threshold не вмикаємо за замовчуванням до map ablation. UniDepth confidence — знак офіційного within-frame error ranking змінено для higher=better; це не probability.

UniDepth виграє за precommitted weighted rubric, але **не за кожною метрикою**: selection RMSE вищий. Код UniDepth має CC-BY-NC-4.0; HF card не декларує окремої checkpoint license. Рішення стосується local non-commercial course experiments, не redistribution або commercial release; license/reproducibility score уже штрафує це обмеження (3 проти 5 DA3). Для permissive deployment лишається DA3; ваги/upstream source не комітяться.

## Межі та перевірки далі

- Два prefixes по 50 сильно корельованих кадрів, один seed; generalization не доведено.
- Internal native resolutions і bf16/fp16 різні та задокументовані; це ready-to-use model/config comparison.
- Held-out fr3/long_office_household заморожений, inference/tuning на ньому не проводився.
- End-to-end mapping/SLAM latency та map quality залежать від WP2/WP3. Current model p95 >33.3 ms при уявному 30 Hz budget; real-time pipeline не заявляємо.
- Юліан (піндос) / Ярополк (дубєнь) мають відтворити smoke й переглянути PRs до team approval.
