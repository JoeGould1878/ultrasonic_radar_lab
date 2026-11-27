# Lab tests: evaluation plan (D7)

Every success criterion (SC1–SC10, `docs/CDIO/CONCEIVE.txt` section 5, agreed by the team 27 Nov 2026) maps to at least one test below. Each test **checks a success criterion**, **sets a value** in `main/app_config.h` (marked MEASURE), or **measures a limit** for CONCEIVE section 7.

- **Pass levels are copied from the SC text**, not invented. Where the SC leaves something open, the gap is listed under "Open points" at the end, so we don't pick a pass rule after seeing the results.
- **Trial counts are PROPOSED**: change them here before the test, not after.
- **Logs:** `docs/evidence/logs/YYYY-MM-DD_<test>.txt` (`idf.py -p /dev/ttyACM0 monitor | tee <file>`). **Photos/videos:** `docs/evidence/photos/YYYY-MM-DD_<test>_<n>.jpg|mp4`. Charts made from logs go next to the log with the same name and a `.png` extension.
- **Standard targets** (make once, reuse): **T1** 5 cm cardboard tube, upright; **T2** flat A4 board on a stand; **T3** 2 cm dowel/pen; **T4** soft (folded jumper / foam); **T5** box. Mark the sensor position and 0°/15°/90°/165°/180° on the bench with tape, and lay a tape measure along 90°.
- **Simulation predictions** (S1/S2) are given where they exist, so each test also checks the model (I7).

## Bring-ups (kit week): procedures written in PLAN tasks B1–B4

| ID | What | Record | Sets |
| --- | --- | --- | --- |
| B1 | Servo calibration + step/settle time | angle vs pulse table, settle ms, any resets | `APP_SERVO_*` |
| B2 | HC-SR04 at fixed angle vs tape | 10 pings × 7 distances; ECHO voltage; unplugged → FAIL | `APP_US_*` |
| B3 | Joystick raw range and centre | counts at rest/extremes | `APP_JOY_DEADZONE` |
| B4 | Kit parts check: sensor version (HC-SR04 or HC-SR04P / RCWL-1601), servo model, joystick module | part markings, photo | echo divider (D4), pins (D6) |

## Success criteria → tests

| SC | Criterion (CONCEIVE section 5) | Tests |
| --- | --- | --- |
| SC1 | Range: detects a 5 cm wide upright tube anywhere in the 150 degree arc from 5 to 150 cm | T-DIST (T1 part), T-MAT |
| SC2 | Distance accuracy: within ±2 cm or 3 % (whichever is larger) for a flat target facing the sensor, 10 to 150 cm | T-DIST |
| SC3 | Direction: displayed bearing of a thin tube within ±5 degrees of its real bearing (after edge-midpoint processing) | T-ANG, T-MATCH |
| SC4 | Speed: one full 150 degree pass in 5 s or less | T-SWEEP |
| SC5 | Updates: a new object appears within 1 pass; a removed object disappears within 2 passes | T-REMOVE, T-MOVE |
| SC6 | Honest display: echo / no echo / failed told apart without colour; points older than one pass visibly faded; STALE warning within 1.5 s if readings stop | T-FAULT, T-STALE |
| SC7 | Latency: a reading is on screen within 200 ms of the ping | T-LAT |
| SC8 | LOCK (extension): locks onto a single tube within 2 passes; keeps the lock while it is moved by hand at about 10 cm/s at 50 cm; back to full sweep within 2 s after it is removed; no false lock in an empty scene over 2 minutes | T-LOCK |
| SC9 | MANUAL (extension): sensor follows the stick within 0.3 s and does not creep when the stick is let go | T-JOY |
| SC10 | Usability: someone outside the team, with no explanation, places 2 objects within ±10 cm and ±10 degrees and can say which points are old | O2 (user test) |

Every SC has at least one test. Tests with no SC: **T-TWO**, **T-XTALK** (limits for CONCEIVE section 7) and **T-POWER** (sustainability, CONCEIVE section 9). They have no pass level; they record a number.

## System tests

| ID | SC | Method | Setup | Trials (PROPOSED) | Pass (copied from the SC) | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T-DIST | SC2, SC1 | **SC2:** sensor fixed at 90° (MANUAL or a bring-up build); compare each `R` line's `dist_cm` with the tape (to the board face). **SC1:** repeat with T1 at 5 and 150 cm, at 90°. | T2 facing the sensor square-on at 10/25/50/75/100/125/150 cm; then T1 at 5/150 cm | 20 readings per distance | **SC2:** within ±2 cm or 3 % (whichever is larger), 10 to 150 cm. **SC1:** T1 detected at 5 cm and at 150 cm | `logs/<date>_t-dist.txt` + `.png` (error vs distance with the SC2 band) |
| T-MAT | SC1 (+ limits) | SWEEP mode; one target at a time; note which give OK points at the target's position. **SC1 part:** T1 at each bearing and range. **Limits part:** T1–T5 at 90°; T2 at 0/20/40/60° tilt. | **SC1:** T1 at 15/60/90/120/165° × 50/100/150 cm. **Limits:** T1–T5 at 50 and 100 cm | 3 passes per position | **SC1:** T1 detected at every position, 15° to 165°, 5 to 150 cm. Limits part: no pass level; record the tilt at which T2 vanishes. Sim: ~40° at 50 cm, ~35° at 100 cm (`docs/evidence/sim/s2_summary.txt`) | `logs/<date>_t-mat.txt`, table in the log, photos `photos/<date>_t-mat_<n>.jpg` |
| T-ANG | SC3 | SWEEP mode; compare the tracker's edge-midpoint bearing (`T` line or cluster output) with the taped bearing; also note the raw nearest-bin bearing for comparison | T1 at 50 cm, bearings 30/60/90/120/150°; plus 15° and 165°, which D-EDGE flags as low confidence, not held to ±5° | 5 passes per bearing | Within ±5 degrees of the real bearing (after edge-midpoint processing), at 30–150°. Sim: midpoint mean < 1°, worst 6° with a dropout; nearest bin mean ~4° | `logs/<date>_t-ang.txt` + `.png` (error vs bearing, raw vs midpoint) |
| T-MATCH | SC3 | Sweep both ways past a thin target; compare the bearing measured left→right with right→left (checks D-SCAN and D-ANGLE-TAG) | T3 at 50 cm, 90° | 10 passes (5 each way) | Difference < 1 step (2°). Not an SC number: it is the check D-SCAN/D-ANGLE-TAG name; SC3's ±5° still applies | `logs/<date>_t-match.txt` |
| T-SWEEP | SC4 | SWEEP mode; pass time = `t_ms` of the last `R` line of a pass minus the first | Empty bench | 10 passes | One full 150 degree pass in 5 s or less (every pass). Sim: 4.5 s (`s1_summary.txt`) | `logs/<date>_t-sweep.txt` |
| T-REMOVE | SC5 | SWEEP mode; place T1 just after the beam has passed its bearing, count passes until it is drawn; then remove it and count passes until it is gone | T1 at 50 cm, at 90° and at 150° (end bins are revisited less often, S1) | 5 add + 5 remove at each bearing | Appears within 1 pass; disappears within 2 passes | `photos/<date>_t-remove_<n>.mp4` + `logs/<date>_t-remove.txt` |
| T-MOVE | SC5 | SWEEP mode; slide T1 across the arc at a steady speed (mark start/end positions, time it) | T1 at 50 cm, moved across 60° → 120° at ~5 and ~20 cm/s | 3 runs per speed | No pass level in SC5 for a moving object (see Open points); record how far the drawn trail lags the real position. Sim: 16–38 cm moved by the end of a pass | `photos/<date>_t-move_<n>.mp4` + log |
| T-FAULT | SC6 | Unplug ECHO mid-sweep, then plug it back; also leave the arc empty (NOECHO) and place T1 (OK). Convert a screenshot to greyscale and check the three statuses still differ | T1 at 50 cm, 90° | 3 unplug/replug cycles | Echo / no echo / failed told apart without colour; no fake 0 cm points (D-PROTO-NULL) | `photos/<date>_t-fault_<n>.mp4` + greyscale screenshot `.png` + log |
| T-STALE | SC6 | (a) Stop readings (pause, or cut sensor power) and time how long until STALE shows. (b) Remove T1 and photograph the display one pass later: is the old point visibly faded? | T1 at 50 cm, 90° | 5 stops; 3 fade checks | STALE warning within 1.5 s if readings stop; points older than one pass visibly faded | `photos/<date>_t-stale_<n>.mp4` + log |
| T-LAT | SC7 | Toggle a GPIO at the ping and film the LED and the PC screen at 240 fps; or log ping time on the ESP32 and draw time in `radar_view.py` on a shared clock | T1 at 50 cm, MANUAL fixed at 90° | 20 readings | Reading on screen within 200 ms of the ping (every reading) | `photos/<date>_t-lat.mp4` or `logs/<date>_t-lat.txt` |
| T-LOCK | SC8 | LOCK mode; read `T` lines: passes until LOCK; move T1 by hand along a marked 50 cm arc at ~10 cm/s (time it); remove T1 and time until full sweep; then 2 min with nothing in the arc | T1 at 50 cm | 5 locks, 5 moves, 5 removals, 1 × 2 min empty | Locks within 2 passes; keeps the lock while moved at about 10 cm/s at 50 cm; back to full sweep within 2 s after removal; no false lock in 2 minutes empty | `logs/<date>_t-lock.txt` (`T,` lines) + video |
| T-JOY | SC9 | MANUAL mode; push the stick to a stop and film the stick and the sensor; let go and watch for 30 s; try position and rate control (D-JOY) | Sensor head marked with a pointer; protractor behind it | 10 steps; 3 × 30 s release | Follows the stick within 0.3 s; does not creep when the stick is let go | `photos/<date>_t-joy_<n>.mp4` + D-JOY row |
| T-TWO | limits (none) | SWEEP mode; two thin targets moved together in 5° steps; note the gap at which they show as one | Two T3s at 50 cm, centred on 90° | 3 passes per gap | No pass level: record the merge angle. Sim: ~17–18° (15° beam) | `logs/<date>_t-two.txt` + photo |
| T-XTALK | limits (none) | Neighbouring team's scanner aimed at ours from 1 m; count phantom points over 2 min, with our 60 ms gap | Empty bench in front of ours | 2 min with, 2 min without the neighbour | No pass level: report the phantom rate per minute (D-GAP needs it before any change) | `logs/<date>_t-xtalk.txt` |
| T-POWER | sustainability (none) | USB power meter between PC and board | Idle, SWEEP, LOCK, MANUAL, paused (servo released) | 1 min per mode, note mean and peak | No pass level: record mA per mode | `logs/<date>_t-power.txt` (table) |
| O2 | SC10 | Someone outside the team, no explanation, uses the PC view only (can't see the bench). They say where 2 objects are and which points are old; write down what confused them | T1 + T5 placed by us at bearings/ranges they don't know | 1 user minimum (PROPOSED: 2) | Places 2 objects within ±10 cm and ±10 degrees and can say which points are old | `logs/<date>_o2-user-test.txt` (notes) |

## Open points (decide before the test, not after)

1. **SC1 "detects".** The SC doesn't say how often. Proposed meaning: an OK point is drawn at the tube's position in every pass of the trial. Joe/team to confirm.
2. **SC2: each reading or the mean?** "Within ±2 cm or 3 %" could apply to every reading or to the mean of 20. Proposed: report both; the pass uses the mean, and the spread is reported alongside. Joe/team to confirm.
3. **SC5 for a moving object.** T-MOVE is listed under SC5, but SC5's numbers are about objects appearing and disappearing. T-MOVE records the lag; it has no pass level unless the team adds one.
4. **SC6 "visibly faded".** Judged by eye in T-STALE and confirmed by O2 (can the outsider tell which points are old?).
