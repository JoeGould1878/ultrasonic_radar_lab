/**
 * @file scan_task.h
 * @brief Owns the servo and the ultrasonic sensor. One loop:
 *        ask sweep_plan for the next angle -> move -> settle -> ping ->
 *        store in scan_map -> send reading to display + serial -> wait out the ping gap.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 *
 * Proposed (D-ANGLE-TAG, to confirm with S1/T-MATCH): the reading is tagged with the angle the servo was commanded to BEFORE the
 * ping (after settling) — fixes the angle/reading mismatch in the previous
 * prototype, where the servo kept moving every 20 ms but pinged every 50 ms.
 * In MODE_LOCK it also runs target_track; in MODE_MANUAL it takes the
 * target angle from input_task.
 */
#pragma once
#include "esp_err.h"
#include "app_types.h"

esp_err_t scan_task_start(void);

/** Latest map, for the display (copy taken under a mutex). */
void scan_task_snapshot(scan_map_t *out);

/** Mode changes from input_task. */
void scan_task_set_mode(app_mode_t mode, bool paused);

/** Joystick target for MODE_MANUAL. */
void scan_task_set_manual(float target_deg);
