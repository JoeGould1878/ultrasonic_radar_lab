/**
 * @file target_track.h
 * @brief Lock-on: find an object in the scan map, confirm it, follow it,
 *        and say when it is lost. Pure C, no ESP-IDF.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Why it works on clusters, not single pings: the HC-SR04 beam is ~15° wide,
 * so one object lights up several neighbouring bins at about the same
 * distance. The object's direction is taken as the MIDDLE of the cluster's
 * two edges, not the closest bin. Confirming over several sweeps stops one
 * noisy ping from causing a lock.
 *
 * Tested on the laptop with simulated scenes (sim/) and later with recorded
 * real scans (docs/evidence/logs/) — this is the main simulation activity.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "scan_map.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float    dist_tol_cm;      /**< neighbours within this are one object */
    int      min_bins;         /**< smallest cluster that counts */
    int      confirm_sweeps;   /**< seen this many passes running before lock */
    int      lost_pings;       /**< misses near the target before "lost" */
    float    max_range_cm;     /**< ignore readings beyond this */
} track_cfg_t;

typedef struct {
    bool  valid;
    float centre_deg;          /**< middle of the two edges */
    float left_deg, right_deg; /**< cluster edges */
    float dist_cm;             /**< median distance of the cluster */
} track_cluster_t;

typedef enum {
    TRACK_SEARCHING = 0,
    TRACK_CANDIDATE,           /**< seen, not yet confirmed */
    TRACK_LOCKED,
} track_state_t;

typedef struct {
    track_cfg_t     cfg;
    track_state_t   state;
    track_cluster_t target;
    int             seen_count;
    int             miss_count;
} target_track_t;

void target_track_init(target_track_t *t, const track_cfg_t *cfg);

/** Find the nearest valid cluster in the map (only bins newer than max_age_ms). */
track_cluster_t target_track_find_cluster(const target_track_t *t, const scan_map_t *m,
                                          uint32_t now_ms, uint32_t max_age_ms);

/** Call once per completed pass (FULL or SECTOR). Returns the new state. */
track_state_t target_track_on_pass(target_track_t *t, const scan_map_t *m,
                                   uint32_t now_ms, uint32_t max_age_ms);

/** Call after every ping while LOCKED, so a lost target is noticed quickly. */
track_state_t target_track_on_ping(target_track_t *t, float angle_deg, float dist_cm,
                                   reading_status_t status);

void target_track_reset(target_track_t *t);

#ifdef __cplusplus
}
#endif
