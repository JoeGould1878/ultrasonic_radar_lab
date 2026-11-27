#!/usr/bin/env python3
"""
S2: scene simulator (docs/PLAN.md task S2).

Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
Credits / sources: HC-SR04 datasheet (range, ~15 deg beam, 0.3 cm resolution).
The "first echo wins" and specular-reflection behaviour are standard ultrasonic
ranging physics; no code adapted.

DESIGN QUESTIONS
    Q1  Smear: across how many degrees / bins does one thin tube (T1) appear at
        50/100/150 cm and at bearings 15..165 deg? How large is the bearing
        error if we take the nearest bin, compared with the middle of the two
        cluster edges, against SC3 (+/-5 deg)? Do the arc ends (15 and 165 deg,
        where the sweep stops) behave differently? (D-LOCK edge-midpoint, SC1, SC3)
    Q2  Resolution: at what angular gap do two thin dowels (T3) at 50 cm merge
        into one object? (predicts T-TWO; feeds APP_LOCK_DIST_TOL_CM in S3)
    Q3  Specular reflection: at what tilt does a flat board (T2) vanish, and how
        does that depend on the cutoff angle? (predicts T-MAT; why the display
        says "no echo", never "clear")
    Q4  Moving target: what does a tube (T1) moving across at 5/10/20 cm/s look
        like, and how far off is the per-pass bearing? (T-MOVE, SC8; S1 walker)
    It also produces the scenes + ground truth that S3 (lock-on host tests) and
    S4 (viewer) are driven with.

METHOD
    A flat 2D bench, top-down. The sensor sits at the servo pivot (origin).
    Angles as the servo: 0-180 deg, 90 = straight ahead (+y), 0 = +x (right).
    Objects match docs/LAB_TESTS.md targets: T1 5 cm tube and T3 2 cm dowel
    (circles), T2 A4 board (one 21 cm segment), T4 soft jumper (circle that
    echoes only sometimes), T5 box (four segments).

    One ping at servo angle theta returns the NEAREST surface point that
      (a) lies inside the beam cone theta +/- beam/2,
      (b) sends sound back: its surface normal is within the specular cutoff
          of the direction back to the sensor, and
      (c) has a clear line of sight (no other object in between).
    A circle always has such a point (the point facing the sensor), so tubes
    are easy to see; a flat board only if it faces the sensor closely enough.
    Then: Gaussian distance noise, random dropouts (-> NOECHO), NOECHO beyond
    APP_US_MAX_RANGE_CM, optional ghost echoes and FAIL windows.

    The sweep and its timing come from S1: bounce between APP_SWEEP_MIN_DEG
    and APP_SWEEP_MAX_DEG in APP_SWEEP_STEP_DEG steps, one ping every
    sweep_timing.Model.period_ms() (60 ms with the current config), stop-and-
    ping (D-SCAN), reading tagged with the settled angle (D-ANGLE-TAG). Moving
    objects move between pings. Every default is parsed from main/app_config.h
    (sim/appcfg.py). Random numbers are seeded per scene, so runs repeat exactly.

    The analysis groups readings by pass, finds clusters (neighbouring OK bins
    within APP_LOCK_DIST_TOL_CM of each other, at least APP_LOCK_MIN_BINS
    long) and takes the bearing as the middle of the two edges. That Python
    code (clusters_illustrative / edge_midpoint_illustrative) is FOR
    ILLUSTRATION ONLY: the reference implementation is the C code in
    components/target_track (S3), whose host tests must give the same answers
    on these scenes.

ASSUMPTIONS (each marked ASSUMED; the named test replaces it)
    S2-A1  Beam: hard-edged cone, 15 deg full width (datasheet); 8 deg run as a
           pessimistic what-if. No side lobes.            -> B2, T-ANG
    S2-A2  Specular cutoff 25 deg (swept 15/25/35): a surface echoes only if
           its normal is within this of the line back to the sensor. -> T-MAT
    S2-A3  Distance noise sigma = max(0.3 cm, 1 % of distance). -> B2, T-DIST
    S2-A4  Dropouts: 2 % of pings that should echo read NOECHO. -> B2, T-DIST
    S2-A5  "Noisy" scenes only: 10 % dropouts and 2 % ghost echoes at a
           random distance. Not used anywhere else.       -> T-XTALK, empty-bench log
    S2-A6  First echo wins: the nearest returning point in the cone sets the
           reading; farther objects in the same cone are not seen. -> T-TWO, B2
    S2-A7  Sensor exactly at the pivot, pointing exactly at the commanded
           angle (S1 A2, ideal settle).                    -> B1, D-MOUNT
    S2-A8  T4 soft jumper echoes on 30 % of pings that reach it, and absorbs
           the rest.                                       -> T-MAT
    S2-A9  Timing from S1 (60 ms per ping, 4.5 s per pass). -> T-SWEEP
    S2-A10 2D: objects are infinitely tall; the bench top and floor never
           echo.                                           -> T-MAT, I7
    Not modelled: side lobes, multipath (wall -> object -> sensor), cross-talk
    from other sensors (T-XTALK), temperature, servo pointing error (B1),
    corner diffraction on the box, the firmware's fault state machine.

CONFIRM ON HARDWARE
    B2 / T-ANG: smear width of T1 at 50/100/150 cm (beam, A1). T-MAT: angle at
    which T2 vanishes (cutoff, A2). T-TWO: merge angle (Q2). T-MOVE: trail
    shape at 5/20 cm/s (Q4). I7: record the SAME scenes for real (the scene
    names below are the test set-ups) and replay them through S3 and the
    viewer; compare smear, merge angle and vanishing tilt with this model.

SERIAL PROTOCOL (matched against main/serial_out.h lines 6-10 and docs/PLAN.md)
      R,<t_ms>,<mode>,<angle_deg>,<dist_cm>,<status>     status OK|NOECHO|FAIL
      M,<t_ms>,<mode>,<paused>,<fault>
    Only R and M are emitted (T lines come from target_track, S3). The first
    line is a "# ..." provenance comment, which the viewer ignores like any
    non-R/M/T line. dist_cm follows D-PROTO-NULL (docs/PLAN.md): 1 decimal
    place when OK, "-" for NOECHO and FAIL. The angle is written with 1
    decimal place (not fixed by the protocol). All formatting is in
    format_r()/format_m().

TRUTH FILES  (<scene>.truth.csv, next to <scene>.txt)
    CSV with a header row; one row per object per ping, with the SAME t_ms as
    the R line of that ping:
      t_ms        int    ping time, matches the R line
      obj         str    object id, unique within the scene (e.g. "T1", "T3a")
      kind        str    T1 | T2 | T3 | T4 | T5
      present     0/1    0 = removed / not yet placed (other fields still filled)
      bearing_deg float  servo angle of the object's centre
      range_cm    float  distance from the sensor to the nearest point of the
                         object's surface (what a perfect sensor would read)
      x_cm, y_cm  float  centre position (x right, y straight ahead)
      size_cm     float  tube diameter / board width / box width
    S3 scores lock time, bearing error (target centre_deg vs bearing_deg),
    false locks (any lock when no object is present) and lost time from these.

OUTPUTS (docs/evidence/sim/)
    s2_scenes/<scene>.txt, .truth.csv   every scene, default sensor model
    s2_scenes/<scene>.clusters.csv      (S3) clusters per pass, bridge 0 and 1,
                                        for the C = Python check (test_scenes)
    s2_results.csv, s2_summary.txt      the numbers behind Q1-Q4
    s2_smear_view.png      top-down: one pass of T1 at 50/100/150 cm and at 15 deg
    s2_bearing_error.png   Q1: nearest-bin vs edge-midpoint error by bearing
    s2_two_poles.png       Q2: % of passes that resolve two dowels, by gap
    s2_board_tilt.png      Q3: echoing bins vs board tilt, by cutoff
    s2_moving.png          Q4: readings and per-pass bearing vs truth over time

RUN
    python sim/scene.py                        everything: logs, analysis, charts
    python sim/scene.py --list                 scene names
    python sim/scene.py --scene t1_b90_r50     stream one scene to stdout
        [--passes N] [--realtime] [--seed S] [--beam 15] [--cutoff 25]
    --realtime paces the lines at the real ping rate (for radar_view --sim).
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import time
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from appcfg import CONFIG_H, EVIDENCE_SIM, ROOT, parse_config  # noqa: E402
import sweep_timing  # noqa: E402

OUT = EVIDENCE_SIM
SCENE_DIR = OUT / "s2_scenes"
NEEDED = sweep_timing.NEEDED + [
    "APP_US_MIN_RANGE_CM", "APP_LOCK_DIST_TOL_CM", "APP_LOCK_MIN_BINS",
]
INF = float("inf")

# --------------------------------------------------------- assumptions ----
@dataclass(frozen=True)
class Sensor:
    beam_deg: float = 15.0        # S2-A1 ASSUMED (datasheet)
    cutoff_deg: float = 25.0      # S2-A2 ASSUMED
    sigma_floor_cm: float = 0.3   # S2-A3 ASSUMED (datasheet resolution)
    sigma_frac: float = 0.01      # S2-A3 ASSUMED
    p_dropout: float = 0.02       # S2-A4 ASSUMED
    p_ghost: float = 0.0          # S2-A5 ASSUMED (noisy scenes only)


NOISY = dict(p_dropout=0.10, p_ghost=0.02)  # S2-A5
T4_P_ECHO = 0.3                             # S2-A8
BEAMS = (15.0, 8.0)
CUTOFFS = (15.0, 25.0, 35.0)
ANALYSIS_PASSES = 40
SC3_DEG = 5.0

# chart style (dataviz reference palette, categorical slots in order)
C1, C2, C3 = "#257de0", "#f47230", "#00b894"
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"


# ------------------------------------------------------------- objects ----
def _wrap(a: float) -> float:
    """Angle difference into (-180, 180]."""
    return (a + 180.0) % 360.0 - 180.0


def _bearing(x: float, y: float) -> float:
    return math.degrees(math.atan2(y, x))


def _seg_hits_seg(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    """Proper intersection of segments AB and CD (touching ends don't count)."""
    def cross(ox, oy, px, py, qx, qy):
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
    d1 = cross(cx, cy, dx, dy, ax, ay)
    d2 = cross(cx, cy, dx, dy, bx, by)
    d3 = cross(ax, ay, bx, by, cx, cy)
    d4 = cross(ax, ay, bx, by, dx, dy)
    return (d1 * d2 < -1e-9) and (d3 * d4 < -1e-9)


@dataclass
class Circle:
    """Tube, dowel or soft object. Position (x, y) is the centre, at t = 0."""
    oid: str
    kind: str
    x: float
    y: float
    r: float
    vx: float = 0.0        # cm/s
    vy: float = 0.0
    t_on: float = 0.0      # ms
    t_off: float = INF
    p_echo: float = 1.0

    def centre(self, t):
        return self.x + self.vx * t / 1000.0, self.y + self.vy * t / 1000.0

    def present(self, t):
        return self.t_on <= t < self.t_off

    def echoes(self, t, theta, half, cutoff):
        cx, cy = self.centre(t)
        d = math.hypot(cx, cy)
        phi = _bearing(cx, cy)
        # the patch whose normal is within the cutoff of the sensor direction
        patch = math.degrees(math.asin(min(1.0, self.r * math.sin(math.radians(cutoff)) / d)))
        if abs(_wrap(phi - theta)) > half + patch:
            return []
        k = (d - self.r) / d
        return [(d - self.r, cx * k, cy * k)]

    def blocks(self, t, px, py) -> bool:
        """Does this circle cut the line from the sensor to (px, py)?"""
        cx, cy = self.centre(t)
        L2 = px * px + py * py
        u = max(0.0, min(1.0, (cx * px + cy * py) / L2))
        return math.hypot(cx - u * px, cy - u * py) < self.r - 1e-6

    def truth(self, t):
        cx, cy = self.centre(t)
        return dict(bearing_deg=_bearing(cx, cy), range_cm=math.hypot(cx, cy) - self.r,
                    x_cm=cx, y_cm=cy, size_cm=2 * self.r)


@dataclass
class Panel:
    """Board or box: straight segments [(x1, y1, x2, y2), ...]."""
    oid: str
    kind: str
    segs: list
    size: float
    t_on: float = 0.0
    t_off: float = INF
    p_echo: float = 1.0
    step_cm: float = 0.25   # surface sampling

    def present(self, t):
        return self.t_on <= t < self.t_off

    def echoes(self, t, theta, half, cutoff):
        best = None
        cos_cut = math.cos(math.radians(cutoff))
        for x1, y1, x2, y2 in self.segs:
            L = math.hypot(x2 - x1, y2 - y1)
            n = max(2, int(L / self.step_cm) + 1)
            s = np.linspace(0.0, 1.0, n)
            px = x1 + s * (x2 - x1)
            py = y1 + s * (y2 - y1)
            nx, ny = -(y2 - y1) / L, (x2 - x1) / L
            dist = np.hypot(px, py)
            # normal facing the sensor side of this point
            facing = np.sign(-(nx * px + ny * py))
            cos_inc = facing * (nx * -px + ny * -py) / dist
            bear = np.degrees(np.arctan2(py, px))
            in_cone = np.abs((bear - theta + 180.0) % 360.0 - 180.0) <= half
            ok = in_cone & (cos_inc >= cos_cut)
            if ok.any():
                i = int(np.argmin(np.where(ok, dist, np.inf)))
                if best is None or dist[i] < best[0]:
                    best = (float(dist[i]), float(px[i]), float(py[i]))
        return [best] if best else []

    def blocks(self, t, px, py) -> bool:
        return any(_seg_hits_seg(0.0, 0.0, px, py, *s) for s in self.segs)

    def truth(self, t):
        xs = [v for s in self.segs for v in (s[0], s[2])]
        ys = [v for s in self.segs for v in (s[1], s[3])]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        rng = min(_seg_dist(s) for s in self.segs)
        return dict(bearing_deg=_bearing(cx, cy), range_cm=rng, x_cm=cx, y_cm=cy, size_cm=self.size)


def _seg_dist(s) -> float:
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    u = max(0.0, min(1.0, -(x1 * dx + y1 * dy) / (dx * dx + dy * dy)))
    return math.hypot(x1 + u * dx, y1 + u * dy)


def _polar(bearing_deg, dist_cm):
    a = math.radians(bearing_deg)
    return dist_cm * math.cos(a), dist_cm * math.sin(a)


def tube(oid, kind, bearing, near_cm, diameter, **kw) -> Circle:
    """Circle whose nearest surface is near_cm from the sensor at bearing."""
    r = diameter / 2
    x, y = _polar(bearing, near_cm + r)
    return Circle(oid, kind, x, y, r, **kw)


def board(oid, bearing, near_cm, tilt_deg, width=21.0) -> Panel:
    """T2: board centred on the line at `bearing`, centre near_cm away, its
    normal turned tilt_deg away from the sensor direction."""
    cx, cy = _polar(bearing, near_cm)
    along = math.radians(bearing + 90.0 + tilt_deg)
    hx, hy = width / 2 * math.cos(along), width / 2 * math.sin(along)
    return Panel(oid, "T2", [(cx - hx, cy - hy, cx + hx, cy + hy)], width)


def box(oid, bearing, near_cm, w=20.0, d=15.0, rot_deg=30.0) -> Panel:
    """T5: w x d box whose centre is near_cm + d/2 away, rotated rot_deg."""
    cx, cy = _polar(bearing, near_cm + d / 2)
    a = math.radians(bearing + 90.0 + rot_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    pts = [(cx + sx * w / 2 * ux + sy * d / 2 * vx, cy + sx * w / 2 * uy + sy * d / 2 * vy)
           for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    segs = [(*pts[i], *pts[(i + 1) % 4]) for i in range(4)]
    return Panel(oid, "T5", segs, w)


# -------------------------------------------------------------- scenes ----
@dataclass
class Scene:
    name: str
    test: str                       # LAB_TESTS set-up it mirrors
    objects: list
    passes: int = 6
    fail_windows: list = field(default_factory=list)   # [(t0_ms, t1_ms)]
    sensor: dict = field(default_factory=dict)          # overrides of Sensor
    note: str = ""


T1_D, T3_D = 5.0, 2.0
T1_BEARINGS = (15, 30, 60, 90, 120, 150, 165)
T1_RANGES = (50, 100, 150)
T3_SEPS = (30, 25, 20, 17.5, 15, 12.5, 10, 7.5, 5)
MOVE_SPEEDS = (5, 10, 20)
T2_TILTS_LOG = (0, 20, 40, 60)


def build_scenes(timing) -> dict[str, Scene]:
    pass_ms = timing["pass_ms"]
    sc: list[Scene] = []
    # 1. T1 single tube (priority 1)
    for b in T1_BEARINGS:
        sc.append(Scene(f"t1_b{b}_r50", "T-ANG", [tube("T1", "T1", b, 50, T1_D)]))
    for r in T1_RANGES[1:]:
        sc.append(Scene(f"t1_b90_r{r}", "T-DIST / smear vs range", [tube("T1", "T1", 90, r, T1_D)]))
    # 2. T3 pair (priority 2)
    for s in T3_SEPS:
        tag = f"{s:g}".replace(".", "p")
        sc.append(Scene(f"t3_pair_s{tag}", "T-TWO",
                        [tube("T3a", "T3", 90 - s / 2, 50, T3_D), tube("T3b", "T3", 90 + s / 2, 50, T3_D)]))
    # 3. T1 moving across at y = 52.5 from x = -60 to +60 (priority 3)
    for v in MOVE_SPEEDS:
        dur_ms = 120.0 / v * 1000.0
        passes = int(math.ceil(dur_ms / pass_ms)) + 1
        sc.append(Scene(f"t1_move_v{v}", "T-MOVE / SC8",
                        [Circle("T1", "T1", -60.0, 50 + T1_D / 2, T1_D / 2, vx=float(v), t_off=dur_ms)],
                        passes=passes, note=f"{v} cm/s left to right at 50 cm"))
    # 4. T1 removed after 2.5 passes (priority 4)
    sc.append(Scene("t1_removed", "T-REMOVE",
                    [tube("T1", "T1", 90, 50, T1_D, t_off=2.5 * pass_ms)], passes=6))
    # 5. empty / noisy (priority 5)
    sc.append(Scene("empty", "SC8 false locks", [], passes=6))
    sc.append(Scene("empty_noisy", "SC8 false locks", [], passes=6, sensor=NOISY))
    sc.append(Scene("t1_noisy", "D-FILTER", [tube("T1", "T1", 90, 50, T1_D)], passes=6, sensor=NOISY))
    sc.append(Scene("t1_fault", "T-FAULT", [tube("T1", "T1", 90, 50, T1_D)], passes=6,
                    fail_windows=[(1.5 * pass_ms, 1.5 * pass_ms + 1000.0)]))
    # 6. T2 board (priority 6)
    for r in (50, 100):
        for tilt in T2_TILTS_LOG:
            sc.append(Scene(f"t2_tilt{tilt}_r{r}", "T-MAT", [board("T2", 90, r, tilt)], passes=4))
    # 7. optional T4 / T5
    sc.append(Scene("t4_t5_materials", "T-MAT",
                    [tube("T4", "T4", 60, 60, 20.0, p_echo=T4_P_ECHO), box("T5", 120, 60)], passes=6))
    return {s.name: s for s in sc}


# ----------------------------------------------------------- simulator ----
def sweep_angles(cfg):
    """Bounce like sweep_plan FULL: yields (pass_index, angle)."""
    lo, hi, step = cfg["APP_SWEEP_MIN_DEG"], cfg["APP_SWEEP_MAX_DEG"], cfg["APP_SWEEP_STEP_DEG"]
    up = [lo + i * step for i in range(int(round((hi - lo) / step)) + 1)]
    yield from ((0, a) for a in up)
    p = 1
    while True:
        seq = up[-2::-1] if p % 2 else up[1:]
        yield from ((p, a) for a in seq)
        p += 1


def scene_seed(name: str, seed: int) -> int:
    return (zlib.crc32(name.encode()) + 7919 * seed) & 0xFFFFFFFF


def ping(objs, t, theta, sensor: Sensor, cfg, rng, failing: bool):
    """One reading: (dist_cm, status)."""
    if failing:
        return 0.0, "FAIL"
    if sensor.p_ghost and rng.random() < sensor.p_ghost:
        return float(rng.uniform(cfg["APP_US_MIN_RANGE_CM"], cfg["APP_US_MAX_RANGE_CM"])), "OK"
    live = [o for o in objs if o.present(t)]
    cands = []
    for o in live:
        for d, px, py in o.echoes(t, theta, sensor.beam_deg / 2, sensor.cutoff_deg):
            cands.append((d, px, py, o))
    cands.sort(key=lambda c: c[0])
    for d, px, py, o in cands:
        if any(other is not o and other.blocks(t, px, py) for other in live):
            continue
        if o.p_echo < 1.0 and rng.random() >= o.p_echo:
            continue                                  # absorbed (S2-A8)
        if d > cfg["APP_US_MAX_RANGE_CM"]:
            break
        if rng.random() < sensor.p_dropout:
            return 0.0, "NOECHO"
        sigma = max(sensor.sigma_floor_cm, sensor.sigma_frac * d)
        return float(d + rng.normal(0.0, sigma)), "OK"
    return 0.0, "NOECHO"


def run_scene(scene: Scene, cfg, timing, sensor: Sensor, seed=0, passes=None):
    """Returns readings [(t_ms, pass, angle, dist, status)] and truth rows."""
    sensor = replace(sensor, **scene.sensor)
    rng = np.random.default_rng(scene_seed(scene.name, seed))
    period = timing["period_ms"]
    n_pass = passes if passes is not None else scene.passes
    readings, truth = [], []
    for k, (p, angle) in enumerate(sweep_angles(cfg)):
        if p >= n_pass:
            break
        t = int(round(k * period))
        failing = any(a <= t < b for a, b in scene.fail_windows)
        d, st = ping(scene.objects, t, angle, sensor, cfg, rng, failing)
        readings.append((t, p, angle, d, st))
        for o in scene.objects:
            tr = o.truth(t)
            truth.append(dict(t_ms=t, obj=o.oid, kind=o.kind, present=int(o.present(t)), **tr))
    return readings, truth


# ------------------------------------------------------------- output ----
def format_m(t_ms, mode="SWEEP", paused=0, fault=0) -> str:
    return f"M,{t_ms},{mode},{paused},{fault}"


def format_r(t_ms, angle, dist, status, mode="SWEEP") -> str:
    # D-PROTO-NULL: 1 decimal place when OK, "-" for NOECHO / FAIL
    d = f"{dist:.1f}" if status == "OK" else "-"
    return f"R,{t_ms},{mode},{angle:.1f},{d},{status}"


def provenance(scene: Scene, sensor: Sensor, seed: int) -> str:
    s = replace(sensor, **scene.sensor)
    return (f"# S2 scene {scene.name} ({scene.test}) seed={seed} beam={s.beam_deg:g} "
            f"cutoff={s.cutoff_deg:g} dropout={s.p_dropout:g} ghost={s.p_ghost:g} "
            f"sigma=max({s.sigma_floor_cm:g},{s.sigma_frac:g}*d)")


def write_scene(scene, readings, truth, sensor, seed):
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCENE_DIR / f"{scene.name}.txt", "w") as f:
        f.write(provenance(scene, sensor, seed) + "\n")
        f.write(format_m(0) + "\n")
        for t, _, a, d, st in readings:
            f.write(format_r(t, a, d, st) + "\n")
    with open(SCENE_DIR / f"{scene.name}.truth.csv", "w", newline="") as f:
        cols = ["t_ms", "obj", "kind", "present", "bearing_deg", "range_cm", "x_cm", "y_cm", "size_cm"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in truth:
            w.writerow({k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in row.items()})


def stream(scene, cfg, timing, sensor, seed, passes, realtime):
    readings, _ = run_scene(scene, cfg, timing, sensor, seed, passes)
    out = sys.stdout
    print(provenance(scene, sensor, seed), file=out)
    print(format_m(0), file=out, flush=True)
    t0 = time.monotonic()
    for t, _, a, d, st in readings:
        if realtime:
            wait = t / 1000.0 - (time.monotonic() - t0)
            if wait > 0:
                time.sleep(wait)
        print(format_r(t, a, d, st), file=out, flush=realtime)


# ------------------------------------------------- analysis (Python) ----
# ---------------------------------------------------------------------------
# clusters_illustrative / edge_midpoint_illustrative
# FOR ILLUSTRATION ONLY. They exist so S2 can show why the edge-midpoint
# method is needed. The reference implementation is the C code in
# components/target_track (PLAN task S3); S3's host tests must check that the
# C code gives the same answers on these same scenes.
# Rule: neighbouring OK bins whose distances differ by <= dist_tol belong to
# one cluster; a cluster needs >= min_bins bins; bearing = middle of its edges.
# bridge (S3, default 0 = the S2 rule, unchanged): an OK reading also joins
# across up to `bridge` non-OK readings, if its distance is still within
# dist_tol of the cluster's last OK reading; an OK reading at another
# distance is never bridged over; bridged readings are not counted in n.
# This is the rule Joe approved for target_track (27/11).
# ---------------------------------------------------------------------------
def clusters_illustrative(pass_readings, step, dist_tol, min_bins, bridge=0):
    """pass_readings: [(t, pass, angle, dist, status)] of ONE pass.
    Returns [dict(left, right, centre, n, dist, t_mid)] sorted by angle."""
    rs = sorted(pass_readings, key=lambda r: r[2])
    out, cur = [], []
    gap = 0

    def close():
        if len(cur) >= min_bins:
            ds = sorted(r[3] for r in cur)
            ts = sorted(r[0] for r in cur)
            out.append(dict(left=cur[0][2], right=cur[-1][2], n=len(cur),
                            centre=edge_midpoint_illustrative(cur[0][2], cur[-1][2]),
                            dist=ds[len(ds) // 2], t_mid=ts[len(ts) // 2],
                            nearest_bin=min(cur, key=lambda r: r[3])[2]))

    for r in rs:
        ok = r[4] == "OK"
        if ok:
            if (cur and gap <= bridge and abs(r[2] - cur[-1][2] - step * (gap + 1)) < 1e-6
                    and abs(r[3] - cur[-1][3]) <= dist_tol):
                cur.append(r)
            else:
                close()
                cur = [r]
            gap = 0
        elif cur:
            gap += 1
            if gap > bridge:
                close()
                cur, gap = [], 0
    close()
    return out


def edge_midpoint_illustrative(left_deg, right_deg):
    return (left_deg + right_deg) / 2.0


def write_clusters(scene, readings, cfg):
    """<scene>.clusters.csv (S3): every cluster of every pass, bridge 0 and 1,
    computed from the readings AS LOGGED (1 decimal place), so that
    host_tests/test_scenes.c, which replays the .txt log through the C
    target_track, sees exactly the same numbers. nearest = 1 marks the
    cluster target_track_find_cluster must return (smallest dist, lower
    angle on a tie). edge: touches the arc ends within half a step.
    Like target_track, an OK reading beyond APP_US_MAX_RANGE_CM is ignored
    (treated as non-OK): S2's noise can push a reading from a target at the
    range limit just past it. The S2 analysis above does not do this.
    Distances are float32, as in the C code (scan_bin_t.dist_cm), so a pair
    that differs by exactly dist_tol after rounding joins or splits the same
    way in both."""
    lo, hi, step = cfg["APP_SWEEP_MIN_DEG"], cfg["APP_SWEEP_MAX_DEG"], cfg["APP_SWEEP_STEP_DEG"]
    rmax = cfg["APP_US_MAX_RANGE_CM"]
    logged = []
    for t, p, a, d, st in readings:
        dl = np.float32(f"{d:.1f}") if st == "OK" else np.float32(0.0)
        logged.append((t, p, float(f"{a:.1f}"), dl, st if (st != "OK" or dl <= rmax) else "RANGE"))
    with open(SCENE_DIR / f"{scene.name}.clusters.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bridge", "pass", "left_deg", "right_deg", "centre_deg", "n_bins",
                    "dist_cm", "edge", "nearest"])
        for bridge in (0, 1):
            for k, pr in enumerate(by_pass(logged)):
                cl = clusters_illustrative(pr, step, cfg["APP_LOCK_DIST_TOL_CM"],
                                           int(cfg["APP_LOCK_MIN_BINS"]), bridge)
                near = min(cl, key=lambda c: c["dist"]) if cl else None
                for c in cl:
                    edge = c["left"] <= lo + step / 2 or c["right"] >= hi - step / 2
                    w.writerow([bridge, k, f"{c['left']:.1f}", f"{c['right']:.1f}",
                                f"{c['centre']:.2f}", c["n"], f"{c['dist']:.1f}",
                                int(edge), int(c is near)])


def by_pass(readings):
    passes: dict[int, list] = {}
    for r in readings:
        passes.setdefault(r[1], []).append(r)
    return [passes[k] for k in sorted(passes)]


class Analysis:
    def __init__(self, cfg, timing, scenes):
        self.cfg, self.timing, self.scenes = cfg, timing, scenes
        self.step = cfg["APP_SWEEP_STEP_DEG"]
        self.tol = cfg["APP_LOCK_DIST_TOL_CM"]
        self.min_bins = int(cfg["APP_LOCK_MIN_BINS"])
        self.rows: list[dict] = []

    def clusters(self, pr):
        return clusters_illustrative(pr, self.step, self.tol, self.min_bins)

    def rec(self, q, scene, beam, cutoff, metric, value):
        self.rows.append(dict(question=q, scene=scene, beam_deg=beam, cutoff_deg=cutoff,
                              metric=metric, value=round(value, 3) if isinstance(value, float) else value))

    # Q1 ---------------------------------------------------------------
    def q1(self):
        res = {}
        names = [f"t1_b{b}_r50" for b in T1_BEARINGS] + [f"t1_b90_r{r}" for r in T1_RANGES[1:]]
        for beam in BEAMS:
            sensor = Sensor(beam_deg=beam)
            for name in names:
                sc = self.scenes[name]
                rd, tr = run_scene(sc, self.cfg, self.timing, sensor, passes=ANALYSIS_PASSES)
                truth_b = tr[0]["bearing_deg"]
                n, e_mid, e_near, missed = [], [], [], 0
                for pr in by_pass(rd):
                    cl = self.clusters(pr)
                    if not cl:
                        missed += 1
                        continue
                    c = min(cl, key=lambda c: c["dist"])
                    n.append(c["n"])
                    e_mid.append(abs(c["centre"] - truth_b))
                    e_near.append(abs(c["nearest_bin"] - truth_b))
                r = dict(bins=float(np.mean(n)), width=float(np.mean(n)) * self.step,
                         mid_mean=float(np.mean(e_mid)), mid_max=float(np.max(e_mid)),
                         near_mean=float(np.mean(e_near)), near_max=float(np.max(e_near)),
                         missed=missed, truth=truth_b)
                res[(beam, name)] = r
                for k, v in r.items():
                    self.rec("Q1", name, beam, 25.0, k, v)
        self.q1_res = res
        return res

    # Q2 ---------------------------------------------------------------
    def q2(self):
        res = {}
        for beam in BEAMS:
            for s in T3_SEPS:
                name = f"t3_pair_s{s:g}".replace(".", "p")
                sc = self.scenes[name]
                rd, _ = run_scene(sc, self.cfg, self.timing, Sensor(beam_deg=beam), passes=ANALYSIS_PASSES)
                two = sum(1 for pr in by_pass(rd) if len(self.clusters(pr)) == 2)
                rd0, _ = run_scene(sc, self.cfg, self.timing, Sensor(beam_deg=beam, p_dropout=0.0), passes=1)
                n_clean = len(self.clusters(by_pass(rd0)[0]))
                res[(beam, s)] = dict(pct_two=100.0 * two / ANALYSIS_PASSES, clean_clusters=n_clean)
                self.rec("Q2", name, beam, 25.0, "pct_passes_two_clusters", 100.0 * two / ANALYSIS_PASSES)
                self.rec("Q2", name, beam, 25.0, "clusters_no_dropouts", n_clean)
        self.q2_res = res
        return res

    # Q3 ---------------------------------------------------------------
    def q3(self):
        res = {}
        tilts = list(range(0, 75, 5))
        for r in (50, 100):
            for cut in CUTOFFS:
                ys = []
                for tilt in tilts:
                    sc = Scene("q3", "T-MAT", [board("T2", 90, r, tilt)], passes=1)
                    rd, _ = run_scene(sc, self.cfg, self.timing,
                                      Sensor(cutoff_deg=cut, p_dropout=0.0), passes=1)
                    k = sum(1 for x in rd if x[4] == "OK")
                    ys.append(k)
                    self.rec("Q3", f"t2_tilt{tilt}_r{r}", 15.0, cut, "ok_bins_per_pass", k)
                vanish = next((t for t, k in zip(tilts, ys) if k == 0), None)
                res[(r, cut)] = dict(tilts=tilts, ok=ys, vanish=vanish)
                self.rec("Q3", f"t2_r{r}", 15.0, cut, "vanish_tilt_deg", vanish if vanish is not None else -1)
        self.q3_res = res
        return res

    # Q4 ---------------------------------------------------------------
    def q4(self):
        res = {}
        for v in MOVE_SPEEDS:
            sc = self.scenes[f"t1_move_v{v}"]
            rd, _ = run_scene(sc, self.cfg, self.timing, Sensor())
            obj = sc.objects[0]
            per = []
            for pr in by_pass(rd):
                direction = "up" if pr[-1][2] > pr[0][2] else "down"
                for c in self.clusters(pr):
                    if not obj.present(c["t_mid"]):
                        continue
                    tb = obj.truth(c["t_mid"])
                    t_end = pr[-1][0]
                    te = obj.truth(min(t_end, obj.t_off - 1))
                    rng_cm = tb["range_cm"]
                    per.append(dict(t=c["t_mid"], dir=direction, n=c["n"], centre=c["centre"],
                                    err_deg=c["centre"] - tb["bearing_deg"],
                                    err_cm=math.radians(abs(c["centre"] - tb["bearing_deg"])) * rng_cm,
                                    stale_cm=math.hypot(te["x_cm"] - tb["x_cm"], te["y_cm"] - tb["y_cm"])))
            # object moves left->right = bearing decreasing; sweep "down" runs WITH it
            w_with = [p["n"] * self.step for p in per if p["dir"] == "down"]
            w_against = [p["n"] * self.step for p in per if p["dir"] == "up"]
            r = dict(passes_seen=len(per),
                     width_with=float(np.mean(w_with)) if w_with else float("nan"),
                     width_against=float(np.mean(w_against)) if w_against else float("nan"),
                     err_deg_max=float(max(abs(p["err_deg"]) for p in per)),
                     err_cm_mean=float(np.mean([p["err_cm"] for p in per])),
                     err_cm_max=float(max(p["err_cm"] for p in per)),
                     stale_cm_max=float(max(p["stale_cm"] for p in per)))
            res[v] = dict(summary=r, per=per, readings=rd, obj=obj)
            for k, val in r.items():
                self.rec("Q4", sc.name, 15.0, 25.0, k, val)
        self.q4_res = res
        return res


# --------------------------------------------------------------- charts ----
def style_axes(ax):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_title(fig, title, sub):
    fig.suptitle(title, x=0.01, ha="left", fontsize=12.5, fontweight="bold", color=INK, y=0.99)
    fig.text(0.01, 0.95 - 0.12 / fig.get_figheight(), sub, ha="left", va="top", fontsize=9, color=INK2)


def chart_smear(cfg, timing, scenes, a: Analysis, path):
    fig, ax = plt.subplots(figsize=(9, 5.6))
    fig.patch.set_facecolor("white")
    style_axes(ax)
    rmax = cfg["APP_US_MAX_RANGE_CM"]
    for rr in (50, 100, 150):
        th = np.radians(np.linspace(cfg["APP_SWEEP_MIN_DEG"], cfg["APP_SWEEP_MAX_DEG"], 200))
        ax.plot(rr * np.cos(th), rr * np.sin(th), color=GRID, linewidth=1.2, zorder=0)
        lx, ly = _polar(150, rr)
        ax.annotate(f"{rr} cm", xy=(lx, ly), xytext=(-4, 4), textcoords="offset points", fontsize=8,
                    color=INK2, ha="right")
    for lim in (cfg["APP_SWEEP_MIN_DEG"], cfg["APP_SWEEP_MAX_DEG"]):
        x, y = _polar(lim, rmax)
        ax.plot([0, x], [0, y], color=INK2, linewidth=0.8, linestyle=(0, (4, 3)), zorder=0)
    for name in ("t1_b90_r50", "t1_b90_r100", "t1_b90_r150", "t1_b15_r50"):
        sc = scenes[name]
        rd, tr = run_scene(sc, cfg, timing, Sensor(), passes=1)
        oks = [r for r in rd if r[4] == "OK"]
        xs, ys = zip(*[_polar(r[2], r[3]) for r in oks])
        ax.plot(xs, ys, "o", color=C1, markersize=5, markeredgecolor="white", markeredgewidth=1, zorder=3)
        o = sc.objects[0]
        cx, cy = o.centre(0)
        ax.add_patch(plt.Circle((cx, cy), o.r, facecolor=INK, edgecolor=INK, zorder=4))
        cl = min(a.clusters(rd), key=lambda c: c["dist"])
        ax.annotate(f"{cl['n']} bins, {cl['right'] - cl['left']:.0f}° edge to edge", xy=(xs[0], ys[0]),
                    xytext=(8, -2), textcoords="offset points", fontsize=8.5, color=INK, va="center")
    ax.plot([0], [0], "s", color=INK, markersize=7)
    ax.annotate("sensor", xy=(0, 0), xytext=(6, -10), textcoords="offset points", fontsize=8.5, color=INK2)
    ax.set_aspect("equal")
    ax.set_xlim(-165, 175)
    ax.set_ylim(-12, 165)
    ax.set_xlabel("x (cm)", fontsize=9, color=INK)
    ax.set_ylabel("y, straight ahead (cm)", fontsize=9, color=INK)
    fig_title(fig, "S2 · One thin tube (T1, black) as the scanner sees it in one pass",
              "Blue: OK readings drawn at their angle and distance. Every bin whose 15° beam touches the tube\n"
              "reads the same distance, so the tube becomes an arc. At 15° the sweep stops, cutting the arc short.")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def chart_bearing_error(a: Analysis, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, beam in zip(axes, BEAMS):
        style_axes(ax)
        bs = list(T1_BEARINGS)
        for key, col, lbl, dx in (("near", C2, "nearest bin", -1.2), ("mid", C1, "edge midpoint", 1.2)):
            mean = [a.q1_res[(beam, f"t1_b{b}_r50")][f"{key}_mean"] for b in bs]
            mx = [a.q1_res[(beam, f"t1_b{b}_r50")][f"{key}_max"] for b in bs]
            xs = [b + dx for b in bs]
            ax.vlines(xs, mean, mx, color=col, linewidth=1.5, zorder=2)
            ax.plot(xs, mx, "_", color=col, markersize=8, markeredgewidth=1.5, zorder=2)
            ax.plot(xs, mean, "o", color=col, markersize=7, markeredgecolor="white", markeredgewidth=1.5,
                    zorder=3, label=f"{lbl} (dot = mean, bar = worst)")
        ax.axhline(SC3_DEG, color=INK2, linestyle=(0, (4, 3)), linewidth=1.2)
        ax.annotate("SC3: ±5°", xy=(0.01, SC3_DEG), xycoords=("axes fraction", "data"), xytext=(0, 3),
                    textcoords="offset points", fontsize=8.5, color=INK2)
        ax.set_xticks(bs)
        ax.set_xlim(5, 175)
        ax.set_ylim(0, 9)
        ax.set_xlabel("True bearing of T1 at 50 cm (°)", fontsize=9, color=INK)
        ax.set_title(f"Beam {beam:g}°" + (" (datasheet)" if beam == 15 else " (what-if)"),
                     fontsize=10, loc="left", color=INK)
    axes[0].set_ylabel("Bearing error (°)", fontsize=9, color=INK)
    axes[0].legend(loc="upper center", fontsize=8.5, frameon=False, labelcolor=INK)
    fig_title(fig, "S2 · Q1: which bin is the tube in?",
              f"{ANALYSIS_PASSES} passes per bearing, with noise and dropouts. The nearest bin is picked by noise anywhere in "
              "the smear; the edge midpoint\nstays near the truth, except at the arc ends (the sweep cuts the smear) and when "
              "a dropout splits the smear in two.")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_two_poles(a: Analysis, path):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    fig.patch.set_facecolor("white")
    style_axes(ax)
    seps = list(T3_SEPS)[::-1]
    for beam, col in zip(BEAMS, (C1, C2)):
        ys = [a.q2_res[(beam, s)]["pct_two"] for s in seps]
        ax.plot(seps, ys, color=col, linewidth=2, zorder=3)
        ax.plot(seps, ys, "o", color=col, markersize=6, markeredgecolor="white", markeredgewidth=1.5, zorder=4)
        ax.annotate(f"{beam:g}° beam", xy=(seps[-1], ys[-1]), xytext=(8, 7 if beam == 8 else -7),
                    textcoords="offset points",
                    va="center", fontsize=9, color=INK)
    ax.set_xlim(3, 36)
    ax.set_ylim(-5, 105)
    ax.set_xticks(seps)
    ax.set_xlabel("Angle between two dowels (T3) at 50 cm (°)", fontsize=9, color=INK)
    ax.set_ylabel("Passes that show two objects (%)", fontsize=9, color=INK)
    fig_title(fig, "S2 · Q2: when do two dowels merge into one?",
              f"{ANALYSIS_PASSES} passes per gap. Below the beam width they merge; above it, a dropout inside one "
              "cluster can still split or shrink it.")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_board(a: Analysis, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, r in zip(axes, (50, 100)):
        style_axes(ax)
        for cut, col in zip(CUTOFFS, (C1, C2, C3)):
            q = a.q3_res[(r, cut)]
            v = q["vanish"]
            lbl = f"cutoff {cut:g}°: gone at {v}°" if v is not None else f"cutoff {cut:g}°: never gone"
            ax.plot(q["tilts"], q["ok"], color=col, linewidth=2, zorder=3, label=lbl)
            if v is not None:
                ax.plot([v], [0], "o", color=col, markersize=6, markeredgecolor="white",
                        markeredgewidth=1.5, zorder=4)
        ax.legend(loc="upper right", fontsize=8.5, frameon=False, labelcolor=INK)
        ax.set_xlim(0, 85)
        ax.set_xlabel("Board tilt away from facing the sensor (°)", fontsize=9, color=INK)
        ax.set_title(f"T2 board, 21 cm wide, at {r} cm", fontsize=10, loc="left", color=INK)
    axes[0].set_ylabel("Bins with an echo in one pass", fontsize=9, color=INK)
    fig_title(fig, "S2 · Q3: when does a flat board vanish?",
              "Specular reflection: a tilted board bounces the sound away. The vanishing tilt depends on the assumed "
              "cutoff (T-MAT measures it)\nand on how much of the board's width the beam sees. Beam 15°, no dropouts.")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_moving(a: Analysis, path):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, v in zip(axes, MOVE_SPEEDS):
        style_axes(ax)
        q = a.q4_res[v]
        rd, obj = q["readings"], q["obj"]
        ts = np.arange(0, obj.t_off, 50)
        ax.plot(ts / 1000, [obj.truth(t)["bearing_deg"] for t in ts], color=INK, linewidth=1.5, zorder=2)
        oks = [r for r in rd if r[4] == "OK"]
        ax.plot([r[0] / 1000 for r in oks], [r[2] for r in oks], "o", color=C1, markersize=3, alpha=0.7,
                markeredgewidth=0, zorder=3)
        ax.plot([p["t"] / 1000 for p in q["per"]], [p["centre"] for p in q["per"]], "D", color=C2,
                markersize=7, markeredgecolor="white", markeredgewidth=1.5, zorder=4)
        s = q["summary"]
        if math.isnan(s["width_with"]):
            title = f"{v} cm/s: seen in 1 pass only, smear {s['width_against']:.0f}° (against)"
        else:
            title = f"{v} cm/s: smear {s['width_with']:.0f}° with the sweep, {s['width_against']:.0f}° against"
        ax.set_title(title,
                     fontsize=9.5, loc="left", color=INK)
        ax.set_xlabel("Time (s)", fontsize=9, color=INK)
        ax.set_ylim(30, 150)
    axes[0].set_ylabel("Bearing (°)", fontsize=9, color=INK)
    axes[0].plot([], [], color=INK, linewidth=1.5, label="true bearing")
    axes[0].plot([], [], "o", color=C1, markersize=4, label="OK readings")
    axes[0].plot([], [], "D", color=C2, markersize=6, label="edge midpoint, per pass")
    axes[0].legend(loc="lower left", fontsize=8.5, frameon=False, labelcolor=INK)
    fig_title(fig, "S2 · Q4: a tube (T1) moving across at 50 cm",
              "When the sweep moves the same way as the tube, the beam stays on it longer and the smear widens; "
              "against it, the smear narrows.")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# -------------------------------------------------------------- summary ----
def summary(cfg, timing, a: Analysis) -> str:
    s = io.StringIO()
    p = lambda *x: print(*x, file=s)  # noqa: E731
    sd = Sensor()
    p("S2 scene simulator: summary")
    p("=" * 72)
    p(f"Config: step {cfg['APP_SWEEP_STEP_DEG']:g} deg, arc {cfg['APP_SWEEP_MIN_DEG']:g}-{cfg['APP_SWEEP_MAX_DEG']:g}, "
      f"range {cfg['APP_US_MAX_RANGE_CM']:g} cm, lock tol {cfg['APP_LOCK_DIST_TOL_CM']:g} cm, "
      f"min bins {cfg['APP_LOCK_MIN_BINS']:g}")
    p(f"Timing (S1): {timing['period_ms']:.0f} ms per ping, {timing['pass_ms'] / 1000:.2f} s per pass")
    p(f"ASSUMED sensor: beam {sd.beam_deg:g} (what-if 8), cutoff {sd.cutoff_deg:g} (swept 15/25/35), "
      f"sigma max({sd.sigma_floor_cm:g} cm, {sd.sigma_frac:.0%}), dropout {sd.p_dropout:.0%}; "
      f"noisy scenes dropout {NOISY['p_dropout']:.0%}, ghosts {NOISY['p_ghost']:.0%}")
    p()
    p(f"Q1 smear and bearing error, T1 ({ANALYSIS_PASSES} passes each)")
    p(f"  {'scene':14s} {'beam':>4} | {'bins':>5} {'width':>6} | {'nearest bin mean/max':>21} | "
      f"{'edge midpoint mean/max':>22} | missed")
    for beam in BEAMS:
        for name in [f"t1_b{b}_r50" for b in T1_BEARINGS] + [f"t1_b90_r{r}" for r in T1_RANGES[1:]]:
            r = a.q1_res[(beam, name)]
            p(f"  {name:14s} {beam:>4g} | {r['bins']:5.1f} {r['width']:5.1f}° | "
              f"{r['near_mean']:8.1f}° / {r['near_max']:4.1f}°      | {r['mid_mean']:8.1f}° / {r['mid_max']:4.1f}°"
              f"       | {r['missed']}")
    p()
    p(f"Q2 two T3 dowels at 50 cm: % of {ANALYSIS_PASSES} passes showing two objects (clusters with no dropouts)")
    p("  gap deg   | " + "  ".join(f"{s:>5g}" for s in T3_SEPS))
    for beam in BEAMS:
        p(f"  beam {beam:>4g} | " + "  ".join(f"{a.q2_res[(beam, s)]['pct_two']:5.0f}" for s in T3_SEPS))
        p(f"   (clean)  | " + "  ".join(f"{a.q2_res[(beam, s)]['clean_clusters']:5d}" for s in T3_SEPS))
    p()
    p("Q3 T2 board (21 cm): tilt at which it gives no echo at all (beam 15, no dropouts)")
    for r in (50, 100):
        p(f"  at {r:>3} cm: " + ", ".join(f"cutoff {c:g} -> {a.q3_res[(r, c)]['vanish']}°" for c in CUTOFFS))
        for c in CUTOFFS:
            q = a.q3_res[(r, c)]
            p(f"     cutoff {c:>2g}: echo bins by tilt " +
              " ".join(f"{t}:{k}" for t, k in zip(q["tilts"], q["ok"]) if t % 10 == 0))
    p()
    p("Q4 T1 moving left to right at 50 cm (per-pass edge midpoint vs truth at the same moment)")
    p(f"  {'speed':>6} | {'passes':>6} | smear with / against sweep | bearing err max | pos err mean/max | "
      f"moved by pass end (max)")
    for v in MOVE_SPEEDS:
        r = a.q4_res[v]["summary"]
        fw = lambda x: "  n/a" if math.isnan(x) else f"{x:4.0f}°"  # noqa: E731
        p(f"  {v:>3} cm/s | {r['passes_seen']:>6} | {fw(r['width_with']):>10} / {fw(r['width_against'])}"
          f"          | {r['err_deg_max']:10.1f}°     | {r['err_cm_mean']:5.1f} / {r['err_cm_max']:4.1f} cm  | "
          f"{r['stale_cm_max']:5.1f} cm")
    return s.getvalue()


# ----------------------------------------------------------------- main ----
def load():
    cfg = parse_config(CONFIG_H, NEEDED)
    tm = sweep_timing.Model(cfg)
    args = (cfg["APP_SWEEP_STEP_DEG"], cfg["APP_US_PING_GAP_MS"], cfg["APP_US_MAX_RANGE_CM"], "stop-and-ping")
    timing = dict(period_ms=tm.period_ms(*args), pass_ms=tm.pass_s(*args) * 1000.0)
    return cfg, timing


def main() -> None:
    ap = argparse.ArgumentParser(description="S2 scene simulator (see module docstring)")
    ap.add_argument("--list", action="store_true", help="list scene names")
    ap.add_argument("--scene", help="stream one scene to stdout")
    ap.add_argument("--passes", type=int, help="number of passes (default: per scene)")
    ap.add_argument("--realtime", action="store_true", help="pace lines at the real ping rate")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--beam", type=float, default=Sensor.beam_deg)
    ap.add_argument("--cutoff", type=float, default=Sensor.cutoff_deg)
    args = ap.parse_args()

    cfg, timing = load()
    scenes = build_scenes(timing)
    if args.list:
        for sc in scenes.values():
            print(f"{sc.name:18s} {sc.test:24s} {sc.passes} passes {sc.note}")
        return
    sensor = Sensor(beam_deg=args.beam, cutoff_deg=args.cutoff)
    if args.scene:
        if args.scene not in scenes:
            sys.exit(f"unknown scene {args.scene!r}; try --list")
        try:
            stream(scenes[args.scene], cfg, timing, sensor, args.seed, args.passes, args.realtime)
        except (BrokenPipeError, KeyboardInterrupt):
            pass
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for sc in scenes.values():
        rd, tr = run_scene(sc, cfg, timing, Sensor(), seed=0)
        write_scene(sc, rd, tr, Sensor(), 0)
        write_clusters(sc, rd, cfg)

    a = Analysis(cfg, timing, scenes)
    a.q1()
    a.q2()
    a.q3()
    a.q4()
    with open(OUT / "s2_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(a.rows[0].keys()))
        w.writeheader()
        w.writerows(a.rows)
    chart_smear(cfg, timing, scenes, a, OUT / "s2_smear_view.png")
    chart_bearing_error(a, OUT / "s2_bearing_error.png")
    chart_two_poles(a, OUT / "s2_two_poles.png")
    chart_board(a, OUT / "s2_board_tilt.png")
    chart_moving(a, OUT / "s2_moving.png")
    text = summary(cfg, timing, a)
    (OUT / "s2_summary.txt").write_text(text)
    print(text)
    print(f"Wrote {len(scenes)} scenes to {SCENE_DIR.relative_to(ROOT)}/, "
          f"{len(a.rows)} result rows and 5 charts to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
