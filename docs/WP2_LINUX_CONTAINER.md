# Ізольований Linux runtime для WP3/WP4 integration

Це додатковий Linux/x86_64 шлях для незмінного WP2 baseline, а не заміна macOS evidence Ярополка. Windows host запускає Docker для classical CPU SLAM і окремий CUDA Python для DA3. Dataset, checkpoints та full runs не входять до image або Git.

## Зафіксовані inputs

- Python 3.11 Debian bookworm image digest: `18d373e126e39c29c6d38e71e2f19ca66636568318fc95c7849c462b7f9d3d64`.
- pySLAM: `96019cfafcfc099ac9866884d7143a9ed1451a0d`, Python core (`PYSLAM_USE_CPP=false`), ORB2/DBOW3, upstream `python -O`.
- GTSAM 4.2a9: `c57988fe554e7213c77fe379c1d7c483de26ad33`, лише patch із pinned pySLAM tree.
- Python package freeze: `requirements/wp2-linux-x86_64.txt`; CPU torch 2.6.0, NumPy 1.26.4, pybind11 2.13.1.
- ORB vocabulary: `ORBvoc.dbow3`, 105381669 bytes, SHA-256 `49b1deee2331aa0897aec95b0fdf0fb07eda4a608ed5b92c54186e9cf6d500ea`.

`scripts/build_wp2_linux_native.py` перевіряє source revisions та збирає native modules. Debian Qhull 8.0 headers несумісні з C++20; CMake hook компілює лише `bounding_boxes_2d.cpp` і `bounding_boxes_3d.cpp` як C++17. Решта solvers/core зберігає upstream C++20. pySLAM sources та baseline config не змінюються. Build потребує кількох GB і може бути тривалим; `--jobs 2` обмежує parallel compile.

Hamming binding upstream використовує SSSE3/SSE4.1 intrinsics навіть у SSE2 branch. Для x86_64 йому явно задається `-msse4.1` без host-specific `-march=native`; CPU повинен підтримувати SSE4.1.

Великий `volumetric_module.cpp` binding компілюється з `-O1`, щоб обмежити compile time/memory. Frozen classical baseline не вмикає upstream volumetric mapping. Solvers/core зберігають Release optimization; власний WP4 fusion знаходиться у `rt_mapping.fusion`.

## Побудова і запуск

Команди нижче завантажують image, source і packages. Виконувати у власному environment після дозволу на setup/downloads.

```powershell
docker build -f containers/wp2.Dockerfile -t rt-mapping-wp2:96019cf .
docker run -d --name rt-mapping-wp2-yulian --shm-size=1g --memory=10g --cpus=4 --mount "type=bind,source=$((Get-Location).Path),target=/workspace" rt-mapping-wp2:96019cf
docker exec rt-mapping-wp2-yulian python scripts/check_wp2_environment.py --pyslam-root /opt/pyslam --pyslam-python /usr/local/bin/python --probe-runtime
docker exec --env WP2_NATIVE_SPARSE_TEST=1 --env WP2_PYSLAM_ROOT=/opt/pyslam rt-mapping-wp2-yulian python -O -m unittest discover -s tests -p test_pyslam_sparse_native.py -v
```

Native source має знаходитися на Linux filesystem усередині container: Windows checkout може містити symlink як text file. `/workspace` — shared repository mount; pipeline CLI використовує relative POSIX output paths, тому host і container бачать ті самі immutable run folders. Використовувати container лише цього проєкту; existing containers не перезаписувати.

## One-config pipeline

`configs/pipeline.tum.windows-docker.json` очікує running container вище, frozen TUM archive/extraction та cached pinned DA3 checkpoint. DA3 environment `.local/da3-venv` використовує host CUDA torch 2.7.1+cu118, Python 3.12, DA3 source `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`, NumPy 1.26.4 і OpenCV 4.11.0.86. Це local environment, не зміна host packages. На іншій машині замінити interpreter argv на власний перевірений environment.

```powershell
python scripts/run_pipeline.py --config configs/pipeline.tum.windows-docker.json --run-id unique_real_pipeline
```

Launcher запускає SLAM, DA3, alignment/fusion та B0/B1/P1 evaluation. Він не встановлює dependencies і не завантажує inputs. Кожний adapter зберігає власний manifest і log. Не використовувати finished run ID повторно. `results/runs/` залишається ignored; передавати full artifacts окремо від маленьких versioned summaries.
