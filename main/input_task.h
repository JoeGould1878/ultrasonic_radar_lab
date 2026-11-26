/**
 * @file input_task.h
 * @brief Polls the joystick and its push switch every APP_INPUT_POLL_MS.
 *        Short press -> next mode; long press -> pause/resume;
 *        in MANUAL, stick X -> target angle (rate or position control, D-JOY).
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 */
#pragma once
#include "esp_err.h"

esp_err_t input_task_start(void);
