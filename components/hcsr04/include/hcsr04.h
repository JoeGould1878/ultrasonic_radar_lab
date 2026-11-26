/**
 * @file hcsr04.h
 * @brief HC-SR04 ultrasonic rangefinder: one ping -> distance + status.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Timing: 10 µs TRIG pulse; the module sends 8 cycles at 40 kHz and raises
 * ECHO for the round-trip time. distance = echo_us * c / 2, with c from the
 * air temperature (331.3 + 0.606·T m/s; ~0.17 % per °C).
 *
 * Implementation choice (decision D-ECHO, to make in Implement): time the
 * ECHO edges with a GPIO interrupt + esp_timer (simple, ~µs jitter) or the
 * RMT receiver (hardware-timed). Either way it must NOT busy-wait like
 * Arduino pulseIn(), so the scan task stays responsive.
 *
 * ECHO is 5 V on the classic module: divider to 3.3 V (see app_config.h).
 */
#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "scan_map.h"   /* reading_status_t */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int      trig_gpio;
    int      echo_gpio;
    uint32_t timeout_us;     /**< echo longer than this = NO_ECHO */
    float    temp_c;         /**< for the speed of sound */
} hcsr04_cfg_t;

typedef struct {
    reading_status_t status; /**< OK / NO_ECHO / FAILED */
    uint32_t         echo_us;
    float            dist_cm;
} hcsr04_result_t;

esp_err_t hcsr04_init(const hcsr04_cfg_t *cfg);

/** Fire one ping and wait (blocking the calling task only, not spinning)
 *  for the result. Caller enforces the >= 60 ms gap between pings. */
esp_err_t hcsr04_ping(hcsr04_result_t *out);

/** Pure helper, testable on the laptop: echo time -> cm at temp_c. */
float hcsr04_echo_to_cm(uint32_t echo_us, float temp_c);

#ifdef __cplusplus
}
#endif
