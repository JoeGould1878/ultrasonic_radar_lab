/**
 * @file scan_map.c
 * @brief Scan map — implementation (S3, 27/11).
 *
 * Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
 * Credits / sources used: none (standard C only).
 *
 * Rules (scan_map.h):
 *  - bin i covers [i*bin_deg, (i+1)*bin_deg); bin = floor(angle / bin_deg),
 *    clamped; centre = (i + 0.5)*bin_deg; n_bins = ceil(180 / bin_deg).
 *  - A bin is "in date" while age <= max_age (the same rule here and in
 *    target_track_find_cluster): expire forgets only age > max_age.
 *  - An unmeasured bin has status READING_NONE, age UINT32_MAX, freshness 0.
 */
#include "scan_map.h"

#include <math.h>
#include <string.h>

/* The smallest bin that still fits 0-180 deg in SCAN_MAP_MAX_BINS (181).
 * Narrower bins would leave the top of the arc clamped into the last bin, so
 * they are raised to 1 deg. The sweep step is a whole number of degrees. */
#define MIN_BIN_DEG 1.0f

static void clear_bin(scan_map_t *m, int i)
{
    m->bins[i].dist_cm   = 0.0f;
    m->bins[i].status    = READING_NONE;
    m->bins[i].t_ms      = 0;
    m->bins[i].angle_deg = scan_map_bin_angle(m, i);
}

void scan_map_init(scan_map_t *m, float bin_deg)
{
    memset(m, 0, sizeof *m);
    if (!(bin_deg >= MIN_BIN_DEG)) {     /* also catches NaN and <= 0 */
        bin_deg = MIN_BIN_DEG;
    }
    if (bin_deg > 180.0f) {
        bin_deg = 180.0f;
    }
    m->bin_deg = bin_deg;
    m->n_bins  = (int)ceilf(180.0f / bin_deg);
    if (m->n_bins > SCAN_MAP_MAX_BINS) {
        m->n_bins = SCAN_MAP_MAX_BINS;
    }
    for (int i = 0; i < m->n_bins; i++) {
        clear_bin(m, i);
    }
}

int scan_map_bin(const scan_map_t *m, float angle_deg)
{
    float x = angle_deg / m->bin_deg;
    if (!(x >= 0.0f)) {                  /* negative or NaN */
        return 0;
    }
    if (x >= (float)m->n_bins) {         /* includes 180 deg itself */
        return m->n_bins - 1;
    }
    return (int)floorf(x);
}

float scan_map_bin_angle(const scan_map_t *m, int bin)
{
    return ((float)bin + 0.5f) * m->bin_deg;
}

void scan_map_update(scan_map_t *m, float angle_deg, float dist_cm,
                     reading_status_t status, uint32_t t_ms)
{
    scan_bin_t *b = &m->bins[scan_map_bin(m, angle_deg)];
    b->dist_cm   = dist_cm;
    b->status    = status;
    b->t_ms      = t_ms;
    b->angle_deg = angle_deg;
}

uint32_t scan_map_age_ms(const scan_map_t *m, int bin, uint32_t now_ms)
{
    if (bin < 0 || bin >= m->n_bins || m->bins[bin].status == READING_NONE) {
        return UINT32_MAX;
    }
    uint32_t t = m->bins[bin].t_ms;
    return now_ms >= t ? now_ms - t : 0;  /* a reading "from the future" is new */
}

float scan_map_freshness(const scan_map_t *m, int bin, uint32_t now_ms, uint32_t fade_ms)
{
    uint32_t age = scan_map_age_ms(m, bin, now_ms);
    if (age == UINT32_MAX || age >= fade_ms) {
        return (fade_ms == 0 && age == 0) ? 1.0f : 0.0f;
    }
    return 1.0f - (float)age / (float)fade_ms;
}

void scan_map_expire(scan_map_t *m, uint32_t now_ms, uint32_t max_age_ms)
{
    for (int i = 0; i < m->n_bins; i++) {
        uint32_t age = scan_map_age_ms(m, i, now_ms);
        if (age != UINT32_MAX && age > max_age_ms) {
            clear_bin(m, i);
        }
    }
}
