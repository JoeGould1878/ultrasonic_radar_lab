/**
 * @file main.c
 * @brief Start-up order only.
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 *
 * Planned order (PLAN.md task I10):
 *   1. servo_init -> park at 90°        (servo moves first, so power dips happen
 *   2. hcsr04_init                        before the sensor starts)
 *   3. joystick_init (stick at rest -> centre measured)
 *   4. scan_task_start (owns mode_fsm and serial_out, D-OWN), input_task_start
 *      (posts events to scan_task; never touches mode_fsm or serial_out)
 */
#include "esp_log.h"
#include "app_config.h"

static const char *TAG = "radar";

void app_main(void)
{
    ESP_LOGI(TAG, "skeleton: nothing implemented yet (see docs/PLAN.md)");
}
