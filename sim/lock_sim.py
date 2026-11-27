#!/usr/bin/env python3
"""
S3: lock-on simulation (docs/PLAN.md task S3), the main simulation activity.

Implementation: Claude (Anthropic), to Joe Gould's design; reviewed by Joe Gould.
No code adapted. The physics (objects, beam, noise, dropouts) is S2's
sim/scene.py; the controller is the REAL firmware C code (scan_map,
sweep_plan, target_track, lock_loop), loaded from
host_tests/build/liblock_shim.so (built by `make -C host_tests shim`).

DESIGN QUESTIONS
    Q1  SC8: does LOCK lock within 2 passes, keep the lock on a tube moved at
        ~10 cm/s at 50 cm, return to a full sweep within 2 s of removal, and
        never false-lock in 2 minutes of an empty scene?
    Q2  Which APP_LOCK_* values: DIST_TOL, MIN_BINS, CONFIRM_SWEEPS,
        SECTOR_HALF, LOST_PINGS, RESWEEP, BRIDGE_BINS? (lock time, bearing
        error, false locks, lost-target time, removal time)
    Q3  Bridging (APP_LOCK_BRIDGE_BINS 0 vs 1): bearing error with and without,
        and does it merge two dowels that should stay apart?
    Q4  SECTOR_HALF: bearing error with the target centred vs off-centre in
        the sector, how often the sector clips the smear (edge flag), and
        whether recentring fixes it.
    Q5  Resweep: does a lock survive the periodic full pass at 5 and 10 cm/s,
        and why not (loss causes); a still target with a closer object
        elsewhere is reported separately.

METHOD
    Closed loop, one ping per period (S1: 60 ms): the C lock_loop picks the
    angle, sim/scene.py's ping() answers from a 2D scene at that time
    (moving objects move between pings), the reading goes into the C
    scan_map and lock_loop_on_reading(). Every default is read from
    main/app_config.h. Random numbers are seeded per run, so the outputs are
    identical on every run. Every loss is logged with its cause: on_ping
    misses / on_pass gate fail / on_pass no cluster. Bearing error = reported
    centre minus the true bearing at the moment the beam crossed that centre.
    Candidate fixes are run through an EXPERIMENT copy of the controller in
    the shim (lock_shim.c, switches off = identical to lock_loop, checked
    here every run); none of them is in the firmware.
    C = Python on the S2 logs: host_tests/test_scenes (its result is quoted).
    That test uses max age = ONE PASS (the per-pass grouping of scene.py);
    the firmware (lock_loop) uses one pass + one ping, which keeps the real
    4.5 s-old end reading of the previous pass (the bounce sweep refreshes the
    end bins only every other pass, D-FADE).

ASSUMPTIONS (S2's sensor model S2-A1..A10 unchanged; plus)
    S3-A1  Hand movement (T-LOCK): the tube's centre moves along the 50 cm arc
           (tangential) at a constant speed, back and forth between 45 and
           135 deg, turning instantly; it starts 10 s in (after the lock).
           One radial run: straight away from the sensor at 10 cm/s from
           45 cm. Real hands are jerkier.                      -> T-LOCK video
    S3-A2  Ping period = S1's 60 ms for every step (sector walk-ins too).
                                                               -> B1, I7
    S3-A3  Removal is instant (t_off).                         -> T-LOCK
    S3-A4  "Back to full sweep" = lock_loop's plan is FULL again.
    S3-A5  Noisy sensor = S2-A5 (10 % dropouts, 2 % ghosts), for false locks
           and false losses only.                              -> T-XTALK, I7

CONFIRM ON HARDWARE
    T-LOCK (SC8): passes to lock, hand movement at 10 cm/s, removal time,
    2 min empty. I7: replay real LOCK recordings through the same C code.

OUTPUTS (docs/evidence/sim/)
    s3_summary.txt, s3_results.csv   every number below
    s3_following.png   locked time vs speed for the candidate settings
    s3_resweep.png     resweep outcome per variant
    s3_bridge.png      bridging: bearing error and two-dowel merge
    s3_timeline.png    one 10 cm/s run: why the sector loses the target

    python sim/lock_sim.py
"""
from __future__ import annotations

import ctypes
import math
import subprocess
import sys
from dataclasses import dataclass, field

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from appcfg import CONFIG_H, EVIDENCE_SIM, ROOT, parse_config
import scene as s2
import sweep_timing

OUT = EVIDENCE_SIM
NEEDED = sorted(set(s2.NEEDED + [
    "APP_LOCK_CONFIRM_SWEEPS", "APP_LOCK_SECTOR_HALF_DEG", "APP_LOCK_LOST_PINGS",
    "APP_LOCK_RESWEEP_S", "APP_LOCK_BRIDGE_BINS",
]))
SHIM = ROOT / "host_tests" / "build" / "liblock_shim.so"

# ls_new parameter order (host_tests/lock_shim.c enum P_*)
PARAMS = ["min_deg", "max_deg", "step_deg", "dist_tol", "min_bins", "confirm", "lost_pings",
          "max_range", "bridge", "gate", "sector_half", "resweep_ms", "period_ms",
          "start_deg", "bin_deg"]
STATUS = {"OK": 1, "NOECHO": 2, "FAIL": 3}
SEARCHING, CANDIDATE, LOCKED = 0, 1, 2
PLAN_FULL, PLAN_SECTOR, PLAN_RESWEEP = 0, 1, 2
CAUSES = {1: "on_ping misses", 2: "on_pass gate fail", 3: "on_pass no cluster"}


def load():
    cfg = s2.parse_config(CONFIG_H, NEEDED)
    tm = sweep_timing.Model(cfg)
    args = (cfg["APP_SWEEP_STEP_DEG"], cfg["APP_US_PING_GAP_MS"], cfg["APP_US_MAX_RANGE_CM"],
            "stop-and-ping")
    timing = dict(period_ms=tm.period_ms(*args), pass_ms=tm.pass_s(*args) * 1000.0)
    return cfg, timing


def build_shim():
    r = subprocess.run(["make", "-s", "-C", str(ROOT / "host_tests"), "shim"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("building the shim failed:\n" + r.stdout + r.stderr)
    lib = ctypes.CDLL(str(SHIM))
    lib.ls_new.restype = ctypes.c_void_p
    lib.ls_new.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
    lib.ls_free.argtypes = [ctypes.c_void_p]
    lib.ls_next.restype = ctypes.c_float
    lib.ls_next.argtypes = [ctypes.c_void_p]
    lib.ls_step.restype = ctypes.c_int
    lib.ls_step.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_float, ctypes.c_float,
                            ctypes.c_int]
    lib.ls_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
    lib.ls_new_x.restype = ctypes.c_void_p
    lib.ls_new_x.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int,
                             ctypes.POINTER(ctypes.c_double)]
    return lib


# EXPERIMENT switches (host_tests/lock_shim.c xflags_t). Not firmware.
XFLAGS = ["no_ping_resweep", "widen_dps", "nearest_bearing", "edge_recentre", "lead_max_dps",
          "jump_in"]


def base_params(cfg, timing) -> dict:
    """Every default comes from app_config.h (gate 0 -> lock_loop uses the sector half)."""
    return dict(
        min_deg=cfg["APP_SWEEP_MIN_DEG"], max_deg=cfg["APP_SWEEP_MAX_DEG"],
        step_deg=cfg["APP_SWEEP_STEP_DEG"], dist_tol=cfg["APP_LOCK_DIST_TOL_CM"],
        min_bins=cfg["APP_LOCK_MIN_BINS"], confirm=cfg["APP_LOCK_CONFIRM_SWEEPS"],
        lost_pings=cfg["APP_LOCK_LOST_PINGS"], max_range=cfg["APP_US_MAX_RANGE_CM"],
        bridge=cfg["APP_LOCK_BRIDGE_BINS"], gate=0.0,
        sector_half=cfg["APP_LOCK_SECTOR_HALF_DEG"], resweep_ms=cfg["APP_LOCK_RESWEEP_S"] * 1000.0,
        period_ms=timing["period_ms"], start_deg=cfg["APP_SWEEP_MIN_DEG"],
        bin_deg=cfg["APP_SWEEP_STEP_DEG"])


class Loop:
    """One lock_loop instance in the shim."""

    def __init__(self, lib, params: dict, x: dict | None = None):
        self.lib = lib
        arr = (ctypes.c_double * len(PARAMS))(*[float(params[k]) for k in PARAMS])
        if x is None:
            self.h = lib.ls_new(arr, len(PARAMS))
        else:
            xa = (ctypes.c_double * len(XFLAGS))(*[float(x.get(k, 0)) for k in XFLAGS])
            self.h = lib.ls_new_x(arr, len(PARAMS), xa)
        if not self.h:
            raise RuntimeError("ls_new failed")
        self._out = (ctypes.c_double * 16)()

    def __del__(self):
        if getattr(self, "h", None):
            self.lib.ls_free(self.h)

    def next(self) -> float:
        return float(self.lib.ls_next(self.h))

    def step(self, t_ms: int, angle: float, dist: float, status: str) -> int:
        return self.lib.ls_step(self.h, t_ms, angle, dist, STATUS[status])

    def info(self) -> dict:
        self.lib.ls_info(self.h, self._out)
        o = list(self._out)
        return dict(state=int(o[0]), plan=int(o[1]), valid=bool(o[2]), centre=o[3], left=o[4],
                    right=o[5], dist=o[6], edge=bool(o[7]), n=int(o[8]), misses=int(o[9]),
                    seen=int(o[10]), angle=o[11], cause=int(o[12]), pass_end=bool(o[13]),
                    pass_kind=int(o[14]), gate_fail_centre=o[15])


# --------------------------------------------------------------- world ----
@dataclass
class ArcTube(s2.Circle):
    """T1 moved by hand along an arc at a fixed range (T-LOCK method):
    still until t_move, then back and forth between b_lo and b_hi at v_cms
    (speed of the centre along the arc), turning instantly at the ends."""
    b0: float = 90.0
    b_lo: float = 45.0
    b_hi: float = 135.0
    v_cms: float = 0.0
    t_move: float = 0.0
    R: float = 52.5                 # range of the centre (near surface 50 cm)

    def bearing(self, t):
        if self.v_cms <= 0 or t <= self.t_move:
            return self.b0
        dps = math.degrees(self.v_cms / self.R)
        span = self.b_hi - self.b_lo
        s = (self.b0 - self.b_lo) + dps * (t - self.t_move) / 1000.0
        s %= 2 * span
        return self.b_lo + (s if s <= span else 2 * span - s)

    def centre(self, t):
        return s2._polar(self.bearing(t), self.R)


def arc_tube(bearing, near_cm, v_cms=0.0, t_move=0.0, b_lo=45.0, b_hi=135.0, **kw):
    r = s2.T1_D / 2
    return ArcTube("T1", "T1", 0.0, 0.0, r, b0=bearing, b_lo=b_lo, b_hi=b_hi, v_cms=v_cms,
                   t_move=t_move, R=near_cm + r, **kw)


def radial_tube(bearing, near_cm, v_cms, t_move):
    """T1 moving straight away from the sensor at v_cms from t_move."""
    r = s2.T1_D / 2
    x, y = s2._polar(bearing, near_cm + r)
    a = math.radians(bearing)

    @dataclass
    class Radial(s2.Circle):
        def centre(self, t):
            dt = max(0.0, t - t_move) / 1000.0
            return x + v_cms * dt * math.cos(a), y + v_cms * dt * math.sin(a)

    return Radial("T1", "T1", x, y, r)


# ----------------------------------------------------------------- run ----
@dataclass
class RunLog:
    t: list = field(default_factory=list)
    angle: list = field(default_factory=list)
    status: list = field(default_factory=list)
    info: list = field(default_factory=list)


def run(lib, cfg, timing, objs, params, dur_ms, seed, sensor=s2.Sensor(), x=None):
    rng = np.random.default_rng(seed)
    loop = Loop(lib, params, x)
    period = timing["period_ms"]
    log = RunLog()
    k = 0
    while True:
        t = int(round(k * period))
        if t >= dur_ms:
            break
        a = loop.next()
        d, st = s2.ping(objs, t, a, sensor, cfg, rng, failing=False)
        loop.step(t, a, d, st)
        log.t.append(t)
        log.angle.append(a)
        log.status.append(st)
        log.info.append(loop.info())
        k += 1
    return log


def events(log: RunLog):
    """Lock / loss events: [(t, 'lock'|'loss', detail dict)]."""
    ev, prev, prev_plan = [], SEARCHING, PLAN_FULL
    for t, i in zip(log.t, log.info):
        if i["state"] == LOCKED and prev != LOCKED:
            ev.append((t, "lock", dict(centre=i["centre"])))
        if prev == LOCKED and i["state"] != LOCKED:
            # plan = the plan in force when the lock was lost (before the switch)
            ev.append((t, "loss", dict(cause=CAUSES.get(i["cause"], "?"), plan=prev_plan,
                                       other=i["gate_fail_centre"])))
        prev, prev_plan = i["state"], i["plan"]
    return ev


def pass_ends(log: RunLog, obj=None):
    """Per on_pass: (t, kind, state, centre, edge, n, truth bearing when the
    beam crossed the reported centre in that pass)."""
    out, start = [], 0
    for k, i in enumerate(log.info):
        if not i["pass_end"]:
            continue
        truth = None
        if obj is not None and i["valid"]:
            seg = range(start, k + 1)
            j = min(seg, key=lambda m: abs(log.angle[m] - i["centre"]))
            truth = obj.truth(log.t[j])["bearing_deg"]
        out.append(dict(t=log.t[k], kind=i["pass_kind"], state=i["state"], centre=i["centre"],
                        edge=i["edge"], n=i["n"], valid=i["valid"], truth=truth))
        start = k + 1
    return out


@dataclass
class JumpTube(ArcTube):
    """Still T1 that jumps to b0 + jump_deg at t_jump (Q4 off-centre test)."""
    jump_deg: float = 0.0
    t_jump: float = 1e18

    def bearing(self, t):
        return self.b0 + (self.jump_deg if t >= self.t_jump else 0.0)


# ------------------------------------------------------------ metrics ----
def seed_of(*parts) -> int:
    return s2.scene_seed("|".join(str(x) for x in parts), 0)


def first_lock(log):
    return next((t for t, i in zip(log.t, log.info) if i["state"] == LOCKED), None)


def passes_to_lock(log):
    """FULL pass ends up to and including the one that locked (None: never)."""
    n = 0
    for i in log.info:
        if i["pass_end"] and i["pass_kind"] == PLAN_FULL:
            n += 1
            if i["state"] == LOCKED:
                return n
    return None


def locked_frac(log, t0):
    st = [i["state"] for t, i in zip(log.t, log.info) if t >= t0]
    return sum(x == LOCKED for x in st) / len(st) if st else 0.0


def losses(log, t0=0):
    return [(t, d["cause"], d["plan"]) for t, k, d in events(log) if k == "loss" and t >= t0]


def sector_stats(log, obj, t0):
    pe = [e for e in pass_ends(log, obj) if e["t"] >= t0 and e["kind"] == PLAN_SECTOR
          and e["state"] == LOCKED and e["valid"]]
    err = [abs(e["centre"] - e["truth"]) for e in pe]
    edge = [e["edge"] for e in pe]
    return err, edge


def resweep_outcomes(log, objs):
    """Each resweep: 'kept' (same object as before it), 'switched' (still
    LOCKED but now on ANOTHER object: a silent target swap), or the loss cause.
    The object = the present object whose true bearing is nearest the target."""
    def which(t, c):
        live = [j for j, o in enumerate(objs) if o.present(t)]
        return min(live, key=lambda j: abs(objs[j].truth(t)["bearing_deg"] - c)) if live else None

    out, prev, start = [], PLAN_FULL, None
    for t, i in zip(log.t, log.info):
        if prev == PLAN_SECTOR and i["plan"] == PLAN_RESWEEP:
            start = which(t, i["centre"])
        if prev == PLAN_RESWEEP and i["plan"] != PLAN_RESWEEP:
            if i["plan"] == PLAN_SECTOR:
                out.append("kept" if which(t, i["centre"]) == start else "switched")
            else:
                out.append(CAUSES.get(i["cause"], "?"))
        prev = i["plan"]
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


class Results:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, exp, case, variant, metric, value):
        self.rows.append(dict(exp=exp, case=case, variant=variant, metric=metric,
                              value=(f"{value:.3f}" if isinstance(value, float) else value)))


PLAN_NAME = {PLAN_FULL: "full", PLAN_SECTOR: "sector", PLAN_RESWEEP: "resweep"}
SEEDS = 10
MOVE_T0 = 10000                    # S3-A1: movement starts after the lock
SC8_DPS = math.degrees(10.0 / 52.5)  # 10 cm/s at the 50 cm arc = 10.9 deg/s


def tally(loss_list):
    c: dict[str, int] = {}
    for _, cause, plan in loss_list:
        k = f"{cause} ({PLAN_NAME[plan]})"
        c[k] = c.get(k, 0) + 1
    return c


# -------------------------------------------------------- experiments ----
def exp_equivalence(lib, cfg, timing, P):
    """The EXPERIMENT controller with all switches off == lock_loop."""
    n = diff = 0
    for v in (0, 10):
        for sd in range(3):
            fn = lambda: [arc_tube(90, 50, v_cms=v, t_move=MOVE_T0)]
            a = run(lib, cfg, timing, fn(), P, 40000, seed=sd)
            b = run(lib, cfg, timing, fn(), P, 40000, seed=sd, x={})
            n += len(a.t)
            diff += sum(1 for i, j, x, y in zip(a.info, b.info, a.angle, b.angle) if i != j or x != y)
    return n, diff


def exp_static(lib, cfg, timing, P, R):
    """Q1 (SC8 lock), Q2, Q3 in LOCK: lock passes, bearing error, edge rate."""
    cases = [(b, 50) for b in s2.T1_BEARINGS] + [(90, 100), (90, 150)]
    out = {}
    for bridge in (0, 1):
        p = dict(P, bridge=bridge)
        for b, r in cases:
            lp, err, edge, nloss = [], [], [], 0
            for k in range(SEEDS):
                obj = arc_tube(b, r)
                log = run(lib, cfg, timing, [obj], p, 30000, seed=seed_of("static", b, r, k))
                lp.append(passes_to_lock(log))
                e, g = sector_stats(log, obj, 0)
                err += e
                edge += g
                nloss += len(losses(log))
            got = [x for x in lp if x is not None]
            o = dict(lock_max=max(got) if got else None, within2=sum(1 for x in got if x <= 2),
                     never=len(lp) - len(got), err_mean=mean(err), err_max=max(err) if err else float("nan"),
                     edge_pct=100.0 * mean([float(x) for x in edge]), losses=nloss)
            out[(bridge, b, r)] = o
            case = f"T1 {b}deg {r}cm"
            for m, v in o.items():
                R.add("static", case, f"bridge {bridge}", m, v)
    return out


def exp_bridge_sweep(cfg, timing, R):
    """Q3 in SWEEP (Python rule = C, proven by test_scenes): edge-midpoint
    error of T1 and the two-dowel merge, 40 passes, bridge 0 vs 1."""
    step, tol, mb = cfg["APP_SWEEP_STEP_DEG"], cfg["APP_LOCK_DIST_TOL_CM"], int(cfg["APP_LOCK_MIN_BINS"])
    sensor = s2.Sensor()
    err = {0: [], 1: []}
    missed = {0: 0, 1: 0}
    for b in (30, 60, 90, 120, 150):
        for r in s2.T1_RANGES:
            sc = s2.Scene("x", "", [s2.tube("T1", "T1", b, r, s2.T1_D)])
            rd, _ = s2.run_scene(sc, cfg, timing, sensor, seed=seed_of("bridge", b, r), passes=40)
            for pr in s2.by_pass(rd):
                for br in (0, 1):
                    cl = s2.clusters_illustrative(pr, step, tol, mb, br)
                    if not cl:
                        missed[br] += 1
                        continue
                    c = min(cl, key=lambda c: c["dist"])
                    err[br].append(abs(c["centre"] - b))
    merge = {0: {}, 1: {}}
    for sep in s2.T3_SEPS:
        objs = [s2.tube("T3a", "T3", 90 - sep / 2, 50, s2.T3_D), s2.tube("T3b", "T3", 90 + sep / 2, 50, s2.T3_D)]
        rd, _ = s2.run_scene(s2.Scene("x", "", objs), cfg, timing, sensor, seed=seed_of("merge", sep), passes=40)
        for br in (0, 1):
            two = sum(1 for pr in s2.by_pass(rd) if len(s2.clusters_illustrative(pr, step, tol, mb, br)) >= 2)
            merge[br][sep] = 100.0 * two / 40
    for br in (0, 1):
        e = sorted(err[br])
        R.add("bridge_sweep", "T1 30-150deg x 50/100/150cm, 40 passes", f"bridge {br}", "err_mean", mean(e))
        R.add("bridge_sweep", "T1 30-150deg x 50/100/150cm, 40 passes", f"bridge {br}", "err_p95", e[int(0.95 * len(e))])
        R.add("bridge_sweep", "T1 30-150deg x 50/100/150cm, 40 passes", f"bridge {br}", "err_max", e[-1])
        R.add("bridge_sweep", "T1 30-150deg x 50/100/150cm, 40 passes", f"bridge {br}", "passes_missed", missed[br])
        for sep, v in merge[br].items():
            R.add("bridge_merge", f"two T3 at 50cm, {sep:g}deg apart", f"bridge {br}", "pct_passes_two", v)
    return err, missed, merge


def exp_offset(lib, cfg, timing, P, R):
    """Q4: target centred, then jumps off-centre by `jump` deg at 20 s."""
    out = {}
    for half in (10, 12, 15, 20):
        p = dict(P, sector_half=half, resweep_ms=0)
        for jump in (0, 5, 10, 14):
            kept = 0
            first_err, first_edge, settle = [], [], []
            cerr, cedge = [], []
            for k in range(SEEDS):
                tj = 20000 + 97 * k
                obj = JumpTube("T1", "T1", 0, 0, s2.T1_D / 2, b0=90.0, R=52.5, jump_deg=jump, t_jump=tj)
                log = run(lib, cfg, timing, [obj], p, 32000, seed=seed_of("offset", half, jump, k))
                kept += not losses(log, tj)
                pe = [e for e in pass_ends(log, obj) if e["kind"] == PLAN_SECTOR and e["state"] == LOCKED
                      and e["valid"]]
                cerr += [abs(e["centre"] - e["truth"]) for e in pe if e["t"] < tj]
                cedge += [e["edge"] for e in pe if e["t"] < tj]
                after = [e for e in pe if e["t"] > tj + 960]   # first pass that saw the new position
                if after:
                    first_err.append(abs(after[0]["centre"] - after[0]["truth"]))
                    first_edge.append(after[0]["edge"])
                    n = next((j + 1 for j, e in enumerate(after) if abs(e["centre"] - e["truth"]) <= 2.0), None)
                    settle.append(n)
            o = dict(kept=kept, first_err_mean=mean(first_err), first_edge_pct=100 * mean([float(x) for x in first_edge]),
                     settle_max=max([x for x in settle if x is not None], default=None),
                     centred_err_mean=mean(cerr), centred_err_max=max(cerr) if cerr else float("nan"),
                     centred_edge_pct=100 * mean([float(x) for x in cedge]))
            out[(half, jump)] = o
            for m, v in o.items():
                R.add("offset", f"jump {jump}deg", f"half {half}", m, v)
    return out


def exp_removal(lib, cfg, timing, P, R):
    """Q1 (SC8 removal), Q2 LOST_PINGS: removal time vs false losses."""
    out = {}
    for lost in (3, 6, 9, 12):
        p = dict(P, lost_pings=lost)
        times = []
        for k in range(SEEDS):
            t_off = 15000 + 173 * k
            log = run(lib, cfg, timing, [arc_tube(90, 50, t_off=t_off)], p, 22000, seed=seed_of("rm", lost, k))
            tf = next((t for t, i in zip(log.t, log.info) if t >= t_off and i["plan"] == PLAN_FULL), None)
            times.append(tf - t_off if tf is not None else None)
        fl = {}
        for sname, sensor in (("normal", s2.Sensor()), ("noisy", s2.Sensor(**s2.NOISY))):
            n = 0
            for k in range(5):
                log = run(lib, cfg, timing, [arc_tube(90, 50)], p, 70000, seed=seed_of("fl", lost, sname, k),
                          sensor=sensor)
                n += len(losses(log))
            fl[sname] = n / 5.0           # per run of ~60 s locked
        got = [x for x in times if x is not None]
        o = dict(removal_max_ms=max(got) if got else None, removal_mean_ms=mean(got),
                 never=len(times) - len(got), false_losses_per_min_normal=fl["normal"],
                 false_losses_per_min_noisy=fl["noisy"])
        out[lost] = o
        for m, v in o.items():
            R.add("removal", "T1 90deg 50cm", f"lost_pings {lost}", m, v)
    return out


def exp_false_lock(lib, cfg, timing, P, R):
    """Q1 (SC8 no false lock), Q2 CONFIRM / MIN_BINS: 2 min empty."""
    out = {}
    for sname, sensor in (("normal", s2.Sensor()), ("noisy", s2.Sensor(**s2.NOISY))):
        for confirm in (1, 2, 3):
            for mb in (1, 2, 3):
                p = dict(P, confirm=confirm, min_bins=mb)
                locks = 0
                for k in range(SEEDS):
                    log = run(lib, cfg, timing, [], p, 120000, seed=seed_of("empty", sname, confirm, mb, k),
                              sensor=sensor)
                    locks += sum(1 for _, kind, _ in events(log) if kind == "lock")
                out[(sname, confirm, mb)] = locks
                R.add("false_lock", f"empty 2 min, {sname} sensor", f"confirm {confirm} min_bins {mb}",
                      "locks_in_10_runs", locks)
    return out


FOLLOW_VARIANTS = [
    ("firmware", {}, None),
    ("lost_pings 9", dict(lost_pings=9), None),
    ("lost_pings 12", dict(lost_pings=12), None),
    ("dist_tol 12", dict(dist_tol=12), None),
    ("min_bins 1", dict(min_bins=1), None),
    ("sector_half 12", dict(sector_half=12), None),
    ("lost 9 + min_bins 1", dict(lost_pings=9, min_bins=1), None),
    ("lost 9 + half 12", dict(lost_pings=9, sector_half=12), None),
    ("EXP F1 edge recentre", {}, dict(edge_recentre=1)),
    ("EXP F2 lead", {}, dict(lead_max_dps=20)),
    ("EXP (e) jump-in + lost 9", dict(lost_pings=9), dict(jump_in=1)),
]
FOLLOW_CASES = [("tangential 5 cm/s", lambda: [arc_tube(90, 50, v_cms=5, t_move=MOVE_T0)], 70000),
                ("tangential 10 cm/s", lambda: [arc_tube(90, 50, v_cms=10, t_move=MOVE_T0)], 70000),
                ("tangential 15 cm/s", lambda: [arc_tube(90, 50, v_cms=15, t_move=MOVE_T0)], 70000),
                ("radial away 10 cm/s", lambda: [radial_tube(90, 45, 10, MOVE_T0)], 19000)]


def exp_follow(lib, cfg, timing, P, R):
    """Q1 (SC8 keep the lock), Q2: following with resweeps OFF (isolated)."""
    out = {}
    for vname, over, x in FOLLOW_VARIANTS:
        p = dict(P, **over, resweep_ms=0)
        for cname, fn, dur in FOLLOW_CASES:
            fr, ll, err = [], [], []
            for k in range(8):
                objs = fn()
                log = run(lib, cfg, timing, objs, p, dur, seed=seed_of("follow", cname, k), x=x)
                fr.append(locked_frac(log, MOVE_T0))
                ll += losses(log, MOVE_T0)
                err += sector_stats(log, objs[0], MOVE_T0)[0]
            minutes = 8 * (dur - MOVE_T0) / 60000.0
            o = dict(locked_pct=100 * mean(fr), losses_per_min=len(ll) / minutes,
                     err_mean=mean(err), err_max=max(err) if err else float("nan"), causes=tally(ll))
            out[(vname, cname)] = o
            for m, v in o.items():
                R.add("follow", cname, vname, m, v if m != "causes" else "; ".join(f"{a}: {b}" for a, b in v.items()))
    return out


RESWEEP_VARIANTS = [("firmware", None), ("(c) no on_ping in resweep", dict(no_ping_resweep=1)),
                    ("(a) (c) + gate widened 10.9 deg/s", dict(no_ping_resweep=1, widen_dps=SC8_DPS)),
                    ("(b) (c) + nearest bearing", dict(no_ping_resweep=1, nearest_bearing=1))]
RESWEEP_CASES = [("still", lambda: [arc_tube(90, 50)]),
                 ("still + closer object at 140deg 30cm from 15 s",
                  lambda: [arc_tube(90, 50), s2.tube("T1b", "T1", 140, 30, s2.T1_D, t_on=15000)]),
                 ("tangential 5 cm/s", lambda: [arc_tube(90, 50, v_cms=5, t_move=MOVE_T0)]),
                 ("tangential 10 cm/s", lambda: [arc_tube(90, 50, v_cms=10, t_move=MOVE_T0)])]


def exp_resweep(lib, cfg, timing, P, R):
    """Q5: the periodic full pass (APP_LOCK_RESWEEP_S) while locked."""
    out = {}
    for lost in (int(P["lost_pings"]), 9):
        for vname, x in RESWEEP_VARIANTS:
            p = dict(P, lost_pings=lost)
            for cname, fn in RESWEEP_CASES:
                oc, fr, ll = [], [], []
                for k in range(8):
                    objs = fn()
                    log = run(lib, cfg, timing, objs, p, 70000, seed=seed_of("rsw", cname, k), x=x)
                    oc += resweep_outcomes(log, objs)
                    fr.append(locked_frac(log, MOVE_T0))
                    ll += losses(log, MOVE_T0)
                o = dict(resweeps=len(oc), kept=oc.count("kept"), switched=oc.count("switched"),
                         lost_ping=oc.count(CAUSES[1]), lost_gate=oc.count(CAUSES[2]),
                         lost_nocluster=oc.count(CAUSES[3]), locked_pct=100 * mean(fr), causes=tally(ll))
                out[(lost, vname, cname)] = o
                for m, v in o.items():
                    R.add("resweep", cname, f"lost_pings {lost}, {vname}", m,
                          v if m != "causes" else "; ".join(f"{a}: {b}" for a, b in v.items()))
    return out


def scenes_result():
    """C = Python (host_tests/test_scenes), quoted from its own output."""
    r = subprocess.run(["make", "-s", "-C", str(ROOT / "host_tests"), "build/test_scenes"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return ["(test_scenes did not build)"]
    r = subprocess.run(["./build/test_scenes"], cwd=ROOT / "host_tests", capture_output=True, text=True)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith(("bridge", "scenes", "ok", "FAIL"))]


# -------------------------------------------------------------- charts ----
C1, C2, C3, C4 = s2.C1, s2.C2, s2.C3, "#f2a600"   # dataviz categorical slots 1-4
INK, INK2, GRID = s2.INK, s2.INK2, s2.GRID


def chart_following(fol, path):
    variants = ["firmware", "lost_pings 9", "lost 9 + min_bins 1"]
    cols = [C1, C2, C3]
    cases = [c[0] for c in FOLLOW_CASES]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    fig.patch.set_facecolor("white")
    s2.style_axes(ax)
    w = 0.26
    for j, (v, col) in enumerate(zip(variants, cols)):
        xs = [i + (j - 1) * w for i in range(len(cases))]
        ys = [fol[(v, c)]["locked_pct"] for c in cases]
        ax.bar(xs, ys, width=w - 0.03, color=col, label=v, zorder=2)
        for x, y in zip(xs, ys):
            ax.text(x, y + 1.5, f"{y:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.axhline(100, color=INK2, lw=0.8, ls=(0, (3, 3)), zorder=1)
    ax.set_xticks(range(len(cases)), cases, fontsize=9, color=INK)
    ax.set_ylim(0, 112)
    ax.set_ylabel("% of time locked after the move starts", fontsize=9, color=INK2)
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper right", ncols=3, bbox_to_anchor=(1, 1.13))
    s2.fig_title(fig, "S3: keeping the lock on a moving T1 at 50 cm (resweeps off)",
                 "8 runs x 60 s per bar. SC8 asks for 100 % at about 10 cm/s. No APP_LOCK_* setting reaches it "
                 "tangentially; lost_pings 9 fixes the radial case.")
    fig.subplots_adjust(top=0.78, bottom=0.12, left=0.07, right=0.99)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_resweep(rsw, lost, path):
    names = [v[0] for v in RESWEEP_VARIANTS]
    short = ["firmware", "(c)", "(a)", "(b)"]
    cols = [C1, C2, C3, C4]
    cases = [c[0] for c in RESWEEP_CASES]
    labels = ["still", "still + closer\nobject (15 s)", "tangential\n5 cm/s", "tangential\n10 cm/s"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    fig.patch.set_facecolor("white")
    s2.style_axes(ax)
    w = 0.2
    for j, (v, sv, col) in enumerate(zip(names, short, cols)):
        xs = [i + (j - 1.5) * w for i in range(len(cases))]
        for x, c in zip(xs, cases):
            o = rsw[(lost, v, c)]
            y = 100.0 * o["kept"] / o["resweeps"] if o["resweeps"] else 0.0
            ax.bar(x, y, width=w - 0.03, color=col, zorder=2, label=sv if c == cases[0] else None)
            lab = f"{o['kept']}/{o['resweeps']}" + (f"\n{o['switched']} swapped" if o["switched"] else "")
            ax.text(x, y + 1.5, lab, ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(range(len(cases)), labels, fontsize=9, color=INK)
    ax.set_ylim(0, 115)
    ax.set_ylabel("% of resweeps that keep the SAME object", fontsize=9, color=INK2)
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper right", ncols=4, bbox_to_anchor=(1, 1.13))
    s2.fig_title(fig, f"S3: does a resweep keep the SAME object? (lost_pings {lost}, every 10 s, 8 runs x 60 s)",
                 "(c) no on_ping in a resweep; (a) = (c) + gate widened 10.9 deg/s; (b) = (c) + nearest last "
                 "bearing. Labels: kept / resweeps. Experiments.")
    fig.subplots_adjust(top=0.78, bottom=0.16, left=0.07, right=0.99)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_bridge(err, missed, merge, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    fig.patch.set_facecolor("white")
    ax = axes[0]
    s2.style_axes(ax)
    bins = np.arange(0, 9.5, 1.0)
    for br, col in ((0, C1), (1, C2)):
        e = np.array(err[br])
        frac = [100.0 * np.mean(e > b) for b in bins]
        ax.plot(bins, frac, color=col, lw=2, marker="o", ms=5, label=f"bridge {br}")
    ax.set_xlabel("edge-midpoint error larger than (deg)", fontsize=9, color=INK2)
    ax.set_ylabel("% of passes", fontsize=9, color=INK2)
    ax.axvline(5, color=INK2, lw=0.8, ls=(0, (3, 3)))
    ax.text(5.1, ax.get_ylim()[1] * 0.6, "SC3 5 deg", fontsize=8, color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("T1, 30-150 deg x 50/100/150 cm, 40 passes each", fontsize=9.5, color=INK, loc="left")
    ax = axes[1]
    s2.style_axes(ax)
    seps = list(s2.T3_SEPS)[::-1]
    for br, col in ((0, C1), (1, C2)):
        ax.plot(seps, [merge[br][s] for s in seps], color=col, lw=2, marker="o", ms=5, label=f"bridge {br}")
    ax.set_xlabel("gap between the two dowels (deg)", fontsize=9, color=INK2)
    ax.set_ylabel("% of passes showing two objects", fontsize=9, color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("Two T3 dowels at 50 cm (merge check)", fontsize=9.5, color=INK, loc="left")
    s2.fig_title(fig, "S3: bridging one non-OK bin (APP_LOCK_BRIDGE_BINS 1) vs off (0)",
                 "Same rule in C and Python (test_scenes 190/190 passes). Left: how often the bearing error "
                 "exceeds x. Right: does bridging merge two dowels?")
    fig.subplots_adjust(top=0.80, bottom=0.13, left=0.07, right=0.99, wspace=0.22)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_timeline(lib, cfg, timing, P, path):
    """lost_pings 9 (resweeps off): the first of the FOLLOW runs that loses the
    target by 'no cluster' after at least 3 sector passes, so the picture shows
    the sector falling behind, not a loss during the first walk-in."""
    p = dict(P, lost_pings=9, resweep_ms=0)
    for k in range(8):
        obj = arc_tube(90, 50, v_cms=10, t_move=MOVE_T0)
        log = run(lib, cfg, timing, [obj], p, 70000, seed=seed_of("follow", "tangential 10 cm/s", k))
        lt = [t for t, c, _ in losses(log, MOVE_T0) if c == CAUSES[3]]
        if lt and sum(1 for t, i in zip(log.t, log.info) if i["pass_end"] and i["pass_kind"] == PLAN_SECTOR
                      and t < lt[0]) >= 3:
            break
    t_loss = lt[0] / 1000.0 if lt else 26.0
    t_lo, t_hi = max(MOVE_T0 / 1000.0 - 2, t_loss - 12), t_loss + 4
    t = np.array(log.t) / 1000.0
    fig, ax = plt.subplots(figsize=(11, 4.6))
    fig.patch.set_facecolor("white")
    s2.style_axes(ax)
    truth = [obj.truth(x)["bearing_deg"] for x in log.t]
    ax.plot(t, truth, color=INK, lw=2, label="true bearing of T1", zorder=3)
    ok = np.array([s == "OK" for s in log.status])
    ang = np.array(log.angle)
    ax.scatter(t[~ok], ang[~ok], s=9, color=GRID, edgecolors=INK2, linewidths=0.3, label="ping, no echo", zorder=2)
    ax.scatter(t[ok], ang[ok], s=12, color=C1, label="ping, echo", zorder=2)
    for tt, kind, d in events(log):
        col = C3 if kind == "lock" else C2
        ax.axvline(tt / 1000.0, color=col, lw=1.2, ls=(0, (4, 2)), zorder=1)
        if t_lo <= tt / 1000.0 <= t_hi:
            ax.text(tt / 1000.0 + 0.1, 168, "lock" if kind == "lock" else f"lost: {d['cause']}", fontsize=8,
                    color=INK2, rotation=0, va="top")
    ax.axvline(MOVE_T0 / 1000.0, color=INK2, lw=0.8)
    if t_lo < MOVE_T0 / 1000.0:
        ax.text(MOVE_T0 / 1000.0 + 0.1, 20, "starts moving, 10 cm/s", fontsize=8, color=INK2)
    ax.set_xlim(t_lo, t_hi)
    ax.set_ylim(10, 172)
    ax.set_xlabel("time (s)", fontsize=9, color=INK2)
    ax.set_ylabel("angle (deg)", fontsize=9, color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", ncols=3)
    s2.fig_title(fig, "S3: one 10 cm/s run (lost_pings 9, resweeps off): the sector falls behind the target",
                 "Each ~0.9 s sector pass is centred where T1 was at the last pass end; T1 moves ~10 deg per pass "
                 "and escapes (on_pass: no cluster).")
    fig.subplots_adjust(top=0.82, bottom=0.12, left=0.06, right=0.99)
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ------------------------------------------------------------- summary ----
def summary(cfg, timing, P, eq, sc, st, bsw, off, rm, fl, fol, rsw) -> str:
    L = []
    p = L.append
    err, missed, merge = bsw
    p("S3 lock-on simulation (sim/lock_sim.py). Real C components in the loop; S2 physics.")
    p(f"Config (app_config.h): step {cfg['APP_SWEEP_STEP_DEG']:g} deg, arc {cfg['APP_SWEEP_MIN_DEG']:g}-"
      f"{cfg['APP_SWEEP_MAX_DEG']:g}, ping {timing['period_ms']:g} ms, dist_tol {P['dist_tol']:g} cm, "
      f"min_bins {P['min_bins']:g}, confirm {P['confirm']:g}, sector_half {P['sector_half']:g}, lost_pings "
      f"{P['lost_pings']:g}, resweep {P['resweep_ms'] / 1000:g} s, bridge {P['bridge']:g}, gate = sector_half.")
    p(f"Experiment controller with all switches off vs lock_loop: {eq[0]} pings, {eq[1]} differences.")
    p("")
    p("C = Python on the S2 logs (host_tests/test_scenes, max age = ONE pass there; firmware uses pass + ping):")
    for ln in sc:
        p("  " + ln)
    p("")
    p("STATIC T1 in LOCK (10 runs x 30 s each; error = sector-pass centre vs truth)")
    p(f"  {'case':16s} {'bridge':>6s} {'lock<=2 passes':>15s} {'worst passes':>12s} {'err mean':>8s} "
      f"{'err max':>7s} {'edge %':>6s} {'losses':>6s}")
    for (br, b, r), o in st.items():
        p(f"  {f'T1 {b} deg {r} cm':16s} {br:6d} {o['within2']:>11d}/10 {str(o['lock_max']):>12s} "
          f"{o['err_mean']:8.2f} {o['err_max']:7.2f} {o['edge_pct']:6.1f} {o['losses']:6d}")
    p("")
    p("BRIDGING in SWEEP (Python rule = C): nearest-cluster edge-midpoint error, T1 at 30-150 deg x 50/100/150 cm")
    for br in (0, 1):
        e = sorted(err[br])
        p(f"  bridge {br}: mean {mean(e):.2f} deg, 95th pct {e[int(0.95 * len(e))]:.1f}, worst {e[-1]:.1f}, "
          f"passes > 5 deg {sum(1 for x in e if x > 5)}/{len(e)}, passes with no cluster {missed[br]}")
    p("  two T3 dowels at 50 cm, % of 40 passes showing two objects:")
    p("    gap (deg) " + " ".join(f"{s:>5g}" for s in s2.T3_SEPS))
    for br in (0, 1):
        p(f"    bridge {br}  " + " ".join(f"{merge[br][s]:5.0f}" for s in s2.T3_SEPS))
    p("")
    p("SECTOR_HALF: centred, then the target jumps off-centre at 20 s (resweeps off, 10 runs)")
    p(f"  {'half':>4s} {'jump':>4s} {'kept':>5s} {'centred err mean/max':>21s} {'centred edge %':>14s} "
      f"{'1st pass err':>12s} {'1st pass edge %':>15s} {'passes to <=2 deg':>17s}")
    for (half, jump), o in off.items():
        p(f"  {half:4d} {jump:4d} {o['kept']:>3d}/10 {o['centred_err_mean']:10.2f} / {o['centred_err_max']:5.2f}"
          f" {o['centred_edge_pct']:14.1f} {o['first_err_mean']:12.2f} {o['first_edge_pct']:15.1f} "
          f"{str(o['settle_max']):>17s}")
    p("")
    p("REMOVAL and LOST_PINGS (removal: 10 runs; false losses: still T1, 5 runs x ~60 s locked)")
    for lost, o in rm.items():
        p(f"  lost_pings {lost:2d}: back to full sweep worst {o['removal_max_ms']} ms, mean "
          f"{o['removal_mean_ms']:.0f} ms (never: {o['never']}); false losses per run: normal "
          f"{o['false_losses_per_min_normal']:.1f}, noisy {o['false_losses_per_min_noisy']:.1f}")
    p("")
    p("FALSE LOCKS, empty scene 2 min x 10 runs (lock events in total)")
    p("  " + " " * 18 + "  ".join(f"min_bins {m}" for m in (1, 2, 3)))
    for sname in ("normal", "noisy"):
        for c in (1, 2, 3):
            p(f"  {sname:6s} confirm {c}  " + "  ".join(f"{fl[(sname, c, m)]:10d}" for m in (1, 2, 3)))
    p("")
    p("FOLLOWING (resweeps off; 8 runs; tangential = along the 50 cm arc, 45-135 deg; S3-A1)")
    for cname, _, _ in FOLLOW_CASES:
        p(f"  {cname}:")
        for vname, _, _ in FOLLOW_VARIANTS:
            o = fol[(vname, cname)]
            cs = "; ".join(f"{a}: {b}" for a, b in o["causes"].items()) or "no losses"
            p(f"    {vname:22s} locked {o['locked_pct']:5.1f} %  losses/min {o['losses_per_min']:4.1f}  "
              f"err mean/max {o['err_mean']:4.1f}/{o['err_max']:4.1f}  [{cs}]")
    p("")
    p("RESWEEP every 10 s (8 runs x 60 s). Still + closer object is the 'nearest cluster across the full arc'")
    p("case, NOT a movement failure: it is listed apart from the moving cases. 'kept' = same object after the")
    p("resweep; 'SWITCHED' = still LOCKED but silently on another object (counted as a failure).")
    for lost in sorted({k[0] for k in rsw}):
        p(f"  lost_pings {lost}:")
        for vname, _ in RESWEEP_VARIANTS:
            p(f"    {vname}")
            for cname, _ in RESWEEP_CASES:
                o = rsw[(lost, vname, cname)]
                p(f"      {cname:48s} kept {o['kept']:2d}/{o['resweeps']:2d}, SWITCHED object {o['switched']:2d} "
                  f"(lost: ping {o['lost_ping']}, "
                  f"gate {o['lost_gate']}, no cluster {o['lost_nocluster']})  locked {o['locked_pct']:5.1f} %")
    return "\n".join(L) + "\n"


def main() -> None:
    cfg, timing = load()
    lib = build_shim()
    P = base_params(cfg, timing)
    R = Results()
    eq = exp_equivalence(lib, cfg, timing, P)
    if eq[1]:
        sys.exit(f"experiment controller differs from lock_loop in {eq[1]} pings: fix the shim first")
    sc = scenes_result()
    st = exp_static(lib, cfg, timing, P, R)
    bsw = exp_bridge_sweep(cfg, timing, R)
    off = exp_offset(lib, cfg, timing, P, R)
    rm = exp_removal(lib, cfg, timing, P, R)
    fl = exp_false_lock(lib, cfg, timing, P, R)
    fol = exp_follow(lib, cfg, timing, P, R)
    rsw = exp_resweep(lib, cfg, timing, P, R)

    OUT.mkdir(parents=True, exist_ok=True)
    import csv
    with open(OUT / "s3_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["exp", "case", "variant", "metric", "value"])
        w.writeheader()
        w.writerows(R.rows)
    chart_following(fol, OUT / "s3_following.png")
    chart_resweep(rsw, 9, OUT / "s3_resweep.png")
    chart_bridge(*bsw, OUT / "s3_bridge.png")
    chart_timeline(lib, cfg, timing, P, OUT / "s3_timeline.png")
    text = summary(cfg, timing, P, eq, sc, st, bsw, off, rm, fl, fol, rsw)
    (OUT / "s3_summary.txt").write_text(text)
    print(text)
    print(f"Wrote {len(R.rows)} result rows and 4 charts to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
