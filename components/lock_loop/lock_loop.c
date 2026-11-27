/**
 * @file lock_loop.c
 * @brief LOCK mode controller — implementation (S3, 27/11).
 *
 * Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
 * Credits / sources used: none (standard C only).
 *
 * Rules (the header leaves these open):
 *  - Config: gate_deg <= 0 -> sector_half_deg (header). The tracker's arc
 *    is always the sweep arc (track.arc_min/max_deg overwritten with
 *    sweep.min/max_deg), so the two can never disagree.
 *  - Max bin age for on_pass = one pass of the CURRENT plan + one ping:
 *    steps between sweep_plan_pass_ends() x ping_period_ms + ping_period_ms.
 *    (Full arc at 2 deg / 60 ms: 75 x 60 + 60 = 4560 ms, so the previous
 *    pass's turnaround reading, 4500 ms old, still counts: it is real data.)
 *  - Lock: at a FULL pass end the tracker reaches LOCKED -> SECTOR around
 *    the target; locked_at_ms = now; the servo steps into the sector (no
 *    jump) and the first sector pass ends at the far sector end.
 *  - Tracker limits = sweep_plan_pass_ends() of the plan in use: the snapped
 *    sector in SECTOR, the arc in FULL / RESWEEP.
 *  - LOCKED: on_ping after every reading, EXCEPT during a RESWEEP (Joe 27/11,
 *    resweep fix (c)): the resweep is judged only at its end by on_pass.
 *    Why: the target moves while the beam is away for ~5 s, so pings across
 *    its OLD left..right were counted as misses and ended the lock mid-pass.
 *    A loss in SECTOR -> FULL at once.
 *  - SECTOR pass end: on_pass; still LOCKED -> recentre on the target (new
 *    limits); and if resweep_ms > 0 and now - last_full_ms >= resweep_ms,
 *    start a RESWEEP. Lost -> FULL.
 *  - RESWEEP (resweep_turned, Joe 27/11): the servo starts at a sector end,
 *    so the first arc end it reaches is only a turnaround: no on_pass there
 *    (no on_ping either), resweep_turned = true. The next pass end closes a
 *    complete end-to-end pass and runs on_pass. A resweep that starts AT an
 *    arc end (sector clamped to the arc) is complete at its first pass end,
 *    so resweep_turned starts true. Holds for any resweep_ms. Then still
 *    LOCKED -> back to a sector on the target; lost -> FULL.
 *    last_full_ms = now.
 *  - FULL pass ends (searching) always run on_pass, even a partial first
 *    pass after a loss: it only sees fewer bins.
 *  - reset: tracker reset, FULL keeping the angle, last_full_ms and
 *    locked_at_ms = 0.
 */
#include "lock_loop.h"

#include <math.h>

static void use_limits(lock_loop_t *ll)
{
    float lo, hi;
    sweep_plan_pass_ends(&ll->plan, &lo, &hi);
    target_track_set_limits(&ll->track, lo, hi);
}

static bool at_arc_end(const lock_loop_t *ll)
{
    return ll->plan.angle_deg <= ll->plan.cfg.min_deg + 1e-3f ||
           ll->plan.angle_deg >= ll->plan.cfg.max_deg - 1e-3f;
}

static void go_full(lock_loop_t *ll, lock_plan_t kind)
{
    sweep_plan_full(&ll->plan);
    ll->kind = kind;
    ll->resweep_turned = (kind == LOCK_PLAN_RESWEEP) && at_arc_end(ll);
    use_limits(ll);
}

static void go_sector(lock_loop_t *ll)
{
    sweep_plan_sector(&ll->plan, ll->track.target.centre_deg, ll->cfg.sector_half_deg);
    ll->kind = LOCK_PLAN_SECTOR;
    use_limits(ll);
}

static uint32_t max_age_ms(const lock_loop_t *ll)
{
    float lo, hi;
    sweep_plan_pass_ends(&ll->plan, &lo, &hi);
    float steps = ceilf((hi - lo) / ll->plan.cfg.step_deg - 1e-4f);
    if (steps < 1.0f) {
        steps = 1.0f;
    }
    return (uint32_t)steps * ll->cfg.ping_period_ms + ll->cfg.ping_period_ms;
}

void lock_loop_init(lock_loop_t *ll, const lock_loop_cfg_t *cfg, float start_deg)
{
    ll->cfg = *cfg;
    if (!(ll->cfg.track.gate_deg > 0.0f)) {
        ll->cfg.track.gate_deg = ll->cfg.sector_half_deg;
    }
    sweep_plan_init(&ll->plan, &ll->cfg.sweep, start_deg);
    ll->cfg.sweep = ll->plan.cfg;                    /* as sanitised by sweep_plan */
    ll->cfg.track.arc_min_deg = ll->plan.cfg.min_deg;
    ll->cfg.track.arc_max_deg = ll->plan.cfg.max_deg;
    target_track_init(&ll->track, &ll->cfg.track);
    ll->kind = LOCK_PLAN_FULL;
    ll->last_full_ms = 0;
    ll->locked_at_ms = 0;
    ll->resweep_turned = false;
}

float lock_loop_next_angle(lock_loop_t *ll)
{
    return sweep_plan_next(&ll->plan, ll->plan.cfg.step_deg);
}

track_state_t lock_loop_on_reading(lock_loop_t *ll, const scan_map_t *map, uint32_t now_ms,
                                   float angle_deg, float dist_cm, reading_status_t status)
{
    if (ll->track.state == TRACK_LOCKED && ll->kind != LOCK_PLAN_RESWEEP &&
        target_track_on_ping(&ll->track, angle_deg, dist_cm, status) != TRACK_LOCKED) {
        go_full(ll, LOCK_PLAN_FULL);                 /* fast "lost" */
        return ll->track.state;
    }
    if (!sweep_plan_take_pass_done(&ll->plan)) {
        return ll->track.state;
    }

    if (ll->kind == LOCK_PLAN_RESWEEP && !ll->resweep_turned) {
        ll->resweep_turned = true;                   /* turnaround: only a leg */
        return ll->track.state;
    }
    const uint32_t max_age = max_age_ms(ll);

    const track_state_t st = target_track_on_pass(&ll->track, map, now_ms, max_age);
    switch (ll->kind) {
    case LOCK_PLAN_FULL:
        ll->last_full_ms = now_ms;
        if (st == TRACK_LOCKED) {
            ll->locked_at_ms = now_ms;
            go_sector(ll);
        }
        break;
    case LOCK_PLAN_SECTOR:
        if (st != TRACK_LOCKED) {
            go_full(ll, LOCK_PLAN_FULL);
        } else if (ll->cfg.resweep_ms > 0 && now_ms - ll->last_full_ms >= ll->cfg.resweep_ms) {
            go_full(ll, LOCK_PLAN_RESWEEP);
        } else {
            sweep_plan_recentre(&ll->plan, ll->track.target.centre_deg);
            use_limits(ll);
        }
        break;
    case LOCK_PLAN_RESWEEP:
        ll->last_full_ms = now_ms;
        if (st == TRACK_LOCKED) {
            go_sector(ll);
        } else {
            go_full(ll, LOCK_PLAN_FULL);
        }
        break;
    }
    return ll->track.state;
}

void lock_loop_reset(lock_loop_t *ll)
{
    target_track_reset(&ll->track);
    go_full(ll, LOCK_PLAN_FULL);
    ll->last_full_ms = 0;
    ll->locked_at_ms = 0;
}

const target_track_t *lock_loop_track(const lock_loop_t *ll)
{
    return &ll->track;
}

lock_plan_t lock_loop_plan(const lock_loop_t *ll)
{
    return ll->kind;
}
