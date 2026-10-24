# Tests

CPU suite перевіряє:

1. back-project → project round trip;
2. відновлення відомого scalar scale з outliers;
3. відновлення synthetic Sim(3) з outliers;
4. transform direction і pose inversion;
5. resize/crop intrinsics update;
6. serialization round trip для data contracts;
7. smoke pipeline на малому fixture без великих model weights.

GPU/model integration tests позначаються окремо й не повинні бути єдиними тестами correctness.

Запуск: `python -m pytest tests -q` після встановлення `.[dev]`. WP3/WP4 — `test_alignment_estimators.py`, `test_mapping_geometry.py`, `test_mapping_run.py`: outliers, degenerate/reflected transforms, distortion, landmark-disjoint validation, checksums, failed/cancelled runs, immutability та map geometry. `test_pyslam_sparse_native.py` opt-in і потребує native environment; scipy filter test потребує `.[filtering]`.

Synthetic smoke: `python scripts/run_alignment_smoke.py`; із `.[plots]` можна додати `--plot`. Tests не потребують TUM downloads або model weights.
