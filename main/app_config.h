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
#define APP_PIN_US_ECHO           9   /* PROPOSED, via divider; was 47 (DESIGN.txt R14) */

/* SG90 servo signal (LEDC PWM, 50 Hz). Servo power from 5 V with a
 * 470–1000 µF capacitor at the servo; common ground with the ESP32. */
#define APP_PIN_SERVO            14   /* PROPOSED */

/* Joystick module powered from 3.3 V (NOT 5 V: the pots would exceed the ADC range). */
#define APP_PIN_JOY_X             4   /* PROPOSED, ADC1_CH3 */
#define APP_PIN_JOY_Y             5   /* PROPOSED, ADC1_CH4 */
#define APP_PIN_JOY_SW            6   /* PROPOSED, to GND when pressed, pull-up */

/* No on-device screen: the display is the PC view over USB, then a web page
 * (D-DISPLAY), so no screen pins. */

/* --------------------------------------------------------------- servo ---- */

#define APP_SERVO_MIN_US        500   /* MEASURE: pulse for 0°   (bring-up B1) */
#define APP_SERVO_MAX_US       2400   /* MEASURE: pulse for 180° (bring-up B1) */
#define APP_SERVO_SPEED_MS_PER_DEG  2 /* MEASURE: SG90 datasheet ~0.1 s / 60° at 4.8 V */
#define APP_SERVO_SETTLE_MS      20   /* SIM + MEASURE: wait after a step before pinging */

/* --------------------------------------------------------------- sweep ---- */

#define APP_SWEEP_MIN_DEG        15   /* PROPOSED: avoid the servo end-stops */
#define APP_SWEEP_MAX_DEG       165   /* PROPOSED */
/* 2 deg: 4.5 s per 150 deg pass at a 60 ms gap (SC4 <= 5 s), 7 readings per
 * thin target (4 if the useful beam is only 8 deg). 1 deg misses SC4. D-STEP. */
/* Changing the step or start angle: check the scan_map bin layout (test_scan_map grid guard). */
#define APP_SWEEP_STEP_DEG        2   /* SIM S1 (s1_summary.txt); re-check at I7 */

/* ----------------------------------------------------------- ultrasonic ---- */

#define APP_US_MAX_RANGE_CM     150   /* PROPOSED: success criterion C-RANGE */
#define APP_US_MIN_RANGE_CM       3   /* datasheet ~2 cm */
/* Datasheet recommends >= 60 ms between pings (late echoes look like near
 * objects). S1: 60 ms already meets SC4, and echoes from up to 10.3 m cannot
 * land in the next ping. Fallback 40 ms ONLY if all three hold: I7 shows the
 * pass is over 5 s, B2 and T-XTALK show no ghosts or cross-talk, and the
 * CONCEIVE stakeholder row ("ping gap >= 60 ms") is changed to match. D-GAP. */
#define APP_US_PING_GAP_MS       60   /* SIM S1 (s1_summary.txt); re-check at I7 */
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
/* Bridge up to this many non-OK bins inside a cluster (S2: one dropout split a
 * smear, worst bearing error 6 deg). 0 = off until Joe approves it on S3's
 * with/without results, including the two-dowel merge check. */
#define APP_LOCK_BRIDGE_BINS      0   /* PROPOSED (S3) */

/* ------------------------------------------------------------ joystick ---- */

#define APP_JOY_DEADZONE        0.10f /* MEASURE: fraction of full scale */
#define APP_JOY_MODE_RATE         1   /* D-JOY: 1 = rate control, 0 = position control */
#define APP_JOY_RATE_DEG_PER_S   90   /* MEASURE: full-stick slew speed (rate control) */
#define APP_JOY_LONG_PRESS_MS   800

/* ------------------------------------------------------------- display ---- */

#define APP_DISPLAY_FPS          20
/* The bounce sweep revisits the end bins only every 2 passes (the middle every
 * pass), so a fade over 2 passes would reach zero just as they are refreshed.
 * With 3: 67 % brightness when redrawn in the middle, 33 % at the ends.
 * O2 judges whether this meets SC6 ("older than one pass visibly faded"). D-FADE. */
#define APP_FADE_SWEEPS           3   /* SIM S1 (s1_summary.txt); was 2 */
/* Max age for scan_map_expire(), in passes. Must be > 2 passes or real objects
 * at the arc ends are forgotten before they are re-measured. Removed objects
 * still go within 2 passes (SC5): the re-ping replaces them, not the expiry.
 * TODO(I1): pass APP_EXPIRE_SWEEPS * pass time to scan_map_expire(). Not used yet. */
#define APP_EXPIRE_SWEEPS         3   /* SIM S1 (s1_summary.txt) */
#define APP_STALE_MS           1500   /* no new reading for this long -> "STALE" banner */

/* ------------------------------------------------------------- tasks ---- */

#define APP_SCAN_TASK_PRIO        6
#define APP_INPUT_TASK_PRIO       5
#define APP_DISPLAY_TASK_PRIO     4
#define APP_INPUT_POLL_MS        10
