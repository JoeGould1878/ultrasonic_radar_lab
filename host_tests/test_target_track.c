/**
 * @file test_target_track.c
 * @brief Host tests for target_track (S3). Written by Claude (Anthropic) for Joe Gould.
 *
 * Hand-built maps on the 2 deg grid (15, 17 ... 165). Checks the cluster
 * rule (the one S2's Python uses), upper median, age / range filters,
 * bridging (Joe's approved rule), the edge flag against the current limits,
 * and the SEARCHING -> CANDIDATE -> LOCKED -> lost state machine.
 * Scene-level C = Python checks are in test_scenes.c.
 */
#include <stdint.h>
#include "target_track.h"
#include "test_util.h"

static scan_map_t m;

static track_cfg_t cfg(void)
{
    return (track_cfg_t){
        .dist_tol_cm = 8.0f, .min_bins = 2, .confirm_sweeps = 2, .lost_pings = 6,
        .max_range_cm = 150.0f, .arc_min_deg = 15.0f, .arc_max_deg = 165.0f,
        .bridge_gap_bins = 0, .gate_deg = 15.0f,
    };
}

static void put(float a, float d, reading_status_t st, uint32_t t)
{
    scan_map_update(&m, a, d, st, t);
}

/* OK readings at a0, a0+2, ... a1, all at dist d (+ ramp per bin), time t. */
static void put_run(float a0, float a1, float d, float ramp, uint32_t t)
{
    int k = 0;
    for (float a = a0; a <= a1 + 1e-3f; a += 2.0f, k++) {
        put(a, d + ramp * (float)k, READING_OK, t);
    }
}

static track_cluster_t find(const target_track_t *t, uint32_t now, uint32_t max_age)
{
    return target_track_find_cluster(t, &m, now, max_age);
}

static void test_basic_cluster(void)
{
    printf("cluster: edges, centre, upper median, nearest\n");
    target_track_t t;
    track_cfg_t c = cfg();
    target_track_init(&t, &c);
    CHECK(t.state == TRACK_SEARCHING);
    CHECK_NEAR(t.lim_lo_deg, 15.0, 0);
    CHECK_NEAR(t.lim_hi_deg, 165.0, 0);

    scan_map_init(&m, 2.0f);
    CHECK(!find(&t, 1000, 5000).valid);                   /* empty map */

    put_run(81, 93, 50.0f, 0.5f, 1000);                   /* 7 bins 50.0 .. 53.0 */
    track_cluster_t k = find(&t, 1000, 5000);
    CHECK(k.valid);
    CHECK_NEAR(k.left_deg, 81.0, 0);
    CHECK_NEAR(k.right_deg, 93.0, 0);
    CHECK_NEAR(k.centre_deg, 87.0, 0);
    CHECK(k.n_bins == 7);
    CHECK_NEAR(k.dist_cm, 51.5, 1e-5);                    /* middle of 7 */
    CHECK(!k.edge);

    scan_map_init(&m, 2.0f);                              /* even count: upper middle */
    put(101, 53.0f, READING_OK, 0);
    put(103, 50.0f, READING_OK, 0);
    put(105, 52.0f, READING_OK, 0);
    put(107, 51.0f, READING_OK, 0);
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 4);
    CHECK_NEAR(k.dist_cm, 52.0, 0);                       /* sorted 50 51 52 53 -> [2] */

    /* Two objects: the nearer wins whatever its size or side. */
    scan_map_init(&m, 2.0f);
    put_run(41, 55, 100.0f, 0, 0);
    put_run(121, 125, 60.0f, 0, 0);
    k = find(&t, 0, 5000);
    CHECK_NEAR(k.centre_deg, 123.0, 0);
    CHECK_NEAR(k.dist_cm, 60.0, 0);

    scan_map_init(&m, 2.0f);                              /* tie: lower angle wins */
    put_run(41, 45, 60.0f, 0, 0);
    put_run(121, 125, 60.0f, 0, 0);
    CHECK_NEAR(find(&t, 0, 5000).centre_deg, 43.0, 0);
}

static void test_split_and_filters(void)
{
    printf("cluster: dist_tol split, min_bins, range, age, never-measured\n");
    target_track_t t;
    track_cfg_t c = cfg();
    target_track_init(&t, &c);

    /* A step of exactly dist_tol joins; tol + 0.1 splits (compared with the
     * LAST bin, so a slow ramp stays one cluster, as in S2). */
    scan_map_init(&m, 2.0f);
    put_run(61, 65, 50.0f, 0, 0);
    put(67, 58.0f, READING_OK, 0);                        /* +8.0: joins */
    put(69, 66.1f, READING_OK, 0);                        /* +8.1: new cluster */
    put(71, 66.5f, READING_OK, 0);
    track_cluster_t k = find(&t, 0, 5000);
    CHECK_NEAR(k.left_deg, 61.0, 0);
    CHECK_NEAR(k.right_deg, 67.0, 0);
    CHECK(k.n_bins == 4);

    scan_map_init(&m, 2.0f);                              /* ramp 5 cm/bin: one cluster */
    put_run(61, 75, 40.0f, 5.0f, 0);
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 8);

    scan_map_init(&m, 2.0f);                              /* single bins don't count */
    put(51, 30.0f, READING_OK, 0);
    put_run(91, 93, 80.0f, 0, 0);
    k = find(&t, 0, 5000);
    CHECK_NEAR(k.centre_deg, 92.0, 0);
    c.min_bins = 1;
    target_track_init(&t, &c);
    CHECK_NEAR(find(&t, 0, 5000).centre_deg, 51.0, 0);
    c.min_bins = 2;
    target_track_init(&t, &c);

    scan_map_init(&m, 2.0f);                              /* beyond max range: ignored */
    put_run(51, 55, 150.0f, 0, 0);
    CHECK(find(&t, 0, 5000).valid);                       /* 150 itself is in range */
    scan_map_init(&m, 2.0f);
    put_run(51, 55, 150.1f, 0, 0);
    CHECK(!find(&t, 0, 5000).valid);

    /* Age: age == max_age used, age > max_age not. */
    scan_map_init(&m, 2.0f);
    put(71, 50.0f, READING_OK, 1000);
    put(73, 50.0f, READING_OK, 1000);
    put(75, 50.0f, READING_OK, 999);
    k = find(&t, 3000, 2000);
    CHECK(k.n_bins == 2);
    CHECK_NEAR(k.right_deg, 73.0, 0);

    /* A never-measured bin breaks a cluster like a NO_ECHO. */
    scan_map_init(&m, 2.0f);
    put_run(71, 75, 50.0f, 0, 0);
    put_run(79, 83, 50.0f, 0, 0);                         /* 77 never measured */
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 3);
    CHECK_NEAR(k.right_deg, 75.0, 0);
}

static void test_bridging(void)
{
    printf("bridging (approved rule)\n");
    target_track_t t;
    track_cfg_t c = cfg();

    /* 81..93 with one NO_ECHO at 87: two 3-bin pieces without bridging. */
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, 0);
    put(87, 0, READING_NO_ECHO, 0);
    target_track_init(&t, &c);
    track_cluster_t k = find(&t, 0, 5000);
    CHECK(k.n_bins == 3);
    CHECK_NEAR(k.centre_deg, 83.0, 0);                    /* tie on dist: lower angle */
    c.bridge_gap_bins = 1;
    target_track_init(&t, &c);
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 6);                                 /* bridged bin not counted */
    CHECK_NEAR(k.left_deg, 81.0, 0);
    CHECK_NEAR(k.right_deg, 93.0, 0);
    CHECK_NEAR(k.centre_deg, 87.0, 0);

    put(87, 0, READING_FAILED, 0);                        /* FAILED bridges too */
    CHECK(find(&t, 0, 5000).n_bins == 6);

    put(89, 0, READING_NO_ECHO, 0);                       /* gap of 2 > bridge 1 */
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 3);
    CHECK_NEAR(k.right_deg, 85.0, 0);
    c.bridge_gap_bins = 2;
    target_track_init(&t, &c);
    CHECK(find(&t, 0, 5000).n_bins == 5);

    /* Across the gap the distances must still be within dist_tol. */
    c.bridge_gap_bins = 1;
    target_track_init(&t, &c);
    scan_map_init(&m, 2.0f);
    put_run(81, 85, 50.0f, 0, 0);
    put(87, 0, READING_NO_ECHO, 0);
    put_run(89, 93, 70.0f, 0, 0);
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 3);
    CHECK_NEAR(k.right_deg, 85.0, 0);

    /* An OK bin at another distance is never bridged over: two dowels. */
    scan_map_init(&m, 2.0f);
    put_run(81, 85, 50.0f, 0, 0);
    put(87, 90.0f, READING_OK, 0);                        /* the wall between them */
    put_run(89, 93, 50.0f, 0, 0);
    k = find(&t, 0, 5000);
    CHECK(k.n_bins == 3);
    CHECK_NEAR(k.right_deg, 85.0, 0);

    /* Stale, too-far and never-measured bins count as non-OK gap bins. */
    scan_map_init(&m, 2.0f);
    put_run(81, 85, 50.0f, 0, 5000);
    put(87, 50.0f, READING_OK, 0);                        /* stale */
    put_run(89, 93, 50.0f, 0, 5000);
    CHECK(find(&t, 5000, 1000).n_bins == 6);
    put(87, 200.0f, READING_OK, 5000);                    /* beyond range */
    CHECK(find(&t, 5000, 1000).n_bins == 6);
    c.bridge_gap_bins = -3;                               /* negative = off */
    target_track_init(&t, &c);
    CHECK(find(&t, 5000, 1000).n_bins == 3);
}

static void test_edge(void)
{
    printf("edge flag vs current limits\n");
    target_track_t t;
    track_cfg_t c = cfg();
    target_track_init(&t, &c);

    scan_map_init(&m, 2.0f);
    put_run(15, 23, 50.0f, 0, 0);
    CHECK(find(&t, 0, 5000).edge);                        /* includes 15 */
    scan_map_init(&m, 2.0f);
    put_run(17, 25, 50.0f, 0, 0);
    CHECK(!find(&t, 0, 5000).edge);                       /* 15 was not OK */
    scan_map_init(&m, 2.0f);
    put_run(157, 165, 50.0f, 0, 0);
    CHECK(find(&t, 0, 5000).edge);

    /* Sector 75..105: the sector ends count, the arc ends no longer matter. */
    target_track_set_limits(&t, 75.0f, 105.0f);
    scan_map_init(&m, 2.0f);
    put_run(95, 105, 50.0f, 0, 0);
    CHECK(find(&t, 0, 5000).edge);
    scan_map_init(&m, 2.0f);
    put_run(85, 95, 50.0f, 0, 0);
    CHECK(!find(&t, 0, 5000).edge);
    scan_map_init(&m, 2.0f);
    put_run(101, 111, 50.0f, 0, 0);                       /* runs past the sector */
    CHECK(find(&t, 0, 5000).edge);
    scan_map_init(&m, 2.0f);
    put_run(75, 79, 50.0f, 0, 0);
    CHECK(find(&t, 0, 5000).edge);

    /* Limits are clamped to the arc and put in order. */
    target_track_set_limits(&t, 200.0f, 5.0f);
    CHECK_NEAR(t.lim_lo_deg, 15.0, 0);
    CHECK_NEAR(t.lim_hi_deg, 165.0, 0);
    target_track_set_limits(&t, 75.0f, 105.0f);
    target_track_reset(&t);                               /* back to the arc */
    CHECK_NEAR(t.lim_lo_deg, 15.0, 0);
    CHECK_NEAR(t.lim_hi_deg, 165.0, 0);
}

static void test_states(void)
{
    printf("states: search -> candidate -> locked -> lost\n");
    target_track_t t;
    track_cfg_t c = cfg();
    target_track_init(&t, &c);
    uint32_t now = 0;

    scan_map_init(&m, 2.0f);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_SEARCHING);

    put_run(81, 93, 50.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    CHECK(t.seen_count == 1);
    CHECK(t.target.valid);

    now = 4500;                                           /* moved 6 deg: in the gate */
    scan_map_init(&m, 2.0f);
    put_run(87, 99, 50.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 93.0, 0);
    CHECK(t.seen_count == 2);

    now = 9000;                                           /* LOCKED, moved 14 deg: kept */
    scan_map_init(&m, 2.0f);
    put_run(101, 113, 52.0f, 0, now);
    t.miss_count = 3;
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 107.0, 0);
    CHECK(t.miss_count == 0);

    now = 13500;                                          /* 16 deg: outside the gate -> lost */
    scan_map_init(&m, 2.0f);
    put_run(117, 129, 52.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_SEARCHING);
    CHECK(!t.target.valid);
    CHECK_NEAR(t.target.centre_deg, 107.0, 0);            /* last numbers kept */
    CHECK(t.seen_count == 0);

    /* Candidate: a cluster outside the gate restarts it; none -> SEARCHING. */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    scan_map_init(&m, 2.0f);
    put_run(41, 45, 60.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    CHECK_NEAR(t.target.centre_deg, 43.0, 0);
    CHECK(t.seen_count == 1);
    scan_map_init(&m, 2.0f);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_SEARCHING);

    /* LOCKED, a CLOSER object elsewhere (140 deg, 30 cm) is outside the
     * gate: the target is kept (fix (b), Joe 27/11; it used to be lost). */
    put_run(81, 93, 50.0f, 0, now);
    target_track_on_pass(&t, &m, now, 5000);
    target_track_on_pass(&t, &m, now, 5000);
    CHECK(t.state == TRACK_LOCKED);
    put_run(137, 143, 30.0f, 0, now);
    CHECK_NEAR(find(&t, now, 5000).centre_deg, 140.0, 0); /* nearest in distance */
    t.miss_count = 2;
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 87.0, 0);
    CHECK_NEAR(t.target.dist_cm, 50.0, 0);
    CHECK(t.miss_count == 0);
    /* ... and once the target has gone, only the outside-gate one is left: lost. */
    scan_map_init(&m, 2.0f);
    put_run(137, 143, 30.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_SEARCHING);

    /* LOCKED with nothing found -> lost. */
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, now);
    target_track_on_pass(&t, &m, now, 5000);
    target_track_on_pass(&t, &m, now, 5000);
    CHECK(t.state == TRACK_LOCKED);
    scan_map_init(&m, 2.0f);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_SEARCHING);

    /* confirm_sweeps 1: locks on the first pass. */
    c.confirm_sweeps = 1;
    target_track_init(&t, &c);
    put_run(81, 93, 50.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);

    /* gate 0: only an exact repeat confirms. */
    c.confirm_sweeps = 2;
    c.gate_deg = 0.0f;
    target_track_init(&t, &c);
    target_track_on_pass(&t, &m, now, 5000);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    target_track_init(&t, &c);
    target_track_on_pass(&t, &m, now, 5000);
    scan_map_init(&m, 2.0f);
    put_run(83, 95, 50.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
}

static void test_gate_choice(void)
{
    printf("gate: nearest bearing within the gate, not nearest distance\n");
    target_track_t t;
    track_cfg_t c = cfg();
    uint32_t now = 0;

    /* LOCKED on 81..93 (87, 50 cm). Two clusters in the gate: 95..99 at
     * 30 cm (centre 97, 10 deg off, closer) and 79..91 at 60 cm (centre 85,
     * 2 deg off). The one nearest the bearing wins. */
    target_track_init(&t, &c);
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, now);
    target_track_on_pass(&t, &m, now, 5000);
    target_track_on_pass(&t, &m, now, 5000);
    CHECK(t.state == TRACK_LOCKED);
    scan_map_init(&m, 2.0f);
    put_run(79, 91, 60.0f, 0, now);
    put_run(95, 99, 30.0f, 0, now);
    CHECK_NEAR(find(&t, now, 5000).centre_deg, 97.0, 0);  /* nearest in distance */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 85.0, 0);
    CHECK_NEAR(t.target.dist_cm, 60.0, 0);

    /* Gate edge: exactly gate_deg off is in (<=). Target now 85. */
    scan_map_init(&m, 2.0f);
    put_run(97, 103, 50.0f, 0, now);                      /* centre 100 = 85 + 15 */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 100.0, 0);

    /* Bearing tie (two clusters 4 deg either side): the lower angle wins. */
    scan_map_init(&m, 2.0f);
    put_run(93, 95, 40.0f, 0, now);                       /* centre 94 */
    put_run(105, 107, 70.0f, 0, now);                     /* centre 106 */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 94.0, 0);

    /* CANDIDATE on 87: the candidate object again (89, 50 cm) plus a closer
     * object at 140 deg. Confirmed on the candidate, not restarted from 140. */
    target_track_init(&t, &c);
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    scan_map_init(&m, 2.0f);
    put_run(83, 95, 50.0f, 0, now);
    put_run(137, 143, 30.0f, 0, now);
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_LOCKED);
    CHECK_NEAR(t.target.centre_deg, 89.0, 0);
    CHECK(t.seen_count == 2);

    /* CANDIDATE, two in the gate: nearest bearing confirms. */
    c.confirm_sweeps = 3;
    target_track_init(&t, &c);
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, now);                       /* candidate 87 */
    target_track_on_pass(&t, &m, now, 5000);
    scan_map_init(&m, 2.0f);
    put_run(71, 75, 20.0f, 0, now);                       /* centre 73, 14 off, closest */
    put_run(85, 93, 55.0f, 0, now);                       /* centre 89, 2 off */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    CHECK_NEAR(t.target.centre_deg, 89.0, 0);
    CHECK(t.seen_count == 2);

    /* CANDIDATE, none in the gate: restart from the NEAREST (distance) one. */
    scan_map_init(&m, 2.0f);
    put_run(41, 45, 60.0f, 0, now);                       /* 43: 46 off, 60 cm */
    put_run(141, 145, 35.0f, 0, now);                     /* 143: 54 off, 35 cm */
    CHECK(target_track_on_pass(&t, &m, now, 5000) == TRACK_CANDIDATE);
    CHECK_NEAR(t.target.centre_deg, 143.0, 0);
    CHECK(t.seen_count == 1);
}

static void lock_on(target_track_t *t, const track_cfg_t *c)
{
    target_track_init(t, c);
    scan_map_init(&m, 2.0f);
    put_run(81, 93, 50.0f, 0, 0);                         /* target 81..93 at 50 cm */
    target_track_on_pass(t, &m, 0, 5000);
    target_track_on_pass(t, &m, 0, 5000);
}

static void test_on_ping(void)
{
    printf("on_ping: near window, consecutive misses\n");
    target_track_t t;
    track_cfg_t c = cfg();

    target_track_init(&t, &c);                            /* not LOCKED: no effect */
    CHECK(target_track_on_ping(&t, 87, 0, READING_NO_ECHO) == TRACK_SEARCHING);
    CHECK(t.miss_count == 0);

    lock_on(&t, &c);
    CHECK(t.state == TRACK_LOCKED);
    for (int k = 0; k < 20; k++) {                        /* outside 81..93: ignored */
        target_track_on_ping(&t, 79, 0, READING_NO_ECHO);
        target_track_on_ping(&t, 95, 0, READING_FAILED);
    }
    CHECK(t.miss_count == 0);

    for (int k = 0; k < 5; k++) {                         /* 5 misses: still locked */
        CHECK(target_track_on_ping(&t, 81.0f + 2.0f * k, 0, READING_NO_ECHO) == TRACK_LOCKED);
    }
    CHECK(t.miss_count == 5);
    target_track_on_ping(&t, 91, 57.9f, READING_OK);      /* hit (7.9 cm): reset */
    CHECK(t.miss_count == 0);

    target_track_on_ping(&t, 81, 58.1f, READING_OK);      /* OK but 8.1 cm off: miss */
    target_track_on_ping(&t, 83, 0, READING_FAILED);      /* FAILED: miss */
    target_track_on_ping(&t, 85, 0, READING_NO_ECHO);
    target_track_on_ping(&t, 87, 0, READING_NO_ECHO);
    target_track_on_ping(&t, 89, 0, READING_NO_ECHO);
    CHECK(t.state == TRACK_LOCKED);
    CHECK(target_track_on_ping(&t, 93, 0, READING_NO_ECHO) == TRACK_SEARCHING);
    CHECK(!t.target.valid);
    CHECK(t.miss_count == 0);

    lock_on(&t, &c);                                      /* too far = miss */
    target_track_on_ping(&t, 87, 160.0f, READING_OK);
    CHECK(t.miss_count == 1);

    c.lost_pings = 0;                                     /* < 1 counts as 1 */
    lock_on(&t, &c);
    CHECK(target_track_on_ping(&t, 87, 0, READING_NO_ECHO) == TRACK_SEARCHING);
}

int main(void)
{
    printf("test_target_track\n");
    test_basic_cluster();
    test_split_and_filters();
    test_bridging();
    test_edge();
    test_states();
    test_gate_choice();
    test_on_ping();
    return TEST_RESULT();
}
