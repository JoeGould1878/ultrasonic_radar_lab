/**
 * @file mode_fsm.c
 * @brief Mode state machine — implementation (S3, 27/11).
 *
 * Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
 * Credits / sources used: none (standard C only).
 *
 * Rules (the header leaves these open):
 *  - Starts in SWEEP, not paused, no fault.
 *  - NEXT cycles SWEEP -> LOCK -> MANUAL -> SWEEP and always reports a
 *    change. It works while paused and leaves pause and fault as they are.
 *  - PAUSE_TOGGLE flips paused (always a change).
 *  - SENSOR_FAULT / SENSOR_OK set / clear fault; they report a change only
 *    if fault actually changed. The mode is never changed by a fault, so
 *    scanning carries on and can recover (header).
 *  - NONE or an unknown event: no change. A mode value out of range in the
 *    struct is put back to SWEEP by NEXT; its name is "?".
 */
#include "mode_fsm.h"

void mode_fsm_init(mode_fsm_t *f)
{
    f->mode   = MODE_SWEEP;
    f->paused = false;
    f->fault  = false;
}

bool mode_fsm_handle(mode_fsm_t *f, mode_evt_t evt)
{
    switch (evt) {
    case MODE_EVT_NEXT:
        f->mode = ((unsigned)f->mode + 1u < (unsigned)MODE_COUNT) ? (app_mode_t)(f->mode + 1)
                                                                  : MODE_SWEEP;
        return true;
    case MODE_EVT_PAUSE_TOGGLE:
        f->paused = !f->paused;
        return true;
    case MODE_EVT_SENSOR_FAULT:
        if (f->fault) {
            return false;
        }
        f->fault = true;
        return true;
    case MODE_EVT_SENSOR_OK:
        if (!f->fault) {
            return false;
        }
        f->fault = false;
        return true;
    case MODE_EVT_NONE:
    default:
        return false;
    }
}

const char *mode_fsm_name(app_mode_t mode)
{
    switch (mode) {
    case MODE_SWEEP:  return "SWEEP";
    case MODE_LOCK:   return "LOCK";
    case MODE_MANUAL: return "MANUAL";
    default:          return "?";
    }
}
