/**
 * @file test_lock_loop.c
 * @brief Host tests for lock_loop (S3). Written by Claude (Anthropic) for Joe Gould.
 *
 * Runs the controller closed-loop against a tiny ideal world (objects seen
 * within +/-7 deg of the beam, no noise), 60 ms per ping, the real sweep
 * config (15..165, 2 deg). Checks: lock after two full passes, the sector
 * and tracker limits, walk-in without jumps, recentring, resweep (whole arc,
 * turnaround leg skipped, started at an arc end, resweep_ms shorter than a
 * pass, a closer object elsewhere does not end the lock, no on_ping loss
 * during a resweep), fast loss on removal, arc-end clipping, reset.
 * The noisy, scene-based measurements are in sim/lock_sim.py.
 */
#include <math.h>
#include <stdint.h>
#include "lock_loop.h"
#include "test_util.h"

#define PERIOD 60u

typedef struct { float bearing, dist, rate_dps; bool present; } obj_t;

typedef struct {
    lock_loop_t ll;
    scan_map_t  map;
    obj_t       obj[3];
    uint32_t    now;
    float       last_angle;
    int         big_steps;      /* steps > 2 deg: must stay 0 */
    int         out_of_arc;
    float       min_seen, max_seen;
} world_t;

static world_t w;

static lock_loop_cfg_t cfg(void)
{
    lock_loop_cfg_t c = {
        .sweep = {.min_deg = 15.0f, .max_deg = 165.0f, .step_deg = 2.0f},
        .track = {.dist_tol_cm = 8.0f, .min_bins = 2, .confirm_sweeps = 2, .lost_pings = 6,
                  .max_range_cm = 150.0f, .arc_min_deg = 0.0f, .arc_max_deg = 180.0f,
                  .bridge_gap_bins = 0, .gate_deg = 0.0f},
        .sector_half_deg = 15.0f,
        .resweep_ms = 0,
        .ping_period_ms = PERIOD,
    };
    return c;
}

static void start(const lock_loop_cfg_t *c, float start_deg)
{
    w = (world_t){0};
    lock_loop_init(&w.ll, c, start_deg);
    scan_map_init(&w.map, 2.0f);
    w.last_angle = start_deg;
    w.min_seen = 999;
    w.max_seen = -999;
}

/* One ping: nearest present object within 7 deg of the beam, else NO_ECHO. */
static track_state_t ping(void)
{
    float a = lock_loop_next_angle(&w.ll);
    if (fabsf(a - w.last_angle) > 2.0f + 1e-3f) w.big_steps++;
    if (a < 15.0f - 1e-3f || a > 165.0f + 1e-3f) w.out_of_arc++;
    w.last_angle = a;
    w.min_seen = fminf(w.min_seen, a);
    w.max_seen = fmaxf(w.max_seen, a);
    w.now += PERIOD;
    float best = 1e9f;
    for (int i = 0; i < 3; i++) {
        obj_t *o = &w.obj[i];
        float b = o->bearing + o->rate_dps * (float)w.now / 1000.0f;
        if (o->present && fabsf(a - b) <= 7.0f && o->dist < best) best = o->dist;
    }
    reading_status_t st = best < 1e9f ? READING_OK : READING_NO_ECHO;
    float d = best < 1e9f ? best : 0.0f;
    scan_map_update(&w.map, a, d, st, w.now);
    return lock_loop_on_reading(&w.ll, &w.map, w.now, a, d, st);
}

static int run_until_locked(int max_pings)
{
    for (int k = 1; k <= max_pings; k++) {
        if (ping() == TRACK_LOCKED) return k;
    }
    return -1;
}

static void test_init(void)
{
    printf("init: gate 0 -> sector half, tracker arc = sweep arc\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    CHECK_NEAR(w.ll.cfg.track.gate_deg, 15.0, 0);
    CHECK_NEAR(w.ll.track.cfg.arc_min_deg, 15.0, 0);
    CHECK_NEAR(w.ll.track.cfg.arc_max_deg, 165.0, 0);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_FULL);
    CHECK(lock_loop_track(&w.ll)->state == TRACK_SEARCHING);
    c.track.gate_deg = 9.0f;                              /* a set gate is kept */
    start(&c, 15.0f);
    CHECK_NEAR(w.ll.cfg.track.gate_deg, 9.0, 0);
}

static void test_lock_and_sector(void)
{
    printf("static target: lock, sector, walk-in, stays locked\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};

    /* Pass 1 ends at ping 75 (165): candidate. Pass 2 ends at ping 150 (15): lock. */
    for (int k = 0; k < 75; k++) ping();
    CHECK(lock_loop_track(&w.ll)->state == TRACK_CANDIDATE);
    CHECK(w.ll.last_full_ms == 75 * PERIOD);
    int k = run_until_locked(200);
    CHECK(k == 75);
    CHECK(w.ll.locked_at_ms == 150 * PERIOD);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_SECTOR);
    const target_track_t *t = lock_loop_track(&w.ll);
    CHECK_NEAR(t->target.centre_deg, 90.0, 1.0);
    CHECK(!t->target.edge);
    CHECK_NEAR(t->lim_lo_deg, 75.0, 1e-3);                /* tracker uses the snapped sector */
    CHECK_NEAR(t->lim_hi_deg, 105.0, 1e-3);

    /* From 15 the servo walks up into the sector; first sector pass ends at 105. */
    int n = 0;
    do { ping(); n++; } while (!(fabsf(w.last_angle - 105.0f) < 1e-3f) && n < 200);
    CHECK(n == 45);                                       /* 17 ... 105 */
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);

    w.min_seen = 999; w.max_seen = -999;
    for (int i = 0; i < 300; i++) ping();                 /* 20 sector passes */
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_SECTOR);
    CHECK_NEAR(w.min_seen, 75.0, 1e-3);
    CHECK_NEAR(w.max_seen, 105.0, 1e-3);
    CHECK(w.big_steps == 0);
    CHECK(w.out_of_arc == 0);
}

static void test_removed(void)
{
    printf("target removed: lost by on_ping within one sector pass\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    for (int i = 0; i < 100; i++) ping();
    w.obj[0].present = false;
    uint32_t gone = w.now;
    int n = 0;
    while (lock_loop_track(&w.ll)->state == TRACK_LOCKED && n < 100) { ping(); n++; }
    CHECK(lock_loop_track(&w.ll)->state == TRACK_SEARCHING);
    CHECK(n <= 15 + 6);                                   /* <= a sector pass + lost_pings */
    CHECK(w.now - gone <= 21 * PERIOD);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_FULL);
    CHECK_NEAR(lock_loop_track(&w.ll)->lim_lo_deg, 15.0, 0);   /* back to the arc */
    CHECK_NEAR(lock_loop_track(&w.ll)->lim_hi_deg, 165.0, 0);
    CHECK(w.big_steps == 0);
}

static void test_follow(void)
{
    printf("slow mover: sector recentres and follows\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 60.0f, .dist = 50.0f, .rate_dps = 2.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    int lost = 0;
    for (int i = 0; i < 300; i++) {                       /* 18 s, target moves 36 deg */
        if (ping() != TRACK_LOCKED) lost++;
    }
    CHECK(lost == 0);
    float truth = 60.0f + 2.0f * (float)w.now / 1000.0f;
    CHECK_NEAR(lock_loop_track(&w.ll)->target.centre_deg, truth, 3.0);
    CHECK_NEAR(w.ll.plan.sector_centre, lock_loop_track(&w.ll)->target.centre_deg, 1e-3);
    CHECK(w.big_steps == 0);
}

static void test_resweep(void)
{
    printf("resweep: whole arc, partial leg skipped, back to the sector\n");
    lock_loop_cfg_t c = cfg();
    c.resweep_ms = 10000;
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    uint32_t full_end = w.ll.last_full_ms;

    int n = 0;
    while (lock_loop_plan(&w.ll) != LOCK_PLAN_RESWEEP && n < 1000) { ping(); n++; }
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP);
    CHECK(w.now - full_end >= 10000);
    CHECK(w.now - full_end < 10000 + 16 * PERIOD);        /* at the first sector end after 10 s */

    /* The first arc end reached is only the leg from the sector: still RESWEEP. */
    w.min_seen = 999; w.max_seen = -999;
    n = 0;
    while (!(w.last_angle <= 15.001f || w.last_angle >= 164.999f) && n < 200) { ping(); n++; }
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP);
    n = 0;
    while (lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP && n < 300) { ping(); n++; }
    CHECK(n == 75);                                       /* then one complete pass */
    CHECK_NEAR(w.min_seen, 15.0, 1e-3);
    CHECK_NEAR(w.max_seen, 165.0, 1e-3);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_SECTOR);
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);
    CHECK(w.ll.last_full_ms == w.now);
    CHECK(w.big_steps == 0);

    /* A closer object elsewhere (140 deg, 30 cm) is seen by the resweep but
     * is outside the gate: the lock stays on the same object (fix (b), Joe
     * 27/11; before it, the nearest cluster across the arc ended the lock). */
    w.obj[1] = (obj_t){.bearing = 140.0f, .dist = 30.0f, .present = true};
    n = 0;
    while (lock_loop_plan(&w.ll) != LOCK_PLAN_RESWEEP && n < 1000) { ping(); n++; }
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);  /* sector never saw it */
    n = 0;
    while (lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP && n < 400) { ping(); n++; }
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_SECTOR);
    CHECK_NEAR(lock_loop_track(&w.ll)->target.centre_deg, 90.0, 1.0);
    CHECK_NEAR(lock_loop_track(&w.ll)->target.dist_cm, 50.0, 1e-3);
}

static void test_resweep_no_ping_loss(void)
{
    printf("resweep: no on_ping loss, judged at its end\n");
    lock_loop_cfg_t c = cfg();
    c.resweep_ms = 10000;
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    int n = 0;
    while (lock_loop_plan(&w.ll) != LOCK_PLAN_RESWEEP && n < 1000) { ping(); n++; }
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP);
    const float left = lock_loop_track(&w.ll)->target.left_deg;
    const float right = lock_loop_track(&w.ll)->target.right_deg;
    CHECK_NEAR(left, 83.0, 1e-3);                         /* seen from 83 to 97 */
    CHECK_NEAR(right, 97.0, 1e-3);

    /* The target moves 12 deg (inside the 15 deg gate) while the beam is
     * away: the full pass now gets 6 NO_ECHO in a row across the OLD
     * 83..97 (83 ... 93) = lost_pings. on_ping would have ended the lock
     * there; it must not run in a resweep. */
    w.obj[0].bearing = 102.0f;
    int misses = 0, run = 0, locked_all = 1;
    n = 0;
    while (lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP && n < 400) {
        track_state_t st = ping();
        n++;
        if (w.last_angle >= left - 1e-3f && w.last_angle <= right + 1e-3f) {
            bool seen = fabsf(w.last_angle - 102.0f) <= 7.0f;
            run = seen ? 0 : run + 1;
            if (run > misses) misses = run;
        }
        if (lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP && st != TRACK_LOCKED) locked_all = 0;
    }
    CHECK(misses >= c.track.lost_pings);                  /* the case really happens */
    CHECK(locked_all);                                    /* LOCKED for the whole resweep */
    CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED); /* kept at its end */
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_SECTOR);
    CHECK_NEAR(lock_loop_track(&w.ll)->target.centre_deg, 102.0, 1.0);

    /* on_ping still ends a lock in the SECTOR: remove the target. The servo
     * first walks back from the arc end; the loss must come lost_pings pings
     * after the beam enters the target's left..right (on_ping), not later at
     * a sector pass end (on_pass). */
    w.obj[0].present = false;
    const float l2 = lock_loop_track(&w.ll)->target.left_deg;
    const float r2 = lock_loop_track(&w.ll)->target.right_deg;
    int inside = 0;
    n = 0;
    while (lock_loop_track(&w.ll)->state == TRACK_LOCKED && n < 100) {
        ping();
        n++;
        if (w.last_angle >= l2 - 1e-3f && w.last_angle <= r2 + 1e-3f) inside++;
    }
    CHECK(lock_loop_track(&w.ll)->state == TRACK_SEARCHING);
    CHECK(inside == c.track.lost_pings);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_FULL);
}

/* Run one resweep from its start to its end; returns pings taken, -1 if none. */
static int one_resweep(float *start_angle)
{
    int n = 0;
    while (lock_loop_plan(&w.ll) != LOCK_PLAN_RESWEEP && n < 2000) { ping(); n++; }
    if (lock_loop_plan(&w.ll) != LOCK_PLAN_RESWEEP) return -1;
    *start_angle = w.last_angle;
    /* The start angle was pinged by the sector pass that just ended (it is
     * in the map, fresh), so it counts as covered by this resweep. */
    w.min_seen = w.max_seen = w.last_angle;
    n = 0;
    while (lock_loop_plan(&w.ll) == LOCK_PLAN_RESWEEP && n < 400) { ping(); n++; }
    return n;
}

static void test_resweep_from_arc_end(void)
{
    printf("resweep starting at an arc end: no turnaround, one pass\n");
    lock_loop_cfg_t c = cfg();
    c.resweep_ms = 1;                       /* a resweep at every chance */
    int from_end = 0, from_mid = 0;
    /* Sector 15..35. Locking at 165 (start 165) puts every sector pass end,
     * and so every resweep start, at 15 (an arc end); locking at 15 (start
     * 15) puts them at 35 (mid-arc). Run both. */
    for (int r = 0; r < 8; r++) {
        if (r == 0 || r == 4) {
            start(&c, r == 0 ? 165.0f : 15.0f);
            w.obj[0] = (obj_t){.bearing = 18.0f, .dist = 50.0f, .present = true};
            CHECK(run_until_locked(400) > 0);
        }
        float a0;
        int n = one_resweep(&a0);
        CHECK(n > 0);
        CHECK_NEAR(w.min_seen, 15.0, 1e-3);           /* always the whole arc */
        CHECK_NEAR(w.max_seen, 165.0, 1e-3);
        if (a0 <= 15.001f || a0 >= 164.999f) {
            from_end++;
            CHECK(n == 75);                           /* already complete */
        } else {
            from_mid++;
            CHECK(n > 75 && n <= 150);                /* leg + one complete pass */
        }
        CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);
    }
    CHECK(from_end > 0);                              /* both cases were exercised */
    CHECK(from_mid > 0);
    CHECK(w.big_steps == 0);
}

static void test_resweep_short_interval(void)
{
    printf("resweep_ms shorter than a pass: still a complete pass each time\n");
    lock_loop_cfg_t c = cfg();
    c.resweep_ms = 1;
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    for (int r = 0; r < 4; r++) {
        float a0;
        int n = one_resweep(&a0);
        /* Starts at a sector end (75 or 105): 30-step leg to the arc end,
         * turnaround, then 75 steps end to end. A check on the map instead
         * of resweep_turned would stop after the leg here (n = 30), because
         * the far end is still fresh from the previous resweep. */
        CHECK(n == 105);
        CHECK_NEAR(w.min_seen, 15.0, 1e-3);
        CHECK_NEAR(w.max_seen, 165.0, 1e-3);
        CHECK(lock_loop_track(&w.ll)->state == TRACK_LOCKED);
    }
    CHECK(w.big_steps == 0);
}

static void test_arc_end(void)
{
    printf("target near the arc end: sector clamped, edge flag\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 18.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    for (int i = 0; i < 200; i++) ping();
    const target_track_t *t = lock_loop_track(&w.ll);
    CHECK(t->state == TRACK_LOCKED);
    CHECK(t->target.edge);                                /* the smear is cut at 15 */
    CHECK_NEAR(t->lim_lo_deg, 15.0, 1e-3);
    CHECK(w.out_of_arc == 0);
}

static void test_reset(void)
{
    printf("reset: SEARCHING, FULL, same angle\n");
    lock_loop_cfg_t c = cfg();
    start(&c, 15.0f);
    w.obj[0] = (obj_t){.bearing = 90.0f, .dist = 50.0f, .present = true};
    CHECK(run_until_locked(400) > 0);
    for (int i = 0; i < 50; i++) ping();
    float a = w.ll.plan.angle_deg;
    lock_loop_reset(&w.ll);
    CHECK(lock_loop_track(&w.ll)->state == TRACK_SEARCHING);
    CHECK(lock_loop_plan(&w.ll) == LOCK_PLAN_FULL);
    CHECK_NEAR(w.ll.plan.angle_deg, a, 0);
    CHECK_NEAR(lock_loop_track(&w.ll)->lim_lo_deg, 15.0, 0);
    CHECK(w.ll.locked_at_ms == 0);
    ping();
    CHECK(w.big_steps == 0);
}

int main(void)
{
    printf("test_lock_loop\n");
    test_init();
    test_lock_and_sector();
    test_removed();
    test_follow();
    test_resweep();
    test_resweep_no_ping_loss();
    test_resweep_from_arc_end();
    test_resweep_short_interval();
    test_arc_end();
    test_reset();
    return TEST_RESULT();
}
