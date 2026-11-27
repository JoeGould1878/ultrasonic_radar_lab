/**
 * @file target_track.c
 * @brief Lock-on tracker — implementation (S3, 27/11).
 *
 * Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
 * Credits / sources used: none (standard C only). The cluster rule matches
 * sim/scene.py clusters_illustrative (S2), which test_scenes checks.
 *
 * Rules (the header leaves these open; items 2, 4 and 5 approved by Joe 27/11;
 * item 5's gated nearest-bearing choice added 27/11 with resweep fix (b)):
 *  1. A bin is usable when it is OK, no older than max_age_ms (age <= max),
 *     and its distance is <= max_range_cm (max_range_cm <= 0: no limit).
 *     Anything else (NO_ECHO, FAILED, never measured, too old, too far) is a
 *     non-OK bin.
 *  2. Clusters, bins in angle order: a usable bin joins the open cluster if
 *     at most bridge_gap_bins non-OK bins separate it from the cluster's last
 *     usable bin AND their distances differ by <= dist_tol_cm (compared with
 *     the LAST bin, as in S2). A usable bin at another distance closes the
 *     cluster and starts a new one: it is never bridged over. Bridged bins
 *     are not counted in n_bins.
 *  3. left/right = angle_deg of the first/last usable bin; centre = their
 *     middle; dist = upper median. Clusters with n_bins < min_bins are
 *     dropped. Nearest = smallest dist; a tie goes to the lower angle.
 *  4. edge: left <= lim_lo + bin_deg/2 or right >= lim_hi - bin_deg/2, i.e.
 *     the cluster includes a reading at (or past) a current sweep limit.
 *  5. on_pass: SEARCHING -> CANDIDATE on the nearest cluster.
 *     CANDIDATE and LOCKED (Joe 27/11, resweep fix (b)): only the clusters
 *     whose centre is within gate_deg of the candidate / target bearing
 *     count, and of those the one whose centre is NEAREST THAT BEARING is
 *     taken (not the nearest in distance: a closer object elsewhere in the
 *     arc must not win). CANDIDATE: one in the gate counts one more pass
 *     (LOCKED at confirm_sweeps); none in the gate -> restart the candidate
 *     from the nearest cluster; no cluster at all -> SEARCHING. LOCKED: one
 *     in the gate -> target updated, miss count reset; none in the gate ->
 *     lost (SEARCHING). confirm_sweeps <= 1 locks on the first pass.
 *     gate_deg is used as given (0 = exact match only; lock_loop substitutes
 *     sector_half_deg for 0). A bearing tie goes to the lower angle.
 *  6. on_ping (LOCKED only): a ping is "near" when its angle lies within the
 *     target's left..right. Near + OK + |dist - target dist| <= dist_tol is a
 *     hit and resets the misses; any other near ping is a miss.
 *     lost_pings misses in a row -> lost. Pings outside left..right are
 *     ignored. lost_pings < 1 counts as 1.
 *  7. Lost / reset: state SEARCHING, target.valid = false (the last target's
 *     numbers are kept for the display / lock_sim), counts 0. reset() also
 *     puts the limits back to the arc, as after init.
 */
#include "target_track.h"

#include <math.h>
#include <stddef.h>

#define EPS_DEG 1e-3f

static float clampf(float x, float lo, float hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

static bool usable(const target_track_t *t, const scan_map_t *m, int i,
                   uint32_t now_ms, uint32_t max_age_ms)
{
    const scan_bin_t *b = &m->bins[i];
    if (b->status != READING_OK || !(b->dist_cm == b->dist_cm)) {
        return false;
    }
    if (scan_map_age_ms(m, i, now_ms) > max_age_ms) {
        return false;
    }
    return t->cfg.max_range_cm <= 0.0f || b->dist_cm <= t->cfg.max_range_cm;
}

/* Members of a cluster = the usable bins in first..last (rule 2 means no
 * usable bin inside the range can belong to anything else). */
static track_cluster_t make_cluster(const target_track_t *t, const scan_map_t *m,
                                    int first, int last,
                                    uint32_t now_ms, uint32_t max_age_ms)
{
    float d[SCAN_MAP_MAX_BINS];
    int n = 0;
    for (int i = first; i <= last; i++) {
        if (!usable(t, m, i, now_ms, max_age_ms)) {
            continue;
        }
        float v = m->bins[i].dist_cm;          /* insertion sort, n <= 181 */
        int j = n++;
        while (j > 0 && d[j - 1] > v) {
            d[j] = d[j - 1];
            j--;
        }
        d[j] = v;
    }
    track_cluster_t c = {0};
    c.n_bins    = n;
    c.left_deg  = m->bins[first].angle_deg;
    c.right_deg = m->bins[last].angle_deg;
    c.centre_deg = 0.5f * (c.left_deg + c.right_deg);
    c.dist_cm   = (n > 0) ? d[n / 2] : 0.0f;   /* upper middle for even n */
    const float half = 0.5f * m->bin_deg;
    c.edge  = (c.left_deg <= t->lim_lo_deg + half) || (c.right_deg >= t->lim_hi_deg - half);
    int min_bins = t->cfg.min_bins < 1 ? 1 : t->cfg.min_bins;
    c.valid = (n >= min_bins);
    return c;
}

/* Which cluster a scan keeps (rule 3 / rule 5). */
typedef struct {
    bool  by_bearing;   /* false: smallest dist; true: centre nearest ref_deg */
    float ref_deg;      /*   ... and only centres within gate_deg of it */
    float gate_deg;
} pick_t;

static void keep_best(track_cluster_t *best, const track_cluster_t *c, const pick_t *pk)
{
    if (!c->valid) {
        return;
    }
    if (!pk->by_bearing) {
        if (!best->valid || c->dist_cm < best->dist_cm) {
            *best = *c;
        }
        return;
    }
    const float off = fabsf(c->centre_deg - pk->ref_deg);
    if (off <= pk->gate_deg &&
        (!best->valid || off < fabsf(best->centre_deg - pk->ref_deg))) {
        *best = *c;
    }
}

static track_cluster_t scan(const target_track_t *t, const scan_map_t *m,
                            uint32_t now_ms, uint32_t max_age_ms, const pick_t *pk)
{
    track_cluster_t best = {0};
    const int bridge = t->cfg.bridge_gap_bins < 0 ? 0 : t->cfg.bridge_gap_bins;
    bool open = false;
    int first = 0, last = 0, gap = 0;

    for (int i = 0; i < m->n_bins; i++) {
        if (usable(t, m, i, now_ms, max_age_ms)) {
            if (open && gap <= bridge &&
                fabsf(m->bins[i].dist_cm - m->bins[last].dist_cm) <= t->cfg.dist_tol_cm) {
                last = i;
                gap = 0;
                continue;
            }
            if (open) {
                track_cluster_t c = make_cluster(t, m, first, last, now_ms, max_age_ms);
                keep_best(&best, &c, pk);
            }
            open = true;
            first = last = i;
            gap = 0;
        } else if (open && ++gap > bridge) {
            track_cluster_t c = make_cluster(t, m, first, last, now_ms, max_age_ms);
            keep_best(&best, &c, pk);
            open = false;
        }
    }
    if (open) {
        track_cluster_t c = make_cluster(t, m, first, last, now_ms, max_age_ms);
        keep_best(&best, &c, pk);
    }
    return best;
}

track_cluster_t target_track_find_cluster(const target_track_t *t, const scan_map_t *m,
                                          uint32_t now_ms, uint32_t max_age_ms)
{
    const pick_t nearest = {.by_bearing = false};
    return scan(t, m, now_ms, max_age_ms, &nearest);
}

static void lose(target_track_t *t)
{
    t->state = TRACK_SEARCHING;
    t->target.valid = false;
    t->seen_count = 0;
    t->miss_count = 0;
}

void target_track_init(target_track_t *t, const track_cfg_t *cfg)
{
    t->cfg = *cfg;
    if (t->cfg.arc_min_deg > t->cfg.arc_max_deg) {
        float x = t->cfg.arc_min_deg;
        t->cfg.arc_min_deg = t->cfg.arc_max_deg;
        t->cfg.arc_max_deg = x;
    }
    t->target = (track_cluster_t){0};
    lose(t);
    t->lim_lo_deg = t->cfg.arc_min_deg;
    t->lim_hi_deg = t->cfg.arc_max_deg;
}

void target_track_set_limits(target_track_t *t, float lo_deg, float hi_deg)
{
    if (lo_deg > hi_deg) {
        float x = lo_deg;
        lo_deg = hi_deg;
        hi_deg = x;
    }
    t->lim_lo_deg = clampf(lo_deg, t->cfg.arc_min_deg, t->cfg.arc_max_deg);
    t->lim_hi_deg = clampf(hi_deg, t->cfg.arc_min_deg, t->cfg.arc_max_deg);
}

/* Rule 5: the cluster nearest the current bearing, within the gate. */
static track_cluster_t in_gate(const target_track_t *t, const scan_map_t *m,
                               uint32_t now_ms, uint32_t max_age_ms)
{
    const pick_t pk = {.by_bearing = true, .ref_deg = t->target.centre_deg,
                       .gate_deg = t->cfg.gate_deg};
    return scan(t, m, now_ms, max_age_ms, &pk);
}

static void start_candidate(target_track_t *t, const track_cluster_t *c)
{
    t->target = *c;
    t->seen_count = 1;
    t->miss_count = 0;
    t->state = (t->cfg.confirm_sweeps <= 1) ? TRACK_LOCKED : TRACK_CANDIDATE;
}

track_state_t target_track_on_pass(target_track_t *t, const scan_map_t *m,
                                   uint32_t now_ms, uint32_t max_age_ms)
{
    track_cluster_t c;
    switch (t->state) {
    case TRACK_SEARCHING:
        c = target_track_find_cluster(t, m, now_ms, max_age_ms);
        if (c.valid) {
            start_candidate(t, &c);
        }
        break;
    case TRACK_CANDIDATE:
        c = in_gate(t, m, now_ms, max_age_ms);
        if (c.valid) {
            t->target = c;
            if (++t->seen_count >= t->cfg.confirm_sweeps) {
                t->state = TRACK_LOCKED;
                t->miss_count = 0;
            }
            break;
        }
        c = target_track_find_cluster(t, m, now_ms, max_age_ms);
        if (c.valid) {
            start_candidate(t, &c);
        } else {
            lose(t);
        }
        break;
    case TRACK_LOCKED:
        c = in_gate(t, m, now_ms, max_age_ms);
        if (c.valid) {
            t->target = c;
            t->miss_count = 0;
        } else {
            lose(t);
        }
        break;
    }
    return t->state;
}

track_state_t target_track_on_ping(target_track_t *t, float angle_deg, float dist_cm,
                                   reading_status_t status)
{
    if (t->state != TRACK_LOCKED) {
        return t->state;
    }
    if (angle_deg < t->target.left_deg - EPS_DEG || angle_deg > t->target.right_deg + EPS_DEG) {
        return t->state;                       /* not looking at the target */
    }
    bool hit = (status == READING_OK) &&
               (t->cfg.max_range_cm <= 0.0f || dist_cm <= t->cfg.max_range_cm) &&
               fabsf(dist_cm - t->target.dist_cm) <= t->cfg.dist_tol_cm;
    if (hit) {
        t->miss_count = 0;
    } else {
        int lost_pings = t->cfg.lost_pings < 1 ? 1 : t->cfg.lost_pings;
        if (++t->miss_count >= lost_pings) {
            lose(t);
        }
    }
    return t->state;
}

void target_track_reset(target_track_t *t)
{
    lose(t);
    t->lim_lo_deg = t->cfg.arc_min_deg;
    t->lim_hi_deg = t->cfg.arc_max_deg;
}
