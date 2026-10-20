# Робочий процес команди

## 1. Git workflow

- main має залишатися відтворюваним; робота йде в коротких branches.
- Рекомендовані назви: feature/nazar-model-inference, feature/yaropolk-pyslam-baseline, feature/yulian-sim3-alignment, fix/<issue>.
- Один PR — одна перевірювана зміна. Не змішувати setup SLAM, model swap і нову метрику.
- PR має reviewer з іншого work package.
- Перед merge owner додає evidence у PR і оновлює docs/PROJECT_STATUS.md.
- Не force-push у shared main і не комітити dataset/checkpoints/secrets.

## 2. PR template у тексті

```markdown
## Goal

## Changes

## How to reproduce

## Evidence
- config/run_id:
- metrics/artifacts:
- environment:

## Limitations / failures

## Checklist
- [ ] tests/smoke run pass
- [ ] units, coordinate frames and transform direction documented
- [ ] no dataset/checkpoints/secrets committed
- [ ] PROJECT_STATUS updated
```

## 3. Definition of Done для коду

- є command/config для відтворення;
- input/output відповідає ARCHITECTURE.md;
- units/shapes/coordinate frames перевіряються assertions/tests;
- run manifest містить git revision, dataset, model/config і hardware;
- happy path має smoke test;
- failure повертає status/reason, а не тихо пропускає кадр;
- для performance claim є warm-up, synchronization і p50/p95;
- reviewer реально запустив smoke case або пояснив, чому це неможливо.

## 4. Дані та артефакти

- data/raw, checkpoints і великі PLY/NPZ/відео ігноруються Git.
- У repo зберігаються download instructions, checksums/manifests, configs, невеликі CSV/JSON summaries та compressed preview images.
- Кожен результат має run_id. Файли без run manifest не використовуються у headline table.
- Якщо потрібен Git LFS/DVC/Drive, команда спочатку узгоджує один спосіб; не додаємо три паралельні системи.

## 5. Комунікація

На короткому sync кожен відповідає трьома рядками: що завершено з evidence; що блокує; який наступний deliverable і дата. Рішення, які змінюють baseline, dataset split, metric або MVP, фіксуються в decision log.
