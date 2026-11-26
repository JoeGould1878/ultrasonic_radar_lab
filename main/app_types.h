/**
 * @file app_types.h
 * @brief Types shared between tasks.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 */
#pragma once

#include <stdint.h>
#include "mode_fsm.h"
#include "scan_map.h"

/** One ping, already tied to the angle the servo was AT when it fired
 *  (not the angle it is heading to — the previous prototype mixed these up). */
typedef struct {
    uint32_t     t_ms;        /**< when the ping fired */
    float        angle_deg;   /**< commanded angle after settling */
    float        dist_cm;     /**< valid only if status == READING_OK */
    reading_status_t status;  /**< OK / NO_ECHO / FAILED */
    app_mode_t   mode;        /**< mode that produced it (for the log) */
} reading_t;

/** Events into the mode state machine come from input_task and scan_task;
 *  see mode_fsm.h for the list. */
