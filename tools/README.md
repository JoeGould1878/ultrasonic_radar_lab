# Tools

| Script | Use | Status |
| --- | --- | --- |
| `radar_view.py` | PC radar viewer: `--port /dev/ttyACM0`, `--file log.txt` (replay) or `--sim` (pipe from `sim/scene.py`). Parses the `R,` / `M,` / `T,` protocol in `docs/PLAN.md` | to write (S4) |
| `capture.sh <test>` | `idf.py monitor \| tee docs/evidence/logs/<date>_<test>.txt` | to write |
| `analyse_dist.py` | T-DIST: error and spread per distance → chart | to write (O1) |
| `analyse_angle.py` | T-ANG / T-TWO: smear width, edge-midpoint error → chart | to write (O1) |

MC2's `tools/logparse.py` and diagram scripts are good starting points: https://github.com/JoeGould1878/spectrum_visualiser_lab/tree/main/tools
