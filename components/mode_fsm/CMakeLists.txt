# Pure C (no ESP-IDF headers) — also built on the laptop by host_tests/
idf_component_register(
    SRCS "mode_fsm.c"
    INCLUDE_DIRS "include"
)
