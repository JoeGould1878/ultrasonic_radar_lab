# Pure C (no ESP-IDF headers) — also built on the laptop by host_tests/
idf_component_register(
    SRCS "target_track.c"
    INCLUDE_DIRS "include"
    REQUIRES scan_map
)
