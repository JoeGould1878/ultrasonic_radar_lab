/**
 * @file main.c
 * @brief Start-up order only.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 *
 * Planned order (PLAN.md task I10):
 *   1. servo_init -> park at 90°        (servo moves first, so power dips happen
 *   2. hcsr04_init                        before the screen and sensor start)
 *   3. joystick_init (stick at rest -> centre measured)
 *   4. display_init -> splash with mode name
 *   5. scan_task_start, input_task_start, display_task_start
 */
#include "esp_log.h"
#include "app_config.h"

static const char *TAG = "radar";

void app_main(void)
{
    ESP_LOGI(TAG, "skeleton: nothing implemented yet (see docs/PLAN.md)");
}
