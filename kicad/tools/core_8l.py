#!/usr/bin/env python3
"""Finish the het68 Core on eight copper layers.

    python3 kicad/tools/core_8l.py stackup [board]
    python3 kicad/tools/core_8l.py lvds    [board]
    python3 kicad/tools/core_8l.py opens   [board]
    python3 kicad/tools/core_8l.py stitch  [board]
    python3 kicad/tools/core_8l.py report  [board]

Each step edits the board in place and saves it. Copper is removed only for
the LVDS nets being re-routed, vias whose drill collides with a same-net
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
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pcbnew

BOARD = Path(__file__).resolve().parents[1] / "het68-core" / "het68-core.kicad_pcb"

F, B = pcbnew.F_Cu, pcbnew.B_Cu
L3, L4, L6 = pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In5_Cu
SIGNAL = (F, L3, L4, L6, B)
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
VIA_KEEP = HALF + max(VIA_R + CLEAR, HOLE_R + HOLE_CLEAR) + SLACK  # track centre to a foreign via
PAIR_OFF = 0.15  # centre line to P or N: (track + gap) / 2
PAIR_HALF = 0.30  # corridor half-width; leaves room for the mitred offset at a 90 degree corner
LEAD = 0.6
GRID = 0.1
CELL = 1.0
REACH = 0.9  # largest query radius the spatial bins must cover

LVDS = tuple(f"{k}{i}" for k in ("SD", "SCK", "WS") for i in range(1, 7))
ANALOG = ("ADC_I", "ADC_ROGO", "ADC_HARVEST")


def mm(v):
    return pcbnew.ToMM(v)


def iu(v):
    return pcbnew.FromMM(float(v))


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


def pad_xy(pad):
    p = pad.GetPosition()
    return mm(p.x), mm(p.y)


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
        x, y = pad_xy(pad)
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
                self.raster(g, shape, h + CLEAR + extra + SLACK, 1)

    def add_hole(self, x, y, r, net):
        j = len(self.holes)
        self.holes.append((x, y, r, net))
        self.net_holes[net].append(j)
        for key in self._cells((x - r, y - r, x + r, y + r)):
            self.hbins[key].append(j)
        for (layer, h, extra), g in self.grids.items():
            self.raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, 1)

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
    def raster(self, g, s, R, val):
        x0, y0, x1, y1 = shape_bbox(s)
        i0 = max(0, int(math.floor((x0 - R) / GRID)))
        i1 = min(self.nx - 1, int(math.ceil((x1 + R) / GRID)))
        j0 = max(0, int(math.floor((y0 - R) / GRID)))
        j1 = min(self.ny - 1, int(math.ceil((y1 + R) / GRID)))
        if i1 < i0 or j1 < j0:
            return
        X = (np.arange(i0, i1 + 1) * GRID)[None, :]
        Y = (np.arange(j0, j1 + 1) * GRID)[:, None]
        hit = (shape_dist_np(s, X, Y) < R).astype(g.dtype)
        if val > 0:
            g[j0 : j1 + 1, i0 : i1 + 1] += hit
        else:
            g[j0 : j1 + 1, i0 : i1 + 1] -= hit

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
                self.raster(g, s, h + CLEAR + extra + SLACK, 1)
        for x, y, r, net in self.holes:
            self.raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, 1)
        for layers, pts in self.keep_track:
            if layer in layers:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                for j in range(max(0, int((min(ys) - h) / GRID)), min(self.ny, int((max(ys) + h) / GRID) + 2)):
                    for i in range(max(0, int((min(xs) - h) / GRID)), min(self.nx, int((max(xs) + h) / GRID) + 2)):
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
                    self.raster(g, s, h + CLEAR + extra + SLACK, -1)
            for j in self.net_holes.get(net, ()):
                x, y, r, _ = self.holes[j]
                self.raster(g, ("disc", x, y, r), h + HOLE_CLEAR + extra + SLACK, -1)
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
    t.thisown = 0
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
    v.thisown = 0
    model.add_track(v)
    return v


def fill_zones(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def save(board, path):
    pcbnew.SaveBoard(str(path), board)


def delete(board, items):
    # BOARD.Remove() hands ownership to Python and corrupts the SWIG type table
    # once the wrappers are collected; Delete() frees the item on the C++ side.
    for it in items:
        board.Delete(it)
    return len(items)


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


def turn_steps(a, b):
    return min((a - b) % 8, (b - a) % 8)


def dir_index(u):
    best, bi = -9.0, 0
    for i, (dx, dy) in enumerate(DIRS):
        d = (u[0] * dx + u[1] * dy) / math.hypot(dx, dy)
        if d > best:
            best, bi = d, i
    return bi


def astar(free, starts, goals, goal_dir=None, turn=0.4, weight=1.25, limit=600_000):
    """8-connected A* on a boolean grid without turns sharper than 90 degrees.

    starts: (i, j, direction or None). With goal_dir the last step into a goal
    must be within 90 degrees of it."""
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
    for i, j, d0 in starts:
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
            if d0 is not None and turn_steps(di, d0) > 2:
                continue
            ni, nj = i + dx, j + dy
            if not (0 <= ni < nx and 0 <= nj < ny) or not fb[nj * nx + ni]:
                continue
            if dx and dy and not (fb[j * nx + ni] and fb[nj * nx + i]):
                continue
            nk = (ni, nj)
            if nk in closed:
                continue
            if goal_dir is not None and nk in goal_set and turn_steps(di, goal_dir) > 2:
                continue
            ng = gc + (SQ2 if dx and dy else 1.0) + (turn if d0 is not None and d0 != di else 0.0)
            if ng < gsc.get(nk, 1e18):
                gsc[nk] = ng
                parent[nk] = k
                dirn[nk] = di
                heapq.heappush(openh, (ng + weight * heur(ni, nj), ng, ni, nj))
    return None


def regions(free):
    """4-connected regions of a boolean grid, labelled run by run. Returns label(i, j), -1 if blocked.
    A* only cuts a corner between two free cells, so it never connects what this separates."""
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    rows = []
    prev = None
    pad = np.zeros(1, np.int8)
    for row in free.astype(np.int8):
        d = np.diff(np.concatenate((pad, row, pad)))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        base = len(parent)
        parent.extend(range(base, base + len(starts)))
        if prev is not None:
            ps, pe, pbase = prev
            k = 0
            for i in range(len(starts)):
                s, e = starts[i], ends[i]
                while k < len(ps) and pe[k] <= s:
                    k += 1
                kk = k
                while kk < len(ps) and ps[kk] < e:
                    ra, rb = find(base + i), find(pbase + kk)
                    if ra != rb:
                        parent[rb] = ra
                    kk += 1
        rows.append((starts, ends, base))
        prev = (starts, ends, base)
    roots = [find(i) for i in range(len(parent))]

    def label(i, j):
        if not (0 <= j < len(rows)):
            return -1
        starts, ends, base = rows[j]
        k = int(np.searchsorted(starts, i, side="right")) - 1
        return roots[base + k] if k >= 0 and i < ends[k] else -1

    return label


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


def pull(free, pts, u_in=None, u_out=None):
    """Drop vertices while the shortcut stays on free cells and no turn exceeds 90 degrees."""
    ny, nx = free.shape
    fb = free.astype(np.uint8).tobytes()
    out = [pts[0]]
    prev = u_in
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1:
            if line_free(fb, nx, ny, pts[i], pts[j]):
                d = unit(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])
                ok = prev is None or d[0] * prev[0] + d[1] * prev[1] >= 0.0
                if ok and j == len(pts) - 1 and u_out is not None:
                    ok = d[0] * u_out[0] + d[1] * u_out[1] >= 0.0
                if ok:
                    break
            j -= 1
        prev = unit(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])
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


TURN_COS = -0.1  # turns up to about 95 degrees; grid snapping tilts the leads a little


def turns_ok(pts):
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        u, v = unit(b[0] - a[0], b[1] - a[1]), unit(c[0] - b[0], c[1] - b[1])
        if u[0] * v[0] + u[1] * v[1] < TURN_COS:
            return False
    return True


def smooth(free, pts, min_seg=0.5):
    """Drop vertices around centre-line segments shorter than min_seg; the inner
    offset of such a segment folds back. The leads at both ends stay."""
    ny, nx = free.shape
    fb = free.astype(np.uint8).tobytes()
    pts = list(pts)
    changed = True
    while changed:
        changed = False
        for i in range(1, len(pts) - 2):
            if math.dist(pts[i], pts[i + 1]) >= min_seg:
                continue
            for drop in (i + 1, i):
                if drop <= 1 or drop >= len(pts) - 2:
                    continue
                cand = pts[:drop] + pts[drop + 1 :]
                if line_free(fb, nx, ny, cand[drop - 1], cand[drop]) and turns_ok(cand[max(0, drop - 2) : drop + 2]):
                    pts = cand
                    changed = True
                    break
            if changed:
                break
    return pts


def poly_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def poly_gap(p1, p2):
    best = 1e18
    for a, b in zip(p1, p1[1:]):
        for c, d in zip(p2, p2[1:]):
            best = min(best, seg_seg(a, b, c, d))
    return best


def point_poly(p, pts):
    return min(dist_seg(p[0], p[1], a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:]))


class End:
    """Where a pair route lands: P and N copper points and the start of the centre line.

    leads are the directions a route may leave in; it arrives against one of them."""

    def __init__(self, vp, vn, mid=None, leads=None, stub_p=(), stub_n=(), new_vias=True, label="", layer=None):
        self.layer = layer  # set when the fan-out to the pins exists only on that layer
        self.vp, self.vn = vp, vn
        self.mid = mid or ((vp[0] + vn[0]) / 2, (vp[1] + vn[1]) / 2)
        if leads is None:
            ax = unit(-(vp[1] - vn[1]), vp[0] - vn[0])
            leads = [ax, (-ax[0], -ax[1])]
        self.leads = leads
        self.stub_p, self.stub_n = list(stub_p), list(stub_n)
        self.stub_layer = F
        self.new_vias = new_vias
        self.label = label
        self.drawn = False

    def side(self, u):
        n = left(u)
        return 1 if (self.vp[0] - self.vn[0]) * n[0] + (self.vp[1] - self.vn[1]) * n[1] > 0 else -1


class Route:
    def __init__(self, start, end, u0, u1, p, n, layer):
        self.start, self.end, self.u0, self.u1 = start, end, u0, u1
        self.p, self.n, self.layer = p, n, layer


def pad_info(pad):
    x, y = pad_xy(pad)
    s = pad_size(pad, F)
    a = math.radians(pad.GetOrientation().AsDegrees())
    hx, hy = mm(s.x) / 2, mm(s.y) / 2
    long_axis = (math.cos(a), -math.sin(a)) if hx >= hy else (math.sin(a), math.cos(a))
    return x, y, long_axis, max(hx, hy)


def outward(pad):
    x, y, ax, hl = pad_info(pad)
    c = pad.GetParentFootprint().GetPosition()
    if (x - mm(c.x)) * ax[0] + (y - mm(c.y)) * ax[1] < 0:
        ax = (-ax[0], -ax[1])
    return ax, hl


def smd_pair_ends(model, pad_p, pad_n, netp, netn, want=6, reach=3.0):
    """Via pairs for two SMD pads: a via in each pad first, then vias on short stubs."""
    xp, yp = pad_xy(pad_p)
    xn, yn = pad_xy(pad_n)
    o, hl = outward(pad_p)
    out = []
    lim = max(0.0, hl - VIA_R - 0.02)
    for t in (0.0, 0.5, -0.5, 1.0, -1.0):
        vp = (xp + o[0] * t * lim, yp + o[1] * t * lim)
        vn = (xn + o[0] * t * lim, yn + o[1] * t * lim)
        if math.dist(vp, vn) >= 0.45 and model.via_ok(*vp, netp) and model.via_ok(*vn, netn):
            out.append(End(vp, vn, label="via in pad"))
            break
    cx, cy = (xp + xn) / 2, (yp + yn) / 2
    cands = []
    steps = np.arange(-reach, reach + 1e-9, 0.25)
    for dx in steps:
        for dy in steps:
            for horiz in (True, False):
                a = (cx + dx - 0.3, cy + dy) if horiz else (cx + dx, cy + dy - 0.3)
                b = (cx + dx + 0.3, cy + dy) if horiz else (cx + dx, cy + dy + 0.3)
                c1 = math.dist(a, (xp, yp)) + math.dist(b, (xn, yn))
                c2 = math.dist(b, (xp, yp)) + math.dist(a, (xn, yn))
                cands.append((c1, a, b) if c1 <= c2 else (c2, b, a))
    cands.sort(key=lambda c: c[0])
    for cost, vp, vn in cands:
        if len(out) >= want or cost > 2 * reach + 1.0:
            break
        if not (model.via_ok(*vp, netp) and model.via_ok(*vn, netn)):
            continue
        sp, sn = [(xp, yp), vp], [(xn, yn), vn]
        if not (model.poly_ok(sp, F, (netp,)) and model.poly_ok(sn, F, (netn,))):
            continue
        if poly_gap(sp, sn) < TRACK + CLEAR + SLACK:
            continue
        if point_poly(vn, sp) < VIA_KEEP or point_poly(vp, sn) < VIA_KEEP:
            continue
        out.append(End(vp, vn, stub_p=sp, stub_n=sn, label="vias beside"))
    return out


def pin_pair_ends(model, pin_p, pin_n, netp, netn, away=(0.0, 1.0), layer=L6, want=8):
    """Junctions next to two through-hole pins, P and N fanning out to the pins on the
    routing layer. The pair leaves roughly along `away`."""
    xp, yp = pad_xy(pin_p)
    xn, yn = pad_xy(pin_n)
    m = ((xp + xn) / 2, (yp + yn) / 2)
    cands = []
    for r in (1.2, 1.6, 2.0, 2.5, 3.0, 3.6, 4.3, 5.0, 6.0):
        for k in range(48):
            a = 2 * math.pi * k / 48
            u = (math.cos(a), math.sin(a))
            facing = u[0] * away[0] + u[1] * away[1]
            if facing < 0.3:
                continue
            j = (m[0] + r * u[0], m[1] + r * u[1])
            cands.append((r - facing, j, u))
    cands.sort(key=lambda c: c[0])
    out = []
    for _, j, u in cands:
        e = End((xp, yp), (xn, yn), mid=j, leads=[u], new_vias=False, label="pins", layer=layer)
        s = e.side(u)
        n = left(u)
        pj = (j[0] + n[0] * s * PAIR_OFF, j[1] + n[1] * s * PAIR_OFF)
        nj = (j[0] - n[0] * s * PAIR_OFF, j[1] - n[1] * s * PAIR_OFF)
        pl = [(xp, yp), pj, (pj[0] + u[0] * LEAD, pj[1] + u[1] * LEAD)]
        nl = [(xn, yn), nj, (nj[0] + u[0] * LEAD, nj[1] + u[1] * LEAD)]
        if not (model.poly_ok(pl, layer, (netp,)) and model.poly_ok(nl, layer, (netn,))):
            continue
        if poly_gap(pl, nl) < TRACK + CLEAR + SLACK:
            continue
        if any(math.dist(j, o.mid) < 0.4 for o in out):
            continue
        out.append(e)
        if len(out) >= want:
            break
    return out


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


def pad_clear(model, pad, net):
    s = pad_shape(pad, F)
    x0, y0, x1, y1 = shape_bbox(s)
    for gx in np.linspace(x0, x1, 5):
        for gy in np.linspace(y0, y1, 5):
            if shape_dist(s, gx, gy) <= 1e-6 and not model.copper_ok(gx, gy, F, (net,), 0.0):
                return False
    return True


def terminator_ends(board, model, rfp, ic_p, ic_n, from_xy, netp, netn, want=12):
    """Spots for the 100 ohm resistor beside the receiver.

    Each spot keeps a via in the resistor pads, a short F.Cu run from the receiver
    pins, and a lead facing the choke so the pair arrives from that side.
    Returns (End, (x, y, rotation)); the footprint is left where it was."""
    pos0, rot0 = rfp.GetPosition(), rfp.GetOrientationDegrees()
    rp = next(p for p in rfp.Pads() if p.GetNetCode() == netp)
    rn = next(p for p in rfp.Pads() if p.GetNetCode() == netn)
    near = tuple((a + b) / 2 for a, b in zip(pad_xy(ic_p), pad_xy(ic_n)))
    others = [courtyard_box(f) for f in board.GetFootprints() if f.GetReference() != rfp.GetReference()]
    out = []
    try:
        for r in (2.2, 2.8, 3.4, 4.2, 5.2, 6.4, 8.0):
            for k in range(24):
                a = 2 * math.pi * k / 24
                centre = (near[0] + r * math.cos(a), near[1] + r * math.sin(a))
                arrive = unit(from_xy[0] - centre[0], from_xy[1] - centre[1])
                for rot in (0.0, 90.0, 180.0, 270.0):
                    rfp.SetPosition(vec(*centre))
                    rfp.SetOrientationDegrees(rot)
                    box = courtyard_box(rfp)
                    if not (model.inside(box[0], box[1], 0.0) and model.inside(box[2], box[3], 0.0)):
                        continue
                    if any(boxes_overlap(box, ob, 0.05) for ob in others):
                        continue
                    if not (pad_clear(model, rp, netp) and pad_clear(model, rn, netn)):
                        continue
                    vp, vn = pad_xy(rp), pad_xy(rn)
                    across = unit(vp[0] - vn[0], vp[1] - vn[1])
                    if abs(across[0] * arrive[0] + across[1] * arrive[1]) > 0.45:
                        continue
                    if not (model.via_ok(*vp, netp) and model.via_ok(*vn, netn)):
                        continue
                    sp, sn = [pad_xy(ic_p), vp], [pad_xy(ic_n), vn]
                    if not (model.poly_ok(sp, F, (netp,)) and model.poly_ok(sn, F, (netn,))):
                        continue
                    if poly_gap(sp, sn) < TRACK + CLEAR + SLACK:
                        continue
                    out.append((End(vp, vn, leads=[arrive], stub_p=sp, stub_n=sn, label=rfp.GetReference()),
                                (centre[0], centre[1], rot)))
                    if len(out) >= want:
                        return out
        return out
    finally:
        rfp.SetPosition(pos0)
        rfp.SetOrientationDegrees(rot0)


def avoid_mask(model, polys, keep_clear_at, radius=1.0):
    g = np.zeros((model.ny, model.nx), np.int16)
    for poly in polys:
        for a, b in zip(poly, poly[1:]):
            model.raster(g, ("stad", a[0], a[1], b[0], b[1], HALF), PAIR_HALF + CLEAR + SLACK, 1)
    x, y = keep_clear_at
    i0, i1 = max(0, int((x - radius) / GRID)), min(model.nx - 1, int((x + radius) / GRID) + 1)
    j0, j1 = max(0, int((y - radius) / GRID)), min(model.ny - 1, int((y + radius) / GRID) + 1)
    X = (np.arange(i0, i1 + 1) * GRID)[None, :]
    Y = (np.arange(j0, j1 + 1) * GRID)[:, None]
    near = np.hypot(X - x, Y - y) < radius
    g[j0 : j1 + 1, i0 : i1 + 1][near] = 0
    return g > 0


def pair_ok(model, codes, p, n, layer, ends, others):
    if not (model.poly_ok(p, layer, (codes[0],)) and model.poly_ok(n, layer, (codes[1],))):
        return False
    if poly_gap(p, n) < TRACK + CLEAR + SLACK:
        return False
    for e in ends:
        if e.new_vias and (point_poly(e.vn, p) < VIA_KEEP or point_poly(e.vp, n) < VIA_KEEP):
            return False
    for poly, code in others:
        mine = n if code == codes[0] else p
        if poly_gap(mine, poly) < TRACK + CLEAR + SLACK:
            return False
    return True


def lead_cell(p, u, length=LEAD):
    """Grid cell about `length` from p along u, never behind the requested length."""
    c = cell_of((p[0] + u[0] * length, p[1] + u[1] * length))
    q = xy_of(c)
    while (q[0] - p[0]) * u[0] + (q[1] - p[1]) * u[1] < length - GRID / 2:
        c = cell_of((q[0] + u[0] * GRID, q[1] + u[1] * GRID))
        q = xy_of(c)
    return c, q


def route_pairs(model, codes, starts, ends, lead=None, others=(), layer=L6, tries=24, deadline=None, half=None):
    """Yield routes between start and end candidates; P and N are offsets of one centre line.

    The search corridor starts at 0.30 mm and narrows to 0.20 mm, so a pair can
    pass a gap the wide corridor cannot enter. The drawn copper is checked exactly."""
    if half is None:
        produced = False
        for h in (PAIR_HALF, 0.24, 0.20):
            for route in route_pairs(model, codes, starts, ends, lead, others, layer, tries, deadline, h):
                produced = True
                yield route
            if produced or (deadline and time.time() > deadline):
                return
        return
    base = model.free(layer, codes, half)
    base_label = None
    n_try = 0
    starts = [s for s in starts if s.layer in (None, layer)]
    ends = [e for e in ends if e.layer in (None, layer)]
    for s in starts:
        for u0 in ([lead] if lead is not None else s.leads):
            side = s.side(u0)
            a0 = s.mid
            c0, a1 = lead_cell(a0, u0)
            if others:
                free = base & ~avoid_mask(model, [poly for poly, _ in others], a0)
                label = regions(free)
            else:
                free = base
                base_label = base_label or regions(base)
                label = base_label
            if label(*c0) < 0:
                continue
            for e in ends:
                for u1 in [(-l[0], -l[1]) for l in e.leads]:
                    if e.side(u1) != side:
                        continue
                    b1 = e.mid
                    c1, b0 = lead_cell(b1, (-u1[0], -u1[1]))
                    if label(*c1) != label(*c0):
                        continue
                    n_try += 1
                    if n_try > tries or (deadline and time.time() > deadline):
                        return
                    path = astar(free, [(c0[0], c0[1], dir_index(u0))], [c1], goal_dir=dir_index(u1))
                    if path is None:
                        continue
                    mid = pull(free, [xy_of(c) for c in path], u0, u1)
                    centre = smooth(free, simplify([a0, a1] + mid + [b0, b1]))
                    if not turns_ok(centre):
                        continue
                    pl = offset(centre, side * PAIR_OFF)
                    nl = offset(centre, -side * PAIR_OFF)
                    p_full = simplify([s.vp] + pl + [e.vp])
                    n_full = simplify([s.vn] + nl + [e.vn])
                    if pair_ok(model, codes, p_full, n_full, layer, (s, e), others):
                        yield Route(s, e, u0, u1, p_full, n_full, layer)


def route_chain(model, codes, cand_lists, layers=(L6, L3), branch=3, budget=240.0):
    """Route through a chain of nodes; a middle node is passed straight through.
    Each leg tries SIG_L6 first, then SIG_L3; the nodes are vias or THT pins."""
    deadline = time.time() + budget

    def rec(idx, starts, lead, done, others):
        if idx == len(cand_lists) - 1:
            return done
        for layer in layers:
            same = [(poly, code) for poly, code, l in others if l == layer]
            tried = set()
            for r in route_pairs(model, codes, starts, cand_lists[idx + 1], lead, same, layer, deadline=deadline):
                # What the next leg depends on: where this one lands and in which direction.
                key = (id(r.end), round(r.u1[0], 2), round(r.u1[1], 2))
                if key in tried:
                    continue
                tried.add(key)
                if len(tried) > branch:
                    break
                res = rec(idx + 1, [r.end], r.u1, done + [r],
                          others + [(r.p, codes[0], layer), (r.n, codes[1], layer)])
                if res:
                    return res
        return None

    return rec(0, cand_lists[0], None, [], [])


def draw_route(board, model, r, netp, netn):
    for e in (r.start, r.end):
        if not e.drawn:
            draw_poly(board, model, e.stub_p, e.stub_layer, netp)
            draw_poly(board, model, e.stub_n, e.stub_layer, netn)
            if e.new_vias:
                draw_via(board, model, *e.vp, netp)
                draw_via(board, model, *e.vn, netn)
        e.drawn = True
    draw_poly(board, model, r.p, r.layer, netp)
    draw_poly(board, model, r.n, r.layer, netn)


def gather_jack(model, pin_p, pin_n, netp, netn):
    """Bring two far-apart jack pins together south of the connector, then run them as a pair.

    WS pins sit four positions apart, so no coupled corridor fits between the holes."""
    xp, yp = pad_xy(pin_p)
    xn, yn = pad_xy(pin_n)
    y0 = max(yp, yn)
    out = []
    # Start far enough south that the coupled pair is clear of the jack holes.
    for layer in (F, L6, L3):
        for extra in (5.0, 7.0, 9.5, 13.0):
            y = y0 + extra
            mid_x = (xp + xn) / 2
            for x in (mid_x, mid_x - 1, mid_x + 1, mid_x - 2, mid_x + 2, xp, xn):
                # Vias need 0.40 mm between centres; the running pair is only 0.30 mm.
                vp, vn = (x - 0.25, y), (x + 0.25, y)
                if layer == F and not (model.via_ok(*vp, netp) and model.via_ok(*vn, netn)):
                    continue
                sp = [(xp, yp), (xp, y), vp]
                sn = [(xn, yn), (xn, y), vn]
                if not (model.poly_ok(sp, layer, (netp,)) and model.poly_ok(sn, layer, (netn,))):
                    continue
                if poly_gap(sp, sn) < TRACK + CLEAR + SLACK:
                    continue
                # A surface escape needs vias. An inner escape is already on the pair layer.
                end = End(vp, vn, leads=[(0.0, 1.0)], stub_p=sp, stub_n=sn, new_vias=(layer == F),
                          layer=None if layer == F else layer, label="gathered")
                end.stub_layer = layer
                out.append(end)
                if len(out) >= 6:
                    return out
    return out


def connect_terminator(board, model, rfp, ic_p, ic_n, netp, netn):
    """Park the 100 ohm resistor by the receiver and tie each pad to its pin on F.Cu."""
    pos0, rot0 = rfp.GetPosition(), rfp.GetOrientationDegrees()
    rp = next(p for p in rfp.Pads() if p.GetNetCode() == netp)
    rn = next(p for p in rfp.Pads() if p.GetNetCode() == netn)
    near = tuple((a + b) / 2 for a, b in zip(pad_xy(ic_p), pad_xy(ic_n)))
    others = [courtyard_box(f) for f in board.GetFootprints() if f.GetReference() != rfp.GetReference()]
    try:
        for radius in (3.0, 4.0, 5.2, 6.6, 8.2, 10.0):
            for k in range(24):
                ang = 2 * math.pi * k / 24
                centre = (near[0] + radius * math.cos(ang), near[1] + radius * math.sin(ang))
                for rot in (0.0, 90.0, 180.0, 270.0):
                    rfp.SetPosition(vec(*centre))
                    rfp.SetOrientationDegrees(rot)
                    box = courtyard_box(rfp)
                    if not (model.inside(box[0], box[1], 0.0) and model.inside(box[2], box[3], 0.0)):
                        continue
                    if any(boxes_overlap(box, ob, 0.05) for ob in others):
                        continue
                    if not (pad_clear(model, rp, netp) and pad_clear(model, rn, netn)):
                        continue
                    vp, vn = pad_xy(rp), pad_xy(rn)
                    stubs = []
                    ok = True
                    for src, dst, net in ((pad_xy(ic_p), vp, netp), (pad_xy(ic_n), vn, netn)):
                        options = ([src, dst], [src, (dst[0], src[1]), dst], [src, (src[0], dst[1]), dst])
                        chosen = next((p for p in options if model.poly_ok(p, F, (net,))), None)
                        if chosen is None:
                            ok = False
                            break
                        stubs.append(chosen)
                    if not ok or poly_gap(stubs[0], stubs[1]) < TRACK + CLEAR + SLACK:
                        continue
                    draw_poly(board, model, stubs[0], F, rp.GetNet())
                    draw_poly(board, model, stubs[1], F, rn.GetNet())
                    return True
        rfp.SetPosition(pos0)
        rfp.SetOrientationDegrees(rot0)
        return False
    except Exception:
        rfp.SetPosition(pos0)
        rfp.SetOrientationDegrees(rot0)
        raise


def ground_near(model, board, gnd, x, y):
    for r in (0.7, 0.9, 1.2, 1.5, 1.9):
        for k in range(16):
            a = k * math.pi / 8
            gx, gy = x + r * math.cos(a), y + r * math.sin(a)
            if model.via_ok(gx, gy, gnd.GetNetCode()):
                draw_via(board, model, gx, gy, gnd)
                return 1
    return 0


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
    z.thisown = 0
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


def pick(pads, prefix):
    return next(p for p in pads if p.GetParentFootprint().GetReference().startswith(prefix))


def cmd_lvds(path, pairs=LVDS):
    """Coupled pairs on SIG_L6: CMC to driver or receiver (and on to the terminator),
    and RJ45 pins to CMC and TVS on the jack side."""
    board = pcbnew.LoadBoard(str(path))
    if board.GetCopperLayerCount() != 8:
        sys.exit("run stackup first")
    names = {f"{p}_{s}" for p in pairs for s in ("P", "N", "PJ", "NJ")}
    print(f"rip up {delete(board, [t for t in board.GetTracks() if t.GetNetname() in names])} items "
          f"of {len(pairs)} pairs", flush=True)
    model = Model(board)
    pads = pads_by_net(board)
    gnd = board.FindNet("GND")

    def span(pair):
        a = pad_xy(pick(pads[f"{pair}_P"], "FL"))
        b = pad_xy(pick(pads[f"{pair}_P"], "U"))
        return math.dist(a, b)

    pairs = sorted(pairs, key=span)
    failed = []
    for pair in pairs:
        netp, netn = board.FindNet(f"{pair}_P"), board.FindNet(f"{pair}_N")
        codes = (netp.GetNetCode(), netn.GetNetCode())
        pp, pn = pads[f"{pair}_P"], pads[f"{pair}_N"]
        cmc = smd_pair_ends(model, pick(pp, "FL"), pick(pn, "FL"), *codes)
        ic_p, ic_n = pick(pp, "U"), pick(pn, "U")
        rterm = [p for p in pp if p.GetParentFootprint().GetReference().startswith("R_")]
        chain = [cmc, smd_pair_ends(model, ic_p, ic_n, *codes)]
        legs = route_chain(model, codes, chain)
        if legs is None:
            print(f"  {pair}: driver/receiver side NOT ROUTED ({len(chain[0])}/{len(chain[1])} ends)", flush=True)
            failed.append(pair)
        else:
            for leg in legs:
                draw_route(board, model, leg, netp, netn)
            for e in {id(x): x for leg in legs for x in (leg.start, leg.end)}.values():
                if e.new_vias:
                    ground_near(model, board, gnd, *e.mid)
            parked = ""
            if rterm:
                parked = " +R" if connect_terminator(
                    board, model, rterm[0].GetParentFootprint(), ic_p, ic_n, *codes
                ) else " R-unplaced"
            lens = [poly_len(leg.p) for leg in legs], [poly_len(leg.n) for leg in legs]
            print(f"  {pair}: {len(legs)} legs, P {sum(lens[0]):.1f} N {sum(lens[1]):.1f} mm{parked}", flush=True)
        save(board, path)

        jp, jn = board.FindNet(f"{pair}_PJ"), board.FindNet(f"{pair}_NJ")
        jcodes = (jp.GetNetCode(), jn.GetNetCode())
        qp, qn = pads[f"{pair}_PJ"], pads[f"{pair}_NJ"]
        pin_p, pin_n = pick(qp, "J"), pick(qn, "J")
        jack = [e for layer in (L6, L3) for e in pin_pair_ends(model, pin_p, pin_n, *jcodes, layer=layer)]
        if not jack:
            jack = gather_jack(model, pin_p, pin_n, *jcodes)
        cmcj = smd_pair_ends(model, pick(qp, "FL"), pick(qn, "FL"), *jcodes)
        tvs = smd_pair_ends(model, pick(qp, "DT"), pick(qn, "DT"), *jcodes)
        # Visit the CMC and the TVS in the order they sit below the jack.
        mids = sorted(((pad_xy(pick(qp, "FL"))[1], cmcj), (pad_xy(pick(qp, "DT"))[1], tvs)), key=lambda t: t[0])
        legs = route_chain(model, jcodes, [jack, mids[0][1]], budget=90)
        if legs is None and jack and jack[0].label != "gathered":
            legs = route_chain(model, jcodes, [gather_jack(model, pin_p, pin_n, *jcodes), mids[0][1]], budget=90)
        if legs is None:
            print(f"  {pair}: jack side NOT ROUTED ({len(jack)}/{len(cmcj)}/{len(tvs)} ends)", flush=True)
            failed.append(pair + "J")
        else:
            for leg in legs:
                draw_route(board, model, leg, jp, jn)
            # The second part leaves the node just reached and runs on to the remaining one.
            landed = legs[-1].end
            nxt = mids[1][1]
            more = route_chain(model, jcodes, [[landed], nxt], budget=60)
            if more:
                for leg in more:
                    leg.start.drawn = True
                    draw_route(board, model, leg, jp, jn)
                legs = legs + more
            for e in {id(x): x for leg in legs for x in (leg.start, leg.end)}.values():
                if e.new_vias:
                    ground_near(model, board, gnd, *e.mid)
            print(f"  {pair}J: P {sum(poly_len(l.p) for l in legs):.1f} N {sum(poly_len(l.n) for l in legs):.1f} mm",
                  flush=True)
        save(board, path)
    fill_zones(board)
    save(board, path)
    print(f"not routed: {' '.join(failed) if failed else 'none'}", flush=True)


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
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                layers = ALL
            else:
                layers = frozenset(l for l in (F, B) if pad.IsOnLayer(l))
            items.append(("pad", pad_xy(pad), layers, pad_shape(pad, F if F in layers else B), pad))
    uf = UF(len(items))

    def anchors(it):
        return list(it[1]) if it[0] == "seg" else [it[1]]

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            if not (a[2] & b[2]):
                continue
            if any(shape_dist(b[3], x, y) <= 0.002 for x, y in anchors(a)) or any(
                shape_dist(a[3], x, y) <= 0.002 for x, y in anchors(b)
            ):
                uf.union(i, j)
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[uf.find(i)].append(it)
    return list(groups.values())


def terminals(model, island, code):
    """Points where inner-layer copper can join the island: its vias and THT pads,
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
            for r in (0.45, 0.8, 1.2, 1.8, 2.6, 3.6, 5.0, 7.0, 9.0):
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

                def snaps(p):
                    """Free cells a straight stub away from a terminal whose own cell is walled in."""
                    base = cell_of(p)
                    found = []
                    for rad in range(0, 16):
                        for dy in range(-rad, rad + 1):
                            for dx in range(-rad, rad + 1):
                                if max(abs(dx), abs(dy)) != rad:
                                    continue
                                i, j = base[0] + dx, base[1] + dy
                                if not (0 <= i < free.shape[1] and 0 <= j < free.shape[0]) or not free[j, i]:
                                    continue
                                xy = xy_of((i, j))
                                if rad and not model.seg_ok(p[0], p[1], xy[0], xy[1], layer, (code,), HALF, extra):
                                    continue
                                found.append((i, j))
                                if len(found) >= 4:
                                    return found
                    return found

                starts, start_of = [], {}
                for p, via in ta:
                    for cell in snaps(p):
                        starts.append((*cell, None))
                        start_of.setdefault(cell, (p, via))
                goals = {}
                for p, via in tb:
                    for cell in snaps(p):
                        goals.setdefault(cell, (p, via))
                path = astar(free, starts, list(goals))
                if path is None:
                    continue
                a = start_of[path[0]]
                b = goals[path[-1]]
                pts = simplify([a[0]] + pull(free, [xy_of(c) for c in path]) + [b[0]])
                if not model.poly_ok(pts, layer, (code,), HALF, extra):
                    continue
                if any(via is not None and not (model.via_ok(*p, code) and model.seg_ok(*via[1], *p, via[0], (code,)))
                       for p, via in (a, b)):
                    continue
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
def hole_clashes(board):
    """Vias whose drill sits on or next to a THT hole."""
    holes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                x, y = pad_xy(pad)
                holes.append((x, y, max(mm(pad.GetDrillSize().x), mm(pad.GetDrillSize().y)) / 2, pad.GetNetCode(), pad))
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
    """A same-net via next to a THT hole is redundant: its tracks move onto the pad."""
    kill = []
    for v, pad, same in hole_clashes(board):
        if not same:
            print(f"  via {v.GetNetname()} clashes with a foreign hole, left for DRC", flush=True)
            continue
        vp, pp = v.GetPosition(), pad.GetPosition()
        r = v.GetWidth(F) // 2
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != v.GetNetCode():
                continue
            if (t.GetStart() - vp).EuclideanNorm() <= r:
                t.SetStart(pp)
            if (t.GetEnd() - vp).EuclideanNorm() <= r:
                t.SetEnd(pp)
        kill.append(v)
    return delete(board, kill)


def stitch_fence(board, model, gnd, pitch=1.5, inset=0.8):
    code = gnd.GetNetCode()
    existing = [(mm(t.GetPosition().x), mm(t.GetPosition().y)) for t in board.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetCode() == code]
    x0, y0, x1, y1 = model.ex0 + inset, model.ey0 + inset, model.ex1 - inset, model.ey1 - inset
    pts = []
    for x, y, dx, dy, length in ((x0, y0, 1, 0, x1 - x0), (x1, y0, 0, 1, y1 - y0),
                                 (x1, y1, -1, 0, x1 - x0), (x0, y1, 0, -1, y1 - y0)):
        for k in range(int(length // pitch)):
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
    """Give each unconnected pour island on the outer layers a ground via."""
    code = gnd.GetNetCode()
    vias = [(mm(t.GetPosition().x), mm(t.GetPosition().y)) for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetCode() == code]
    gpads = [pad for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetNetCode() == code]
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
            if any(pad.IsOnLayer(layer) and in_poly(*pad_xy(pad), pts) for pad in gpads):
                continue
            gx = min(xs)
            while gx <= max(xs):
                gy = min(ys)
                hit = False
                while gy <= max(ys):
                    if in_poly(gx, gy, pts) and poly_dist(gx, gy, pts) > VIA_R + 0.05 and model.via_ok(gx, gy, code):
                        draw_via(board, model, gx, gy, gnd)
                        vias.append((gx, gy))
                        added += 1
                        hit = True
                        break
                    gy += 0.3
                if hit:
                    break
                gx += 0.3
    return added


def remove_dangling(board, path, rounds=8):
    removed = 0
    for _ in range(rounds):
        rep = drc(path, "all")
        ids = {it["uuid"] for v in rep.get("violations") or [] if v["type"] in ("track_dangling", "via_dangling")
               for it in v["items"] if it.get("uuid")}
        if not ids:
            break
        removed += delete(board, [t for t in board.GetTracks() if t.m_Uuid.AsString() in ids])
        fill_zones(board)
        save(board, path)
    return removed


def cmd_stitch(path):
    board = pcbnew.LoadBoard(str(path))
    print(f"vias on a same-net THT hole removed: {fix_hole_clashes(board)}", flush=True)
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.SetMinThickness(iu(0.2))
    fill_zones(board)
    model = Model(board)
    gnd = board.FindNet("GND")
    added, total = stitch_fence(board, model, gnd)
    print(f"edge fence: {added} ground vias added for {total} sites at 1.5 mm", flush=True)
    fill_zones(board)
    print(f"pour islands stitched: {stitch_islands(board, model, gnd)} vias", flush=True)
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    fill_zones(board)
    save(board, path)
    print(f"dangling copper removed: {remove_dangling(board, path)}", flush=True)
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

    def link(a, b, w=None):
        if w is None:
            w = math.hypot(b[0] - a[0], b[1] - a[1])
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
    coords = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if pad.GetNetname() != name:
                continue
            s = pad_shape(pad, F if pad.IsOnLayer(F) else B)
            px, py = pad_xy(pad)
            node = ("pad", ref, pad.GetNumber())
            coords[node] = (px, py)
            for p in pts:
                if shape_dist(s, p[0], p[1]) <= 0.08:
                    link(node, p, math.hypot(p[0] - px, p[1] - py))
            if src is None and is_src(ref):
                src = node
            elif dst is None and is_dst(ref):
                dst = node
    if not src or not dst:
        return None
    dist, prev, cnt = {src: 0.0}, {}, 0
    pq = [(0.0, cnt, src)]
    while pq:
        d, _, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in g[u]:
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                prev[v] = u
                cnt += 1
                heapq.heappush(pq, (d + w, cnt, v))
    if dst not in dist:
        return None
    seq = [dst]
    while seq[-1] != src:
        seq.append(prev[seq[-1]])
    seq.reverse()
    return [coords.get(n, n) for n in seq], dist[dst]


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
    for pair in sorted(LVDS, key=lambda s: (s.rstrip("0123456789") != "SCK", s.rstrip("0123456789") != "WS", s)):
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


def cmd_repair(path):
    """Route only the pair sides that are still open. Already drawn pairs stay."""
    board = pcbnew.LoadBoard(str(path))
    model = Model(board)
    pads = pads_by_net(board)
    gnd = board.FindNet("GND")
    for pair in LVDS:
        netp, netn = board.FindNet(f"{pair}_P"), board.FindNet(f"{pair}_N")
        codes = (netp.GetNetCode(), netn.GetNetCode())
        pp, pn = pads[f"{pair}_P"], pads[f"{pair}_N"]
        if shortest_path(board, f"{pair}_P", is_cmc, is_ic) is None:
            cmc = smd_pair_ends(model, pick(pp, "FL"), pick(pn, "FL"), *codes)
            ic_p, ic_n = pick(pp, "U"), pick(pn, "U")
            ic = smd_pair_ends(model, ic_p, ic_n, *codes)
            legs = route_chain(model, codes, [cmc, ic], budget=90)
            if legs is None:
                print(f"  {pair}: driver/receiver still open", flush=True)
            else:
                for leg in legs:
                    draw_route(board, model, leg, netp, netn)
                for e in {id(x): x for leg in legs for x in (leg.start, leg.end)}.values():
                    if e.new_vias:
                        ground_near(model, board, gnd, *e.mid)
                rterm = [p for p in pp if p.GetParentFootprint().GetReference().startswith("R_")]
                parked = ""
                if rterm:
                    parked = " +R" if connect_terminator(
                        board, model, rterm[0].GetParentFootprint(), ic_p, ic_n, *codes
                    ) else " R-unplaced"
                print(f"  {pair}: repaired P {sum(poly_len(l.p) for l in legs):.1f} "
                      f"N {sum(poly_len(l.n) for l in legs):.1f} mm{parked}", flush=True)
                save(board, path)
        if shortest_path(board, f"{pair}_PJ", is_cmc, is_jack) is None:
            jp, jn = board.FindNet(f"{pair}_PJ"), board.FindNet(f"{pair}_NJ")
            jcodes = (jp.GetNetCode(), jn.GetNetCode())
            qp, qn = pads[f"{pair}_PJ"], pads[f"{pair}_NJ"]
            pin_p, pin_n = pick(qp, "J"), pick(qn, "J")
            jack = [e for layer in (L6, L3) for e in pin_pair_ends(model, pin_p, pin_n, *jcodes, layer=layer)]
            if not jack:
                jack = gather_jack(model, pin_p, pin_n, *jcodes)
            cmcj = smd_pair_ends(model, pick(qp, "FL"), pick(qn, "FL"), *jcodes)
            tvs = smd_pair_ends(model, pick(qp, "DT"), pick(qn, "DT"), *jcodes)
            mids = sorted(((pad_xy(pick(qp, "FL"))[1], cmcj), (pad_xy(pick(qp, "DT"))[1], tvs)), key=lambda t: t[0])
            legs = route_chain(model, jcodes, [jack, mids[0][1], mids[1][1]], budget=90)
            if legs is None:
                print(f"  {pair}J: jack side still open ({len(jack)} gathered/pin ends)", flush=True)
            else:
                for leg in legs:
                    draw_route(board, model, leg, jp, jn)
                print(f"  {pair}J: repaired P {sum(poly_len(l.p) for l in legs):.1f} "
                      f"N {sum(poly_len(l.n) for l in legs):.1f} mm", flush=True)
                save(board, path)
    fill_zones(board)
    save(board, path)


def main(argv):
    cmds = {"stackup": cmd_stackup, "lvds": cmd_lvds, "repair": cmd_repair, "opens": cmd_opens,
            "stitch": cmd_stitch, "report": cmd_report}
    if len(argv) < 2 or argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[argv[1]](Path(argv[2]) if len(argv) > 2 else BOARD)


if __name__ == "__main__":
    main(sys.argv)
