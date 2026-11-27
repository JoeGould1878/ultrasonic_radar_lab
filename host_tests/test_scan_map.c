/**
 * @file test_scan_map.c
 * @brief Host tests for scan_map (S3). Written by Claude (Anthropic) for Joe Gould.
 *
 * Checks the bin layout Joe chose on 27/11 (floor, centre at i + 0.5, the 2 deg
 * sweep grid mid-bin), exact angle storage, the three statuses kept apart,
 * age / freshness, and the age <= max_age boundary used everywhere.
 */
#include <stdint.h>
#include "scan_map.h"
#include "test_util.h"

static scan_map_t m;   /* ~3 KB: keep it off the stack */

static void test_layout(void)
{
    printf("layout\n");
    scan_map_init(&m, 2.0f);
    CHECK(m.n_bins == 90);
    CHECK_NEAR(m.bin_deg, 2.0, 0);
    for (int i = 0; i < m.n_bins; i++) {
        CHECK(m.bins[i].status == READING_NONE);
        CHECK_NEAR(m.bins[i].angle_deg, scan_map_bin_angle(&m, i), 0);
    }

    scan_map_init(&m, 1.0f);
    CHECK(m.n_bins == 180);
    CHECK_NEAR(scan_map_bin_angle(&m, 0), 0.5, 0);
    CHECK_NEAR(scan_map_bin_angle(&m, 179), 179.5, 0);

    scan_map_init(&m, 7.0f);          /* 180/7 = 25.7 -> 26 bins, last one past 180 */
    CHECK(m.n_bins == 26);
    CHECK(scan_map_bin(&m, 180.0f) == 25);

    scan_map_init(&m, 180.0f);
    CHECK(m.n_bins == 1);
    CHECK_NEAR(scan_map_bin_angle(&m, 0), 90.0, 0);
}

static void test_bad_bin_width(void)
{
    printf("bad bin width\n");
    const float bad[] = {0.0f, -2.0f, 0.5f, NAN};
    for (unsigned k = 0; k < sizeof bad / sizeof bad[0]; k++) {
        scan_map_init(&m, bad[k]);    /* raised to 1 deg: still covers 0-180 */
        CHECK_NEAR(m.bin_deg, 1.0, 0);
        CHECK(m.n_bins == 180);
    }
    scan_map_init(&m, 400.0f);
    CHECK_NEAR(m.bin_deg, 180.0, 0);
    CHECK(m.n_bins == 1);
}

static void test_bin_lookup(void)
{
    printf("bin lookup (2 deg)\n");
    scan_map_init(&m, 2.0f);
    CHECK(scan_map_bin(&m, 15.0f) == 7);
    CHECK_NEAR(scan_map_bin_angle(&m, 7), 15.0, 0);
    CHECK(scan_map_bin(&m, 14.999f) == 7);    /* Joe: drift either side, same bin */
    CHECK(scan_map_bin(&m, 15.001f) == 7);
    CHECK(scan_map_bin(&m, 14.0f) == 7);      /* lower edge belongs to the bin */
    CHECK(scan_map_bin(&m, 16.0f) == 8);      /* upper edge belongs to the next */
    CHECK(scan_map_bin(&m, 165.0f) == 82);
    CHECK_NEAR(scan_map_bin_angle(&m, 82), 165.0, 0);

    /* clamping */
    CHECK(scan_map_bin(&m, 0.0f) == 0);
    CHECK(scan_map_bin(&m, -3.0f) == 0);
    CHECK(scan_map_bin(&m, NAN) == 0);
    CHECK(scan_map_bin(&m, 179.99f) == 89);
    CHECK(scan_map_bin(&m, 180.0f) == 89);    /* 180 clamps into the last bin */
    CHECK(scan_map_bin(&m, 250.0f) == 89);

    /* The whole sweep grid 15, 17 ... 165: one bin each, consecutive, each
     * angle exactly on its bin centre, and +/-0.9 deg never changes the bin. */
    int prev = -1;
    for (int a = 15; a <= 165; a += 2) {
        int b = scan_map_bin(&m, (float)a);
        CHECK(b == prev + 1 || prev == -1);
        CHECK_NEAR(scan_map_bin_angle(&m, b), a, 0);
        CHECK(scan_map_bin(&m, a - 0.9f) == b);
        CHECK(scan_map_bin(&m, a + 0.9f) == b);
        prev = b;
    }
    CHECK(prev == 82);
}

static void test_update(void)
{
    printf("update\n");
    scan_map_init(&m, 2.0f);
    scan_map_update(&m, 15.3f, 52.3f, READING_OK, 1000);
    const scan_bin_t *b = &m.bins[7];
    CHECK(b->status == READING_OK);
    CHECK_NEAR(b->dist_cm, 52.3, 1e-5);
    CHECK(b->t_ms == 1000);
    CHECK_NEAR(b->angle_deg, 15.3, 1e-6);     /* the real angle, not the centre */

    scan_map_update(&m, 14.6f, 60.0f, READING_OK, 1060);   /* same bin: replaced */
    CHECK_NEAR(b->dist_cm, 60.0, 1e-5);
    CHECK(b->t_ms == 1060);
    CHECK_NEAR(b->angle_deg, 14.6, 1e-6);

    /* Three outcomes kept apart (and never confused with "never measured") */
    scan_map_update(&m, 17.0f, 0.0f, READING_NO_ECHO, 1100);
    scan_map_update(&m, 19.0f, 0.0f, READING_FAILED, 1160);
    CHECK(m.bins[8].status == READING_NO_ECHO);
    CHECK(m.bins[9].status == READING_FAILED);
    CHECK(m.bins[10].status == READING_NONE);
    CHECK(m.bins[8].t_ms == 1100);
    CHECK(m.bins[9].t_ms == 1160);

    /* Out-of-range angles clamp to the end bins but keep their real angle */
    scan_map_update(&m, 181.0f, 40.0f, READING_OK, 1200);
    CHECK(m.bins[89].status == READING_OK);
    CHECK_NEAR(m.bins[89].angle_deg, 181.0, 1e-6);
}

static void test_age_freshness(void)
{
    printf("age and freshness\n");
    scan_map_init(&m, 2.0f);
    CHECK(scan_map_age_ms(&m, 7, 5000) == UINT32_MAX);     /* never measured */
    CHECK(scan_map_age_ms(&m, -1, 5000) == UINT32_MAX);    /* no such bin */
    CHECK(scan_map_age_ms(&m, 90, 5000) == UINT32_MAX);

    scan_map_update(&m, 15.0f, 50.0f, READING_OK, 1000);
    scan_map_update(&m, 17.0f, 0.0f, READING_NO_ECHO, 1000);
    CHECK(scan_map_age_ms(&m, 7, 1500) == 500);
    CHECK(scan_map_age_ms(&m, 8, 1500) == 500);            /* NO_ECHO ages too */
    CHECK(scan_map_age_ms(&m, 7, 900) == 0);               /* clock behind: new */

    const uint32_t fade = 3000;
    CHECK_NEAR(scan_map_freshness(&m, 7, 1000, fade), 1.0, 1e-6);
    CHECK_NEAR(scan_map_freshness(&m, 7, 2500, fade), 0.5, 1e-6);
    CHECK_NEAR(scan_map_freshness(&m, 7, 4000, fade), 0.0, 0);
    CHECK_NEAR(scan_map_freshness(&m, 7, 9000, fade), 0.0, 0);
    CHECK_NEAR(scan_map_freshness(&m, 9, 1000, fade), 0.0, 0);   /* never measured */
    CHECK_NEAR(scan_map_freshness(&m, 7, 1000, 0), 1.0, 0);      /* no fade: only "now" */
    CHECK_NEAR(scan_map_freshness(&m, 7, 1001, 0), 0.0, 0);
}

static void test_expire(void)
{
    printf("expire (age <= max_age kept)\n");
    scan_map_init(&m, 2.0f);
    scan_map_update(&m, 15.0f, 50.0f, READING_OK, 0);        /* age 3000 at now */
    scan_map_update(&m, 17.0f, 51.0f, READING_OK, 1000);     /* age 2000 = max: kept */
    scan_map_update(&m, 19.0f, 52.0f, READING_OK, 2999);
    scan_map_update(&m, 21.0f, 0.0f, READING_NO_ECHO, 500);  /* old NO_ECHO goes too */
    scan_map_update(&m, 23.0f, 0.0f, READING_FAILED, 500);   /* and old FAILED */

    scan_map_expire(&m, 3000, 2000);
    CHECK(m.bins[7].status == READING_NONE);
    CHECK(scan_map_age_ms(&m, 7, 3000) == UINT32_MAX);
    CHECK_NEAR(m.bins[7].angle_deg, 15.0, 0);                /* back to the centre */
    CHECK_NEAR(m.bins[7].dist_cm, 0.0, 0);
    CHECK(m.bins[8].status == READING_OK);
    CHECK(m.bins[9].status == READING_OK);
    CHECK(m.bins[10].status == READING_NONE);
    CHECK(m.bins[11].status == READING_NONE);

    scan_map_expire(&m, 3001, 2000);                         /* now 2001 old: gone */
    CHECK(m.bins[8].status == READING_NONE);
    CHECK(m.bins[9].status == READING_OK);
}

int main(void)
{
    printf("test_scan_map\n");
    test_layout();
    test_bad_bin_width();
    test_bin_lookup();
    test_update();
    test_age_freshness();
    test_expire();
    return TEST_RESULT();
}
