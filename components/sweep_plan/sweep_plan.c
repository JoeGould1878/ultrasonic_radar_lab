/**
 * @file sweep_plan.c
 * @brief Sweep planner — implementation (S3, 27/11).
 *
 * Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
 * Credits / sources used: none (standard C only).
 *
 * Rules (the header leaves these open; chosen in S3, Joe approved the grid
 * and no-jump rules on 27/11):
 *  - FULL and SECTOR move on one fixed grid, min_deg + k * step_deg (15, 17,
 *    ... 165). Every step goes to the next grid point in the direction of
 *    travel, so after MANUAL (off-grid) the sweep rejoins the grid at once
 *    and readings land on the scan_map bin centres. The ends (min/max, or
 *    the sector ends) are always reachable even if not on the grid.
 *  - SECTOR ends: centre +/- half, clamped to min..max, then snapped INWARD
 *    to the grid. A sector narrower than one step becomes one step wide.
 *  - No jumps: switching plan keeps the angle. If the angle is outside a new
 *    sector, the plan steps toward it; the pass ends at the FAR end, so the
 *    first sector pass covers the whole sector.
 *  - next() first advances, then returns (the start angle itself is not
 *    returned by the first call).
 *  - sweep_done is set when a FULL/SECTOR step lands on the end it was
 *    heading for; the next step turns back. Switching plan kind clears a
 *    pending flag (it belonged to the old plan); recentre keeps it.
 *  - MANUAL: moves toward the (clamped) target by at most max_step_deg; a
 *    max_step <= 0 (or NaN) means no movement. Never sets sweep_done. dir
 *    follows the last movement, so FULL carries on the same way afterwards.
 *  - Bad config: min > max is swapped; step <= 0 (or NaN) becomes 1 deg.
 */
#include "sweep_plan.h"

#include <math.h>

#define EPS_DEG  1e-3f   /* "at the end" tolerance */
#define EPS_K    1e-4f   /* grid-index tolerance (fraction of a step) */

static float clampf(float x, float lo, float hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

/* Ends of the current FULL / SECTOR pass. */
static void pass_ends(const sweep_plan_t *p, float *lo, float *hi)
{
    const float a = p->cfg.min_deg, b = p->cfg.max_deg, s = p->cfg.step_deg;
    if (p->kind != SWEEP_SECTOR) {
        *lo = a;
        *hi = b;
        return;
    }
    const float c   = clampf(p->sector_centre, a, b);
    const float lo0 = clampf(c - p->sector_half, a, b);
    const float hi0 = clampf(c + p->sector_half, a, b);
    float l = (lo0 <= a + EPS_DEG) ? a : a + ceilf((lo0 - a) / s - EPS_K) * s;
    float h = (hi0 >= b - EPS_DEG) ? b : a + floorf((hi0 - a) / s + EPS_K) * s;
    if (h - l < s - EPS_DEG) {           /* narrower than one step */
        l = a + floorf((c - a) / s + EPS_K) * s;
        h = l + s;
        if (h > b) {
            h = b;
            l = (b - s > a) ? b - s : a;
        }
    }
    *lo = l;
    *hi = h;
}

void sweep_plan_init(sweep_plan_t *p, const sweep_cfg_t *cfg, float start_deg)
{
    p->cfg = *cfg;
    if (p->cfg.min_deg > p->cfg.max_deg) {
        float t = p->cfg.min_deg;
        p->cfg.min_deg = p->cfg.max_deg;
        p->cfg.max_deg = t;
    }
    if (!(p->cfg.step_deg > 0.0f)) {
        p->cfg.step_deg = 1.0f;
    }
    p->kind = SWEEP_FULL;
    p->angle_deg = (start_deg == start_deg) ? clampf(start_deg, p->cfg.min_deg, p->cfg.max_deg)
                                            : p->cfg.min_deg;
    p->dir = (p->angle_deg >= p->cfg.max_deg - EPS_DEG) ? -1 : +1;
    p->sector_centre = p->angle_deg;
    p->sector_half   = 0.0f;
    p->manual_target = p->angle_deg;
    p->sweep_done    = false;
}

void sweep_plan_full(sweep_plan_t *p)
{
    p->kind = SWEEP_FULL;
    p->sweep_done = false;
}

void sweep_plan_sector(sweep_plan_t *p, float centre_deg, float half_width_deg)
{
    p->kind = SWEEP_SECTOR;
    p->sector_centre = centre_deg;
    p->sector_half   = fabsf(half_width_deg);
    p->sweep_done = false;
}

void sweep_plan_manual(sweep_plan_t *p, float target_deg)
{
    p->kind = SWEEP_MANUAL;
    p->manual_target = clampf(target_deg, p->cfg.min_deg, p->cfg.max_deg);
    p->sweep_done = false;
}

void sweep_plan_recentre(sweep_plan_t *p, float centre_deg)
{
    p->sector_centre = centre_deg;
}

static float next_manual(sweep_plan_t *p, float max_step_deg)
{
    float ms = (max_step_deg > 0.0f) ? max_step_deg : 0.0f;
    float move = clampf(p->manual_target - p->angle_deg, -ms, ms);
    if (move > 0.0f) {
        p->dir = +1;
    } else if (move < 0.0f) {
        p->dir = -1;
    }
    p->angle_deg = clampf(p->angle_deg + move, p->cfg.min_deg, p->cfg.max_deg);
    return p->angle_deg;
}

float sweep_plan_next(sweep_plan_t *p, float max_step_deg)
{
    if (p->kind == SWEEP_MANUAL) {
        return next_manual(p, max_step_deg);
    }
    const float a = p->cfg.min_deg, s = p->cfg.step_deg;
    float lo, hi;
    pass_ends(p, &lo, &hi);

    /* Head for the plan: outside it, turn toward it; at an end, turn back. */
    if (p->angle_deg >= hi - EPS_DEG && p->dir > 0) {
        p->dir = -1;
    } else if (p->angle_deg <= lo + EPS_DEG && p->dir < 0) {
        p->dir = +1;
    }

    const float g = (p->angle_deg - a) / s;
    float next;
    if (p->dir > 0) {
        next = a + (floorf(g + EPS_K) + 1.0f) * s;
        if (next >= hi - EPS_DEG) {
            next = hi;
            p->sweep_done = true;
        }
    } else {
        next = a + (ceilf(g - EPS_K) - 1.0f) * s;
        if (next <= lo + EPS_DEG) {
            next = lo;
            p->sweep_done = true;
        }
    }
    p->angle_deg = next;
    return next;
}

bool sweep_plan_take_pass_done(sweep_plan_t *p)
{
    bool d = p->sweep_done;
    p->sweep_done = false;
    return d;
}
