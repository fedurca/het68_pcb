#!/usr/bin/env python3
"""Finish the het68 Core on eight copper layers.

    python3 kicad/tools/core_8l.py stackup [board]
    python3 kicad/tools/core_8l.py lvds    [board]
    python3 kicad/tools/core_8l.py opens   [board]
    python3 kicad/tools/core_8l.py stitch  [board]
    python3 kicad/tools/core_8l.py report  [board]

Each step edits the board in place and saves it. Copper is removed only for
the LVDS pairs being re-routed, vias whose drill collides with a same-net
hole, and copper KiCad DRC reports as dangling.

Lengths are millimetres. Clearances follow the board setup: 0.10 copper,
0.20 copper to a hole of another net, 0.25 hole to hole, 0.30 to the edge.
"""
from __future__ import annotations

import heapq
import json
import math
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pcbnew

BOARD = Path(__file__).resolve().parents[1] / "het68-core" / "het68-core.kicad_pcb"

F, B = pcbnew.F_Cu, pcbnew.B_Cu
L3, L6 = pcbnew.In2_Cu, pcbnew.In5_Cu
SIGNAL = (F, L3, L6, B)
ALL = frozenset(SIGNAL)

CLEAR = 0.10
HOLE_CLEAR = 0.20
HOLE_TO_HOLE = 0.25
EDGE_CLEAR = 0.30
SLACK = 0.005
TRACK = 0.15
HALF = TRACK / 2
VIA_D, VIA_DRILL = 0.30, 0.15
VIA_R, HOLE_R = VIA_D / 2, VIA_DRILL / 2
PAIR_OFF = 0.15  # centre line to P or N: (track + gap) / 2
PAIR_HALF = 0.30  # corridor half-width; leaves room for the mitred offset at a 90 degree corner
LEAD = 0.6
GRID = 0.1
CELL = 1.0
REACH = 0.9  # largest query radius the spatial bins must cover

# Pairs whose IC-to-CMC loop exceeded 50 mm2, and the four that were open.
LVDS_PAIRS = ("SD5", "SD6", "SD2", "SD3", "SD4", "WS1", "SCK6", "SCK2", "WS2", "SCK3", "WS3")
ALL_PAIRS = tuple(f"{k}{i}" for k in ("SCK", "WS", "SD") for i in range(1, 7))
ANALOG = ("ADC_I", "ADC_ROGO", "ADC_HARVEST")


def mm(v):
    return pcbnew.ToMM(v)


def iu(v):
    return pcbnew.FromMM(v)


def vec(x, y):
    return pcbnew.VECTOR2I(iu(x), iu(y))


def dist_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)


def seg_seg(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(
        dist_seg(a[0], a[1], c[0], c[1], d[0], d[1]),
        dist_seg(b[0], b[1], c[0], c[1], d[0], d[1]),
        dist_seg(c[0], c[1], a[0], a[1], b[0], b[1]),
        dist_seg(d[0], d[1], a[0], a[1], b[0], b[1]),
    )


def shape_dist(s, px, py):
    """Distance from a point to the copper of shape s, 0 inside."""
    k = s[0]
    if k == "disc":
        return math.hypot(px - s[1], py - s[2]) - s[3]
    if k == "stad":
        return dist_seg(px, py, s[1], s[2], s[3], s[4]) - s[5]
    dx, dy = px - s[1], py - s[2]
    lx, ly = dx * s[6] + dy * s[7], -dx * s[7] + dy * s[6]
    return math.hypot(max(abs(lx) - s[3], 0.0), max(abs(ly) - s[4], 0.0))


def shape_dist_np(s, X, Y):
    k = s[0]
    if k == "disc":
        return np.hypot(X - s[1], Y - s[2]) - s[3]
    if k == "stad":
        x1, y1, x2, y2, r = s[1:6]
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 < 1e-12:
            return np.hypot(X - x1, Y - y1) - r
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / l2, 0.0, 1.0)
        return np.hypot(X - x1 - t * dx, Y - y1 - t * dy) - r
    DX, DY = X - s[1], Y - s[2]
    lx = DX * s[6] + DY * s[7]
    ly = -DX * s[7] + DY * s[6]
    return np.hypot(np.maximum(np.abs(lx) - s[3], 0.0), np.maximum(np.abs(ly) - s[4], 0.0))


def shape_bbox(s):
    k = s[0]
    if k == "disc":
        return s[1] - s[3], s[2] - s[3], s[1] + s[3], s[2] + s[3]
    if k == "stad":
        r = s[5]
        return min(s[1], s[3]) - r, min(s[2], s[4]) - r, max(s[1], s[3]) + r, max(s[2], s[4]) + r
    ex = abs(s[3] * s[6]) + abs(s[4] * s[7])
    ey = abs(s[3] * s[7]) + abs(s[4] * s[6])
    return s[1] - ex, s[2] - ey, s[1] + ex, s[2] + ey


def pad_size(pad, layer):
    try:
        return pad.GetSize(layer)
    except TypeError:
        return pad.GetSize()


def pad_shape(pad, layer=F):
    p = pad.GetPosition()
    x, y = mm(p.x), mm(p.y)
    size = pad_size(pad, layer)
    hx, hy = mm(size.x) / 2, mm(size.y) / 2
    try:
        kind = pad.GetShape(layer)
    except TypeError:
        kind = pad.GetShape()
    ang = pad.GetOrientation().AsDegrees()
    a = math.radians(ang)
    if kind == pcbnew.PAD_SHAPE_CIRCLE:
        return ("disc", x, y, max(hx, hy))
    if kind == pcbnew.PAD_SHAPE_OVAL and abs(hx - hy) > 1e-6:
        r, half = min(hx, hy), abs(hx - hy)
        ux, uy = (math.cos(a), -math.sin(a)) if hx > hy else (math.sin(a), math.cos(a))
        return ("stad", x - ux * half, y - uy * half, x + ux * half, y + uy * half, r)
    return ("rect", x, y, hx, hy, ang, math.cos(a), math.sin(a))


def poly_points(zone):
    ol = zone.Outline()
    return [(mm(ol.CVertex(i).x), mm(ol.CVertex(i).y)) for i in range(ol.TotalVertices())]


def in_poly(x, y, pts):
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def poly_dist(x, y, pts):
    return min(dist_seg(x, y, *pts[i - 1], *pts[i]) for i in range(len(pts)))


class Model:
    """Copper and holes of the board for clearance queries."""

    def __init__(self, board):
        self.board = board
        bb = board.GetBoardEdgesBoundingBox()
        # The edge line is 0.1 mm wide; clearance is measured from its inner side.
        self.ex0, self.ey0 = mm(bb.GetX()) + 0.1, mm(bb.GetY()) + 0.1
        self.ex1, self.ey1 = mm(bb.GetRight()) - 0.1, mm(bb.GetBottom()) - 0.1
        self.nx = int(math.ceil(self.ex1 / GRID)) + 3
        self.ny = int(math.ceil(self.ey1 / GRID)) + 3
        self.items = []
        self.holes = []
        self.bins = defaultdict(list)
        self.hbins = defaultdict(list)
        self.net_items = defaultdict(list)
        self.net_holes = defaultdict(list)
        self.keep_track = []
        self.keep_via = []
        self.grids = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                self.add_pad(pad)
            for z in fp.Zones():
                self.add_keepout(z)
        for z in board.Zones():
            self.add_keepout(z)
        for t in board.GetTracks():
            self.add_track(t)

    # --- loading -------------------------------------------------------
    def add_keepout(self, z):
        if not z.GetIsRuleArea():
            return
        layers = frozenset(l for l in z.GetLayerSet().Seq() if l in SIGNAL)
        pts = poly_points(z)
        if len(pts) < 3:
            return
        if z.GetDoNotAllowTracks():
            self.keep_track.append((layers, pts))
        if z.GetDoNotAllowVias():
            self.keep_via.append((layers, pts))

    def add_pad(self, pad):
        attr = pad.GetAttribute()
        net = pad.GetNetCode() if pad.GetNetname() else None
        p = pad.GetPosition()
        x, y = mm(p.x), mm(p.y)
        if attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            d = pad.GetDrillSize()
            self.add_hole(x, y, max(mm(d.x), mm(d.y)) / 2, net if attr == pcbnew.PAD_ATTRIB_PTH else None)
            if attr == pcbnew.PAD_ATTRIB_PTH:
                self.add_copper(pad_shape(pad, F), ALL, net)
            return
        for layer in (F, B):
            if pad.IsOnLayer(layer):
                self.add_copper(pad_shape(pad, layer), frozenset((layer,)), net)

    def add_track(self, t):
        net = t.GetNetCode()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            x, y = mm(p.x), mm(p.y)
            self.add_copper(("disc", x, y, mm(t.GetWidth(F)) / 2), ALL, net)
            self.add_hole(x, y, mm(t.GetDrillValue()) / 2, net)
            return
        layer = t.GetLayer()
        if layer not in SIGNAL:
            return
        a, c = t.GetStart(), t.GetEnd()
        r = mm(t.GetWidth()) / 2
        if t.GetClass() == "PCB_ARC":
            m = t.GetMid()
            self.add_copper(("stad", mm(a.x), mm(a.y), mm(m.x), mm(m.y), r), frozenset((layer,)), net)
            self.add_copper(("stad", mm(m.x), mm(m.y), mm(c.x), mm(c.y), r), frozenset((layer,)), net)
            return
        self.add_copper(("stad", mm(a.x), mm(a.y), mm(c.x), mm(c.y), r), frozenset((layer,)), net)

    def _cells(self, box):
        x0, y0, x1, y1 = box
        for ix in range(int(math.floor((x0 - REACH) / CELL)), int(math.floor((x1 + REACH) / CELL)) + 1):
            for iy in range(int(math.floor((y0 - REACH) / CELL)), int(math.floor((y1 + REACH) / CELL)) + 1):
                yield ix, iy

    def add_copper(self, shape, layers, net):
        i = len(self.items)
        self.items.append((shape, layers, net))
        self.net_items[net].append(i)
        for key in self._cells(shape_bbox(shape)):
            self.bins[key].append(i)
        for (layer, h, extra), g in self.grids.items():
            if layer in layers:
                self._raster(g, shape, h + CLEAR + extra + SLACK, 1)

    def add_hole(self, x, y, r, net):
        j = len(self.holes)
        self.holes.append((x, y, r, net))
        self.net_holes[net].append(j)
        for key in self._cells((x - r, y - r, x + r, y + r)):
            self.hbins[key].append(j)
        for (layer, h, extra), g in self.grids.items():
            self._raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, 1)

    # --- exact queries -------------------------------------------------
    def inside(self, x, y, r):
        m = EDGE_CLEAR + r + SLACK
        return self.ex0 + m <= x <= self.ex1 - m and self.ey0 + m <= y <= self.ey1 - m

    def kept_out(self, areas, x, y, layer, r):
        for layers, pts in areas:
            if layer is not None and layer not in layers:
                continue
            if in_poly(x, y, pts) or poly_dist(x, y, pts) < r:
                return True
        return False

    def copper_ok(self, x, y, layer, nets, h=HALF, extra=0.0):
        if not self.inside(x, y, h):
            return False
        key = (int(math.floor(x / CELL)), int(math.floor(y / CELL)))
        need = h + CLEAR + extra + SLACK
        for i in self.bins.get(key, ()):
            s, layers, net = self.items[i]
            if layer in layers and (net is None or net not in nets) and shape_dist(s, x, y) < need:
                return False
        need = h + HOLE_CLEAR + extra + SLACK
        for j in self.hbins.get(key, ()):
            hx, hy, r, net = self.holes[j]
            if (net is None or net not in nets) and math.hypot(x - hx, y - hy) - r < need:
                return False
        return not self.kept_out(self.keep_track, x, y, layer, h)

    def seg_ok(self, x1, y1, x2, y2, layer, nets, h=HALF, extra=0.0):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / 0.02)))
        for i in range(n + 1):
            t = i / n
            if not self.copper_ok(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, layer, nets, h, extra):
                return False
        return True

    def poly_ok(self, pts, layer, nets, h=HALF, extra=0.0):
        return all(self.seg_ok(a[0], a[1], b[0], b[1], layer, nets, h, extra) for a, b in zip(pts, pts[1:]))

    def via_ok(self, x, y, net):
        if not self.inside(x, y, VIA_R) or self.kept_out(self.keep_via, x, y, None, VIA_R):
            return False
        key = (int(math.floor(x / CELL)), int(math.floor(y / CELL)))
        need = max(VIA_R + CLEAR, HOLE_R + HOLE_CLEAR) + SLACK
        for i in self.bins.get(key, ()):
            s, layers, inet = self.items[i]
            if (inet is None or inet != net) and shape_dist(s, x, y) < need:
                return False
        for j in self.hbins.get(key, ()):
            hx, hy, r, hnet = self.holes[j]
            gap = math.hypot(x - hx, y - hy) - r
            if hnet is not None and hnet == net:
                lim = HOLE_R + HOLE_TO_HOLE
            else:
                lim = max(HOLE_R + HOLE_TO_HOLE, VIA_R + HOLE_CLEAR)
            if gap < lim + SLACK:
                return False
        return True

    # --- raster grids for A* ------------------------------------------
    def _raster(self, g, s, R, val):
        x0, y0, x1, y1 = shape_bbox(s)
        i0 = max(0, int(math.floor((x0 - R) / GRID)))
        i1 = min(self.nx - 1, int(math.ceil((x1 + R) / GRID)))
        j0 = max(0, int(math.floor((y0 - R) / GRID)))
        j1 = min(self.ny - 1, int(math.ceil((y1 + R) / GRID)))
        if i1 < i0 or j1 < j0:
            return
        X = (np.arange(i0, i1 + 1) * GRID)[None, :]
        Y = (np.arange(j0, j1 + 1) * GRID)[:, None]
        hit = shape_dist_np(s, X, Y) < R
        if val > 0:
            g[j0 : j1 + 1, i0 : i1 + 1] += hit.astype(np.int16)
        else:
            g[j0 : j1 + 1, i0 : i1 + 1] -= hit.astype(np.int16)

    def grid(self, layer, h, extra=0.0):
        key = (layer, round(h, 4), round(extra, 4))
        g = self.grids.get(key)
        if g is not None:
            return g
        g = np.zeros((self.ny, self.nx), np.int16)
        X = np.arange(self.nx) * GRID
        Y = np.arange(self.ny) * GRID
        m = EDGE_CLEAR + h + SLACK
        g[:, (X < self.ex0 + m) | (X > self.ex1 - m)] += 1
        g[(Y < self.ey0 + m) | (Y > self.ey1 - m), :] += 1
        for s, layers, net in self.items:
            if layer in layers:
                self._raster(g, s, h + CLEAR + extra + SLACK, 1)
        for x, y, r, net in self.holes:
            self._raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, 1)
        for layers, pts in self.keep_track:
            if layer in layers:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                i0, i1 = int((min(xs) - h) / GRID), int((max(xs) + h) / GRID) + 1
                j0, j1 = int((min(ys) - h) / GRID), int((max(ys) + h) / GRID) + 1
                for j in range(max(0, j0), min(self.ny, j1 + 1)):
                    for i in range(max(0, i0), min(self.nx, i1 + 1)):
                        if in_poly(i * GRID, j * GRID, pts) or poly_dist(i * GRID, j * GRID, pts) < h + SLACK:
                            g[j, i] += 1
        self.grids[key] = g
        return g

    def free(self, layer, nets, h, extra=0.0):
        g = self.grid(layer, h, extra).copy()
        for net in nets:
            for i in self.net_items.get(net, ()):
                s, layers, _ = self.items[i]
                if layer in layers:
                    self._raster(g, s, h + CLEAR + extra + SLACK, -1)
            for j in self.net_holes.get(net, ()):
                x, y, r, _ = self.holes[j]
                self._raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, -1)
        return g == 0


# --- board edits ---------------------------------------------------------
def draw_track(board, model, x1, y1, x2, y2, layer, net):
    if math.hypot(x2 - x1, y2 - y1) < 1e-4:
        return None
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(x1, y1))
    t.SetEnd(vec(x2, y2))
    t.SetWidth(iu(TRACK))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)
    model.add_track(t)
    return t


def draw_poly(board, model, pts, layer, net):
    return [draw_track(board, model, a[0], a[1], b[0], b[1], layer, net) for a, b in zip(pts, pts[1:])]


def draw_via(board, model, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(iu(VIA_D))
    v.SetDrill(iu(VIA_DRILL))
    v.SetNet(net)
    board.Add(v)
    model.add_track(v)
    return v


def fill_zones(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def save(board, path):
    pcbnew.SaveBoard(str(path), board)


def drc(path, severity="error"):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "drc.json"
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json", "--units", "mm", f"--severity-{severity}",
             "-o", str(out), str(path)],
            check=True, capture_output=True,
        )
        return json.loads(out.read_text())


def drc_summary(report):
    counts = defaultdict(int)
    for v in report.get("violations") or []:
        counts[v["type"]] += 1
    return dict(counts), len(report.get("unconnected_items") or [])


def net_of(desc):
    return desc[desc.find("[") + 1 : desc.find("]")] if "[" in desc and "]" in desc else None


# --- A* on the raster ----------------------------------------------------
DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
SQ2 = math.sqrt(2.0)


def astar(free, starts, goals, turn=0.4, weight=1.2, limit=4_000_000):
    """8-connected A* on a boolean grid. Turns sharper than 90 degrees are not taken."""
    ny, nx = free.shape
    fb = free.astype(np.uint8).tobytes()
    goal_set = {g for g in goals if 0 <= g[0] < nx and 0 <= g[1] < ny and fb[g[1] * nx + g[0]]}
    if not goal_set:
        return None
    gl = list(goal_set)

    def heur(i, j):
        best = 1e18
        for gi, gj in gl:
            dx, dy = abs(i - gi), abs(j - gj)
            v = max(dx, dy) + (SQ2 - 1.0) * min(dx, dy)
            if v < best:
                best = v
        return best

    openh = []
    gsc, parent, dirn = {}, {}, {}
    for s in starts:
        i, j = s[0], s[1]
        d0 = s[2] if len(s) > 2 else None
        if 0 <= i < nx and 0 <= j < ny and fb[j * nx + i]:
            gsc[(i, j)] = 0.0
            parent[(i, j)] = None
            dirn[(i, j)] = d0
            heapq.heappush(openh, (weight * heur(i, j), 0.0, i, j))
    closed = set()
    pops = 0
    while openh and pops < limit:
        _, gc, i, j = heapq.heappop(openh)
        k = (i, j)
        if k in closed:
            continue
        closed.add(k)
        pops += 1
        if k in goal_set:
            path = [k]
            while parent[path[-1]] is not None:
                path.append(parent[path[-1]])
            return path[::-1]
        d0 = dirn[k]
        for di, (dx, dy) in enumerate(DIRS):
            if d0 is not None and min((di - d0) % 8, (d0 - di) % 8) > 2:
                continue
            ni, nj = i + dx, j + dy
            if not (0 <= ni < nx and 0 <= nj < ny) or not fb[nj * nx + ni]:
                continue
            if dx and dy and not (fb[j * nx + ni] and fb[nj * nx + i]):
                continue
            nk = (ni, nj)
            if nk in closed:
                continue
            ng = gc + (SQ2 if dx and dy else 1.0) + (turn if d0 is not None and d0 != di else 0.0)
            if ng < gsc.get(nk, 1e18):
                gsc[nk] = ng
                parent[nk] = k
                dirn[nk] = di
                heapq.heappush(openh, (ng + weight * heur(ni, nj), ng, ni, nj))
    return None


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < 1e-6:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            cr = (b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])
            dot = (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1])
            if abs(cr) < 1e-9 and dot > 0:
                out[-1] = p
                continue
        out.append(p)
    return out


def line_free(fb, nx, ny, a, b):
    n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / (GRID / 2))))
    for k in range(n + 1):
        t = k / n
        i = int(round((a[0] + (b[0] - a[0]) * t) / GRID))
        j = int(round((a[1] + (b[1] - a[1]) * t) / GRID))
        if not (0 <= i < nx and 0 <= j < ny) or not fb[j * nx + i]:
            return False
    return True


def pull(free, pts, max_turn_deg=90.0):
    """Drop vertices while the straight shortcut stays on free cells."""
    ny, nx = free.shape
    fb = free.astype(np.uint8).tobytes()
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1:
            if line_free(fb, nx, ny, pts[i], pts[j]):
                if len(out) >= 2:
                    a, b, c = out[-2], out[-1], pts[j]
                    u = (b[0] - a[0], b[1] - a[1])
                    v = (c[0] - b[0], c[1] - b[1])
                    nu, nv = math.hypot(*u), math.hypot(*v)
                    if nu > 1e-9 and nv > 1e-9:
                        cosang = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
                        if cosang < math.cos(math.radians(max_turn_deg)) - 1e-9:
                            j -= 1
                            continue
                break
            j -= 1
        out.append(pts[j])
        i = j
    return simplify(out)


def cell_of(p):
    return int(round(p[0] / GRID)), int(round(p[1] / GRID))


def xy_of(c):
    return c[0] * GRID, c[1] * GRID


# --- pair geometry -------------------------------------------------------
def unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-12 else (0.0, 0.0)


def left(u):
    # Left of travel with the y axis pointing down.
    return (u[1], -u[0])


def intersect(p, u, q, v):
    cr = u[0] * v[1] - u[1] * v[0]
    if abs(cr) < 1e-9:
        return None
    t = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / cr
    return (p[0] + u[0] * t, p[1] + u[1] * t)


def offset(pts, off):
    pts = simplify(pts)
    segs = []
    for a, b in zip(pts, pts[1:]):
        u = unit(b[0] - a[0], b[1] - a[1])
        n = left(u)
        segs.append(((a[0] + n[0] * off, a[1] + n[1] * off), (b[0] + n[0] * off, b[1] + n[1] * off), u))
    out = [segs[0][0]]
    for s1, s2 in zip(segs, segs[1:]):
        p = intersect(s1[0], s1[2], s2[0], s2[2])
        out.append(p if p is not None else s1[1])
    out.append(segs[-1][1])
    return out


def poly_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def poly_gap(p1, p2):
    best = 1e18
    for a, b in zip(p1, p1[1:]):
        for c, d in zip(p2, p2[1:]):
            best = min(best, seg_seg(a, b, c, d))
    return best


class End:
    """One end of a pair: via positions, F.Cu stubs to the pads, lead axis."""

    def __init__(self, vp, vn, stub_p, stub_n, axis):
        self.vp, self.vn = vp, vn
        self.stub_p, self.stub_n = stub_p, stub_n
        self.mid = ((vp[0] + vn[0]) / 2, (vp[1] + vn[1]) / 2)
        self.axis = axis  # unit vector, leads run along +axis or -axis

    def side(self, u):
        n = left(u)
        return 1 if (self.vp[0] - self.mid[0]) * n[0] + (self.vp[1] - self.mid[1]) * n[1] > 0 else -1


def pad_info(pad):
    p = pad.GetPosition()
    s = pad_size(pad, F)
    a = math.radians(pad.GetOrientation().AsDegrees())
    hx, hy = mm(s.x) / 2, mm(s.y) / 2
    long_axis = (math.cos(a), -math.sin(a)) if hx >= hy else (math.sin(a), math.cos(a))
    return mm(p.x), mm(p.y), long_axis, max(hx, hy)


def outward(pad):
    x, y, ax, hl = pad_info(pad)
    fp = pad.GetParentFootprint()
    c = fp.GetPosition()
    cx, cy = mm(c.x), mm(c.y)
    if (x - cx) * ax[0] + (y - cy) * ax[1] < 0:
        ax = (-ax[0], -ax[1])
    return ax, hl


def end_candidates(model, p_xy, n_xy, o, hl, netp, netn, pre_p=(), pre_n=(), inward=False, limit=2):
    """Via pairs in line with two pads, outward along o (and under the body if inward)."""
    found = []
    sides = (1, -1) if inward else (1,)
    for sgn in sides:
        for k in (0.25, 0.45, 0.7, 1.0, 1.4, 1.9, 2.5, 3.2, 4.0):
            d = hl + k if sgn > 0 else -(hl + 0.35 + k)
            vp = (p_xy[0] + o[0] * d, p_xy[1] + o[1] * d)
            vn = (n_xy[0] + o[0] * d, n_xy[1] + o[1] * d)
            if math.hypot(vp[0] - vn[0], vp[1] - vn[1]) < 0.45:
                continue
            if not (model.via_ok(*vp, netp) and model.via_ok(*vn, netn)):
                continue
            sp = list(pre_p) + [p_xy, vp]
            sn = list(pre_n) + [n_xy, vn]
            if not (model.poly_ok(sp, F, (netp,)) and model.poly_ok(sn, F, (netn,))):
                continue
            if poly_gap(sp, sn) < TRACK + CLEAR + SLACK:
                continue
            found.append(End(vp, vn, sp, sn, o))
            if sum(1 for e in found if (e.mid[0] - p_xy[0]) * o[0] + (e.mid[1] - p_xy[1]) * o[1] > 0) >= limit and sgn > 0:
                break
            if sgn < 0 and len(found) >= 2 * limit:
                break
    return found


# --- stackup -------------------------------------------------------------
def cmd_stackup(path):
    board = pcbnew.LoadBoard(str(path))
    if board.GetCopperLayerCount() == 8:
        print("already 8 copper layers")
        return
    board.SetCopperLayerCount(8)
    board.SetLayerName(pcbnew.In5_Cu, "SIG_L6")
    board.SetLayerName(pcbnew.In6_Cu, "GND_L7")
    board.SetLayerType(pcbnew.In5_Cu, pcbnew.LT_SIGNAL)
    board.SetLayerType(pcbnew.In6_Cu, pcbnew.LT_SIGNAL)
    src = next(z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In4_Cu)
    z = src.Duplicate(False)
    z = z.Cast() if hasattr(z, "Cast") else z
    z.SetLayer(pcbnew.In6_Cu)
    board.Add(z)
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        # Fill slivers under 0.2 mm etch away unevenly; JLC's minimum feature is 0.09 mm.
        zone.SetMinThickness(iu(0.2))
    fill_zones(board)
    save(board, path)
    names = [board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()]
    print("copper stack:", " / ".join(names))


# --- LVDS pairs ----------------------------------------------------------
def pads_by_net(board):
    out = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname():
                out[pad.GetNetname()].append(pad)
    return out


def rip_up(board, names):
    kill = [t for t in board.GetTracks() if t.GetNetname() in names]
    for t in kill:
        board.Remove(t)
    return len(kill)


def courtyard_box(fp):
    try:
        fp.BuildCourtyardCaches()
    except Exception:
        pass
    try:
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() > 0:
            bb = cy.BBox()
            return mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())
    except Exception:
        pass
    bb = fp.GetBoundingBox(False)
    return mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())


def boxes_overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def place_terminator(board, model, rfp, pin_p, pin_n, netp, netn):
    """Move the 100 ohm resistor next to the receiver pins; returns the new End or None."""
    o, hl = outward(pin_p)
    row = (-o[1], o[0])
    px, py = mm(pin_p.GetPosition().x), mm(pin_p.GetPosition().y)
    nx_, ny_ = mm(pin_n.GetPosition().x), mm(pin_n.GetPosition().y)
    mid = ((px + nx_) / 2, (py + ny_) / 2)
    others = [(f, courtyard_box(f)) for f in board.GetFootprints() if f.GetReference() != rfp.GetReference()]
    old_pos, old_rot = rfp.GetPosition(), rfp.GetOrientation().AsDegrees()
    rpads = {p.GetNetCode(): p for p in rfp.Pads()}
    for k in (hl + 0.95, hl + 1.2, hl + 1.5, hl + 1.9, hl + 2.4):
        for shift in (0.0, 0.25, -0.25, 0.5, -0.5, 0.8, -0.8):
            c = (mid[0] + o[0] * k + row[0] * shift, mid[1] + o[1] * k + row[1] * shift)
            for rot in (90.0, 270.0, 0.0, 180.0):
                rfp.SetPosition(vec(*c))
                rfp.SetOrientationDegrees(rot)
                rp, rn = rpads[netp], rpads[netn]
                rpx, rpy = mm(rp.GetPosition().x), mm(rp.GetPosition().y)
                rnx, rny = mm(rn.GetPosition().x), mm(rn.GetPosition().y)
                # The resistor pads must sit in the same order as the pins, across the row.
                if ((rpx - rnx) * row[0] + (rpy - rny) * row[1]) * ((px - nx_) * row[0] + (py - ny_) * row[1]) <= 0:
                    continue
                if abs((rpx - rnx) * o[0] + (rpy - rny) * o[1]) > 0.05:
                    continue
                box = courtyard_box(rfp)
                if any(boxes_overlap(box, ob) for _, ob in others):
                    continue
                ok = True
                for pad, net in ((rp, netp), (rn, netn)):
                    s = pad_shape(pad, F)
                    x0, y0, x1, y1 = shape_bbox(s)
                    for gx in np.linspace(x0, x1, 5):
                        for gy in np.linspace(y0, y1, 5):
                            if shape_dist(s, gx, gy) <= 1e-6 and not model.copper_ok(gx, gy, F, (net,), 0.0):
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                if not ok:
                    continue
                hl_r = pad_info(rp)[3] if abs(pad_info(rp)[2][0] * o[0] + pad_info(rp)[2][1] * o[1]) > 0.5 else min(
                    mm(pad_size(rp, F).x), mm(pad_size(rp, F).y)) / 2
                ends = end_candidates(model, (rpx, rpy), (rnx, rny), o, hl_r, netp, netn,
                                      pre_p=[(px, py)], pre_n=[(nx_, ny_)], limit=2)
                if ends:
                    return ends
    rfp.SetPosition(old_pos)
    rfp.SetOrientationDegrees(old_rot)
    return None


def route_pair(model, board, netp, netn, starts, ends, log):
    """Centre line on SIG_L6 between two via pairs; P and N are its offsets."""
    codes = (netp.GetNetCode(), netn.GetNetCode())
    free = model.free(L6, codes, PAIR_HALF)
    tried = 0
    for s in starts:
        for lead_sign in (1, -1):
            u0 = (s.axis[0] * lead_sign, s.axis[1] * lead_sign)
            side = s.side(u0)
            for e in ends:
                # Arrive along the end axis with P on the same side as at the start.
                u1 = None
                for sg in (1, -1):
                    cand = (e.axis[0] * sg, e.axis[1] * sg)
                    if e.side(cand) == side:
                        u1 = cand
                if u1 is None:
                    continue
                a0 = s.mid
                a1 = (a0[0] + u0[0] * LEAD, a0[1] + u0[1] * LEAD)
                b1 = e.mid
                b0 = (b1[0] - u1[0] * LEAD, b1[1] - u1[1] * LEAD)
                c0, c1 = cell_of(a1), cell_of(b0)
                tried += 1
                path = astar(free, [(c0[0], c0[1])], [c1], turn=0.5, weight=1.3)
                if path is None:
                    continue
                mid_pts = pull(free, [xy_of(c) for c in path])
                centre = simplify([a0, a1] + mid_pts + [b0, b1])
                pl = offset(centre, side * PAIR_OFF)
                nl = offset(centre, -side * PAIR_OFF)
                p_full = [s.vp] + pl + [e.vp]
                n_full = [s.vn] + nl + [e.vn]
                if not (model.poly_ok(p_full, L6, (codes[0],)) and model.poly_ok(n_full, L6, (codes[1],))):
                    log(f"    exact check failed, try next ({tried})")
                    continue
                if poly_gap(p_full[1:-1], n_full[1:-1]) < TRACK + CLEAR + SLACK:
                    log("    P/N too close")
                    continue
                if min(dist_seg(*e.vn, *a, *b) for a, b in zip(p_full, p_full[1:])) < HALF + VIA_R + HOLE_CLEAR - 0.05:
                    continue
                return s, e, p_full, n_full
    return None


def ground_near(model, board, gnd, x, y, count=1):
    placed = 0
    for r in (0.7, 0.9, 1.2, 1.5, 1.9):
        for k in range(16):
            a = k * math.pi / 8
            gx, gy = x + r * math.cos(a), y + r * math.sin(a)
            if model.via_ok(gx, gy, gnd.GetNetCode()):
                draw_via(board, model, gx, gy, gnd)
                placed += 1
                if placed >= count:
                    return placed
    return placed


def cmd_lvds(path, pairs=LVDS_PAIRS):
    board = pcbnew.LoadBoard(str(path))
    if board.GetCopperLayerCount() != 8:
        sys.exit("run stackup first")
    names = {f"{p}_{s}" for p in pairs for s in ("P", "N")}
    print(f"rip up {rip_up(board, names)} items of {len(pairs)} pairs", flush=True)
    model = Model(board)
    pads = pads_by_net(board)
    gnd = board.FindNet("GND")
    done = []
    for pair in pairs:
        netp, netn = board.FindNet(f"{pair}_P"), board.FindNet(f"{pair}_N")
        pp, pn = pads[f"{pair}_P"], pads[f"{pair}_N"]
        cmc_p = next(p for p in pp if p.GetParentFootprint().GetReference().startswith("FL"))
        cmc_n = next(p for p in pn if p.GetParentFootprint().GetReference().startswith("FL"))
        ic_p = next(p for p in pp if p.GetParentFootprint().GetReference().startswith("U"))
        ic_n = next(p for p in pn if p.GetParentFootprint().GetReference().startswith("U"))
        rterm = [p for p in pp if p.GetParentFootprint().GetReference().startswith("R_")]
        cp, cn = netp.GetNetCode(), netn.GetNetCode()
        o, hl = outward(cmc_p)
        starts = end_candidates(model, pad_info(cmc_p)[:2], pad_info(cmc_n)[:2], o, hl, cp, cn, limit=2)
        if rterm:
            rfp = rterm[0].GetParentFootprint()
            ends = place_terminator(board, model, rfp, ic_p, ic_n, cp, cn)
            if ends:
                print(f"  {pair}: {rfp.GetReference()} moved next to {ic_p.GetParentFootprint().GetReference()}", flush=True)
                model = Model(board)
                ends = place_terminator(board, model, rfp, ic_p, ic_n, cp, cn) or []
            else:
                ends = []
                print(f"  {pair}: no room for {rfp.GetReference()} at the receiver", flush=True)
        else:
            o2, hl2 = outward(ic_p)
            ends = end_candidates(model, pad_info(ic_p)[:2], pad_info(ic_n)[:2], o2, hl2, cp, cn, inward=True, limit=2)
        print(f"  {pair}: {len(starts)} start and {len(ends)} end via pairs", flush=True)
        res = route_pair(model, board, netp, netn, starts, ends, lambda m: print(m, flush=True))
        if res is None:
            print(f"  {pair}: NOT ROUTED", flush=True)
            continue
        s, e, p_full, n_full = res
        for end in (s, e):
            draw_poly(board, model, end.stub_p, F, netp)
            draw_poly(board, model, end.stub_n, F, netn)
            draw_via(board, model, *end.vp, netp)
            draw_via(board, model, *end.vn, netn)
        draw_poly(board, model, p_full, L6, netp)
        draw_poly(board, model, n_full, L6, netn)
        g = sum(ground_near(model, board, gnd, *end.mid) for end in (s, e))
        lp, ln = poly_len(s.stub_p) + poly_len(p_full) + poly_len(e.stub_p), poly_len(s.stub_n) + poly_len(n_full) + poly_len(e.stub_n)
        print(f"  {pair}: routed P {lp:.1f} N {ln:.1f} mm, {g} ground vias", flush=True)
        done.append(pair)
        save(board, path)
    fill_zones(board)
    save(board, path)
    print(f"routed {len(done)}/{len(pairs)}: {' '.join(done)}", flush=True)


# --- islands and remaining opens -----------------------------------------
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def net_islands(board, name):
    """Copper islands of one net, joined the way KiCad anchors items."""
    items = []
    for t in board.GetTracks():
        if t.GetNetname() != name:
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            items.append(("via", (mm(p.x), mm(p.y)), ALL, ("disc", mm(p.x), mm(p.y), mm(t.GetWidth(F)) / 2), t))
        else:
            a, c = t.GetStart(), t.GetEnd()
            s = ("stad", mm(a.x), mm(a.y), mm(c.x), mm(c.y), mm(t.GetWidth()) / 2)
            items.append(("seg", ((mm(a.x), mm(a.y)), (mm(c.x), mm(c.y))), frozenset((t.GetLayer(),)), s, t))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != name:
                continue
            p = pad.GetPosition()
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                layers = ALL
            else:
                layers = frozenset(l for l in (F, B) if pad.IsOnLayer(l))
            items.append(("pad", (mm(p.x), mm(p.y)), layers, pad_shape(pad, F if F in layers else B), pad))
    uf = UF(len(items))

    def anchors(it):
        if it[0] == "seg":
            return list(it[1])
        return [it[1]]

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            if not (a[2] & b[2]):
                continue
            hit = any(shape_dist(b[3], x, y) <= 0.002 for x, y in anchors(a)) or any(
                shape_dist(a[3], x, y) <= 0.002 for x, y in anchors(b))
            if hit:
                uf.union(i, j)
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[uf.find(i)].append(it)
    return list(groups.values())


def terminals(model, island, code):
    """Points where SIG_L6/SIG_L3 copper can join the island: its vias and THT pads,
    else new via sites one straight outer-layer stub away."""
    out = []
    for kind, pos, layers, s, obj in island:
        if kind == "via" or (kind == "pad" and layers == ALL):
            out.append((pos, None))
    if out:
        return out
    seen = set()
    for kind, pos, layers, s, obj in island:
        layer = next(iter(layers))
        pts = list(pos) if kind == "seg" else [pos]
        for px, py in pts:
            for r in (0.45, 0.6, 0.8, 1.0, 1.3, 1.7, 2.2, 2.8, 3.5, 4.5):
                for k in range(16):
                    a = k * math.pi / 8
                    vx, vy = px + r * math.cos(a), py + r * math.sin(a)
                    key = (round(vx, 1), round(vy, 1))
                    if key in seen:
                        continue
                    seen.add(key)
                    if model.via_ok(vx, vy, code) and model.seg_ok(px, py, vx, vy, layer, (code,)):
                        out.append(((vx, vy), (layer, (px, py))))
                if len(out) >= 8:
                    return out
    return out


def connect_net(model, board, name, layers=(L6, L3), extras=(0.0,)):
    net = board.FindNet(name)
    code = net.GetNetCode()
    isl = net_islands(board, name)
    if len(isl) < 2:
        return "connected"
    isl.sort(key=len, reverse=True)
    main = isl[0]
    for other in isl[1:]:
        ta = terminals(model, main, code)
        tb = terminals(model, other, code)
        if not ta or not tb:
            return f"no terminals ({len(ta)}/{len(tb)})"
        routed = False
        for extra in extras:
            for layer in layers:
                free = model.free(layer, (code,), HALF, extra)
                starts = [cell_of(p) for p, _ in ta]
                goals = {cell_of(p): (p, via) for p, via in tb}
                path = astar(free, starts, list(goals))
                if path is None:
                    continue
                a = next((p, v) for p, v in ta if cell_of(p) == path[0])
                b = goals[path[-1]]
                pts = simplify([a[0]] + pull(free, [xy_of(c) for c in path], 135.0) + [b[0]])
                if not model.poly_ok(pts, layer, (code,), HALF, extra):
                    continue
                for p, via in (a, b):
                    if via is not None and not (model.via_ok(*p, code) and model.seg_ok(*via[1], *p, via[0], (code,))):
                        break
                else:
                    for p, via in (a, b):
                        if via is not None:
                            draw_track(board, model, *via[1], *p, via[0], net)
                            draw_via(board, model, *p, net)
                    draw_poly(board, model, pts, layer, net)
                    routed = True
                    print(f"    {name}: {poly_len(pts):.1f} mm on {board.GetLayerName(layer)}"
                          f"{f', clearance {CLEAR + extra:.2f}' if extra else ''}", flush=True)
                    break
            if routed:
                break
        if not routed:
            return "no path"
        main = main + other
    return "ok"


def cmd_opens(path):
    board = pcbnew.LoadBoard(str(path))
    report = drc(path)
    names = []
    for u in report.get("unconnected_items") or []:
        for it in u["items"]:
            n = net_of(it["description"])
            if n and n not in names and not n.startswith("unconnected"):
                names.append(n)
    names.sort(key=lambda n: (n not in ANALOG, n))
    print(f"{len(names)} nets with islands: {' '.join(names)}", flush=True)
    model = Model(board)
    for name in names:
        extras = (0.2, 0.1, 0.0) if name in ANALOG else (0.0,)
        res = connect_net(model, board, name, extras=extras)
        print(f"  {name}: {res}", flush=True)
        save(board, path)
    fill_zones(board)
    save(board, path)


# --- stitching and clean-up ----------------------------------------------
def same_net_hole_clashes(board):
    """Vias whose drill sits on or next to a same-net THT hole."""
    holes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                p = pad.GetPosition()
                holes.append((mm(p.x), mm(p.y), max(mm(pad.GetDrillSize().x), mm(pad.GetDrillSize().y)) / 2,
                              pad.GetNetCode(), pad))
    out = []
    for v in board.GetTracks():
        if v.GetClass() != "PCB_VIA":
            continue
        p = v.GetPosition()
        x, y, r = mm(p.x), mm(p.y), mm(v.GetDrillValue()) / 2
        for hx, hy, hr, net, pad in holes:
            if math.hypot(x - hx, y - hy) - hr - r < HOLE_TO_HOLE - 1e-6:
                out.append((v, pad, net == v.GetNetCode()))
    return out


def fix_hole_clashes(board):
    fixed = 0
    for v, pad, same in same_net_hole_clashes(board):
        if not same:
            print(f"  via {v.GetNetname()} clashes with a foreign hole, left for DRC", flush=True)
            continue
        vp = v.GetPosition()
        pp = pad.GetPosition()
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != v.GetNetCode():
                continue
            r = v.GetWidth(F) // 2
            if (t.GetStart() - vp).EuclideanNorm() <= r:
                t.SetStart(pp)
            if (t.GetEnd() - vp).EuclideanNorm() <= r:
                t.SetEnd(pp)
        board.Remove(v)
        fixed += 1
    return fixed


def stitch_fence(board, model, gnd, pitch=1.5, inset=0.8):
    code = gnd.GetNetCode()
    existing = [(mm(t.GetPosition().x), mm(t.GetPosition().y)) for t in board.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetCode() == code]
    x0, y0, x1, y1 = model.ex0 + inset, model.ey0 + inset, model.ex1 - inset, model.ey1 - inset
    pts = []
    for x, y, dx, dy, L in ((x0, y0, 1, 0, x1 - x0), (x1, y0, 0, 1, y1 - y0), (x1, y1, -1, 0, x1 - x0), (x0, y1, 0, -1, y1 - y0)):
        n = int(L // pitch)
        for k in range(n):
            pts.append((x + dx * k * pitch, y + dy * k * pitch))
    added = 0
    for x, y in pts:
        if any(math.hypot(x - ex, y - ey) < pitch * 0.6 for ex, ey in existing):
            continue
        for dx, dy in ((0, 0), (0.2, 0), (-0.2, 0), (0, 0.2), (0, -0.2), (0.4, 0), (-0.4, 0), (0, 0.4), (0, -0.4)):
            if model.via_ok(x + dx, y + dy, code):
                draw_via(board, model, x + dx, y + dy, gnd)
                existing.append((x + dx, y + dy))
                added += 1
                break
    return added, len(pts)


def stitch_islands(board, model, gnd, min_area=2.0):
    """Give every unconnected pour island on the outer layers a ground via."""
    code = gnd.GetNetCode()
    vias = [(mm(t.GetPosition().x), mm(t.GetPosition().y)) for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetCode() == code]
    gpads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == code:
                gpads.append(pad)
    added = 0
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != code or z.GetLayer() not in (F, B):
            continue
        layer = z.GetLayer()
        polys = z.GetFilledPolysList(layer)
        for k in range(polys.OutlineCount()):
            ol = polys.Outline(k)
            pts = [(mm(ol.CPoint(i).x), mm(ol.CPoint(i).y)) for i in range(ol.PointCount())]
            if len(pts) < 3:
                continue
            area = abs(sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))) / 2
            if area < min_area:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            if any(min(xs) <= vx <= max(xs) and min(ys) <= vy <= max(ys) and in_poly(vx, vy, pts) for vx, vy in vias):
                continue
            if any(pad.IsOnLayer(layer) and in_poly(mm(pad.GetPosition().x), mm(pad.GetPosition().y), pts) for pad in gpads):
                continue
            placed = 0
            step = 0.3
            gx = min(xs)
            while gx <= max(xs) and placed < 2:
                gy = min(ys)
                while gy <= max(ys) and placed < 2:
                    if in_poly(gx, gy, pts) and poly_dist(gx, gy, pts) > VIA_R + 0.05 and model.via_ok(gx, gy, code):
                        if all(math.hypot(gx - a, gy - b) > 1.0 for a, b in vias[-placed:] if placed):
                            draw_via(board, model, gx, gy, gnd)
                            vias.append((gx, gy))
                            placed += 1
                    gy += step
                gx += step
            added += placed
    return added


def remove_dangling(board, path, rounds=8):
    removed = 0
    for _ in range(rounds):
        rep = drc(path, "all")
        ids = set()
        for v in rep.get("violations") or []:
            if v["type"] in ("track_dangling", "via_dangling"):
                for it in v["items"]:
                    if it.get("uuid"):
                        ids.add(it["uuid"])
        if not ids:
            break
        kill = [t for t in board.GetTracks() if t.m_Uuid.AsString() in ids]
        for t in kill:
            board.Remove(t)
        removed += len(kill)
        fill_zones(board)
        save(board, path)
        board = pcbnew.LoadBoard(str(path))
    return removed, board


def cmd_stitch(path):
    board = pcbnew.LoadBoard(str(path))
    print(f"same-net hole clashes removed: {fix_hole_clashes(board)}", flush=True)
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.SetMinThickness(iu(0.2))
    fill_zones(board)
    model = Model(board)
    gnd = board.FindNet("GND")
    added, total = stitch_fence(board, model, gnd)
    print(f"edge fence: {added} ground vias added along {total} sites", flush=True)
    fill_zones(board)
    print(f"pour islands stitched: {stitch_islands(board, model, gnd)} vias", flush=True)
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    fill_zones(board)
    save(board, path)
    removed, board = remove_dangling(board, path)
    print(f"dangling copper removed: {removed}", flush=True)
    fill_zones(board)
    save(board, path)


# --- report --------------------------------------------------------------
def shortest_path(board, name, is_src, is_dst):
    """Shortest copper path of one net between two pads, as a 2D polyline."""
    segs = []
    for t in board.GetTracks():
        if t.GetNetname() == name and t.GetClass() != "PCB_VIA":
            a, c = t.GetStart(), t.GetEnd()
            segs.append((mm(a.x), mm(a.y), mm(c.x), mm(c.y)))
    g = defaultdict(list)

    def key(x, y):
        return (round(x, 3), round(y, 3))

    def link(a, b):
        w = math.hypot(b[0] - a[0], b[1] - a[1]) if isinstance(a[0], float) and isinstance(b[0], float) else 0.0
        g[a].append((b, w))
        g[b].append((a, w))

    pts = set()
    for x1, y1, x2, y2 in segs:
        a, b = key(x1, y1), key(x2, y2)
        link(a, b)
        pts |= {a, b}
    # A track may end on the middle of another one.
    for p in list(pts):
        for x1, y1, x2, y2 in segs:
            a, b = key(x1, y1), key(x2, y2)
            if p not in (a, b) and dist_seg(p[0], p[1], x1, y1, x2, y2) < 0.01:
                link(p, a)
                link(p, b)
    src = dst = None
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if pad.GetNetname() != name:
                continue
            s = pad_shape(pad, F if pad.IsOnLayer(F) else B)
            px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
            node = ("pad", ref, pad.GetNumber())
            for p in pts:
                if shape_dist(s, p[0], p[1]) <= 0.08:
                    w = math.hypot(p[0] - px, p[1] - py)
                    g[node].append((p, w))
                    g[p].append((node, w))
            if src is None and is_src(ref):
                src = (node, (px, py))
            elif dst is None and is_dst(ref):
                dst = (node, (px, py))
    if not src or not dst:
        return None
    dist, prev, cnt = {src[0]: 0.0}, {}, 0
    pq = [(0.0, cnt, src[0])]
    while pq:
        d, _, u = heapq.heappop(pq)
        if u == dst[0]:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in g[u]:
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                prev[v] = u
                cnt += 1
                heapq.heappush(pq, (d + w, cnt, v))
    if dst[0] not in dist:
        return None
    seq = [dst[0]]
    while seq[-1] != src[0]:
        seq.append(prev[seq[-1]])
    seq.reverse()
    coords = {src[0]: src[1], dst[0]: dst[1]}
    return [coords.get(n, n) for n in seq], dist[dst[0]]


def loop_between(board, name_p, name_n, is_src, is_dst):
    """Area enclosed by P out and N back; a uniform field induces in proportion to it."""
    rp = shortest_path(board, name_p, is_src, is_dst)
    rn = shortest_path(board, name_n, is_src, is_dst)
    if not rp or not rn:
        return None
    poly = rp[0] + rn[0][::-1]
    area = abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2
    return area, rp[1], rn[1]


def is_cmc(ref):
    return ref.startswith("FL")


def is_ic(ref):
    return ref.startswith("U")


def is_jack(ref):
    return ref[0] == "J" and ref[1:].isdigit()


def cmd_report(path):
    board = pcbnew.LoadBoard(str(path))
    rep = drc(path, "all")
    counts, unconn = drc_summary(rep)
    errors = sum(1 for v in rep.get("violations") or [] if v["severity"] == "error")
    print(f"DRC: {errors} errors, {unconn} unconnected; warnings {dict(sorted(counts.items()))}")
    print(f"{'pair':6} {'loop IC-CMC':>12} {'P':>7} {'N':>7} {'dP-N':>6} {'loop CMC-jack':>14}")
    for pair in ALL_PAIRS:
        a = loop_between(board, f"{pair}_P", f"{pair}_N", is_cmc, is_ic)
        j = loop_between(board, f"{pair}_PJ", f"{pair}_NJ", is_cmc, is_jack)
        jt = f"{j[0]:10.1f} mm2" if j else "      open"
        if a is None:
            print(f"{pair:6} {'open':>12} {'':7} {'':7} {'':6} {jt}")
            continue
        area, lp, ln = a
        print(f"{pair:6} {area:9.1f} mm2 {lp:7.1f} {ln:7.1f} {abs(lp - ln):6.1f} {jt}")
    per = defaultdict(float)
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            per[board.GetLayerName(t.GetLayer())] += mm(t.GetLength())
    print("track length by layer (m):", {k: round(v / 1000, 2) for k, v in per.items()})
    print("vias:", sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"))


def main(argv):
    if len(argv) < 2 or argv[1] not in ("stackup", "lvds", "opens", "stitch", "report"):
        sys.exit(__doc__)
    path = Path(argv[2]) if len(argv) > 2 else BOARD
    {"stackup": cmd_stackup, "lvds": cmd_lvds, "opens": cmd_opens, "stitch": cmd_stitch, "report": cmd_report}[argv[1]](path)


if __name__ == "__main__":
    main(sys.argv)
