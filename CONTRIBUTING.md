# Робочий процес команди

## Branches та дозволи

Працюємо від актуального `develop` в окремій `feature/<owner>-<topic>` або `fix/<topic>` branch. Один PR — одна перевірювана зміна. Перед роботою перевірити dirty files, worktrees і ongoing PRs; чужі зміни, finished runs та дані не перезаписувати.

Commit, push, PR, merge, release/tag, зміна benchmark scope або datasets, installs/downloads та destructive cleanup потребують відповідного явного дозволу. Дозвіл на code edit не означає дозвіл на публікацію. Історичні chunk briefs або D-8 не замінюють поточну інструкцію користувача. `main` не змінювати без окремого дозволу; shared history не переписувати.

Рекомендований reviewer — учасник іншого WP. Merge лише після required CI, перевірки scope/diff та відсутності review blockers; permission може встановити додаткові умови. Template — `.github/PULL_REQUEST_TEMPLATE.md`.

## Ownership та evidence

Назар — WP1/depth і dense benchmark; Ярополк — WP2/SLAM; Юліан — WP3 alignment і WP4 fusion/evaluation. Assistance позначати окремо: авторство коду, owner work package та experiment execution не об'єднувати в один credit. Contribution table і поточний стан — [RESULTS](docs/RESULTS.md).

Перед зміною contracts читати [ARCHITECTURE](docs/ARCHITECTURE.md), перед experiments — [EXPERIMENTS](docs/EXPERIMENTS.md). Нові підсумки повинні посилатися на PR/commit, run ID, config, data/model hashes, hardware і failure/limitations. Finished `run.json` та existing evidence не редагувати; для нового виконання — новий run ID. Неперевірену причину позначати як гіпотезу.

## Перевірка

```bash
python -m pip install -e ".[dev,benchmark,filtering]"
python -m pytest tests -q
python scripts/run_alignment_smoke.py --plot
python scripts/run_comparison_smoke.py --plot
git diff --check
```

Install потрібен лише для нового environment і не виконується автоматично агентом. CPU correctness tests використовують synthetic inputs; модель/GPU/TUM не потрібні. Installed pySLAM test opt-in: `WP2_NATIVE_SPARSE_TEST=1` у налаштованому native runtime (див. REPRODUCIBILITY). Для low-impact docs edits не додавати тести, що лише повторюють текст; перевіряти links, commands і configs. Не запускати дорогі inference/SLAM або held-out reruns без потреби та дозволу.

Definition of Done: interfaces сумісні, units/frames/transform direction documented, happy/failure paths перевірені, run provenance відтворювана, missing metrics мають null+reason, required CI passed. Latency claims потребують hardware, resolution, warm-up, synchronization і scope; real-time criterion визначено протоколом.

## Дані й документація

Не комітити `data/raw/`, checkpoints, environments, full runs/logs, великі PLY/NPZ/video чи secrets. Зберігати маленькі evidence summaries та потрібні figures. Не видаляти failed runs, лише тому що вони failed. Універсальне правило: GT тільки evaluation або labelled B1 oracle, без held-out tuning; GT tolerance frozen 20 ms.

README — основний user-facing guide. Технічні contracts, protocols, reproduction і results мають по одному canonical document. Не створювати новий progress/handoff Markdown для кожної задачі; актуальні результати додавати в RESULTS з provenance. Історичні facts перевіряти на original commit; не переписувати summaries заради перейменування документа.

Presentation/demo і fresh-clone submission audit залишаються окремими deliverables. Active grading requirements — [INTERIM_REVIEW](docs/INTERIM_REVIEW.md). Cleanup PR не означає завершення всього проєкту.
