# CLAUDE.md

Guidance for Claude (and Claude Code) working in this repository.

## Project

Scanning ultrasonic sonar ("radar" display): Mini-Challenge 3, CDIO, 2026. ESP32-S3 + HC-SR04 on an SG90 servo + joystick; the display is a PC view over USB first, then a web page served by the ESP32 (D-DISPLAY; no on-device screen), ESP-IDF v6.1, C. Three modes: SWEEP (essential), LOCK (lock-on), MANUAL (joystick).
The assessment is on the **engineering process and evidence**, with extra weight on **design, simulation, and case design → circuit**. Read `docs/CONTEXT.md` first, then `docs/PLAN.md` (the master task list).

## How we work

- **Everything goes through Joe.** He's the only one working on it this week and he approves the direction. Claude writes the code and docs; Joe reviews, flashes and tests.
- Work through `docs/PLAN.md` in order. One task at a time; tick it off and log it in `docs/CONTEXT.md`.
- **Headers are the contract.** Implement against `components/*/include/*.h` and `main/*.h`. Change a header only for a real reason, and say why.
- **Ask Joe first** before changing anything in the decision log, the success criteria in `docs/CDIO/CONCEIVE.txt`, the modes, or the wiring.
- **Keep Joe in the loop.** After each chunk: what was written, each design choice and why, and what he needs to do or record next. He has to explain all of it at the demo.
- Every tunable number lives in `main/app_config.h` and is marked PROPOSED / SIM / MEASURE. When a test or sim sets it, change the value and add a decision-log line citing the evidence file.
- Simulations answer a design question and record assumptions + what hardware must confirm (the brief asks for exactly that). Outputs go to `docs/evidence/sim/`.
- Build before handing over: `idf.py build` and `cd host_tests && make`. Fix errors first.
- Commit messages say what changed and why. The git history is evidence.
- Credit any external code or idea in the file header and in `README.md`.
- CDIO write-ups live in `docs/CDIO/*.txt` (plain text so Joe can paste into Canvas).

## Commands

```bash
get_idf   # alias: . ~/esp/esp-idf-v6.1/export.sh
idf.py set-target esp32s3                    # once per project dir
idf.py build
idf.py build flash -p /dev/ttyACM0 monitor   # Ctrl+] to exit
idf.py -p /dev/ttyACM0 monitor | tee docs/evidence/logs/<date>_<test>.txt
cd host_tests && make                        # laptop tests, pure-C components
. .venv/bin/activate && python sim/sweep_timing.py
python tools/radar_view.py --port /dev/ttyACM0      # or --file / --sim
```

## Layout rules

- `components/` never include from `main/`.
- Pure components (`scan_map`, `sweep_plan`, `target_track`, `mode_fsm`, `lock_loop`) include only the C standard library, so they build on the laptop.
- Only `scan_task` touches `servo` and `hcsr04`; only `input_task` touches `joystick`/`button`; only `scan_task` calls `mode_fsm` and `serial_out` (D-OWN; `input_task` posts events with `scan_task_post_event()`).
