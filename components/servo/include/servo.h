/**
 * @file servo.h
 * @brief Hobby servo (SG90) on LEDC PWM, 50 Hz, angle in degrees.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * The SG90 has no position feedback: the code only knows the angle it
 * COMMANDED. That is why scan_task waits a settle time after each step
 * before pinging, and why angle accuracy is measured in Operate (test T-ANG).
 */
#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int gpio;
    int min_us;     /**< pulse width for 0°   (calibrated at bring-up B1) */
    int max_us;     /**< pulse width for 180° */
} servo_cfg_t;

esp_err_t servo_init(const servo_cfg_t *cfg);

/** Command an angle 0–180° (clamped). */
esp_err_t servo_set_deg(float deg);

/** Stop sending pulses: servo goes limp, stops buzzing, saves power. */
esp_err_t servo_release(void);

/** Pure helper, testable on the laptop: angle -> pulse width in µs. */
int servo_deg_to_us(const servo_cfg_t *cfg, float deg);

#ifdef __cplusplus
}
#endif
