/**
 * @file app_config.h
 * @brief Pins, timings and thresholds — the single place every number lives.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 *
 * Marks:
 *   PROPOSED  — chosen on paper, confirm at bring-up (kit arrives week 2)
 *   MEASURE   — set from a test in docs/LAB_TESTS.md; add a decision-log line
 *   SIM       — first value comes from a simulation in sim/; re-check on hardware
 *
 * Board: Freenove ESP32-S3-WROOM, camera ribbon unplugged (frees GPIO 4–18).
 * Never use 35/36/37 (PSRAM), 19/20 (USB), 0/3/45/46 (strapping), 2 (on-board LED).
 */
#pragma once

/* ---------------------------------------------------------------- pins ---- */

/* HC-SR04 at 5 V. ECHO is a 5 V output: 1 kΩ series + 2 kΩ to GND -> 3.3 V.
 * (If the kit has the HC-SR04P / 3.3 V version, power it at 3.3 V, no divider.) */
#define APP_PIN_US_TRIG          21   /* PROPOSED */
#define APP_PIN_US_ECHO          47   /* PROPOSED, via divider */

/* SG90 servo signal (LEDC PWM, 50 Hz). Servo power from 5 V with a
 * 470–1000 µF capacitor at the servo; common ground with the ESP32. */
#define APP_PIN_SERVO            14   /* PROPOSED */

/* Joystick module powered from 3.3 V (NOT 5 V: the pots would exceed the ADC range). */
#define APP_PIN_JOY_X             4   /* PROPOSED, ADC1_CH3 */
#define APP_PIN_JOY_Y             5   /* PROPOSED, ADC1_CH4 */
#define APP_PIN_JOY_SW            6   /* PROPOSED, to GND when pressed, pull-up */

/* On-device screen — ONLY if D-DISPLAY picks the kit's screen (still open).
 * SPI set shown; if it is I2C use SDA 8 / SCL 9; a parallel character LCD
 * would need its own pin set. Unused if the display is the PC or web page. */
#define APP_PIN_SCREEN_MOSI         11   /* PROPOSED */
#define APP_PIN_SCREEN_SCLK         12   /* PROPOSED */
#define APP_PIN_SCREEN_CS           10   /* PROPOSED */
#define APP_PIN_SCREEN_DC            9   /* PROPOSED */
#define APP_PIN_SCREEN_RST           8   /* PROPOSED */
#define APP_PIN_SCREEN_BL           13   /* PROPOSED, backlight (PWM-able) */

/* --------------------------------------------------------------- servo ---- */

#define APP_SERVO_MIN_US        500   /* MEASURE: pulse for 0°   (bring-up B1) */
#define APP_SERVO_MAX_US       2400   /* MEASURE: pulse for 180° (bring-up B1) */
#define APP_SERVO_SPEED_MS_PER_DEG  2 /* MEASURE: SG90 datasheet ~0.1 s / 60° at 4.8 V */
#define APP_SERVO_SETTLE_MS      20   /* SIM + MEASURE: wait after a step before pinging */

/* --------------------------------------------------------------- sweep ---- */

#define APP_SWEEP_MIN_DEG        15   /* PROPOSED: avoid the servo end-stops */
#define APP_SWEEP_MAX_DEG       165   /* PROPOSED */
#define APP_SWEEP_STEP_DEG        2   /* SIM: step vs sweep time vs beam width */

/* ----------------------------------------------------------- ultrasonic ---- */

#define APP_US_MAX_RANGE_CM     150   /* PROPOSED: success criterion C-RANGE */
#define APP_US_MIN_RANGE_CM       3   /* datasheet ~2 cm */
#define APP_US_PING_GAP_MS       60   /* datasheet recommends >= 60 ms between pings (old echoes) */
#define APP_US_TEMP_C            20   /* speed of sound = 331.3 + 0.606*T m/s; MEASURE lab temp */
/* Echo timeout follows from max range: 2 * 1.5 m / 343 m/s ≈ 8.7 ms (+ margin) */
#define APP_US_TIMEOUT_US     10000

/* ------------------------------------------------------------ lock-on ---- */

#define APP_LOCK_DIST_TOL_CM      8   /* SIM: neighbouring bins are "the same object" */
#define APP_LOCK_MIN_BINS         2   /* SIM: object must span >= this many bins */
#define APP_LOCK_CONFIRM_SWEEPS   2   /* SIM: seen this many sweeps running before locking */
#define APP_LOCK_SECTOR_HALF_DEG 15   /* SIM: narrow sweep ± around the target */
#define APP_LOCK_LOST_PINGS       6   /* SIM: no echo near target this many times -> lost */
#define APP_LOCK_RESWEEP_S       10   /* SIM: full wide sweep every N s while locked */

/* ------------------------------------------------------------ joystick ---- */

#define APP_JOY_DEADZONE        0.10f /* MEASURE: fraction of full scale */
#define APP_JOY_MODE_RATE         1   /* D-JOY: 1 = rate control, 0 = position control */
#define APP_JOY_RATE_DEG_PER_S   90   /* MEASURE: full-stick slew speed (rate control) */
#define APP_JOY_LONG_PRESS_MS   800

/* ------------------------------------------------------------- display ---- */

#define APP_DISPLAY_FPS          20
#define APP_FADE_SWEEPS           2   /* a point fades out over this many sweep times */
#define APP_STALE_MS           1500   /* no new reading for this long -> "STALE" banner */

/* ------------------------------------------------------------- tasks ---- */

#define APP_SCAN_TASK_PRIO        6
#define APP_INPUT_TASK_PRIO       5
#define APP_DISPLAY_TASK_PRIO     4
#define APP_INPUT_POLL_MS        10
