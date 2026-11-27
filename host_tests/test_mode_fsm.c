/**
 * @file test_mode_fsm.c
 * @brief Host tests for mode_fsm (S3). Written by Claude (Anthropic) for Joe Gould.
 *
 * Mode names must match the serial protocol (PLAN: SWEEP | LOCK | MANUAL).
 */
#include <string.h>
#include "mode_fsm.h"
#include "test_util.h"

static void test_cycle(void)
{
    printf("init and NEXT cycle\n");
    mode_fsm_t f;
    mode_fsm_init(&f);
    CHECK(f.mode == MODE_SWEEP);
    CHECK(!f.paused);
    CHECK(!f.fault);
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));
    CHECK(f.mode == MODE_LOCK);
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));
    CHECK(f.mode == MODE_MANUAL);
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));
    CHECK(f.mode == MODE_SWEEP);

    f.mode = (app_mode_t)7;                               /* corrupted: back to SWEEP */
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));
    CHECK(f.mode == MODE_SWEEP);
}

static void test_pause_fault(void)
{
    printf("pause and fault\n");
    mode_fsm_t f;
    mode_fsm_init(&f);
    CHECK(mode_fsm_handle(&f, MODE_EVT_PAUSE_TOGGLE));
    CHECK(f.paused);
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));            /* NEXT works while paused */
    CHECK(f.mode == MODE_LOCK);
    CHECK(f.paused);
    CHECK(mode_fsm_handle(&f, MODE_EVT_PAUSE_TOGGLE));
    CHECK(!f.paused);

    CHECK(mode_fsm_handle(&f, MODE_EVT_SENSOR_FAULT));
    CHECK(f.fault);
    CHECK(f.mode == MODE_LOCK);                           /* fault never changes the mode */
    CHECK(!mode_fsm_handle(&f, MODE_EVT_SENSOR_FAULT));   /* already in fault */
    CHECK(mode_fsm_handle(&f, MODE_EVT_NEXT));
    CHECK(f.fault);                                       /* NEXT keeps the fault */
    CHECK(mode_fsm_handle(&f, MODE_EVT_SENSOR_OK));
    CHECK(!f.fault);
    CHECK(!mode_fsm_handle(&f, MODE_EVT_SENSOR_OK));

    mode_fsm_t before = f;
    CHECK(!mode_fsm_handle(&f, MODE_EVT_NONE));
    CHECK(!mode_fsm_handle(&f, (mode_evt_t)99));
    CHECK(f.mode == before.mode && f.paused == before.paused && f.fault == before.fault);
}

static void test_names(void)
{
    printf("names match the serial protocol\n");
    CHECK(strcmp(mode_fsm_name(MODE_SWEEP), "SWEEP") == 0);
    CHECK(strcmp(mode_fsm_name(MODE_LOCK), "LOCK") == 0);
    CHECK(strcmp(mode_fsm_name(MODE_MANUAL), "MANUAL") == 0);
    CHECK(strcmp(mode_fsm_name(MODE_COUNT), "?") == 0);
    CHECK(strcmp(mode_fsm_name((app_mode_t)-1), "?") == 0);
}

int main(void)
{
    printf("test_mode_fsm\n");
    test_cycle();
    test_pause_fault();
    test_names();
    return TEST_RESULT();
}
