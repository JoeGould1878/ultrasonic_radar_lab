#!/usr/bin/env python3
"""
S1: sweep timing model (docs/PLAN.md task S1).

Implementation: Claude (Anthropic), to Joe Gould's design question; reviewed by Joe Gould.
Credits / sources: HC-SR04 and SG90 datasheet figures as noted below. No code adapted.

DESIGN QUESTION
    Which step size (D-STEP), scan style (D-SCAN: stop-and-ping vs
    ping-while-moving) and ping gap (D-GAP) give an acceptable sweep time
    (SC4: one 150 degree pass in <= 5 s) without leaving gaps wider than the
    ~15 degree beam, and what should APP_FADE_SWEEPS be?

METHOD
    A closed-form timing model, no randomness. Every default is parsed from
    main/app_config.h (APP_SERVO_*, APP_SWEEP_*, APP_US_*, APP_FADE_SWEEPS),
    so if a value there changes, re-running this script updates the evidence.
    The grid is step 1/2/3/5 deg x ping gap 30/40/60 ms x range 100/150/200 cm
    x scan style (stop-and-ping / ping-while-moving).

    Per reading:
      echo wait   = sensor overhead + echo timeout(range)
                    timeout(range) = 2*range/c + the margin app_config.h adds
                    on top of 2*APP_US_MAX_RANGE_CM/c
      stop-and-ping:      T = max(gap, echo wait + step*speed + settle, hold)
                          (ping, wait for the echo, move, settle, ping again;
                          the move + settle happen inside the ping gap)
      ping-while-moving:  T = max(gap, echo wait, hold)
                          servo moves continuously at w = step / T
    where hold = how long the sensor keeps ECHO high when nothing answers
    (worst case: an empty scene, every ping times out).

    The sweep bounces between APP_SWEEP_MIN_DEG and APP_SWEEP_MAX_DEG (like
    sweep_plan FULL), so a pass has N = arc/step + 1 readings and N - 1
    intervals; the end bins are read once per reversal.
      pass time        = (N - 1) * T
      point age        = time until a bin is read again. Bin i is revisited
                         after 2*i or 2*(N-1-i) intervals depending on the
                         direction, so the middle bin is about 1 pass old when
                         redrawn and an end bin exactly 2 passes old.
      walker           = 0.2 m/s * point age (how far someone walking has moved
                         before their bin is read again)
      reading spacing  = chord between neighbouring readings, 2 r sin(step/2)
      beam footprint   = 2 r tan(beam/2), at 50/100/150 cm
      hits per target  = floor(beam/step): readings that see one thin target
      angle error (ping-while-moving, reading tagged with the commanded angle
                   at trigger): the real beam lags the command by up to
                   (PWM period + settle) and keeps turning during the echo
                   flight, so error = w * (lag + 2d/c). It flips sign when the
                   sweep reverses, so an object jumps by 2x this between passes.
      ghost-free range = c * gap / 2: an echo from further away than this can
                   arrive after the next trigger and be read as a near object.
    Sensitivity: the summary and the left panel of s1_scan_style.png also
    run with the no-echo hold (A6) set to 0, the best case for
    ping-while-moving, so the D-SCAN answer doesn't rest on A6.

ASSUMPTIONS (each one is something hardware can prove wrong)
    A1  Servo speed is the datasheet figure in APP_SERVO_SPEED_MS_PER_DEG
        (SG90 ~0.1 s / 60 deg at 4.8 V, rounded up to 2 ms/deg), constant,
        with no load from the sensor bracket.
    A2  Settle is ideal: after APP_SERVO_SETTLE_MS the sensor points exactly at
        the commanded angle (no overshoot or wobble left).
    A3  No echo retries: one ping per bin.
    A4  Worst-case echo wait: every ping waits the full timeout (empty scene).
    A5  Sensor overhead per ping 0.5 ms (10 us trigger + 8-cycle 40 kHz burst
        + internal delay). ASSUMED, not in app_config.h.
    A6  No-echo hold 38 ms: commonly quoted for HC-SR04 modules; some clones
        hold ECHO high much longer. A trigger sent while ECHO is still high is
        ignored. ASSUMED, not in app_config.h.
    A7  Beam: 15 deg full cone (datasheet). For a thin target at range the
        useful cone may be narrower; 8 deg is used as a pessimistic what-if,
        not a measured value.
    A8  Ping-while-moving: the servo really moves at a constant w. A real SG90
        moves in small jerks (PWM updates every 20 ms, ~1 deg deadband).
        Servo lag behind the command is taken as up to one 50 Hz PWM period
        (20 ms) plus APP_SERVO_SETTLE_MS.
    A9  Speed of sound from APP_US_TEMP_C (331.3 + 0.606 T m/s).
    A10 CPU, logging and display time are negligible next to the ping gap.

CONFIRM ON HARDWARE
    B1  Time one step of 1/2/3/5 deg and the settle (camera at 240 fps or a
        scope on the PWM + a microphone/IMU), and the pass time for the chosen
        step. Replaces A1, A2, A8.
    B2  Scope ECHO with nothing in front: hold time (A6). Scope a trigger every
        30/40/60 ms in a big room: ghost readings? Effective beam width for a
        5 cm tube at 50/100/150 cm (A7).
    I7  Compare the measured pass time and point age with this model; put the
        model-vs-real table in docs/evidence/ and update these assumptions.

OUTPUTS (docs/evidence/sim/)
    s1_sweep_timing.csv   every grid point, every output
    s1_summary.txt        the tables printed below (what the report quotes)
    s1_sweep_time.png     pass time vs ping gap, per step, for each range
    s1_scan_style.png     stop-and-ping vs ping-while-moving: time and angle error
    s1_point_age.png      point age across the arc vs fade-out time
    s1_coverage.png       reading spacing vs beam footprint; hits per target

Run:  . .venv/bin/activate && python sim/sweep_timing.py
"""
from __future__ import annotations

import csv
import io
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_H = ROOT / "main" / "app_config.h"
OUT = ROOT / "docs" / "evidence" / "sim"

# ----------------------------------------------------------------- grid ----
STEPS_DEG = [1, 2, 3, 5]
GAPS_MS = [30, 40, 60]
RANGES_CM = [100, 150, 200]
STYLES = ["stop-and-ping", "ping-while-moving"]
EVAL_DIST_CM = [50, 100, 150]

# --------------------------------------------- assumptions not in config ----
SENSOR_OVERHEAD_MS = 0.5     # A5
NO_ECHO_HOLD_MS = 38.0       # A6
BEAM_DEG = 15.0              # A7, datasheet
BEAM_PESSIMISTIC_DEG = 8.0   # A7, what-if
PWM_PERIOD_MS = 20.0         # A8, 50 Hz servo PWM
WALKER_M_S = 0.2
SC4_PASS_S = 5.0             # CONCEIVE.txt SC4
SC3_BEARING_DEG = 5.0        # CONCEIVE.txt SC3
TUBE_CM = 5.0                # CONCEIVE.txt SC1
# Fade options compared, fixed so the evidence doesn't change with app_config.h
FADE_COMPARE = ((2, "original"), (3, "D-FADE"))

# --------------------------------------------------------- chart style ----
# Categorical slots 1-4 of the dataviz reference palette (validated order).
STEP_COLOR = {1: "#257de0", 2: "#f47230", 3: "#00b894", 5: "#f2a600"}
INK = "#191919"
INK2 = "#666666"
GRID = "#e6e6e6"


def parse_config(path: Path) -> dict[str, float]:
    """Read every numeric #define from app_config.h."""
    vals: dict[str, float] = {}
    pat = re.compile(r"^\s*#define\s+(APP_\w+)\s+(-?\d+(?:\.\d+)?)f?\b")
    for line in path.read_text().splitlines():
        m = pat.match(line)
        if m:
            vals[m.group(1)] = float(m.group(2))
    needed = [
        "APP_SERVO_SPEED_MS_PER_DEG", "APP_SERVO_SETTLE_MS",
        "APP_SWEEP_MIN_DEG", "APP_SWEEP_MAX_DEG", "APP_SWEEP_STEP_DEG",
        "APP_US_MAX_RANGE_CM", "APP_US_PING_GAP_MS", "APP_US_TEMP_C",
        "APP_US_TIMEOUT_US", "APP_FADE_SWEEPS",
    ]
    missing = [n for n in needed if n not in vals]
    if missing:
        sys.exit(f"app_config.h is missing: {', '.join(missing)}")
    return vals


class Model:
    def __init__(self, cfg: dict[str, float], hold_ms: float = NO_ECHO_HOLD_MS):
        self.cfg = cfg
        self.hold_ms = hold_ms
        self.speed_ms_per_deg = cfg["APP_SERVO_SPEED_MS_PER_DEG"]
        self.settle_ms = cfg["APP_SERVO_SETTLE_MS"]
        self.arc_deg = cfg["APP_SWEEP_MAX_DEG"] - cfg["APP_SWEEP_MIN_DEG"]
        self.c_cm_per_ms = (331.3 + 0.606 * cfg["APP_US_TEMP_C"]) / 10.0
        # Margin the config adds to the round trip at its own max range
        self.timeout_margin_ms = (cfg["APP_US_TIMEOUT_US"] / 1000.0
                                  - self.flight_ms(cfg["APP_US_MAX_RANGE_CM"]))

    def flight_ms(self, d_cm: float) -> float:
        return 2.0 * d_cm / self.c_cm_per_ms

    def echo_wait_ms(self, range_cm: float) -> float:
        return SENSOR_OVERHEAD_MS + self.flight_ms(range_cm) + self.timeout_margin_ms

    def readings(self, step: float) -> int:
        return int(math.floor(self.arc_deg / step + 1e-9)) + 1

    def period_ms(self, step: float, gap: float, range_cm: float, style: str) -> float:
        wait = self.echo_wait_ms(range_cm)
        if style == "stop-and-ping":
            busy = wait + step * self.speed_ms_per_deg + self.settle_ms
        else:
            busy = wait
        return max(gap, busy, self.hold_ms)

    def limited_by(self, step, gap, range_cm, style) -> str:
        wait = self.echo_wait_ms(range_cm)
        busy = wait + (step * self.speed_ms_per_deg + self.settle_ms
                       if style == "stop-and-ping" else 0.0)
        top = max(gap, busy, self.hold_ms)
        if top == gap:
            return "ping gap"
        if top == self.hold_ms:
            return "no-echo hold"
        return "move+settle+echo" if style == "stop-and-ping" else "echo wait"

    def pass_s(self, step, gap, range_cm, style) -> float:
        return (self.readings(step) - 1) * self.period_ms(step, gap, range_cm, style) / 1000.0

    def age_profile_s(self, step, gap, range_cm, style):
        """(angle, worst age at redraw) for each bin of the bouncing sweep."""
        n = self.readings(step)
        t = self.period_ms(step, gap, range_cm, style) / 1000.0
        lo = self.cfg["APP_SWEEP_MIN_DEG"]
        out = []
        for i in range(n):
            ages = [a for a in (2 * i, 2 * (n - 1 - i)) if a > 0]
            out.append((lo + i * step, max(ages) * t, min(ages) * t))
        return out

    def angle_err_deg(self, step, gap, range_cm, d_cm) -> float:
        """Ping-while-moving, tag = commanded angle at trigger, worst lag."""
        t = self.period_ms(step, gap, range_cm, "ping-while-moving")
        w = step / t
        lag = PWM_PERIOD_MS + self.settle_ms
        return w * (lag + self.flight_ms(d_cm))


def build_rows(m: Model) -> list[dict]:
    rows = []
    for style in STYLES:
        for rng in RANGES_CM:
            for gap in GAPS_MS:
                for step in STEPS_DEG:
                    n = m.readings(step)
                    period = m.period_ms(step, gap, rng, style)
                    pass_s = m.pass_s(step, gap, rng, style)
                    ages = m.age_profile_s(step, gap, rng, style)
                    worst_age = max(a[1] for a in ages)
                    mid_age = ages[len(ages) // 2][1]
                    row = {
                        "style": style, "range_cm": rng, "gap_ms": gap, "step_deg": step,
                        "readings_per_pass": n,
                        "echo_wait_ms": round(m.echo_wait_ms(rng), 2),
                        "period_ms": round(period, 2),
                        "limited_by": m.limited_by(step, gap, rng, style),
                        "pass_s": round(pass_s, 3),
                        "meets_SC4": pass_s <= SC4_PASS_S,
                        "age_mid_s": round(mid_age, 3),
                        "age_worst_s": round(worst_age, 3),
                        "walker_mid_cm": round(WALKER_M_S * 100 * mid_age, 1),
                        "walker_worst_cm": round(WALKER_M_S * 100 * worst_age, 1),
                        "ghost_free_m": round(m.c_cm_per_ms * gap / 2 / 100, 2),
                        "gap_shorter_than_hold": gap < NO_ECHO_HOLD_MS,
                        "hits_beam15": int(BEAM_DEG // step),
                        "hits_beam8": int(BEAM_PESSIMISTIC_DEG // step),
                    }
                    for d in EVAL_DIST_CM:
                        row[f"spacing_{d}cm"] = round(2 * d * math.sin(math.radians(step) / 2), 2)
                        row[f"footprint15_{d}cm"] = round(2 * d * math.tan(math.radians(BEAM_DEG) / 2), 1)
                        if style == "ping-while-moving":
                            e = m.angle_err_deg(step, gap, rng, d)
                            row[f"angle_err_{d}cm_deg"] = round(e, 2)
                            row[f"pass_to_pass_jump_{d}cm_deg"] = round(2 * e, 2)
                        else:
                            row[f"angle_err_{d}cm_deg"] = 0.0   # A2: ideal settle
                            row[f"pass_to_pass_jump_{d}cm_deg"] = 0.0
                    rows.append(row)
    return rows


# ------------------------------------------------------------- charts ----
def style_axes(ax):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.title.set_color(INK)


def ref_line(ax, y, text, horizontal=True):
    if horizontal:
        ax.axhline(y, color=INK2, linestyle=(0, (4, 3)), linewidth=1.2, zorder=1)
        ax.annotate(text, xy=(0.01, y), xycoords=("axes fraction", "data"),
                    xytext=(0, 3), textcoords="offset points", color=INK2, fontsize=8.5)


def end_label(ax, x, y, text, color, dy=0):
    ax.plot([x], [y], "o", color=color, markersize=6, markeredgecolor="white",
            markeredgewidth=1.5, zorder=4)
    ax.annotate(text, xy=(x, y), xytext=(6, dy), textcoords="offset points",
                va="center", fontsize=8.5, color=INK)


def fig_title(fig, title, sub):
    fig.suptitle(title, x=0.01, ha="left", fontsize=12.5, fontweight="bold", color=INK, y=0.99)
    fig.text(0.01, 0.925, sub, ha="left", fontsize=9, color=INK2)


def chart_sweep_time(m: Model, path: Path):
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.2), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, rng in zip(axes, RANGES_CM):
        style_axes(ax)
        for step in STEPS_DEG:
            ys = [m.pass_s(step, g, rng, "stop-and-ping") for g in GAPS_MS]
            ax.plot(GAPS_MS, ys, color=STEP_COLOR[step], linewidth=2, zorder=3)
            end_label(ax, GAPS_MS[-1], ys[-1], f"{step}°  {ys[-1]:.1f} s", STEP_COLOR[step])
        ref_line(ax, SC4_PASS_S, "SC4: 5 s per pass")
        ax.set_xticks(GAPS_MS)
        ax.set_xlim(27, 72)
        ax.set_title(f"Range {rng} cm", fontsize=10, loc="left")
        ax.set_xlabel("Ping gap (ms)", fontsize=9)
    axes[0].set_ylabel("Time for one 150° pass (s)", fontsize=9)
    axes[0].set_ylim(0, 10)
    fig_title(fig, "S1 · Pass time, stop-and-ping, by step size",
              "Worst case (empty scene). Below 40 ms the no-echo hold (A6) and the servo move + settle set "
              "the pace; at 40-60 ms the ping gap does, so range changes nothing.")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_scan_style(m: Model, path: Path):
    rng = int(m.cfg["APP_US_MAX_RANGE_CM"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4))
    fig.patch.set_facecolor("white")
    style_axes(a1)
    style_axes(a2)

    # Left: pass time saved by ping-while-moving, per step, vs gap. Drawn with
    # the no-echo hold ignored (A6 wrong), the best case for ping-while-moving;
    # with A6 the saving is 0-6 %.
    m0 = Model(m.cfg, hold_ms=0.0)
    for step in STEPS_DEG:
        sp = [m0.pass_s(step, g, rng, "stop-and-ping") for g in GAPS_MS]
        pm = [m0.pass_s(step, g, rng, "ping-while-moving") for g in GAPS_MS]
        saved = [100 * (1 - b / a) for a, b in zip(sp, pm)]
        a1.plot(GAPS_MS, saved, color=STEP_COLOR[step], linewidth=2, zorder=3)
        end_label(a1, GAPS_MS[0], saved[0], "", STEP_COLOR[step])
        a1.annotate(f"{step}°  {saved[0]:.0f} %", xy=(GAPS_MS[0], saved[0]), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=8.5, color=INK)
    a1.set_xticks(GAPS_MS)
    a1.set_xlim(20, 63)
    a1.set_ylim(-2, 30)
    a1.set_xlabel("Ping gap (ms)", fontsize=9)
    a1.set_ylabel("Pass time saved by ping-while-moving (%)", fontsize=9)
    a1.set_title(f"Time saved, best case (A6 hold ignored; range {rng} cm)", fontsize=10, loc="left")

    # Right: angle error of ping-while-moving vs target distance, gap = config
    gap = m.cfg["APP_US_PING_GAP_MS"]
    ds = list(range(5, rng + 1, 5))
    for step in STEPS_DEG:
        es = [2 * m.angle_err_deg(step, gap, rng, d) for d in ds]
        a2.plot(ds, es, color=STEP_COLOR[step], linewidth=2, zorder=3)
        end_label(a2, ds[-1], es[-1], f"{step}°  {es[-1]:.1f}°", STEP_COLOR[step])
    a2.axhline(2 * SC3_BEARING_DEG, color=INK2, linestyle=(0, (4, 3)), linewidth=1.2)
    a2.annotate("SC3 ±5° band (10° wide)", xy=(0.01, 2 * SC3_BEARING_DEG),
                xycoords=("axes fraction", "data"), xytext=(0, 3), textcoords="offset points",
                color=INK2, fontsize=8.5)
    a2.set_xlim(0, rng * 1.25)
    a2.set_ylim(0, 11)
    a2.set_xlabel("Target distance (cm)", fontsize=9)
    a2.set_ylabel("Jump between left and right passes (°)", fontsize=9)
    a2.set_title(f"Ping-while-moving angle error (gap {gap:.0f} ms)", fontsize=10, loc="left")
    fig_title(fig, "S1 · Stop-and-ping vs ping-while-moving",
              "Left: speed gained by not waiting for the servo. Right: what it costs; the error flips "
              "sign each pass, so an object jumps by twice the error. Stop-and-ping: 0 (A2).")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_point_age(m: Model, path: Path):
    gap = m.cfg["APP_US_PING_GAP_MS"]
    rng = m.cfg["APP_US_MAX_RANGE_CM"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    fig.patch.set_facecolor("white")
    style_axes(ax)
    top = 0
    for step in STEPS_DEG:
        prof = m.age_profile_s(step, gap, rng, "stop-and-ping")
        xs = [p[0] for p in prof]
        ys = [p[1] for p in prof]
        top = max(top, max(ys))
        ax.plot(xs, ys, color=STEP_COLOR[step], linewidth=2, zorder=3)
        # nudge a label off the fade line it would sit on
        cpass = m.pass_s(m.cfg["APP_SWEEP_STEP_DEG"], gap, rng, "stop-and-ping")
        dy = -9 if any(abs(ys[-1] - k * cpass) < 0.3 for k, _ in FADE_COMPARE) else 0
        end_label(ax, xs[-1], ys[-1], f"{step}°  {ys[-1]:.1f} s", STEP_COLOR[step], dy=dy)
    # fade lines are relative to each step's pass time; draw them for the config step
    cstep = m.cfg["APP_SWEEP_STEP_DEG"]
    p = m.pass_s(cstep, gap, rng, "stop-and-ping")
    for (k, name), ls in zip(FADE_COMPARE, ((0, (4, 3)), (0, (1, 2)))):
        lbl = f"fade = {k} passes ({name})"
        ax.axhline(k * p, color=INK2, linestyle=ls,
                   linewidth=1.2, zorder=1)
        ax.annotate(f"{lbl}\nat step {cstep:.0f}°: {k * p:.1f} s", xy=(0.995, k * p),
                    xycoords=("axes fraction", "data"), xytext=(0, 3), textcoords="offset points",
                    ha="right", va="bottom", color=INK2, fontsize=8.5)
    ax.set_xlim(m.cfg["APP_SWEEP_MIN_DEG"] - 5, m.cfg["APP_SWEEP_MAX_DEG"] + 75)
    ax.set_xticks(range(15, 166, 30))
    ax.set_ylim(0, max(top, 3 * p) * 1.12)
    ax.set_xlabel("Bin angle (°)", fontsize=9)
    ax.set_ylabel("Worst age when the bin is redrawn (s)", fontsize=9)
    fig_title(fig, "S1 · How old a point gets before it is measured again",
              f"Stop-and-ping, gap {gap:.0f} ms. The sweep bounces, so the middle is revisited every "
              "pass but the ends only every 2 passes.")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_coverage(path: Path):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.3, 1]})
    fig.patch.set_facecolor("white")
    style_axes(a1)
    style_axes(a2)
    ds = list(range(10, 201, 5))
    for step in STEPS_DEG:
        ys = [2 * d * math.sin(math.radians(step) / 2) for d in ds]
        a1.plot(ds, ys, color=STEP_COLOR[step], linewidth=2, zorder=3)
        end_label(a1, ds[-1], ys[-1], f"{step}° step", STEP_COLOR[step])
    for beam, ls, name in ((BEAM_DEG, (0, (4, 3)), "15° beam footprint"),
                           (BEAM_PESSIMISTIC_DEG, (0, (1, 2)), "8° what-if footprint")):
        ys = [2 * d * math.tan(math.radians(beam) / 2) for d in ds]
        a1.plot(ds, ys, color=INK2, linestyle=ls, linewidth=1.2, zorder=2)
        a1.annotate(name, xy=(ds[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=INK2)
    a1.axhline(TUBE_CM, color=INK2, linewidth=0.8, zorder=1)
    a1.annotate("5 cm tube (SC1)", xy=(0.995, TUBE_CM), xycoords=("axes fraction", "data"),
                xytext=(0, 3), textcoords="offset points", ha="right", fontsize=8.5, color=INK2)
    for d in EVAL_DIST_CM:
        a1.axvline(d, color=GRID, linewidth=1.5, zorder=0)
    a1.set_xlim(0, 330)
    a1.set_xticks(range(0, 201, 50))
    a1.set_ylim(0, 55)
    a1.set_xlabel("Distance (cm)", fontsize=9)
    a1.set_ylabel("Width (cm)", fontsize=9)
    a1.set_title("Gap between neighbouring readings vs beam width", fontsize=10, loc="left")

    # Right: readings that see one thin target
    x = range(len(STEPS_DEG))
    w = 0.38
    h15 = [int(BEAM_DEG // s) for s in STEPS_DEG]
    h8 = [int(BEAM_PESSIMISTIC_DEG // s) for s in STEPS_DEG]
    a2.bar([i - w / 2 - 0.01 for i in x], h15, width=w, color=[STEP_COLOR[s] for s in STEPS_DEG],
           zorder=3)
    a2.bar([i + w / 2 + 0.01 for i in x], h8, width=w, color="white", zorder=3,
           edgecolor=[STEP_COLOR[s] for s in STEPS_DEG], linewidth=1.8, hatch="///")
    for i, (a, b) in enumerate(zip(h15, h8)):
        a2.annotate(str(a), xy=(i - w / 2, a), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8.5, color=INK)
        a2.annotate(str(b), xy=(i + w / 2, b), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8.5, color=INK)
    a2.axhline(3, color=INK2, linestyle=(0, (4, 3)), linewidth=1.2, zorder=1)
    a2.annotate("dashed: 3 hits, the least for\nmedian-of-3 or edge-midpoint", xy=(0.98, 0.97),
                xycoords="axes fraction", ha="right", va="top", fontsize=8.5, color=INK2)
    a2.set_xticks(list(x), [f"{s}°" for s in STEPS_DEG])
    a2.set_ylim(0, 17)
    a2.set_xlabel("Step size  (solid = 15° beam, hatched = 8° what-if)", fontsize=9)
    a2.set_ylabel("Readings that see one thin target", fontsize=9)
    a2.set_title("Hits per target", fontsize=10, loc="left")
    fig_title(fig, "S1 · Coverage: does the step leave holes?",
              "Every step here is far narrower than the beam, so there are no holes; "
              "the step instead sets how many readings see each target.")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ------------------------------------------------------------ summary ----
def summary(m: Model, rows: list[dict]) -> str:
    cfg = m.cfg
    s = io.StringIO()
    p = lambda *a: print(*a, file=s)  # noqa: E731
    p("S1 sweep timing model: summary")
    p("=" * 72)
    p("Config read from main/app_config.h:")
    for k in sorted(k for k in cfg if k.startswith(("APP_SERVO_", "APP_SWEEP_", "APP_US_")) or k == "APP_FADE_SWEEPS"):
        p(f"  {k:28s} {cfg[k]:g}")
    p(f"Derived: c = {m.c_cm_per_ms * 10:.1f} m/s; timeout margin over 2R/c = {m.timeout_margin_ms:.2f} ms; "
      f"arc = {m.arc_deg:g} deg")
    p(f"Assumed (not in config): overhead {SENSOR_OVERHEAD_MS} ms, no-echo hold {NO_ECHO_HOLD_MS} ms, "
      f"beam {BEAM_DEG}/{BEAM_PESSIMISTIC_DEG} deg, PWM period {PWM_PERIOD_MS} ms")
    p()
    for style in STYLES:
        p(f"Pass time (s), {style}, worst case (empty scene)")
        p(f"  {'range':>6} {'gap':>5} | " + " ".join(f"{st:>4}°" for st in STEPS_DEG) + " | limited by (2°)")
        for rng in RANGES_CM:
            for gap in GAPS_MS:
                r = {x["step_deg"]: x for x in rows
                     if x["style"] == style and x["range_cm"] == rng and x["gap_ms"] == gap}
                cells = " ".join(f"{r[st]['pass_s']:5.2f}" + ("*" if not r[st]["meets_SC4"] else " ")
                                 for st in STEPS_DEG)
                p(f"  {rng:>4}cm {gap:>3}ms | {cells}| {r[2]['limited_by']}")
        p("  (* = misses SC4, 5 s per pass)")
        p()
    rng = int(cfg["APP_US_MAX_RANGE_CM"])
    p(f"Per step at range {rng} cm, stop-and-ping")
    p(f"  {'step':>4} {'gap':>4} {'N':>4} {'T ms':>6} {'pass s':>7} {'age mid':>8} {'age end':>8} "
      f"{'walk mid':>9} {'walk end':>9}")
    for gap in GAPS_MS:
        for st in STEPS_DEG:
            r = next(x for x in rows if x["style"] == "stop-and-ping" and x["range_cm"] == rng
                     and x["gap_ms"] == gap and x["step_deg"] == st)
            p(f"  {st:>3}° {gap:>4} {r['readings_per_pass']:>4} {r['period_ms']:>6.1f} {r['pass_s']:>7.2f} "
              f"{r['age_mid_s']:>7.2f}s {r['age_worst_s']:>7.2f}s {r['walker_mid_cm']:>7.0f}cm "
              f"{r['walker_worst_cm']:>7.0f}cm")
    p()
    p("Coverage (independent of gap and style)")
    p(f"  {'step':>4} | spacing at 50/100/150 cm  | 15° footprint 50/100/150 cm | hits 15°/8°")
    r0 = {x["step_deg"]: x for x in rows if x["style"] == "stop-and-ping" and x["range_cm"] == rng
          and x["gap_ms"] == GAPS_MS[-1]}
    for st in STEPS_DEG:
        r = r0[st]
        p(f"  {st:>3}° | {r['spacing_50cm']:5.1f} {r['spacing_100cm']:5.1f} {r['spacing_150cm']:5.1f} cm"
          f"       | {r['footprint15_50cm']:5.1f} {r['footprint15_100cm']:5.1f} {r['footprint15_150cm']:5.1f} cm"
          f"           | {r['hits_beam15']:>3} / {r['hits_beam8']}")
    p()
    p(f"Ping-while-moving angle error at {rng} cm range setting (deg; jump between passes = 2x)")
    p(f"  {'gap':>4} | " + "  ".join(f"{st}°: 50/100/150 cm" for st in STEPS_DEG))
    for gap in GAPS_MS:
        cells = []
        for st in STEPS_DEG:
            r = next(x for x in rows if x["style"] == "ping-while-moving" and x["range_cm"] == rng
                     and x["gap_ms"] == gap and x["step_deg"] == st)
            cells.append(f"{r['angle_err_50cm_deg']:.2f}/{r['angle_err_100cm_deg']:.2f}/{r['angle_err_150cm_deg']:.2f}")
        p(f"  {gap:>4} | " + "  ".join(f"{c:>17}" for c in cells))
    p()
    p("Ghost-free range (echo from further than this can land in the next ping)")
    for gap in GAPS_MS:
        flag = "  < no-echo hold: trigger may be ignored (A6)" if gap < NO_ECHO_HOLD_MS else ""
        p(f"  gap {gap} ms: {m.c_cm_per_ms * gap / 2 / 100:.1f} m{flag}")
    p()
    p("Sensitivity: A6 wrong (sensor accepts a new trigger as soon as the timeout ends)")
    m0 = Model(cfg, hold_ms=0.0)
    p(f"  pass s at {rng} cm: stop-and-ping / ping-while-moving (saved)")
    for gap in GAPS_MS:
        cells = []
        for st in STEPS_DEG:
            a = m0.pass_s(st, gap, rng, "stop-and-ping")
            b = m0.pass_s(st, gap, rng, "ping-while-moving")
            cells.append(f"{st}°: {a:.2f}/{b:.2f} ({100 * (1 - b / a):.0f}%)")
        p(f"  gap {gap:>2} ms | " + "  ".join(cells))
    p()
    p("Fade check: an end bin is redrawn at exactly 2 passes for every step and gap,")
    p("so with linear fade over 2 passes it reaches 0 just as it is")
    p("re-measured. Brightness when redrawn, middle / end bin:")
    names = dict(FADE_COMPARE)
    for k in (2, 3, 4):
        lbl = f"{k} passes ({names[k]})" if k in names else f"{k} passes"
        p(f"  fade {lbl}: {max(0, 1 - 1 / k):.0%} / {max(0, 1 - 2 / k):.0%}")
    return s.getvalue()


def main() -> None:
    cfg = parse_config(CONFIG_H)
    m = Model(cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_rows(m)

    with open(OUT / "s1_sweep_timing.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    chart_sweep_time(m, OUT / "s1_sweep_time.png")
    chart_scan_style(m, OUT / "s1_scan_style.png")
    chart_point_age(m, OUT / "s1_point_age.png")
    chart_coverage(OUT / "s1_coverage.png")

    text = summary(m, rows)
    (OUT / "s1_summary.txt").write_text(text)
    print(text)
    print(f"Wrote {len(rows)} rows + 4 charts to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
