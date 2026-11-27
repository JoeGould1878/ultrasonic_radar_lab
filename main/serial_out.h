/**
 * @file serial_out.h
 * @brief One text line per ping on the USB serial port, for the PC viewer
 *        (tools/radar_view.py) and for logging evidence.
 *
 *   R,<t_ms>,<mode>,<angle_deg>,<dist_cm>,<status>      one reading
 *   M,<t_ms>,<mode>,<paused>,<fault>                     mode change
 *   T,<t_ms>,<state>,<centre_deg>,<left>,<right>,<dist> lock-on state
 *
 * status = OK | NOECHO | FAIL. Format is fixed in docs/PLAN.md — change
 * both ends together.
 *
 * dist_cm (D-PROTO-NULL): OK -> 1 decimal place, e.g. "52.3"; NOECHO and
 * FAIL -> "-", never a number, so a reader can't draw a fake 0 cm object.
 *
 * D-OWN: call only from scan_task; each line is written with a single call,
 * so lines never interleave and no mutex is needed.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 */
#pragma once
#include "app_types.h"
#include "target_track.h"

void serial_out_reading(const reading_t *r);
void serial_out_mode(uint32_t t_ms, app_mode_t mode, bool paused, bool fault);
void serial_out_track(uint32_t t_ms, const target_track_t *t);
