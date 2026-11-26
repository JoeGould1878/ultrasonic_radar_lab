idf_component_register(
    SRCS
        "main.c"
        "scan_task.c"
        "input_task.c"
        "display_task.c"
        "serial_out.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        hcsr04 servo joystick button display
        scan_map sweep_plan target_track mode_fsm radar_gfx
        esp_timer
)
