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
typedef struct {
    int   no_ping_resweep;  /* (c) no on_ping while a resweep runs */
    float widen_dps;        /* (a) resweep gate += widen_dps * time since the last sector pass end */
    int   nearest_bearing;  /* (b) resweep judges the cluster nearest the last bearing, no gate */
    int   edge_recentre;    /* F1 recentre on the clipped edge when the target is edge-flagged */
    float lead_max_dps;     /* F2 > 0: recentre ahead by measured speed x sector pass time, |speed| capped */
    int   jump_in;          /* (e) outside a new / moved sector: jump to its nearer end instead of
                               stepping 2 deg per ping (servo travel time not modelled) */
} xflags_t;

typedef struct {
    lock_loop_t     ll;
    scan_map_t      map;
    int             use_x;          /* run the EXPERIMENT controller below */
    xflags_t        x;
    uint32_t        t_sector_end;   /* x: last sector pass end */
    float           prev_centre;    /* x: lead estimate */
    uint32_t        prev_t;
    int             have_prev;
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
 * EXPERIMENT controller: a copy of lock_loop_on_reading() (bb27c04) with the
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
    x_limits(ll);
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

/* (b): the cluster whose centre is nearest `bearing`. Clusters are listed
 * with the REAL find_cluster by masking each found cluster's bins and asking
 * again; exact for bridge 0 (masked bins are gaps either way). */
static track_cluster_t x_nearest_bearing(shim_t *s, uint32_t now, uint32_t max_age, float bearing)
{
    static scan_map_t m;
    m = s->map;
    track_cluster_t best = {0};
    for (int k = 0; k < 32; k++) {
        track_cluster_t c = target_track_find_cluster(&s->ll.track, &m, now, max_age);
        if (!c.valid) break;
        if (!best.valid || fabsf(c.centre_deg - bearing) < fabsf(best.centre_deg - bearing)) best = c;
        for (int i = 0; i < m.n_bins; i++) {
            float a = m.bins[i].angle_deg;
            if (m.bins[i].status == READING_OK && a >= c.left_deg - 1e-3f && a <= c.right_deg + 1e-3f)
                m.bins[i].status = READING_NO_ECHO;
        }
    }
    return best;
}

static track_state_t x_on_reading(shim_t *s, uint32_t now, float angle, float dist,
                                  reading_status_t status)
{
    lock_loop_t *ll = &s->ll;
    target_track_t *t = &ll->track;
    const bool in_resweep = (ll->kind == LOCK_PLAN_RESWEEP);
    if (t->state == TRACK_LOCKED && !(s->x.no_ping_resweep && in_resweep) &&
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
    track_state_t st;
    if (in_resweep && s->x.nearest_bearing && t->state == TRACK_LOCKED) {
        track_cluster_t c = x_nearest_bearing(s, now, max_age, t->target.centre_deg);
        if (c.valid) {
            t->target = c;
            t->miss_count = 0;
        } else {
            t->state = TRACK_SEARCHING;
            t->target.valid = false;
            t->seen_count = t->miss_count = 0;
        }
        st = t->state;
    } else {
        const float gate0 = t->cfg.gate_deg;
        if (in_resweep && s->x.widen_dps > 0.0f)
            t->cfg.gate_deg = gate0 + s->x.widen_dps * (float)(now - s->t_sector_end) / 1000.0f;
        st = target_track_on_pass(t, &s->map, now, max_age);
        t->cfg.gate_deg = gate0;
    }
    switch (ll->kind) {
    case LOCK_PLAN_FULL:
        ll->last_full_ms = now;
        if (st == TRACK_LOCKED) {
            ll->locked_at_ms = now;
            s->have_prev = 0;
            x_sector(s, t->target.centre_deg, 1);
        }
        break;
    case LOCK_PLAN_SECTOR:
        s->t_sector_end = now;
        if (st != TRACK_LOCKED) {
            x_full(s, LOCK_PLAN_FULL);
        } else if (ll->cfg.resweep_ms > 0 && now - ll->last_full_ms >= ll->cfg.resweep_ms) {
            x_full(s, LOCK_PLAN_RESWEEP);
        } else {
            x_sector(s, x_centre(s, now), 0);
        }
        break;
    case LOCK_PLAN_RESWEEP:
        ll->last_full_ms = now;
        if (st == TRACK_LOCKED) {
            s->have_prev = 0;
            x_sector(s, t->target.centre_deg, 1);
        } else {
            x_full(s, LOCK_PLAN_FULL);
        }
        break;
    }
    return t->state;
}

/* Same as ls_new, plus the EXPERIMENT switches:
 * x[0] no_ping_resweep, x[1] widen_dps, x[2] nearest_bearing,
 * x[3] edge_recentre, x[4] lead_max_dps, x[5] jump_in. */
shim_t *ls_new_x(const double *p, int n, const double *x)
{
    shim_t *s = ls_new(p, n);
    if (!s) return NULL;
    s->use_x = 1;
    s->x = (xflags_t){(int)x[0], (float)x[1], (int)x[2], (int)x[3], (float)x[4], (int)x[5]};
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
        const bool ping_ran = !(s->use_x && s->x.no_ping_resweep && before.kind == LOCK_PLAN_RESWEEP);
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

/* out[16]: state, plan, valid, centre, left, right, dist, edge, n_bins,
 *          miss_count, seen_count, angle, cause, pass_end, pass_kind,
 *          gate-fail cluster centre (or -1) */
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
}

/* Nearest cluster in the map right now (for scoring a SWEEP-only run). */
int ls_find(const shim_t *s, uint32_t now, uint32_t max_age, double *out)
{
    track_cluster_t c = target_track_find_cluster(&s->ll.track, &s->map, now, max_age);
    out[0] = c.centre_deg; out[1] = c.left_deg; out[2] = c.right_deg;
    out[3] = c.dist_cm; out[4] = c.n_bins; out[5] = c.edge;
    return c.valid;
}
