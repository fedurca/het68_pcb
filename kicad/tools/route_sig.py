"""Grid router for het68 signal nets.

One cell is 0.25 mm. A track centre may sit on its own net or on empty
board, never inside another net's clearance. SMT pads get a short stub
away from the package before the net is allowed to turn.
"""
from __future__ import annotations

import heapq
import math

import pcbnew

from route6 import add_via

G = 0.25
TRACK = 0.20
CLEAR = 0.22
FINE = 0.12


def _mm(v):
    return pcbnew.ToMM(v)


class Router:
    def __init__(self, board):
        self.board = board
        self.w = board.w
        self.h = board.h
        self.nx = int(self.w / G) + 3
        self.ny = int(self.h / G) + 3
        self.grid = [0] * (self.nx * self.ny)
        self.grid_b = [0] * (self.nx * self.ny)
        self.ids = {}
        self.nxt = 1
        self.via_d = getattr(board, "via_d", 0.6)
        self.via_drill = getattr(board, "via_drill", 0.2)
        self.pads = []

    def nid(self, net):
        if net not in self.ids:
            self.ids[net] = self.nxt
            self.nxt += 1
        return self.ids[net]

    def idx(self, ix, iy):
        return iy * self.nx + ix

    def cell(self, x, y):
        return int(round(x / G)), int(round(y / G))

    def paint(self, x, y, hw, hh, val, overwrite=False, layers="both"):
        ix0 = max(1, int((x - hw) / G))
        ix1 = min(self.nx - 2, int((x + hw) / G))
        iy0 = max(1, int((y - hh) / G))
        iy1 = min(self.ny - 2, int((y + hh) / G))
        grids = []
        if layers in ("both", "f"):
            grids.append(self.grid)
        if layers in ("both", "b"):
            grids.append(self.grid_b)
        for grid in grids:
            for iy in range(iy0, iy1 + 1):
                row = iy * self.nx
                for ix in range(ix0, ix1 + 1):
                    i = row + ix
                    if overwrite or grid[i] == 0:
                        grid[i] = val

    def load(self):
        for fp in self.board.b.GetFootprints():
            c = fp.GetPosition()
            cx, cy = _mm(c.x), _mm(c.y)
            for pad in fp.Pads():
                try:
                    if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                        bb = pad.GetBoundingBox()
                        x = _mm(bb.GetX()) + _mm(bb.GetWidth()) / 2
                        y = _mm(bb.GetY()) + _mm(bb.GetHeight()) / 2
                        r = max(_mm(bb.GetWidth()), _mm(bb.GetHeight())) / 2 + TRACK / 2 + 0.25
                        self.paint(x, y, r, r, 65535)
                        continue
                except Exception:
                    pass
                net = pad.GetNetname() or ""
                if net.startswith("unconnected"):
                    net = ""
                bb = pad.GetBoundingBox()
                hw = _mm(bb.GetWidth()) / 2
                hh = _mm(bb.GetHeight()) / 2
                if hw < 0.04 or hh < 0.04:
                    continue
                x = _mm(bb.GetX()) + hw
                y = _mm(bb.GetY()) + hh
                smd = True
                try:
                    smd = pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH
                except Exception:
                    pass
                val = 65535 if not net else self.nid(net)
                fine = min(hw, hh) <= 0.16
                gap = 0.14 if fine else TRACK / 2 + 0.25
                self.paint(x, y, hw + gap, hh + gap, val, layers="f" if smd else "both")
                self.pads.append({
                    "net": net, "x": x, "y": y, "hw": hw, "hh": hh,
                    "cx": cx, "cy": cy, "smd": smd, "id": val, "ref": fp.GetReference(),
                })
        for p in self.pads:
            if p["id"] == 65535:
                continue
            self.paint(
                p["x"], p["y"], max(p["hw"] - 0.02, 0.05), max(p["hh"] - 0.02, 0.05),
                p["id"], overwrite=True, layers="f" if p["smd"] else "both",
            )
        for t in self.board.b.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            pos = t.GetPosition()
            net = t.GetNetname()
            val = self.nid(net) if net in self.board.nets else 65535
            r = _mm(t.GetWidth(pcbnew.F_Cu)) / 2 + TRACK / 2 + 0.25
            self.paint(_mm(pos.x), _mm(pos.y), r, r, val)

    def _ok_cell(self, ix, iy, own, back=False):
        if not (1 <= ix < self.nx - 1 and 1 <= iy < self.ny - 1):
            return False
        grid = self.grid_b if back else self.grid
        v = grid[self.idx(ix, iy)]
        return v == 0 or v == own

    def _mark_seg(self, x1, y1, x2, y2, own, width, back=False):
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / (G * 0.5)))
        rad = width / 2 + 0.25
        layer = "b" if back else "f"
        for i in range(steps + 1):
            t = i / steps
            self.paint(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, rad, rad, own, layers=layer)

    def add_track(self, x1, y1, x2, y2, net, width, own, back=False):
        if abs(x1 - x2) < 0.02 and abs(y1 - y2) < 0.02:
            return
        if net not in self.board.nets:
            return
        t = pcbnew.PCB_TRACK(self.board.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
        t.SetNet(self.board.nets[net])
        self.board.b.Add(t)
        self._mark_seg(x1, y1, x2, y2, own, width, back)

    def stub(self, pad):
        if not pad["smd"] or pad["net"] not in self.board.nets:
            return pad["x"], pad["y"]
        dx, dy = pad["x"] - pad["cx"], pad["y"] - pad["cy"]
        dirs = []
        # Gullwing: leave along the long axis, away from the body, so
        # neighbouring pins stub in parallel and do not cross.
        if pad["hw"] >= pad["hh"]:
            dirs.append((-1 if dx <= 0 else 1, 0))
        else:
            dirs.append((0, -1 if dy <= 0 else 1))
        if str(pad.get("ref", "")).startswith("J") and not str(pad.get("ref", "")).startswith("J_"):
            dirs.insert(0, (0, 1))
        dirs += [(1, 0), (-1, 0), (0, 1), (0, -1)]
        fine = min(pad["hw"], pad["hh"]) <= 0.16
        width = FINE if fine else TRACK
        reach = max(pad["hw"], pad["hh"]) + (1.15 if fine else 0.9)
        own = pad["id"]
        for ux, uy in dirs:
            n = math.hypot(ux, uy) or 1.0
            tx = min(max(pad["x"] + ux / n * reach, 0.8), self.w - 0.8)
            ty = min(max(pad["y"] + uy / n * reach, 0.8), self.h - 0.8)
            if self._segment_free(pad["x"], pad["y"], tx, ty, own):
                self.add_track(pad["x"], pad["y"], tx, ty, pad["net"], width, own)
                return tx, ty
        return pad["x"], pad["y"]

    def _segment_free(self, x1, y1, x2, y2, own, back=False):
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / (G * 0.5)))
        for i in range(steps + 1):
            t = i / steps
            if not self._ok_cell(*self.cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t), own, back):
                return False
        return True

    def _draw_poly(self, pts, net, own, back=False):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if not self._segment_free(x1, y1, x2, y2, own, back):
                return False
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.add_track(x1, y1, x2, y2, net, TRACK, own, back)
        return True

    def connect(self, ax, ay, bx, by, net, own):
        if math.hypot(ax - bx, ay - by) < G:
            return True
        options = [
            [(ax, ay), (bx, ay), (bx, by)],
            [(ax, ay), (ax, by), (bx, by)],
        ]
        for off in (2, -2, 4, -4, 8, -8):
            options.append([(ax, ay), (bx + off, ay), (bx + off, by), (bx, by)])
            options.append([(ax, ay), (ax, by + off), (bx, by + off), (bx, by)])
        for back in (False, True):
            if back and not (self._via_at(ax, ay, net, own) and self._via_at(bx, by, net, own)):
                continue
            for pts in options:
                if self._draw_poly(pts, net, own, back):
                    return True
        if self._astar(ax, ay, bx, by, net, own, False):
            return True
        if self._via_at(ax, ay, net, own) and self._via_at(bx, by, net, own):
            return self._astar(ax, ay, bx, by, net, own, True)
        return False

    def _via_at(self, x, y, net, own):
        ix, iy = self.cell(x, y)
        if not (self._ok_cell(ix, iy, own, False) and self._ok_cell(ix, iy, own, True)):
            return False
        r = self.via_d / 2 + TRACK / 2 + 0.25
        # refuse if the via disc would cover another net on either layer
        ix0 = max(1, int((x - r) / G))
        ix1 = min(self.nx - 2, int((x + r) / G))
        iy0 = max(1, int((y - r) / G))
        iy1 = min(self.ny - 2, int((y + r) / G))
        for iy_ in range(iy0, iy1 + 1):
            for ix_ in range(ix0, ix1 + 1):
                for grid in (self.grid, self.grid_b):
                    v = grid[self.idx(ix_, iy_)]
                    if v not in (0, own):
                        return False
        if not add_via(self.board, x, y, net, self.via_d, self.via_drill):
            return False
        self.paint(x, y, r, r, own, overwrite=True)
        return True

    def _astar(self, ax, ay, bx, by, net, own, back=False):
        sx, sy = self.cell(ax, ay)
        tx, ty = self.cell(bx, by)
        heap = [(0, 0, sx, sy)]
        prev = {}
        seen = set()
        expands = 0
        found = None
        while heap:
            _f, cost, ix, iy = heapq.heappop(heap)
            if (ix, iy) in seen:
                continue
            seen.add((ix, iy))
            if abs(ix - tx) + abs(iy - ty) <= 1:
                found = (ix, iy)
                break
            expands += 1
            if expands > 40000:
                return False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if (jx, jy) in seen or not self._ok_cell(jx, jy, own, back):
                    continue
                step = cost + 1
                h = abs(jx - tx) + abs(jy - ty)
                prev[(jx, jy)] = (ix, iy)
                heapq.heappush(heap, (step + h, step, jx, jy))
        if found is None:
            return False
        path = [found]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        pts = [(ax, ay)]
        for ix, iy in path:
            pts.append((ix * G, iy * G))
        pts.append((bx, by))
        slim = [pts[0]]
        for p in pts[1:]:
            if len(slim) >= 2:
                a, b = slim[-2], slim[-1]
                col_x = abs(a[0] - b[0]) < 0.05 and abs(b[0] - p[0]) < 0.05
                col_y = abs(a[1] - b[1]) < 0.05 and abs(b[1] - p[1]) < 0.05
                if col_x or col_y:
                    slim[-1] = p
                    continue
            slim.append(p)
        return self._draw_poly(slim, net, own, back)

    def fanout_gnd(self):
        own = self.ids.get("GND")
        if not own:
            return 0
        n = 0
        for p in self.pads:
            if p["net"] != "GND" or not p["smd"]:
                continue
            dx, dy = p["x"] - p["cx"], p["y"] - p["cy"]
            norm = math.hypot(dx, dy) or 1.0
            dirs = [(dx / norm, dy / norm), (1, 0), (-1, 0), (0, 1), (0, -1)]
            for ux, uy in dirs:
                vx = p["x"] + ux * 1.2
                vy = p["y"] + uy * 1.2
                ix, iy = self.cell(vx, vy)
                if not self._ok_cell(ix, iy, own):
                    continue
                if not self._segment_cells_ok(p["x"], p["y"], vx, vy, own):
                    continue
                if add_via(self.board, vx, vy, "GND", self.via_d, self.via_drill):
                    self.add_track(p["x"], p["y"], vx, vy, "GND", TRACK, own)
                    self.paint(vx, vy, self.via_d / 2 + TRACK / 2 + 0.25, self.via_d / 2 + TRACK / 2 + 0.25, own, overwrite=True)
                    n += 1
                    break
        return n

    def _segment_cells_ok(self, x1, y1, x2, y2, own):
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / G))
        for i in range(steps + 1):
            t = i / steps
            if not self._ok_cell(*self.cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t), own):
                return False
        return True


def _mst(points):
    if len(points) < 2:
        return []
    used = {0}
    edges = []
    while len(used) < len(points):
        best = None
        for i in used:
            ax, ay = points[i]
            for j, (bx, by) in enumerate(points):
                if j in used:
                    continue
                d = abs(ax - bx) + abs(ay - by)
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            break
        _d, i, j = best
        used.add(j)
        edges.append((i, j))
    return edges


def route_signals(board) -> list:
    rt = Router(board)
    rt.load()
    groups = {}
    for p in rt.pads:
        if not p["net"] or p["net"] == "GND" or p["id"] == 65535:
            continue
        groups.setdefault(p["net"], []).append(p)
    missing = []
    def _rank(n):
        if n.endswith(("_PJ", "_NJ")):
            band = 1
        elif n.endswith(("_P", "_N", "_3V3")):
            band = 0
        else:
            band = 2
        return (band, len(groups[n]), n)
    names = sorted(groups, key=_rank)
    for i, net in enumerate(names):
        pts = [rt.stub(p) for p in groups[net]]
        if len(pts) < 2:
            continue
        if i % 15 == 0:
            print(f"  {board.name} {i}/{len(names)} {net} ({len(pts)})", flush=True)
        own = rt.nid(net)
        bad = False
        for a, b in _mst(pts):
            if not rt.connect(pts[a][0], pts[a][1], pts[b][0], pts[b][1], net, own):
                bad = True
        if bad:
            missing.append(net)
            print(f"  open {net}", flush=True)
    print(f"  {board.name} GND fanout {rt.fanout_gnd()}", flush=True)
    print(f"  {board.name} open {len(missing)}", flush=True)
    return missing
