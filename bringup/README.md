# Bring-ups

One small, separate ESP-IDF project per part, run before the main firmware so each part is proven on its own. Created in Phase B (kit week). Each one logs to serial in a format the `tools/` scripts can read.

| Folder | Part | Wiring (PROPOSED, `main/app_config.h`) | What it proves / measures |
| --- | --- | --- | --- |
| `01_servo` | SG90 | signal → GPIO 14; red → 5 V; brown → GND; 470–1000 µF across 5 V/GND at the servo | pulse ↔ angle calibration, step + settle time, brown-out on start |
| `02_hcsr04` | HC-SR04 | VCC → 5 V; TRIG → GPIO 21; ECHO → 1 kΩ → GPIO 47, with 2 kΩ GPIO 47 → GND | echo time vs tape measure, noise, FAILED when unplugged |
| `03_joystick` | joystick | VCC → **3.3 V**; VRx → GPIO 4; VRy → GPIO 5; SW → GPIO 6 | raw range, centre, dead-zone, press |
| `04_screen` | kit screen (if graphic) | SPI: MOSI 11, SCLK 12, CS 10, DC 9, RST 8, BL 13 (or I2C: SDA 8, SCL 9) | what it is (graphic or character), bus, draw speed. Feeds D-DISPLAY |

Before powering anything: camera ribbon unplugged; check the HC-SR04 version (HC-SR04P runs at 3.3 V and needs no divider); measure the ECHO pin voltage at the GPIO side of the divider (must be ≤ 3.3 V).
