# Scanning Ultrasonic Sonar — Plan (everything to be done)

Mini-Challenge 3 (CDIO) · started Thu 26 Nov 2026 · Joe Gould

This is the master task list. Each task has an ID, who does it, what "done" looks like and where the output goes. Claude Code works through it top to bottom; Joe approves anything marked **[JOE]** and the team signs off anything marked **[TEAM]**. Tick tasks here and log progress in `docs/CONTEXT.md`.

## Status

- Kit (component box) arrives **next week**. Until then: Conceive, Design, simulation, and the pure-C logic, all of which need no hardware.
- Known hardware: Freenove ESP32-S3-WROOM, everything from MC2, 32×8 MAX7219, and a screen in the box of **unknown type**: it may be a long character LCD (16×2 style), which can't draw a radar picture. HC-SR04, SG90 servo and an analogue joystick are expected but not confirmed.
- Firmware: ESP-IDF v6.1, C. Skeleton = headers (the contract) + build files + empty `.c` files.
- `docs/CDIO/CONCEIVE.txt` drafted. The rest of `docs/CDIO/` is outlines.

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

**Where the display lives is not decided** (D-DISPLAY, below). Options: the kit's screen, a PC over USB, or a web page served by the ESP32 that a PC *and* a phone can open. If the web page is chosen as the main display, the brief's phone stretch comes along with it.

---

## Phase 0: setup (this week)

- [x] **P0.1** [JOE] Create the empty GitHub repo `ultrasonic_radar_lab` and push this skeleton (`git remote add origin …; git push -u origin main`).
- [x] **P0.2** First `idf.py set-target esp32s3 && idf.py build` of the skeleton; fix any build errors. *Done when:* it builds clean and `cd host_tests && make` passes.
- [x] **P0.3** Python env for the sims: `python3 -m venv .venv && . .venv/bin/activate && pip install numpy matplotlib pyserial`. Add `requirements.txt`.

## Phase C: Conceive (this week)

- [x] **C1** Draft `docs/CDIO/CONCEIVE.txt` (purpose, users, similar products, success criteria, essential vs desirable, is ultrasonic appropriate, sonar vs radar, risks, ethics, sustainability).
- [ ] **C2** [JOE] Read C1 and fix anything marked `[CHECK]`. [TEAM] Agree the purpose and success criteria when the team is back.
- [ ] **C3** Read the remaining brief resources (Arduino Project Hub page, How To Mechatronics video description) and add anything new to C1's "similar projects" table. Don't copy code; note ideas and credit them.
- [ ] **C4** Canvas Conceive reflection: draft answers from C1, in "we" voice, flag anything that needs the team's confirmation.

## Phase D: Design (this week, finalise when the kit arrives)

- [ ] **D1** Block diagrams in `docs/diagrams/`: hardware (ESP32-S3, servo + supply, HC-SR04 + divider, joystick, display path(s) under consideration) and firmware (tasks, queues, data flow as in `main/*.h`). SVG + PNG, generated by a script like MC2's `gen_diagrams.py`.
- [ ] **D2** Alternatives tables (fill in the decision log as each one closes):
  - **D-DISPLAY** (the big open one). Score each option on: readability of a radar picture, works without installing anything, cost in effort, reliability in a busy lab (Wi-Fi congestion, USB cable), latency, phone access, power.
    - (a) Kit screen on the device. Only works if it's a graphic screen; a 16×2 character LCD can't draw positions (at most mode + live distance as a *secondary* readout).
    - (b) PC over USB serial → Python viewer (`tools/radar_view.py`). Simple and reliable; needs Python on the lab PC.
    - (c) PC over USB serial → a web page in Chrome using the Web Serial API. Nothing to install; Chrome/Edge only.
    - (d) ESP32 hosts a web page (soft-AP + WebSocket). PC and phone both work; adds Wi-Fi code, power draw and the brief's questions on lost connections / who has control.
    - (e) 32×8 MAX7219 from MC2: too coarse for positions; listed only to show it was considered.
    - Note: (b)–(d) can share the same drawing rules (`radar_gfx` ideas, same serial protocol), so we can prototype on simulated data now (S4) and decide after B4 without losing work.
  - D-SCAN: stop-and-ping (move, settle, ping) / continuous sweep with pings on the fly.
  - D-STEP: step size 1° / 2° / 3° / 5° (from S1).
  - D-ECHO: timing the echo with GPIO interrupt + esp_timer / RMT receiver / blocking busy-wait (rejected).
  - D-JOY: joystick position control / rate control (test both in T-JOY).
  - D-FILTER: raw / median of 3 per bin / reject jumps. The brief asks for "reducing unstable readings without hiding genuine changes".
  - D-MOUNT: sensor on servo horn bracket / pan from the base / fixed sensor array (rejected: only one sensor).
- [ ] **D3** Mode state machine diagram (`mode_fsm.h`) and the lock-on sub-states (`target_track.h`: SEARCHING → CANDIDATE → LOCKED → lost → SEARCHING).
- [ ] **D4** Electrical design. Schematic (KiCad, like MC2) with:
  - echo divider calculation (1 kΩ / 2 kΩ → 3.33 V; check current and edge speed);
  - joystick on 3.3 V (why not 5 V);
  - servo supply: SG90 peak/stall current (datasheet), whether the board's 5 V pin can supply it, the 470–1000 µF capacitor, and the brown-out risk when the servo starts;
  - screen supply and logic levels (if an on-device screen is used); Wi-Fi peak current (if the web option is used);
  - power budget per mode.
- [ ] **D5** Case and mount design and how it changes the circuit (slides emphasise this). Sketch + a short list of consequences, e.g.:
  - The sensor rides on the servo, so its 4 wires flex every sweep: service loop, strain relief, wire length, and connector vs solder.
  - The capacitor and divider sit near the servo and sensor, not on the far breadboard.
  - Sensor height and tilt: too low and it sees the table (floor echo).
  - The front must not cover the transducers: any window blocks ultrasound.
  - The base must not "walk" when the servo reverses: weight or clamps.
  - Joystick (and screen, if any) placement for the user; USB cable route if a PC is the display.
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
- [ ] **S2** `sim/scene.py`: scene simulator.
  - A 2D desk scene (poles = circles, boxes, a wall at an angle), a beam cone of about ±7.5°, the nearest surface in the cone returns an echo, surfaces at a steep angle return none (specular), plus Gaussian noise and random dropouts.
  - Emits the **same serial protocol** as the firmware (`R,…` lines), so everything downstream can't tell sim from real.
  - Shows the "smear": one thin pole appears across about 15° of bins. That motivates the edge-midpoint in D-LOCK.
- [ ] **S3** Lock-on logic on the laptop (the main simulation activity):
  - implement `scan_map`, `sweep_plan`, `target_track`, `mode_fsm` (pure C) + host tests in `host_tests/`;
  - drive them with S2 scenes: static pole, slowly moving pole, two poles close together, pole removed, noisy/dropout readings, nothing there;
  - record lock time, angle error vs true centre, false locks and lost-target time while varying `APP_LOCK_*`, then pick values with evidence.
  - *Assumptions:* S2's idealised sensor. Later re-run with recorded real scans (I7).
- [ ] **S4** Display prototype on simulated data, so D-DISPLAY can be judged before the kit arrives. Start with `tools/radar_view.py` (Python); if the team leans to a web page, prototype that as `tools/web/radar.html` fed by the same lines.
  - `tools/radar_view.py`: PC viewer (pygame or matplotlib). Reads `R,…` lines from a serial port **or** a file/S2 pipe. Draws rings, beam, points faded by age, a shape per status, the mode name and a STALE banner. This prototypes the display before the hardware exists (one of the brief's example simulations). Whatever D-DISPLAY decides, it stays useful as the logging/evidence tool.
- [ ] **S5** (optional) Wokwi project (`sim/wokwi/`): ESP32-S3 + HC-SR04 + servo + joystick (+ a screen if relevant), to check the wiring and the servo/ping sequencing. Note Wokwi's sensor is ideal: no beam width, no noise.
- [ ] **S6** Write up the simulation section of `DESIGN.txt`: question → method → result → assumptions → what the hardware must confirm.

## Phase B: bring-ups (kit week). Separate IDF projects in `bringup/`

- [ ] **B1** `bringup/01_servo`: sweep 0→180 slowly; calibrate `APP_SERVO_MIN/MAX_US` against a protractor; measure the time for a 2° step + settle (camera at 240 fps or a sensor reading that stabilises); watch for brown-out resets when it starts. Sets `APP_SERVO_*`.
- [ ] **B2** `bringup/02_hcsr04`: fixed angle, log `echo_us` and cm at 10/25/50/75/100/125/150 cm against a tape measure (10 pings each). Check ECHO at the GPIO with a meter/scope (≤ 3.3 V). Unplug ECHO → must log FAILED, not 0 cm. Sets `APP_US_*`, gives T-DIST data.
- [ ] **B3** `bringup/03_joystick`: raw counts at rest, full left/right/up/down, centre drift; press detection. Sets `APP_JOY_DEADZONE`.
- [ ] **B4** Identify the kit screen: graphic or character? resolution, controller (markings; pin labels: SDA/SCL only = I2C, SCK/MOSI/DC/CS = SPI, RS/E/D4–D7 = parallel character LCD). If graphic: `bringup/04_screen` esp_lcd hello world, time a full fill and a 100-line redraw. **Then decide D-DISPLAY** with S4's prototypes and this data.

## Phase I: implement (kit week onwards)

- [ ] **I1** Pure components finished and tested (from S3) + `radar_gfx` + `hcsr04_echo_to_cm` / `servo_deg_to_us` / `joystick_normalise` helpers with host tests.
- [ ] **I2** `servo` driver (LEDC 50 Hz, 14-bit).
- [ ] **I3** `serial_out` + protocol test against `radar_view.py`.
- [ ] **I4** `hcsr04` driver (D-ECHO choice); timeout → NO_ECHO; echo never rises / stuck high → FAILED.
- [ ] **I5** `scan_task` in SWEEP mode: next angle → move → settle → ping → map → serial. **Milestone M1: real scans on the PC viewer.** Commit and tag `m1-sweep`.
- [ ] **I6** The display chosen in D-DISPLAY, finished: rings + labels, beam, fading points, mode name, live distance, STALE/FAULT banners (on-device: `display` + `display_task`; PC: `radar_view.py`; web: ESP32 server + page). **M2: chosen display working on real data.**
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

- [ ] **X1** Phone page (only if D-DISPLAY didn't already make the web page the main display): ESP32 soft-AP + HTTP page + WebSocket push of `R,…` lines; shows connection status and "data no longer current"; one controller at a time, others view-only (brief question on contested control).

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
| 3 (kit) | Design → Implement | B1–B4, D-DISPLAY, D6, I1–I4 | Each part works on its own; display decided; pins final |
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

Anything else (ESP-IDF log lines) is ignored by the viewer, so normal logging still works.

## Decision log

Only decisions actually made go here, each with its reason/evidence. Everything still being weighed is in **Options under consideration** below and moves up when it is decided (by the team, from a test or a simulation).

| ID | Date | Decision | Alternatives | Reason / evidence |
| --- | --- | --- | --- | --- |
| D-FW | 26/11 | ESP-IDF v6.1 on the ESP32-S3 (`~/esp/esp-idf-v6.1`, loaded by the `get_idf` alias) | Arduino-ESP32; Uno R4 | Same toolchain/board as MC2; Joe is the only one working on it this week; v6.0.2 also installed; v6.1 pinned so builds are reproducible |
| D-ORDER | 26/11 | Build and test SWEEP first; LOCK and MANUAL only after it works | All modes at once | Brief: "keep a working version of the core scanner as you experiment" |
| | | | | |

## Options under consideration (not decided)

| ID | Question | Options | Leaning / why (if any) | Decided by |
| --- | --- | --- | --- | --- |
| D-DISPLAY | Where is the radar picture shown? | kit screen / PC over USB (Python) / PC over USB (Web Serial page) / ESP32 web page (PC + phone) / MAX7219 | None yet: depends on what the kit screen is | B4 + S4 prototypes, team |
| D-MODES | Which modes beyond SWEEP? | LOCK (lock-on), MANUAL (joystick), both, neither | Joe's idea: both; LOCK matches a brief extension ("rescan a region where an object was detected") | Team, after M1 |
| D-MODEBTN | How are modes switched? | joystick press / separate button / from the PC or phone page | Joystick press saves a part, if the kit joystick has a switch | Team + kit |
| D-ANGLE-TAG | Which angle is a reading drawn at? | settled angle at ping time / angle at send time / interpolated | Previous prototype moved the servo every 20 ms but pinged every 50 ms, so readings could be up to ~2.5° off | S1, T-MATCH |
| D-STATUS | How are no-echo and failed readings shown? | three statuses with shapes / distance 0 / hide them | Brief asks how the display tells them apart | S4 prototype, O2 user test |
| D-RANGE | Maximum range / echo timeout | 100 / 150 / 200 / 400 cm | Shorter = faster sweep; desk-scale use | S1, T-DIST |
| D-GAP | Time between pings | 20–50 ms (previous prototype) / ≥ 60 ms (datasheet) | Late echoes look like near objects | S1, T-XTALK |
| D-SCAN | Stop-and-ping or continuous | move → settle → ping / ping while moving | | S1, T-MATCH |
| D-STEP | Step size | 1 / 2 / 3 / 5° | | S1 |
| D-ECHO | How the echo is timed | GPIO interrupt + esp_timer / RMT / busy-wait | Busy-wait blocks everything | I4 |
| D-JOY | Joystick control | position / rate | | T-JOY |
| D-FILTER | Steadying readings | raw / median of 3 / reject jumps | Must not hide real changes | T-MOVE |
| D-MOUNT | How the sensor is moved | bracket on servo horn / pan base | | D5, team |

## Open questions

- [ ] What's actually in the kit: HC-SR04 or HC-SR04P (3.3 V)? SG90 or MG90S? Joystick module? What is the screen: graphic or long character LCD? (decides whether it's in D-DISPLAY at all)
- [ ] Team members and roles for this challenge [TEAM]
- [ ] Demo date (session 6)? Canvas reflection deadlines?
- [ ] Can the lab PC run Python with pyserial for the viewer?
- [ ] Is a 3D printer / laser cutter available for the mount (D5)?

## Sources

- Mini-Challenge 3 brief, *Scanning Ultrasonic Radar Sonar* (W. Al-Nuaimy, H. van Zalinge, Oct 2026): `docs/brief/`
- Week 9a lecture slides, *Ultrasonic Radar* (H. van Zalinge): expectations on design, simulation, case design
- CDIO Lab-in-a-Box: *ESP32 Wi-Fi Ultrasonic Radar Prototype* (J. Wang, Jul 2026): https://cdioatc.blogspot.com/2026/07/esp32-wifi-ultrasonic-radar-prototype.html
- Lab-in-a-Box companion blog (Z. Wang): https://wang66666.blogspot.com/ (speed-detector projects; related, not the spec)
- Arduino Project Hub: *Building an Ultrasonic Radar Using Arduino and Processing*: https://projecthub.arduino.cc/diegogalvan_1294/building-an-ultrasonic-radar-using-arduino-and-processing-59053e (still to read: C3)
- How To Mechatronics, Arduino Radar demo: https://www.youtube.com/watch?v=8NboJtVqWRw
- Processing Serial library: https://processing.org/reference/libraries/serial/
- Espressif Arduino-ESP32 Wi-Fi docs: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html
- AI use: plan, interfaces and drafts developed by Joe Gould with Claude (Anthropic); every decision recorded above.
