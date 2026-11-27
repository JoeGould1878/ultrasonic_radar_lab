# Scanning Ultrasonic Sonar — Plan (everything to be done)

Mini-Challenge 3 (CDIO) · started Thu 26 Nov 2026 · Joe Gould

This is the master task list. Each task has an ID, who does it, what "done" looks like and where the output goes. Claude Code works through it top to bottom; Joe approves anything marked **[JOE]** and the team signs off anything marked **[TEAM]**. Tick tasks here and log progress in `docs/CONTEXT.md`.

## Status

- Kit (component box) arrives **next week**. Until then: Conceive, Design, simulation, and the pure-C logic, all of which need no hardware.
- Known hardware: Freenove ESP32-S3-WROOM, everything from MC2, 32×8 MAX7219, and a screen in the box that we **don't use** (D-DISPLAY: PC view first, then an ESP32 web page). HC-SR04, SG90 servo and an analogue joystick are expected but not confirmed.
- Firmware: ESP-IDF v6.1, C. Skeleton = headers (the contract) + build files + empty `.c` files.
- `docs/CDIO/CONCEIVE.txt` drafted. The rest of `docs/CDIO/` is outlines.

## Work order until the kit arrives (Joe, 26/11)

The phases below are grouped by type, not by when to do them. Until the kit arrives, work in this order:

1. **S2** scene simulator (feeds S3 and S4).
2. **S3** lock-on logic on the laptop (the main simulation activity).
3. **D1, D4, D5, D7**: block diagrams, schematic, case → circuit, evaluation plan. Design and case → circuit carry extra marks and must not be left until kit week.
4. **S4** display prototype (`tools/radar_view.py` on S2 data), if there is time before the kit; otherwise in kit week.
5. Then D2, D3, D8, D9, S6 and C3, C4 as time allows.

Why: S1 is done and simulation is on track, but no Design task had started. The kit arrives at session 3, so the paper design has to be done before then.

## What the brief is really marking

The brief and the Week 9 slides say: **more emphasis on design**, **a simulation or modelling activity that answers a design question**, and **case design and its impact on the circuit**. The emphasis is "on your engineering process, understanding, contribution and development, as well as the final prototype". A simple, well-tested system beats a fancy one you can't explain, and an animation that isn't driven by real measurements doesn't count.

| What they look for | Where it lives | Evidence |
| --- | --- | --- |
| Scans an area, measures distances | Implement / Operate | T-DIST, T-SWEEP logs |
| Each distance tied to the right direction | Design (D-ANGLE-TAG) → Operate | T-ANG, T-MATCH |
| Display helps interpret surroundings | Design D1/D2 | Screenshots, user feedback |
| Updates as objects appear, move or go away | Operate | T-REMOVE, T-MOVE videos |
| Capabilities and limits you can explain | Conceive → Operate | T-MAT, T-TWO, T-XTALK, limits table |
| Valid echo vs no echo vs failed measurement | Design (status model) | T-FAULT (sensor unplugged) |
| Old vs current information | Design (fading, STALE) | T-STALE |
| Simulation that informed the design | Design S1–S6 | `sim/` outputs, model vs real (I7) |
| Case design → circuit impact | Design D5 | Sketch + list of consequences |
| Sonar vs radar | Conceive | Comparison table |
| Ethics, privacy, accessibility, sustainability | Conceive + Design | Short sections tied to choices |
| Bench observation: contribution, understanding, testing, conduct | Every session | Git history, reflections, decision log |
| Session reflections (Canvas) | After each session | `docs/CDIO/REFLECTIONS.txt` notes |

## Product idea (draft; team to confirm)

An **"honest" desk-scale sonar for a teaching lab**. It scans a 150° arc out to 1.5 m and draws what it finds on a radar-style display, showing its own limits: how old each point is, when there's no echo, and when the sensor has failed. Proposed modes (Joe's idea; how they are switched is still open, see D-MODEBTN):

1. **SWEEP**: automatic back-and-forth sweep. *Essential*, built first.
2. **LOCK** (Joe's proposal): sweeps until something is confirmed, then sweeps only a narrow sector around it and follows it, with a full re-sweep every few seconds. *Extension*; the brief lists "automatic rescanning of a region where an object has been detected".
3. **MANUAL** (Joe's proposal): the joystick points the sensor like a torch, with a live distance readout. *Extension.*

**Display: PC view over USB first, then an ESP32 web page** (D-DISPLAY). The web page can be opened on a PC *and* a phone, so the brief's phone stretch comes along with it. The kit's screen is not used.

---

## Phase 0: setup (this week)

- [x] **P0.1** [JOE] Create the empty GitHub repo `ultrasonic_radar_lab` and push this skeleton (`git remote add origin …; git push -u origin main`).
- [x] **P0.2** First `idf.py set-target esp32s3 && idf.py build` of the skeleton; fix any build errors. *Done when:* it builds clean and `cd host_tests && make` passes.
- [x] **P0.3** Python env for the sims: `python3 -m venv .venv && . .venv/bin/activate && pip install numpy matplotlib pyserial`. Add `requirements.txt`.

## Phase C: Conceive (this week)

- [x] **C1** Draft `docs/CDIO/CONCEIVE.txt` (purpose, users, similar products, success criteria, essential vs desirable, is ultrasonic appropriate, sonar vs radar, risks, ethics, sustainability).
- [x] **C2** [JOE] Read C1 and fix anything marked `[CHECK]`. [TEAM] Agree the purpose and success criteria when the team is back.
- [x] **C3** Read the remaining brief resources (Arduino Project Hub page, How To Mechatronics video description) and add anything new to C1's "similar projects" table. Don't copy code; note ideas and credit them.
- [x] **C4** Canvas Conceive reflection: draft answers from C1, in "we" voice, flag anything that needs the team's confirmation.

## Phase D: Design (this week, finalise when the kit arrives)

- [ ] **D1** Diagrams in `docs/diagrams/`: hardware block diagram (ESP32-S3, servo + supply, HC-SR04 + divider, joystick, USB to the PC view, Wi-Fi to the browser later) and firmware (tasks, queues, data flow as in `main/*.h`). SVG + PNG, generated by a script like MC2's `gen_diagrams.py`.
  - **Firmware diagram standard (applies to D1 firmware and D3).** Firmware diagrams are real flowcharts and state diagrams, not box-and-arrow sketches. Every symbol means something and each diagram has a legend:
    - Flowcharts (ISO 5807): rounded terminator = start/end; rectangle = process step; diamond = decision, every exit labelled (yes/no or the condition); parallelogram = input/output (ping, serial line, joystick read); rectangle with double side bars = predefined process (a call into another component, e.g. `target_track_on_pass()`); small circle = connector; arrows show the flow direction, and there are no unlabelled branches.
    - One flowchart per task loop: `scan_task` (next angle → move → settle → ping → map → serial, with the timeout/FAILED branches), `input_task`, and the `lock_loop` on_reading flow (pass end, lock/loss, resweep timer).
    - State diagrams (UML style): filled dot = initial state, rounded box = state, every arrow labelled event [guard] / action. `mode_fsm` (SWEEP/LOCK/MANUAL + pause + fault), `target_track` (SEARCHING → CANDIDATE → LOCKED → lost), `lock_loop` plans (FULL / SECTOR / RESWEEP).
    - Names in the diagrams match the code exactly (functions, states, `APP_*` values), so each diagram can be checked against the source. Generated by a script (`gen_diagrams.py`, Graphviz or similar), SVG + PNG.
- [ ] **D2** Alternatives tables (fill in the decision log as each one closes):
  - **D-DISPLAY**: decided 27 Nov (see decision log). The options below are kept as the record of what was considered.
    - (a) Kit screen on the device. Only works if it's a graphic screen; a 16×2 character LCD can't draw positions (at most mode + live distance as a *secondary* readout).
    - (b) PC over USB serial → Python viewer (`tools/radar_view.py`). Simple and reliable; needs Python on the lab PC.
    - (c) PC over USB serial → a web page in Chrome using the Web Serial API. Nothing to install; Chrome/Edge only.
    - (d) ESP32 hosts a web page (soft-AP + WebSocket). PC and phone both work; adds Wi-Fi code, power draw and the brief's questions on lost connections / who has control.
    - (e) 32×8 MAX7219 from MC2: too coarse for positions; listed only to show it was considered.
    - Note: (b)–(d) share the same drawing rules (`radar_gfx` ideas, same serial protocol), which is why (b) then (d) loses no work and (c) is a cheap fallback.
  - D-SCAN: stop-and-ping (move, settle, ping) / continuous sweep with pings on the fly.
  - D-STEP: step size 1° / 2° / 3° / 5° (from S1).
  - D-ECHO: timing the echo with GPIO interrupt + esp_timer / RMT receiver / blocking busy-wait (rejected).
  - D-JOY: joystick position control / rate control (test both in T-JOY).
  - D-FILTER: raw / median of 3 per bin / reject jumps. The brief asks for "reducing unstable readings without hiding genuine changes".
  - D-MOUNT: sensor on servo horn bracket / pan from the base / fixed sensor array (rejected: only one sensor).
- [ ] **D3** Mode state machine diagram (`mode_fsm.h`) and the lock-on sub-states (`target_track.h`: SEARCHING → CANDIDATE → LOCKED → lost → SEARCHING).
  - Drawn to the firmware diagram standard under D1: UML-style state diagrams (filled dot = initial state, rounded box = state, every arrow labelled event [guard] / action), with a legend, names matching the code exactly, generated by `gen_diagrams.py` (SVG + PNG). Also the `lock_loop` plans (FULL / SECTOR / RESWEEP).
- [ ] **D4** Electrical design. Schematic (KiCad, like MC2) with:
  - echo divider calculation (1 kΩ / 2 kΩ → 3.33 V; check current and edge speed);
  - joystick on 3.3 V (why not 5 V);
  - servo supply: SG90 peak/stall current (datasheet), whether the board's 5 V pin can supply it, the 470–1000 µF capacitor, and the brown-out risk when the servo starts;
  - Wi-Fi peak current (for the web page, D-DISPLAY);
  - power budget per mode.
  - **Schematic standard.** Don't draw until the kit arrives: the sensor version decides the echo divider. Two schematic outputs, both required, reusing MC2's approach (`../spectrum_visualiser`: `docs/diagrams/gen_schematic_kicad.py` and `hardware/kicad/gen_kicad_sch.py`; credit them in the file headers):
    1. KiCad-style drawing for the report: `docs/diagrams/gen_schematic_kicad.py` → `schematic-kicad.svg` + `.png`. KiCad Eeschema look: green wires, dark-red part bodies, power symbols (+5V, +3V3, GND) instead of drawn rails, reference + value on every part (R1 10k…), junction dots, global labels for the ESP32-S3 pins, page frame + title block.
    2. Real KiCad project: `hardware/kicad/ultrasonic_radar.kicad_pro` + `.kicad_sch`, generated by `hardware/kicad/gen_kicad_sch.py` from KiCad's standard symbol library (`Device:R`, `Device:C_Polarized`, `Connector_Generic:Conn_01x04` for the HC-SR04, `Conn_01x03` for the servo, `Conn_01x05` for the joystick, `power:*`), with the symbols embedded so the file opens on any machine. It must pass `kicad-cli sch erc` with no errors, and `kicad-cli sch export netlist` must be checked net by net against the circuit and listed in `hardware/kicad/README.md`. Export `.pdf` + `.png` from KiCad for the report.
    - Both show the same circuit: servo supply + bulk capacitor (value from the SG90 current calculation), HC-SR04 echo divider (5 V version only; note the HC-SR04P variant), joystick, decoupling, and pins from `main/app_config.h`. Every component value has its calculation in `DESIGN.txt`.
    - Needs KiCad installed (Joe: `sudo apt install kicad`); if `kicad-cli` is missing, stop and say so rather than skipping the checks.
- [ ] **D5** Case and mount design and how it changes the circuit (slides emphasise this). Sketch + a short list of consequences, e.g.:
  - The sensor rides on the servo, so its 4 wires flex every sweep: service loop, strain relief, wire length, and connector vs solder.
  - The capacitor and divider sit near the servo and sensor, not on the far breadboard.
  - Sensor height and tilt: too low and it sees the table (floor echo).
  - The front must not cover the transducers: any window blocks ultrasound.
  - The base must not "walk" when the servo reverses: weight or clamps.
  - Joystick placement for the user; USB cable route to the PC (the display, D-DISPLAY).
  - Repairable: screws, not glue; the sensor clips out.
  - Sustainability: reuse kit parts; release the servo when paused.
- [ ] **D6** [JOE] Final pin map once the kit is known (update `main/app_config.h`, remove PROPOSED marks).
- [ ] **D7** Evaluation plan: map every success criterion in C1 to a test in `docs/LAB_TESTS.md`, with method and pass level.
- [ ] **D8** Risks and failure modes table (start from C1's risks; add mitigations and the test that checks each one).
- [ ] **D9** Write `docs/CDIO/DESIGN.txt` from D1–D8 + S1–S6, then the Canvas Design reflection.

## Phase S: simulation and modelling (this week; the brief requires one)

The brief wants a simulation that **answers a design question**, records its **assumptions**, and says **what still needs testing on hardware**. S1 and S3 are the main ones; S4 and S5 are cheap extras.

- [x] **S1** `sim/sweep_timing.py`: timing model.
  - Inputs: step size, servo speed (deg/ms), settle time, ping gap (≥ 60 ms), echo time at max range, arc width.
  - Outputs: time per sweep; readings per sweep; worst-case age of a point when it is redrawn; gap between neighbouring readings in cm at 50/100/150 cm compared with the ~15° beam width; how far a 0.2 m/s walker moves between visits.
  - Charts to `docs/evidence/sim/`. *Answers:* D-STEP, D-SCAN, `APP_FADE_SWEEPS`. *Assumptions:* datasheet servo speed, ideal settle, no echo retries. *Check on hardware:* B1 measures real step + settle time; I7 compares.
- [x] **S2** `sim/scene.py`: scene simulator.
  - A 2D desk scene (poles = circles, boxes, a wall at an angle), a beam cone of about ±7.5°, the nearest surface in the cone returns an echo, surfaces at a steep angle return none (specular), plus Gaussian noise and random dropouts.
  - Emits the **same serial protocol** as the firmware (`R,…` lines), so everything downstream can't tell sim from real.
  - Shows the "smear": one thin pole appears across about 15° of bins. That motivates the edge-midpoint in D-LOCK.
- [ ] **S3** Lock-on logic on the laptop (the main simulation activity):
  - implement `scan_map`, `sweep_plan`, `target_track`, `mode_fsm` (pure C) + host tests in `host_tests/`;
  - drive them with S2 scenes: static pole, slowly moving pole, two poles close together, pole removed, noisy/dropout readings, nothing there;
  - record lock time, angle error vs true centre, false locks and lost-target time while varying `APP_LOCK_*`, then pick values with evidence.
  - *Assumptions:* S2's idealised sensor. Later re-run with recorded real scans (I7).
- [ ] **S4** Display prototype on simulated data: `tools/radar_view.py` first, then `tools/web/radar.html` fed by the same lines (D-DISPLAY).
  - `tools/radar_view.py`: PC viewer (pygame or matplotlib). Reads `R,…` lines from a serial port **or** a file/S2 pipe. Draws rings, beam, points faded by age, a shape per status, the mode name and a STALE banner. This prototypes the display before the hardware exists (one of the brief's example simulations). It is the core display (D-DISPLAY) and the logging/evidence tool.
- [ ] **S5** (optional) Wokwi project (`sim/wokwi/`): ESP32-S3 + HC-SR04 + servo + joystick, to check the wiring and the servo/ping sequencing. Note Wokwi's sensor is ideal: no beam width, no noise.
- [ ] **S6** Write up the simulation section of `DESIGN.txt`: question → method → result → assumptions → what the hardware must confirm.

## Phase B: bring-ups (kit week). Separate IDF projects in `bringup/`

- [ ] **B1** `bringup/01_servo`: sweep 0→180 slowly; calibrate `APP_SERVO_MIN/MAX_US` against a protractor; measure the time for a 2° step + settle (camera at 240 fps or a sensor reading that stabilises); watch for brown-out resets when it starts. Sets `APP_SERVO_*`.
- [ ] **B2** `bringup/02_hcsr04`: fixed angle, log `echo_us` and cm at 10/25/50/75/100/125/150 cm against a tape measure (10 pings each). Check ECHO at the GPIO with a meter/scope (≤ 3.3 V). Unplug ECHO → must log FAILED, not 0 cm. Sets `APP_US_*`, gives T-DIST data.
- [ ] **B3** `bringup/03_joystick`: raw counts at rest, full left/right/up/down, centre drift; press detection. Sets `APP_JOY_DEADZONE`.
- [ ] **B4** Check the kit parts: sensor version (HC-SR04 or 3.3 V HC-SR04P / RCWL-1601: decides the echo divider in D4), servo model (SG90 or MG90S: current), joystick module (switch? pinout). The kit screen isn't used (D-DISPLAY).

## Phase I: implement (kit week onwards)

- [ ] **I1** Pure components finished and tested (from S3) + `radar_gfx` + `hcsr04_echo_to_cm` / `servo_deg_to_us` / `joystick_normalise` helpers with host tests.
- [ ] **I2** `servo` driver (LEDC 50 Hz, 14-bit).
- [ ] **I3** `serial_out` + protocol test against `radar_view.py`.
- [ ] **I4** `hcsr04` driver (D-ECHO choice); timeout → NO_ECHO; echo never rises / stuck high → FAILED.
- [ ] **I5** `scan_task` in SWEEP mode: next angle → move → settle → ping → map → serial. **Milestone M1: real scans on the PC viewer.** Commit and tag `m1-sweep`.
- [ ] **I6** PC view (`radar_view.py`) finished on real data: rings + labels, beam, fading points, mode name, live distance, STALE/FAULT banners. **M2: PC view working on real data.** The web page is X1.
- [ ] **I7** Model vs reality: record real sweeps of the S2 test scenes, compare the sweep time with S1 and the smear with S2, replay recordings through the S3 host tests, and update the assumptions. *This comparison is explicitly asked for.*
- [ ] **I8** `joystick` + `input_task` + `mode_fsm` wired in: press cycles the mode, long press pauses. MANUAL mode with D-JOY (try both, keep the better one, log it).
- [ ] **I9** LOCK mode: `target_track` in `scan_task`, sector sweep, recentring, periodic full sweep, lock box on screen. **M3: all three modes.**
- [ ] **I10** `main.c` start-up order, fault handling (sensor unplugged mid-run → FAULT banner, recovers), servo released when paused.
- [ ] **I11** [TEAM] Build the mount/case from D5; re-run T-DIST at 3 points to check nothing changed.

## Phase O: operate and evaluate

All in `docs/LAB_TESTS.md` with method, pass level and evidence file.

- [ ] **O1** Run the tests: T-DIST, T-ANG, T-MATCH, T-SWEEP, T-REMOVE, T-MOVE, T-MAT (size/material/angle: pole, box, foam, cloth, angled board), T-TWO (two poles closing in), T-XTALK (a neighbouring team's scanner on), T-FAULT, T-STALE, T-LAT, T-LOCK, T-JOY, T-POWER.
- [ ] **O2** User feedback: someone outside the team uses it with no explanation. Can they say where the objects are and which readings are old? Write down what confused them.
- [ ] **O3** Evaluation table: each success criterion → measured → pass/fail → why.
- [ ] **O4** Choose the one improvement with the most value, make it, and re-test (before/after).
- [ ] **O5** `docs/CDIO/OPERATE.txt` + Canvas reflections.

## Phase X: stretch (only after M3 and O1)

- [ ] **X1** Web page served by the ESP32 (D-DISPLAY, second display; also the phone view): soft-AP with a password + HTTP page + WebSocket push of the same `R,…` lines; shows connection status and "data no longer current"; one controller at a time, others view-only (brief question on contested control).

## Demo prep (session 6)

- [ ] **E1** Demo script (2–3 min): purpose → live sweep with a pole being moved → mode switch → a limitation shown on purpose (soft/angled object, or the beam smear) → evidence slide.
- [ ] **E2** Evidence pack: test table, model vs real chart, decision log, photos/videos, git log.
- [ ] **E3** [JOE] Make sure every team member can explain one decision and one limitation.

---

## Six-session plan (dates to fill in)

| Session | CDIO focus | Tasks | Done when |
| --- | --- | --- | --- |
| 1 (26 Nov) | Conceive | P0, C1–C2 | Repo up, Conceive draft reviewed |
| 2 | Design + sim | D1–D5, S1–S4 | Timing model + lock-on host tests + PC viewer on sim data |
| 3 (kit) | Design → Implement | B1–B4, D6, I1–I4 | Each part works on its own; pins final |
| 4 | Implement | I5–I7 | M1 + M2; model vs real compared |
| 5 | Implement → Operate | I8–I11, O1 starts | M3; mount built |
| 6 | Operate | O1–O5, E1–E3 | Tests done, demo rehearsed |

Reflection after **every** session (Canvas), with one piece of evidence each time.

## Serial protocol (firmware ↔ PC viewer ↔ simulator)

One ASCII line per event, comma-separated, `\n` terminated, 921600 baud:

```
R,<t_ms>,<mode>,<angle_deg>,<dist_cm>,<status>       status: OK | NOECHO | FAIL
M,<t_ms>,<mode>,<paused 0/1>,<fault 0/1>             mode: SWEEP | LOCK | MANUAL
T,<t_ms>,<state>,<centre_deg>,<left_deg>,<right_deg>,<dist_cm>   state: SEARCH | CAND | LOCK
```

`dist_cm` in `R` lines (D-PROTO-NULL): OK readings send the distance with 1 decimal place (`R,1234,SWEEP,90.0,52.3,OK`); NOECHO and FAIL send `-` (`R,1294,SWEEP,92.0,-,NOECHO`), never a number, so no reader can mistake them for an object at 0 cm.

Anything else (ESP-IDF log lines) is ignored by the viewer, so normal logging still works.

## Display spec (PC view and web page)

One spec for both displays (D-DISPLAY): `tools/radar_view.py` (S4, I6) and the ESP32 web page (X1) draw the same picture from the same serial lines. Built from the drawing rules in `components/radar_gfx/include/radar_gfx.h` and `main/display_task.h` (written for an on-device screen, now dropped), so those rules survive that code being removed. Everything here is PROPOSED until S4 and O2 test it; D-STATUS is still under "Options under consideration".

**Input.** The `R`/`M`/`T` lines above, nothing else, so a recorded log or an S2 scene file draws exactly like the live device. Lines that don't parse are ignored (ESP-IDF log lines).

**Numbers come from `main/app_config.h`**, read at start-up (as `sim/appcfg.py` does), not copied into the viewer: `APP_US_MAX_RANGE_CM` (150), `APP_SWEEP_MIN_DEG`/`APP_SWEEP_MAX_DEG` (15/165), `APP_FADE_SWEEPS` (3), `APP_EXPIRE_SWEEPS` (3), `APP_STALE_MS` (1500). The web page gets the same values from the ESP32 (built from the same header).

**Geometry** (from `radar_gfx_fit` / `radar_gfx_to_xy`):
- A half-disc with the sensor at bottom centre; 90° points straight up the screen. The max range (`APP_US_MAX_RANGE_CM`) fits the window with a margin and scales with the window size.
- Which side 0° is on must match the bench tape marks (LAB_TESTS) and the servo mounting: fix it at B1 and note it here.
- The scanned arc (15–165°) is drawn; outside it is greyed, so "not scanned" never looks like "empty".

**Range rings and labels:** rings with cm labels (CONCEIVE section 2 "clear range rings with cm labels"), PROPOSED every 50 cm to 150 cm; bearing lines with degree labels at the arc ends and 90°.

**Beam line:** a line at the angle of the latest `R` line, so the user can see where the sensor is pointing now.

**Readings: one mark per bin, a different SHAPE per status, not just a colour** (`radar_gfx_mark`, D-STATUS; brief: "without relying solely on colour"; SC6):

| Status (`R` line) | Mark | Notes |
| --- | --- | --- |
| OK | filled dot at (angle, dist_cm) | brightness from age, below |
| NOECHO | faint short dash across the bearing at the max-range ring | fades with age like an OK point (D-FADE), so "no echo" stays visible after the beam moves on and never looks like "never measured" (CONCEIVE section 7: "no echo", not "nothing there"). Joe, 27 Nov |
| FAIL | small cross | `dist_cm` is `-` (D-PROTO-NULL), so it has no range: PROPOSED to draw it on the outer ring, never at 0 cm |

**Fading (SC6 "points older than one pass visibly faded"; D-FADE):** age is shown by fading only; there is no separate per-point "stale" mark (`radar_gfx.h`'s hollow ring is dropped, Joe 27 Nov), and STALE is only the global banner below. Each mark's brightness falls linearly with its age, from full when measured to zero at `APP_FADE_SWEEPS` passes (3). Age counts in passes, not frames, so the fade means "not re-measured" whatever the frame rate. A point re-measured in the middle of the arc is redrawn at 67 % brightness, at the ends at 33 % (S1). Points are removed after `APP_EXPIRE_SWEEPS` passes.

**Banners (text + a shape, never colour alone):**
- **STALE:** no `R` line for `APP_STALE_MS` (1.5 s) → a "STALE" banner across the picture, and everything drawn is dimmed (SC6, T-STALE). Also shown when the serial port or the web socket drops.
- **FAULT:** `M` line with `fault` = 1 → a "SENSOR FAULT" banner (T-FAULT). Cleared by the next `M` line with `fault` = 0.
- **PAUSED:** `M` line with `paused` = 1 → "PAUSED".

**Status strip:** the mode name (SWEEP / LOCK / MANUAL from the `M` line), the live distance at the beam in large text (or "no echo" / "failed" in words), and the time since the last reading.

**LOCK:** a box or bracket from `left_deg` to `right_deg` around `centre_deg` from the `T` line, labelled with the state (SEARCH / CAND / LOCK). A D-EDGE target (arc end) is drawn with a "low confidence" mark once the `T` line carries the flag (see Open questions).

**Accessibility (CONCEIVE section 9):** every status has a shape and text as well as a colour; a large-text option; nothing relies on sound. Check: a greyscale screenshot still tells OK / NOECHO / FAIL apart (T-FAULT).

**Latency (SC7: a reading on screen within 200 ms of the ping; T-LAT):** draw each `R` line on the next frame, and redraw at least 20 times a second (the old `APP_DISPLAY_FPS`), so drawing adds at most 50 ms. The rest of the 200 ms is for serial or Wi-Fi.

## Decision log

Only decisions actually made go here, each with its reason/evidence. Everything still being weighed is in **Options under consideration** below and moves up when it is decided (by the team, from a test or a simulation).

| ID | Date | Decision | Alternatives | Reason / evidence |
| --- | --- | --- | --- | --- |
| D-FW | 26/11 | ESP-IDF v6.1 on the ESP32-S3 (`~/esp/esp-idf-v6.1`, loaded by the `get_idf` alias) | Arduino-ESP32; Uno R4 | Same toolchain/board as MC2; Joe is the only one working on it this week; v6.0.2 also installed; v6.1 pinned so builds are reproducible |
| D-ORDER | 26/11 | Build and test SWEEP first; LOCK and MANUAL only after it works | All modes at once | Brief: "keep a working version of the core scanner as you experiment" |
| D-STEP | 26/11 | 2° step (`APP_SWEEP_STEP_DEG`) | 1° / 3° / 5° | S1: 4.5 s per 150° pass at a 60 ms gap (SC4 ≤ 5 s); 7 readings see a thin target (4 if the useful beam is only 8°), enough for median-of-3 and edge-midpoint. 1° misses SC4 at every gap (9.0 s at 60 ms); 3° drops to 2 hits in the 8° case, 5° to 1. Evidence: `docs/evidence/sim/s1_summary.txt`; re-check at I7 |
| D-SCAN | 26/11 | Stop-and-ping: move → settle → ping | Ping while moving | S1: ping-while-moving saves 0 % at a 40–60 ms gap (the 4 ms move + 20 ms settle fit inside the gap), but its angle error flips sign each pass, so an object jumps 3.2° between passes at 2° (a third of the SC3 ±5° band). Evidence: `docs/evidence/sim/s1_summary.txt`; T-MATCH confirms |
| D-ANGLE-TAG | 26/11 | Tag each reading with the settled angle at ping time | Angle at send time; interpolated | Follows from D-SCAN: once settled, the commanded angle is the real one (S1 assumption A2; B1 measures the settle). The previous prototype could be ~2.5° off. Evidence: `docs/evidence/sim/s1_summary.txt`; T-MATCH confirms |
| D-GAP | 26/11 | 60 ms between pings (`APP_US_PING_GAP_MS`) | 30 / 40 ms | S1: 60 ms already meets SC4 (4.5 s at 2°); echoes from up to 10.3 m can't land in the next ping (6.9 m at 40 ms, 5.2 m at 30 ms); 30 ms is shorter than the assumed 38 ms no-echo hold, so triggers may be ignored. Dropping to 40 ms needs all three: I7 shows the pass is over 5 s, B2 and T-XTALK show no ghosts or cross-talk, and the CONCEIVE stakeholder row ("ping gap >= 60 ms") is changed to match. Evidence: `docs/evidence/sim/s1_summary.txt` |
| D-FADE | 26/11 | Points fade out over 3 passes (`APP_FADE_SWEEPS` 2 → 3); expiry also 3 passes (`APP_EXPIRE_SWEEPS`, wired up in I1) | Fade over 2 passes | S1: the bounce sweep re-measures the end bins only every 2 passes, so a 2-pass fade reaches zero just as they're refreshed. With 3: 67 % brightness when redrawn in the middle, 33 % at the ends. O2 judges whether this meets SC6. Evidence: `docs/evidence/sim/s1_summary.txt` |
| D-PROTO-NULL | 26/11 | In `R` lines, `dist_cm` is `-` for NOECHO and FAIL; OK readings use 1 decimal place | `0.0`; empty field; `-1` | `0.0` could be read as an object at 0 cm: the dishonest-display failure B2 already guards against ("must log FAILED, not 0 cm"). `-` is not a number, so a reader that ignores the status fails visibly instead of drawing a fake point. S2 scene logs use it. |
| D-EDGE | 26/11 | (a) Flag objects at the arc ends: a cluster touching `APP_SWEEP_MIN_DEG` or `APP_SWEEP_MAX_DEG` gets an "edge" flag and its bearing is reported as low confidence, not held to ±5°; the display shows the flag (S4) | (b) overscan ~8° past each end (pass ~5.0 s, SC4 on the limit); (c) narrow SC3 to 30–150° | S2: at 15° and 165° only ~4.5 bins are seen and the edge midpoint is pulled ~4.5° inward (worst 5.0°). (a) costs no sweep time and fits the honest-display goal; SC1 and SC3 unchanged. Evidence: `docs/evidence/sim/s2_summary.txt` |
| D-DISPLAY | 27/11 | PC radar view over USB serial first (`tools/radar_view.py`), then an ESP32-hosted web page (PC + phone, X1) fed by the same lines; kit screen not used | Kit screen; PC Web Serial page; MAX7219 | The PC view doesn't depend on the kit and the brief allows the core display on a lab PC; the kit screen is probably a character LCD (can't show positions); the web page gives the phone view almost free. Joe, team agreed 27 Nov. Risk: needs Python + pyserial on the lab PC (open question, check session 2); fallback: Web Serial page in Chrome, no install. |
| | | | | |

## Options under consideration (not decided)

| ID | Question | Options | Leaning / why (if any) | Decided by |
| --- | --- | --- | --- | --- |
| D-MODES | Which modes beyond SWEEP? | LOCK (lock-on), MANUAL (joystick), both, neither | Joe's idea: both; LOCK matches a brief extension ("rescan a region where an object was detected") | Team, after M1 |
| D-MODEBTN | How are modes switched? | joystick press / separate button / from the PC or phone page | Joystick press saves a part, if the kit joystick has a switch | Team + kit |
| D-STATUS | How are no-echo and failed readings shown? | three statuses with shapes / distance 0 / hide them | Brief asks how the display tells them apart | S4 prototype, O2 user test |
| D-RANGE | Maximum range / echo timeout | 100 / 150 / 200 / 400 cm | Desk scale and accuracy (S1: range doesn't change pass time at a 60 ms gap) | S1, T-DIST |
| D-ECHO | How the echo is timed | GPIO interrupt + esp_timer / RMT / busy-wait | Busy-wait blocks everything | I4 |
| D-JOY | Joystick control | position / rate | | T-JOY |
| D-FILTER | Steadying readings | raw / median of 3 / reject jumps | Must not hide real changes | T-MOVE |
| D-MOUNT | How the sensor is moved | bracket on servo horn / pan base | | D5, team |

## Open questions

- [ ] What's actually in the kit: HC-SR04 or HC-SR04P (3.3 V)? SG90 or MG90S? Joystick module?
- [ ] Team members and roles for this challenge [TEAM]
- [ ] Demo date (session 6)? Canvas reflection deadlines?
- [ ] Can the lab PC run Python with pyserial for the viewer? Check in session 2. This is the D-DISPLAY risk; fallback: a Web Serial page in Chrome, no install.
- [ ] Is a 3D printer / laser cutter available for the mount (D5)?
- [ ] T line (decide in S4; the Display spec's D-EDGE mark waits on it): add a field for the D-EDGE flag (low-confidence bearing)? And what goes in `centre_deg`, `left_deg`, `right_deg`, `dist_cm` while SEARCHING: `-` as in D-PROTO-NULL?

## Sources

- Mini-Challenge 3 brief, *Scanning Ultrasonic Radar Sonar* (W. Al-Nuaimy, H. van Zalinge, Oct 2026): `docs/brief/`
- Week 9a lecture slides, *Ultrasonic Radar* (H. van Zalinge): expectations on design, simulation, case design
- CDIO Lab-in-a-Box: *ESP32 Wi-Fi Ultrasonic Radar Prototype* (J. Wang, Jul 2026): https://cdioatc.blogspot.com/2026/07/esp32-wifi-ultrasonic-radar-prototype.html
- Lab-in-a-Box companion blog (Z. Wang): https://wang66666.blogspot.com/ (speed-detector projects; related, not the spec)
- Arduino Project Hub: *Building an Ultrasonic Radar Using Arduino and Processing*: https://projecthub.arduino.cc/diegogalvan_1294/building-an-ultrasonic-radar-using-arduino-and-processing-59053e
- How To Mechatronics, *Arduino Radar Project* (D. Nedelkovski): https://howtomechatronics.com/projects/arduino-radar-project/ (demo video, not watched: https://www.youtube.com/watch?v=8NboJtVqWRw)
- HC-SR04 datasheet (ElecFreaks, PDF dated 11 May 2011): https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf
- Processing Serial library: https://processing.org/reference/libraries/serial/
- Espressif Arduino-ESP32 Wi-Fi docs: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html
- AI use: plan, interfaces and drafts developed by Joe Gould with Claude (Anthropic); every decision recorded above.
