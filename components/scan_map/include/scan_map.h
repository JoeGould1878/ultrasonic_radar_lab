/**
 * @file scan_map.h
 * @brief What the scanner currently "knows": the latest reading per angle bin,
 *        with its status and age. Pure C, no ESP-IDF.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * The display and the lock-on tracker both read from this map, so it is the
 * one place where "old vs new" and "echo vs no echo vs failed" are decided.
 * Bins are APP_SWEEP_STEP_DEG wide; the map is sized for 0–180°.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Three outcomes the display must keep apart (the brief asks this directly). */
typedef enum {
    READING_NONE = 0,   /**< bin never measured */
    READING_OK,         /**< echo received inside the range */
    READING_NO_ECHO,    /**< echo pulse ended at the timeout: nothing within range */
    READING_FAILED,     /**< echo never started / stuck high: sensor or wiring fault */
} reading_status_t;

#define SCAN_MAP_MAX_BINS 181

typedef struct {
    float            dist_cm;
    reading_status_t status;
    uint32_t         t_ms;      /**< when this bin was last written */
} scan_bin_t;

typedef struct {
    float      bin_deg;        /**< bin width */
    int        n_bins;
    scan_bin_t bins[SCAN_MAP_MAX_BINS];
} scan_map_t;

/** Clear the map. bin_deg in (0, 180]. */
void scan_map_init(scan_map_t *m, float bin_deg);

/** Angle -> bin index (clamped). */
int scan_map_bin(const scan_map_t *m, float angle_deg);

/** Bin index -> centre angle. */
float scan_map_bin_angle(const scan_map_t *m, int bin);

/** Store a reading in the bin for angle_deg (replaces the old one). */
void scan_map_update(scan_map_t *m, float angle_deg, float dist_cm,
                     reading_status_t status, uint32_t t_ms);

/** Age of a bin in ms (UINT32_MAX if never measured). */
uint32_t scan_map_age_ms(const scan_map_t *m, int bin, uint32_t now_ms);

/** 1.0 = just measured, falling linearly to 0.0 at fade_ms. Used for drawing. */
float scan_map_freshness(const scan_map_t *m, int bin, uint32_t now_ms, uint32_t fade_ms);

/** Forget bins older than max_age_ms (so removed objects disappear). */
void scan_map_expire(scan_map_t *m, uint32_t now_ms, uint32_t max_age_ms);

#ifdef __cplusplus
}
#endif
