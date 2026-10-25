# CPU-only pinned classical baseline. Dataset, checkpoints and run artifacts
# are supplied through the /workspace bind mount and never baked into the image.
FROM python:3.11-bookworm@sha256:18d373e126e39c29c6d38e71e2f19ca66636568318fc95c7849c462b7f9d3d64
ENV DEBIAN_FRONTEND=noninteractive PYSLAM_USE_CPP=false QT_QPA_PLATFORM=offscreen
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake ninja-build build-essential clang libeigen3-dev libsuitesparse-dev libopencv-dev \
    libglew-dev libglfw3-dev libgl1-mesa-dev libflann-dev libboost-all-dev libopenblas-dev \
    libusb-1.0-0-dev libprotobuf-dev protobuf-compiler libqhull-dev pkg-config
COPY requirements/wp2-linux-x86_64.txt /opt/wp2-requirements.txt
RUN python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /opt/wp2-requirements.txt
RUN git init /opt/pyslam && git -C /opt/pyslam remote add origin https://github.com/luigifreda/pyslam.git \
    && git -C /opt/pyslam fetch --depth 1 origin 96019cfafcfc099ac9866884d7143a9ed1451a0d \
    && git -C /opt/pyslam checkout --detach FETCH_HEAD
COPY scripts/build_wp2_linux_native.py /opt/build_wp2_linux_native.py
RUN python /opt/build_wp2_linux_native.py
RUN gdown 'https://drive.google.com/uc?id=13xmRtop_ow3aPtv3qCT5beG19_mlogqI' -O /opt/pyslam/data/ORBvoc.dbow3
RUN python -c "import hashlib; from pathlib import Path; assert hashlib.sha256(Path('/opt/pyslam/data/ORBvoc.dbow3').read_bytes()).hexdigest() == '49b1deee2331aa0897aec95b0fdf0fb07eda4a608ed5b92c54186e9cf6d500ea'"
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libQt5Core.so.5:/usr/lib/x86_64-linux-gnu/libQt5Gui.so.5:/usr/lib/x86_64-linux-gnu/libQt5Widgets.so.5
WORKDIR /workspace
CMD ["sleep", "infinity"]
