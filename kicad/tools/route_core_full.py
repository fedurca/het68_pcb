"""Route het68-core on 6 layers with JLCPCB 0.15 mm drills.

The 0.60 mm via does not fit a 0.40 mm QFN pitch, and the old L4 split put
+5V_ALWAYS under the RP2350, so a 3.3 V through-via never met its plane.
This pass:

- replaces L4 with one +3V3_DIG pour (5 V and 1.8 V stay on tracks)
- fans the QFN out on two staggered rows of 0.35/0.15 vias
- routes every other net on L3, then on the outer layers if L3 is blocked

JLCPCB multilayer minimum is 0.15 mm hole / 0.25 mm pad. 0.35/0.15 leaves a
0.10 mm annular ring. A 0.15 mm hole is a paid via option on the quote.
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict, deque
from heapq import heappop, heappush

import numpy as np
import pcbnew

G = 0.10
# 0.30 mm pad / 0.15 mm drill: annular ring 0.075 mm, which is JLCPCB's
# preferred "diameter 0.15 mm larger than the hole". A 0.35 mm pad's
# keepout walled off the second escape row.
VIA_D = 0.30
VIA_R = VIA_D / 2
VIA_DRILL = 0.15
# Netclass clearance. 0.15 mm is above JLCPCB's 0.09 mm 6-layer minimum
# and still lets a 0.35 mm via sit on a 0.40 mm QFN escape.
CLEAR = 0.15
# A via centre must clear foreign copper by the worse of the pad rule and
# the hole rule (0.20 mm from the hole wall).
VIA_GAP = max(VIA_R + CLEAR, VIA_DRILL / 2 + 0.20) + 0.01
TRACK = 0.15
# Extra reach past a copper edge so a new TRACK-wide trace still clears it.
WALK_EXTRA = TRACK / 2 + CLEAR
PLANE = {"GND", "+3V3_DIG"}
# One width. A wider 5 V trace was centred on cells that only guaranteed
# clearance for 0.15 mm copper, so it closed to 0.10 mm. 0.15 mm on 1 oz
# carries the Heltec and the LDO input.
WIDE = {}
MOVES = {
    "L_VREG": (89.0, 48.0),
    "C_DVDD": (96.0, 48.0),
    "C18A": (63.5, 74.0),
    "C18B": (68.0, 74.0),
    "C_ADX": (86.5, 74.5),
}


def mm(v):
    return pcbnew.ToMM(v)


class Router:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0 = mm(bb.GetX())
        self.y0 = mm(bb.GetY())
        self.x1 = self.x0 + mm(bb.GetWidth())
        self.y1 = self.y0 + mm(bb.GetHeight())
        self.nx = int(round(self.x1 / G)) + 6
        self.ny = int(round(self.y1 / G)) + 6
        self.walk = np.zeros((3, self.ny, self.nx), dtype=np.int16)
        self.vgrid = np.zeros((3, self.ny, self.nx), dtype=np.int16)
        self.vias = []
        self.segs = []
        self.blocks = []
        self.anchors = []
        self.parent = []
        self.added = 0
        self.layers = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
        self.fps = list(board.GetFootprints())
        self.tracks = list(board.GetTracks())

    def cell(self, x, y):
        return int(round(x / G)), int(round(y / G))

    def xy(self, ix, iy):
        return ix * G, iy * G

    def inside(self, ix, iy):
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    def _paint(self, grid, layer, ix, iy, code, force=False):
        if not self.inside(ix, iy):
            return
        cur = int(grid[layer, iy, ix])
        if force:
            grid[layer, iy, ix] = code
            return
        if cur == -1:
            return
        if cur == 0 or cur == code:
            grid[layer, iy, ix] = code
        else:
            grid[layer, iy, ix] = -1

    def _disk(self, grid, layer, x, y, rad, code, force=False):
        rcell = int(rad / G) + 1
        ix, iy = self.cell(x, y)
        rad2 = rad * rad
        for dy in range(-rcell, rcell + 1):
            for dx in range(-rcell, rcell + 1):
                if (dx * G) * (dx * G) + (dy * G) * (dy * G) <= rad2 + 1e-9:
                    self._paint(grid, layer, ix + dx, iy + dy, code, force)

    def _rect(self, grid, layer, cx, cy, hx, hy, ang_deg, code, force=False):
        ang = math.radians(ang_deg)
        c, s = math.cos(ang), math.sin(ang)
        reach = math.hypot(hx, hy) + G
        ix0, iy0 = self.cell(cx - reach, cy - reach)
        ix1, iy1 = self.cell(cx + reach, cy + reach)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                x, y = self.xy(ix, iy)
                dx, dy = x - cx, y - cy
                lx = dx * c + dy * s
                ly = -dx * s + dy * c
                if abs(lx) <= hx and abs(ly) <= hy:
                    self._paint(grid, layer, ix, iy, code, force)

    def _seg(self, grid, layer, x1, y1, x2, y2, rad, code):
        step = max(1, int(math.hypot(x2 - x1, y2 - y1) / (G * 0.5)))
        for i in range(step + 1):
            t = i / step
            self._disk(grid, layer, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, rad, code)

    def hard_edge(self):
        m = 0.40
        for iy in range(self.ny):
            y = iy * G
            for ix in range(self.nx):
                x = ix * G
                if x < self.x0 + m or y < self.y0 + m or x > self.x1 - m or y > self.y1 - m:
                    for layer in range(3):
                        self.walk[layer, iy, ix] = -1
                        self.vgrid[layer, iy, ix] = -1

    def stamp_pad(self, pad, code):
        if not (pad.IsOnLayer(pcbnew.F_Cu) or pad.IsOnLayer(pcbnew.B_Cu)):
            return
        layers = []
        if pad.IsOnLayer(pcbnew.F_Cu):
            layers.append(0)
        if pad.IsOnLayer(pcbnew.B_Cu):
            layers.append(2)
        attr = pad.GetAttribute()
        pth = attr == pcbnew.PAD_ATTRIB_PTH
        if pth:
            layers = [0, 1, 2]
        pos = pad.GetPosition()
        cx, cy = mm(pos.x), mm(pos.y)
        sz = pad.GetSize()
        hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
        ang = pad.GetOrientation().AsDegrees()
        if attr == pcbnew.PAD_ATTRIB_NPTH:
            rad = max(hx, hy) + 0.45
            for layer in range(3):
                self._disk(self.walk, layer, cx, cy, rad, -1, force=True)
                self._disk(self.vgrid, layer, cx, cy, rad, -1, force=True)
            return
        for layer in layers:
            self._rect(self.walk, layer, cx, cy, hx + WALK_EXTRA, hy + WALK_EXTRA, ang, code)
            self._rect(self.vgrid, layer, cx, cy, hx + VIA_GAP, hy + VIA_GAP, ang, code)
            # The pad copper itself belongs to this net even if a halo collided.
            self._rect(self.walk, layer, cx, cy, hx, hy, ang, code, force=True)

    def stamp_keepouts(self, rects):
        """rects were captured before any board.Remove. KiCad 10 drops the
        Python type of zones once a track is deleted, so the geometry has
        to be copied first."""
        for x0, y0, x1, y1 in rects:
            ix0, iy0 = self.cell(x0, y0)
            ix1, iy1 = self.cell(x1, y1)
            for iy in range(iy0, iy1 + 1):
                for ix in range(ix0, ix1 + 1):
                    if not self.inside(ix, iy):
                        continue
                    x, y = self.xy(ix, iy)
                    if x0 <= x <= x1 and y0 <= y <= y1 and int(self.walk[0, iy, ix]) == 0:
                        self.walk[0, iy, ix] = -1
                        self.vgrid[0, iy, ix] = -1

    def new_id(self):
        i = len(self.parent)
        self.parent.append(i)
        return i

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def add_anchor(self, net, code, cells):
        aid = self.new_id()
        self.anchors.append({"id": aid, "net": net, "code": code, "cells": cells})
        return aid

    def via_ok(self, x, y, code):
        if not (self.x0 + 1.1 < x < self.x1 - 1.1 and self.y0 + 1.1 < y < self.y1 - 1.1):
            return False
        ix, iy = self.cell(x, y)
        if not self.inside(ix, iy):
            return False
        for layer in range(3):
            v = int(self.vgrid[layer, iy, ix])
            if v not in (0, code):
                return False
        for vx, vy, vcode in self.vias:
            d = math.hypot(vx - x, vy - y)
            need = 0.45 if vcode == code else (2 * VIA_R + CLEAR + 0.04)
            if d < need:
                return False
        return True

    def line_ok(self, x1, y1, x2, y2, code, layer):
        step = max(1, int(math.hypot(x2 - x1, y2 - y1) / (G * 0.45)))
        for i in range(step + 1):
            t = i / step
            ix, iy = self.cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if not self.inside(ix, iy):
                return False
            v = int(self.walk[layer, iy, ix])
            if v not in (0, code):
                return False
        return True

    def commit_via(self, x, y, code):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(VIA_D))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetNetCode(code)
        try:
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
        except Exception:
            pass
        self.b.Add(v)
        self.vias.append((x, y, code))
        for layer in range(3):
            self._disk(self.walk, layer, x, y, VIA_R + WALK_EXTRA, code)
            self._disk(self.vgrid, layer, x, y, VIA_R + VIA_GAP, code)
            ix, iy = self.cell(x, y)
            self._paint(self.walk, layer, ix, iy, code, force=True)
        self.added += 1
        ix, iy = self.cell(x, y)
        return [(0, ix, iy), (1, ix, iy), (2, ix, iy)]

    def commit_track(self, x1, y1, x2, y2, layer, code, width):
        if math.hypot(x2 - x1, y2 - y1) < 0.04:
            return
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(self.layers[layer])
        t.SetNetCode(code)
        self.b.Add(t)
        self.segs.append((x1, y1, x2, y2, layer, code, width))
        # Own half-width is already the copper. Add the other trace's half
        # so two tracks cannot be centred one cell apart.
        rad_w = width / 2 + CLEAR + TRACK / 2
        rad_v = width / 2 + VIA_GAP
        self._seg(self.walk, layer, x1, y1, x2, y2, rad_w, code)
        self._seg(self.vgrid, layer, x1, y1, x2, y2, rad_v, code)
        self.added += 1

    def collect_pads(self, keepouts):
        pads = []
        pending = []
        for fp in self.fps:
            fx, fy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
            for pad in fp.Pads():
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    self.stamp_pad(pad, -1)
                    pos = pad.GetPosition()
                    sz = pad.GetSize()
                    self.blocks.append({
                        "x": mm(pos.x), "y": mm(pos.y),
                        "sx": mm(sz.x), "sy": mm(sz.y),
                        "ang": 0.0, "code": -1, "npth": True,
                        "pth": True, "layer": 0, "both": True,
                    })
                    continue
                name = pad.GetNetname()
                on_cu = pad.IsOnLayer(pcbnew.F_Cu) or pad.IsOnLayer(pcbnew.B_Cu)
                if not on_cu:
                    continue
                # Unconnected QFN and connector pins are still copper.
                # Stamp them before signal pads so a signal pad can reclaim
                # its own copper afterwards.
                if not name or name.startswith("unconnected"):
                    self.stamp_pad(pad, -1)
                    pos = pad.GetPosition()
                    sz = pad.GetSize()
                    self.blocks.append({
                        "x": mm(pos.x), "y": mm(pos.y),
                        "sx": mm(sz.x), "sy": mm(sz.y),
                        "ang": pad.GetOrientation().AsDegrees(),
                        "code": -1,
                        "pth": pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                        "layer": 0 if pad.IsOnLayer(pcbnew.F_Cu) else 2,
                        "both": pad.IsOnLayer(pcbnew.F_Cu) and pad.IsOnLayer(pcbnew.B_Cu),
                    })
                    continue
                pending.append((fp, pad, fx, fy, name))
        for fp, pad, fx, fy, name in pending:
                code = pad.GetNetCode()
                self.stamp_pad(pad, code)
                pos = pad.GetPosition()
                sz = pad.GetSize()
                pads.append({
                    "fp": fp.GetReference(),
                    "num": pad.GetNumber(),
                    "net": name,
                    "code": code,
                    "x": mm(pos.x),
                    "y": mm(pos.y),
                    "sx": mm(sz.x),
                    "sy": mm(sz.y),
                    "ang": pad.GetOrientation().AsDegrees(),
                    "fx": fx,
                    "fy": fy,
                    "pth": pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                    "layer": 0 if pad.IsOnLayer(pcbnew.F_Cu) else 2,
                    "both": pad.IsOnLayer(pcbnew.F_Cu) and pad.IsOnLayer(pcbnew.B_Cu),
                })
        self.stamp_keepouts(keepouts)
        self._block_qfn_interior()
        return pads

    def _block_qfn_interior(self):
        """Keep F.Cu routes out from between the QFN pins.

        Escape tracks leave outward; the courtyard inside the pin row is
        only the exposed pad and its thermal vias.
        """
        x0, x1, y0, y1 = 75.6, 84.4, 53.6, 62.4
        ix0, iy0 = self.cell(x0, y0)
        ix1, iy1 = self.cell(x1, y1)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                if int(self.walk[0, iy, ix]) == 0:
                    self.walk[0, iy, ix] = -1
                    self.vgrid[0, iy, ix] = -1

    def register(self, pads):
        plane_id = {}
        for p in pads:
            if p["pth"] or p["both"]:
                ix, iy = self.cell(p["x"], p["y"])
                cells = [(0, ix, iy), (1, ix, iy), (2, ix, iy)]
            else:
                ix, iy = self.cell(p["x"], p["y"])
                cells = [(p["layer"], ix, iy)]
            p["aid"] = self.add_anchor(p["net"], p["code"], cells)
            if p["net"] in PLANE and (p["pth"] or p["both"]):
                pid = plane_id.get(p["net"])
                if pid is None:
                    plane_id[p["net"]] = p["aid"]
                else:
                    self.union(pid, p["aid"])
        self.plane_id = plane_id

    def join_plane(self, net, aid):
        pid = self.plane_id.get(net)
        if pid is None:
            self.plane_id[net] = aid
        else:
            self.union(pid, aid)

    def place_via_track(self, p, x, y):
        if not self.via_ok(x, y, p["code"]):
            return False
        layer = 0 if p["layer"] == 0 or p["both"] else p["layer"]
        if not self.line_ok(p["x"], p["y"], x, y, p["code"], layer):
            return False
        cells = self.commit_via(x, y, p["code"])
        self.commit_track(p["x"], p["y"], x, y, layer, p["code"], TRACK)
        aid = self.add_anchor(p["net"], p["code"], cells)
        self.union(aid, p["aid"])
        if p["net"] in PLANE:
            self.join_plane(p["net"], aid)
        return True

    def exit_free(self, x, y, ox, oy, code):
        """True when L3 just outside this via is not already walled in."""
        for dist in (0.8, 2.4):
            ix, iy = self.cell(x + ox * dist, y + oy * dist)
            if not self.inside(ix, iy):
                return False
            if int(self.walk[1, iy, ix]) not in (0, code):
                return False
        return True

    def _snap(self, x, y):
        return int(round(x / G)) * G, int(round(y / G)) * G

    def _poly_via(self, p, pts):
        """F.Cu polyline ending in a via. All-or-nothing."""
        layer = 0
        for a, b in zip(pts, pts[1:]):
            if not self.line_ok(a[0], a[1], b[0], b[1], p["code"], layer):
                return False
        ex, ey = pts[-1]
        if not self.via_ok(ex, ey, p["code"]):
            return False
        for a, b in zip(pts, pts[1:]):
            self.commit_track(a[0], a[1], b[0], b[1], layer, p["code"], TRACK)
        cells = self.commit_via(ex, ey, p["code"])
        aid = self.add_anchor(p["net"], p["code"], cells)
        self.union(aid, p["aid"])
        if p["net"] in PLANE:
            self.join_plane(p["net"], aid)
        return True

    def qfn_fanout(self, pads):
        """Spread each QFN row before the via.

        A via on every pin at the 0.40 mm pitch seals a ring: the keepouts
        touch and L3 cannot leave the pin. The outer pin turns aside first;
        the next pin runs further out, past that via, and only then turns.
        """
        u1 = [p for p in pads if p["fp"] == "U1" and not p["pth"]]
        sides = {"N": [], "S": [], "E": [], "W": []}
        for p in u1:
            if abs(p["x"] - 75.05) < 0.15 and 54 < p["y"] < 62:
                sides["W"].append(p)
            elif abs(p["x"] - 84.95) < 0.15 and 54 < p["y"] < 62:
                sides["E"].append(p)
            elif abs(p["y"] - 53.05) < 0.15 and 76 < p["x"] < 84:
                sides["N"].append(p)
            elif abs(p["y"] - 62.95) < 0.15 and 76 < p["x"] < 84:
                sides["S"].append(p)
        # out, along for the low-coordinate half, along for the high half
        spec = {
            "N": ((0, -1), (-1, 0), (1, 0), "x"),
            "S": ((0, 1), (-1, 0), (1, 0), "x"),
            "W": ((-1, 0), (0, -1), (0, 1), "y"),
            "E": ((1, 0), (0, -1), (0, 1), "y"),
        }
        n = 0
        for side, items in sides.items():
            ox, oy = spec[side][0]
            key = spec[side][3]
            items.sort(key=lambda p: p["x"] if key == "x" else p["y"])
            mid = len(items) // 2
            # Outside pin first, so its turn is already aside when the
            # next pin runs further out past it.
            halves = (
                (items[:mid], spec[side][1]),
                (list(reversed(items[mid:])), spec[side][2]),
            )
            for half, (ax, ay) in halves:
                for p in half:
                    placed = False
                    if p["net"] in PLANE:
                        # A via into the 3.3 V / GND plane needs no L3 escape.
                        spans = ((1.2, 1.8, 2.4), (0.0, 0.6, -0.6, 1.2, -1.2))
                        want_stub = False
                    else:
                        spans = ((2.4, 3.4, 4.4, 5.4, 6.4, 7.4), (0.0, 0.9, -0.9, 1.8, -1.8, 2.7, -2.7, 3.6, -3.6))
                        want_stub = True
                    for dist in spans[0]:
                        for lat in spans[1]:
                            x, y = self._snap(p["x"] + ox * dist + ax * lat, p["y"] + oy * dist + ay * lat)
                            x2, y2 = self._snap(x + ox * 2.4, y + oy * 2.4)
                            if want_stub and not self.exit_free(x, y, ox, oy, p["code"]):
                                continue
                            if want_stub and not self.line_ok(x, y, x2, y2, p["code"], 1):
                                continue
                            if not self.place_via_track(p, x, y):
                                continue
                            if want_stub:
                                self.commit_track(x, y, x2, y2, 1, p["code"], TRACK)
                                # Other vias stay far enough that their halo
                                # cannot cover this exit.
                                self._seg(self.vgrid, 1, x, y, x2, y2, 0.55, p["code"])
                            placed = True
                            break
                        if placed:
                            break
                    if not placed and p["net"] not in PLANE:
                        for dist in (1.6, 2.6, 3.6, 4.6):
                            for lat in (0.0, 1.2, -1.2, 2.4, -2.4):
                                x, y = self._snap(p["x"] + ox * dist + ax * lat, p["y"] + oy * dist + ay * lat)
                                if self.place_via_track(p, x, y):
                                    placed = True
                                    break
                            if placed:
                                break
                    p["escaped"] = placed
                    if placed:
                        n += 1
                    else:
                        print(f"  qfn miss {p['net']} pin {p['num']}", flush=True)
        # Thermal vias inside the exposed pad. Paste-only apertures are not pads here.
        for x in (78.8, 79.6, 80.4, 81.2):
            for y in (56.8, 57.6, 58.4, 59.2):
                gnd = next((p for p in u1 if p["net"] == "GND"), None)
                if gnd is None:
                    continue
                if not self.via_ok(x, y, gnd["code"]):
                    continue
                cells = self.commit_via(x, y, gnd["code"])
                aid = self.add_anchor("GND", gnd["code"], cells)
                self.join_plane("GND", aid)
                n += 1
        print(f"qfn fanout {n}", flush=True)

    def general_escape(self, pads):
        n = 0
        missed = 0
        for p in pads:
            if p.get("escaped") or p["pth"] or p["both"]:
                continue
            # Skip a pad whose centre already sits on a larger same-net pad (EP grid).
            if any(
                o is not p and o["net"] == p["net"] and o["fp"] == p["fp"]
                and abs(o["x"] - p["x"]) < o["sx"] / 2 and abs(o["y"] - p["y"]) < o["sy"] / 2
                and max(o["sx"], o["sy"]) > max(p["sx"], p["sy"]) + 0.2
                for o in pads
            ):
                p["escaped"] = True
                continue
            dx, dy = p["x"] - p["fx"], p["y"] - p["fy"]
            if abs(dx) + abs(dy) < 0.2:
                dx, dy = 0.0, 1.0
            if abs(dx) >= abs(dy):
                ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
            else:
                ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)
            half = max(p["sx"], p["sy"]) / 2
            placed = False
            for dist in (half + 0.55, half + 0.85, half + 1.15, half + 1.55, half + 2.05):
                for lat in (0.0, 0.45, -0.45, 0.9, -0.9, 1.35, -1.35):
                    x = p["x"] + ux * dist - uy * lat
                    y = p["y"] + uy * dist + ux * lat
                    x = round(x / G) * G
                    y = round(y / G) * G
                    if self.place_via_track(p, x, y):
                        placed = True
                        break
                if placed:
                    break
            p["escaped"] = placed
            if placed:
                n += 1
            else:
                missed += 1
                print(f"  escape miss {p['fp']}.{p['num']} {p['net']}", flush=True)
        print(f"escape {n} missed {missed}", flush=True)

    def short_links(self, pads):
        """Join two close pads of one net when a straight track fits."""
        by = defaultdict(list)
        for p in pads:
            if not p["pth"]:
                by[p["net"]].append(p)
        n = 0
        for net, items in by.items():
            if net in PLANE or len(items) < 2:
                continue
            code = items[0]["code"]
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    a, b = items[i], items[j]
                    if self.find(a["aid"]) == self.find(b["aid"]):
                        continue
                    d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                    if d > 7.0 or a["layer"] != b["layer"]:
                        continue
                    if self.line_ok(a["x"], a["y"], b["x"], b["y"], code, a["layer"]):
                        self.commit_track(a["x"], a["y"], b["x"], b["y"], a["layer"], code, WIDE.get(net, TRACK))
                        self.union(a["aid"], b["aid"])
                        n += 1
        print(f"short {n}", flush=True)

    def _goals(self, net, layer):
        buckets = defaultdict(list)
        for a in self.anchors:
            if a["net"] != net:
                continue
            root = self.find(a["id"])
            for lay, ix, iy in a["cells"]:
                if layer is None or lay == layer:
                    buckets[root].append((lay, ix, iy) if layer is None else (ix, iy))
        return buckets

    def route_layer(self, net, code, layer):
        linked = 0
        failed = set()
        guard = 0
        while guard < 40 and len(failed) < 8:
            guard += 1
            buckets = self._goals(net, layer)
            roots = [r for r, cells in buckets.items() if cells]
            if len(roots) < 2:
                break
            best = None
            for i in range(len(roots)):
                for j in range(i + 1, len(roots)):
                    key = (roots[i], roots[j]) if roots[i] < roots[j] else (roots[j], roots[i])
                    if key in failed:
                        continue
                    ca, cb = buckets[roots[i]], buckets[roots[j]]
                    ax, ay = ca[0]
                    bx, by = cb[0]
                    d = abs(ax - bx) + abs(ay - by)
                    if best is None or d < best[0]:
                        best = (d, roots[i], roots[j], key)
            if best is None:
                break
            d, ra, rb, key = best
            path = self._bfs(code, buckets[ra], set(buckets[rb]), layer)
            if path is None:
                failed.add(key)
                continue
            self._draw(code, path, layer, WIDE.get(net, TRACK))
            self.union(ra, rb)
            linked += 1
            print(f"  {net} L{layer} {d * G:.1f} mm", flush=True)
        return linked

    def _bfs(self, code, src, dst, layer):
        if not src or not dst:
            return None
        start = set(src)
        if start & dst:
            return []
        dq = deque(start)
        parent = {c: None for c in start}
        found = None
        pops = 0
        while dq and pops < 2000000:
            ix, iy = dq.popleft()
            pops += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = ix + dx, iy + dy
                if not self.inside(nx, ny) or (nx, ny) in parent:
                    continue
                v = int(self.walk[layer, ny, nx])
                if v not in (0, code):
                    continue
                parent[(nx, ny)] = (ix, iy)
                if (nx, ny) in dst:
                    found = (nx, ny)
                    dq.clear()
                    break
                dq.append((nx, ny))
        if found is None:
            return None
        path = []
        cur = found
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        return path

    def _draw(self, code, path, layer, width):
        if len(path) < 2:
            return
        pts = [self.xy(ix, iy) for ix, iy in path]
        run = [pts[0]]
        for p in pts[1:]:
            if len(run) >= 2:
                ax, ay = run[-2]
                bx, by = run[-1]
                if (bx - ax) * (p[1] - by) == (by - ay) * (p[0] - bx):
                    run[-1] = p
                    continue
            run.append(p)
        for a, b in zip(run, run[1:]):
            self.commit_track(a[0], a[1], b[0], b[1], layer, code, width)

    def route_multilayer(self, net, code):
        """Dijkstra on F / L3 / B. Via cost keeps long runs on L3."""
        buckets = self._goals(net, None)
        roots = list(buckets)
        if len(roots) < 2:
            return 0
        # Only the closest leftover pair, repeated by the caller.
        best = None
        for i in range(len(roots)):
            for j in range(i + 1, len(roots)):
                a = buckets[roots[i]][0]
                b = buckets[roots[j]][0]
                d = abs(a[1] - b[1]) + abs(a[2] - b[2])
                if best is None or d < best[0]:
                    best = (d, roots[i], roots[j])
        d, ra, rb = best
        src = buckets[ra]
        dst = set(buckets[rb])
        if any(c in dst for c in src):
            self.union(ra, rb)
            return 1
        parent = {}
        gscore = {}
        heap = []
        for c in src:
            gscore[c] = 0
            parent[c] = c
            heappush(heap, (0, c))
        found = None
        pops = 0
        while heap and pops < 2000000:
            g, cur = heappop(heap)
            pops += 1
            if g != gscore.get(cur):
                continue
            if cur in dst and g > 0:
                found = cur
                break
            layer, ix, iy = cur
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = ix + dx, iy + dy
                if not self.inside(nx, ny):
                    continue
                if int(self.walk[layer, ny, nx]) not in (0, code):
                    continue
                nid = (layer, nx, ny)
                step = 1 if layer == 1 else 2
                ng = g + step
                if ng < gscore.get(nid, 1 << 30):
                    gscore[nid] = ng
                    parent[nid] = cur
                    heappush(heap, (ng, nid))
            via_free = True
            for nlayer in range(3):
                if int(self.vgrid[nlayer, iy, ix]) not in (0, code):
                    via_free = False
                    break
            if via_free:
                for nlayer in range(3):
                    if nlayer == layer:
                        continue
                    if int(self.walk[nlayer, iy, ix]) not in (0, code):
                        continue
                    nid = (nlayer, ix, iy)
                    ng = g + 3
                    if ng < gscore.get(nid, 1 << 30):
                        gscore[nid] = ng
                        parent[nid] = cur
                        heappush(heap, (ng, nid))
        if found is None:
            print(f"  open {net} {d * G:.1f} mm", flush=True)
            return 0
        path = []
        cur = found
        seen = set()
        while cur not in seen:
            seen.add(cur)
            path.append(cur)
            if parent[cur] == cur:
                break
            cur = parent[cur]
        path.reverse()
        self._draw_multi(code, path, WIDE.get(net, TRACK))
        self.union(ra, rb)
        print(f"  {net} multi {d * G:.1f} mm", flush=True)
        return 1

    def _draw_multi(self, code, path, width):
        if len(path) < 2:
            return
        run = [path[0]]
        for p in path[1:]:
            if p[0] != run[-1][0]:
                self._flush_run(code, run, width)
                x, y = self.xy(p[1], p[2])
                if not any(abs(vx - x) < 0.05 and abs(vy - y) < 0.05 for vx, vy, _ in self.vias):
                    if self.via_ok(x, y, code):
                        cells = self.commit_via(x, y, code)
                        self.add_anchor("", code, cells)
                run = [p]
            else:
                if len(run) >= 2:
                    a, b = run[-2], run[-1]
                    if (b[1] - a[1]) * (p[2] - b[2]) == (b[2] - a[2]) * (p[1] - b[1]):
                        run[-1] = p
                        continue
                run.append(p)
        self._flush_run(code, run, width)

    def _flush_run(self, code, run, width):
        if len(run) < 2:
            return
        layer = run[0][0]
        for a, b in zip(run, run[1:]):
            x1, y1 = self.xy(a[1], a[2])
            x2, y2 = self.xy(b[1], b[2])
            self.commit_track(x1, y1, x2, y2, layer, code, width)

    def route_all(self, pads):
        nets = []
        seen = set()
        for p in pads:
            if p["net"] in seen or p["net"] in PLANE:
                continue
            seen.add(p["net"])
            nets.append(p["net"])

        def rank(name):
            if name in ("DVDD", "VREG_LX", "XIN", "XOUT"):
                return 0
            if name.startswith("QSPI") or name.startswith("USB"):
                return 1
            if name.startswith("PSRAM") or name.startswith("SPI"):
                return 2
            return 3

        nets.sort(key=rank)
        linked = 0
        for net in nets:
            code = next(p["code"] for p in pads if p["net"] == net)
            for layer in (1, 0, 2):
                linked += self.route_layer(net, code, layer)
            # Leftover islands: one multilayer attempt per remaining pair.
            for _ in range(8):
                before = self._group_count(net)
                if before < 2:
                    break
                got = self.route_multilayer(net, code)
                linked += got
                if not got:
                    break
        # Plane pads that never received a via.
        for net in PLANE:
            code = next((p["code"] for p in pads if p["net"] == net), None)
            if code is None:
                continue
            for _ in range(12):
                if self._group_count(net) < 2:
                    break
                got = self.route_multilayer(net, code)
                linked += got
                if not got:
                    break
        print(f"links {linked}", flush=True)

    def _group_count(self, net):
        return len({self.find(a["id"]) for a in self.anchors if a["net"] == net})

    def open_nets(self):
        groups = {}
        for a in self.anchors:
            if not a["net"]:
                continue
            groups.setdefault(a["net"], set()).add(self.find(a["id"]))
        return [name for name, roots in groups.items() if len(roots) > 1]

    def _restamp(self, pads, keepouts):
        """Rebuild the grids from pads and copper already on the board."""
        global WALK_EXTRA, VIA_GAP
        WALK_EXTRA = TRACK / 2 + CLEAR
        VIA_GAP = max(VIA_R + CLEAR, VIA_DRILL / 2 + 0.20) + 0.01
        self.walk = np.zeros((3, self.ny, self.nx), dtype=np.int16)
        self.vgrid = np.zeros((3, self.ny, self.nx), dtype=np.int16)
        self.hard_edge()
        for b in self.blocks:
            if b.get("npth"):
                rad = max(b["sx"], b["sy"]) / 2 + 0.45
                for layer in range(3):
                    self._disk(self.walk, layer, b["x"], b["y"], rad, -1, force=True)
                    self._disk(self.vgrid, layer, b["x"], b["y"], rad, -1, force=True)
                continue
            layers = [0, 1, 2] if b["pth"] or b["both"] else [b["layer"]]
            for layer in layers:
                self._rect(self.walk, layer, b["x"], b["y"], b["sx"] / 2 + WALK_EXTRA, b["sy"] / 2 + WALK_EXTRA, b["ang"], -1, force=True)
                self._rect(self.vgrid, layer, b["x"], b["y"], b["sx"] / 2 + VIA_GAP, b["sy"] / 2 + VIA_GAP, b["ang"], -1, force=True)
        for p in pads:
            layers = [0, 1, 2] if p["pth"] or p["both"] else [p["layer"]]
            for layer in layers:
                self._rect(self.walk, layer, p["x"], p["y"], p["sx"] / 2 + WALK_EXTRA, p["sy"] / 2 + WALK_EXTRA, p["ang"], p["code"])
                self._rect(self.vgrid, layer, p["x"], p["y"], p["sx"] / 2 + VIA_GAP, p["sy"] / 2 + VIA_GAP, p["ang"], p["code"])
                self._rect(self.walk, layer, p["x"], p["y"], p["sx"] / 2, p["sy"] / 2, p["ang"], p["code"], force=True)
        self.stamp_keepouts(keepouts)
        self._block_qfn_interior()
        for x, y, code in self.vias:
            for layer in range(3):
                self._disk(self.walk, layer, x, y, VIA_R + WALK_EXTRA, code)
                self._disk(self.vgrid, layer, x, y, VIA_R + VIA_GAP, code)
                ix, iy = self.cell(x, y)
                self._paint(self.walk, layer, ix, iy, code, force=True)
        for x1, y1, x2, y2, layer, code, width in self.segs:
            self._seg(self.walk, layer, x1, y1, x2, y2, width / 2 + CLEAR + TRACK / 2, code)
            self._seg(self.vgrid, layer, x1, y1, x2, y2, width / 2 + VIA_GAP, code)

    def rescue(self, pads, keepouts):
        """Second pass at 0.10 mm for nets the 0.15 mm grid could not finish."""
        global CLEAR
        left = self.open_nets()
        if not left:
            return
        print(f"rescue {len(left)} at 0.10 mm", flush=True)
        CLEAR = 0.10
        self._restamp(pads, keepouts)
        # Only the unfinished nets. route_all walks every net, which is cheap
        # once a net is already one group.
        self.route_all(pads)
        print("rescue left", " ".join(self.open_nets()) or "none", flush=True)

    def stitch(self):
        gnd = next((a for a in self.anchors if a["net"] == "GND"), None)
        if gnd is None:
            return
        code = gnd["code"]
        n = 0
        x = self.x0 + 1.6
        while x < self.x1 - 1.5:
            for y in (self.y0 + 1.6, self.y1 - 1.6):
                if self.via_ok(x, y, code):
                    cells = self.commit_via(x, y, code)
                    aid = self.add_anchor("GND", code, cells)
                    self.join_plane("GND", aid)
                    n += 1
            x += 2.5
        y = self.y0 + 1.6 + 2.5
        while y < self.y1 - 1.6:
            for x in (self.x0 + 1.6, self.x1 - 1.6):
                if self.via_ok(x, y, code):
                    cells = self.commit_via(x, y, code)
                    aid = self.add_anchor("GND", code, cells)
                    self.join_plane("GND", aid)
                    n += 1
            y += 2.5
        print(f"stitch {n}", flush=True)


def move_parts(board):
    by = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, (x, y) in MOVES.items():
        fp = by.get(ref)
        if fp is None:
            print("missing", ref, flush=True)
            continue
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    print("moved", " ".join(MOVES), flush=True)


def retile_l4(board):
    # Grab the net object first. Remove() makes a later GetNetsByName()
    # call return an untyped pointer in this KiCad build.
    net = board.GetNetsByName()["+3V3_DIG"]
    victims = []
    for z in list(board.Zones()):
        name = board.GetLayerName(z.GetLayer())
        if z.GetIsRuleArea() and name == "SIG_L3":
            victims.append(z)
        elif not z.GetIsRuleArea() and name == "PWR_L4":
            victims.append(z)
    for z in victims:
        board.Remove(z)
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.In3_Cu)
    z.SetNet(net)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetMinThickness(0)
    z.SetLocalClearance(pcbnew.FromMM(0.20))
    z.SetIsFilled(False)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    z.SetAssignedPriority(1)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((1.2, 1.2), (158.8, 1.2), (158.8, 98.8), (1.2, 98.8)):
        ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(z)


def design_rules(board):
    ds = board.GetDesignSettings()
    ds.m_MinClearance = pcbnew.FromMM(0.10)
    ds.m_TrackMinWidth = pcbnew.FromMM(0.10)
    ds.m_ViasMinSize = pcbnew.FromMM(VIA_D)
    ds.m_MinThroughDrill = pcbnew.FromMM(VIA_DRILL)
    ds.m_ViasMinAnnularWidth = pcbnew.FromMM(0.07)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.30)
    ds.m_HoleClearance = pcbnew.FromMM(0.20)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    # Floor is 0.10 mm. The router aims at 0.15 mm; the last hop of a
    # boxed QFN pin may use 0.10 mm, still above JLCPCB's 0.09 mm.
    nc.SetClearance(pcbnew.FromMM(0.10))
    nc.SetTrackWidth(pcbnew.FromMM(TRACK))
    nc.SetViaDiameter(pcbnew.FromMM(VIA_D))
    nc.SetViaDrill(pcbnew.FromMM(VIA_DRILL))
    nc.SetDiffPairGap(pcbnew.FromMM(CLEAR))
    nc.SetDiffPairWidth(pcbnew.FromMM(TRACK))


def keepout_rects(board):
    rects = []
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if not z.GetIsRuleArea() or not z.GetDoNotAllowTracks():
                continue
            if not z.GetLayerSet().Contains(pcbnew.F_Cu):
                continue
            ol = z.Outline()
            if ol.OutlineCount() < 1:
                continue
            line = ol.Outline(0)
            xs, ys = [], []
            for k in range(line.PointCount()):
                p = line.GetPoint(k)
                xs.append(mm(p.x))
                ys.append(mm(p.y))
            rects.append((min(xs), min(ys), max(xs), max(ys)))
    return rects


def main(path):
    board = pcbnew.LoadBoard(path)
    # The first Remove() in this KiCad build untypes later swig lookups
    # (GetTracks, GetNetsByName, GetDesignSettings). Snapshot first.
    design_rules(board)
    keepouts = keepout_rects(board)
    rt = Router(board)
    move_parts(board)
    # Pad geometry has to be read before Remove(); after that VECTOR2I
    # comes back untyped. The numpy grids do not care that the old tracks
    # are still on the board until we delete them below.
    rt.hard_edge()
    print("collect", flush=True)
    pads = rt.collect_pads(keepouts)
    rt.register(pads)
    print(f"pads {len(pads)}", flush=True)
    retile_l4(board)
    for t in list(rt.tracks):
        board.Remove(t)
    rt.qfn_fanout(pads)
    rt.short_links(pads)
    rt.general_escape(pads)
    if os.environ.get("HET68_FANOUT_ONLY"):
        print("fanout only", flush=True)
        return
    rt.route_all(pads)
    rt.rescue(pads, keepouts)
    rt.stitch()
    print("fill", flush=True)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    print(f"saved {path} copper {rt.added}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
