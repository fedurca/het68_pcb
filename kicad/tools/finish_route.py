"""Finish signal routing on an already-placed het68 board.

QFN-80 pads are 0.20 mm wide on a 0.40 mm pitch. A 0.15 mm track on the
pad centreline clears the neighbour by about 0.22 mm, which is enough for
the 0.20 mm netclass. Vias are 0.60 mm and do not fit in that bundle, so
each fine pad gets a straight escape and the maze only drops a via once
the track has left the bundle.

Order: escapes for every fine pad, then signal bridges shortest-first
(crystal, QSPI and LVDS included), then power. GND uses the planes: the
only extra copper is a via just past pin 62's escape.

New tracks are 0.15 mm on 6-layer boards and 0.20 mm on 2-layer boards.
"""
from __future__ import annotations

import math
import os
import sys
from array import array
from heapq import heappop, heappush

import pcbnew

G = 0.2
CLEAR = 0.20
POWER = {
    "GND", "+3V3_DIG", "+3V3_RF", "+3V3", "+5V_ALWAYS", "+1V8_AUDIO", "+1V8",
    "DVDD", "VBUS", "BAT", "DC", "VHARV", "AC1", "AC2", "VREG_LX",
}
# Routed before the other signals so the crystal and the buses own the channel.
EARLY = {
    "XIN", "XOUT", "VREG_LX", "DVDD",
    "USB_DP", "USB_DM",
    "QSPI_SS", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3",
}


def _hypot(dx, dy):
    return math.hypot(dx, dy)


def dist_point_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return _hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return _hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def dist_point_rect(px, py, x0, y0, x1, y1):
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return _hypot(dx, dy)


def _ccw(ax, ay, bx, by, cx, cy):
    return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)


def _seg_cross(a, b, c, d):
    return _ccw(a[0], a[1], c[0], c[1], d[0], d[1]) != _ccw(b[0], b[1], c[0], c[1], d[0], d[1]) and _ccw(
        a[0], a[1], b[0], b[1], c[0], c[1]
    ) != _ccw(a[0], a[1], b[0], b[1], d[0], d[1])


def dist_seg_seg(x1, y1, x2, y2, x3, y3, x4, y4):
    if _seg_cross((x1, y1), (x2, y2), (x3, y3), (x4, y4)):
        return 0.0
    return min(
        dist_point_seg(x1, y1, x3, y3, x4, y4),
        dist_point_seg(x2, y2, x3, y3, x4, y4),
        dist_point_seg(x3, y3, x1, y1, x2, y2),
        dist_point_seg(x4, y4, x1, y1, x2, y2),
    )


def dist_seg_rect(x1, y1, x2, y2, rx0, ry0, rx1, ry1):
    if dist_point_rect(x1, y1, rx0, ry0, rx1, ry1) == 0 or dist_point_rect(x2, y2, rx0, ry0, rx1, ry1) == 0:
        return 0.0
    corners = ((rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1))
    edges = ((corners[0], corners[1]), (corners[1], corners[2]), (corners[2], corners[3]), (corners[3], corners[0]))
    for p, q in edges:
        if _seg_cross((x1, y1), (x2, y2), p, q):
            return 0.0
    d = min(dist_point_rect(x1, y1, rx0, ry0, rx1, ry1), dist_point_rect(x2, y2, rx0, ry0, rx1, ry1))
    for cx, cy in corners:
        d = min(d, dist_point_seg(cx, cy, x1, y1, x2, y2))
    return d


def copper_gap(a, b):
    """Gap between copper edges. Negative means the shapes overlap."""
    ka, kb = a[0], b[0]
    if ka == "via" and kb != "via":
        return copper_gap(b, a)
    if ka == "pad" and kb == "pad":
        return dist_point_rect(a[1], a[2], b[1] - b[3], b[2] - b[4], b[1] + b[3], b[2] + b[4]) - 0.0 and (
            dist_seg_rect(a[1] - a[3], a[2], a[1] + a[3], a[2], b[1] - b[3], b[2] - b[4], b[1] + b[3], b[2] + b[4])
        )
    # handled below more directly
    return _gap(a, b)


def _gap(a, b):
    ka, kb = a[0], b[0]
    if ka > kb:
        return _gap(b, a)
    if ka == "pad" and kb == "pad":
        ax0, ay0, ax1, ay1 = a[1] - a[3], a[2] - a[4], a[1] + a[3], a[2] + a[4]
        return dist_point_rect(b[1], b[2], ax0, ay0, ax1, ay1) - b[3] if False else dist_seg_rect(
            b[1] - b[3], b[2], b[1] + b[3], b[2], ax0, ay0, ax1, ay1
        )
    if ka == "pad" and kb == "seg":
        return dist_seg_rect(b[1], b[2], b[3], b[4], a[1] - a[3], a[2] - a[4], a[1] + a[3], a[2] + a[4]) - b[5]
    if ka == "pad" and kb == "via":
        return dist_point_rect(b[1], b[2], a[1] - a[3], a[2] - a[4], a[1] + a[3], a[2] + a[4]) - b[3]
    if ka == "seg" and kb == "seg":
        return dist_seg_seg(a[1], a[2], a[3], a[4], b[1], b[2], b[3], b[4]) - a[5] - b[5]
    if ka == "seg" and kb == "via":
        return dist_point_seg(b[1], b[2], a[1], a[2], a[3], a[4]) - a[5] - b[3]
    if ka == "via" and kb == "via":
        return _hypot(a[1] - b[1], a[2] - b[2]) - a[3] - b[3]
    return 1e9


def _bbox(item):
    k = item[0]
    if k == "pad":
        return item[1] - item[3], item[2] - item[4], item[1] + item[3], item[2] + item[4]
    if k == "seg":
        return min(item[1], item[3]), min(item[2], item[4]), max(item[1], item[3]), max(item[2], item[4])
    return item[1] - item[3], item[2] - item[3], item[1] + item[3], item[2] + item[3]


def _bbox_gap(a, b):
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return _hypot(dx, dy)


class NetState:
    def __init__(self, code, name):
        self.code = code
        self.name = name
        self.items = []
        self.p = []

    def add(self, item):
        self.items.append(item)
        self.p.append(len(self.p))

    def find(self, i):
        p = self.p
        while p[i] != i:
            p[i] = p[p[i]]
            i = p[i]
        return i

    def union(self, i, j):
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.p[rj] = ri

    def rebuild(self):
        n = len(self.items)
        self.p = list(range(n))
        items = self.items
        for i in range(n):
            bi = _bbox(items[i])
            for j in range(i):
                if _bbox_gap(bi, _bbox(items[j])) > 0.8:
                    continue
                if _gap(items[i], items[j]) <= 0.03:
                    self.union(i, j)

    def groups(self):
        buckets = {}
        for i in range(len(self.items)):
            buckets.setdefault(self.find(i), []).append(i)
        out = []
        for idxs in buckets.values():
            bb = [1e9, 1e9, -1e9, -1e9]
            has_pad = False
            has_via = False
            for i in idxs:
                it = self.items[i]
                b = _bbox(it)
                bb[0] = min(bb[0], b[0])
                bb[1] = min(bb[1], b[1])
                bb[2] = max(bb[2], b[2])
                bb[3] = max(bb[3], b[3])
                has_pad = has_pad or it[0] == "pad"
                has_via = has_via or it[0] == "via"
            out.append({"idx": idxs, "bb": tuple(bb), "pad": has_pad, "via": has_via})
        return out


def _mm(v):
    return pcbnew.ToMM(v)


class Finish:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        self.layers_n = board.GetCopperLayerCount()
        self.track_w = 0.15 if self.layers_n >= 4 else 0.20
        self.via_d, self.via_drill = 0.60, 0.20
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                self.via_d = _mm(t.GetWidth(pcbnew.F_Cu))
                self.via_drill = _mm(t.GetDrillValue())
                break
        bb = board.GetBoardEdgesBoundingBox()
        self.x0 = _mm(bb.GetX())
        self.y0 = _mm(bb.GetY())
        self.x1 = self.x0 + _mm(bb.GetWidth())
        self.y1 = self.y0 + _mm(bb.GetHeight())
        self.nx = int(round(self.x1 / G)) + 4
        self.ny = int(round(self.y1 / G)) + 4
        self.ncell = self.nx * self.ny
        self.own_f = array("i", [0]) * self.ncell
        self.own_b = array("i", [0]) * self.ncell
        self.via_g = array("i", [0]) * self.ncell
        self.halo = CLEAR + self.track_w / 2
        self.via_r = self.via_d / 2
        self.nets = {}
        self.blocks = []
        self.added = 0
        self.fanouts = 0

    def cell(self, x, y):
        return int(round(x / G)), int(round(y / G))

    def idx(self, ix, iy):
        return iy * self.nx + ix

    def xy(self, ix, iy):
        return ix * G, iy * G

    def inside(self, ix, iy):
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    def _mark(self, grid, ix, iy, net):
        if not self.inside(ix, iy):
            return
        i = self.idx(ix, iy)
        v = grid[i]
        if v == 0 or v == net:
            grid[i] = net
        else:
            grid[i] = -1

    def _mark_disc(self, grid, x, y, rad, net):
        rcell = int(rad / G) + 1
        ix, iy = self.cell(x, y)
        rad2 = rad * rad
        for dy in range(-rcell, rcell + 1):
            for dx in range(-rcell, rcell + 1):
                cx, cy = self.xy(ix + dx, iy + dy)
                if (cx - x) * (cx - x) + (cy - y) * (cy - y) <= rad2:
                    self._mark(grid, ix + dx, iy + dy, net)

    def _mark_rect(self, grid, x0, y0, x1, y1, net):
        ix0, iy0 = self.cell(x0, y0)
        ix1, iy1 = self.cell(x1, y1)
        if ix0 > ix1:
            ix0, ix1 = ix1, ix0
        if iy0 > iy1:
            iy0, iy1 = iy1, iy0
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                cx, cy = self.xy(ix, iy)
                if x0 - 1e-6 <= cx <= x1 + 1e-6 and y0 - 1e-6 <= cy <= y1 + 1e-6:
                    self._mark(grid, ix, iy, net)

    def _mark_seg(self, grid, x1, y1, x2, y2, rad, net):
        step = max(1, int(_hypot(x2 - x1, y2 - y1) / G))
        for i in range(step + 1):
            t = i / step
            self._mark_disc(grid, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, rad, net)

    def stamp_item(self, item, net, extra=0.0):
        k = item[0]
        rad = self.halo + extra
        grids = []
        if k == "pad":
            layer = item[5]
            grids = [self.own_f] if layer == 0 else [self.own_b] if layer == 1 else [self.own_f, self.own_b]
            x0, y0, x1, y1 = item[1] - item[3] - rad, item[2] - item[4] - rad, item[1] + item[3] + rad, item[2] + item[4] + rad
            for g in grids:
                self._mark_rect(g, x0, y0, x1, y1, net)
            self._mark_disc(self.via_g, item[1], item[2], _hypot(item[3], item[4]) + self.via_r + CLEAR, net)
        elif k == "seg":
            g = self.own_f if item[6] == 0 else self.own_b
            self._mark_seg(g, item[1], item[2], item[3], item[4], item[5] + rad, net)
            self._mark_seg(self.via_g, item[1], item[2], item[3], item[4], item[5] + self.via_r + CLEAR, net)
        elif k == "via":
            self._mark_disc(self.own_f, item[1], item[2], item[3] + rad, net)
            self._mark_disc(self.own_b, item[1], item[2], item[3] + rad, net)
            self._mark_disc(self.via_g, item[1], item[2], item[3] + self.via_r + CLEAR, net)

    def block_edges(self):
        m = 0.45
        for iy in range(self.ny):
            for ix in range(self.nx):
                x, y = self.xy(ix, iy)
                if x < self.x0 + m or y < self.y0 + m or x > self.x1 - m or y > self.y1 - m:
                    i = self.idx(ix, iy)
                    self.own_f[i] = -1
                    self.own_b[i] = -1
                    self.via_g[i] = -1
        for z in self.b.Zones():
            if not z.GetIsRuleArea() or not z.GetDoNotAllowVias():
                continue
            ol = z.Outline()
            if ol.OutlineCount() < 1:
                continue
            line = ol.Outline(0)
            xs, ys = [], []
            for k in range(line.PointCount()):
                p = line.GetPoint(k)
                xs.append(_mm(p.x))
                ys.append(_mm(p.y))
            # Through vias hit every layer, including an inner keepout.
            self._mark_rect(self.via_g, min(xs) - self.via_r, min(ys) - self.via_r, max(xs) + self.via_r, max(ys) + self.via_r, -1)

    def collect(self):
        states = {}

        def st(net):
            if net is None:
                return None
            name = net.GetNetname()
            if not name or name.startswith("unconnected"):
                return None
            code = net.GetNetCode()
            if code not in states:
                states[code] = NetState(code, name)
            return states[code]

        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                if not (pad.IsOnLayer(pcbnew.F_Cu) or pad.IsOnLayer(pcbnew.B_Cu)):
                    continue
                net = pad.GetNet()
                name = pad.GetNetname()
                pos = pad.GetPosition()
                bb = pad.GetBoundingBox()
                x = _mm(bb.GetX()) + _mm(bb.GetWidth()) / 2
                y = _mm(bb.GetY()) + _mm(bb.GetHeight()) / 2
                hw = _mm(bb.GetWidth()) / 2
                hh = _mm(bb.GetHeight()) / 2
                if hw < 0.04 or hh < 0.04:
                    sz = pad.GetSize()
                    x, y = _mm(pos.x), _mm(pos.y)
                    hw, hh = _mm(sz.x) / 2, _mm(sz.y) / 2
                attr = pad.GetAttribute()
                both = attr == pcbnew.PAD_ATTRIB_PTH
                layer = 2 if both else (0 if pad.IsOnLayer(pcbnew.F_Cu) else 1)
                item = ("pad", x, y, hw, hh, layer)
                if attr == pcbnew.PAD_ATTRIB_NPTH or not name:
                    # A hole goes through the board, so it blocks both outer layers.
                    self.blocks.append(("pad", x, y, hw, hh, 2))
                    continue
                s = st(net)
                if s is None:
                    self.blocks.append(item)
                    continue
                s.add(("pad", x, y, hw, hh, layer, fp.GetReference(), pad.GetNumber()))
        for t in list(self.b.GetTracks()):
            net = t.GetNet()
            s = st(net)
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                item = ("via", _mm(p.x), _mm(p.y), _mm(t.GetWidth(pcbnew.F_Cu)) / 2)
                if s is None:
                    self.blocks.append(item)
                else:
                    s.add(item)
            else:
                a, c = t.GetStart(), t.GetEnd()
                layer = 0 if t.GetLayer() == pcbnew.F_Cu else 1
                item = ("seg", _mm(a.x), _mm(a.y), _mm(c.x), _mm(c.y), _mm(t.GetWidth()) / 2, layer)
                if s is None:
                    self.blocks.append(item)
                else:
                    s.add(item)
        self.nets = states

    def deletion_keys(self):
        """Geometry to remove. One GetTracks() snapshot deletes them later."""
        keys = []
        for s in self.nets.values():
            if s.name == "GND":
                continue
            s.rebuild()
            kill = []
            for g in s.groups():
                if g["pad"]:
                    continue
                if s.name in POWER and g["via"]:
                    continue
                kill.extend(g["idx"])
            for i in kill:
                it = s.items[i]
                if it[0] == "via":
                    keys.append((s.code, "via", round(it[1], 3), round(it[2], 3)))
                elif it[0] == "seg":
                    keys.append((s.code, "seg", round(it[1], 3), round(it[2], 3), round(it[3], 3), round(it[4], 3)))
            if kill:
                s.items = [it for i, it in enumerate(s.items) if i not in set(kill)]
        windows = []
        for fp in self.b.GetFootprints():
            xs, ys, nfine = [], [], 0
            for pad in fp.Pads():
                sz = pad.GetSize()
                if min(_mm(sz.x), _mm(sz.y)) > 0.25:
                    continue
                nfine += 1
                p = pad.GetPosition()
                xs.append(_mm(p.x))
                ys.append(_mm(p.y))
            if nfine >= 16 and xs:
                windows.append((min(xs) - 1.8, min(ys) - 1.8, max(xs) + 1.8, max(ys) + 1.8, fp.GetReference()))
        ch = 0
        for s in self.nets.values():
            if s.name == "GND":
                continue
            keep = []
            for it in s.items:
                if it[0] != "seg":
                    keep.append(it)
                    continue
                drop = False
                for x0, y0, x1, y1, _ref in windows:
                    if dist_seg_rect(it[1], it[2], it[3], it[4], x0, y0, x1, y1) <= 0:
                        drop = True
                        break
                if drop:
                    keys.append((s.code, "seg", round(it[1], 3), round(it[2], 3), round(it[3], 3), round(it[4], 3)))
                    ch += 1
                else:
                    keep.append(it)
            s.items = keep
        # Any track that lands on a foreign pad (a part was moved onto old copper).
        pads = []
        for s in self.nets.values():
            for it in s.items:
                if it[0] == "pad":
                    pads.append((s.code, it))
        for item in self.blocks:
            if item[0] == "pad":
                pads.append((-1, item))
        crossed = 0
        for s in self.nets.values():
            keep = []
            for it in s.items:
                if it[0] != "seg":
                    keep.append(it)
                    continue
                hit = False
                for code, pad in pads:
                    if code == s.code:
                        continue
                    gap = dist_seg_rect(
                        it[1], it[2], it[3], it[4],
                        pad[1] - pad[3], pad[2] - pad[4], pad[1] + pad[3], pad[2] + pad[4],
                    ) - it[5]
                    if gap < CLEAR:
                        hit = True
                        break
                if hit:
                    keys.append((s.code, "seg", round(it[1], 3), round(it[2], 3), round(it[3], 3), round(it[4], 3)))
                    crossed += 1
                else:
                    keep.append(it)
            s.items = keep
        for s in self.nets.values():
            keep = []
            for it in s.items:
                if it[0] != "via":
                    keep.append(it)
                    continue
                hit = False
                for code, pad in pads:
                    if code == s.code:
                        continue
                    if dist_point_rect(it[1], it[2], pad[1] - pad[3], pad[2] - pad[4], pad[1] + pad[3], pad[2] + pad[4]) < it[3] + CLEAR:
                        hit = True
                        break
                if hit:
                    keys.append((s.code, "via", round(it[1], 3), round(it[2], 3)))
                    crossed += 1
                else:
                    keep.append(it)
            s.items = keep
        print(f"delete {len(keys)} copper, channel segs {ch}, crossed {crossed}, windows {' '.join(w[4] for w in windows)}", flush=True)
        return keys

    def delete_keys(self, keys):
        wanted = set(keys)
        gone = 0
        for t in list(self.b.GetTracks()):
            code = t.GetNetCode()
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                key = (code, "via", round(_mm(p.x), 3), round(_mm(p.y), 3))
            else:
                a, c = t.GetStart(), t.GetEnd()
                key = (code, "seg", round(_mm(a.x), 3), round(_mm(a.y), 3), round(_mm(c.x), 3), round(_mm(c.y), 3))
            if key in wanted:
                self.b.Remove(t)
                gone += 1
        print(f"removed {gone}", flush=True)

    def _legal_line(self, x1, y1, x2, y2, net):
        step = max(1, int(_hypot(x2 - x1, y2 - y1) / (G * 0.5)))
        for i in range(step + 1):
            t = i / step
            ix, iy = self.cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if not self.inside(ix, iy):
                return False
            v = self.own_f[self.idx(ix, iy)]
            if v not in (0, net):
                return False
        return True

    def fanout(self):
        """Escape every fine SMD pad along the long axis, away from the part."""
        for fp in self.b.GetFootprints():
            fx, fy = _mm(fp.GetPosition().x), _mm(fp.GetPosition().y)
            for pad in fp.Pads():
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                name = pad.GetNetname()
                if not name or name.startswith("unconnected"):
                    continue
                sz = pad.GetSize()
                sw, sh = _mm(sz.x), _mm(sz.y)
                if min(sw, sh) > 0.25 or max(sw, sh) > 1.2:
                    continue
                if not pad.IsOnLayer(pcbnew.F_Cu):
                    continue
                code = pad.GetNetCode()
                s = self.nets.get(code)
                if s is None:
                    continue
                pos = pad.GetPosition()
                x, y = _mm(pos.x), _mm(pos.y)
                # Already touching foreign-net-free copper of its own net?
                joined = False
                for it in s.items:
                    if it[0] == "pad" and abs(it[1] - x) < 0.05 and abs(it[2] - y) < 0.05:
                        continue
                    if _gap(("pad", x, y, sw / 2, sh / 2, 0), it) <= 0.0:
                        joined = True
                        break
                if joined:
                    continue
                # Along the long axis, away from the part. A radial ray from the
                # footprint origin is diagonal on a side-row pin and clips the
                # neighbour 0.20 mm away.
                if sw >= sh:
                    ux, uy = (1.0 if x >= fx else -1.0), 0.0
                else:
                    ux, uy = 0.0, (1.0 if y >= fy else -1.0)
                half = max(sw, sh) / 2
                reach = half + (2.0 if name == "GND" else 1.0)
                tipx, tipy = x + ux * reach, y + uy * reach
                ix, iy = self.cell(tipx, tipy)
                tipx, tipy = self.xy(ix, iy)
                # Keep the tip outside the pad, on the outward side.
                if (tipx - x) * ux + (tipy - y) * uy < half + 0.3:
                    continue
                if not self._legal_line(x, y, tipx, tipy, code):
                    # Shorten in 0.2 mm steps until the escape fits.
                    ok = False
                    dist = reach
                    while dist > half + 0.35:
                        dist -= 0.2
                        tipx, tipy = x + ux * dist, y + uy * dist
                        ix, iy = self.cell(tipx, tipy)
                        tipx, tipy = self.xy(ix, iy)
                        if (tipx - x) * ux + (tipy - y) * uy < half + 0.25:
                            break
                        if self._legal_line(x, y, tipx, tipy, code):
                            ok = True
                            break
                    if not ok:
                        continue
                self._add_seg(x, y, tipx, tipy, 0, s)
                self.fanouts += 1
                if name == "GND":
                    self._try_via(tipx, tipy, s)
        # Staggered lanes were tried. They claim the only free row and trap
        # the pins that cannot turn, so the straight escapes stay as they are.
        print(f"fanout {self.fanouts}", flush=True)

    def _add_seg(self, x1, y1, x2, y2, layer, s):
        if _hypot(x2 - x1, y2 - y1) < 0.05:
            return
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(self.track_w))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNetCode(s.code)
        self.b.Add(t)
        item = ("seg", x1, y1, x2, y2, self.track_w / 2, layer)
        s.add(item)
        self.stamp_item(item, s.code)
        self.added += 1

    def _try_via(self, x, y, s):
        ix, iy = self.cell(x, y)
        if not self.inside(ix, iy):
            return False
        if self.via_g[self.idx(ix, iy)] not in (0, s.code):
            return False
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(self.via_d))
        v.SetDrill(pcbnew.FromMM(self.via_drill))
        v.SetNetCode(s.code)
        try:
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
        except Exception:
            pass
        self.b.Add(v)
        item = ("via", x, y, self.via_r)
        s.add(item)
        self.stamp_item(item, s.code)
        self.added += 1
        return True

    def _cells_for(self, s, idxs):
        out = []
        seen = set()
        for i in idxs:
            it = s.items[i]
            k = it[0]
            if k == "pad":
                layers = (0, 1) if it[5] == 2 else (it[5],)
                x0, y0, x1, y1 = it[1] - it[3], it[2] - it[4], it[1] + it[3], it[2] + it[4]
                ix0, iy0 = self.cell(x0, y0)
                ix1, iy1 = self.cell(x1, y1)
                for layer in layers:
                    grid = self.own_f if layer == 0 else self.own_b
                    for iy in range(min(iy0, iy1), max(iy0, iy1) + 1):
                        for ix in range(min(ix0, ix1), max(ix0, ix1) + 1):
                            cx, cy = self.xy(ix, iy)
                            if not (x0 - 1e-6 <= cx <= x1 + 1e-6 and y0 - 1e-6 <= cy <= y1 + 1e-6):
                                continue
                            id_ = layer * self.ncell + self.idx(ix, iy)
                            if id_ in seen:
                                continue
                            if grid[self.idx(ix, iy)] not in (0, s.code):
                                continue
                            seen.add(id_)
                            out.append(id_)
            elif k == "seg":
                layer = it[6]
                grid = self.own_f if layer == 0 else self.own_b
                step = max(1, int(_hypot(it[3] - it[1], it[4] - it[2]) / G))
                for n in range(step + 1):
                    t = n / step
                    ix, iy = self.cell(it[1] + (it[3] - it[1]) * t, it[2] + (it[4] - it[2]) * t)
                    if not self.inside(ix, iy):
                        continue
                    if grid[self.idx(ix, iy)] not in (0, s.code):
                        continue
                    id_ = layer * self.ncell + self.idx(ix, iy)
                    if id_ not in seen:
                        seen.add(id_)
                        out.append(id_)
            else:
                ix, iy = self.cell(it[1], it[2])
                for layer in (0, 1):
                    grid = self.own_f if layer == 0 else self.own_b
                    if not self.inside(ix, iy):
                        continue
                    if grid[self.idx(ix, iy)] not in (0, s.code):
                        continue
                    id_ = layer * self.ncell + self.idx(ix, iy)
                    if id_ not in seen:
                        seen.add(id_)
                        out.append(id_)
        return out

    def _route(self, s, src, dst, expand=250000):
        src_cells = self._cells_for(s, src["idx"])
        dst_cells = set(self._cells_for(s, dst["idx"]))
        if not src_cells or not dst_cells:
            return False
        hbb = dst["bb"]
        if len(src_cells) > len(dst_cells):
            src_cells, dst_cells = list(dst_cells), set(src_cells)
            hbb = src["bb"]
        bx0, by0, bx1, by1 = hbb
        # Prefer the smaller side as the destination so the heuristic is tight.
        def h_of(id_):
            layer = id_ // self.ncell
            rest = id_ - layer * self.ncell
            ix, iy = rest % self.nx, rest // self.nx
            x, y = self.xy(ix, iy)
            dx = 0.0 if bx0 <= x <= bx1 else min(abs(x - bx0), abs(x - bx1))
            dy = 0.0 if by0 <= y <= by1 else min(abs(y - by0), abs(y - by1))
            return int((dx + dy) / G) * 2

        gscore = {}
        parent = {}
        heap = []
        for c in src_cells:
            gscore[c] = 0
            parent[c] = c
            heappush(heap, (h_of(c), 0, c))
        found = None
        pops = 0
        grids = (self.own_f, self.own_b)
        while heap and pops < expand:
            _, g, cur = heappop(heap)
            pops += 1
            if g != gscore.get(cur):
                continue
            if cur in dst_cells and cur not in parent or (cur in dst_cells and parent.get(cur) != cur and g > 0):
                found = cur
                break
            if cur in dst_cells and g > 0:
                found = cur
                break
            layer = cur // self.ncell
            rest = cur - layer * self.ncell
            ix, iy = rest % self.nx, rest // self.nx
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nix, niy = ix + dx, iy + dy
                if not self.inside(nix, niy):
                    continue
                if grids[layer][self.idx(nix, niy)] not in (0, s.code):
                    continue
                nid = layer * self.ncell + self.idx(nix, niy)
                ng = g + 2
                if ng < gscore.get(nid, 1 << 30):
                    gscore[nid] = ng
                    parent[nid] = cur
                    heappush(heap, (ng + h_of(nid), ng, nid))
            oi = self.idx(ix, iy)
            if self.via_g[oi] in (0, s.code):
                nlayer = 1 - layer
                nid = nlayer * self.ncell + oi
                if grids[nlayer][oi] in (0, s.code):
                    ng = g + 5
                    if ng < gscore.get(nid, 1 << 30):
                        gscore[nid] = ng
                        parent[nid] = cur
                        heappush(heap, (ng + h_of(nid), ng, nid))
        if found is None:
            return False
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
        self._draw_path(s, path)
        return True

    def _draw_path(self, s, path):
        pts = []
        for id_ in path:
            layer = id_ // self.ncell
            rest = id_ - layer * self.ncell
            ix, iy = rest % self.nx, rest // self.nx
            pts.append((layer, self.xy(ix, iy)))
        # Drop the starting cell's private prefix that is already copper; keep it
        # so the new segment begins inside the existing copper.
        run = [pts[0]]
        for p in pts[1:]:
            if p[0] != run[-1][0]:
                self._flush(s, run)
                # Via on the new layer, which still overlaps the previous track.
                self._try_via(p[1][0], p[1][1], s)
                run = [p]
            else:
                prev = run[-1][1]
                if len(run) >= 2:
                    a, b = run[-2][1], run[-1][1]
                    if (b[0] - a[0]) * (p[1][1] - b[1]) == (b[1] - a[1]) * (p[1][0] - b[0]):
                        run[-1] = p
                        continue
                run.append(p)
        self._flush(s, run)

    def _flush(self, s, run):
        if len(run) < 2:
            return
        layer = run[0][0]
        for a, b in zip(run, run[1:]):
            self._add_seg(a[1][0], a[1][1], b[1][0], b[1][1], layer, s)

    def bridges(self):
        order = []
        for s in self.nets.values():
            if s.name == "GND" or s.name.startswith("unconnected"):
                continue
            s.rebuild()
            pri = 0 if s.name in EARLY else 2 if s.name in POWER else 1
            if any(tok in s.name for tok in ("_P", "_N", "SCK", "WS", "SD", "USB", "QSPI", "XIN", "XOUT")):
                pri = min(pri, 1 if s.name not in EARLY else 0)
            order.append((pri, s.name, s))
        order.sort()
        fail = set()
        done = 0
        for pri, name, s in order:
            guard = 0
            while guard < 40:
                guard += 1
                groups = [g for g in s.groups() if g["pad"] or g["via"] or name not in POWER]
                if name in POWER:
                    groups = s.groups()
                if len(groups) < 2:
                    break
                best = None
                for i in range(len(groups)):
                    for j in range(i + 1, len(groups)):
                        key = (name, round(groups[i]["bb"][0], 1), round(groups[i]["bb"][1], 1), round(groups[j]["bb"][0], 1), round(groups[j]["bb"][1], 1))
                        if key in fail:
                            continue
                        d = _bbox_gap(groups[i]["bb"], groups[j]["bb"])
                        if best is None or d < best[0]:
                            best = (d, i, j, key)
                if best is None:
                    break
                d, i, j, key = best
                cap = 500000
                ok = self._route(s, groups[i], groups[j], expand=cap)
                if ok:
                    done += 1
                    s.rebuild()
                    print(f"  link {name} gap {d:.1f} mm", flush=True)
                else:
                    fail.add(key)
                    print(f"  open {name} gap {d:.1f} mm", flush=True)
        print(f"links {done}", flush=True)


def finish_board(board: pcbnew.BOARD, fill=True, prepared=False):
    fin = Finish(board)
    print("collect", flush=True)
    fin.collect()
    print(f"nets {len(fin.nets)} blocks {len(fin.blocks)}", flush=True)
    # Copper was already cleaned in a previous process. Restamp only.
    fin.own_f = array("i", [0]) * fin.ncell
    fin.own_b = array("i", [0]) * fin.ncell
    fin.via_g = array("i", [0]) * fin.ncell
    fin.block_edges()
    for item in fin.blocks:
        fin.stamp_item(item, -1)
    for s in fin.nets.values():
        for it in s.items:
            fin.stamp_item(it, s.code)
    fin.fanout()
    for s in fin.nets.values():
        s.rebuild()
    fin.bridges()
    if fill:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
    return fin


def _move(board, ref, x, y):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            return
    print(f"missing {ref}", flush=True)


def relax_core(board: pcbnew.BOARD):
    """Open a channel north of the QFN.

    Y1 sat on the north edge, 2 mm from the 0.40 mm pin row, so only a few
    of the twenty escapes could leave. XIN and XOUT are on the south edge;
    12 MHz still tolerates the longer loop. The series I2S resistors move
    to the west row, next to those pins.
    """
    if not any(fp.GetReference() == "Y1" for fp in board.GetFootprints()):
        return
    _move(board, "Y1", 78, 40)
    _move(board, "C_X1", 73, 40)
    _move(board, "C_X2", 84, 40)
    _move(board, "L_VREG", 93, 44)
    # Clear of U3 (PSRAM at x=64) and of the west-side escapes.
    _move(board, "R_I2S_SCK", 71, 48)
    _move(board, "R_I2S_WS", 71, 66)
    print("relaxed core crystal and series parts", flush=True)


def prepare(board: pcbnew.BOARD):
    """Move the crystal off the fanout, drop blocking copper, then reload."""
    relax_core(board)
    fin = Finish(board)
    fin.collect()
    fin.delete_keys(fin.deletion_keys())
    return fin


def main(argv):
    # pcbnew in this build cannot load a second board in the same process.
    if argv[1] == "--route":
        path = argv[2]
        board = pcbnew.LoadBoard(path)
        fin = finish_board(board, fill=True, prepared=True)
        pcbnew.SaveBoard(path, board)
        print(f"saved {path} fanout {fin.fanouts} added {fin.added}", flush=True)
        return
    path = argv[1]
    board = pcbnew.LoadBoard(path)
    prepare(board)
    pcbnew.SaveBoard(path, board)
    print("prepared", path, flush=True)
    os.execv(sys.executable, [sys.executable, __file__, "--route", path])


if __name__ == "__main__":
    main(sys.argv)
