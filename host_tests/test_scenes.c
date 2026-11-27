/**
 * @file test_scenes.c
 * @brief C = Python check on the S2 scenes (S3). Written by Claude (Anthropic)
 *        for Joe Gould.
 *
 * For every docs/evidence/sim/s2_scenes/<scene>.txt (the firmware's serial
 * protocol), replay the R lines into a scan_map, and at the end of each pass
 * ask target_track_find_cluster for the nearest cluster, with bridging off
 * (0) and on (1). It must equal the row marked nearest = 1 for that pass in
 * <scene>.clusters.csv, written by sim/scene.py's clusters_illustrative from
 * the same logged numbers: left, right, centre, n_bins, dist and edge.
 *
 * Max age = ONE PASS here: the span of the pass just finished (first to last
 * reading). That excludes the previous pass's turnaround reading, exactly as
 * scene.py's per-pass grouping does, so both sides see the same readings.
 * The firmware (lock_loop) uses one pass + one ping instead, which keeps that
 * real 4.5 s-old end reading (the bounce sweep only refreshes the end bins
 * every other pass, D-FADE); this test checks the clustering rule, not the
 * age choice.
 *
 * Passes are split at the arc ends: a reading at APP_SWEEP_MIN/MAX_DEG ends
 * a pass (except the very first reading), the same order as scene.py's
 * sweep_angles().
 */
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "target_track.h"
#include "test_util.h"
#include "../main/app_config.h"   /* host tests may read the config */

#define SCENE_DIR "../docs/evidence/sim/s2_scenes/"
#define MAX_PASSES 64

typedef struct {
    bool  have;
    float left, right, centre, dist;
    int   n, edge;
} row_t;

static row_t want[2][MAX_PASSES];   /* [bridge][pass] nearest rows from the CSV */
static scan_map_t map;

static int read_csv(const char *name)
{
    char path[512];
    snprintf(path, sizeof path, SCENE_DIR "%s.clusters.csv", name);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    memset(want, 0, sizeof want);
    char line[256];
    if (!fgets(line, sizeof line, f)) { fclose(f); return -1; }        /* header */
    while (fgets(line, sizeof line, f)) {
        int b, p, n, edge, near;
        float l, r, c, d;
        if (sscanf(line, "%d,%d,%f,%f,%f,%d,%f,%d,%d", &b, &p, &l, &r, &c, &n, &d, &edge, &near) != 9)
            continue;
        if (near && b >= 0 && b < 2 && p >= 0 && p < MAX_PASSES)
            want[b][p] = (row_t){true, l, r, c, d, n, edge};
    }
    fclose(f);
    return 0;
}

static track_cfg_t track_cfg(int bridge)
{
    return (track_cfg_t){
        .dist_tol_cm = APP_LOCK_DIST_TOL_CM, .min_bins = APP_LOCK_MIN_BINS,
        .confirm_sweeps = APP_LOCK_CONFIRM_SWEEPS, .lost_pings = APP_LOCK_LOST_PINGS,
        .max_range_cm = APP_US_MAX_RANGE_CM,
        .arc_min_deg = APP_SWEEP_MIN_DEG, .arc_max_deg = APP_SWEEP_MAX_DEG,
        .bridge_gap_bins = bridge, .gate_deg = APP_LOCK_SECTOR_HALF_DEG,
    };
}

static int total[2], matched[2], with_target[2];

static void compare(const char *scene, int pass, uint32_t now, uint32_t span)
{
    for (int b = 0; b < 2; b++) {
        target_track_t t;
        track_cfg_t c = track_cfg(b);
        target_track_init(&t, &c);
        track_cluster_t k = target_track_find_cluster(&t, &map, now, span);
        const row_t *w = &want[b][pass];
        bool ok = (k.valid == w->have);
        if (ok && k.valid) {
            ok = fabsf(k.left_deg - w->left) < 0.01f && fabsf(k.right_deg - w->right) < 0.01f &&
                 fabsf(k.centre_deg - w->centre) < 0.006f && k.n_bins == w->n &&
                 fabsf(k.dist_cm - w->dist) < 0.051f && (int)k.edge == w->edge;
        }
        total[b]++;
        with_target[b] += w->have;
        matched[b] += ok;
        CHECK(ok);
        if (!ok) {
            printf("    %s pass %d bridge %d: C %s %.1f..%.1f n=%d d=%.1f edge=%d | "
                   "Python %s %.1f..%.1f n=%d d=%.1f edge=%d\n", scene, pass, b,
                   k.valid ? "yes" : "none", k.left_deg, k.right_deg, k.n_bins, k.dist_cm, k.edge,
                   w->have ? "yes" : "none", w->left, w->right, w->n, w->dist, w->edge);
        }
    }
}

static void run_scene(const char *name)
{
    char path[512];
    snprintf(path, sizeof path, SCENE_DIR "%s.txt", name);
    FILE *f = fopen(path, "r");
    CHECK(f != NULL);
    if (!f) return;
    CHECK(read_csv(name) == 0);
    scan_map_init(&map, (float)APP_SWEEP_STEP_DEG);

    char line[256];
    int pass = 0, n_in_pass = 0, n_total = 0;
    uint32_t t_first = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] != 'R') continue;
        unsigned t;
        char mode[16], dist[16], status[16];
        float a;
        if (sscanf(line, "R,%u,%15[^,],%f,%15[^,],%15s", &t, mode, &a, dist, status) != 5) {
            CHECK(!"bad R line");
            continue;
        }
        reading_status_t st = strcmp(status, "OK") == 0     ? READING_OK
                             : strcmp(status, "NOECHO") == 0 ? READING_NO_ECHO
                             : strcmp(status, "FAIL") == 0   ? READING_FAILED
                                                             : READING_NONE;
        CHECK(st != READING_NONE);
        CHECK((st == READING_OK) == (strcmp(dist, "-") != 0));      /* D-PROTO-NULL */
        float d = (st == READING_OK) ? strtof(dist, NULL) : 0.0f;
        if (n_in_pass == 0) t_first = t;
        scan_map_update(&map, a, d, st, t);
        n_in_pass++;
        n_total++;
        bool at_end = fabsf(a - APP_SWEEP_MIN_DEG) < 1e-3f || fabsf(a - APP_SWEEP_MAX_DEG) < 1e-3f;
        if (at_end && n_total > 1) {
            if (pass < MAX_PASSES) compare(name, pass, t, t - t_first);
            pass++;
            n_in_pass = 0;
        }
    }
    fclose(f);
    CHECK(n_in_pass == 0);                  /* every scene ends on a pass end */
}

static int by_name(const void *a, const void *b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

int main(void)
{
    printf("test_scenes (C target_track vs sim/scene.py on the S2 logs)\n");
    DIR *dir = opendir(SCENE_DIR);
    CHECK(dir != NULL);
    if (!dir) return TEST_RESULT();
    char *names[128];
    int n = 0;
    struct dirent *e;
    while ((e = readdir(dir)) != NULL && n < 128) {
        size_t len = strlen(e->d_name);
        if (len > 4 && strcmp(e->d_name + len - 4, ".txt") == 0) {
            names[n] = strndup(e->d_name, len - 4);
            n++;
        }
    }
    closedir(dir);
    qsort(names, (size_t)n, sizeof names[0], by_name);
    CHECK(n == 35);                         /* all S2 scenes present */
    for (int i = 0; i < n; i++) {
        run_scene(names[i]);
        free(names[i]);
    }
    for (int b = 0; b < 2; b++) {
        printf("  bridge %d: %d of %d passes match (%d with a cluster, %d with none)\n",
               b, matched[b], total[b], with_target[b], total[b] - with_target[b]);
    }
    printf("  scenes: %d\n", n);
    return TEST_RESULT();
}
