# Lab tests: what to run, what to record, what it sets

Checklist for lab sessions. Claude keeps it updated; tick items and note the evidence file.
Each test **sets a value** in `main/app_config.h` (marked MEASURE), **checks a success criterion** (SCn in `docs/CDIO/CONCEIVE.txt`), or both.

Logs: `docs/evidence/logs/YYYY-MM-DD_<test>.txt` (`idf.py -p /dev/ttyACM0 monitor | tee <file>`). Photos/videos: `docs/evidence/photos/`.
Standard targets (make once, reuse): **T1** 5 cm cardboard tube, upright; **T2** flat A4 board on a stand; **T3** 2 cm dowel/pen; **T4** soft (folded jumper / foam); **T5** box. Mark sensor position and 0°/90°/180° on the bench with tape.

## Bring-ups (kit week): procedures written in tasks B1–B4

| ID | What | Record | Sets |
| --- | --- | --- | --- |
| B1 | Servo calibration + step/settle time | angle vs pulse table, settle ms, any resets | `APP_SERVO_*` |
| B2 | HC-SR04 at fixed angle vs tape | 10 pings × 7 distances; ECHO voltage; unplugged → FAIL | `APP_US_*` |
| B3 | Joystick raw range and centre | counts at rest/extremes | `APP_JOY_DEADZONE` |
| B4 | Kit screen: identify (graphic or character?) + draw timing | type, controller, bus, ms per fill | D-DISPLAY, pins |

## System tests

| ID | Criterion | Method | Pass | Evidence |
| --- | --- | --- | --- | --- |
| T-DIST | SC1, SC2 | T2 facing sensor at 10/25/50/75/100/125/150 cm, 20 readings each; repeat T1 | mean error and spread within SC2 | log + `tools/` chart |
| T-ANG | SC3 | T1 at 50 cm, bearings 30/60/90/120/150°; compare raw smear and edge-midpoint | ±5° (midpoint) | log + chart |
| T-MATCH | SC3 | Sweep both ways past T3; same bearing left→right and right→left? | difference < 1 step | log |
| T-SWEEP | SC4 | Time 10 full passes | ≤ 5 s each; compare with S1 model | log |
| T-REMOVE | SC5 | Add T1, then remove it; count passes until it shows up / clears | 1 / 2 passes | video |
| T-MOVE | SC5 | Slide T1 across at ~5 and ~20 cm/s | describe trail; when does it break? | video |
| T-MAT | SC1 | T1–T5, and T2 at 0/20/40/60° to the beam, at 50 and 100 cm | which are detected; at what angle T2 vanishes | table + photos |
| T-TWO | limits | Two T3s at 50 cm, move closer together in 5° steps | angle at which they merge | log + photo |
| T-XTALK | limits | Neighbour's scanner aimed at ours, 1 m away; count phantom points over 2 min | report rate; with and without 60 ms gap | log |
| T-FAULT | SC6 | Unplug ECHO mid-sweep, plug back | FAULT shown, recovers, no fake 0 cm points | video |
| T-STALE | SC6 | Unplug servo/sensor power or pause | STALE within 1.5 s | video |
| T-LAT | SC7 | Toggle a GPIO at ping, film screen at 240 fps (or log timestamps) | ≤ 200 ms | video/log |
| T-LOCK | SC8 | T1 alone: lock time; move at ~10 cm/s; remove; 2 min empty | SC8 limits | log (`T,` lines) |
| T-JOY | SC9 | Step stick, time servo response; release, watch creep; position vs rate control | ≤ 0.3 s, no creep | video + D-JOY |
| T-POWER | sustainability | USB meter: idle, SWEEP, LOCK, MANUAL, paused (servo released) | record values | table |
| O2 | SC10 | Outsider places 2 objects from the display only | ±10 cm, ±10° | notes |
