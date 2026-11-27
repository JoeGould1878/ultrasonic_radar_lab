# Laptop tests for the pure-C components (no ESP32 needed).
#   make          build and run every test
#   make clean
# Each test_<name>.c is linked with components/<name>/<name>.c plus
# scan_map.c (most components use it). Add a name to TESTS when its test exists.

CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -g -O0
LDLIBS  := -lm
COMP    := ../components
BUILD   := build
INCS    := $(foreach c,scan_map sweep_plan target_track mode_fsm radar_gfx lock_loop,-I$(COMP)/$(c)/include)

# PLAN.md tasks S2/S3/I1 add: scan_map sweep_plan target_track mode_fsm radar_gfx
TESTS   := scan_map sweep_plan target_track

.PHONY: all run clean check-headers
all: check-headers run

$(BUILD):
	mkdir -p $(BUILD)

# Every pure component must compile without ESP-IDF
check-headers:
	@for c in scan_map sweep_plan target_track mode_fsm radar_gfx lock_loop; do \
	  $(CC) $(CFLAGS) -Wno-pedantic $(INCS) -fsyntax-only $(COMP)/$$c/$$c.c || exit 1; done
	@echo "Pure components compile on the laptop."

.SECONDEXPANSION:
$(BUILD)/test_%: test_%.c $$(COMP)/$$*/$$*.c $(COMP)/scan_map/scan_map.c | $(BUILD)
	$(CC) $(CFLAGS) $(INCS) $< $(sort $(COMP)/$*/$*.c $(COMP)/scan_map/scan_map.c) -o $@ $(LDLIBS)

run: $(addprefix $(BUILD)/test_,$(TESTS))
	@for t in $^; do echo "== $$t"; ./$$t || exit 1; done
	@echo "All host tests passed ($(words $(TESTS)) suites)."

clean:
	rm -rf $(BUILD)
