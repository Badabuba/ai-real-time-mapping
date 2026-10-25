# Frozen TUM inputs

Owner: Назар (WP1/WP0 data). Заморожено 23 жовтня 2026 на локальній WP1 гілці (`58f3e7a`, консолідовано в `6fa2f55`/`5e542d7`); перенесено на `develop` у chunk N-01 (`docs/TWO_PERSON_COMPLETION_PLAN.md` §5) з base `origin/develop` = `1041942191428b7c290698fb7c78026ef995e276`. Нові manifests не змінюють historical fr1/xyz manifest або smoke split.

## Splits

Вибір split остаточний для поточної версії (план, рішення D-1). Зміна потребує нової ревізії плану. Перелік sequence із proposal (`EXPERIMENTS.md §2`) не змінено.

| Manifest | Роль | `splits` key | Кадри | Archive bytes | SHA-256 archive |
|---|---|---|---:|---:|---|
| tum_fr1_xyz.json | smoke | `smoke` | 200 із 792 associations | 448204271 | a0236d97b8c30cd93b653656d2b6c293ff7c982a4130ef2a1a8beecdb124ef98 |
| tum_fr1_desk_development.json | development | `development` | усі 573 | 344011403 | e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c |
| tum_fr1_desk_spike50.json | development spike | `development` | перші 50 із 573 | 344011403 | e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c |
| tum_fr2_desk_selection50.json | selection | `selection` | перші 50 із 2893 | 1893351095 | 1a0756d72510a26e26e2a02bf0b6c69c2796619fca531e176fc2e5110173807c |
| tum_fr3_long_office_heldout.json | held-out | `held-out` | усі 2488 | 1483556251 | c7cd8e1afb87c80e5744a356214819b110fa09b4744fa4ba0cc2382f9ba59e9c |

Spike50 — це exact prefix (frame_id 0..49) development manifest; роль "spike" задана назвою файла і цією таблицею, а `splits` key лишається `development`.

`tum_fr3_long_office_heldout.json` має ~1.09 MB (1089987 bytes): це лише manifest з timestamps, repo-relative paths і SHA-256 файлів, не дані. Raw TUM дані, як і раніше, лежать тільки в ignored `data/raw/`.

Архіви отримано з офіційних TUM links: https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download . Source URL записаний у кожному manifest. Нові manifests додатково містять SHA-256 кожного вибраного RGB/depth файла та `rgb.txt`/`depth.txt`; timestamps та association rule походять із C1 loader (20 ms, greedy one-to-one). Усі paths — repo-relative POSIX; абсолютних або user-specific paths немає.

`MODEL_SELECTION.md §6` вимагає 50 development кадрів, тоді як `EXPERIMENTS.md §2` виділяє окрему selection sequence. Зберігаємо обидві вимоги: спочатку 50-frame spike на fr1/desk, потім підтвердження вибору на тих самих exact 50 fr2/desk кадрах для обох моделей.

## Held-out

Held-out лише заморожено: freezing читає тільки bytes файлів для SHA-256. До merge protocol freeze (IC3) на fr3 не запускається depth/map inference, P1 і не рахуються GT-based metrics; held-out ніколи не використовується для tuning або вибору (план, D-5).

Disclosure: run `wp2_heldout2488_4484fd7` (superseded альтернативний pySLAM v2.2.1 runner Назара, clean commit `4484fd7`; не merged baseline `96019cf`) спробував B0 на fr3 і **failed** всередині upstream `local_mapping.py` (`TypeError: 'int' object is not iterable`). Він не дав trajectory і жодних metrics, і нічого за ним не налаштовувалось. Тому fr3 лишається valid held-out split.

## Відтворення

Команда для перевірки одного manifest після download/extraction із кореня repo:

```powershell
.venv/Scripts/python.exe scripts/freeze_tum_split.py --sequence-dir data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk --archive data/raw/tum_rgbd/rgbd_dataset_freiburg1_desk.tgz --archive-url https://webshare.cvg.cit.tum.de/g/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_desk.tgz --split development --frames 50 --output data/manifests/tum_fr1_desk_spike50.json --check
```

Для інших manifests: sequence/archive/source з відповідного JSON, `--split` із колонки `splits` key; `--frames 50` лише для двох prefix50. Без `--frames` — уся sequence. `--check` порівнює bytes і нічого не пише; створення через `open('x')` відмовляється перезаписувати існуючий manifest. `--data-repo-root` дозволяє читати наявні дані з іншого локального checkout (наприклад, з git worktree без `data/raw/`), не записуючи абсолютні paths у manifest.

Перевірка N-01 (25 жовтня 2026): `--check` byte-identical для всіх чотирьох manifests; повторна генерація в окремий каталог дала ті самі SHA-256; `build_tum_manifest.py --check` для fr1/xyz без змін.
