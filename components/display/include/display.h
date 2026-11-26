/**
 * @file display.h
 * @brief Thin drawing layer for an ON-DEVICE screen (via esp_lcd).
 *
 * Design and interface: Joe Gould, drafted with Claude (Anthropic)
 *
 * Only used if decision D-DISPLAY picks the kit's screen. It may turn out to
 * be a long character LCD (e.g. 16×2), which cannot draw a radar picture —
 * it could still show mode + live distance — in which case the radar is drawn
 * on a PC (USB) or a web page instead, and this component shrinks or goes.
 * Its controller and bus are unknown until the kit arrives. Everything above this file (radar_gfx,
 * display_task) only uses these few calls, so swapping the screen — or
 * dropping it for the PC / web viewer — touches this file only.
 *
 * Drawing strategy (decision D-REDRAW, Implement): redraw only the beam
 * line and changed bins each frame, not the full screen — a full SPI redraw
 * of 320×240 at 16-bit is ~150 kB per frame.
 */
#pragma once

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef uint16_t display_color_t;   /**< RGB565 */

#define DISPLAY_RGB565(r, g, b) \
    ((display_color_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))

esp_err_t display_init(void);
int  display_width(void);
int  display_height(void);

void display_fill(display_color_t c);
void display_pixel(int x, int y, display_color_t c);
void display_line(int x0, int y0, int x1, int y1, display_color_t c);
void display_circle(int cx, int cy, int r, display_color_t c, int filled);
void display_text(int x, int y, const char *s, display_color_t fg, display_color_t bg);

/** Push any buffered drawing to the panel. */
void display_flush(void);

void display_backlight(uint8_t level);

#ifdef __cplusplus
}
#endif
