"""Generate the ultrasonic sonar diagrams (PLAN task D1).

    . .venv/bin/activate && python docs/diagrams/gen_diagrams.py

Writes hardware.svg + hardware.png next to this file.

Hardware block diagram only, for now. The firmware diagrams follow the
firmware diagram standard in docs/PLAN.md (D1/D3: ISO 5807 flowcharts and UML
state diagrams) and are added once the display_task/radar_gfx layout settles.

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


def main():
    pins = read_pins()
    fig = hardware(pins)
    for ext in ("svg", "png"):
        out = os.path.join(HERE, f"hardware.{ext}")
        fig.savefig(out, facecolor=fig.get_facecolor(), metadata={"Date": None} if ext == "svg" else None)
        print("wrote", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
