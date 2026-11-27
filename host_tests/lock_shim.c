/**
 * @file lock_shim.c
 * @brief Flat C interface to lock_loop for sim/lock_sim.py (ctypes). S3.
 *        Written by Claude (Anthropic) for Joe Gould.
 *
 * Why a shim (Joe approved, 27/11): ctypes would otherwise have to copy the
 * layout of lock_loop_t / track_cfg_t / ... into Python, which breaks
 * silently when a struct changes. Here Python only sees floats and ints.
 *
 * The shim runs the REAL components (scan_map, sweep_plan, target_track,
 * lock_loop), exactly as scan_task will in I9: next angle -> (Python pings
 * the simulated scene) -> scan_map_update -> lock_loop_on_reading. It adds
 * only diagnostics: why a lock was lost, and whether a pass ended.
 *
 * Built by `make -C host_tests shim` into host_tests/build/liblock_shim.so.
 */
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#include "lock_loop.h"

/* Parameter order of ls_new(p, n). Keep in step with PARAMS in lock_sim.py. */
enum {
    P_MIN_DEG, P_MAX_DEG, P_STEP_DEG,
    P_DIST_TOL, P_MIN_BINS, P_CONFIRM, P_LOST_PINGS, P_MAX_RANGE, P_BRIDGE, P_GATE,
    P_SECTOR_HALF, P_RESWEEP_MS, P_PERIOD_MS, P_START_DEG, P_BIN_DEG,
    P_COUNT
};

/* Why a lock ended (ls_step's cause). */
enum { CAUSE_NONE = 0, CAUSE_PING_MISSES = 1, CAUSE_GATE_FAIL = 2, CAUSE_NO_CLUSTER = 3 };

/* EXPERIMENT switches (ls_new_x). None of this is firmware: it exists so
 * S3 can put numbers on candidate fixes before Joe chooses one. */
/* (a) widened gate, (b) nearest bearing and (c) no on_ping in a resweep were
 * switches here until 27/11: Joe chose (b)+(c), now in target_track.c /
 * lock_loop.c (749592d), and rejected (a), so they were removed. Their
 * results are in 91190ea's s3_summary.txt. */
typedef struct {
    int   edge_recentre;    /* F1 recentre on the clipped edge when the target is edge-flagged */
    float lead_max_dps;     /* F2 > 0: recentre ahead by measured speed x sector pass time, |speed| capped */
    int   jump_in;          /* (e) outside a new / moved sector: jump to its nearer end instead of
                               stepping 2 deg per ping (servo travel time not modelled) */
    float defer_dps;        /* SC8 fix 3b: > 0 = a due resweep waits while the target's measured
                               angular speed is above this (deg/s) */
} xflags_t;

typedef struct {
    lock_loop_t     ll;
    scan_map_t      map;
    int             use_x;          /* run the EXPERIMENT controller below */
    xflags_t        x;
    float           prev_centre;    /* x: lead estimate */
    uint32_t        prev_t;
    int             have_prev;
    float           v_centre[3];    /* x defer: last sector pass-end centres ... */
    uint32_t        v_t[3];         /*          ... and times (oldest first) */
    int             v_n;
    int             deferred;       /* x defer: resweeps postponed (pass ends) */
    int             cause;          /* last ls_step */
    track_cluster_t cause_cluster;  /* GATE_FAIL: the nearest cluster that was outside the gate */
    int             pass_end;       /* last ls_step ran on_pass */
    lock_plan_t     pass_kind;      /* plan of that pass */
} shim_t;

shim_t *ls_new(const double *p, int n)
{
    if (n != P_COUNT) return NULL;
    shim_t *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    lock_loop_cfg_t c = {
        .sweep = {.min_deg = (float)p[P_MIN_DEG], .max_deg = (float)p[P_MAX_DEG],
                  .step_deg = (float)p[P_STEP_DEG]},
        .track = {.dist_tol_cm = (float)p[P_DIST_TOL], .min_bins = (int)p[P_MIN_BINS],
                  .confirm_sweeps = (int)p[P_CONFIRM], .lost_pings = (int)p[P_LOST_PINGS],
                  .max_range_cm = (float)p[P_MAX_RANGE], .bridge_gap_bins = (int)p[P_BRIDGE],
                  .gate_deg = (float)p[P_GATE]},
        .sector_half_deg = (float)p[P_SECTOR_HALF],
        .resweep_ms = (uint32_t)p[P_RESWEEP_MS],
        .ping_period_ms = (uint32_t)p[P_PERIOD_MS],
    };
    lock_loop_init(&s->ll, &c, (float)p[P_START_DEG]);
    scan_map_init(&s->map, (float)p[P_BIN_DEG]);
    return s;
}

void ls_free(shim_t *s) { free(s); }

float ls_next(shim_t *s) { return lock_loop_next_angle(&s->ll); }

/* Mirrors lock_loop.c's static max_age_ms() (one pass of the plan + one
 * ping). Used only to classify an on_pass loss after the fact. */
static uint32_t max_age_of(const lock_loop_t *ll)
{
    float lo, hi;
    sweep_plan_pass_ends(&ll->plan, &lo, &hi);
    float steps = ceilf((hi - lo) / ll->plan.cfg.step_deg - 1e-4f);
    if (steps < 1.0f) steps = 1.0f;
    return (uint32_t)steps * ll->cfg.ping_period_ms + ll->cfg.ping_period_ms;
}

/* ------------------------------------------------------------------------
 * EXPERIMENT controller: a copy of lock_loop_on_reading() (749592d) with the
 * candidate fixes behind switches. With every switch off it must behave
 * exactly like the real one (lock_sim checks this run for run). Not used by
 * the firmware; if Joe picks a fix, it goes into lock_loop.c properly.
 * ---------------------------------------------------------------------- */
static void x_limits(lock_loop_t *ll)
{
    float lo, hi;
    sweep_plan_pass_ends(&ll->plan, &lo, &hi);
    target_track_set_limits(&ll->track, lo, hi);
}

static void x_full(shim_t *s, lock_plan_t kind)
{
    lock_loop_t *ll = &s->ll;
    sweep_plan_full(&ll->plan);
    ll->kind = kind;
    ll->resweep_turned = (kind == LOCK_PLAN_RESWEEP) &&
        (ll->plan.angle_deg <= ll->plan.cfg.min_deg + 1e-3f ||
         ll->plan.angle_deg >= ll->plan.cfg.max_deg - 1e-3f);
    s->have_prev = 0;
    s->v_n = 0;
    x_limits(ll);
}

/* Measured angular speed (deg/s) over the last up-to-3 sector pass ends:
 * a pass-to-pass difference alone jitters by ~1-2 deg/s on a still target. */
static float x_speed(shim_t *s, uint32_t now, float centre)
{
    if (s->v_n == 3) {
        s->v_centre[0] = s->v_centre[1]; s->v_t[0] = s->v_t[1];
        s->v_centre[1] = s->v_centre[2]; s->v_t[1] = s->v_t[2];
        s->v_n = 2;
    }
    s->v_centre[s->v_n] = centre;
    s->v_t[s->v_n] = now;
    s->v_n++;
    if (s->v_n < 2 || s->v_t[s->v_n - 1] == s->v_t[0]) return 0.0f;
    return 1000.0f * (s->v_centre[s->v_n - 1] - s->v_centre[0]) / (float)(s->v_t[s->v_n - 1] - s->v_t[0]);
}

/* Where to put the sector centre after a locked pass (F1 / F2). */
static float x_centre(shim_t *s, uint32_t now)
{
    const target_track_t *t = &s->ll.track;
    float c = t->target.centre_deg;
    const float half_bin = 0.5f * s->map.bin_deg;
    if (s->x.edge_recentre && t->target.edge) {
        if (t->target.right_deg >= t->lim_hi_deg - half_bin) c = t->target.right_deg;
        else if (t->target.left_deg <= t->lim_lo_deg + half_bin) c = t->target.left_deg;
    }
    if (s->x.lead_max_dps > 0.0f) {
        if (s->have_prev && now > s->prev_t) {
            float v = (t->target.centre_deg - s->prev_centre) / (float)(now - s->prev_t); /* deg/ms */
            float vmax = s->x.lead_max_dps / 1000.0f;
            v = v > vmax ? vmax : (v < -vmax ? -vmax : v);
            float lo, hi;
            sweep_plan_pass_ends(&s->ll.plan, &lo, &hi);
            float pass_ms = (hi - lo) / s->ll.plan.cfg.step_deg * (float)s->ll.cfg.ping_period_ms;
            c += v * pass_ms;
        }
        s->prev_centre = t->target.centre_deg;
        s->prev_t = now;
        s->have_prev = 1;
    }
    return c;
}

static void x_sector(shim_t *s, float centre, int fresh)
{
    lock_loop_t *ll = &s->ll;
    if (fresh) {
        sweep_plan_sector(&ll->plan, centre, ll->cfg.sector_half_deg);
        ll->kind = LOCK_PLAN_SECTOR;
    } else {
        sweep_plan_recentre(&ll->plan, centre);
    }
    x_limits(ll);
    if (s->x.jump_in) {
        float lo, hi;
        sweep_plan_pass_ends(&ll->plan, &lo, &hi);
        if (ll->plan.angle_deg > hi) ll->plan.angle_deg = hi;
        else if (ll->plan.angle_deg < lo) ll->plan.angle_deg = lo;
    }
}

static track_state_t x_on_reading(shim_t *s, uint32_t now, float angle, float dist,
                                  reading_status_t status)
{
    lock_loop_t *ll = &s->ll;
    target_track_t *t = &ll->track;
    const bool in_resweep = (ll->kind == LOCK_PLAN_RESWEEP);
    if (t->state == TRACK_LOCKED && !in_resweep &&
        target_track_on_ping(t, angle, dist, status) != TRACK_LOCKED) {
        x_full(s, LOCK_PLAN_FULL);
        return t->state;
    }
    if (!sweep_plan_take_pass_done(&ll->plan)) return t->state;
    if (in_resweep && !ll->resweep_turned) {
        ll->resweep_turned = true;
        return t->state;
    }
    const uint32_t max_age = max_age_of(ll);
    const track_state_t st = target_track_on_pass(t, &s->map, now, max_age);
    switch (ll->kind) {
    case LOCK_PLAN_FULL:
        ll->last_full_ms = now;
        if (st == TRACK_LOCKED) {
            ll->locked_at_ms = now;
            s->have_prev = 0;
            s->v_n = 0;
            x_sector(s, t->target.centre_deg, 1);
        }
        break;
    case LOCK_PLAN_SECTOR:
        if (st != TRACK_LOCKED) {
            x_full(s, LOCK_PLAN_FULL);
            break;
        }
        const float v = x_speed(s, now, t->target.centre_deg);
        const bool due = ll->cfg.resweep_ms > 0 && now - ll->last_full_ms >= ll->cfg.resweep_ms;
        const bool defer = due && s->x.defer_dps > 0.0f && fabsf(v) > s->x.defer_dps;
        s->deferred += defer;
        if (due && !defer) {
            x_full(s, LOCK_PLAN_RESWEEP);
        } else {
            x_sector(s, x_centre(s, now), 0);
        }
        break;
    case LOCK_PLAN_RESWEEP:
        ll->last_full_ms = now;
        if (st == TRACK_LOCKED) {
            s->have_prev = 0;
            s->v_n = 0;
            x_sector(s, t->target.centre_deg, 1);
        } else {
            x_full(s, LOCK_PLAN_FULL);
        }
        break;
    }
    return t->state;
}

/* Same as ls_new, plus the EXPERIMENT switches:
 * x[0] edge_recentre, x[1] lead_max_dps, x[2] jump_in, x[3] defer_dps. */
shim_t *ls_new_x(const double *p, int n, const double *x)
{
    shim_t *s = ls_new(p, n);
    if (!s) return NULL;
    s->use_x = 1;
    s->x = (xflags_t){(int)x[0], (float)x[1], (int)x[2], (float)x[3]};
    return s;
}

/* status: 1 OK, 2 NO_ECHO, 3 FAILED (reading_status_t). Returns the state. */
int ls_step(shim_t *s, uint32_t now, float angle, float dist, int status)
{
    const lock_loop_t before = s->ll;
    const bool flag = before.plan.sweep_done;
    scan_map_update(&s->map, angle, dist, (reading_status_t)status, now);
    track_state_t st = s->use_x
        ? x_on_reading(s, now, angle, dist, (reading_status_t)status)
        : lock_loop_on_reading(&s->ll, &s->map, now, angle, dist, (reading_status_t)status);
    s->cause = CAUSE_NONE;
    s->pass_end = 0;
    if (flag && !(before.kind == LOCK_PLAN_RESWEEP && !before.resweep_turned)) {
        s->pass_end = 1;
        s->pass_kind = before.kind;
    }
    if (before.track.state == TRACK_LOCKED && st != TRACK_LOCKED) {
        target_track_t t = before.track;
        const bool ping_ran = before.kind != LOCK_PLAN_RESWEEP;      /* (c) */
        if (ping_ran &&
            target_track_on_ping(&t, angle, dist, (reading_status_t)status) != TRACK_LOCKED) {
            s->cause = CAUSE_PING_MISSES;
        } else {
            track_cluster_t c = target_track_find_cluster(&t, &s->map, now, max_age_of(&before));
            s->cause = c.valid ? CAUSE_GATE_FAIL : CAUSE_NO_CLUSTER;
            s->cause_cluster = c;
        }
    }
    return (int)st;
}

/* out[19]: state, plan, valid, centre, left, right, dist, edge, n_bins,
 *          miss_count, seen_count, angle, cause, pass_end, pass_kind,
 *          gate-fail cluster centre (or -1), current pass ends lo, hi
 *          (angle outside them in SECTOR = walking into the sector),
 *          resweeps deferred so far (EXPERIMENT defer_dps) */
void ls_info(const shim_t *s, double *out)
{
    const target_track_t *t = lock_loop_track(&s->ll);
    out[0]  = t->state;
    out[1]  = lock_loop_plan(&s->ll);
    out[2]  = t->target.valid;
    out[3]  = t->target.centre_deg;
    out[4]  = t->target.left_deg;
    out[5]  = t->target.right_deg;
    out[6]  = t->target.dist_cm;
    out[7]  = t->target.edge;
    out[8]  = t->target.n_bins;
    out[9]  = t->miss_count;
    out[10] = t->seen_count;
    out[11] = s->ll.plan.angle_deg;
    out[12] = s->cause;
    out[13] = s->pass_end;
    out[14] = s->pass_kind;
    out[15] = (s->cause == CAUSE_GATE_FAIL) ? s->cause_cluster.centre_deg : -1.0;
    float lo, hi;
    sweep_plan_pass_ends(&s->ll.plan, &lo, &hi);
    out[16] = lo;
    out[17] = hi;
    out[18] = s->deferred;
}

/* Nearest cluster in the map right now (for scoring a SWEEP-only run). */
int ls_find(const shim_t *s, uint32_t now, uint32_t max_age, double *out)
{
    track_cluster_t c = target_track_find_cluster(&s->ll.track, &s->map, now, max_age);
    out[0] = c.centre_deg; out[1] = c.left_deg; out[2] = c.right_deg;
    out[3] = c.dist_cm; out[4] = c.n_bins; out[5] = c.edge;
    return c.valid;
}
