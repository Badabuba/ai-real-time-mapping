# WP2: all-frame causal tracking export (Y-01)

Y-01 continuation за `TWO_PERSON_COMPLETION_PLAN.md`. Original WP2 owner — Ярополк; реалізація та перевірка цього PR — Юліан/Codex як assistance. Existing WP3/WP4, baseline parameters і upstream pySLAM source не змінюються.

## Артефакти

Новий `run_wp2_pyslam.py` run автоматично записує в корені run directory:

- `trajectory_all.csv`: **один рядок на кожний frozen input frame**, включно з initialization/LOST; frame_id, timestamp_s, tracking_state, state_reason, tx/ty/tz/qx/qy/qz/qw, pose_reason, is_keyframe_created, created_keyframe_frame_ids, keyframe_reason, error.
- `timing.csv`: frame_id, timestamp_s, tracking_ms, mapping_ms, mapping_reason, total_ms, total_reason.
- `tracking_export.json`: schema `rt_mapping.slam_tracking_export/v1`, counts, SHA-256 обох CSV та precise pose/timing/keyframe semantics.

Serialization: UTF-8, LF, floats із 17 significant digits, fixed columns, canonical quaternion sign. Existing files не перезаписуються. Після normal shutdown CSV перечитуються, hashes/counts/IDs/timestamps/poses перевіряються проти frozen frames. Неповне покриття або malformed artifact означають failed run. `UNKNOWN`, observer errors або missing OK pose означають degraded run із причиною. Часткові CSV зберігаються при failure.

## Що саме спостерігається

Bootstrap обгортає pinned Python-core `Slam.track`, `Map.add_keyframe` та `Slam.quit`, викликаючи original methods і зберігаючи їхні return values/exceptions. GT не читається observer-ом. Запис flush-иться після кожного кадру, бо upstream завершує процес через `os._exit`.

- **State:** native `tracking.state.name` після track call; стандартні NO_IMAGES_YET / NOT_INITIALIZED / OK / LOST / RELOCALIZE / INIT_RELOCALIZE. Якщо state не спостерігається — UNKNOWN + reason, не припущення OK.
- **Pose:** `tracking.f_cur.Twc()` копіюється безпосередньо після успішного OK call з matching timestamp. Missing/non-OK/stale/invalid pose → сім порожніх полів і reason. Немає interpolation, identity placeholders або підстановки final poses.
- **World/units:** online upstream world, monocular SLAM units. Це causal pose у момент спостереження, **не** optimized final trajectory і **не** normalized world stopped sparse snapshot. Після наступних BA/loop closure log не переписується. Для alignment/fusion як і раніше використовувати stopped `sparse/keyframes.npz` разом із його landmarks.
- **Keyframes:** successful `Map.add_keyframe` calls під час поточного track call; background threads не приписуються цьому call. Boolean означає creation event під час call, не membership у final retained snapshot. Initialization може вставити reference frame 0 та current frame 2 у call 2: у рядку 2 events `[0,2]`, у рядку 0 нічого не backfill-иться. Подальше culling не змінює історію.
- **Tracking time:** wall time original track invocation, включно з waits і невеликим in-call keyframe-hook overhead; post-call pose collection/CSV I/O виключено. Це не image decode, whole input loop або end-to-end latency.
- **Mapping/total:** порожні; mapping асинхронний і не атрибутується окремому input frame. Whole-loop timer не встановлюється. `0 ms` не підставляється.

## Перевірка

Unit tests: initialization/loss, causal poses та створення потім culled keyframes, unknown/stale observations, preserved exceptions, deterministic serialization/no overwrite, malformed CSV, hash/identity checks і справжній child-process `os._exit`. New import hygiene test перевіряє, що modules не завантажують pySLAM/CV2/torch.

Existing Linux/Docker runtime та TUM inputs можна використати повторно; downloads/build не потрібні. Windows host example (кожного разу новий run ID):

```powershell
docker exec --env LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libQt5Core.so.5:/usr/lib/x86_64-linux-gnu/libQt5Gui.so.5:/usr/lib/x86_64-linux-gnu/libQt5Widgets.so.5 rt-mapping-wp2-yulian python -O scripts/run_wp2_pyslam.py --pyslam-root /opt/pyslam --pyslam-python /usr/local/bin/python --frames 200 --export-sparse --run-id new_unique_tracking_smoke
```

## Clean real-run evidence

Обидва native runs мають clean `be9bff24eb2a54ea7927078c7cfc48969fd6d45a`, `dirty_worktree=false`, status **ok**. [Small summary із hashes](../results/summaries/yaropolk_y01_tracking_smoke200_be9bff2.json).

| Run suffix | Rows | States | Online poses | Creation events | Retained keyframes | Final poses |
|---|---:|---|---:|---:|---:|---:|
| `_01` | 200 | 198 OK / 2 NOT_INITIALIZED | 198 | 62 | 20 | 198 |
| `_02` | 200 | 198 OK / 2 NOT_INITIALIZED | 198 | 55 | 24 | 198 |

Full IDs: `yaropolk_y01_smoke200_be9bff2_01` та `_02`. State vectors збігаються на всіх 200 frames; unposed frames лише 0/1. UNKNOWN/observation errors — 0. Обидва final pose counts збігаються з prior clean baseline (198); upstream LOST counter також 0. Sparse read-back валідний: `_01` 1,254 landmarks / 8,097 observations; `_02` 1,375 / 10,140.

Keyframe event sequences відрізняються між runs. Це спостережувана nondeterminism upstream workers; identical states/pose counts не доводять byte-identical geometry. Retained frame IDs в обох runs є підмножиною recorded creation events. Initialization events `[0,2]` записані під час input frame 2, без backfill рядка 0. Mapping/whole-loop timing порожні в усіх 200 рядках кожного run.

CI Ubuntu/Windows × Python 3.11/3.12: **489 passed, 1 native skip**. Installed-backend sparse API check окремо **1 passed**. Historical pipeline: перевірено, що 13 hashes source artifacts не змінилися. Baseline config, upstream sources, existing summaries та WP3/WP4 code не змінювалися.

Automated ATE/RPE/resources і gap-aware success reporting належать наступним Y-02/Y-03; existing evaluators тут не змінюються. Shared status docs лишаються для IC1 за file boundaries поточного team plan; status row та evidence надано в PR.
