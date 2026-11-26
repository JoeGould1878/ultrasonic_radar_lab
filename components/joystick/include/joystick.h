/**
 * @file joystick.h
 * @brief 2-axis analogue joystick (two pots) on ADC1, normalised to -1..+1.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Power the module from 3.3 V so the pot outputs stay inside the ADC range.
 * The centre is measured at start-up (sticks rarely rest at exactly mid-scale),
 * and a dead-zone stops the servo creeping when the stick is let go.
 * The push switch is read by the shared `button` component.
 */
#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int   gpio_x;
    int   gpio_y;
    float deadzone;      /**< 0..1 of full scale */
} joystick_cfg_t;

typedef struct {
    float x, y;          /**< -1..+1 after centre, dead-zone and rescale */
    int   raw_x, raw_y;  /**< ADC counts, for the bring-up log */
} joystick_state_t;

/** Configure ADC and measure the resting centre (don't touch the stick). */
esp_err_t joystick_init(const joystick_cfg_t *cfg);

esp_err_t joystick_read(joystick_state_t *out);

/** Pure helper, testable on the laptop: raw -> -1..+1 with dead-zone. */
float joystick_normalise(int raw, int centre, int full_scale, float deadzone);

#ifdef __cplusplus
}
#endif
