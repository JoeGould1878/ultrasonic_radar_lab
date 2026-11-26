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
- Environment: Debian 13, ESP-IDF v6, VS Code; board on `/dev/ttyACM0`

## Hardware

- Known: Freenove ESP32-S3-WROOM (camera unplugged), MC2 parts, 32×8 MAX7219, and a screen in the box (type unknown; may be a long character LCD, which would rule it out for the radar picture).
- Expected in the kit (next week): HC-SR04, SG90, analogue joystick. Not confirmed.
- Pins: `main/app_config.h`, all PROPOSED.

## Decided

- ESP-IDF v6, same board as MC2.
- Three modes, SWEEP first; LOCK and MANUAL are extensions; joystick press cycles modes (proposed).
- This week = Conceive, Design, simulation (no kit).
- **Not decided:** where the radar is displayed (D-DISPLAY: kit screen / PC over USB / web page on PC + phone). Keep all docs neutral until it's decided with evidence.

## Progress

- [x] 26 Nov: brief + Week 9a slides + previous prototype blog read; repo skeleton (headers, build files, stubs, host-test Makefile); `docs/PLAN.md`; `docs/CDIO/CONCEIVE.txt` drafted.
- [ ] **Next:** P0.1 push to GitHub → P0.2 first build → C2 Joe reviews CONCEIVE → S1 timing model.

## Open questions

See `docs/PLAN.md` → Open questions.

## Log

- **26 Nov:** skeleton + plan + Conceive draft (Claude, in chat). Not yet built with ESP-IDF; pure components syntax-checked with gcc (`host_tests: make check-headers`).
