/**
 * @file lock_loop.h
 * @brief LOCK mode controller: where to point next, and when to switch between
 *        a full sweep and a narrow sector around the target. Pure C, no ESP-IDF.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic), S3 26/11.
 *
 * Why a component (not code inside scan_task): the same loop is run by the
 * laptop simulation (sim/lock_sim.py via host_tests) and by scan_task in I9,
 * so the firmware runs exactly the code whose APP_LOCK_* values were chosen
 * from evidence.
 *
 * Behaviour (D3 state diagram):
 *   SEARCHING / CANDIDATE  full sweep; target_track_on_pass() at each pass end.
 *   -> LOCKED              sector sweep, centre +/- sector_half_deg, clamped to
 *                          the arc. Tracker limits = the sector (edge flag).
 *                          target_track_on_ping() after every ping (fast "lost").
 *                          At each sector pass end: on_pass(), then recentre
 *                          the sector on the target.
 *   every resweep_ms       one full pass while still LOCKED (sees the rest of
 *                          the area; the brief's "rescan" extension), then
 *                          back to the sector if the target is still found.
 *                          A resweep starts at a sector end, usually mid-arc,
 *                          so the first arc end it reaches is a turnaround
 *                          (on_ping still runs, no on_pass) and one complete
 *                          end-to-end pass is judged after it. If it starts
 *                          at an arc end, that first pass is already complete.
 *   lost                   back to a full sweep, tracker limits = the arc.
 *
 * Use, once per ping (scan_task in LOCK mode, or the simulator):
 *   float a = lock_loop_next_angle(&ll);
 *   ... move servo to a, settle, ping ...
 *   scan_map_update(&map, a, dist, status, now);        // caller owns the map
 *   lock_loop_on_reading(&ll, &map, now, a, dist, status);
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "scan_map.h"
#include "sweep_plan.h"
#include "target_track.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    sweep_cfg_t sweep;            /**< arc and step (APP_SWEEP_*) */
    track_cfg_t track;            /**< APP_LOCK_*; gate_deg 0 -> sector_half_deg */
    float       sector_half_deg;  /**< APP_LOCK_SECTOR_HALF_DEG */
    uint32_t    resweep_ms;       /**< APP_LOCK_RESWEEP_S * 1000; 0 = never */
    uint32_t    ping_period_ms;   /**< time per ping (S1 model / measured), used
                                       to set the tracker's max bin age to one
                                       pass of the current plan + one ping */
} lock_loop_cfg_t;

typedef enum {
    LOCK_PLAN_FULL = 0,           /**< searching: full sweep */
    LOCK_PLAN_SECTOR,             /**< locked: sector around the target */
    LOCK_PLAN_RESWEEP,            /**< locked: periodic full pass */
} lock_plan_t;

typedef struct {
    lock_loop_cfg_t cfg;
    sweep_plan_t    plan;
    target_track_t  track;
    lock_plan_t     kind;
    uint32_t        last_full_ms; /**< end of the last full pass (resweep timer) */
    uint32_t        locked_at_ms; /**< when the current lock started */
    bool            resweep_turned; /**< RESWEEP: the turnaround arc end has been
                                         reached (or the resweep started at an
                                         arc end), so the next pass end closes a
                                         complete end-to-end pass */
} lock_loop_t;
/* Why resweep_turned (S3, 27/11, Joe approved): without it a resweep that
 * starts mid-arc would be judged at the first arc end after sweeping only
 * part of the arc, and the far side's bins (from the last resweep) are older
 * than the max age, so it would not see "the rest of the area". A check on
 * the map instead (is the far end fresh?) needs no field but is only right
 * while resweep_ms is longer than one full pass; the field holds for any
 * resweep_ms. */

/** Start in a full sweep (SEARCHING) from start_deg. */
void lock_loop_init(lock_loop_t *ll, const lock_loop_cfg_t *cfg, float start_deg);

/** Next commanded angle. Call once per ping, before moving the servo. */
float lock_loop_next_angle(lock_loop_t *ll);

/** Feed the reading just stored in the map. Updates the tracker and, at pass
 *  ends or on a lock / loss, the sweep plan. Returns the tracker state. */
track_state_t lock_loop_on_reading(lock_loop_t *ll, const scan_map_t *map, uint32_t now_ms,
                                   float angle_deg, float dist_cm, reading_status_t status);

/** Back to SEARCHING with a full sweep, keeping the current angle (used when
 *  the mode is switched away from LOCK and back). */
void lock_loop_reset(lock_loop_t *ll);

/** Read-only views for the display and the T line. */
const target_track_t *lock_loop_track(const lock_loop_t *ll);
lock_plan_t           lock_loop_plan(const lock_loop_t *ll);

#ifdef __cplusplus
}
#endif
