# Pure C (no ESP-IDF headers) — also built on the laptop by host_tests/
idf_component_register(
    SRCS "scan_map.c"
    INCLUDE_DIRS "include"
)
