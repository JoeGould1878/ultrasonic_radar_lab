#!/usr/bin/env python3
"""
S4: PC radar view (docs/PLAN.md task S4; D-DISPLAY core display).

Implementation: Claude (Anthropic), for Joe Gould, built to the Display spec in
docs/PLAN.md. Credits: pygame (LGPL, https://www.pygame.org) for drawing,
pyserial for the port. Geometry follows components/radar_gfx/include/
radar_gfx.h (half-disc, sensor bottom centre, 90 deg straight up). No code
adapted.

INPUT  The R / M / T lines of the serial protocol (docs/PLAN.md "Serial
       protocol", main/serial_out.h), nothing else, so a recorded log, an S2
       scene and the live device all draw the same picture.
         --port /dev/ttyACM0        live, pyserial at 921600 baud
         --file LOG [--speed N]     replay a log at its own t_ms timing
         --sim SCENE [--passes N]   S2 scene from sim/scene.py (imported, read-only)

MODEL  Config, parser, state and clock are in tools/radar_model.py (tested by
       tools/test_radar_view.py); drawing is in tools/radar_draw.py.

RUN
    python tools/radar_view.py --port /dev/ttyACM0 [--log docs/evidence/logs/x.txt]
    python tools/radar_view.py --file docs/evidence/sim/s2_scenes/t1_fault.txt --speed 2
    python tools/radar_view.py --sim t1_move_v10
    python tools/radar_view.py --file LOG --screenshot out.png --at 7000   (headless)
    python tools/radar_view.py --sim t1_b90_r50 --bench 10                 (fps)
  Keys: q / Esc quit, l large text.
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

from radar_model import DeviceClock, RadarState, ViewConfig, line_t_ms

BAUD = 921600  # docs/PLAN.md "Serial protocol"


# ----------------------------------------------------------- sources ----
class Link:
    """Lines from a reader thread to the draw loop."""

    def __init__(self, name: str):
        self.name = name
        self.q: queue.Queue[str] = queue.Queue()
        self.up = False
        self.done = False
        self.error = ""
        self.stop = threading.Event()


def paced(lines, speed: float, link: Link) -> None:
    """Emit lines at their own t_ms timing (/ speed). Non-timed lines go at once."""
    link.up = True
    t0 = w0 = None
    for line in lines:
        if link.stop.is_set():
            return
        t = line_t_ms(line)
        if t is not None:
            if t0 is None or t < t0:
                t0, w0 = t, time.monotonic()
            wait = w0 + (t - t0) / 1000.0 / speed - time.monotonic()
            if wait > 0 and link.stop.wait(wait):
                return
        link.q.put(line)
    link.done = True


def file_lines(path: Path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        yield from f


def sim_lines(name: str, passes: int | None, seed: int):
    import scene   # sim/scene.py, read-only
    cfg, timing = scene.load()
    scenes = scene.build_scenes(timing)
    if name not in scenes:
        sys.exit(f"unknown scene {name!r}; try: python sim/scene.py --list")
    sc, sensor = scenes[name], scene.Sensor()
    readings, _ = scene.run_scene(sc, cfg, timing, sensor, seed, passes)
    yield scene.provenance(sc, sensor, seed)
    yield scene.format_m(0)
    for t, _, a, d, st in readings:
        yield scene.format_r(t, a, d, st)


def serial_reader(port: str, link: Link, log_path: Path | None) -> None:
    import serial   # pyserial
    log = open(log_path, "a", encoding="utf-8") if log_path else None
    try:
        while not link.stop.is_set():
            try:
                with serial.Serial(port, BAUD, timeout=0.2) as ser:
                    link.up, link.error = True, ""
                    while not link.stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode("utf-8", errors="replace")
                        link.q.put(line)
                        if log:
                            log.write(line if line.endswith("\n") else line + "\n")
                            log.flush()
            except (serial.SerialException, OSError) as e:
                link.up, link.error = False, str(e)
                link.stop.wait(1.0)          # retry: the board may be re-plugged
    finally:
        if log:
            log.close()


def start(target, *args) -> threading.Thread:
    th = threading.Thread(target=target, args=args, daemon=True)
    th.start()
    return th


# ---------------------------------------------------------------- main ----
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="PC radar view (S4); see the module docstring")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial port, e.g. /dev/ttyACM0")
    src.add_argument("--file", type=Path, help="replay a recorded log / S2 scene file")
    src.add_argument("--sim", metavar="SCENE", help="S2 scene name (python sim/scene.py --list)")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed for --file / --sim")
    ap.add_argument("--passes", type=int, help="--sim: number of passes")
    ap.add_argument("--seed", type=int, default=0, help="--sim: random seed")
    ap.add_argument("--log", type=Path, help="--port: append every raw line to this file")
    ap.add_argument("--large", action="store_true", help="large text")
    ap.add_argument("--size", default="1000x700", help="window size WxH")
    ap.add_argument("--screenshot", type=Path, help="render once, headless, save PNG, exit")
    ap.add_argument("--at", type=float, help="--screenshot: device time in ms (default: end)")
    ap.add_argument("--bench", type=float, metavar="SECONDS",
                    help="draw uncapped for this long and print the frame rate")
    a = ap.parse_args(argv)
    if a.speed <= 0:
        ap.error("--speed must be > 0")
    w, h = (int(v) for v in a.size.lower().split("x"))

    cfg = ViewConfig.load()
    state = RadarState(cfg)
    name = a.port or (a.file.name if a.file else f"sim:{a.sim}")

    if a.screenshot:
        lines = file_lines(a.file) if a.file else sim_lines(a.sim, a.passes, a.seed) if a.sim else None
        if lines is None:
            ap.error("--screenshot needs --file or --sim")
        last = None
        for line in lines:
            t = line_t_ms(line)
            if a.at is not None and t is not None and t > a.at:
                break
            state.feed_line(line)
            last = t if t is not None else last
        now = a.at if a.at is not None else last
        if now is not None:
            state.expire(now)
        import radar_draw
        radar_draw.screenshot(state, now, name, (w, h), a.large, a.screenshot)
        print(f"wrote {a.screenshot} at t={now} ms; counts {state.counts}")
        return

    link = Link(name)
    if a.port:
        start(serial_reader, a.port, link, a.log)
        speed = 1.0
    else:
        lines = file_lines(a.file) if a.file else sim_lines(a.sim, a.passes, a.seed)
        start(paced, lines, a.speed, link)
        speed = a.speed
    import radar_draw
    radar_draw.run(state, DeviceClock(speed), link, (w, h), a.large, a.bench)


if __name__ == "__main__":
    main()
