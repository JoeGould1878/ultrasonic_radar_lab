#!/usr/bin/env python3
"""
S4: how fast can matplotlib redraw the radar picture on this laptop? The
comparison behind choosing pygame for tools/radar_view.py (s4_summary.txt).

Implementation: Claude (Anthropic), for Joe Gould. No code adapted.

Draws the same content as radar_draw.py for one moment of an S2 scene (all
bins filled): unscanned wedges, 3 rings, 3 bearing lines, a dot / dash /
cross per bin with per-bin brightness, beam line, status text. Agg backend,
off-screen: this laptop's Python has no tkinter, so matplotlib has no window
backend without adding Qt or GTK, and Agg is an upper bound (a GUI backend
adds the copy to the screen on top).

  A  full redraw: clear and rebuild every artist each frame (what the pygame
     view does).
  B  update only: build artists once, change data/colours each frame, then
     canvas.draw() (the fastest matplotlib can go without blitting).

RUN  python tools/bench_matplotlib.py [--scene t1_noisy] [--seconds 8]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_model import RadarState, ViewConfig  # noqa: E402  (sets Agg)

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_state(scene: str):
    cfg = ViewConfig.load()
    st = RadarState(cfg)
    last = 0
    for ln in (ROOT / "docs/evidence/sim/s2_scenes" / f"{scene}.txt").read_text().splitlines():
        msg = st.feed_line(ln)
        if msg is not None:
            last = msg.t_ms
            if last > 2 * cfg.pass_ms:
                break
    return st, last


def xy(a, d):
    return d * math.cos(math.radians(a)), d * math.sin(math.radians(a))


def build(ax, st, now):
    cfg, R = st.cfg, st.cfg.max_range_cm
    ax.set_facecolor("#08100c")
    ax.set_xlim(-R * 1.1, R * 1.1)
    ax.set_ylim(-R * 0.05, R * 1.15)
    ax.set_aspect("equal")
    ax.axis("off")
    for a0, a1 in ((0, cfg.min_deg), (cfg.max_deg, 180)):
        pts = [(0, 0)] + [xy(a0 + (a1 - a0) * i / 20, R) for i in range(21)]
        ax.fill(*zip(*pts), color="#28282e")
    for ring in range(50, int(R) + 1, 50):
        ax.plot(*zip(*[xy(i, ring) for i in range(181)]), color="#225838", lw=1)
        ax.text(*xy(0, ring), f"{ring} cm", color="#6eaa82", ha="right", va="bottom", fontsize=9)
    for a in (cfg.min_deg, 90, cfg.max_deg):
        ax.plot(*zip((0, 0), xy(a, R)), color="#225838", lw=1)
        ax.text(*xy(a, R * 1.07), f"{a:g}°", color="#6eaa82", ha="center", fontsize=10)
    ok, ok_c, dash, dash_c, cross, cross_c = [], [], [], [], [], []
    for r in st.bins.values():
        f = st.freshness(r, now)
        if r.status == "OK":
            ok.append(xy(r.angle, r.dist))
            ok_c.append((0.27, 1.0, 0.47, f))
        elif r.status == "NOECHO":
            dash.append([xy(r.angle - 0.7, R), xy(r.angle + 0.7, R)])
            dash_c.append((0.63, 0.7, 0.86, 0.55 * f))
        else:
            cross.append(xy(r.angle, R))
            cross_c.append((1.0, 0.59, 0.16, f))
    sc = ax.scatter(*zip(*ok) if ok else ([], []), c=ok_c or None, s=20)
    lc = LineCollection(dash, colors=dash_c or None, linewidths=2)
    ax.add_collection(lc)
    if cross:
        ax.scatter(*zip(*cross), c=cross_c, marker="x", s=40)
    beam, = ax.plot(*zip((0, 0), xy(st.latest.angle, R)), color="#78ffa0", lw=2)
    txt = ax.text(0, R * 1.13, "SWEEP   52.3 cm   0.1 s ago", color="w", ha="center", fontsize=16)
    return sc, lc, beam, txt


def bench(fn, seconds):
    times = []
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        t0 = time.perf_counter()
        fn(len(times))
        times.append((time.perf_counter() - t0) * 1000)
    times = sorted(times[3:])
    mean = sum(times) / len(times)
    p95 = times[int(0.95 * (len(times) - 1))]
    return (f"frames {len(times)}  mean {mean:.1f} ms ({1000 / mean:.1f} fps)  "
            f"p95 {p95:.1f} ms ({1000 / p95:.1f} fps)  worst {times[-1]:.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="t1_noisy")
    ap.add_argument("--seconds", type=float, default=8)
    a = ap.parse_args()
    st, now = load_state(a.scene)
    fig = plt.figure(figsize=(10, 7), dpi=100, facecolor="#08100c")   # 1000 x 700 px
    ax = fig.add_axes((0, 0, 1, 1))

    def full(i):
        ax.clear()
        build(ax, st, now + i)
        fig.canvas.draw()

    sc, lc, beam, txt = build(ax, st, now)

    def update(i):
        a_ = 15 + (i * 2) % 150
        beam.set_data(*zip((0, 0), xy(a_, st.cfg.max_range_cm)))
        cols = sc.get_facecolors()
        if len(cols):
            cols[:, 3] = (cols[:, 3] * 0.999)
            sc.set_facecolors(cols)
        txt.set_text(f"SWEEP   {i % 150}.0 cm   0.1 s ago")
        fig.canvas.draw()

    print(f"matplotlib {plt.matplotlib.__version__}, backend {plt.get_backend()}, "
          f"1000x700 px, scene {a.scene}, {len(st.bins)} bins")
    print("A full redraw :", bench(full, a.seconds))
    print("B update only :", bench(update, a.seconds))


if __name__ == "__main__":
    main()
