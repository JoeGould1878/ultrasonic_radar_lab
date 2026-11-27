/**
 * @file scan_task.h
 * @brief Owns the servo, the ultrasonic sensor, mode_fsm and ALL serial output
 *        (D-OWN). One loop: drain the event queue (mode_fsm_handle, M line on any
 *        change) -> ask sweep_plan for the next angle -> move -> settle -> ping ->
 *        store in scan_map -> R (and T) line -> wait out the ping gap.
 *        While paused it sends an M line every 1 s (heartbeat).
 *
 * Design: Joe Gould, drafted with Claude (Anthropic)
 *
 * Proposed (D-ANGLE-TAG, to confirm with S1/T-MATCH): the reading is tagged with the angle the servo was commanded to BEFORE the
 * ping (after settling) — fixes the angle/reading mismatch in the previous
 * prototype, where the servo kept moving every 20 ms but pinged every 50 ms.
 * In MODE_LOCK it also runs target_track; in MODE_MANUAL it takes the
 * target angle from input_task.
 *
 * D-OWN: scan_task is the only caller of mode_fsm and serial_out. input_task
 * and scan_task would both have fed mode_fsm (press events vs SENSOR_FAULT/OK)
 * and both could write serial; one owner needs no shared FSM state and no mutex.
 */
#pragma once
#include "esp_err.h"
#include "app_types.h"

esp_err_t scan_task_start(void);

/** Post a mode event (input_task: MODE_EVT_NEXT / MODE_EVT_PAUSE_TOGGLE).
 *  Non-blocking, safe from any task. Goes into a FreeRTOS queue of length
 *  APP_INPUT_EVT_QUEUE_LEN; when it is full the event is dropped and counted.
 *  scan_task drains the queue at the top of each loop. */
void scan_task_post_event(mode_evt_t evt);

/** Joystick target for MODE_MANUAL. */
void scan_task_set_manual(float target_deg);
