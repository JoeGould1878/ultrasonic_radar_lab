"""
S4: the radar view's drawing (pygame), to the Display spec in docs/PLAN.md.

Implementation: Claude (Anthropic), for Joe Gould. Credits: pygame (LGPL,
https://www.pygame.org). Geometry follows radar_gfx_fit / radar_gfx_to_xy in
components/radar_gfx/include/radar_gfx.h. No code adapted.

What is drawn (Display spec section in brackets):
  - half-disc, sensor at bottom centre, 90 deg straight up, max range fits the
    window and scales with it (Geometry). 0 deg is on the RIGHT, as in S2
    (sim/scene.py: 0 deg = +x). PROPOSED until B1 fixes it against the tape
    marks and the servo mounting.
  - outside APP_SWEEP_MIN/MAX_DEG greyed and labelled "not scanned".
  - range rings every RING_STEP_CM with cm labels; bearing lines + labels at
    the arc ends and 90 deg (Range rings and labels).
  - beam line at the latest R angle (Beam line).
  - one mark per bin, shape per status (Readings): OK filled dot; NOECHO faint
    short dash across the bearing at the max-range ring; FAIL small cross on
    the outer ring. Brightness = freshness (Fading), linear to 0 at
    APP_FADE_SWEEPS passes; bins removed after APP_EXPIRE_SWEEPS passes.
  - STALE / SENSOR FAULT / PAUSED banners, each text + its own icon shape;
    STALE also dims the whole picture (Banners).
  - status strip: mode, live distance in large text (or "no echo" /
    "failed"), time since the last reading (Status strip).
  - LOCK: bracket from left_deg to right_deg at dist_cm, centre tick, state
    label, while the mode is LOCK (LOCK). The D-EDGE low-confidence mark is
    NOT drawn: the T line has no edge field yet (open question in PLAN).
  - legend with the three shapes and their words, large-text option ('l' or
    --large) (Accessibility).
"""
from __future__ import annotations

import math
import os
import time
from collections import deque

from radar_model import TRACK_HIDE_PASSES, RadarState, Reading

# Viewer-only constants (not in app_config.h; none is a design value). All
# PROPOSED: builder 2 lists them in the Display spec; O2 may change them.
RING_STEP_CM = 50          # Display spec: "PROPOSED every 50 cm"
FRAME_CAP_FPS = 60         # only stops the loop spinning; the floor is FLOOR_FPS (SC7)
NOECHO_MAX_BRIGHT = 0.55   # "faint" dash (Display spec, NOECHO row)
STALE_DIM_ALPHA = 150      # 0-255 darkening over the picture while STALE
EDGE_DASH_DEG = 2.0        # D-EDGE mark: dashed bracket, dash length in degrees
# (the "hide bracket after 2 passes without a T line" rule is TRACK_HIDE_PASSES in radar_model.py)

BG = (8, 16, 12)
GRID = (34, 88, 56)
GRID_TEXT = (110, 170, 130)
UNSCANNED = (40, 40, 46)
UNSCANNED_TEXT = (120, 120, 128)
TEXT = (215, 235, 220)
TEXT_DIM = (130, 150, 138)
BEAM = (120, 255, 160)
C_OK = (70, 255, 120)
C_NOECHO = (160, 180, 220)
C_FAIL = (255, 150, 40)
C_LOCK = (255, 220, 80)
B_STALE = ((60, 60, 60), (230, 230, 230))      # banner fill, border/text
B_FAULT = ((120, 10, 10), (255, 210, 210))
B_PAUSED = ((20, 40, 90), (210, 225, 255))


def _mix(col, b):
    b = max(0.0, min(1.0, b))
    return tuple(int(BG[i] + (col[i] - BG[i]) * b) for i in range(3))


class Renderer:
    def __init__(self, state: RadarState, large: bool = False):
        import pygame
        self.pg = pygame
        self.state = state
        self.cfg = state.cfg
        self.large = large
        self._fonts: dict[int, object] = {}
        self._size = None

    # ------------------------------------------------------- geometry ----
    def font(self, px: float):
        px = int(px * (1.5 if self.large else 1.0))
        if px not in self._fonts:
            self._fonts[px] = self.pg.font.Font(None, px)
        return self._fonts[px]

    def fit(self, w: int, h: int) -> None:
        """radar_gfx_fit: the max-range half-disc fits the window with a margin."""
        if self._size == (w, h):
            return
        self._size = (w, h)
        u = min(w, h)
        self.u = u
        self.strip_h = int(u * 0.11 * (1.4 if self.large else 1.0))
        self.foot_h = int(u * 0.045 * (1.3 if self.large else 1.0))
        # banner row reserved under the strip: banners never cover marks, and
        # the picture does not jump when one appears
        self.banner_h = int(u * 0.075 * (1.3 if self.large else 1.0))
        m = int(u * 0.07)
        top = self.strip_h + self.banner_h
        r = min((w - 2 * m) / 2, h - top - self.foot_h - 2 * m)
        self.r_px = max(r, 10)
        self.ox = w / 2
        self.oy = top + m + self.r_px
        self.scale = self.r_px / self.cfg.max_range_cm
        self.dot = max(3, int(u / 160))

    def xy(self, angle_deg: float, dist_cm: float):
        """radar_gfx_to_xy: 90 deg straight up, 0 deg to the right."""
        a = math.radians(angle_deg)
        r = dist_cm * self.scale
        return (self.ox + r * math.cos(a), self.oy - r * math.sin(a))

    def arc_pts(self, a0, a1, dist_cm, n=None):
        n = n or max(2, int(abs(a1 - a0)))
        return [self.xy(a0 + (a1 - a0) * i / n, dist_cm) for i in range(n + 1)]

    # ---------------------------------------------------------- draw ----
    def draw(self, surf, now_ms, link_up=True, link_note="", fps=None, source=""):
        pg, st, cfg = self.pg, self.state, self.cfg
        w, h = surf.get_size()
        self.fit(w, h)
        surf.fill(BG)
        R = cfg.max_range_cm

        # not-scanned wedges
        for a0, a1 in ((0.0, cfg.min_deg), (cfg.max_deg, 180.0)):
            if a1 > a0:
                pg.draw.polygon(surf, UNSCANNED, [(self.ox, self.oy)] + self.arc_pts(a0, a1, R))
                tx, ty = self.xy((a0 + a1) / 2, R * 0.72)
                self.text(surf, "not scanned", 0.026, UNSCANNED_TEXT, (tx, ty), "center")

        # range rings + labels (on the 0 deg baseline, in the unscanned wedge)
        ring = RING_STEP_CM
        while ring <= R + 1e-6:
            pg.draw.aalines(surf, GRID, False, self.arc_pts(0, 180, ring, 90))
            x, y = self.xy(0, ring)
            self.text(surf, f"{ring:g} cm", 0.028, GRID_TEXT, (x - 3, y - 4), "bottomright")
            ring += RING_STEP_CM
        pg.draw.aaline(surf, GRID, self.xy(0, R), self.xy(180, R))

        # bearing lines + labels at the arc ends and 90
        for a in (cfg.min_deg, 90.0, cfg.max_deg):
            pg.draw.aaline(surf, GRID, (self.ox, self.oy), self.xy(a, R))
            lx, ly = self.xy(a, R * 1.07)
            self.text(surf, f"{a:g}°", 0.03, GRID_TEXT, (lx, ly), "center")

        # beam line at the latest R angle
        if st.latest is not None:
            pg.draw.line(surf, BEAM, (self.ox, self.oy), self.xy(st.latest.angle, R), 2)

        # marks, oldest first so fresh ones are on top
        if now_ms is not None:
            for r in sorted(st.bins.values(), key=lambda r: r.t_ms):
                self.mark(surf, r, st.freshness(r, now_ms))

        # LOCK bracket from the T line
        if now_ms is not None:
            tr = st.lock_bracket(now_ms)
            if tr is not None:
                self.lock(surf, tr)
            t = st.track
            if (tr is None and t is not None and st.mode == "LOCK"
                    and now_ms - t.t_ms <= TRACK_HIDE_PASSES * self.cfg.pass_ms):
                self.text(surf, f"tracking: {t.state}", 0.03, C_LOCK,        # SEARCH / CAND: no bracket yet
                          (self.ox, self.oy - self.r_px * 0.25), "center")

        self.legend(surf)
        stale = st.is_stale(now_ms, link_up)
        if stale:   # dim everything drawn so far
            veil = pg.Surface((w, h - self.strip_h), pg.SRCALPHA)
            veil.fill((0, 0, 0, STALE_DIM_ALPHA))
            surf.blit(veil, (0, self.strip_h))

        self.strip(surf, now_ms)
        banners = []
        if st.fault:
            banners.append(("SENSOR FAULT", B_FAULT, self.icon_fault))
        if st.paused:
            banners.append(("PAUSED", B_PAUSED, self.icon_paused))
        if stale:
            why = link_note or ("no data yet" if st.latest is None else
                                f"no reading for {st.since_last_reading_ms(now_ms) / 1000:.1f} s")
            banners.append((f"STALE  ({why})", B_STALE, self.icon_stale))
        self.banners(surf, banners)
        self.footer(surf, fps, source)

    def mark(self, surf, r: Reading, fresh: float):
        pg, R = self.pg, self.cfg.max_range_cm
        if fresh <= 0:
            return
        if r.status == "OK":
            pg.draw.circle(surf, _mix(C_OK, fresh), self.xy(r.angle, r.dist), self.dot)
        elif r.status == "NOECHO":     # short dash across the bearing at max range
            half = self.cfg.step_deg * 0.35
            pg.draw.line(surf, _mix(C_NOECHO, fresh * NOECHO_MAX_BRIGHT),
                         self.xy(r.angle - half, R), self.xy(r.angle + half, R), max(2, self.dot - 1))
        else:                          # FAIL: small cross on the outer ring
            x, y = self.xy(r.angle, R)
            s = self.dot + 2
            col = _mix(C_FAIL, fresh)
            pg.draw.line(surf, col, (x - s, y - s), (x + s, y + s), 2)
            pg.draw.line(surf, col, (x - s, y + s), (x + s, y - s), 2)

    def lock(self, surf, t):
        pg = self.pg
        if t.left is not None and t.right is not None:
            d = t.dist if t.dist is not None else self.cfg.max_range_cm
            lo, hi = min(t.left, t.right), max(t.left, t.right)
            out = self.cfg.max_range_cm * 0.04      # bracket sits just beyond the target
            if t.edge:      # D-EDGE: dashed arc instead of a solid one
                a = lo
                while a < hi:
                    pg.draw.lines(surf, C_LOCK, False, self.arc_pts(a, min(a + EDGE_DASH_DEG, hi), d + out, 2), 2)
                    a += 2 * EDGE_DASH_DEG
            else:
                pg.draw.lines(surf, C_LOCK, False, self.arc_pts(lo, hi, d + out), 2)
            for a in (lo, hi):        # ends point in towards the target: [ ]
                pg.draw.line(surf, C_LOCK, self.xy(a, d + out), self.xy(a, max(0.0, d - out)), 2)
            if t.centre is not None:  # centre tick points out; edge: hollow circle (bearing uncertain)
                if t.edge:
                    pg.draw.circle(surf, C_LOCK, self.xy(t.centre, d + 2.5 * out), self.dot + 2, 2)
                else:
                    pg.draw.line(surf, C_LOCK, self.xy(t.centre, d + out), self.xy(t.centre, d + 2.5 * out), 3)
            lx, ly = self.xy((lo + hi) / 2, d + 4.5 * out)
            self.text(surf, "LOCK ? edge: low confidence" if t.edge else t.state, 0.032, C_LOCK, (lx, ly), "center")
        else:
            self.text(surf, t.state, 0.032, C_LOCK, (self.ox, self.oy - self.r_px * 0.25), "center")

    # ------------------------------------------------------ text bits ----
    def text(self, surf, s, size, col, pos, anchor="topleft"):
        img = self.font(self.u * size).render(s, True, col)
        rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        surf.blit(img, rect)
        return rect

    def strip(self, surf, now_ms):
        pg, st = self.pg, self.state
        w = surf.get_width()
        pg.draw.rect(surf, (14, 26, 20), (0, 0, w, self.strip_h))
        pg.draw.line(surf, GRID, (0, self.strip_h), (w, self.strip_h), 1)
        pad = self.u * 0.025
        mid = self.strip_h / 2
        self.text(surf, "MODE", 0.025, TEXT_DIM, (pad, pad * 0.6))
        self.text(surf, st.mode or "?", 0.065, TEXT, (pad, mid + pad * 0.3), "midleft")
        r = st.latest
        if r is None:
            big, small = "no data", ""
        else:
            big = {"OK": f"{r.dist:.1f} cm" if r.dist is not None else "",
                   "NOECHO": "no echo", "FAIL": "failed"}[r.status]
            small = f"at {r.angle:g}°"
        self.text(surf, "AT THE BEAM", 0.025, TEXT_DIM, (w / 2, pad * 0.6), "midtop")
        rect = self.text(surf, big, 0.085, TEXT, (w / 2, mid + pad * 0.4), "center")
        self.text(surf, small, 0.03, TEXT_DIM, (rect.right + pad * 0.5, rect.bottom - pad * 0.3), "bottomleft")
        age = st.since_last_reading_ms(now_ms) if now_ms is not None else None
        self.text(surf, "LAST READING", 0.025, TEXT_DIM, (w - pad, pad * 0.6), "topright")
        self.text(surf, "-" if age is None else f"{age / 1000:.1f} s ago", 0.05, TEXT,
                  (w - pad, mid + pad * 0.3), "midright")

    def legend(self, surf):
        pg = self.pg
        items = (("echo (distance)", "OK"), ("no echo", "NOECHO"), ("failed reading", "FAIL"))
        n = self.cfg.fade_ms / self.cfg.pass_ms
        fade = f"fades over {n:g} passes ({self.cfg.fade_ms / 1000:g} s)"
        tw = max(self.font(self.u * 0.027).size(t)[0] for t, _ in items)
        tw = max(tw + 22, self.font(self.u * 0.024).size(fade)[0] + 8)
        x = surf.get_width() - self.u * 0.02 - tw + 8
        y = self.strip_h + self.banner_h + self.u * 0.02
        step = self.u * 0.035 * (1.4 if self.large else 1.0)
        for i, (word, kind) in enumerate(items):
            cy = y + i * step
            if kind == "OK":
                pg.draw.circle(surf, C_OK, (x, cy), self.dot)
            elif kind == "NOECHO":
                pg.draw.line(surf, _mix(C_NOECHO, NOECHO_MAX_BRIGHT), (x - 7, cy), (x + 7, cy), max(2, self.dot - 1))
            else:
                s = self.dot + 2
                pg.draw.line(surf, C_FAIL, (x - s, cy - s), (x + s, cy + s), 2)
                pg.draw.line(surf, C_FAIL, (x - s, cy + s), (x + s, cy - s), 2)
            self.text(surf, word, 0.027, TEXT_DIM, (x + 14, cy), "midleft")
        self.text(surf, fade, 0.024, TEXT_DIM, (x - 8, y + 3 * step), "midleft")

    def footer(self, surf, fps, source):
        st = self.state
        w, h = surf.get_size()
        c = st.counts
        left = (f"{source}   R {c['R']}  M {c['M']}  T {c['T']}   bad {c['bad']}  "
                f"ignored {c['ignored']}" + (f"  restarts {c['restarts']}" if c["restarts"] else ""))
        self.text(surf, left, 0.026, TEXT_DIM, (self.u * 0.02, h - self.u * 0.01), "bottomleft")
        if fps is not None:
            low = fps < self.cfg.floor_fps
            s = f"{fps:.0f} fps" + (f"  BELOW {self.cfg.floor_fps:g} fps FLOOR" if low else "")
            self.text(surf, s, 0.026, C_FAIL if low else TEXT_DIM, (w - self.u * 0.02, h - self.u * 0.01),
                      "bottomright")

    # --------------------------------------------------------- banners ----
    def banners(self, surf, banners):
        """Side by side in the banner row, shrunk to fit the window width."""
        if not banners:
            return
        pg = self.pg
        w = surf.get_width()
        gap = self.u * 0.02
        px = self.banner_h * 0.62
        while True:
            imgs = [self.pg.font.Font(None, int(px)).render(t, True, c[1]) for t, c, _ in banners]
            ih = imgs[0].get_height()
            widths = [im.get_width() + ih * 2.0 for im in imgs]
            total = sum(widths) + gap * (len(imgs) - 1)
            if total <= w - 2 * gap or px < 12:
                break
            px *= 0.9
        x = (w - total) / 2
        y = self.strip_h + (self.banner_h - ih * 1.45) / 2
        for (text, (fill, fg), icon), img, bw in zip(banners, imgs, widths):
            rect = pg.Rect(int(x), int(y), int(bw), int(ih * 1.45))
            pg.draw.rect(surf, fill, rect)
            pg.draw.rect(surf, fg, rect, 3)
            icon(surf, fg, (rect.left + ih * 0.8, rect.centery), ih * 0.38)
            surf.blit(img, img.get_rect(midleft=(rect.left + ih * 1.55, rect.centery)))
            x += bw + gap

    def icon_stale(self, surf, col, c, s):       # hourglass
        x, y = c
        self.pg.draw.polygon(surf, col, [(x - s, y - s), (x + s, y - s), (x, y)])
        self.pg.draw.polygon(surf, col, [(x - s, y + s), (x + s, y + s), (x, y)])

    def icon_fault(self, surf, col, c, s):       # warning triangle with "!"
        x, y = c
        self.pg.draw.polygon(surf, col, [(x, y - s * 1.1), (x + s * 1.1, y + s), (x - s * 1.1, y + s)], 3)
        self.pg.draw.line(surf, col, (x, y - s * 0.4), (x, y + s * 0.3), 3)
        self.pg.draw.circle(surf, col, (x, y + s * 0.65), 2)

    def icon_paused(self, surf, col, c, s):      # two bars
        x, y = c
        self.pg.draw.rect(surf, col, (x - s * 0.8, y - s, s * 0.55, 2 * s))
        self.pg.draw.rect(surf, col, (x + s * 0.25, y - s, s * 0.55, 2 * s))


# ---------------------------------------------------------- entry points ----
def screenshot(state, now_ms, source, size, large, path) -> None:
    """Draw one frame off-screen (no window) and save it as PNG."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    surf = pygame.Surface(size)
    Renderer(state, large).draw(surf, now_ms, True, "", None, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(path))
    pygame.quit()


def run(state, clock, link, size, large, bench_s=None) -> None:
    import pygame
    pygame.init()
    screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    pygame.display.set_caption(f"radar_view - {link.name}")
    rend = Renderer(state, large)
    tick = pygame.time.Clock()
    frame_ms: deque[float] = deque(maxlen=60)
    bench: list[float] = []
    t_start = time.perf_counter()
    last = t_start
    restarts = 0
    try:
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_q, pygame.K_ESCAPE)):
                    return
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_l:
                    rend.large = not rend.large
                    rend._size = None
            while True:                       # every line that arrived -> this frame
                try:
                    line = link.q.get_nowait()
                except Exception:
                    break
                msg = state.feed_line(line)
                if msg is not None:
                    clock.sync(msg.t_ms, restarted=state.counts["restarts"] != restarts)
                    restarts = state.counts["restarts"]
            now = clock.now_ms()
            if now is not None:
                state.expire(now)
            fps = 1000.0 / (sum(frame_ms) / len(frame_ms)) if frame_ms else None
            note = "" if link.up else (f"port down: {link.error}" if link.error else "port not open")
            rend.draw(screen, now, link.up, note, fps, link.name + ("  (end of file)" if link.done else ""))
            pygame.display.flip()
            tick.tick(0 if bench_s else FRAME_CAP_FPS)
            t = time.perf_counter()
            frame_ms.append((t - last) * 1000.0)
            if bench_s:
                bench.append((t - last) * 1000.0)
                if t - t_start >= bench_s:
                    _report(bench, state.cfg.floor_fps)
                    return
            last = t
    finally:
        link.stop.set()
        pygame.quit()


def _report(frames_ms: list[float], floor: float) -> None:
    f = sorted(frames_ms[5:] or frames_ms)       # drop window start-up frames
    n = len(f)
    mean = sum(f) / n
    p95 = f[int(0.95 * (n - 1))]
    print(f"frames {n}  mean {mean:.2f} ms ({1000 / mean:.1f} fps)  "
          f"p95 {p95:.2f} ms ({1000 / p95:.1f} fps)  worst {f[-1]:.2f} ms  "
          f"frames over {1000 / floor:.0f} ms: {sum(x > 1000 / floor for x in f)}")
