# UniDepth V2 adapter — WP1 C6

Owner: Назар (бос). Реалізація, CPU-тести та one-frame/20-frame GPU verification готові; team review pending.

## Джерела й identity

- Official code: https://github.com/lpiccinelli-eth/UniDepth/tree/8d8cfe4c7ee15297099983607febf0d4f32eb3d6
- Code license: CC-BY-NC-4.0; academic non-commercial use. Не переносимо upstream-код або ваги до repo; checkpoint card не має окремої license declaration, тому зберігаємо це обмеження й attribution upstream.
- Official model: `lpiccinelli/unidepth-v2-vitl14`, ungated, revision `52b349b514bd8b47642f67ac78cb7b5dc5c51dd9`.
- `model.safetensors`: 1415383604 bytes (~1.42 GB), SHA-256 `ba73d3de735302ccc64a50f1e557122050c4b1893e6060b28dba05d6af3e67c6`.
- `config.json`: 3848 bytes, SHA-256 `09eb0ea8de53a6c9a1d428ac98c79847fe2602ea417701261f3f628099a30816`.
- Config має `pixel_encoder.pretrained=null`; додаткові backbone downloads заборонені. Backend перевіряє config/weights hashes, створює модель і робить strict safetensors load.

## Ізольоване environment

UniDepth декларує NumPy >=2, DA3 використовує NumPy 1.26.4. `.venv` DA3 не змінюється; optional environment усередині ignored `.venv/unidepth`:

```powershell
uv venv --python 3.11 .venv/unidepth
uv pip install --python .venv/unidepth/Scripts/python.exe torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/unidepth/Scripts/python.exe --no-deps -r requirements/wp1-unidepth.txt
uv pip install --python .venv/unidepth/Scripts/python.exe -r requirements/wp1-unidepth-lock.txt
```

Training packages, Linux-only Triton, KNN/patch CUDA extensions не потрібні для `infer`. Warnings про KNN/NystromAttention стосуються evaluation upstream / V1; проєкт оцінює depth власним C4 evaluator. Wandb імпортується upstream для visualization, але adapter не викликає init/login чи telemetry APIs.

Top-level dependencies наведені у wp1-unidepth-runtime.txt, повний перевірений dependency snapshot — wp1-unidepth-lock.txt. Psutil 7.2.2 потрібен для однакових non-null RAM metadata з DA3. На sandboxed Windows за потреби задати TEMP/TMP у власну ignored writable directory перед import (upstream Wandb створює temp-папки навіть без login).

Weights завантажуються явно перед inference: base URL `https://huggingface.co/lpiccinelli/unidepth-v2-vitl14/resolve/52b349b514bd8b47642f67ac78cb7b5dc5c51dd9/`, файли `config.json` і `model.safetensors` у `checkpoints/unidepth-v2-vitl14-52b349b/`. Перевірити hashes з таблиці вище. Inference не має Hub/download викликів.

## Output semantics та K_processed

Підтверджено в official `unidepthv2.py`, `decoder.py`, `utils/camera.py`, `utils/coordinate.py` і `assets/docs/V2_README.md`:

1. `infer` повертає `depth=points[:, -1:]`: camera-z у метрах, не Euclidean radius. Output grid відновлюється bilinear resize і видаленням padding до розміру raw RGB.
2. Camera input — відомий calibrated pinhole, без GT depth/pose. `coords_grid` upstream має half-integer centres; adapter додає 0.5 до cx/cy. `camera.resize` множить K на nominal scalar, хоча image dimensions округлюються вгору до /14. Adapter компенсує camera input так, щоб після цих upstream-операцій K дорівнювала actual per-axis image transform. Геометрію перевіряють CPU-тести для landscape/portrait/padding.
3. `K_processed=FrameRecord.K`: depth повертається на raw grid із calibrated rays. `out['intrinsics']` — незалежний camera-head prediction навіть у calibrated mode. Він зберігається лише як diagnostic metadata, не підміняє K, що використана для rays.
4. Upstream `confidence` — estimated scale-invariant log error, ranking тільки всередині кадру. Для контракту higher=more reliable змінюємо лише знак: `-error`, діапазон (-inf,0]. Це офіційний error output зі зворотним напрямком, без евристичної нормалізації або probability. Якщо output відсутній, confidence=None. Historical runs до 24 жовтня мали reciprocal mapping; їх не змінюємо.
5. Ваги float32, official infer() autocast float16; resolution_level=0, native mode (200k–240k pixels до округлення). Немає median scaling, GT correction чи silent fallback.

PR #4 C5 і PR #5 WP2 merged у develop; поточна local integration повторно використовує їхні contracts/runner. Перед load backend порівнює всі installed UniDepth Python files з pinned Git tree `checkpoints/upstream/UniDepth@8d8cfe4c`; source SHA-256 записується в environment. Missing/mismatched source завершує run помилкою, без downloads. Code checkout потрібен лише для цієї read-only verification. Effective infer dtype — upstream float16 autocast, weights float32.

## GPU verification

- One-frame `c6_unidepth_f1_devicefix`: status=ok, clean local integration commit, calibrated RGB only.
- 20 frames `c6_unidepth_smoke20_a9ccd5d`: status=ok, commit a9ccd5d, dirty_worktree=false, 10 prewarm calls, raw-grid evaluation. AbsRel=0.0380, RMSE=0.0963 m, δ1=0.9905; warm median=76.4 ms, p95=82.5 ms на RTX 5070 Laptop.
- Перший f1 probe `c6_unidepth_f1_fe80b15` failed через `set_device(torch.device('cuda'))` без explicit index. Виправлено у bd8f452; failed run не редагувався.
- Перше порівняння відхилене через RAM=null лише в UniDepth optional environment. Причина підтверджена: psutil відсутній; після встановлення pinned psutil створені нові runs, старі лишаються immutable.
- Canonical paired runs: `wp1_dev50_unidepth_final_f9c181a`, `wp1_selection50_unidepth_final_f9c181a`; timer включає required CPU export результатів, як і DA3. Final scorecards / ADR001 обрали UniDepth primary для course MVP; первісний fallback-role superseded рішенням.
