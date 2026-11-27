#!/usr/bin/env python3
"""
Tests for tools/radar_model.py (S4): the line parser and the age / fade /
expiry / STALE logic of the PC radar view. No pygame, no display.

Implementation: Claude (Anthropic), for Joe Gould. No code adapted.

Lines come from the S2 scene logs in docs/evidence/sim/s2_scenes/, plus
malformed versions of them (cut short, glued together, D-PROTO-NULL broken),
since those are what a real serial port produces when it is opened mid-line.
Expected numbers are worked out from main/app_config.h, never typed in, so
the tests follow the config.

RUN   python tools/test_radar_view.py        (plain asserts)
      python -m pytest tools/test_radar_view.py   (if pytest is installed)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_model import (BadLine, DeviceClock, ModeMsg, RadarState, Reading,  # noqa: E402
                         TrackMsg, ViewConfig, parse_line)

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "docs" / "evidence" / "sim" / "s2_scenes"
CFG = ViewConfig.load()


def scene_lines(name: str) -> list[str]:
    return (SCENES / f"{name}.txt").read_text().splitlines(keepends=True)


def bad(line: str) -> bool:
    try:
        parse_line(line)
    except BadLine:
        return True
    return False


def feed_all(lines, until_ms=None) -> RadarState:
    st = RadarState(CFG)
    for ln in lines:
        msg = st.feed_line(ln)
        if until_ms is not None and msg is not None and msg.t_ms > until_ms:
            break
    return st


# ------------------------------------------------------------ config ----
def test_config_from_header():
    # D-FADE: fade and expiry are whole passes of the S1 pass time
    assert CFG.pass_ms > 0
    assert math.isclose(CFG.fade_ms / CFG.pass_ms, round(CFG.fade_ms / CFG.pass_ms))
    assert CFG.min_deg < 90 < CFG.max_deg
    # S2 logs are generated from the same config: their pass is the same length
    r = [parse_line(x) for x in scene_lines("empty")]
    r = [m for m in r if isinstance(m, Reading)]
    n_per_pass = round((CFG.max_deg - CFG.min_deg) / CFG.step_deg)
    assert math.isclose(r[n_per_pass].t_ms - r[0].t_ms, CFG.pass_ms)


# ------------------------------------------------------------ parser ----
def test_parse_real_lines():
    assert parse_line("R,0,SWEEP,15.0,-,NOECHO\n") == Reading(0, "SWEEP", 15.0, None, "NOECHO")
    assert parse_line("M,0,SWEEP,0,0") == ModeMsg(0, "SWEEP", False, False)
    ok = [ln for ln in scene_lines("t1_b90_r50") if ln.endswith(",OK\n")][0]
    r = parse_line(ok)
    assert r.status == "OK" and r.dist is not None and 0 < r.dist <= CFG.max_range_cm
    fail = [ln for ln in scene_lines("t1_fault") if ln.endswith(",FAIL\n")][0]
    r = parse_line(fail)
    assert r.status == "FAIL" and r.dist is None


def test_crlf_and_spaces():
    assert parse_line("R,60,SWEEP,17.0,-,NOECHO\r\n") == Reading(60, "SWEEP", 17.0, None, "NOECHO")
    assert parse_line("  M,5,LOCK,1,1  \r\n") == ModeMsg(5, "LOCK", True, True)


def test_not_protocol_is_ignored_not_bad():
    for ln in ["", "\n", "# S2 scene t1_fault (T-FAULT) seed=0",
               "I (1234) scan_task: started", "E (99) hcsr04: timeout",
               ",SWEEP,90.0,52.3,OK",          # head lost
               "1234,SWEEP,90.0,52.3,OK",      # head lost
               "\x00\xffR,0,SWEEP,15.0,-,NOECHO",  # garbage on connect
               "RX buffer", "Reading 3"]:
        assert parse_line(ln) is None, ln


def test_malformed_is_bad():
    full = "R,1260,SWEEP,57.0,-,NOECHO"
    for cut in range(2, len(full)):            # every truncation of a real line
        assert bad(full[:cut]), full[:cut]
    for ln in [
        "R,1260,SWEEP,57.0,-,NOECHOR,1320,SWEEP,59.0,-,NOECHO",  # two lines glued
        "R,0,SWEEP,15.0,0.0,NOECHO",           # D-PROTO-NULL: number for NOECHO
        "R,0,SWEEP,15.0,0,FAIL",               # D-PROTO-NULL: number for FAIL
        "R,0,SWEEP,90.0,-,OK",                 # OK without a distance
        "R,0,SWEEP,90.0,nan,OK", "R,0,SWEEP,inf,52.3,OK",
        "R,0,SWEEP,90.0,-3.0,OK",              # negative distance
        "R,0,SWEEP,190.0,52.3,OK",             # outside the servo range
        "R,-5,SWEEP,90.0,52.3,OK", "R,1.5,SWEEP,90.0,52.3,OK",
        "R,0,sweep,90.0,52.3,OK", "R,0,SWEEP,90.0,52.3,ok", "R,0,SCAN,90.0,52.3,OK",
        "M,0,SWEEP,0", "M,0,SWEEP,2,0", "M,0,SWEEP,0,yes",
        "T,0,LOCK,90.0,85.0,95.0", "T,0,LOCKED,90.0,85.0,95.0,50.0,0",
        "T,0,LOCK,90.0,85.0,95.0,50.0",        # old 7-field T line: bad since the edge field
        "T,0,LOCK,90.0,85.0,95.0,50.0,2", "T,0,LOCK,90.0,85.0,95.0,50.0,",
        "T,0,SEARCH,90.0,-,-,-,0",             # SEARCH must be all "-"
        "T,0,LOCK,-,-,-,-,0", "T,0,CAND,90.0,85.0,95.0,-,0",
    ]:
        assert bad(ln), ln


def test_track_lines():
    assert parse_line("T,9000,LOCK,90.5,84.0,97.0,50.2,0") == TrackMsg(9000, "LOCK", 90.5, 84.0, 97.0, 50.2, False)
    assert parse_line("T,9000,LOCK,163.0,157.0,165.0,50.2,1").edge is True      # D-EDGE
    assert parse_line("T,9000,CAND,90.5,84.0,97.0,50.2,0").state == "CAND"
    assert parse_line("T,9000,SEARCH,-,-,-,-,0") == TrackMsg(9000, "SEARCH", None, None, None, None, False)


def test_real_logs_parse_cleanly():
    for path in sorted(SCENES.glob("*.txt")):
        st = feed_all(path.read_text().splitlines())
        assert st.counts["bad"] == 0, (path.name, st.last_bad)
        assert st.counts["ignored"] == 1, path.name   # the "# S2 scene" line
        assert st.counts["M"] == 1 and st.counts["R"] > 0


def test_t1_fault_counts_and_bad_lines_are_skipped():
    lines = scene_lines("t1_fault")
    st = feed_all(lines)
    n_r = sum(ln.startswith("R,") for ln in lines)
    n_fail = sum(ln.endswith(",FAIL\n") for ln in lines)
    assert st.counts["R"] == n_r and n_fail > 0
    # now with damage mixed in: same picture, damage counted
    noisy = []
    for i, ln in enumerate(lines):
        noisy.append(ln)
        if i % 50 == 10:
            noisy += [ln[: len(ln) // 2], "I (1) wifi: hello\n", "R,1,SWEEP,90.0,0.0,NOECHO\n"]
    st2 = feed_all(noisy)
    assert st2.counts["R"] == st.counts["R"]
    assert st2.counts["bad"] == 2 * sum(1 for i in range(len(lines)) if i % 50 == 10)
    assert {k: (r.status, r.dist) for k, r in st2.bins.items()} == \
           {k: (r.status, r.dist) for k, r in st.bins.items()}


# ------------------------------------------------- age / fade / expiry ----
def test_fade_is_linear_in_passes():
    st = RadarState(CFG)
    r = Reading(1000, "SWEEP", 90.0, 50.0, "OK")
    st.feed(r)
    n = CFG.fade_ms / CFG.pass_ms
    assert st.freshness(r, 1000) == 1.0
    assert math.isclose(st.freshness(r, 1000 + CFG.pass_ms), 1 - 1 / n)
    assert math.isclose(st.freshness(r, 1000 + 2 * CFG.pass_ms), 1 - 2 / n)
    assert st.freshness(r, 1000 + CFG.fade_ms) == 0.0
    assert st.freshness(r, 1000 + 10 * CFG.fade_ms) == 0.0
    assert st.freshness(r, 500) == 1.0          # "now" before t: never > 1


def test_s1_redraw_brightness_from_real_log():
    """D-FADE / S1: mid-arc bins are re-measured after ~1 pass (67 %), end bins
    after ~2 passes (33 %). Check it on the S2 log of a tube at 90 deg."""
    n = CFG.fade_ms / CFG.pass_ms
    st = RadarState(CFG)
    seen: dict[int, Reading] = {}
    at_redraw: dict[int, list[float]] = {}
    for ln in scene_lines("t1_b90_r50"):
        msg = parse_line(ln)
        if not isinstance(msg, Reading):
            continue
        k = st.bin_of(msg.angle)
        if k in seen:
            at_redraw.setdefault(k, []).append(st.freshness(seen[k], msg.t_ms))
        seen[k] = msg
        st.feed(msg)
    mid_k = min(at_redraw, key=lambda k: abs(seen[k].angle - 90.0))   # sweep is on odd degrees
    mid = at_redraw[mid_k]
    end = at_redraw[st.bin_of(CFG.min_deg)]
    # the middle bin is revisited every ~pass, the end bin every 2 passes
    assert all(abs(f - (1 - 1 / n)) < 0.01 for f in mid), mid
    assert all(abs(f - (1 - 2 / n)) < 0.01 for f in end), end


def test_expiry_after_expire_sweeps():
    st = RadarState(CFG)
    st.feed(Reading(0, "SWEEP", 90.0, 50.0, "OK"))
    st.feed(Reading(0, "SWEEP", 30.0, None, "NOECHO"))
    assert st.expire(CFG.expire_ms) == 0 and len(st.bins) == 2
    assert st.expire(CFG.expire_ms + 1) == 2 and not st.bins


def test_one_mark_per_bin_newest_wins():
    st = RadarState(CFG)
    st.feed(Reading(0, "SWEEP", 90.0, 50.0, "OK"))
    st.feed(Reading(4500, "SWEEP", 90.0, None, "NOECHO"))     # object removed
    assert len(st.bins) == 1 and st.bins[st.bin_of(90.0)].status == "NOECHO"


def test_bins_match_scan_map():
    """scan_map.h: bin = floor(angle / step), clamped; every sweep angle has
    its own bin (a bug with round(): 87 and 89 deg shared one)."""
    st = RadarState(CFG)
    grid, a = [], CFG.min_deg
    while a <= CFG.max_deg:
        grid.append(a)
        a += CFG.step_deg
    assert len({st.bin_of(a) for a in grid}) == len(grid)
    assert st.bin_of(0.0) == 0 and st.bin_of(180.0) == st.bin_of(179.9)
    assert st.bin_of(89.0) == st.bin_of(88.0) != st.bin_of(87.9)


def test_t1_removed_dot_is_replaced_within_a_pass():
    """SC5 through the viewer: after the tube goes, the 90 deg bin turns NOECHO
    at the next visit, not only when it expires."""
    lines = scene_lines("t1_removed")
    st = feed_all(lines)
    near = [r for r in st.bins.values() if abs(r.angle - 90.0) <= 3 * CFG.step_deg]
    assert near and all(r.status == "NOECHO" for r in near)


def test_stale():
    st = RadarState(CFG)
    assert st.is_stale(None) and st.is_stale(0)               # nothing yet
    st.feed(ModeMsg(0, "SWEEP", False, False))
    assert st.is_stale(10)                                     # M only, no R
    st.feed(Reading(1000, "SWEEP", 90.0, 50.0, "OK"))
    assert not st.is_stale(1000 + CFG.stale_ms)
    assert st.is_stale(1000 + CFG.stale_ms + 1)
    assert st.is_stale(1001, link_up=False)                    # port dropped


def test_paused_is_not_stale_while_m_lines_keep_coming():
    """Joe 27/11: STALE = no line of ANY kind for STALE_MS; paused firmware
    sends an M line every 1 s, so PAUSED shows and STALE does not."""
    st = RadarState(CFG)
    st.feed(ModeMsg(0, "SWEEP", False, False))
    st.feed(Reading(1000, "SWEEP", 90.0, 50.0, "OK"))
    st.feed(ModeMsg(1200, "SWEEP", True, False))               # pause
    assert st.paused
    for t in (2200, 3200, 4200):                               # M every 1 s, no R
        st.feed(ModeMsg(t, "SWEEP", True, False))
        assert not st.is_stale(t + 900)                        # 0.9 s after the last M
    assert not st.is_stale(4200 + CFG.stale_ms)
    assert st.is_stale(4200 + CFG.stale_ms + 1)                # lines stop (cable out): STALE
    # not paused: an M line does not hide a missing R stream? it does count as a line:
    st2 = RadarState(CFG)
    st2.feed(Reading(0, "SWEEP", 90.0, 50.0, "OK"))
    st2.feed(ModeMsg(1000, "SWEEP", False, False))
    assert not st2.is_stale(1000 + CFG.stale_ms)
    assert st2.is_stale(1000 + CFG.stale_ms + 1)
    # paused before any R line: PAUSED, not "no data yet"
    st3 = RadarState(CFG)
    st3.feed(ModeMsg(0, "SWEEP", True, False))
    assert not st3.is_stale(500)


def test_lock_bracket_rules():
    """Joe 27/11: bracket only when mode = LOCK and T state = LOCK; hidden when
    no T line for 2 full passes."""
    st = RadarState(CFG)
    lock_t = TrackMsg(10000, "LOCK", 90.0, 85.0, 95.0, 50.0, False)
    st.feed(Reading(10000, "LOCK", 90.0, 50.0, "OK"))
    st.feed(lock_t)
    assert st.lock_bracket(10000) is None                      # no M line yet: mode unknown
    st.feed(ModeMsg(10000, "SWEEP", False, False))
    assert st.lock_bracket(10000) is None                      # mode SWEEP
    st.feed(ModeMsg(10000, "LOCK", False, False))
    assert st.lock_bracket(10000) is lock_t
    hide = 2 * CFG.pass_ms
    assert st.lock_bracket(10000 + hide) is lock_t
    assert st.lock_bracket(10000 + hide + 1) is None           # 2 passes with no T line
    st.feed(TrackMsg(20000, "CAND", 90.0, 85.0, 95.0, 50.0, False))
    assert st.lock_bracket(20000) is None                      # CAND: no bracket
    st.feed(TrackMsg(20100, "SEARCH", None, None, None, None, False))
    assert st.lock_bracket(20100) is None
    assert st.lock_bracket(None) is None


def test_t1_fault_flags():
    st = RadarState(CFG)
    st.feed(ModeMsg(0, "SWEEP", False, True))
    assert st.fault
    st.feed(ModeMsg(10, "SWEEP", True, False))
    assert not st.fault and st.paused


def test_restart_clears_map():
    st = RadarState(CFG)
    st.feed(Reading(60000, "SWEEP", 90.0, 50.0, "OK"))
    st.feed(TrackMsg(59990, "LOCK", 90.0, 85.0, 95.0, 50.0, False))  # slightly older: fine
    assert st.counts["restarts"] == 0 and st.track is not None
    st.feed(Reading(0, "SWEEP", 15.0, None, "NOECHO"))         # device rebooted
    assert st.counts["restarts"] == 1 and list(st.bins) == [st.bin_of(15.0)] and st.track is None


def test_device_clock():
    wall = [100.0]
    c = DeviceClock(speed=2.0, wall=lambda: wall[0])
    assert c.now_ms() is None
    c.sync(1000)
    wall[0] += 0.5
    assert c.now_ms() == 2000                  # 0.5 s wall at 2x = 1000 ms
    c.sync(1500)                               # late line: clock doesn't go back
    assert c.now_ms() == 2000
    c.sync(0, restarted=True)
    assert c.now_ms() == 0


def _run():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print(f"ok  {n}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
