/**
 * @file test_sweep_plan.c
 * @brief Host tests for sweep_plan (S3). Written by Claude (Anthropic) for Joe Gould.
 *
 * Checks the bounce sweep against S2's sweep order, the sector rules Joe
 * approved (ends snapped inward to the grid, no jumps, pass ends at the far
 * end), MANUAL slew limiting, and a randomised "never jumps" property.
 */
#include <math.h>
#include <stdint.h>
#include "sweep_plan.h"
#include "test_util.h"

static const sweep_cfg_t CFG = {.min_deg = 15.0f, .max_deg = 165.0f, .step_deg = 2.0f};

static int on_grid(float a)
{
    float k = (a - 15.0f) / 2.0f;
    return fabsf(k - roundf(k)) < 1e-4f;
}

static void test_full_bounce(void)
{
    printf("full bounce (S2 order)\n");
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 15.0f);
    CHECK(p.kind == SWEEP_FULL);
    /* First call advances: 17, 19 ... 165 (75 steps), pass done only at 165. */
    for (int k = 1; k <= 75; k++) {
        float a = sweep_plan_next(&p, 0);
        CHECK_NEAR(a, 15.0 + 2.0 * k, 1e-4);
        CHECK(sweep_plan_take_pass_done(&p) == (k == 75));
    }
    CHECK(sweep_plan_take_pass_done(&p) == false);       /* cleared once taken */
    /* Back down: 163 ... 15, done only at 15 (the end ping is not repeated). */
    for (int k = 1; k <= 75; k++) {
        float a = sweep_plan_next(&p, 0);
        CHECK_NEAR(a, 165.0 - 2.0 * k, 1e-4);
        CHECK(sweep_plan_take_pass_done(&p) == (k == 75));
    }
    CHECK_NEAR(sweep_plan_next(&p, 0), 17.0, 1e-4);
}

static void test_full_starts(void)
{
    printf("full: start angles, bad config, uneven arc\n");
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 165.0f);                    /* at max: heads down */
    CHECK_NEAR(sweep_plan_next(&p, 0), 163.0, 1e-4);
    sweep_plan_init(&p, &CFG, 200.0f);                    /* clamped to max */
    CHECK_NEAR(p.angle_deg, 165.0, 0);
    CHECK_NEAR(sweep_plan_next(&p, 0), 163.0, 1e-4);
    sweep_plan_init(&p, &CFG, 90.0f);                     /* off-grid: next grid point */
    CHECK_NEAR(sweep_plan_next(&p, 0), 91.0, 1e-4);
    sweep_plan_init(&p, &CFG, NAN);
    CHECK_NEAR(p.angle_deg, 15.0, 0);

    sweep_cfg_t bad = {.min_deg = 165.0f, .max_deg = 15.0f, .step_deg = 0.0f};
    sweep_plan_init(&p, &bad, 15.0f);
    CHECK_NEAR(p.cfg.min_deg, 15.0, 0);
    CHECK_NEAR(p.cfg.max_deg, 165.0, 0);
    CHECK_NEAR(p.cfg.step_deg, 1.0, 0);
    CHECK_NEAR(sweep_plan_next(&p, 0), 16.0, 1e-4);

    /* 150 / 4 is not whole: last step up is clamped to 165, then back on grid. */
    sweep_cfg_t c4 = {.min_deg = 15.0f, .max_deg = 165.0f, .step_deg = 4.0f};
    sweep_plan_init(&p, &c4, 159.0f);
    CHECK_NEAR(sweep_plan_next(&p, 0), 163.0, 1e-4);
    CHECK(!sweep_plan_take_pass_done(&p));
    CHECK_NEAR(sweep_plan_next(&p, 0), 165.0, 1e-4);
    CHECK(sweep_plan_take_pass_done(&p));
    CHECK_NEAR(sweep_plan_next(&p, 0), 163.0, 1e-4);
}

static void test_sector(void)
{
    printf("sector: ends snapped inward, bounce\n");
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 89.0f);
    sweep_plan_sector(&p, 90.0f, 15.0f);                  /* 75..105, both on grid */
    int n = 0;
    float a;
    do { a = sweep_plan_next(&p, 0); n++; } while (!sweep_plan_take_pass_done(&p) && n < 100);
    CHECK_NEAR(a, 105.0, 1e-4);
    CHECK(n == 8);                                        /* 91 ... 105 */
    n = 0;
    do { a = sweep_plan_next(&p, 0); n++; CHECK(on_grid(a)); }
    while (!sweep_plan_take_pass_done(&p) && n < 100);
    CHECK_NEAR(a, 75.0, 1e-4);
    CHECK(n == 15);                                       /* a full sector pass */

    sweep_plan_sector(&p, 91.0f, 15.0f);                  /* 76..106 -> 77..105 */
    float lo = 999, hi = -999;
    for (int k = 0; k < 40; k++) {
        a = sweep_plan_next(&p, 0);
        CHECK(on_grid(a));
        lo = fminf(lo, a);
        hi = fmaxf(hi, a);
    }
    CHECK_NEAR(lo, 77.0, 1e-4);
    CHECK_NEAR(hi, 105.0, 1e-4);

    sweep_plan_init(&p, &CFG, 25.0f);                     /* clamped at the arc: 15..35 */
    sweep_plan_sector(&p, 20.0f, 15.0f);
    lo = 999; hi = -999;
    for (int k = 0; k < 40; k++) {
        a = sweep_plan_next(&p, 0);
        lo = fminf(lo, a);
        hi = fmaxf(hi, a);
    }
    CHECK_NEAR(lo, 15.0, 1e-4);
    CHECK_NEAR(hi, 35.0, 1e-4);

    sweep_plan_init(&p, &CFG, 89.0f);                     /* narrower than a step */
    sweep_plan_sector(&p, 90.0f, 0.0f);
    CHECK_NEAR(sweep_plan_next(&p, 0), 91.0, 1e-4);
    CHECK(sweep_plan_take_pass_done(&p));
    CHECK_NEAR(sweep_plan_next(&p, 0), 89.0, 1e-4);
    CHECK(sweep_plan_take_pass_done(&p));
    sweep_plan_sector(&p, 165.0f, -1.0f);                 /* at the arc end; |half| */
    for (int k = 0; k < 60; k++) {                        /* 38 steps to walk there */
        a = sweep_plan_next(&p, 0);
    }
    CHECK(a >= 163.0f - 1e-4f && a <= 165.0f + 1e-4f);
}

static void test_sector_entry(void)
{
    printf("sector: walk in from outside, no jump, pass ends at the far end\n");
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 15.0f);
    for (int k = 0; k < 75; k++) {
        sweep_plan_next(&p, 0);                           /* up to 165 */
    }
    CHECK(sweep_plan_take_pass_done(&p));
    sweep_plan_sector(&p, 90.0f, 15.0f);
    int n = 0;
    float prev = p.angle_deg, a;
    do {
        a = sweep_plan_next(&p, 0);
        CHECK(fabsf(a - prev) <= 2.0f + 1e-4f);
        prev = a;
        n++;
    } while (!sweep_plan_take_pass_done(&p) && n < 200);
    CHECK_NEAR(a, 75.0, 1e-4);                            /* not done at 105 */
    CHECK(n == 45);                                       /* 163 ... 75 */

    /* Recentre at a pass end so the old end is outside: steps across. */
    sweep_plan_recentre(&p, 100.0f);                      /* 85..115; at 75, going up */
    n = 0;
    do { a = sweep_plan_next(&p, 0); n++; } while (!sweep_plan_take_pass_done(&p) && n < 200);
    CHECK_NEAR(a, 115.0, 1e-4);
    CHECK(n == 20);
    sweep_plan_recentre(&p, 80.0f);                       /* 65..95; at 115, going down */
    n = 0;
    do { a = sweep_plan_next(&p, 0); n++; } while (!sweep_plan_take_pass_done(&p) && n < 200);
    CHECK_NEAR(a, 65.0, 1e-4);
    CHECK(n == 25);

    /* Recentre keeps a pending pass flag; a plan switch clears it. */
    sweep_plan_init(&p, &CFG, 163.0f);
    sweep_plan_next(&p, 0);
    CHECK(p.sweep_done);
    sweep_plan_recentre(&p, 90.0f);
    CHECK(p.sweep_done);
    sweep_plan_sector(&p, 90.0f, 15.0f);
    CHECK(!sweep_plan_take_pass_done(&p));
    sweep_plan_full(&p);
    CHECK(p.kind == SWEEP_FULL);
}

static void test_manual(void)
{
    printf("manual: slew limit, clamp, no pass flag\n");
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 90.0f);
    sweep_plan_manual(&p, 100.0f);
    CHECK_NEAR(sweep_plan_next(&p, 3.0f), 93.0, 1e-4);
    CHECK_NEAR(sweep_plan_next(&p, 3.0f), 96.0, 1e-4);
    CHECK_NEAR(sweep_plan_next(&p, 3.0f), 99.0, 1e-4);
    CHECK_NEAR(sweep_plan_next(&p, 3.0f), 100.0, 1e-4);
    CHECK_NEAR(sweep_plan_next(&p, 3.0f), 100.0, 1e-4);
    CHECK(!sweep_plan_take_pass_done(&p));
    CHECK(p.dir == +1);
    sweep_plan_manual(&p, 300.0f);
    CHECK_NEAR(p.manual_target, 165.0, 0);
    sweep_plan_manual(&p, 50.0f);
    CHECK_NEAR(sweep_plan_next(&p, 0.0f), 100.0, 0);      /* 0 = no movement */
    CHECK_NEAR(sweep_plan_next(&p, -5.0f), 100.0, 0);
    CHECK_NEAR(sweep_plan_next(&p, NAN), 100.0, 0);
    CHECK_NEAR(sweep_plan_next(&p, 10.5f), 89.5, 1e-4);
    CHECK(p.dir == -1);
    sweep_plan_full(&p);                                  /* rejoins the grid, same way */
    CHECK_NEAR(sweep_plan_next(&p, 0), 89.0, 1e-4);       /* first grid point below 89.5 */
    CHECK_NEAR(sweep_plan_next(&p, 0), 87.0, 1e-4);
}

/* Random plan switches: the angle never leaves the arc and never moves more
 * than one step (FULL/SECTOR) or max_step (MANUAL) per call. */
static void test_never_jumps(void)
{
    printf("random switches: never jumps, stays in the arc\n");
    uint32_t r = 12345;
    sweep_plan_t p;
    sweep_plan_init(&p, &CFG, 90.0f);
    int bad_step = 0, bad_range = 0;
    for (int k = 0; k < 20000; k++) {
        r = r * 1664525u + 1013904223u;
        uint32_t pick = (r >> 24) % 40;
        float x = 10.0f + (float)((r >> 8) % 1700) / 10.0f;   /* 10..180 */
        if (pick == 0) sweep_plan_full(&p);
        else if (pick == 1) sweep_plan_sector(&p, x, (float)((r >> 4) % 30));
        else if (pick == 2) sweep_plan_recentre(&p, x);
        else if (pick == 3) sweep_plan_manual(&p, x);
        float prev = p.angle_deg;
        float ms = 3.7f;
        float a = sweep_plan_next(&p, ms);
        float lim = (p.kind == SWEEP_MANUAL) ? ms : CFG.step_deg;
        if (fabsf(a - prev) > lim + 1e-3f) bad_step++;
        if (a < 15.0f - 1e-4f || a > 165.0f + 1e-4f) bad_range++;
    }
    CHECK(bad_step == 0);
    CHECK(bad_range == 0);
}

static void test_pass_ends(void)
{
    printf("pass_ends: what the servo really reaches\n");
    sweep_plan_t p;
    float lo, hi;
    sweep_plan_init(&p, &CFG, 90.0f);
    sweep_plan_pass_ends(&p, &lo, &hi);
    CHECK_NEAR(lo, 15.0, 0);
    CHECK_NEAR(hi, 165.0, 0);
    sweep_plan_sector(&p, 91.0f, 15.0f);
    sweep_plan_pass_ends(&p, &lo, &hi);
    CHECK_NEAR(lo, 77.0, 1e-4);
    CHECK_NEAR(hi, 105.0, 1e-4);
    sweep_plan_recentre(&p, 20.0f);
    sweep_plan_pass_ends(&p, &lo, &hi);
    CHECK_NEAR(lo, 15.0, 1e-4);
    CHECK_NEAR(hi, 35.0, 1e-4);
    sweep_plan_manual(&p, 50.0f);
    sweep_plan_pass_ends(&p, &lo, &hi);
    CHECK_NEAR(lo, 15.0, 0);
    CHECK_NEAR(hi, 165.0, 0);

    /* Matches the angles actually visited, for many centres and widths. */
    int bad = 0;
    for (int c10 = 100; c10 <= 1800; c10 += 37) {
        for (int h = 0; h <= 30; h += 3) {
            sweep_plan_init(&p, &CFG, 90.0f);
            sweep_plan_sector(&p, c10 / 10.0f, (float)h);
            float vlo = 999, vhi = -999;
            for (int k = 0; k < 200; k++) {
                float a = sweep_plan_next(&p, 0);
                if (k >= 100) {               /* after any walk-in */
                    vlo = fminf(vlo, a);
                    vhi = fmaxf(vhi, a);
                }
            }
            sweep_plan_pass_ends(&p, &lo, &hi);
            if (fabsf(lo - vlo) > 1e-3f || fabsf(hi - vhi) > 1e-3f) bad++;
        }
    }
    CHECK(bad == 0);
}

int main(void)
{
    printf("test_sweep_plan\n");
    test_full_bounce();
    test_full_starts();
    test_sector();
    test_sector_entry();
    test_manual();
    test_never_jumps();
    test_pass_ends();
    return TEST_RESULT();
}
