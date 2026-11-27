"""Generate the ultrasonic sonar diagrams (PLAN task D1).

    . .venv/bin/activate && python docs/diagrams/gen_diagrams.py

Writes, next to this file (SVG + PNG each):
  hardware            D1 hardware block diagram
  state-mode-fsm      D3 state diagram, components/mode_fsm
  state-target-track  D3 state diagram, components/target_track
  state-lock-loop     D3 state diagram, components/lock_loop

The firmware diagrams follow the firmware diagram standard in docs/PLAN.md
(D1/D3). The ISO 5807 flowcharts are added once the display_task/radar_gfx
layout settles.

Pins and part values are read from main/app_config.h, so the diagram can't
drift from the code. They are PROPOSED until D6 (kit known).

Approach credit: the idea of one Python script that draws every diagram and
writes SVG + PNG, and the colour scheme (red 5 V, orange 3.3 V, grey GND,
teal signals), come from our MC2 project (../spectrum_visualiser,
docs/diagrams/gen_diagrams.py). That script hand-writes SVG; this one draws
with matplotlib (already in requirements.txt), which also gives the PNG.

Design: Joe Gould, drafted with Claude (Anthropic).
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CFG = os.path.join(ROOT, "main", "app_config.h")

# Colours (MC2 light theme)
INK, MUTED, LINE, PANEL, BG = "#16202b", "#5d6b7b", "#9aa7b5", "#ffffff", "#f4f6f8"
P5, P3, GND, SIG, ACC = "#b3261e", "#c2410c", "#55606d", "#0f7b6c", "#1f6f8b"
NOTE_BG, NOTE_LINE = "#fff7e0", "#b98a12"

plt.rcParams["svg.fonttype"] = "none"  # keep text as text in the SVG
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["svg.hashsalt"] = "ultrasonic-radar"  # stable SVG ids between runs


def read_pins(path=CFG):
    """Return {NAME: value} for every '#define APP_PIN_* <int>' in app_config.h."""
    pins = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*#define\s+(APP_PIN_\w+)\s+(\d+)", line)
            if m:
                pins[m.group(1)] = int(m.group(2))
    need = ["APP_PIN_US_TRIG", "APP_PIN_US_ECHO", "APP_PIN_SERVO",
            "APP_PIN_JOY_X", "APP_PIN_JOY_Y", "APP_PIN_JOY_SW"]
    missing = [n for n in need if n not in pins]
    if missing:
        raise SystemExit(f"app_config.h is missing {missing}")
    return pins


# ------------------------------------------------------------ drawing helpers
def box(ax, x, y, w, h, title, lines=(), dashed=False, fill=PANEL, edge=LINE, title_size=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                fc=fill, ec=edge, lw=1.3, ls=(0, (5, 3)) if dashed else "-"))
    ax.text(x + 1.5, y + h - 2.2, title, fontsize=title_size, weight="bold", color=INK, va="top")
    for i, s in enumerate(lines):
        ax.text(x + 1.5, y + h - 6.2 - 3.1 * i, s, fontsize=8.5, color=MUTED, va="top")


def wire(ax, pts, color, lw=2.0, arrow=False, dashed=False, label=None, lpos=0, ldx=0.0, ldy=1.0,
         lcolor=None, lsize=8, lha="center"):
    xs, ys = zip(*pts)
    ls = (0, (5, 3)) if dashed else "-"
    if arrow:
        ax.plot(xs[:-1] + (xs[-1],), ys[:-1] + (ys[-1],), color=color, lw=lw, ls=ls, solid_capstyle="butt")
        ax.annotate("", xy=pts[-1], xytext=pts[-2],
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=12, ls=ls))
    else:
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="butt")
    if label:
        (x1, y1), (x2, y2) = pts[lpos], pts[lpos + 1]
        ax.text((x1 + x2) / 2 + ldx, (y1 + y2) / 2 + ldy, label, fontsize=lsize,
                color=lcolor or color, ha=lha, va="bottom", weight="bold")


def ground_symbol(ax, x, y):
    """Ground symbol hanging from (x, y): same net as the GND line."""
    ax.plot([x, x], [y, y - 0.8], color=GND, lw=1.6)
    for i, half in enumerate((2.0, 1.3, 0.6)):
        yy = y - 0.8 - 0.6 * i
        ax.plot([x - half, x + half], [yy, yy], color=GND, lw=1.6)


def dot(ax, x, y, color):
    ax.plot([x], [y], "o", color=color, ms=5)


# ------------------------------------------------------------------ diagram
def hardware(pins):
    fig = plt.figure(figsize=(13, 8.4), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 130)
    ax.set_ylim(0, 84)
    ax.axis("off")

    ax.text(2, 81.5, "Scanning ultrasonic sonar: hardware block diagram", fontsize=15,
            weight="bold", color=INK, va="top")
    ax.text(2, 77.5, "Pins from main/app_config.h, all PROPOSED until D6 (kit known). "
            "Power and part values are checked in D4 (schematic).", fontsize=9.5, color=MUTED, va="top")

    # ---- PC and browser (left)
    box(ax, 2, 50, 22, 16, "Lab PC",
        ["tools/radar_view.py", "(core display, D-DISPLAY)", "USB power source"])
    box(ax, 2, 25.5, 22, 12, "Browser (PC / phone)",
        ["web page served by", "the ESP32 (X1, later)"], dashed=True)

    # ---- ESP32-S3 (centre)
    ex, ey, ew, eh = 40, 14, 28, 56
    box(ax, ex, ey, ew, eh, "ESP32-S3",
        ["Freenove ESP32-S3-WROOM", "on-board 3.3 V regulator", "Wi-Fi (for X1)"], fill="#e3f0f5", edge=ACC,
        title_size=13)
    R = ex + ew  # right edge

    def pin_label(y, text):
        ax.text(R - 1, y + 0.7, text, fontsize=8.5, color=ACC, ha="right", va="bottom",
                family="DejaVu Sans Mono", weight="bold")

    # pin rows on the right edge
    y_5v, y_servo, y_trig, y_echo = 64, 56.5, 47, 41
    y_3v3, y_jx, y_jy, y_jsw = 30, 24, 20, 16
    pin_label(y_5v, "5V")
    pin_label(y_servo, f"GPIO{pins['APP_PIN_SERVO']}")
    pin_label(y_trig, f"GPIO{pins['APP_PIN_US_TRIG']}")
    pin_label(y_echo, f"GPIO{pins['APP_PIN_US_ECHO']}")
    pin_label(y_3v3, "3V3")
    pin_label(y_jx, f"GPIO{pins['APP_PIN_JOY_X']} ADC1")
    pin_label(y_jy, f"GPIO{pins['APP_PIN_JOY_Y']} ADC1")
    pin_label(y_jsw, f"GPIO{pins['APP_PIN_JOY_SW']}")

    # ---- PC <-> ESP32
    wire(ax, [(24, 62), (ex, 62)], P5, arrow=True, label="5 V (USB VBUS)", ldy=0.8)
    wire(ax, [(ex, 54), (24, 54)], SIG, arrow=True, label="USB serial: R/M/T lines", ldy=0.8)
    ax.text(32, 52.6, "921600 baud", fontsize=7.5, color=SIG, ha="center", va="top")
    wire(ax, [(ex, 31), (24, 31)], SIG, arrow=True, dashed=True, label="Wi-Fi (later)", ldy=0.8)

    # ---- right-hand parts
    sx = 100  # x of part boxes
    box(ax, sx, 55, 27, 13, "SG90 servo", ["pan: turns the sensor", "15–165°, 2° steps"])
    box(ax, sx, 37, 27, 14, "HC-SR04", ["ultrasonic sensor on the", "servo horn (moves)", "VCC 5 V version assumed"])
    box(ax, sx, 10, 27, 18, "Joystick module", ["2 pots + push switch", "VRx, VRy, SW", "powered from 3.3 V",
                                                "(5 V would exceed the ADC)"])

    # 5 V rail: ESP32 5V -> servo V+ and HC-SR04 VCC
    rail_x = 76
    wire(ax, [(R, y_5v), (sx, y_5v)], P5, label="5 V", lpos=0, ldx=-12)
    dot(ax, rail_x, y_5v, P5)
    wire(ax, [(rail_x, y_5v), (rail_x, 49), (sx, 49)], P5, label="5 V", lpos=1, ldx=7)

    # bulk capacitor across servo supply (5 V to GND, at the servo)
    cx = 85
    dot(ax, cx, y_5v, P5)
    wire(ax, [(cx, y_5v), (cx, 62.4)], P5, lw=1.6)
    ax.plot([cx - 2.2, cx + 2.2], [62.4, 62.4], color=INK, lw=2.2)
    ax.plot([cx - 2.2, cx + 2.2], [61.4, 61.4], color=INK, lw=2.2)
    ax.text(cx + 2.6, 63.0, "+", fontsize=8, color=INK, va="center")
    wire(ax, [(cx, 61.4), (cx, 60.4)], GND, lw=1.6)
    ground_symbol(ax, cx, 60.4)
    ax.text(cx - 2, 65.0, "C bulk 470–1000 µF (value: D4)", fontsize=7.5, color=INK,
            ha="center", va="bottom")

    # servo PWM
    wire(ax, [(R, y_servo), (sx, y_servo)], SIG, arrow=True, label="PWM 50 Hz (LEDC)", ldx=9)

    # TRIG
    wire(ax, [(R, y_trig), (sx, y_trig)], SIG, arrow=True, label="TRIG 10 µs pulse", ldx=4, ldy=0.6)

    # ECHO via divider
    dvx, dvy, dvw, dvh = 76, 37, 15, 8
    ax.add_patch(FancyBboxPatch((dvx, dvy), dvw, dvh, boxstyle="round,pad=0,rounding_size=1",
                                fc=NOTE_BG, ec=NOTE_LINE, lw=1.3, ls=(0, (5, 3))))
    ax.text(dvx + dvw / 2, dvy + dvh - 1.0, "Echo divider", fontsize=8.5, weight="bold", color=INK,
            ha="center", va="top")
    ax.text(dvx + dvw / 2, dvy + 1.0, "1 kΩ / 2 kΩ", fontsize=8, color=MUTED, ha="center", va="bottom")
    wire(ax, [(sx, y_echo), (dvx + dvw, y_echo)], SIG, arrow=True, label="ECHO 5 V", lpos=0, ldy=0.5, lsize=7.5)
    wire(ax, [(dvx, y_echo), (R, y_echo)], SIG, arrow=True, label="3.3 V", lpos=0, ldy=0.5, lsize=7.5)
    ax.text(dvx + dvw / 2, dvy - 0.8, "only if 5 V HC-SR04,\nnot HC-SR04P (B4 decides)", fontsize=7.5,
            color=NOTE_LINE, ha="center", va="top", style="italic")

    # 3.3 V -> joystick
    wire(ax, [(R, y_3v3), (sx + 3, y_3v3), (sx + 3, 28)], P3, label="3.3 V", ldx=-12)
    # joystick signals (arrows into the ESP32)
    wire(ax, [(sx, y_jx), (R, y_jx)], SIG, arrow=True, label="VRx (analogue)", ldx=4, ldy=0.4)
    wire(ax, [(sx, y_jy), (R, y_jy)], SIG, arrow=True, label="VRy (analogue)", ldx=4, ldy=0.4)
    wire(ax, [(sx, y_jsw), (R, y_jsw)], SIG, arrow=True, label="SW (low = pressed, pull-up)", ldx=4, ldy=0.4)

    # common ground bus
    gy = 5
    wire(ax, [(ex + ew / 2, ey), (ex + ew / 2, gy), (124, gy)], GND, label="GND 0 V (common to all parts)",
         lpos=1, ldx=0, ldy=0.6)
    wire(ax, [(124, 10), (124, gy)], GND)          # joystick
    dot(ax, 124, gy, GND)
    # servo and HC-SR04 grounds run down the far right
    wire(ax, [(127, 60), (128.5, 60), (128.5, gy), (124, gy)], GND)
    wire(ax, [(127, 41), (128.5, 41)], GND)
    dot(ax, 128.5, 41, GND)
    dot(ax, ex + ew / 2, gy, GND)

    # ---- legend
    lx, ly = 2, 1
    ax.add_patch(FancyBboxPatch((lx, ly), 34, 22, boxstyle="round,pad=0,rounding_size=1", fc=PANEL, ec=LINE, lw=1))
    ax.text(lx + 1.5, ly + 20.6, "Legend", fontsize=9.5, weight="bold", color=INK, va="top")
    items = [
        (P5, "-", False, "power line, 5 V (voltage on each line)"),
        (P3, "-", False, "power line, 3.3 V"),
        (GND, "-", False, "ground (0 V)"),
        (SIG, "-", True, "signal (arrow = direction of data)"),
        (SIG, "--", True, "later / only in some cases (dashed)"),
    ]
    for i, (c, ls, arr, txt) in enumerate(items):
        yy = ly + 16.6 - 2.4 * i
        if arr:
            ax.annotate("", xy=(lx + 7.5, yy), xytext=(lx + 1.5, yy),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=2, mutation_scale=10,
                                        ls=(0, (4, 2)) if ls == "--" else "-"))
        else:
            ax.plot([lx + 1.5, lx + 7.5], [yy, yy], color=c, lw=2.2)
        ax.text(lx + 9, yy, txt, fontsize=8, color=INK, va="center")
    ground_symbol(ax, lx + 4.5, ly + 5.4)
    ax.text(lx + 9, ly + 4.4, "ground symbol: joins the GND line", fontsize=8, color=INK, va="center")
    ax.text(lx + 1.5, ly + 0.5, "Yellow dashed box: depends on the kit (B4).", fontsize=7.5, color=NOTE_LINE,
            va="bottom")
    return fig


# ============================================================ state diagrams
# D3, drawn to the firmware diagram standard in docs/PLAN.md (D1/D3): UML-style
# state diagrams, filled dot = initial state, rounded box = state, every arrow
# "event [guard] / action", a legend on each. Every name below is copied from
# the source (components/mode_fsm, target_track, lock_loop); the (Lnn) tags are
# the lines in the .c file that implement each arrow, so a reader can check them.
# APP_* values are read from main/app_config.h.

STATE_FILL, STATE_EDGE = "#e3f0f5", ACC
ARROW = INK


def read_defines(path=CFG):
    """Return {NAME: text} for every '#define APP_* <value>' in app_config.h."""
    out = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*#define\s+(APP_\w+)\s+(\S+)", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def new_canvas(w, h, title, subtitle):
    fig = plt.figure(figsize=(w / 10, h / 10), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    ax.text(2, h - 2, title, fontsize=15, weight="bold", color=INK, va="top")
    ax.text(2, h - 6.2, subtitle, fontsize=9.5, color=MUTED, va="top")
    return fig, ax


def state(ax, x, y, w, h, name, body=(), fill=STATE_FILL, edge=STATE_EDGE, size=10.5):
    """UML state: rounded box, name on top, optional compartment below a rule."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=2.2",
                                fc=fill, ec=edge, lw=1.6))
    if body:
        ax.text(x + w / 2, y + h - 1.4, name, fontsize=size, weight="bold", color=INK, ha="center",
                va="top", family="DejaVu Sans Mono")
        ax.plot([x + 0.8, x + w - 0.8], [y + h - 5.0, y + h - 5.0], color=edge, lw=0.8)
        for i, t in enumerate(body):
            ax.text(x + w / 2, y + h - 6.2 - 2.6 * i, t, fontsize=7.5, color=MUTED, ha="center", va="top",
                    family="DejaVu Sans Mono")
    else:
        ax.text(x + w / 2, y + h / 2, name, fontsize=size, weight="bold", color=INK, ha="center",
                va="center", family="DejaVu Sans Mono")


def initial(ax, x, y):
    ax.plot([x], [y], "o", color=INK, ms=11)


def choice(ax, x, y, r=1.6):
    ax.add_patch(plt.Polygon([(x, y + r), (x + r, y), (x, y - r), (x - r, y)], closed=True,
                             fc=PANEL, ec=INK, lw=1.3))


def trans(ax, p1, p2, label=None, lxy=None, rad=0.0, ha="center", color=ARROW, lsize=7.6, va="center"):
    """Transition arrow p1 -> p2 (curved by rad) with its 'event [guard] / action' label at lxy."""
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch(p1, p2, connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
                                 mutation_scale=13, lw=1.3, color=color, shrinkA=0, shrinkB=0))
    if label:
        ax.text(lxy[0], lxy[1], label, fontsize=lsize, color=INK, ha=ha, va=va, family="DejaVu Sans Mono",
                bbox=dict(boxstyle="round,pad=0.25", fc=BG, ec="none"), linespacing=1.25)


def self_loop(ax, x, y, side, label, lxy, ha="center", size=5.0, va="center"):
    """Self-transition leaving and re-entering a state at (x, y) on the given side."""
    d = 2.2
    if side == "top":
        p1, p2, rad = (x - d, y), (x + d, y), -1.9
    elif side == "bottom":
        p1, p2, rad = (x + d, y), (x - d, y), -1.9
    elif side == "right":
        p1, p2, rad = (x, y + d), (x, y - d), -1.9
    else:
        p1, p2, rad = (x, y - d), (x, y + d), -1.9
    trans(ax, p1, p2, label, lxy, rad=rad, ha=ha, va=va)


def note(ax, x, y, w, h, title, lines, size=7.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1", fc=NOTE_BG,
                                ec=NOTE_LINE, lw=1.0))
    ax.text(x + 1.2, y + h - 1.2, title, fontsize=8.5, weight="bold", color=INK, va="top")
    for i, t in enumerate(lines):
        ax.text(x + 1.2, y + h - 4.4 - 2.55 * i, t, fontsize=size, color=INK, va="top", family="DejaVu Sans Mono")


def legend_states(ax, x, y, extra=()):
    h = 15 + 2.6 * len(extra)
    ax.add_patch(FancyBboxPatch((x, y), 46, h, boxstyle="round,pad=0,rounding_size=1", fc=PANEL, ec=LINE,
                                lw=1.0))
    ax.text(x + 1.5, y + h - 1.4, "Legend (UML state diagram)", fontsize=9, weight="bold", color=INK, va="top")
    yy = y + h - 5.6
    initial(ax, x + 4, yy)
    ax.text(x + 8, yy, "initial state", fontsize=8, color=INK, va="center")
    yy -= 3.0
    ax.add_patch(FancyBboxPatch((x + 1.5, yy - 1.1), 5, 2.2, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=STATE_FILL, ec=STATE_EDGE, lw=1.2))
    ax.text(x + 8, yy, "state (name as in the code)", fontsize=8, color=INK, va="center")
    yy -= 3.0
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch((x + 1.5, yy), (x + 6.5, yy), arrowstyle="-|>", mutation_scale=11, lw=1.3,
                                 color=ARROW))
    ax.text(x + 8, yy, "transition: event [guard] / action  (Lnn = line in the .c)", fontsize=8, color=INK,
            va="center")
    for t in extra:
        yy -= 2.6
        ax.text(x + 1.5, yy, t, fontsize=8, color=INK, va="center")


def mode_fsm_diagram():
    fig, ax = new_canvas(150, 92, "mode_fsm: operating modes (D3)",
                         "components/mode_fsm/mode_fsm.c. One mode_fsm_t holds three independent parts "
                         "(UML orthogonal regions): mode, paused, fault. All events go through mode_fsm_handle().")
    # composite state with three regions
    cx, cy, cw, ch = 2, 21, 146, 61
    ax.add_patch(FancyBboxPatch((cx, cy), cw, ch, boxstyle="round,pad=0,rounding_size=2.5", fc=PANEL,
                                ec=STATE_EDGE, lw=1.6))
    ax.text(cx + 2, cy + ch - 1.5, "mode_fsm_t", fontsize=11, weight="bold", color=INK, va="top",
            family="DejaVu Sans Mono")
    for xr in (60, 100):
        ax.plot([xr, xr], [cy + 1, cy + ch - 5], color=STATE_EDGE, lw=1.0, ls=(0, (5, 3)))
    ax.text(5, cy + ch - 5.5, "region: mode (app_mode_t)", fontsize=8.5, color=MUTED, va="top")
    ax.text(63, cy + ch - 5.5, "region: paused", fontsize=8.5, color=MUTED, va="top")
    ax.text(103, cy + ch - 5.5, "region: fault", fontsize=8.5, color=MUTED, va="top")

    # mode region: cycle SWEEP -> LOCK -> MANUAL -> SWEEP
    initial(ax, 6, 62)
    state(ax, 12, 58, 20, 8, "MODE_SWEEP")
    state(ax, 36, 42, 20, 8, "MODE_LOCK")
    state(ax, 12, 25, 20, 8, "MODE_MANUAL")
    trans(ax, (7.2, 62), (12, 62), None)
    ax.text(4, 57, "mode_fsm_init()\n(L21-26)", fontsize=7.2, color=MUTED, va="top", family="DejaVu Sans Mono")
    nxt = "MODE_EVT_NEXT\n/ return true\n(L31-34)"
    trans(ax, (32, 62), (46, 50), nxt, (47, 59), rad=-0.3)
    trans(ax, (46, 42), (32, 29), nxt, (48, 33), rad=-0.3)
    trans(ax, (20, 33), (20, 58), nxt, (11.5, 45.5), rad=0.0)

    # paused region
    initial(ax, 64, 62)
    state(ax, 68, 58, 24, 8, "paused = false")
    state(ax, 68, 28, 24, 8, "paused = true")
    trans(ax, (65.2, 62), (68, 62), None)
    trans(ax, (71, 58), (71, 36), "MODE_EVT_PAUSE_TOGGLE\n/ paused = true;\n  return true (L35-37)",
          (72, 52), lsize=6.9, ha="left")
    trans(ax, (89, 36), (89, 58), "MODE_EVT_PAUSE_TOGGLE\n/ paused = false;\n  return true (L35-37)",
          (88, 42), lsize=6.9, ha="right")

    # fault region
    initial(ax, 104, 62)
    state(ax, 109, 58, 28, 8, "fault = false")
    state(ax, 109, 28, 28, 8, "fault = true")
    trans(ax, (105.2, 62), (109, 62), None)
    trans(ax, (112, 58), (112, 36), "MODE_EVT_SENSOR_FAULT\n/ fault = true;\n  return true\n(L38, L42-43)",
          (113, 52), lsize=6.9, ha="left")
    trans(ax, (134, 36), (134, 58), "MODE_EVT_SENSOR_OK\n/ fault = false;\n  return true\n(L44, L48-49)",
          (133, 42), lsize=6.9, ha="right")
    self_loop(ax, 123, 66, "top", "MODE_EVT_SENSOR_OK [!fault] / return false (L45-47)", (123, 71.5))
    self_loop(ax, 123, 28, "bottom", "MODE_EVT_SENSOR_FAULT [fault] / return false (L39-41)", (123, 22.8))

    note(ax, 50, 2, 98, 17, "Rules from the code", [
        "MODE_EVT_NONE or any unknown event: nothing changes, return false (L50-52).",
        "MODE_EVT_NEXT works while paused and never changes paused or fault.",
        "A fault never changes the mode: scanning carries on so it can recover.",
        "A mode value out of range goes to MODE_SWEEP on MODE_EVT_NEXT (L32-33).",
        "Events come from input_task (D-MODEBTN still open: short press = NEXT, long = PAUSE).",
    ])
    legend_states(ax, 2, 2, extra=["dashed line: independent regions of one state"])
    return fig


def on_line_label(ax, x, y, text, size=7.6):
    """Label sitting on its arrow (background box hides the line under it)."""
    ax.text(x, y, text, fontsize=size, color=INK, ha="center", va="center", family="DejaVu Sans Mono",
            bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=LINE, lw=0.6), linespacing=1.25)


def target_track_diagram(cfg):
    fig, ax = new_canvas(190, 112, "target_track: lock-on tracker (D3)",
                         "components/target_track/target_track.c. track_state_t; events are calls to "
                         "target_track_on_pass() (once per pass) and target_track_on_ping() (every ping).")
    y0, h = 56, 9
    S, C, L = (14, y0, 30, h), (76, y0, 30, h), (138, y0, 30, h)
    top, bot, mid = y0 + h, y0, y0 + h / 2
    state(ax, *S, "TRACK_SEARCHING")
    state(ax, *C, "TRACK_CANDIDATE")
    state(ax, *L, "TRACK_LOCKED")
    initial(ax, 29, 90)
    trans(ax, (29, 88.8), (29, top), "target_track_init()\n/ lose() (L151-163)", (30.5, 82), ha="left")

    # SEARCHING
    self_loop(ax, 14, mid, "left", "on_pass\n[!c.valid]\n(L195)", (11, mid - 7), ha="right")
    trans(ax, (44, mid + 2), (76, mid + 2), None)
    ax.text(60, mid + 3.2, "on_pass [c.valid &&\n confirm_sweeps > 1]\n/ start_candidate(c):\n  seen_count = 1\n"
            "(L194-197, L181-187)", fontsize=7.2, color=INK, ha="center", va="bottom", family="DejaVu Sans Mono")
    trans(ax, (38, top), (144, top), None, rad=-0.45)
    on_line_label(ax, 91, top + 23.8, "on_pass [c.valid && confirm_sweeps <= 1] / start_candidate(c): "
                  "locks at once (L194-197, L186)", size=7.2)

    # CANDIDATE
    trans(ax, (76, mid - 2), (44, mid - 2), None)
    ax.text(60, mid - 3.2, "on_pass [!c.valid]\n/ lose() (L208-209)", fontsize=7.2, color=INK, ha="center",
            va="top", family="DejaVu Sans Mono")
    self_loop(ax, 91, top, "top", None, None)
    ax.text(91, top + 5.2, "on_pass [in_gate(c) &&\n ++seen_count < confirm_sweeps]\n/ target = c (L200-202)",
            fontsize=7.2, color=INK, ha="center", va="bottom", family="DejaVu Sans Mono")
    self_loop(ax, 91, bot, "bottom", None, None)
    ax.text(95, bot - 3.5, "candidate restart:\non_pass [!in_gate(c) && c.valid]\n/ start_candidate(c):\n"
            "  seen_count = 1 (L206-207)", fontsize=7.2, color=INK, ha="left", va="top", family="DejaVu Sans Mono")
    trans(ax, (106, mid + 2), (138, mid + 2), None)
    ax.text(122, mid + 3.2, "on_pass [in_gate(c) &&\n ++seen_count >=\n confirm_sweeps]\n/ target = c;\n"
            "  miss_count = 0\n(L200-205)", fontsize=7.2, color=INK, ha="center", va="bottom",
            family="DejaVu Sans Mono")

    # LOCKED self-transitions
    self_loop(ax, 160, top, "top", None, None)
    ax.text(156, top + 5.2, "on_pass [in_gate(c)]\n/ target = c;\n  miss_count = 0\n(L213-215)", fontsize=7.2,
            color=INK, ha="left", va="bottom", family="DejaVu Sans Mono")
    self_loop(ax, 168, mid, "right", None, None)
    ax.text(174, mid, "on_ping\n[near && hit]\n/ miss_count = 0\n(L233-237)", fontsize=7.2, color=INK,
            ha="left", va="center", family="DejaVu Sans Mono")
    self_loop(ax, 162, bot, "bottom", None, None)
    ax.text(166, bot - 3.5, "on_ping [near && !hit &&\n ++miss_count < lost_pings]\n/ ++miss_count\n(L238-240)",
            fontsize=7.2, color=INK, ha="left", va="top", family="DejaVu Sans Mono")

    # lost: LOCKED -> SEARCHING (two ways)
    trans(ax, (146, bot), (36, bot), None, rad=-0.3)
    on_line_label(ax, 91, bot - 16.5, "lost: on_pass [!in_gate(c)] / lose() (L216-217)")
    trans(ax, (152, bot), (22, bot), None, rad=-0.42)
    on_line_label(ax, 87, bot - 27.3, "lost: on_ping [near && !hit && ++miss_count >= lost_pings] / lose() "
                  "(L239-241)")

    note(ax, 52, 2, 136, 23, "Guards and names (from the code)", [
        "c          = target_track_find_cluster(): the NEAREST valid cluster of fresh OK bins (L107-141)",
        "in_gate(c) = c.valid && |c.centre_deg - target.centre_deg| <= gate_deg (L176-179)",
        "near       = target.left_deg <= angle_deg <= target.right_deg; other pings are ignored (L230-231)",
        "hit        = status == READING_OK && dist_cm <= max_range_cm && |dist_cm - target.dist_cm| <= dist_tol_cm"
        " (L233-235)",
        "on_ping does nothing unless TRACK_LOCKED (L227-228). \"lost\" is not a state: lose() sets TRACK_SEARCHING "
        "(L143-149).",
        f"confirm_sweeps = APP_LOCK_CONFIRM_SWEEPS ({cfg['APP_LOCK_CONFIRM_SWEEPS']}); lost_pings = "
        f"APP_LOCK_LOST_PINGS ({cfg['APP_LOCK_LOST_PINGS']}); dist_tol_cm = APP_LOCK_DIST_TOL_CM "
        f"({cfg['APP_LOCK_DIST_TOL_CM']}); gate_deg = APP_LOCK_SECTOR_HALF_DEG ({cfg['APP_LOCK_SECTOR_HALF_DEG']}, "
        "via lock_loop)",
        "target_track_reset(): any state -> TRACK_SEARCHING, limits back to the arc (L247-252).",
    ], size=7.2)
    legend_states(ax, 2, 2)
    return fig


def lock_loop_diagram(cfg):
    fig, ax = new_canvas(190, 112, "lock_loop: LOCK mode sweep plans (D3)",
                         "components/lock_loop/lock_loop.c. lock_plan_t; the event is lock_loop_on_reading() "
                         "(every ping). \"pass end\" = sweep_plan_take_pass_done() is true (L111).")
    lab = dict(size=7.0)
    F = (10, 62, 34, 9)
    SEC = (146, 62, 34, 9)
    state(ax, *F, "LOCK_PLAN_FULL")
    state(ax, *SEC, "LOCK_PLAN_SECTOR")
    initial(ax, 16, 92)
    trans(ax, (16, 90.8), (16, 71), None)
    ax.text(17.5, 84, "lock_loop_init()\n(L81-96)", fontsize=7.0, color=INK, ha="left", va="center",
            family="DejaVu Sans Mono")

    # FULL self-transition (still searching)
    self_loop(ax, 10, 66.5, "left", None, None)
    ax.text(1.5, 58.5, "pass end\n[st != TRACK_LOCKED]\n/ last_full_ms = now\n(L123-125)", fontsize=7.0,
            color=INK, ha="left", va="top", family="DejaVu Sans Mono")

    # FULL <-> SECTOR
    trans(ax, (44, 69), (146, 69), None)
    on_line_label(ax, 95, 69, "pass end [st == TRACK_LOCKED]\n/ last_full_ms = locked_at_ms = now; go_sector()"
                  " (L124-128)", **lab)
    trans(ax, (146, 64), (44, 64), None)
    on_line_label(ax, 95, 61.5, "pass end [st != TRACK_LOCKED] / go_full(ll, LOCK_PLAN_FULL) (L131-132)", **lab)

    # fast lost: any reading while the tracker is LOCKED (SECTOR or RESWEEP)
    trans(ax, (152, 71), (34, 71), None, rad=0.25)
    on_line_label(ax, 93, 85.7, "fast lost: every reading [track.state == TRACK_LOCKED &&\n"
                  " target_track_on_ping() != TRACK_LOCKED] / go_full(ll, LOCK_PLAN_FULL) (L106-109)\n"
                  "from LOCK_PLAN_SECTOR, and from LOCK_PLAN_RESWEEP (the tracker is LOCKED there too)", **lab)

    # SECTOR self-transition (recentre)
    self_loop(ax, 172, 71, "top", None, None)
    ax.text(172, 76.2, "pass end [st == TRACK_LOCKED &&\n !resweep_due]\n/ sweep_plan_recentre();\n"
            "  use_limits() (L136-137)", fontsize=7.0, color=INK, ha="center", va="bottom",
            family="DejaVu Sans Mono")

    # RESWEEP composite: choice on entry, then resweep_turned false -> true
    rx, ry, rw, rh = 58, 16, 68, 36
    ax.add_patch(FancyBboxPatch((rx, ry), rw, rh, boxstyle="round,pad=0,rounding_size=2.5", fc=PANEL,
                                ec=STATE_EDGE, lw=1.6))
    ax.text(rx + rw / 2, ry + rh - 1.3, "LOCK_PLAN_RESWEEP", fontsize=10.5, weight="bold", color=INK,
            ha="center", va="top", family="DejaVu Sans Mono")
    ax.text(rx + 1.5, ry + rh - 1.6, "entry / go_full():\n sweep_plan_full();\n resweep_turned =\n  at_arc_end()"
            " (L55-60)", fontsize=6.6, color=MUTED, va="top", family="DejaVu Sans Mono")
    chx, chy = 118, 40
    choice(ax, chx, chy)
    state(ax, 88, 38, 22, 7.5, "resweep_turned\n= false", size=8)
    state(ax, 90, 19, 22, 7.5, "resweep_turned\n= true", size=8)
    trans(ax, (chx - 1.6, chy), (110, 41.75), None)
    ax.text(119, 43.2, "[!at_arc_end()]", fontsize=6.6, color=INK, ha="center", va="bottom",
            family="DejaVu Sans Mono")
    trans(ax, (chx, chy - 1.6), (112, 22.75), None, rad=-0.3)
    ax.text(118.5, 31.5, "[at_arc_end()]\n(L59)", fontsize=6.6, color=INK, ha="left", va="center",
            family="DejaVu Sans Mono")
    trans(ax, (96, 38), (99, 26.5), None)
    ax.text(95.5, 32.3, "pass end\n[!resweep_turned]\n/ resweep_turned = true;\n  no on_pass (L115-117)",
            fontsize=6.6, color=INK, ha="right", va="center", family="DejaVu Sans Mono")

    # SECTOR -> RESWEEP (enters at the choice)
    trans(ax, (152, 62), (chx + 0.4, chy + 1.4), None, rad=0.1)
    on_line_label(ax, 140, 54, "pass end [st == TRACK_LOCKED &&\n resweep_due]\n/ go_full(ll, LOCK_PLAN_RESWEEP)\n"
                  "(L133-134)", **lab)

    # RESWEEP (turned) exits
    trans(ax, (112, 21), (170, 62), None, rad=0.35)
    on_line_label(ax, 160, 33, "pass end [resweep_turned &&\n st == TRACK_LOCKED]\n/ last_full_ms = now;\n"
                  "  go_sector() (L141-143)", **lab)
    trans(ax, (90, 21), (28, 62), None, rad=-0.35)
    on_line_label(ax, 33, 33, "pass end [resweep_turned &&\n st != TRACK_LOCKED]\n/ last_full_ms = now;\n"
                  "  go_full(ll, LOCK_PLAN_FULL)\n(L141, L144-145)", **lab)

    note(ax, 52, 2, 136, 12.5, "Guards and names (from the code)", [
        "st = target_track_on_pass(&ll->track, map, now_ms, max_age) at each counted pass end (L119-121); "
        "go_sector() = sweep_plan_sector() (L63-68)",
        f"resweep_due = resweep_ms > 0 && now_ms - last_full_ms >= resweep_ms (L133); resweep_ms = "
        f"APP_LOCK_RESWEEP_S ({cfg['APP_LOCK_RESWEEP_S']}) x 1000; sector = centre +/- APP_LOCK_SECTOR_HALF_DEG "
        f"({cfg['APP_LOCK_SECTOR_HALF_DEG']})",
        "at_arc_end() = plan.angle_deg at min_deg or max_deg (L49-53). Readings that are not a pass end change no "
        "plan (L111-113). lock_loop_reset(): any -> LOCK_PLAN_FULL (L152-158).",
    ], size=6.8)
    legend_states(ax, 2, 2, extra=["diamond: choice on entry (UML choice pseudostate)"])
    return fig


DIAGRAMS = [
    ("hardware", lambda c: hardware(read_pins())),
    ("state-mode-fsm", lambda c: mode_fsm_diagram()),
    ("state-target-track", target_track_diagram),
    ("state-lock-loop", lock_loop_diagram),
]


def main():
    cfg = read_defines()
    for name, make in DIAGRAMS:
        fig = make(cfg)
        for ext in ("svg", "png"):
            out = os.path.join(HERE, f"{name}.{ext}")
            fig.savefig(out, facecolor=fig.get_facecolor(), metadata={"Date": None} if ext == "svg" else None)
            print("wrote", os.path.relpath(out, ROOT))
        plt.close(fig)


if __name__ == "__main__":
    main()
