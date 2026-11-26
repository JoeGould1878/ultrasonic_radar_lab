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
 *
 * Changes in S3 (26/11, approved by Joe):
 *  - edge flag (D-EDGE): a cluster touching the CURRENT sweep limits (the arc
 *    ends in a full sweep, the sector edges in LOCK) has had part of its smear
 *    cut off, so its edge midpoint is pulled inward (S2: ~4.5 deg at 15/165).
 *    It is flagged and its bearing reported as low confidence, not held to
 *    SC3's +/-5 deg. arc_min/max_deg give the default limits;
 *    target_track_set_limits() narrows them while sweeping a sector.
 *  - bridge_gap_bins: a PROPOSED rule (APP_LOCK_BRIDGE_BINS, default 0 = off)
 *    that lets a cluster continue across this many non-OK bins. S2 showed one
 *    dropout splitting a smear in two (worst bearing error 6 deg). Stays 0
 *    until Joe approves it on the with/without evidence.
 *  - gate_deg: how far a cluster's centre may move between passes and still
 *    count as the same object (confirming a candidate, following a lock).
 *    Needed because the header had no association rule; lock_loop sets it to
 *    APP_LOCK_SECTOR_HALF_DEG.
 *  - Bearings use scan_bin_t.angle_deg (the exact reading angle), not bin
 *    centres.
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
    float    arc_min_deg;      /**< full-sweep limits (APP_SWEEP_MIN/MAX_DEG): */
    float    arc_max_deg;      /**<   a cluster touching them is flagged edge */
    int      bridge_gap_bins;  /**< bridge up to this many non-OK bins (0 = off) */
    float    gate_deg;         /**< max centre move between passes, same object */
} track_cfg_t;

typedef struct {
    bool  valid;
    float centre_deg;          /**< middle of the two edges */
    float left_deg, right_deg; /**< cluster edges */
    float dist_cm;             /**< median distance of the cluster (upper
                                    middle value when the count is even) */
    int   n_bins;              /**< OK bins in the cluster */
    bool  edge;                /**< touches the current sweep limits: bearing
                                    is low confidence (D-EDGE) */
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
    float           lim_lo_deg;    /**< current sweep limits (edge flag) */
    float           lim_hi_deg;
} target_track_t;

/** Also sets the current limits to cfg->arc_min_deg .. arc_max_deg. */
void target_track_init(target_track_t *t, const track_cfg_t *cfg);

/** Current sweep limits, used for the edge flag: the sector while sweeping a
 *  sector in LOCK, the arc otherwise. Clamped to the arc. */
void target_track_set_limits(target_track_t *t, float lo_deg, float hi_deg);

/** Find the nearest valid cluster in the map (only bins newer than max_age_ms).
 *  Bins are read in angle order; neighbours join a cluster if both are OK
 *  and their distances differ by <= dist_tol_cm, or if they are separated
 *  by at most bridge_gap_bins non-OK bins. */
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
