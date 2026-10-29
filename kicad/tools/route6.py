"""6-layer Faraday stackup, GND stitch, L4 split planes, L3 gap keepout.

Signal router for 6L boards: F.Cu, In2.Cu (stripline), B.Cu.
L2/L5 are solid GND. L4 is power only — never route signals there.
Tracks on In2.Cu must not cross the split gaps on L4.
"""
from __future__ import annotations

import heapq
import math

import pcbnew

G = 0.1
TRACK_W = 0.2
CLEAR = 0.15
MARGIN = 0.06
BODY = CLEAR + TRACK_W / 2 + MARGIN


def set_stackup(board) -> None:
    b = board.b
    b.SetCopperLayerCount(6)
    names = {
        pcbnew.F_Cu: "F.Cu",
        pcbnew.In1_Cu: "GND_L2",
        pcbnew.In2_Cu: "SIG_L3",
        pcbnew.In3_Cu: "PWR_L4",
        pcbnew.In4_Cu: "GND_L5",
        pcbnew.B_Cu: "B.Cu",
    }
    for layer, name in names.items():
        try:
            b.SetLayerName(layer, name)
        except Exception:
            pass
    try:
        enabled = b.GetEnabledLayers()
        for layer in (
            pcbnew.F_Cu,
            pcbnew.In1_Cu,
            pcbnew.In2_Cu,
            pcbnew.In3_Cu,
            pcbnew.In4_Cu,
            pcbnew.B_Cu,
        ):
            enabled.AddLayer(layer)
        b.SetEnabledLayers(enabled)
    except Exception:
        pass


def add_via(board, x, y, netname, diameter=0.45, drill=0.2):
    if netname not in board.nets:
        return None
    v = pcbnew.PCB_VIA(board.b)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetWidth(pcbnew.FromMM(diameter))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetNet(board.nets[netname])
    try:
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
    except Exception:
        pass
    board.b.Add(v)
    return v


def stitch_gnd(board, pitch=2.0, margin=1.6, diameter=0.45, drill=0.2):
    """Through-via fence L1–L6 on GND, 1.5–2 mm pitch along the outline."""
    xs, xe = margin, board.w - margin
    ys, ye = margin, board.h - margin
    n = 0
    x = xs
    while x <= xe + 1e-6:
        add_via(board, x, ys, "GND", diameter, drill)
        add_via(board, x, ye, "GND", diameter, drill)
        n += 2
        x += pitch
    y = ys + pitch
    while y < ye - 0.5:
        add_via(board, xs, y, "GND", diameter, drill)
        add_via(board, xe, y, "GND", diameter, drill)
        n += 2
        y += pitch
    return n


def add_keepout_rect(board, x0, y0, x1, y1, layer, tracks=True, vias=True):
    z = pcbnew.ZONE(board.b)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetLayer(layer)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.b.Add(z)
    return z


def split_power_l4(board, regions, gap=2.0, keepout_l3=True):
    """regions: list of (net, x0, x1) covering the board width with gaps.

    Also plants keepouts on L3 (In2.Cu) over each gap so stripline cannot
    cross a split in the power plane below. Skip keepouts when L3 is GND.
    """
    m = 1.2
    for net, x0, x1 in regions:
        pts = ((max(m, x0), m), (min(board.w - m, x1), m),
               (min(board.w - m, x1), board.h - m), (max(m, x0), board.h - m))
        board.add_zone(net, pcbnew.In3_Cu, pts=pts, priority=1, clearance=0.25, islands="always")
    gaps = []
    ordered = sorted(regions, key=lambda r: r[1])
    for a, b in zip(ordered, ordered[1:]):
        gx0, gx1 = a[2], b[1]
        if gx1 > gx0:
            gaps.append((gx0, gx1))
            if keepout_l3:
                add_keepout_rect(board, gx0, m, gx1, board.h - m, pcbnew.In2_Cu)
    board.l4_gaps = gaps
    return gaps


def faraday_planes(board, splits, l3_gnd=False):
    """Solid GND on L2 and L5, GND pours on L1/L6, split L4.

    When l3_gnd is set, L3 is also a solid GND (outer-layer routing only).
    """
    set_stackup(board)
    board.add_zone("GND", pcbnew.In1_Cu, islands="always")
    board.add_zone("GND", pcbnew.In4_Cu, islands="always")
    if l3_gnd:
        board.add_zone("GND", pcbnew.In2_Cu, islands="always")
    board.add_zone("GND", pcbnew.F_Cu, islands="area", clearance=0.2)
    board.add_zone("GND", pcbnew.B_Cu, islands="area", clearance=0.2)
    split_power_l4(board, splits, keepout_l3=not l3_gnd)
    stitch_gnd(board)


# ---------------------------------------------------------------------------
# 3-layer signal router (F, In2, B). Does not touch L2/L4/L5.
# ---------------------------------------------------------------------------

_SIG = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)


def route_stripline(board) -> list:
    """Route non-power nets on F / L3 / B. Skip fine-pitch QFN pads."""
    VIA_R = getattr(board, "via_d", 0.45) / 2
    nx = int(round(board.w / G)) + 3
    ny = int(round(board.h / G)) + 3
    nlay = 3
    copper = [bytearray(nx * ny) for _ in range(nlay)]
    block = [bytearray(nx * ny) for _ in range(nlay)]
    ids = {}
    nxt = 1
    skip_refs = set(getattr(board, "route_skip_refs", ()) or ())
    power = set(getattr(board, "plane_nets", {}) or {"GND"})
    power |= {"GND", "+3V3", "+3V3_DIG", "+3V3_RF", "+5V_ALWAYS",
              "+1V8", "+1V8_AUDIO", "DVDD", "VBUS"}

    def nid(name: str) -> int:
        nonlocal nxt
        if name not in ids:
            ids[name] = nxt
            nxt += 1
        return ids[name]

    def idx(ix, iy):
        return iy * nx + ix

    def inside(ix, iy):
        return 0 <= ix < nx and 0 <= iy < ny

    def cell(x, y):
        return int(round(x / G)), int(round(y / G))

    # Block L3 cells over L4 gaps.
    for gx0, gx1 in getattr(board, "l4_gaps", []):
        ix0 = max(0, int(gx0 / G) - 1)
        ix1 = min(nx - 1, int(gx1 / G) + 1)
        for iy in range(ny):
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                copper[1][row + ix] = 255
                block[1][row + ix] = 255

    pads = []
    for part, fp in board.fps:
        ref = fp.GetReference()
        skip = ref in skip_refs
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net or net in power:
                continue
            if skip:
                continue
            bb = pad.GetBoundingBox()
            hw = pcbnew.ToMM(bb.GetWidth()) / 2
            hh = pcbnew.ToMM(bb.GetHeight()) / 2
            if hw < 0.18 or hh < 0.18:
                # QFN 0.4 mm pitch — leave to a later revision.
                continue
            x = pcbnew.ToMM(bb.GetX()) + pcbnew.ToMM(bb.GetWidth()) / 2
            y = pcbnew.ToMM(bb.GetY()) + pcbnew.ToMM(bb.GetHeight()) / 2
            attr = pad.GetAttribute()
            both = attr == pcbnew.PAD_ATTRIB_PTH or pad.IsOnLayer(pcbnew.B_Cu)
            layers = (0, 1, 2) if both else (0,)
            pads.append({"net": net, "id": nid(net), "x": x, "y": y, "hw": hw, "hh": hh, "layers": layers})

    def mark_rect(layer, x, y, hw, hh, val):
        ix0 = max(0, int((x - hw) / G) - 1)
        ix1 = min(nx - 1, int((x + hw) / G) + 1)
        iy0 = max(0, int((y - hh) / G) - 1)
        iy1 = min(ny - 1, int((y + hh) / G) + 1)
        grid = copper[layer]
        for iy in range(iy0, iy1 + 1):
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                if grid[row + ix] == 0:
                    grid[row + ix] = val

    for p in pads:
        for layer in p["layers"]:
            mark_rect(layer, p["x"], p["y"], p["hw"], p["hh"], p["id"])
        r = BODY
        for layer in range(nlay):
            mark_rect(layer, p["x"], p["y"], p["hw"] + r, p["hh"] + r, 254)

    # restore pad centres as own-id
    for p in pads:
        for layer in p["layers"]:
            mark_rect(layer, p["x"], p["y"], max(0.05, p["hw"] - 0.02), max(0.05, p["hh"] - 0.02), p["id"])

    by_net = {}
    for p in pads:
        by_net.setdefault(p["net"], []).append(p)

    def walkable(layer, ix, iy, owner):
        if not inside(ix, iy):
            return False
        v = copper[layer][idx(ix, iy)]
        return v in (0, owner)

    def bfs(start, targets, owner):
        sx, sy, sl = start
        heap = [(0, 0, sx, sy, sl)]
        prev = {}
        seen = set()
        best = None
        expands = 0
        tx, ty = next(iter(targets))[0], next(iter(targets))[1]
        while heap:
            f, cost, ix, iy, layer = heapq.heappop(heap)
            key = (ix, iy, layer)
            if key in seen:
                continue
            seen.add(key)
            if cost > 0 and (ix, iy, layer) in targets or (cost > 0 and (ix, iy) in {(t[0], t[1]) for t in targets}):
                best = key
                break
            expands += 1
            if expands > 250000:
                return None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if not walkable(layer, jx, jy, owner):
                    continue
                nk = (jx, jy, layer)
                if nk in seen:
                    continue
                step = cost + 1
                h = abs(jx - tx) + abs(jy - ty)
                prev[nk] = key
                heapq.heappush(heap, (step + h, step, jx, jy, layer))
            for ol in range(nlay):
                if ol == layer:
                    continue
                if not walkable(ol, ix, iy, owner):
                    continue
                nk = (ix, iy, ol)
                if nk in seen:
                    continue
                step = cost + 5
                h = abs(ix - tx) + abs(iy - ty)
                prev[nk] = key
                heapq.heappush(heap, (step + h, step, ix, iy, ol))
        if best is None:
            return None
        path = [best]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    def draw_path(path, netname):
        for (x1, y1, l1), (x2, y2, l2) in zip(path, path[1:]):
            if l1 != l2:
                add_via(board, x1 * G, y1 * G, netname, getattr(board, "via_d", 0.45), getattr(board, "via_drill", 0.2))
                continue
            t = pcbnew.PCB_TRACK(board.b)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1 * G), pcbnew.FromMM(y1 * G)))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2 * G), pcbnew.FromMM(y2 * G)))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(_SIG[l1])
            t.SetNet(board.nets[netname])
            board.b.Add(t)

    missing = []
    for net, pts in by_net.items():
        if len(pts) < 2:
            continue
        owner = nid(net)
        targets = {(cell(pts[0]["x"], pts[0]["y"])[0], cell(pts[0]["x"], pts[0]["y"])[1], 0)}
        ok = True
        for p in pts[1:]:
            six, siy = cell(p["x"], p["y"])
            path = bfs((six, siy, 0), targets, owner)
            if not path:
                ok = False
                break
            draw_path(path, net)
            for ix, iy, layer in path:
                targets.add((ix, iy, layer))
                copper[layer][idx(ix, iy)] = owner
        if not ok:
            missing.append(net)
    return missing
