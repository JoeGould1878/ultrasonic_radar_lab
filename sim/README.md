# Simulation and modelling

The brief asks for a simulation that **answers a design question**, records **what it assumes**, and says **what still needs testing on real hardware**. Every script here starts with a docstring stating those three things. Outputs (charts, CSVs) go to `docs/evidence/sim/`.

| Script (PLAN task) | Design question | Status |
| --- | --- | --- |
| `sweep_timing.py` (S1) | Step size and ping gap vs sweep time, data age, coverage vs beam width | done 26 Nov: `docs/evidence/sim/s1_*` (4 charts, CSV, summary); recommendations awaiting Joe's approval |
| `scene.py` (S2) | What does one object look like to a 15° beam? Produces simulated `R,…` lines | done 26 Nov: `docs/evidence/sim/s2_*` (5 charts, results CSV, summary) + 35 scenes with truth files in `s2_scenes/` |
| `../host_tests/` (S3) | Do the lock-on rules lock fast, follow, and not false-lock? Which `APP_LOCK_*` values? | to write |
| `../tools/radar_view.py` (S4) | Is the display readable: age, statuses, labels? (prototyped on simulated data) | to write |
| `wokwi/` (S5, optional) | Wiring and servo/ping sequencing on a virtual ESP32-S3 | optional |

Later (I7): real recordings replace simulated data in the same tools. Model vs reality is part of the evidence.
