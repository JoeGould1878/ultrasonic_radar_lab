# Scanning Ultrasonic Sonar

Desk-scale scanning sonar with a radar-style display. Mini-Challenge 3 (CDIO), 2026.

An HC-SR04 ultrasonic sensor on an SG90 servo sweeps a 150° arc. An ESP32-S3 ties each distance to the direction the sensor was pointing and draws the result on a radar-style display. It is displayed on a PC over USB first (`tools/radar_view.py`), then on a web page served by the ESP32 that a phone can open too (decision D-DISPLAY; the kit's screen is not used). The display is honest about its limits: it shows how old each point is, and keeps "no echo" and "sensor failed" apart. Pressing the joystick cycles three modes: **SWEEP**, **LOCK** (follow a detected object) and **MANUAL** (point it with the joystick).

> It's sonar, not radar: it uses sound echoes, not radio waves. The display only looks like a radar screen.

**Status:** skeleton: headers, build files, plan, Conceive draft. See [`docs/PLAN.md`](docs/PLAN.md) for every task and [`docs/CONTEXT.md`](docs/CONTEXT.md) for where things stand.

## Hardware (expected; confirmed when the kit arrives)

| Part | Notes |
| --- | --- |
| Freenove ESP32-S3-WROOM | camera ribbon unplugged |
| HC-SR04 | 5 V; ECHO through a 1 k / 2 k divider to 3.3 V |
| SG90 servo | 5 V with 470–1000 µF capacitor; LEDC 50 Hz |
| Analogue joystick + push switch | powered from 3.3 V; press = mode |
| Display | PC view over USB (`tools/radar_view.py`) first, then a web page served by the ESP32 (D-DISPLAY); no on-device screen |

Pins: [`main/app_config.h`](main/app_config.h) (all PROPOSED until bring-up).

## Layout

```
ultrasonic_radar_lab/
├── main/                 tasks: scan (servo+sensor), input (joystick), display, serial out
├── components/
│   ├── hcsr04/           ultrasonic driver (ping -> cm + status)
│   ├── servo/            SG90 on LEDC
│   ├── joystick/         2-axis ADC, centre + dead-zone
│   ├── button/           debounced switch (from MC2)
│   ├── scan_map/         latest reading per angle, status, age        [pure C]
│   ├── sweep_plan/       next angle for FULL / SECTOR / MANUAL         [pure C]
│   ├── target_track/     lock-on: cluster, confirm, follow, lost       [pure C]
│   ├── mode_fsm/         SWEEP / LOCK / MANUAL, pause, fault           [pure C]
│   └── lock_loop/        LOCK controller: full sweep <-> sector        [pure C]
├── bringup/              standalone hardware tests (servo, sensor, joystick)
├── host_tests/           laptop tests for the [pure C] components
├── sim/                  timing model, scene simulator, (Wokwi)
├── tools/                PC radar viewer, log capture/analysis
└── docs/                 PLAN, CONTEXT, LAB_TESTS, CDIO write-ups, brief, evidence
```

Data path: `sweep_plan → servo → (settle) → hcsr04 → scan_map → target_track → serial_out → PC viewer / web page`.

## Build

```bash
. ~/esp/esp-idf-v6.1/export.sh   # ESP-IDF v6.1 (D-FW); Joe: get_idf
idf.py set-target esp32s3      # first time only
idf.py build flash -p /dev/ttyACM0 monitor
cd host_tests && make          # laptop tests, no board needed
```

## Credits and sources

- Brief: Mini-Challenge 3, *Scanning Ultrasonic Radar Sonar* (W. Al-Nuaimy, H. van Zalinge, 2026): `docs/brief/`
- Previous prototype used as reference (no code reused): [CDIO Lab-in-a-Box ESP32 Wi-Fi Ultrasonic Radar](https://cdioatc.blogspot.com/2026/07/esp32-wifi-ultrasonic-radar-prototype.html) (J. Wang)
- [pygame](https://www.pygame.org) 2.6.1 (LGPL, pygame.org): drawing for `tools/radar_view.py` (library only, no code copied)
- `components/button` reused from our MC2 project ([spectrum_visualiser_lab](https://github.com/JoeGould1878/spectrum_visualiser_lab))
- AI use: plan, interfaces (headers) and drafts developed by Joe Gould with Claude (Anthropic); all requirements, design decisions, hardware testing and evaluation by the team. Each source file's header says who designed and who implemented it.
