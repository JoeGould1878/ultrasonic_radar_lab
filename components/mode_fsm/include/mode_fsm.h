/**
 * @file mode_fsm.h
 * @brief The three operating modes and how they change. Pure C, no ESP-IDF.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 *   SWEEP ──press──► LOCK (searching ⇄ locked) ──press──► MANUAL ──press──► SWEEP
 *
 * Proposed (D-MODEBTN, not decided): joystick press (short) cycles the mode,
 * long press = pause/resume. The FSM only sees events, so a separate button
 * or a command from the PC/phone page works the same way.
 * Lock-on and joystick are EXTENSIONS: the build plan gets SWEEP working and
 * tested first (essential), then adds the others.
 */
#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MODE_SWEEP = 0,     /**< auto sweep */
    MODE_LOCK,          /**< auto sweep + lock-on */
    MODE_MANUAL,        /**< joystick controlled */
    MODE_COUNT
} app_mode_t;

typedef enum {
    MODE_EVT_NONE = 0,
    MODE_EVT_NEXT,          /**< short press */
    MODE_EVT_PAUSE_TOGGLE,  /**< long press */
    MODE_EVT_SENSOR_FAULT,  /**< several FAILED readings in a row */
    MODE_EVT_SENSOR_OK,
} mode_evt_t;

typedef struct {
    app_mode_t mode;
    bool       paused;
    bool       fault;       /**< shown on screen; scanning continues so it can recover */
} mode_fsm_t;

void mode_fsm_init(mode_fsm_t *f);

/** Apply an event. Returns true if the mode (or pause/fault) changed. */
bool mode_fsm_handle(mode_fsm_t *f, mode_evt_t evt);

/** Short name for the screen and the serial log, e.g. "SWEEP". */
const char *mode_fsm_name(app_mode_t mode);

#ifdef __cplusplus
}
#endif
