/**
 * @file radar_gfx.h
 * @brief Screen-size-independent geometry for the radar picture. Pure C.
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Turns (angle, distance) into pixel positions for whatever screen the kit
 * is chosen (D-DISPLAY), and picks how each reading is drawn. Kept apart from
 * any driver so it can be tested on the laptop; the PC/web viewers follow
 * the same rules.
 *
 * Proposed accessibility rule (D-STATUS; brief: "without relying solely on
 * colour"): every status has its own SHAPE as well as colour —
 *   OK       = filled dot     NO_ECHO = nothing drawn (beam line only)
 *   FAILED   = small cross    stale   = hollow ring + "STALE" text
 */
#pragma once

#include <stdint.h>
#include "scan_map.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int   width, height;     /**< screen size in pixels */
    int   origin_x, origin_y;/**< sensor position on screen (bottom centre) */
    float px_per_cm;         /**< scale: max range fits the screen */
} radar_geom_t;

typedef enum {
    MARK_NONE = 0,
    MARK_DOT,
    MARK_CROSS,
    MARK_RING,
} radar_mark_t;

/** Fit a half-disc of max_range_cm onto the screen, leaving margin_px. */
void radar_gfx_fit(radar_geom_t *g, int width, int height, float max_range_cm, int margin_px);

/** Polar -> screen. 90° points straight up the screen. */
void radar_gfx_to_xy(const radar_geom_t *g, float angle_deg, float dist_cm, int *x, int *y);

/** How to draw a bin, and how bright (0–255) given its freshness 0..1. */
radar_mark_t radar_gfx_mark(reading_status_t status, float freshness, uint8_t *brightness);

#ifdef __cplusplus
}
#endif
