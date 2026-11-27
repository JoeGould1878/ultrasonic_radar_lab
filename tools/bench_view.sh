#!/bin/sh
# S4: measure the PC radar view's frame rate on THIS machine and save it as evidence.
# Usage (from the repo root, venv active):  sh tools/bench_view.sh <short-machine-name>
# Writes docs/evidence/s4/s4_fps_<name>.txt. Needs a desktop session (real window).
# Implementation: Claude (Anthropic), for Joe Gould.
set -e
name=${1:?usage: sh tools/bench_view.sh <machine-name>}
out=docs/evidence/s4/s4_fps_$name.txt
{
  echo "# S4 fps on $name, $(date -Iseconds)"
  echo "# $(grep -m1 'model name' /proc/cpuinfo), $(nproc) threads, $(free -g | awk '/Mem/{print $2}') GB RAM, session ${XDG_SESSION_TYPE:-?}"
  echo "# $(uname -sr), $(python -V 2>&1), git $(git rev-parse --short HEAD)"
  for i in 1 2 3; do
    echo "\$ python tools/radar_view.py --sim t1_b90_r50 --speed 4 --bench 10   (run $i, 1000x700)"
    python tools/radar_view.py --sim t1_b90_r50 --speed 4 --bench 10 2>&1 | grep frames
  done
} | tee "$out"
