# Two stages, built with different contexts by `stead image` (stead/image.py):
#   tools  context = {tools.tar, home.tar}          -> stead-tools
#   core   context = {tree/, recipe/, manifest}     -> stead-<repo>:<commit>   (FROM stead-tools)
#          the tree already has the shim applied (stead/image.py build_core)
# The recipe is copied after the tree: a run.sh edit rebuilds the simulator, not the tree layer.

FROM ubuntu:22.04 AS tools
LABEL org.opencontainers.image.source=https://github.com/abhimanyumagapu/benchmarks
ENV DEBIAN_FRONTEND=noninteractive STEAD_TOOLS=/opt/stead/tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential clang cmake ccache git make perl python3 python3-venv python3-pip python3-yaml \
      flex bison autoconf libfl-dev zlib1g-dev liblz4-dev libzstd-dev libelf-dev libboost-dev \
      libboost-regex-dev libboost-system-dev libgoogle-perftools-dev libssl-dev libffi-dev \
      device-tree-compiler srecord ninja-build openjdk-17-jdk-headless numactl curl xxd pkgconf \
      help2man ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ADD tools.tar /opt/stead/tools/
ADD home.tar /root/
# The tools were built under the owner's home; absolute symlinks and venv shebangs still say so.
RUN find /opt/stead/tools -maxdepth 2 -type l | while read -r l; do \
      t=$(readlink "$l"); case $t in /home/*/repos/tools/*) ln -sfn "/opt/stead/tools/${t#*/repos/tools/}" "$l";; esac; done \
    && sed -i 's|^#!/home/[^/]*/repos/tools|#!/opt/stead/tools|' /opt/stead/tools/venvs/*/bin/* 2>/dev/null; true
ENV PATH=/opt/stead/tools/verilator/bin:/opt/stead/tools/bin:$PATH

FROM stead-tools AS core
COPY tree /work/tree
COPY manifest /work/manifest
COPY env.sh /work/env.sh
COPY recipe /work/recipe
# ccache warmed by the clean build below: a rebuild after a one-file patch recompiles that file, not the core.
# Verilator's makefiles honor OBJCACHE; rocket-chip's cmake honors the launcher variable.
ENV OBJCACHE=ccache CCACHE_DIR=/work/ccache CCACHE_MAXSIZE=2G CMAKE_CXX_COMPILER_LAUNCHER=ccache
RUN /work/recipe/run.sh build /work/tree
WORKDIR /work
