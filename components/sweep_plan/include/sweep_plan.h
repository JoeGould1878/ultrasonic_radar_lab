/**
 * @file sweep_plan.h
 * @brief Decides where the servo points next, for each mode. Pure C, no ESP-IDF.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Three behaviours, one interface, so scan_task stays the same in every mode:
 *   FULL    — bounce between min and max in fixed steps (auto sweep)
 *   SECTOR  — bounce inside centre ± half_width (lock-on), clamped to min/max
 *   MANUAL  — move toward a target angle, at most max_step per call (joystick)
 */
#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SWEEP_FULL = 0,
    SWEEP_SECTOR,
    SWEEP_MANUAL,
} sweep_kind_t;

typedef struct {
    float min_deg, max_deg;   /**< mechanical limits of the scan */
    float step_deg;           /**< FULL / SECTOR step */
} sweep_cfg_t;

typedef struct {
    sweep_cfg_t  cfg;
    sweep_kind_t kind;
    float        angle_deg;      /**< current commanded angle */
    int          dir;            /**< +1 / -1 */
    float        sector_centre;  /**< SECTOR */
    float        sector_half;    /**< SECTOR */
    float        manual_target;  /**< MANUAL */
    bool         sweep_done;     /**< set when a FULL/SECTOR pass reaches an end */
} sweep_plan_t;

void sweep_plan_init(sweep_plan_t *p, const sweep_cfg_t *cfg, float start_deg);

/** Switch behaviour; keeps the current angle so the servo doesn't jump. */
void sweep_plan_full(sweep_plan_t *p);
void sweep_plan_sector(sweep_plan_t *p, float centre_deg, float half_width_deg);
void sweep_plan_manual(sweep_plan_t *p, float target_deg);

/** Move the sector centre (lock-on follows a moving target). */
void sweep_plan_recentre(sweep_plan_t *p, float centre_deg);

/** Advance one step and return the next commanded angle.
 *  MANUAL: max_step_deg limits how far it moves this call (slew limit). */
float sweep_plan_next(sweep_plan_t *p, float max_step_deg);

/** True once after each end-of-pass (used to count sweeps). Clears the flag. */
bool sweep_plan_take_pass_done(sweep_plan_t *p);

#ifdef __cplusplus
}
#endif
