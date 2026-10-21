# Data

Датасети не зберігаються в Git. Очікувана локальна структура:

```text
data/
├── raw/
│   └── tum_rgbd/<official-sequence-directory>/
└── manifests/
    └── <sequence>.json
```

Manifest має містити official URL, archive filename/checksum, extracted directory, frame count, camera intrinsics source і timestamp association rule. Ground-truth depth/trajectory доступні лише evaluation module або явно позначеному oracle experiment.

Згенерувати / перевірити manifest для fr1/xyz (CPU, без завантаження): `.venv\Scripts\python.exe scripts\build_tum_manifest.py [--check]`.

Primary source: https://cvg.cit.tum.de/data/datasets/rgbd-dataset

Не комітити RGB/depth archives, extracted frames або персональні absolute paths.
