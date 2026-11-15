"""Animated "predicting the future" SVG: a football motion forecast and a dashcam tracker.

Everything is simulated here in plain Python and baked into SMIL keyframes, so the
SVG needs no JavaScript and animates inside a GitHub README <img>:

* Left, a top-down pitch. 16 players move on smooth periodic paths. Every frame,
  each player's next 2 s is forecast from its current velocity and acceleration
  (a dashed line plus an uncertainty disc), and the ball carrier's most likely
  pass is scored from distance, openness and progress.
* Right, a dashcam view in true perspective. Cars are tracked with IDs. Each has
  a predicted 2 s path drawn on the road, the lead car's time-to-collision is
  computed live, and a lane change into the ego lane raises a cut-in alert.

The predictions are computed from the motion they forecast, not hand-drawn, so
they can be wrong just as a real model can.
"""
from __future__ import annotations

import math
from html import escape

TAU = math.tau


def _f(v: float) -> str:
    s = f"{v:.1f}"
    return "0" if s == "-0.0" else s.rstrip("0").rstrip(".") if "." in s else s


def _pts(points) -> str:
    return " ".join(f"{_f(a)},{_f(b)}" for a, b in points)


def _vals(seq) -> str:
    return ";".join(seq)


def _anim(attr: str, values, dur: float, discrete: bool = False) -> str:
    mode = ' calcMode="discrete"' if discrete else ""
    return f'<animate attributeName="{attr}" dur="{dur}s" repeatCount="indefinite"{mode} values="{_vals(values)}"/>'


def _translate(values, dur: float, extra: str = "") -> str:
    return (f'<animateTransform attributeName="transform" type="translate" dur="{dur}s" '
            f'repeatCount="indefinite" values="{_vals(values)}"{extra}/>')


def _smooth(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _window(t: float, a: float, b: float, ramp: float = 0.25) -> float:
    """1 inside [a, b], easing to 0 over `ramp` seconds outside."""
    return min(_smooth((t - a + ramp) / ramp), _smooth((b + ramp - t) / ramp))


# --------------------------------------------------------------------------- football

class Pitch:
    T = 16.0
    N = 64
    LEN, WID = 105.0, 68.0
    HORIZON = 2.0

    # (base x, base y, wobble amplitude)
    TEAM_A = [(9, 34, 1.2), (30, 13, 3), (27, 34, 2.5), (30, 55, 3), (47, 23, 4), (45, 46, 4), (64, 30, 4.5), (66, 53, 4.5)]
    TEAM_B = [(96, 34, 1.2), (79, 15, 3), (81, 34, 2.5), (79, 53, 3), (66, 22, 3.5), (63, 44, 3.5), (47, 33, 4), (49, 57, 4)]

    def __init__(self) -> None:
        self.dt = self.T / self.N
        rnd = _Rand(7)
        self.wob = []
        for _ in range(len(self.TEAM_A) + len(self.TEAM_B)):
            self.wob.append([(rnd.pick([1, 2, 3]), rnd.uniform(0, TAU), rnd.pick([1, 2, 3]), rnd.uniform(0, TAU), rnd.uniform(0.6, 1.0))
                             for _ in range(2)])
        self._schedule()

    def pos(self, i: int, t: float) -> tuple[float, float]:
        team_a = i < len(self.TEAM_A)
        bx, by, amp = (self.TEAM_A + self.TEAM_B)[i]
        w = TAU * t / self.T
        shift = 9 * math.sin(w) + 3.5 * math.sin(2 * w + 1.1)          # the block pushes up and drops back
        side = 7 * math.sin(2 * w + 0.4)                                # and slides towards the ball side
        gk = bx < 12 or bx > 93
        k = 0.25 if gk else 1.0
        x = bx + k * (shift if team_a else 0.75 * shift)
        y = by + k * 0.6 * side * (1 if team_a else 0.8)
        (k1, p1, k2, p2, a1), (k3, p3, k4, p4, a2) = self.wob[i]
        x += amp * a1 * (0.7 * math.sin(k1 * w + p1) + 0.3 * math.sin(k2 * w + p2))
        y += amp * a2 * (0.7 * math.sin(k3 * w + p3) + 0.3 * math.sin(k4 * w + p4))
        return min(max(x, 2), self.LEN - 2), min(max(y, 2), self.WID - 2)

    def vel_acc(self, i: int, t: float):
        h = 0.05
        p0, p1, p2 = self.pos(i, t - h), self.pos(i, t), self.pos(i, t + h)
        v = ((p2[0] - p0[0]) / (2 * h), (p2[1] - p0[1]) / (2 * h))
        a = ((p2[0] - 2 * p1[0] + p0[0]) / h ** 2, (p2[1] - 2 * p1[1] + p0[1]) / h ** 2)
        return p1, v, a

    def forecast(self, i: int, t: float, steps: int = 6):
        """Constant-velocity forecast with damped acceleration, as a simple motion model would do."""
        p, v, a = self.vel_acc(i, t)
        out = []
        for s in range(steps + 1):
            tau = self.HORIZON * s / steps
            damp = 0.45 * tau * tau * math.exp(-tau / 1.2)
            out.append((p[0] + v[0] * tau + a[0] * damp, p[1] + v[1] * tau + a[1] * damp))
        return out, math.hypot(*v)

    # pass scoring ------------------------------------------------------------
    def pass_scores(self, holder: int, t: float):
        hx, hy = self.pos(holder, t)
        opp = [self.pos(j, t) for j in range(len(self.TEAM_A), len(self.TEAM_A) + len(self.TEAM_B))]
        scores = {}
        for j in range(1, len(self.TEAM_A)):
            if j == holder:
                continue
            x, y = self.pos(j, t)
            d = math.hypot(x - hx, y - hy)
            if d < 6:
                continue
            open_ = min(math.hypot(x - ox, y - oy) for ox, oy in opp)
            lane = min(_seg_dist((ox, oy), (hx, hy), (x, y)) for ox, oy in opp)
            scores[j] = -d / 11 + min(open_, 12) / 4 + min(lane, 8) / 3 + (x - hx) / 18
        z = max(scores.values())
        e = {j: math.exp(2.2 * (s - z)) for j, s in scores.items()}
        tot = sum(e.values())
        return {j: v / tot for j, v in e.items()}

    def _schedule(self) -> None:
        self.seg = 2.0
        self.hold = 1.35
        holders = [4]
        n = int(self.T / self.seg)
        for k in range(1, n):
            t = k * self.seg
            sc = self.pass_scores(holders[-1], t - self.seg + self.hold)
            ranked = sorted(sc, key=sc.get, reverse=True)
            nxt = next(j for j in ranked if j != (holders[-2] if len(holders) > 1 else -1))
            holders.append(nxt)
        holders.append(holders[0])
        self.holders = holders

    def ball(self, t: float):
        t %= self.T
        k = int(t // self.seg)
        u = t - k * self.seg
        a, b = self.holders[k], self.holders[k + 1]
        if u <= self.hold:
            x, y = self.pos(a, t)
            return x + 1.1, y + 0.4, a, False
        s = (u - self.hold) / (self.seg - self.hold)
        s = 1 - (1 - s) ** 1.6                       # a struck ball slows down as it rolls
        x0, y0 = self.pos(a, k * self.seg + self.hold)
        x1, y1 = self.pos(b, (k + 1) * self.seg)
        return x0 + 1.1 + (x1 - x0) * s, y0 + 0.4 + (y1 - y0) * s, a, True


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy or 1
    u = min(max(((px - ax) * dx + (py - ay) * dy) / L, 0), 1)
    return math.hypot(px - ax - u * dx, py - ay - u * dy)


class _Rand:
    """Tiny deterministic LCG so the artwork never changes between builds."""

    def __init__(self, seed: int) -> None:
        self.s = seed

    def _next(self) -> float:
        self.s = (1103515245 * self.s + 12345) % 2 ** 31
        return self.s / 2 ** 31

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._next()

    def pick(self, seq):
        return seq[int(self._next() * len(seq)) % len(seq)]


def football_panel(ox: float, oy: float, w: float, h: float, th: dict) -> str:
    P = Pitch()
    T, N, dt = P.T, P.N, P.dt
    vx, vy, vw, vh = ox + 16, oy + 54, w - 32, h - 54 - 40
    sx, sy = vw / P.LEN, vh / P.WID

    def m(p):
        return vx + p[0] * sx, vy + p[1] * sy

    nA = len(P.TEAM_A)
    nP = nA + len(P.TEAM_B)
    colA, colB = "#22D3EE", "#F472B6"
    frames = [f * dt for f in range(N + 1)]

    # pitch markings
    line = 'stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="1.3" fill="none"'
    cx, cy = m((P.LEN / 2, P.WID / 2))
    stripes = "".join(
        f'<rect x="{_f(vx + i * vw / 12)}" y="{vy}" width="{_f(vw / 12 + 0.5)}" height="{vh}" fill="#FFFFFF" fill-opacity="{0.035 if i % 2 else 0}"/>'
        for i in range(12))
    box = lambda x0, x1, y0, y1: f'<rect x="{_f(m((x0, y0))[0])}" y="{_f(m((x0, y0))[1])}" width="{_f((x1 - x0) * sx)}" height="{_f((y1 - y0) * sy)}" {line}/>'
    marks = (f'<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" {line}/>'
             f'<line x1="{_f(cx)}" y1="{vy}" x2="{_f(cx)}" y2="{vy + vh}" {line}/>'
             f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(9.15 * sx)}" {line}/>'
             f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="1.8" fill="#fff" fill-opacity="0.6"/>'
             + box(0, 16.5, 13.85, 54.15) + box(0, 5.5, 24.85, 43.15)
             + box(88.5, 105, 13.85, 54.15) + box(99.5, 105, 24.85, 43.15))

    # forecasts, trails and players
    preds, discs, trails, players = [], [], [], []
    for i in range(nP):
        col = colA if i < nA else colB
        pv, dv, rv, tv, gv = [], [], [], [], []
        for t in frames:
            fc, speed = P.forecast(i, t)
            pv.append(_pts(m(p) for p in fc))
            ex, ey = m(fc[-1])
            dv.append(f"{_f(ex)}")
            rv.append(f"{_f(ey)}")
            tv.append(_f(sx * (1.1 + 0.32 * speed)))
            trail = [m(P.pos(i, t - k * 0.25)) for k in range(5)]
            gv.append(_pts(trail))
        op = 0.95 if i < nA else 0.7
        preds.append(f'<polyline fill="none" stroke="{col}" stroke-opacity="{op}" stroke-width="2" stroke-dasharray="4 3" '
                     f'stroke-linecap="round">{_anim("points", pv, T)}</polyline>')
        discs.append(f'<circle fill="{col}" fill-opacity="0.13" stroke="{col}" stroke-opacity="0.55" stroke-width="0.8">'
                     f'{_anim("cx", dv, T)}{_anim("cy", rv, T)}{_anim("r", tv, T)}</circle>')
        trails.append(f'<polyline fill="none" stroke="#FFFFFF" stroke-opacity="0.22" stroke-width="2.4" stroke-linecap="round" '
                      f'stroke-linejoin="round">{_anim("points", gv, T)}</polyline>')
        pos = [f"{_f(m(P.pos(i, t))[0])},{_f(m(P.pos(i, t))[1])}" for t in frames]
        gk = i in (0, nA)
        fill = ("#FBBF24" if i == 0 else "#A3E635") if gk else col
        players.append(f'<g><circle r="9" fill="{fill}" fill-opacity="0.18"/><circle r="5.6" fill="{fill}" stroke="#0B1220" stroke-width="1.6"/>'
                       f'{_translate(pos, T)}</g>')

    # ball and its predicted pass
    ball_pos, ring_pos, arrow, arrow_op, labels = [], [], [], [], {}
    lab_frames = []
    for f, t in enumerate(frames):
        bx, by, holder, flying = P.ball(t)
        bpx, bpy = m((bx, by))
        ball_pos.append(f"{_f(bpx)},{_f(bpy)}")
        sc = P.pass_scores(holder, t)
        j = max(sc, key=sc.get)
        rx, ry = m(P.pos(j, t))
        hx, hy = m(P.pos(holder, t))
        ring_pos.append(f"{_f(rx)},{_f(ry)}")
        d = math.hypot(rx - hx, ry - hy) or 1
        ux, uy = (rx - hx) / d, (ry - hy) / d
        arrow.append((hx + ux * 9, hy + uy * 9, rx - ux * 11, ry - uy * 11))
        u = t % P.seg
        visible = 0.0 if flying else _window(u, 0.25, P.hold - 0.1, 0.2)
        arrow_op.append(_f(visible))
        lab = f"NEXT PASS  {round(sc[j] * 100)}%"
        lab_frames.append(lab if visible > 0.5 else None)
        labels.setdefault(lab, None)

    arr = (f'<line stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" marker-end="url(#fh-arrow)">'
           + _anim("x1", [_f(a[0]) for a in arrow], T) + _anim("y1", [_f(a[1]) for a in arrow], T)
           + _anim("x2", [_f(a[2]) for a in arrow], T) + _anim("y2", [_f(a[3]) for a in arrow], T)
           + _anim("opacity", arrow_op, T) + "</line>")
    ring = (f'<g><circle r="11" fill="none" stroke="#FFFFFF" stroke-width="1.6"><animate attributeName="r" values="9;14;9" dur="1.2s" repeatCount="indefinite"/></circle>'
            f'{_translate(ring_pos, T)}{_anim("opacity", arrow_op, T)}</g>')
    ball = (f'<g><circle r="6" fill="#FFFFFF" fill-opacity="0.25"/><circle r="3.4" fill="#FFFFFF" stroke="#0B1220" stroke-width="1"/>'
            f'{_translate(ball_pos, T)}</g>')

    # pass-probability chip, one text per distinct value, shown frame by frame
    chip_x, chip_y = vx + vw - 8, vy + 10
    chip = (f'<rect x="{_f(chip_x - 128)}" y="{_f(chip_y)}" width="128" height="24" rx="12" fill="#0B1220" fill-opacity="0.72" stroke="#FFFFFF" stroke-opacity="0.25">'
            f'{_anim("opacity", ["1" if l else "0" for l in lab_frames], T, True)}</rect>')
    for lab in labels:
        chip += (f'<text x="{_f(chip_x - 64)}" y="{_f(chip_y + 16)}" text-anchor="middle" font-family="{th["MONO"]}" font-size="11" '
                 f'font-weight="700" fill="#FFFFFF" opacity="0">{escape(lab)}'
                 f'{_anim("opacity", ["1" if l == lab else "0" for l in lab_frames], T, True)}</text>')

    return f'''
<g>
<rect x="{ox + 0.5}" y="{oy + 0.5}" width="{w - 1}" height="{h - 1}" rx="20" fill="{th["card"]}" stroke="{th["border"]}"/>
<text x="{ox + 20}" y="{oy + 26}" font-family="{th["MONO"]}" font-size="11.5" font-weight="700" letter-spacing="1.4" fill="{th["accent"]}">PLAYER MOTION FORECAST</text>
<text x="{ox + 20}" y="{oy + 43}" font-family="{th["SANS"]}" font-size="14" font-weight="700" fill="{th["text"]}">Every player’s next 2 s, re-predicted live</text>
<text x="{ox + w - 20}" y="{oy + 26}" text-anchor="end" font-family="{th["MONO"]}" font-size="11" fill="{th["muted"]}">16 tracks · t + 2.0 s</text>
<clipPath id="fh-pitch"><rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" rx="10"/></clipPath>
<g clip-path="url(#fh-pitch)">
<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="url(#fh-grass)"/>
{stripes}
{marks}
{"".join(trails)}
{"".join(discs)}
{"".join(preds)}
{arr}
{ring}
{"".join(players)}
{ball}
{chip}
</g>
<g font-family="{th["MONO"]}" font-size="11" fill="{th["muted"]}">
<circle cx="{ox + 26}" cy="{oy + h - 18}" r="4.5" fill="{colA}"/><text x="{ox + 36}" y="{oy + h - 14}">attack</text>
<circle cx="{ox + 96}" cy="{oy + h - 18}" r="4.5" fill="{colB}"/><text x="{ox + 106}" y="{oy + h - 14}">defence</text>
<line x1="{ox + 176}" y1="{oy + h - 18}" x2="{ox + 200}" y2="{oy + h - 18}" stroke="{th["strong"]}" stroke-width="1.6" stroke-dasharray="3 3"/><text x="{ox + 207}" y="{oy + h - 14}">forecast</text>
<circle cx="{ox + 284}" cy="{oy + h - 18}" r="5" fill="{th["strong"]}" fill-opacity="0.15" stroke="{th["strong"]}" stroke-width="0.8"/><text x="{ox + 295}" y="{oy + h - 14}">uncertainty</text>
<text x="{ox + w - 20}" y="{oy + h - 14}" text-anchor="end">FutureHuman3D</text>
</g>
</g>'''


# --------------------------------------------------------------------------- dashcam

class Road:
    T = 16.0
    N = 64
    V = 20.0          # ego speed, m/s
    CAM_H = 1.3
    LANE = 3.6

    def __init__(self, vx, vy, vw, vh) -> None:
        self.cx = vx + vw / 2
        self.hy = vy + vh * 0.36
        self.f = vw * 0.92

    def proj(self, x: float, z: float, y: float = 0.0):
        z = max(z, 0.6)
        return self.cx + self.f * x / z, self.hy + self.f * (self.CAM_H - y) / z

    # cars: (id, kind, colour) and their relative state at time t ----------------
    CARS = [("21", "truck", "#CBD5E1"), ("07", "car", "#60A5FA"), ("12", "car", "#F8FAFC"), ("03", "car", "#F87171")]

    def state(self, k: int, t: float):
        """Returns x, z (m, relative to ego), brake (0..1), visible (0..1)."""
        t %= self.T
        if k == 0:   # slow truck far ahead in the right lane
            return self.LANE + 0.1 * math.sin(TAU * t / self.T), 62 - 6 * math.sin(TAU * t / self.T), 0.0, 1.0
        if k == 1:   # lead car: brakes hard, then pulls away again
            close = _smooth((t - 1.2) / 2.6)
            away = _smooth((t - 4.6) / 6.5)
            z = 24 - 15.5 * close + 15.5 * away
            brake = _window(t, 1.3, 4.4, 0.3)
            return 0.05 * math.sin(TAU * t / 8), z, brake, 1.0
        if k == 2:   # cut-in from the right lane, then back out
            cut = _smooth((t - 8.6) / 2.4) - _smooth((t - 13.2) / 2.4)
            return self.LANE * (1 - 0.9 * cut), 13.5 + 1.5 * math.sin(TAU * t / self.T + 1), 0.0, 1.0
        # overtaking car in the left lane: drives from behind into the distance
        z = 1.5 + 46 * (t / self.T)
        vis = min(_smooth((z - 3) / 4), _smooth((47 - z) / 6))
        return -self.LANE, z, 0.0, vis

    def vel(self, k: int, t: float):
        h = 0.05
        a, b = self.state(k, t - h), self.state(k, t + h)
        return (b[0] - a[0]) / (2 * h), (b[1] - a[1]) / (2 * h)


def _car_shape(kind: str, colour: str, brake_anim: str) -> str:
    """Rear view in metres; origin at the ground centre, y up = negative."""
    if kind == "truck":
        return ('<ellipse cx="0" cy="0" rx="1.5" ry="0.16" fill="#000" fill-opacity="0.45"/>'
                '<rect x="-1.25" y="-3.4" width="2.5" height="3.0" rx="0.08" fill="#94A3B8"/>'
                '<rect x="-1.25" y="-3.4" width="2.5" height="3.0" rx="0.08" fill="url(#fh-body)"/>'
                '<rect x="-1.05" y="-3.2" width="2.1" height="2.4" fill="none" stroke="#475569" stroke-width="0.05"/>'
                '<rect x="-1.2" y="-0.55" width="0.32" height="0.16" fill="#EF4444"/><rect x="0.88" y="-0.55" width="0.32" height="0.16" fill="#EF4444"/>'
                '<rect x="-1.1" y="-0.4" width="0.5" height="0.4" fill="#0F172A"/><rect x="0.6" y="-0.4" width="0.5" height="0.4" fill="#0F172A"/>')
    return (f'<ellipse cx="0" cy="0" rx="1.08" ry="0.13" fill="#000" fill-opacity="0.5"/>'
            f'<rect x="-0.82" y="-0.3" width="0.36" height="0.3" rx="0.06" fill="#0B0F17"/><rect x="0.46" y="-0.3" width="0.36" height="0.3" rx="0.06" fill="#0B0F17"/>'
            f'<path d="M-0.72 -1.02 L-0.58 -1.44 Q0 -1.5 0.58 -1.44 L0.72 -1.02 Z" fill="{colour}"/>'
            f'<path d="M-0.6 -1.06 L-0.5 -1.36 Q0 -1.41 0.5 -1.36 L0.6 -1.06 Z" fill="#0F172A" fill-opacity="0.85"/>'
            f'<rect x="-0.9" y="-1.06" width="1.8" height="0.82" rx="0.2" fill="{colour}"/>'
            f'<rect x="-0.9" y="-1.06" width="1.8" height="0.82" rx="0.2" fill="url(#fh-body)"/>'
            f'<rect x="-0.84" y="-0.92" width="0.42" height="0.15" rx="0.05" fill="#DC2626"/>'
            f'<rect x="0.42" y="-0.92" width="0.42" height="0.15" rx="0.05" fill="#DC2626"/>'
            f'<g opacity="0">{brake_anim}<ellipse cx="-0.63" cy="-0.85" rx="0.45" ry="0.22" fill="#FF3B3B" fill-opacity="0.55"/>'
            f'<ellipse cx="0.63" cy="-0.85" rx="0.45" ry="0.22" fill="#FF3B3B" fill-opacity="0.55"/>'
            f'<rect x="-0.84" y="-0.92" width="0.42" height="0.15" rx="0.05" fill="#FFB4B4"/><rect x="0.42" y="-0.92" width="0.42" height="0.15" rx="0.05" fill="#FFB4B4"/></g>'
            f'<rect x="-0.26" y="-0.66" width="0.52" height="0.13" rx="0.02" fill="#E2E8F0"/>')


def dashcam_panel(ox: float, oy: float, w: float, h: float, th: dict) -> str:
    vx, vy, vw, vh = ox + 16, oy + 54, w - 32, h - 54 - 40
    R = Road(vx, vy, vw, vh)
    T, N = R.T, R.N
    dt = T / N
    frames = [f * dt for f in range(N + 1)]
    L = R.LANE

    def poly(pts):
        return _pts(pts)

    # static road
    far, near = 400.0, 0.7
    road = poly([R.proj(-L * 1.5 - 0.6, far), R.proj(L * 1.5 + 0.6, far), R.proj(L * 1.5 + 0.6, near), R.proj(-L * 1.5 - 0.6, near)])
    edges = "".join(
        f'<polygon points="{poly([R.proj(s * (L * 1.5) - 0.08, far), R.proj(s * (L * 1.5) + 0.08, far), R.proj(s * (L * 1.5) + 0.08, near), R.proj(s * (L * 1.5) - 0.08, near)])}" fill="#E5E7EB" fill-opacity="0.75"/>'
        for s in (-1, 1))
    ego = poly([R.proj(-1.0, 3), R.proj(1.0, 3), R.proj(0.9, 40), R.proj(-0.9, 40)])

    # moving lane dashes (short seamless loop: each dash moves exactly one spacing)
    spacing, dash = 12.0, 3.0
    loop = spacing / R.V
    dashes = ""
    for lx in (-L / 2, L / 2):
        for k in range(12):
            z0 = 2 + spacing * k
            vals = []
            for s in range(9):
                z = z0 - spacing * s / 8
                vals.append(poly([R.proj(lx - 0.07, max(z, 0.7)), R.proj(lx + 0.07, max(z, 0.7)),
                                  R.proj(lx + 0.07, max(z + dash, 0.7)), R.proj(lx - 0.07, max(z + dash, 0.7))]))
            dashes += f'<polygon fill="#F8FAFC" fill-opacity="0.85">{_anim("points", vals, loop)}</polygon>'

    # roadside posts and street lights
    posts = ""
    for side in (-1, 1):
        for k in range(9):
            z0 = 3 + 24 * k
            pv, lv = [], []
            for s in range(9):
                z = max(z0 - 24 * s / 8, 0.7)
                bx, by = R.proj(side * (L * 1.5 + 1.6), z)
                tx, ty = R.proj(side * (L * 1.5 + 1.6), z, 6.0)
                pw_ = max(0.6, 0.12 * R.f / z)
                pv.append(poly([(bx - pw_ / 2, by), (bx + pw_ / 2, by), (tx + pw_ / 2, ty), (tx - pw_ / 2, ty)]))
                ax, ay = R.proj(side * (L * 1.5 + 0.3), z, 6.0)
                lv.append(f"{_f(ax)},{_f(ay)}")
            posts += f'<polygon fill="#64748B" fill-opacity="0.75">{_anim("points", pv, 24 / R.V)}</polygon>'
            posts += (f'<g><circle r="2.2" fill="#FDE68A"/><circle r="7" fill="#FDE68A" fill-opacity="0.18"/>'
                      f'{_translate(lv, 24 / R.V)}</g>')

    # skyline
    sk = _Rand(3)
    xs, skyline = vx - 4, []
    while xs < vx + vw + 4:
        bw = sk.uniform(10, 26)
        bh = sk.uniform(6, 30) * (0.5 if abs(xs - R.cx) < 40 else 1)
        skyline.append(f'<rect x="{_f(xs)}" y="{_f(R.hy - bh)}" width="{_f(bw)}" height="{_f(bh + 1)}" fill="#141A2E"/>')
        if bh > 14:
            for _ in range(2):
                skyline.append(f'<rect x="{_f(xs + sk.uniform(2, bw - 4))}" y="{_f(R.hy - bh + sk.uniform(3, bh - 4))}" width="1.6" height="1.6" fill="#FCD34D" fill-opacity="0.7"/>')
        xs += bw + sk.uniform(0, 3)

    # cars, boxes, labels, predicted paths
    order = [0, 1, 2, 3]
    cars, ribbons, labels = "", "", ""
    ttc_frames, cut_frames, lead_risk = [], [], []
    for k in order:
        cid, kind, colour = R.CARS[k]
        tr, sc, brake, vis, rib, lab, box_col = [], [], [], [], [], [], []
        hh = 3.6 if kind == "truck" else 1.62
        hw = 1.42 if kind == "truck" else 1.06
        for t in frames:
            x, z, br, v = R.state(k, t)
            gx, gy = R.proj(x, z)
            s = R.f / z
            tr.append(f"{_f(gx)},{_f(gy)}")
            sc.append(f"{s:.2f}")
            brake.append(_f(br))
            vis.append(_f(v))
            dx, dz = R.vel(k, t)
            left, right = [], []
            for q in range(9):
                tau = 1.0 * q / 8            # world frame: where the car itself will be
                px, pz = x + dx * tau, z + (R.V + dz) * tau
                left.append(R.proj(px - 0.85, max(pz, 1.2)))
                right.append(R.proj(px + 0.85, max(pz, 1.2)))
            rib.append(poly(left + right[::-1]))
            lab.append(f"{_f(gx)},{_f(gy - hh * s - 7)}")
            col = "#34D399"
            if k == 1:
                closing = -dz
                ttc = (z - 4.5) / closing if closing > 0.4 else None
                ttc_frames.append(None if ttc is None or ttc > 9.9 else f"{ttc:.1f}")
                col = "#34D399" if ttc is None or ttc > 3.2 else "#FBBF24" if ttc > 2.0 else "#F43F5E"
                lead_risk.append(col)
            if k == 2:
                inward = -dx > 0.25 and abs(x) > 0.5
                cut_frames.append(inward)
                if inward:
                    col = "#FBBF24"
            box_col.append(col)
        rib_col = {0: "#94A3B8", 1: "#60A5FA", 2: "#FBBF24", 3: "#F87171"}[k]
        ribbons += (f'<polygon fill="{rib_col}" fill-opacity="0.4" stroke="{rib_col}" stroke-opacity="0.9" stroke-width="1.4" stroke-dasharray="4 3">'
                    f'{_anim("points", rib, T)}{_anim("opacity", vis, T)}</polygon>')
        brake_anim = _anim("opacity", brake, T) if k == 1 else ""
        box = (f'<path d="M{-hw} {-hh + 0.35} V{-hh} H{-hw + 0.4} M{hw - 0.4} {-hh} H{hw} V{-hh + 0.35} '
               f'M{hw} {-0.3} V0.08 H{hw - 0.4} M{-hw + 0.4} 0.08 H{-hw} V-0.3" fill="none" stroke-width="2" '
               f'vector-effect="non-scaling-stroke" stroke-linecap="round">{_anim("stroke", box_col, T, True)}</path>'
               f'<rect x="{-hw}" y="{-hh}" width="{2 * hw}" height="{hh + 0.08}" fill-opacity="0.06" stroke-opacity="0.35" stroke-width="1" vector-effect="non-scaling-stroke">'
               f'{_anim("fill", box_col, T, True)}{_anim("stroke", box_col, T, True)}</rect>')
        cars += (f'<g>{_translate(tr, T)}{_anim("opacity", vis, T)}<g>'
                 f'<animateTransform attributeName="transform" type="scale" dur="{T}s" repeatCount="indefinite" values="{_vals(sc)}"/>'
                 f'{_car_shape(kind, colour, brake_anim)}{box}</g></g>')
        name = "truck" if kind == "truck" else "car"
        tw = 62
        if kind == "truck":
            continue                         # far away: box only, its label would collide with the lead car's
        labels += (f'<g>{_translate(lab, T)}{_anim("opacity", vis, T)}'
                   f'<rect x="{-tw / 2}" y="-15" width="{tw}" height="15" rx="4" fill="#0B1220" fill-opacity="0.78"/>'
                   f'<text x="0" y="-4.2" text-anchor="middle" font-family="{th["MONO"]}" font-size="9.5" font-weight="700" fill="#F8FAFC">{name} #{cid}</text></g>')

    # HUD: TTC readout and cut-in alert
    hud_x, hud_y = vx + 10, vy + vh - 34
    ttc_texts = ""
    uniq = []
    for v in ttc_frames:
        if v not in uniq:
            uniq.append(v)
    for v in uniq:
        label = "TTC  —" if v is None else f"TTC  {v} s"
        ttc_texts += (f'<text x="{hud_x + 62}" y="{hud_y + 16.5}" font-family="{th["MONO"]}" font-size="12" font-weight="700" fill="#F8FAFC" opacity="0">{label}'
                      f'{_anim("opacity", ["1" if f == v else "0" for f in ttc_frames], T, True)}</text>')
    hud = (f'<rect x="{hud_x}" y="{hud_y}" width="150" height="24" rx="12" fill="#0B1220" fill-opacity="0.8" stroke-width="1.2">'
           f'{_anim("stroke", lead_risk, T, True)}</rect>'
           f'<circle cx="{hud_x + 13}" cy="{hud_y + 12}" r="4">{_anim("fill", lead_risk, T, True)}</circle>'
           f'<text x="{hud_x + 22}" y="{hud_y + 16.5}" font-family="{th["MONO"]}" font-size="12" font-weight="700" fill="#94A3B8">LEAD</text>'
           + ttc_texts)
    cut_op = ["1" if c else "0" for c in cut_frames]
    alert = (f'<g opacity="0">{_anim("opacity", cut_op, T, True)}'
             f'<rect x="{vx + vw - 128}" y="{vy + vh - 34}" width="118" height="24" rx="12" fill="#FBBF24"/>'
             f'<text x="{vx + vw - 69}" y="{vy + vh - 17.5}" text-anchor="middle" font-family="{th["MONO"]}" font-size="12" font-weight="800" fill="#1F1300">⚠ CUT-IN #12</text></g>')
    top = (f'<rect x="{vx + 10}" y="{vy + 10}" width="96" height="20" rx="10" fill="#0B1220" fill-opacity="0.7"/>'
           f'<circle cx="{vx + 22}" cy="{vy + 20}" r="3.6" fill="#F43F5E"><animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite"/></circle>'
           f'<text x="{vx + 31}" y="{vy + 24}" font-family="{th["MONO"]}" font-size="10.5" font-weight="700" fill="#F8FAFC">REC 30 fps</text>'
           f'<rect x="{vx + vw - 104}" y="{vy + 10}" width="94" height="20" rx="10" fill="#0B1220" fill-opacity="0.7"/>'
           f'<text x="{vx + vw - 57}" y="{vy + 24}" text-anchor="middle" font-family="{th["MONO"]}" font-size="10.5" font-weight="700" fill="#F8FAFC">EGO 72 km/h</text>')

    return f'''
<g>
<rect x="{ox + 0.5}" y="{oy + 0.5}" width="{w - 1}" height="{h - 1}" rx="20" fill="{th["card"]}" stroke="{th["border"]}"/>
<text x="{ox + 20}" y="{oy + 26}" font-family="{th["MONO"]}" font-size="11.5" font-weight="700" letter-spacing="1.4" fill="{th["accent2"]}">DASHCAM TRACKING · RISK</text>
<text x="{ox + 20}" y="{oy + 43}" font-family="{th["SANS"]}" font-size="14" font-weight="700" fill="{th["text"]}">Track every car, predict its path, warn early</text>
<text x="{ox + w - 20}" y="{oy + 26}" text-anchor="end" font-family="{th["MONO"]}" font-size="11" fill="{th["muted"]}">offline · on-device</text>
<clipPath id="fh-cam"><rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" rx="10"/></clipPath>
<g clip-path="url(#fh-cam)">
<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="url(#fh-sky)"/>
<ellipse cx="{_f(R.cx + 70)}" cy="{_f(R.hy)}" rx="160" ry="34" fill="url(#fh-sun)"/>
{"".join(skyline)}
<rect x="{vx}" y="{_f(R.hy)}" width="{vw}" height="{_f(vy + vh - R.hy)}" fill="#0A0D14"/>
<polygon points="{road}" fill="url(#fh-road)"/>
<polygon points="{ego}" fill="url(#fh-ego)"/>
{edges}
{dashes}
{posts}
{ribbons}
{cars}
{labels}
<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="url(#fh-vignette)"/>
{top}
{hud}
{alert}
</g>
<g font-family="{th["MONO"]}" font-size="11" fill="{th["muted"]}">
<rect x="{ox + 21}" y="{oy + h - 23}" width="11" height="10" rx="2" fill="none" stroke="#34D399" stroke-width="1.6"/><text x="{ox + 38}" y="{oy + h - 14}">tracked</text>
<rect x="{ox + 106}" y="{oy + h - 23}" width="22" height="10" rx="2" fill="#60A5FA" fill-opacity="0.25" stroke="#60A5FA" stroke-dasharray="3 2"/><text x="{ox + 134}" y="{oy + h - 14}">1 s path</text>
<circle cx="{ox + 212}" cy="{oy + h - 18}" r="4" fill="#F43F5E"/><text x="{ox + 221}" y="{oy + h - 14}">time-to-collision</text>
<text x="{ox + w - 20}" y="{oy + h - 14}" text-anchor="end">Foresight</text>
</g>
</g>'''


def foresight_svg(th: dict) -> str:
    W, H = 1000, 380
    gap = 20
    pw = (W - gap) / 2
    dark = th["dark"]
    grass = ("#0E3B22", "#145030") if dark else ("#2F8A4E", "#3A9C5B")
    body = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Animated forecasts: football players' next two seconds and tracked cars' predicted paths with time-to-collision">
<title>Predicting the future: football motion forecast and dashcam tracking</title>
<defs>
<linearGradient id="fh-grass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{grass[0]}"/><stop offset="1" stop-color="{grass[1]}"/></linearGradient>
<marker id="fh-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#FFFFFF"/></marker>
<linearGradient id="fh-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#060914"/><stop offset="0.3" stop-color="#1A1838"/><stop offset="0.38" stop-color="#4C2A55"/><stop offset="0.4" stop-color="#0A0D14"/></linearGradient>
<radialGradient id="fh-sun"><stop offset="0" stop-color="#F59E0B" stop-opacity="0.55"/><stop offset="1" stop-color="#F59E0B" stop-opacity="0"/></radialGradient>
<linearGradient id="fh-road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1A1E28"/><stop offset="1" stop-color="#2A2F3B"/></linearGradient>
<linearGradient id="fh-ego" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#22D3EE" stop-opacity="0.32"/><stop offset="1" stop-color="#22D3EE" stop-opacity="0"/></linearGradient>
<linearGradient id="fh-body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.28"/><stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0"/><stop offset="1" stop-color="#000000" stop-opacity="0.35"/></linearGradient>
<radialGradient id="fh-vignette" cx="0.5" cy="0.45" r="0.75"><stop offset="0.65" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.45"/></radialGradient>
</defs>
{football_panel(0, 0, pw, H, th)}
{dashcam_panel(pw + gap, 0, pw, H, th)}
</svg>
'''
    return body
