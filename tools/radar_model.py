#!/usr/bin/env python3
"""
S4: the radar view's model: config, line parser, display state, device clock.
Pure Python (no pygame), so tools/test_radar_view.py tests it headless.

Implementation: Claude (Anthropic), for Joe Gould, to the Display spec in
docs/PLAN.md. No code adapted.

NUMBERS  Every display number comes from main/app_config.h through
       sim/appcfg.py at start-up (arc, max range, fade, expiry, STALE time, the
       20 fps floor). The pass time that "age in passes" needs comes from the
       S1 timing model (sim/sweep_timing.py) on the same config, so it is the
       pass time the firmware is designed to (4.5 s today). Not copied here.

PARSING  parse_line() never raises anything but BadLine. A line that does not
       start with "R,", "M," or "T," is not protocol (ESP-IDF log, "# ..."
       comment, a line whose head was lost): counted as "ignored". A line that
       starts like one but is malformed (wrong field count, bad number, unknown
       status, a number in dist_cm for NOECHO/FAIL, "-" for OK) is counted as
       "bad". Both are skipped; neither stops the view.

CLOCK  "Now" is device time: the t_ms of the latest line plus wall time since
       it arrived (x --speed on replay). Ages, fading, expiry and STALE all use
       it, so live, replay and sim behave identically and a replay at --speed 4
       fades 4x faster in wall time but identically per pass.
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))
from appcfg import CONFIG_H, parse_config  # noqa: E402
import sweep_timing  # noqa: E402  (sets matplotlib to Agg; the view draws with pygame)

NEEDED = sweep_timing.NEEDED + [
    "APP_EXPIRE_SWEEPS", "APP_STALE_MS", "APP_DISPLAY_FPS",
]

MODES = ("SWEEP", "LOCK", "MANUAL")
STATUSES = ("OK", "NOECHO", "FAIL")
TRACK_STATES = ("SEARCH", "CAND", "LOCK")
NULL = "-"  # D-PROTO-NULL


# ------------------------------------------------------------ config ----
@dataclass(frozen=True)
class ViewConfig:
    min_deg: float
    max_deg: float
    step_deg: float
    max_range_cm: float
    pass_ms: float
    fade_ms: float
    expire_ms: float
    stale_ms: float
    floor_fps: float

    @classmethod
    def load(cls, path: Path = CONFIG_H) -> "ViewConfig":
        cfg = parse_config(path, NEEDED)
        model = sweep_timing.Model(cfg)
        args = (cfg["APP_SWEEP_STEP_DEG"], cfg["APP_US_PING_GAP_MS"],
                cfg["APP_US_MAX_RANGE_CM"], "stop-and-ping")   # D-SCAN
        pass_ms = model.pass_s(*args) * 1000.0
        return cls(
            min_deg=cfg["APP_SWEEP_MIN_DEG"], max_deg=cfg["APP_SWEEP_MAX_DEG"],
            step_deg=cfg["APP_SWEEP_STEP_DEG"], max_range_cm=cfg["APP_US_MAX_RANGE_CM"],
            pass_ms=pass_ms,
            fade_ms=cfg["APP_FADE_SWEEPS"] * pass_ms,
            expire_ms=cfg["APP_EXPIRE_SWEEPS"] * pass_ms,
            stale_ms=cfg["APP_STALE_MS"],
            floor_fps=cfg["APP_DISPLAY_FPS"],
        )


# ------------------------------------------------------------ parser ----
class BadLine(ValueError):
    """A line that starts like R/M/T but is malformed."""


@dataclass(frozen=True)
class Reading:
    t_ms: int
    mode: str
    angle: float
    dist: float | None      # None for NOECHO / FAIL (D-PROTO-NULL)
    status: str


@dataclass(frozen=True)
class ModeMsg:
    t_ms: int
    mode: str
    paused: bool
    fault: bool


@dataclass(frozen=True)
class TrackMsg:
    t_ms: int
    state: str
    centre: float | None    # "-" accepted for SEARCH (open question in PLAN)
    left: float | None
    right: float | None
    dist: float | None


def _t(s: str) -> int:
    if not s.isdigit():
        raise BadLine(f"t_ms {s!r}")
    return int(s)


def _num(s: str, what: str) -> float:
    try:
        v = float(s)
    except ValueError:
        raise BadLine(f"{what} {s!r}") from None
    if not math.isfinite(v):
        raise BadLine(f"{what} {s!r}")
    return v


def _num_or_null(s: str, what: str) -> float | None:
    return None if s == NULL else _num(s, what)


def _flag(s: str, what: str) -> bool:
    if s not in ("0", "1"):
        raise BadLine(f"{what} {s!r}")
    return s == "1"


def _one_of(s: str, allowed: tuple, what: str) -> str:
    if s not in allowed:
        raise BadLine(f"{what} {s!r}")
    return s


def parse_line(line: str) -> Reading | ModeMsg | TrackMsg | None:
    """One protocol line -> message. None = not a protocol line (ignore it).
    Raises BadLine (only) for a line that starts with R, / M, / T, but is
    malformed. Never raises anything else, whatever the input."""
    s = line.strip()
    if len(s) < 2 or s[0] not in "RMT" or s[1] != ",":
        return None
    f = s.split(",")
    kind = f[0]
    if kind == "R":
        if len(f) != 6:
            raise BadLine(f"R needs 6 fields, got {len(f)}")
        t = _t(f[1])
        mode = _one_of(f[2], MODES, "mode")
        angle = _num(f[3], "angle")
        if not 0.0 <= angle <= 180.0:
            raise BadLine(f"angle {angle} outside the servo's 0..180")
        status = _one_of(f[5], STATUSES, "status")
        if status == "OK":
            if f[4] == NULL:
                raise BadLine("OK reading with no distance")
            dist = _num(f[4], "dist_cm")
            if dist < 0:
                raise BadLine(f"negative dist_cm {dist}")
        else:
            if f[4] != NULL:      # D-PROTO-NULL: never a number
                raise BadLine(f"{status} with dist_cm {f[4]!r}, expected '-'")
            dist = None
        return Reading(t, mode, angle, dist, status)
    if kind == "M":
        if len(f) != 5:
            raise BadLine(f"M needs 5 fields, got {len(f)}")
        return ModeMsg(_t(f[1]), _one_of(f[2], MODES, "mode"),
                       _flag(f[3], "paused"), _flag(f[4], "fault"))
    # kind == "T"
    if len(f) != 7:
        raise BadLine(f"T needs 7 fields, got {len(f)}")
    return TrackMsg(_t(f[1]), _one_of(f[2], TRACK_STATES, "state"),
                    _num_or_null(f[3], "centre_deg"), _num_or_null(f[4], "left_deg"),
                    _num_or_null(f[5], "right_deg"), _num_or_null(f[6], "dist_cm"))


def line_t_ms(line: str) -> int | None:
    """t_ms of a well-formed protocol line, else None (for replay pacing)."""
    try:
        msg = parse_line(line)
    except BadLine:
        return None
    return msg.t_ms if msg is not None else None


# ------------------------------------------------------------- state ----
class RadarState:
    """What the display knows: one reading per bin, mode flags, lock state.
    Pure logic, no drawing, so it is tested on its own."""

    def __init__(self, cfg: ViewConfig):
        self.cfg = cfg
        self.bins: dict[int, Reading] = {}
        self.latest: Reading | None = None
        self.mode: str | None = None
        self.paused = False
        self.fault = False
        self.track: TrackMsg | None = None
        self.last_t: int | None = None
        self.counts = dict(R=0, M=0, T=0, ignored=0, bad=0, restarts=0)
        self.last_bad: str = ""

    def bin_of(self, angle: float) -> int:
        """Same bins as scan_map_bin() (scan_map.h, S3 27/11): APP_SWEEP_STEP_DEG
        wide, bin = floor(angle / bin_deg) clamped to 0..180, so the odd-degree
        sweep grid sits mid-bin. A newer reading in a bin replaces the older
        one (one mark per bin). round() would be wrong here: Python rounds
        43.5 and 44.5 both to 44, putting 87 and 89 deg in one bin."""
        n_bins = math.ceil(180.0 / self.cfg.step_deg)
        return min(max(int(math.floor(angle / self.cfg.step_deg)), 0), n_bins - 1)

    def feed_line(self, line: str) -> Reading | ModeMsg | TrackMsg | None:
        try:
            msg = parse_line(line)
        except BadLine as e:
            self.counts["bad"] += 1
            self.last_bad = str(e)
            return None
        if msg is None:
            if line.strip():
                self.counts["ignored"] += 1
            return None
        self.feed(msg)
        return msg

    def feed(self, msg: Reading | ModeMsg | TrackMsg) -> None:
        # A big backwards jump in t_ms means the device restarted: start clean.
        # Small ones (a T line stamped just before the last R) are accepted.
        if self.last_t is not None and msg.t_ms < self.last_t - self.cfg.stale_ms:
            self.counts["restarts"] += 1
            self.bins.clear()
            self.latest = None
            self.track = None
            self.last_t = None
        if self.last_t is None or msg.t_ms > self.last_t:
            self.last_t = msg.t_ms
        if isinstance(msg, Reading):
            self.counts["R"] += 1
            self.bins[self.bin_of(msg.angle)] = msg
            self.latest = msg
        elif isinstance(msg, ModeMsg):
            self.counts["M"] += 1
            self.mode, self.paused, self.fault = msg.mode, msg.paused, msg.fault
        else:
            self.counts["T"] += 1
            self.track = msg

    def age_ms(self, r: Reading, now_ms: float) -> float:
        return max(0.0, now_ms - r.t_ms)

    def freshness(self, r: Reading, now_ms: float) -> float:
        """1 just measured -> 0 at APP_FADE_SWEEPS passes, linear (D-FADE)."""
        return max(0.0, 1.0 - self.age_ms(r, now_ms) / self.cfg.fade_ms)

    def expire(self, now_ms: float) -> int:
        """Drop bins older than APP_EXPIRE_SWEEPS passes. Returns how many."""
        old = [k for k, r in self.bins.items() if self.age_ms(r, now_ms) > self.cfg.expire_ms]
        for k in old:
            del self.bins[k]
        return len(old)

    def since_last_reading_ms(self, now_ms: float) -> float | None:
        return None if self.latest is None else self.age_ms(self.latest, now_ms)

    def is_stale(self, now_ms: float | None, link_up: bool = True) -> bool:
        """No R line for APP_STALE_MS, no R line yet, or the link is down."""
        if not link_up or now_ms is None or self.latest is None:
            return True
        return self.age_ms(self.latest, now_ms) > self.cfg.stale_ms


class DeviceClock:
    """Device time now = t_ms of the latest line + wall time since, x speed."""

    def __init__(self, speed: float = 1.0, wall=time.monotonic):
        self.speed = speed
        self.wall = wall
        self.anchor: tuple[int, float] | None = None

    def sync(self, t_ms: int, restarted: bool = False) -> None:
        if self.anchor is None or restarted or t_ms >= self.now_ms():
            self.anchor = (t_ms, self.wall())

    def now_ms(self) -> float | None:
        if self.anchor is None:
            return None
        t, w = self.anchor
        return t + (self.wall() - w) * 1000.0 * self.speed
