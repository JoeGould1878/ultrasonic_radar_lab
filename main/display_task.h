/**
 * @file display_task.h
 * @brief Draws the radar at APP_DISPLAY_FPS from scan_task's map on whichever
 *        on-device display D-DISPLAY picks (may be none: PC / web viewer instead):
 *        range rings + labels, beam line, readings faded by age, mode name,
 *        live distance at the beam, STALE / FAULT banners, lock-on box.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 */
#pragma once
#include "esp_err.h"

esp_err_t display_task_start(void);
