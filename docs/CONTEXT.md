# Ultrasonic sonar — running context

Kept by Claude so any new chat or Claude Code session can pick up where we left off. Update after each task.
**Last updated:** Thu 26 Nov 2026

## How we work

- Claude writes code and docs; **everything goes through Joe** (team not around this week). Joe flashes, tests and records evidence.
- Master task list: `docs/PLAN.md`. Work top to bottom, tick off, log here.
- Joe stays in the loop: after each chunk, a short summary of what was written, the decisions made and why, and the next step. Team decisions (criteria, modes, wiring) are checked with him first.

## Where things are

- Repo: `~/esp/s1_labs/ultrasonic_radar_lab` (suggested) → GitHub `JoeGould1878/ultrasonic_radar_lab` (to create: P0.1)
- Plan + decision log: `docs/PLAN.md` · Lab tests: `docs/LAB_TESTS.md` · Write-ups: `docs/CDIO/`
- Brief: `docs/brief/MiniChallenge3-ScanningUltrasonicRadar.pdf`
- Previous project for patterns/tools: https://github.com/JoeGould1878/spectrum_visualiser_lab (diagram scripts, log tools, KiCad generator)
- Environment: Debian 13, ESP-IDF v6.1 (`~/esp/esp-idf-v6.1`, `get_idf` alias), VS Code; board on `/dev/ttyACM0`

## Hardware

- Known: Freenove ESP32-S3-WROOM (camera unplugged), MC2 parts, 32×8 MAX7219, and a screen in the box (type unknown; may be a long character LCD, which would rule it out for the radar picture).
- Expected in the kit (next week): HC-SR04, SG90, analogue joystick. Not confirmed.
- Pins: `main/app_config.h`, all PROPOSED.

## Decided

- ESP-IDF v6.1 (pinned; D-FW), same board as MC2.
- Three modes, SWEEP first; LOCK and MANUAL are extensions; joystick press cycles modes (proposed).
- This week = Conceive, Design, simulation (no kit).
- **Not decided:** where the radar is displayed (D-DISPLAY: kit screen / PC over USB / web page on PC + phone). Keep all docs neutral until it's decided with evidence.

## Progress

- [x] 26 Nov: brief + Week 9a slides + previous prototype blog read; repo skeleton (headers, build files, stubs, host-test Makefile); `docs/PLAN.md`; `docs/CDIO/CONCEIVE.txt` drafted.
- [x] 26 Nov: P0.1–P0.3 done (repo pushed, first ESP-IDF build clean, Python venv + `requirements.txt`).
- [x] 26 Nov: S1 timing model done; recommendations for D-STEP, D-SCAN, D-GAP and `APP_FADE_SWEEPS` waiting for Joe.
- [x] 26 Nov: Joe approved the S1 recommendations; applied to app_config.h, decision log and CONCEIVE.
- [x] 26 Nov: S2 scene simulator done (35 scenes + truth files; Q1–Q4 answered).
- [ ] **Next:** S3 lock-on logic + host tests (work order in PLAN.md); C2 Joe reviews CONCEIVE.

## Open questions

See `docs/PLAN.md` → Open questions.

## Log

- **26 Nov:** skeleton + plan + Conceive draft (Claude, in chat). Not yet built with ESP-IDF; pure components syntax-checked with gcc (`host_tests: make check-headers`).
- **26 Nov:** P0.2 first build with ESP-IDF v6.1 (`~/esp/esp-idf-v6.1`, the `get_idf` alias), target esp32s3: builds clean, no errors or warnings in project code, no source or header changes needed. Image 169,856 B; DIRAM 14.1 % used. `host_tests: make` passes (header check only; 0 test suites yet). P0.3 `.venv` + pinned `requirements.txt` (numpy 2.5.5, matplotlib 3.11.2, pyserial 3.5); checked it installs into a fresh venv.
- **26 Nov:** `sdkconfig.defaults` sets flash size to 8 MB (N8R8 module; was the 2 MB default). Still to confirm from the first boot log. Rebuild clean. The 5 CMake "private include directory" warnings at configure time come from ESP-IDF v6.1's own `esp_wifi`/`wpa_supplicant` components, not project code.
- **26 Nov:** ESP-IDF pinned to v6.1 (Joe approved; D-FW updated). v6.0.2 is also installed, so the version is now named everywhere: CLAUDE.md, README.md build steps, PLAN.md status + D-FW, CONTEXT.md.
- **26 Nov:** S1 `sim/sweep_timing.py` reads the defaults from `main/app_config.h` and models step 1/2/3/5° x gap 30/40/60 ms x range 100/150/200 cm x stop-and-ping / ping-while-moving. Outputs in `docs/evidence/sim/s1_*` (4 PNG, CSV, summary). Key results: step 2° + gap 60 ms = 4.5 s pass (SC4 met), 1° misses SC4 at every gap; ping-while-moving saves 0 % at 40-60 ms but adds a 3.2° jump between passes at 2°; end bins are only redrawn every 2 passes, so APP_FADE_SWEEPS = 2 fades them to zero just as they're refreshed; range has no effect on pass time at a 60 ms gap. Proposed (not applied, waiting for Joe): D-STEP 2°, D-SCAN stop-and-ping, D-GAP 60 ms, APP_FADE_SWEEPS 3. Assumptions A5/A6/A7 (overhead, 38 ms no-echo hold, 8° what-if beam) are not in app_config.h; B1/B2 must measure them.
- **26 Nov:** S1 recommendations approved by Joe and applied. Decision log: D-STEP 2°, D-SCAN stop-and-ping, D-ANGLE-TAG settled angle at ping time, D-GAP 60 ms (40 ms fallback only if I7 pass > 5 s AND B2/T-XTALK clean AND the CONCEIVE stakeholder row changes), D-FADE 3 passes; all cite `docs/evidence/sim/s1_summary.txt`. These four left "Options under consideration". `app_config.h`: step and gap marked SIM S1, `APP_FADE_SWEEPS` 2 → 3, new `APP_EXPIRE_SWEEPS` 3 (not wired up until I1). CONCEIVE section 5 "Why these numbers" corrected (range doesn't change pass time at 60 ms); section 7 gains the SWEEP-can't-follow-a-walker limit as a reason for LOCK. No success criteria changed.
- **26 Nov:** S1 tidy-up: `sim/sweep_timing.py` now always compares fade = 2 passes (original) with 3 passes (D-FADE), whatever `APP_FADE_SWEEPS` is set to, so the evidence no longer shifts with the config. Outputs regenerated: only `s1_point_age.png` and the config + fade lines of `s1_summary.txt` changed; the CSV and other 3 charts are byte-identical. PLAN D-RANGE leaning reworded (S1: range doesn't change pass time at a 60 ms gap).
- **26 Nov:** S2 `sim/scene.py`: a 2D bench with the LAB_TESTS targets, a 15° hard-cone beam (8° what-if), first echo wins, 25° specular cutoff (15/25/35 swept), noise σ = max(0.3 cm, 1 %), 2 % dropouts, all ASSUMED (B2/T-MAT replace them); timing from S1. 35 scenes in the firmware protocol + truth CSVs in `docs/evidence/sim/s2_scenes/`, for S3/S4. Results (`s2_summary.txt`): T1 smears over 7–8 bins (~15°) at every range; nearest-bin error mean ~4°, worst 7–8°, edge midpoint mean <1° but worst 6° when one dropout splits the smear (S3: bridge one-bin gaps); at the arc ends (15/165°) only ~4.5 bins and the midpoint is biased ~4.5° inward (worst 5.0°, right at SC3). Two T3s merge below ~18° gap (15° beam) / ~11° (8°). T2 board vanishes at 40° tilt at 50 cm, 35° at 100 cm (cutoff 25°). A moving T1 smears 20–24° with the sweep and 12–15° against it; per-pass bearing within ~1°, but it has moved 16–38 cm by the end of the pass. Protocol: R/M lines match `main/serial_out.h`; decimals and dist for NOECHO/FAIL are not defined anywhere (S2 uses 1 decimal and 0.0, PROVISIONAL, for Joe).
- **26 Nov:** Joe's S2 decisions applied. D-PROTO-NULL: `dist_cm` is `-` for NOECHO/FAIL, 1 decimal place when OK (PLAN protocol section, `serial_out.h` comment only, S2 `format_r`); S2 re-run, and only the 35 scene logs changed (`0.0` → `-` on NOECHO/FAIL lines, nothing else). D-EDGE: objects touching the arc ends get an "edge" flag and a low-confidence bearing (S3 implements, S4 displays); SC1/SC3 unchanged. CONCEIVE section 7: three S2 limits added (arc ends, two objects under ~17°, tilted board gives no echo).
