# The fake core, shaped like a real core image: /work/recipe/run.sh, /work/tree, /work/manifest.
# Build context: tests/fixtures. ALU_EXTRA appends a line to the clean DUT (a broken clean tree).
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY mini.vcd /work/mini.vcd
COPY fakerepo/run.sh /work/recipe/run.sh
COPY fakerepo/manifest /work/manifest
COPY fakerepo/tree /work/tree
ARG ALU_EXTRA=""
RUN [ -z "$ALU_EXTRA" ] || printf '%s\n' "$ALU_EXTRA" >> /work/tree/rtl/alu.sv
RUN /work/recipe/run.sh build /work/tree
WORKDIR /work
