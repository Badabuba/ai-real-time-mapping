# Проміжна презентація (5 хв) і демо

Юліан, 25 жовтня 2026. Deck і демо зібрані лише з committed evidence та одного перевіреного локального run. **Offline research prototype**: жоден слайд, відео чи текст не заявляє real-time.

- **База:** `origin/develop` `242c0cb` (merge PR #29). Merged PR #1–#29. Branch створено від `55392d3`, перед комітом fast-forward на `242c0cb`; PR #29 змінює лише SLAM preflight/evaluation code і не впливає на жоден використаний артефакт.
- **Held-out fr3 не відкривався.** Нові held-out evidence не створювались. ML-моделі, SLAM і fusion не перезапускались: демо — read-only replay записаних артефактів.

## Файли

| Файл | Що це |
|---|---|
| `AI_Real_Time_Mapping_Midterm.pptx` | 6 слайдів 16:9, speaker notes з джерелами; відео вбудоване (`ppt/media/media1.mp4` = `assets/mapping_demo.mp4`, SHA-256 однаковий) |
| `AI_Real_Time_Mapping_Midterm.pdf` | PDF fallback з PowerPoint; на слайді 4 — постер-кадр відео (фінальний стан усіх чотирьох панелей) |
| `MIDTERM_SCRIPT_UA.md` | дослівний текст, спікери, таймінг, коротка версія, відповіді на питання |
| `assets/mapping_demo.mp4` | демо 31.0 с, 1280×720, H.264 High, 30 fps, без звуку, 4 146 773 B |
| `assets/mapping_demo_thumbnail.png` | постер відео (кадр 199) |
| `assets/final_dense_map.png` | фінальна карта P1-global (слайд 1) |
| `assets/architecture.png` | рендер слайда 2 (native diagram) |
| `assets/sparse_dense_oracle.png` | B0 landmarks / P1-global / B1 oracle, той самий вигляд |
| `assets/depth_comparison.png` | кадр 100: RGB, DA3 depth, GT depth і \|pred − GT\| (GT — evaluation only) |
| `assets/failure_analysis.png` | кадри 80, 72, 84 (найгірші за U-01): ті самі панелі |
| `assets/demo_provenance.json` | SHA-256 вхідних артефактів і всіх виходів, keyframes, scale, параметри відео |
| `build_deck.py`, `check_script.py`, `export_pdf.ps1` | збірка PPTX, хронометраж, експорт PDF/PNG |
| `../../scripts/render_midterm_demo.py` | рендер відео і зображень |

Logo UCU/команди в repo немає, тому logo не використано.

## Відтворення

Потрібні: локальний ignored run `results/runs/yulian_tum_e2e_f200_20261025_01` (clean `4952e37`), `data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz`, FFmpeg, Python з `numpy`, `Pillow`, `matplotlib` (+ `python-pptx` для deck). Project `.venv` не змінювався; використано окремий тимчасовий uv environment.

```powershell
python scripts/render_midterm_demo.py --run results/runs/yulian_tum_e2e_f200_20261025_01 `
  --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_xyz --manifest data/manifests/tum_fr1_xyz.json `
  --output-dir presentation/midterm/assets --work-dir <new empty dir for PNG frames>
cd presentation/midterm
python build_deck.py
python check_script.py
powershell -File export_pdf.ps1 -Pptx <abs path>.pptx -Pdf <abs path>.pdf -PngDir <dir>   # потрібен PowerPoint
```

Рендер нічого не перезаписує. Він повторює записаний P1-global fusion loop (`mapping_run.run_mapping`: ті самі keyframes, scale, voxel 2 см) і зупиняється, якщо отримана карта не дорівнює записаному `map.npz` **побайтово** (перевірка пройшла: 72 887 вокселів). Колір вокселів — середній RGB keyframes, лише для показу. Повторний рендер дав побайтово той самий MP4.

Опційний live view після презентації (не обов'язковий): відкрити локальний `…/methods/yulian_tum_e2e_f200_20261025_01.comparison.global/map.ply` (72 887 точок, метри) у будь-якому PLY viewer. PLY не комітиться.

## Джерело кожного зображення

| Візуал | Слайд | Run / файл |
|---|---|---|
| Фінальна карта, відео, постер | 1, 4 | `yulian_tum_e2e_f200_20261025_01` (clean `4952e37`, status ok, усі stages ok): SLAM `….slam/sparse/{keyframes,landmarks}.npz`, `input_setup/trajectory/trajectory_online.txt`; depth `….geometry/predictions/*.npz` (DA3METRIC-LARGE, **process_res 384**, bf16); scale і карта `….comparison/methods/….global/{alignment.json,map.npz}` |
| B1 oracle карта | asset | той самий run, `methods/….oracle/map.npz` |
| GT depth на depth/failure панелях | asset | `data/raw/…/depth/*.png` (/5000, nearest на сітку prediction), лише evaluation |
| Діаграма | 2 | native shapes (`build_deck.py`), за `docs/ARCHITECTURE.md` |
| Charts | 3, 5 | native PowerPoint charts, значення з таблиці нижче |

Tracking state у відео недоступний: run передує Y-01 export. Показано лише, чи є online pose для кадру (197/200) і чи кадр став retained keyframe.

Недоступні візуали і заміни: окремого «sparse → dense» відео немає, його роль виконує `sparse_dense_oracle.png`. Live viewer не використовувався: Open3D тут не встановлено, тому замість нього є rotation segment у відео.

## Джерело кожного числа

| Число на слайді / в тексті | Значення в джерелі | Джерело |
|---|---|---|
| 22 keyframes, 72 887 вокселів, scale 1.19 | 22; 72887; 1.1920834129618625 | `demo_provenance.json`; `results/summaries/yulian_u03_robust_smoke200_cc7a4d9.csv` (`map_voxels`); `docs/ROBUST_FUSION.md` §2.3 |
| DA3 504 dev: AbsRel 0.082 / RMSE 0.163 м / p95 97.9 ms | 0.08189 / 0.16258 / 97.865 | `results/summaries/nazar_n05_model_only_0dc5f7f.csv` |
| UniDepth dev: AbsRel 0.083 / RMSE 0.137 м / p95 86.4 ms | 0.08267 / 0.13735 / 86.423 | той самий CSV |
| B0 dev: 430/573 = 0.750 | `tracking_success` 0.75044, `matched_poses` 430 | `results/summaries/nazar_n05_benchmark.json`, run `nazar_n05_dev573_b0eval_cd64251_01` |
| ATE 0.0195 м (Sim(3), evaluation only) | 0.019530 | там само (`ate_rmse_m`, final trajectory) |
| SLAM track p50 611 ms / p95 2312.5 ms | 611.38 / 2312.47 | там само (`warm_p50_ms`, `warm_p95_ms`) |
| бюджет 33.3 ms | 1000/30 | D-7, `docs/DEVELOPMENT_BENCHMARK.md` §8 |
| Chamfer-L1 B0 0.1377 / P1-global 0.0887 / B1 0.0329 м | 0.137738 / 0.088659 / 0.032900 | `results/summaries/yulian_u03_robust_smoke200_cc7a4d9.csv` |
| per-frame anchored 0.1051 м | 0.105136 | там само |
| F@5 см 0.480 → 0.407 | 0.479970 → 0.406996 | там само |
| точність B0 4.9 см проти P1 9.2 см; ≈ тисяча точок | 0.04937 / 0.09239 м; 1 038 eval points | там само |
| узгодженість зі SLAM ↑ (у notes 0.0388 → 0.0301 м) | pooled withheld median | `results/summaries/yulian_u02_anchor_gate_smoke200_2e6fad5.json`, `docs/ROBUST_FUSION.md` §3.2 |
| UniDepth dev map Chamfer 0.0447 проти DA3 0.1057 (Q&A) | 0.04467 / 0.10574 | `docs/DEVELOPMENT_BENCHMARK.md` §5, `results/summaries/nazar_n05_benchmark.csv` |
| held-out: зупинка на preflight, 0 SLAM frames, без метрик | — | `docs/HELDOUT_BENCHMARK.md`, `results/summaries/nazar_n06_heldout2488_e561d8c.json` |

Жодне число не вигадане й не перераховане з GT для презентації. Округлення: 3 значущі цифри в мові й 4 знаки на charts.

## Розбіжності між джерелами

1. **process_res.** Smoke-карта (слайди 1, 4, 5) — DA3 **384** (C5 default у run `4952e37`), а frozen primary для dev/held-out — **504**. Слайди підписують це явно; smoke і dev числа не змішуються в одному chart.
2. **Latency B0.** N-05 (машина Назара, Docker Python core): track p50/p95 611/2312 ms. Y-05 Ярополка (`yaropolk_y05_benchmark.csv`, 3 dev runs): p95 1221–1339 ms, tracking 0.750–0.766. На слайді — N-05 (той самий SLAM stage, що й development benchmark P1); висновок «offline» однаковий. Розкид між повторами показує недетермінізм pySLAM.
3. **Held-out статус змінився після брифу.** Обидва preflight fixes уже merged: GT boundary (PR #27) і partial-GT coverage (PR #29, 25.10 20:38 UTC). N-06 rerun ще не запускався. Крім того, merged PR #28 містить **B0-only** held-out run Ярополка (Y-06, `results/summaries/yaropolk_y06_retry.json`, status ok). Повного P1 held-out (N-06 rerun) ще немає. Тому за брифом held-out метрики на слайдах не показані; Y-06 згадано лише в Q&A, без чисел. Якщо команда вирішить показувати Y-06 як B0-only, числа брати лише з того summary.
4. **`docs/PROJECT_STATUS.md` застарів** (demo/presentation «planned», 472 tests). Deck спирається на summaries і run artifacts, а не на цю таблицю; файл не змінено, бо він належить Назару.
5. **Y-01 all-frame tracking export** (PR #11) зробив Юліан як assistance у WP2, хоча за планом це chunk Ярополка. У Q&A це вказано за авторством PR.

## Тривалість

`python check_script.py` рахує слова блоків «Говорить» і бере повільнішу з двох оцінок: 125 слів/хв або 4.6 складів/с (голосні; англійські терміни дають завищення). Додає 5 × 1.5 с на зміну спікера і 2 с на старт відео. Слайд 4 триває щонайменше 31 с відео.

| Версія | Слова | Оцінка |
|---|---:|---:|
| Повна | 555 | **4:49** (лише за 125 слів/хв ≈ 4:36) |
| Коротка аварійна | 347 | **3:12** |

Це розрахунок, не запис голосу; українського TTS на машині немає. Перед виступом провести дві репетиції з таймером. Якщо повна версія > 4:50, переходити на коротку.

## Перевірки

- PPTX: `validate.py` (pptx skill) пройшов; відкрито в PowerPoint 16.0 (COM). Video shape: `MediaType=3`, `IsEmbedded=True`, `Length=31000 ms`. Відносне посилання `assets/mapping_demo.mp4` резолвиться від теки PPTX.
- PDF експортовано PowerPoint. Усі 6 сторінок переглянуто як зображення: шрифт лише Calibri, без overflow чи перекриттів, постер-кадр на сторінці 4.
- MP4: `ffprobe` (h264 High, 1280×720, 30/1, 930 frames, 31.0 s); `ffmpeg -f null` декодує без помилок; ключові кадри переглянуто.
- Charts: осі від 0, лінійні, одиниці в назвах.

## Що змінити, якщо held-out rerun завершиться успішно

Числа брати лише з нового committed summary (`results/summaries/nazar_n06_heldout2488_*` і B0 evaluation). Протокол не змінювати.

1. `build_deck.py`, слайд 6:
   - «Обмеження», 5-й пункт → `"Held‑out fr3 (2488 кадрів): run <run_id>, див. HELDOUT_BENCHMARK"`;
   - «Далі», перші два пункти → `"Аналіз held‑out результатів (frozen config, без tuning)"` і `"Порівняння з dev: чи зберігся висновок dense > sparse"`;
   - notes слайда 6: додати summary-файл і run ID.
2. Якщо команда хоче held-out число на слайді 5: додати третій chart або підпис `Held‑out Chamfer-L1 P1-global / B0 / B1` з того summary, з позначкою «held-out, DA3 504, keyframe 2». Smoke chart не змінювати.
3. `MIDTERM_SCRIPT_UA.md`, слайд 6 і коротка версія: речення про held-out замінити одним реченням про результат, у межах того ж обсягу слів. Потім `python check_script.py` має дати ≤ 4:50 / ≤ 4:15. Q&A «Що не вийшло на held-out?»: додати run ID успішного rerun, перший failed run лишити як disclosure.
4. Цей README: оновити §«Розбіжності» п. 3 і таблицю чисел.
5. `python build_deck.py` → `export_pdf.ps1` → переглянути сторінку 6 → комміт у цей draft PR.
