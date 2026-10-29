"""2-layer router: signals on top, GND pour on the bottom.

Grid is 0.1 mm. A track center may sit only on a cell that is either its own
pad or far enough from foreign copper that the finished 0.25 mm track still
has 0.2 mm clearance, including the straight segment between cell centers.
Footprint keepouts (SHT40 body, Pico antenna) are blocked. Tracks are not
dropped after the search: if the grid allows a cell, the segment is drawn.
"""
from __future__ import annotations

import heapq
import math

import pcbnew

G = 0.1
TRACK_W = 0.25
CLEAR = 0.2
# Extra beyond the nominal clearance so a segment between two legal cells
# cannot clip a pad corner.
MARGIN = 0.08
BODY = CLEAR + TRACK_W / 2 + MARGIN
VIA_R = 0.3
VIA_DRILL = 0.3
EDGE = 255


def route_board(board) -> list:
    VIA_R = getattr(board, "via_d", 0.9) / 2
    VIA_DRILL = getattr(board, "via_drill", 0.5)
    # Cells around a new via centre that must be free, so the via disc keeps
    # CLEAR to foreign track halos (the halo only covers track centres).
    ring_r = max(2.2, (VIA_R - 0.2 + 0.1) / G)
    ring_span = int(math.ceil(ring_r))
    four = getattr(board, "layers", 2) >= 4 and not getattr(board, "outer_route", False)
    hat = "hat" in board.name
    diag = four or hat
    nx = int(round(board.w / G)) + 3
    ny = int(round(board.h / G)) + 3
    copper = [bytearray(nx * ny) for _ in range(2)]
    block = [bytearray(nx * ny) for _ in range(2)]
    via_keep = bytearray(nx * ny)
    ids = {}
    nxt = 1

    def nid(name: str) -> int:
        nonlocal nxt
        if name not in ids:
            if nxt >= 250:
                raise RuntimeError("too many nets for the router grid")
            ids[name] = nxt
            nxt += 1
        return ids[name]

    def idx(ix, iy):
        return iy * nx + ix

    def mm(ix, iy):
        return ix * G, iy * G

    def cell(x, y):
        return int(round(x / G)), int(round(y / G))

    def inside(ix, iy):
        return 0 <= ix < nx and 0 <= iy < ny

    pads = []
    obstacles = []
    holes = []
    for _part, fp in board.fps:
        fx = pcbnew.ToMM(fp.GetPosition().x)
        fy = pcbnew.ToMM(fp.GetPosition().y)
        for pad in fp.Pads():
            # Paste-only windows (exposed-pad apertures) are not copper.
            if not (pad.IsOnLayer(pcbnew.F_Cu) or pad.IsOnLayer(pcbnew.B_Cu)):
                continue
            pos = pad.GetPosition()
            bb = pad.GetBoundingBox()
            x = pcbnew.ToMM(bb.GetX()) + pcbnew.ToMM(bb.GetWidth()) / 2
            y = pcbnew.ToMM(bb.GetY()) + pcbnew.ToMM(bb.GetHeight()) / 2
            hw = pcbnew.ToMM(bb.GetWidth()) / 2
            hh = pcbnew.ToMM(bb.GetHeight()) / 2
            if hw < 0.05 or hh < 0.05:
                sz = pad.GetSize()
                x = pcbnew.ToMM(pos.x)
                y = pcbnew.ToMM(pos.y)
                hw = pcbnew.ToMM(sz.x) / 2
                hh = pcbnew.ToMM(sz.y) / 2
            attr = pad.GetAttribute()
            net = pad.GetNetname()
            drill = pad.GetDrillSize()
            drill_r = pcbnew.ToMM(max(drill.x, drill.y)) / 2
            if attr == pcbnew.PAD_ATTRIB_NPTH or not net:
                obstacles.append((x, y, hw, hh))
                holes.append((x, y, max(hw, hh, drill_r)))
                continue
            both = attr == pcbnew.PAD_ATTRIB_PTH or pad.IsOnLayer(pcbnew.B_Cu)
            layers = (0, 1) if both else (0,)
            pads.append(
                {
                    "ref": fp.GetReference(),
                    "num": pad.GetNumber(),
                    "net": net,
                    "id": nid(net),
                    "x": x,
                    "y": y,
                    "hw": hw,
                    "hh": hh,
                    "layers": layers,
                    "smd": attr != pcbnew.PAD_ATTRIB_PTH,
                    "fx": fx,
                    "fy": fy,
                    "drill_r": drill_r,
                    "shape": pad.GetShape(),
                }
            )
            if drill_r > 0.05:
                holes.append((x, y, drill_r))

    def mark_rect_cells(x, y, hw, hh, inset=0.0):
        x0, x1 = x - hw + inset, x + hw - inset
        y0, y1 = y - hh + inset, y + hh - inset
        if x1 < x0 or y1 < y0:
            return
        ix0 = max(0, int(math.ceil(x0 / G - 1e-6)))
        ix1 = min(nx - 1, int(math.floor(x1 / G + 1e-6)))
        iy0 = max(0, int(math.ceil(y0 / G - 1e-6)))
        iy1 = min(ny - 1, int(math.floor(y1 / G + 1e-6)))
        for iy in range(iy0, iy1 + 1):
            cy = iy * G
            if cy < y0 - 1e-9 or cy > y1 + 1e-9:
                continue
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                cx = ix * G
                if x0 - 1e-9 <= cx <= x1 + 1e-9:
                    yield row + ix, ix, iy

    def dist_rect(px, py, pad):
        dx = max(abs(px - pad["x"]) - pad["hw"], 0.0)
        dy = max(abs(py - pad["y"]) - pad["hh"], 0.0)
        return math.hypot(dx, dy)

    for p in pads:
        for layer in p["layers"]:
            grid = copper[layer]
            for i, _ix, _iy in mark_rect_cells(p["x"], p["y"], p["hw"], p["hh"]):
                grid[i] = p["id"]

    # Keepouts in board coordinates (Footprint.SetPosition already moved them).
    keep_polys = []
    for _part, fp in board.fps:
        try:
            zones = fp.Zones()
            count = zones.size()
        except Exception:
            continue
        for zi in range(count):
            zone = zones[zi]
            if not zone.GetDoNotAllowTracks() and not zone.GetDoNotAllowVias():
                continue
            try:
                lset = zone.GetLayerSet()
                on_f = bool(lset.Contains(pcbnew.F_Cu))
                on_b = bool(lset.Contains(pcbnew.B_Cu))
            except Exception:
                on_f, on_b = True, False
            outline = zone.Outline()
            n = outline.FullPointCount()
            if n < 3:
                continue
            pts = []
            for i in range(n):
                v = outline.CVertex(i)
                pts.append((pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)))
            keep_polys.append((outline, on_f, on_b, zone.GetDoNotAllowTracks(), zone.GetDoNotAllowVias(), pts))

    for outline, on_f, on_b, no_track, no_via, pts in keep_polys:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ix0 = max(0, int(min(xs) / G) - 1)
        ix1 = min(nx - 1, int(max(xs) / G) + 1)
        iy0 = max(0, int(min(ys) / G) - 1)
        iy1 = min(ny - 1, int(max(ys) / G) + 1)
        layers = []
        if no_track and on_f:
            layers.append(0)
        if no_track and on_b:
            layers.append(1)
        hits = []
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                x, y = mm(ix, iy)
                if not outline.PointInside(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))):
                    continue
                hits.append((ix, iy))
        track_r = TRACK_W / 2 + 0.22
        via_r = VIA_R + CLEAR
        for ix, iy in hits:
            span = int(math.ceil(max(track_r, via_r) / G)) + 1
            for oy in range(-span, span + 1):
                for ox in range(-span, span + 1):
                    jx, jy = ix + ox, iy + oy
                    if not inside(jx, jy):
                        continue
                    dist = math.hypot(ox * G, oy * G)
                    j = idx(jx, jy)
                    if no_via and dist <= via_r:
                        via_keep[j] = 1
                    if dist > track_r:
                        continue
                    for layer in layers:
                        if copper[layer][j] == 0:
                            copper[layer][j] = EDGE
                            block[layer][j] = EDGE

    def paint_halo(layer, x, y, hw, hh, myid, radius):
        ix0 = max(0, int((x - hw - radius) / G) - 1)
        ix1 = min(nx - 1, int((x + hw + radius) / G) + 1)
        iy0 = max(0, int((y - hh - radius) / G) - 1)
        iy1 = min(ny - 1, int((y + hh + radius) / G) + 1)
        grid_c = copper[layer]
        grid_b = block[layer]
        for iy in range(iy0, iy1 + 1):
            cy = iy * G
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                dx = max(abs(ix * G - x) - hw, 0.0)
                dy = max(abs(cy - y) - hh, 0.0)
                if dx * dx + dy * dy > radius * radius:
                    continue
                i = row + ix
                if grid_c[i] not in (0, myid):
                    continue
                cur = grid_b[i]
                if cur == 0 or cur == myid:
                    grid_b[i] = myid
                elif cur != EDGE:
                    grid_b[i] = EDGE

    for p in pads:
        for layer in p["layers"]:
            paint_halo(layer, p["x"], p["y"], p["hw"], p["hh"], p["id"], BODY)

    def force_obstacle(x, y, hw, hh):
        radius = CLEAR + TRACK_W / 2 + 0.08
        ix0 = max(0, int((x - hw - radius) / G) - 1)
        ix1 = min(nx - 1, int((x + hw + radius) / G) + 1)
        iy0 = max(0, int((y - hh - radius) / G) - 1)
        iy1 = min(ny - 1, int((y + hh + radius) / G) + 1)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                dx = max(abs(ix * G - x) - hw, 0.0)
                dy = max(abs(iy * G - y) - hh, 0.0)
                if dx * dx + dy * dy > radius * radius:
                    continue
                i = idx(ix, iy)
                for layer in (0, 1):
                    # NC and NPTH copper stays blocked even if a net halo claimed it.
                    if copper[layer][i] in (0, EDGE):
                        block[layer][i] = EDGE
                        if dx == 0 and dy == 0:
                            copper[layer][i] = EDGE

    for ox, oy, hw, hh in obstacles:
        force_obstacle(ox, oy, hw, hh)

    def paint_hole(x, y, r):
        radius = r + BODY
        ix0 = max(0, int((x - radius) / G) - 1)
        ix1 = min(nx - 1, int((x + radius) / G) + 1)
        iy0 = max(0, int((y - radius) / G) - 1)
        iy1 = min(ny - 1, int((y + radius) / G) + 1)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                dx = ix * G - x
                dy = iy * G - y
                d2 = dx * dx + dy * dy
                i = idx(ix, iy)
                if d2 <= (r + VIA_DRILL / 2 + CLEAR + 0.05) * (r + VIA_DRILL / 2 + CLEAR + 0.05):
                    via_keep[i] = 1
                if d2 <= (r + 0.05) * (r + 0.05):
                    for layer in (0, 1):
                        # Don't route across the drill. The annular ring stays usable.
                        block[layer][i] = EDGE
                        if copper[layer][i] == 0:
                            copper[layer][i] = EDGE
                elif d2 <= radius * radius:
                    for layer in (0, 1):
                        if copper[layer][i] == 0 and block[layer][i] == 0:
                            block[layer][i] = EDGE

    for hx, hy, hr in holes:
        paint_hole(hx, hy, hr)

    # Board edge. Track copper stays 0.3 mm inside the outline.
    edge = CLEAR + TRACK_W / 2 + 0.05
    for layer in (0, 1):
        for iy in range(ny):
            y = iy * G
            row = iy * nx
            for ix in range(nx):
                x = ix * G
                if x < edge or y < edge or x > board.w - edge or y > board.h - edge:
                    i = row + ix
                    if copper[layer][i] == 0:
                        copper[layer][i] = EDGE

    def walkable(layer, ix, iy, myid):
        if not inside(ix, iy):
            return False
        i = idx(ix, iy)
        c = copper[layer][i]
        b = block[layer][i]
        if c == EDGE or b == EDGE:
            return False
        if c not in (0, myid):
            return False
        if b not in (0, myid):
            return False
        return True

    def via_ok(ix, iy, myid, lattice=True, ring=True):
        # Signal vias sit on a 0.4 mm lattice. Dedicated GND vias may use any cell.
        if lattice and (ix & 1 or iy & 1):
            return False
        x, y = mm(ix, iy)
        if not (0.9 < x < board.w - 0.9 and 0.9 < y < board.h - 0.9):
            return False
        i = idx(ix, iy)
        if via_keep[i]:
            return False
        if ring:
            for layer in (0, 1):
                for oy in range(-ring_span, ring_span + 1):
                    for ox in range(-ring_span, ring_span + 1):
                        if ox * ox + oy * oy > ring_r * ring_r:
                            continue
                        if not walkable(layer, ix + ox, iy + oy, myid):
                            return False
        else:
            for layer in (0, 1):
                c = copper[layer][i]
                b = block[layer][i]
                if c not in (0, myid) or b == EDGE and c != myid:
                    return False
        # A 0.6 mm via needs more room than a 0.25 mm track. The track halo
        # is not enough next to a 0.65 mm TSSOP pad.
        need = VIA_R + CLEAR + TRACK_W / 2 + 0.08
        for q in pads:
            if q["id"] == myid:
                continue
            if abs(q["x"] - x) > q["hw"] + need + 0.2:
                continue
            if abs(q["y"] - y) > q["hh"] + need + 0.2:
                continue
            if dist_rect(x, y, q) < need:
                return False
        return True

    def paint_disc(x, y, myid, radius):
        ix0 = max(0, int((x - radius) / G) - 1)
        ix1 = min(nx - 1, int((x + radius) / G) + 1)
        iy0 = max(0, int((y - radius) / G) - 1)
        iy1 = min(ny - 1, int((y + radius) / G) + 1)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                if math.hypot(ix * G - x, iy * G - y) > radius:
                    continue
                i = idx(ix, iy)
                for layer in (0, 1):
                    c = copper[layer][i]
                    if c not in (0, myid):
                        continue
                    b = block[layer][i]
                    if b == 0 or b == myid:
                        block[layer][i] = myid
                    elif b != EDGE:
                        block[layer][i] = EDGE

    power_w = getattr(board, "power_w", 0.4)

    def add_track(x1, y1, x2, y2, layer, netname, width=None):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            return
        t = pcbnew.PCB_TRACK(board.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        wide = netname in {
            "+3V3", "+1V8", "+3V3A", "+3V3_MIC", "VSYS", "VSYS_IN", "VSYS_RAW", "VBUS", "DC",
        }
        if width is None:
            width = power_w if wide else TRACK_W
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNet(board.nets[netname])
        board.b.Add(t)

    def add_via(x, y, netname):
        v = pcbnew.PCB_VIA(board.b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(VIA_R * 2))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetNet(board.nets[netname])
        board.b.Add(v)

    def paint_path_cells(cells, myid):
        # Center-to-center clearance for two 0.25 mm tracks, plus margin so
        # the segment between cell centers still clears.
        radius = TRACK_W + CLEAR + MARGIN
        for ix, iy, layer in cells:
            x, y = mm(ix, iy)
            i = idx(ix, iy)
            if copper[layer][i] in (0, myid):
                copper[layer][i] = myid
            ix0 = max(0, ix - 8)
            ix1 = min(nx - 1, ix + 8)
            iy0 = max(0, iy - 8)
            iy1 = min(ny - 1, iy + 8)
            for jy in range(iy0, iy1 + 1):
                for jx in range(ix0, ix1 + 1):
                    if math.hypot((jx - ix) * G, (jy - iy) * G) > radius:
                        continue
                    j = idx(jx, jy)
                    if copper[layer][j] not in (0, myid):
                        continue
                    b = block[layer][j]
                    if b == 0 or b == myid:
                        block[layer][j] = myid
                    elif b != EDGE:
                        block[layer][j] = EDGE

    def copper_cells(p):
        if p.get("tip"):
            return [p["tip"]]
        found = []
        for layer in p["layers"]:
            grid = copper[layer]
            for i, ix, iy in mark_rect_cells(p["x"], p["y"], p["hw"], p["hh"]):
                if grid[i] != p["id"] or block[layer][i] == EDGE:
                    continue
                x, y = mm(ix, iy)
                dx = abs(x - p["x"])
                dy = abs(y - p["y"])
                if p["drill_r"] > 0.05 and math.hypot(dx, dy) <= p["drill_r"] + 0.05:
                    continue
                shape = p["shape"]
                if shape == pcbnew.PAD_SHAPE_CIRCLE:
                    if math.hypot(dx, dy) > p["hw"] - 0.02:
                        continue
                elif shape == pcbnew.PAD_SHAPE_OVAL:
                    rad = min(p["hw"], p["hh"])
                    if p["hw"] >= p["hh"]:
                        cx = max(dx - (p["hw"] - rad), 0.0)
                        if math.hypot(cx, dy) > rad - 0.02:
                            continue
                    else:
                        cy = max(dy - (p["hh"] - rad), 0.0)
                        if math.hypot(dx, cy) > rad - 0.02:
                            continue
                found.append((ix, iy, layer))
        if not found:
            for layer in p["layers"]:
                grid = copper[layer]
                for i, ix, iy in mark_rect_cells(p["x"], p["y"], p["hw"], p["hh"]):
                    if grid[i] == p["id"]:
                        found.append((ix, iy, layer))
                        break
                if found:
                    break
        return found

    def line_cells_ok(x1, y1, x2, y2, layer, myid):
        steps = int(math.hypot(x2 - x1, y2 - y1) / (G * 0.5)) + 1
        for s in range(steps + 1):
            t = s / max(steps, 1)
            ix, iy = cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if not walkable(layer, ix, iy, myid):
                return False
        return True

    def foreign_tracks(layer_mm=None):
        segs = []
        for t in board.b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                pos = t.GetPosition()
                try:
                    rw = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
                except Exception:
                    rw = VIA_R
                segs.append(
                    (
                        pcbnew.ToMM(pos.x),
                        pcbnew.ToMM(pos.y),
                        pcbnew.ToMM(pos.x),
                        pcbnew.ToMM(pos.y),
                        rw,
                        t.GetNetname(),
                        None,
                    )
                )
                continue
            if t.GetClass() != "PCB_TRACK":
                continue
            layer = 0 if t.GetLayer() == pcbnew.F_Cu else 1
            if layer_mm is not None and layer != layer_mm:
                continue
            a = t.GetStart()
            b = t.GetEnd()
            segs.append(
                (
                    pcbnew.ToMM(a.x),
                    pcbnew.ToMM(a.y),
                    pcbnew.ToMM(b.x),
                    pcbnew.ToMM(b.y),
                    pcbnew.ToMM(t.GetWidth()) / 2,
                    t.GetNetname(),
                    layer,
                )
            )
        return segs

    def point_seg_dist(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def segment_clear(x1, y1, x2, y2, myid, layer=0, netname=None):
        need = CLEAR + TRACK_W / 2 + 0.02
        steps = int(math.hypot(x2 - x1, y2 - y1) / 0.05) + 1
        for s in range(steps + 1):
            t = s / max(steps, 1)
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            for q in pads:
                if q["id"] == myid:
                    continue
                if dist_rect(x, y, q) < need:
                    return False
            for ox, oy, hw, hh in obstacles:
                dx = max(abs(x - ox) - hw, 0.0)
                dy = max(abs(y - oy) - hh, 0.0)
                if dx * dx + dy * dy < need * need:
                    return False
        for sx1, sy1, sx2, sy2, rw, other, olayer in foreign_tracks(layer):
            if netname and other == netname:
                continue
            if olayer is not None and olayer != layer:
                continue
            # Sample along the candidate and keep centre-to-track clearance.
            need_t = CLEAR + TRACK_W / 2 + rw + 0.02
            for s in range(steps + 1):
                t = s / max(steps, 1)
                x = x1 + (x2 - x1) * t
                y = y1 + (y2 - y1) * t
                if point_seg_dist(x, y, sx1, sy1, sx2, sy2) < need_t:
                    return False
        return True

    def fine_pitch(p):
        short = min(p["hw"], p["hh"])
        long = max(p["hw"], p["hh"])
        return p["smd"] and short <= 0.36 and long >= short * 2.2

    plane_nets = getattr(board, "plane_nets", None) or {"GND": None}

    # Fine-pitch fingers (TSSOP, USB-C) are too close for a track to wander
    # off their centreline. Draw that centreline out past the pin field first.
    # On four layers plane pins skip this: they drop a via under the body instead.
    no_escape = getattr(board, "no_escape", set())
    net_count = {}
    for p in pads:
        net_count[p["net"]] = net_count.get(p["net"], 0) + 1
    for p in pads:
        if not fine_pitch(p) or net_count[p["net"]] < 2:
            continue
        if four and p["net"] in plane_nets:
            continue
        if (p["ref"], p["num"]) in no_escape:
            continue
        long_x = p["hw"] >= p["hh"]
        away = (p["x"] - p["fx"]) if long_x else (p["y"] - p["fy"])
        primary = 1 if away >= 0 else -1
        placed_escape = False
        for sign in (primary, -primary):
            if placed_escape:
                break
            for extra in (1.2, 0.7, 0.4):
                if long_x:
                    ex = p["x"] + sign * (p["hw"] + extra)
                    ey = p["y"]
                else:
                    ex = p["x"]
                    ey = p["y"] + sign * (p["hh"] + extra)
                if not (1.2 < ex < board.w - 1.2 and 1.2 < ey < board.h - 1.2):
                    continue
                if not segment_clear(p["x"], p["y"], ex, ey, p["id"], 0, p["net"]):
                    continue
                ix, iy = cell(ex, ey)
                i = idx(ix, iy)
                if copper[0][i] not in (0, p["id"]) or block[0][i] == EDGE:
                    continue
                add_track(p["x"], p["y"], ex, ey, 0, p["net"], width=TRACK_W)
                steps = int(math.hypot(ex - p["x"], ey - p["y"]) / G) + 1
                cells = []
                for s in range(steps + 1):
                    tt = s / max(steps, 1)
                    cells.append((*cell(p["x"] + (ex - p["x"]) * tt, p["y"] + (ey - p["y"]) * tt), 0))
                paint_path_cells(cells, p["id"])
                copper[0][i] = p["id"]
                block[0][i] = p["id"]
                p["tip"] = (ix, iy, 0)
                p["tip_mm"] = (ex, ey)
                placed_escape = True
                break

    # Join tips of one net that landed on the same Y, when the corridor is free.
    tips_by_net = {}
    for p in pads:
        if p.get("tip_mm"):
            tips_by_net.setdefault(p["net"], []).append(p)
    for net, group in tips_by_net.items():
        rows = {}
        for p in group:
            rows.setdefault(round(p["tip_mm"][1], 2), []).append(p)
        for _y, row in rows.items():
            row.sort(key=lambda p: p["tip_mm"][0])
            for a, b in zip(row, row[1:]):
                x1, y1 = a["tip_mm"]
                x2, y2 = b["tip_mm"]
                if abs(x2 - x1) < 0.2:
                    continue
                if not segment_clear(x1, y1, x2, y2, a["id"], 0, net):
                    continue
                if not line_cells_ok(x1, y1, x2, y2, 0, a["id"]):
                    continue
                add_track(x1, y1, x2, y2, 0, net)
                steps = int(abs(x2 - x1) / G) + 1
                cells = [(*cell(x1 + (x2 - x1) * (s / max(steps, 1)), y1), 0) for s in range(steps + 1)]
                paint_path_cells(cells, a["id"])

    def place_vbus_bus():
        """USB-C VBUS cannot squeeze past adjacent GND. Bus them north first."""
        if board.name != "het68-pwr" or "VBUS" not in by_net:
            return False
        group = [p for p in by_net["VBUS"] if p["y"] < 26]
        if len(group) < 2:
            return False
        myid = group[0]["id"]
        bus_y = 20.8
        xs = sorted({round(p["x"], 2) for p in group})
        for x in xs:
            src = next(p for p in group if abs(p["x"] - x) < 0.05)
            if abs(src["y"] - bus_y) > 0.05:
                if not segment_clear(src["x"], src["y"], x, bus_y, myid, 0, "VBUS"):
                    return False
                add_track(src["x"], src["y"], x, bus_y, 0, "VBUS")
                steps = int(abs(src["y"] - bus_y) / G) + 1
                cells = [
                    (*cell(x, src["y"] + (bus_y - src["y"]) * (s / max(steps, 1))), 0)
                    for s in range(steps + 1)
                ]
                paint_path_cells(cells, myid)
        for x1, x2 in zip(xs, xs[1:]):
            if not segment_clear(x1, bus_y, x2, bus_y, myid, 0, "VBUS"):
                return False
            add_track(x1, bus_y, x2, bus_y, 0, "VBUS")
            steps = int(abs(x2 - x1) / G) + 1
            cells = [
                (*cell(x1 + (x2 - x1) * (s / max(steps, 1)), bus_y), 0)
                for s in range(steps + 1)
            ]
            paint_path_cells(cells, myid)
        print(f"  {board.name} early VBUS bus y={bus_y}", flush=True)
        return True

    by_net = {}
    for p in pads:
        by_net.setdefault(p["net"], []).append(p)
    place_vbus_bus()

    def paint_segment(x1, y1, x2, y2, layer, myid):
        steps = int(math.hypot(x2 - x1, y2 - y1) / (G * 0.5)) + 1
        cells = []
        for s in range(steps + 1):
            t = s / max(steps, 1)
            cells.append((*cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t), layer))
        paint_path_cells(cells, myid)

    def draw_poly(pts, layer, netname, width=None):
        myid = ids[netname]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            add_track(x1, y1, x2, y2, layer, netname, width=width)
            paint_segment(x1, y1, x2, y2, layer, myid)

    def place_via(x, y, netname):
        myid = ids[netname]
        add_via(x, y, netname)
        ix, iy = cell(x, y)
        copper[0][idx(ix, iy)] = myid
        copper[1][idx(ix, iy)] = myid
        paint_disc(x, y, myid, VIA_R + CLEAR + TRACK_W / 2 + MARGIN)

    def set_tip(p, x, y, layer=0):
        p["tip"] = (*cell(x, y), layer)
        p["tip_mm"] = (x, y)

    # Board-specific fixed copper (connector escapes, in-line ESD) before anything else.
    if hasattr(board, "prewire"):
        board.prewire(
            {
                "pads": pads,
                "by_net": by_net,
                "ids": ids,
                "draw_poly": draw_poly,
                "place_via": place_via,
                "set_tip": set_tip,
                "segment_clear": segment_clear,
            }
        )

    def is_exposed_pad(p):
        return min(p["hw"], p["hh"]) >= 0.42 and math.hypot(p["x"] - p["fx"], p["y"] - p["fy"]) < 0.3

    # One via per SMD pad of a plane net, outward from the part. On two layers
    # that is GND onto the bottom pour; on four it also covers the In2 rails.
    plane_fail = {}
    plane_vias = {}

    def fanout(vip_only):
        for pnet, allowed in plane_nets.items():
            pid = ids.get(pnet)
            if not pid or pnet not in board.nets:
                continue

            def ok_here(x, y, allowed=allowed):
                return allowed is None or allowed(x, y)

            fails = plane_fail.setdefault(pnet, [])
            for p in by_net.get(pnet, []):
                if not p["smd"] or p.get("plane_done"):
                    continue
                ix, iy = cell(p["x"], p["y"])
                vip = is_exposed_pad(p) if four else min(p["hw"], p["hh"]) > 0.4
                if vip and ok_here(*mm(ix, iy)) and via_ok(ix, iy, pid, lattice=False, ring=False):
                    place_via(*mm(ix, iy), pnet)
                    plane_vias.setdefault(pnet, []).append(mm(ix, iy))
                    p["plane_done"] = True
                    continue
                if vip_only:
                    continue
                if fanout_pad(p, pnet, pid, ok_here):
                    p["plane_done"] = True
                else:
                    fails.append(p)

    def fanout_pad(p, pnet, pid, ok_here):
        sx, sy = p.get("tip_mm", (p["x"], p["y"]))
        # A same-net plane via a short straight hop away is enough.
        if four:
            near = sorted(
                (math.hypot(vx - sx, vy - sy), vx, vy) for vx, vy in plane_vias.get(pnet, [])
            )
            for d, vx, vy in near:
                if d > 2.2:
                    break
                if line_cells_ok(sx, sy, vx, vy, 0, pid):
                    add_track(sx, sy, vx, vy, 0, pnet, width=TRACK_W)
                    paint_segment(sx, sy, vx, vy, 0, pid)
                    return True
        dx, dy = p["x"] - p["fx"], p["y"] - p["fy"]
        nrm = math.hypot(dx, dy)
        diag = ((0.7, 0.7), (0.7, -0.7), (-0.7, 0.7), (-0.7, -0.7))
        if nrm < 0.4:
            dirs = ((0, -1), (0, 1), (1, 0), (-1, 0)) + diag
        else:
            dirs = ((dx / nrm, dy / nrm), (0, -1), (0, 1), (1, 0), (-1, 0)) + diag
        tries = [(dist, d) for dist in (0.9, 1.2, 1.6, 2.2, 3.0, 4.2, 5.5, 7.0) for d in dirs]
        if four and fine_pitch(p) and nrm >= 0.4:
            # Fine-pitch plane pin: via under the package body, clear of the
            # signal fingers that escape outwards.
            inward = (-dx / nrm, -dy / nrm)
            tries = [(dist, inward) for dist in (1.5, 1.8, 2.1, 2.5, 2.9)] + tries
        for dist, (ux, uy) in tries:
            scale = math.hypot(ux, uy) or 1
            ix, iy = cell(sx + ux / scale * dist, sy + uy / scale * dist)
            x, y = mm(ix, iy)
            if not ok_here(x, y):
                continue
            if not via_ok(ix, iy, pid, lattice=False):
                continue
            if not line_cells_ok(sx, sy, x, y, 0, pid):
                continue
            add_track(sx, sy, x, y, 0, pnet, width=TRACK_W)
            copper[0][idx(*cell(sx, sy))] = pid
            place_via(x, y, pnet)
            plane_vias.setdefault(pnet, []).append((x, y))
            paint_segment(sx, sy, x, y, 0, pid)
            return True
        return False

    # On four layers exposed pads take their via first, so neighbouring pins
    # of the same net can share it.
    if four:
        fanout(vip_only=True)
    fanout(vip_only=False)

    # 8-connected search so fine-pitch bundles fan out at 45 deg.
    # Costs are in tenths of a cell; a diagonal step costs 14.
    if diag:
        moves = ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10),
                 (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14))
        unit = 10
    else:
        moves = ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1))
        unit = 1

    def heur(ix, iy, tx, ty):
        ax, ay = abs(ix - tx), abs(iy - ty)
        if diag:
            return 10 * max(ax, ay) + 4 * min(ax, ay)
        return ax + ay

    def bfs(starts, targets, myid, via_cost=20, limit=500000, back_cost=3):
        if not starts or not targets:
            return None
        target_set = set(targets)
        sx0, sy0, _sl0 = starts[0]
        tx, ty, _tl = min(targets, key=lambda t: abs(t[0] - sx0) + abs(t[1] - sy0))
        heap = []
        prev = {}
        best_cost = {}
        for sx, sy, sl in starts:
            if (sx, sy, sl) in target_set:
                return [(sx, sy, sl)]
            key = (sx, sy, sl)
            heapq.heappush(heap, (0, 0, sx, sy, sl))
            best_cost[key] = 0
            prev[key] = None
        expands = 0
        best = None
        while heap:
            _f, cost, ix, iy, layer = heapq.heappop(heap)
            key = (ix, iy, layer)
            if cost != best_cost.get(key):
                continue
            if cost > 0 and key in target_set:
                best = key
                break
            expands += 1
            if expands > limit:
                return None
            lc = 1 if layer == 0 else back_cost
            for dx, dy, mc in moves:
                jx, jy = ix + dx, iy + dy
                if not walkable(layer, jx, jy, myid):
                    continue
                # No corner cutting between two blocked cells.
                if dx and dy and not (walkable(layer, ix + dx, iy, myid) and walkable(layer, ix, iy + dy, myid)):
                    continue
                nk = (jx, jy, layer)
                step = cost + mc * lc
                if step >= best_cost.get(nk, 1 << 30):
                    continue
                prev[nk] = key
                best_cost[nk] = step
                heapq.heappush(heap, (step + heur(jx, jy, tx, ty), step, jx, jy, layer))
            ol = 1 - layer
            if via_ok(ix, iy, myid) and walkable(ol, ix, iy, myid):
                nk = (ix, iy, ol)
                step = cost + via_cost * unit
                if step < best_cost.get(nk, 1 << 30):
                    prev[nk] = key
                    best_cost[nk] = step
                    heapq.heappush(heap, (step + heur(ix, iy, tx, ty), step, ix, iy, ol))
        if best is None:
            return None
        path = [best]
        while prev.get(path[-1]) is not None:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    def draw(path, netname, myid):
        if not path or len(path) < 2:
            paint_path_cells(path, myid)
            return
        i = 0
        while i < len(path) - 1:
            a = path[i]
            b = path[i + 1]
            if a[2] != b[2]:
                x, y = mm(a[0], a[1])
                add_via(x, y, netname)
                paint_disc(x, y, myid, VIA_R + CLEAR + TRACK_W / 2 + MARGIN)
                copper[0][idx(a[0], a[1])] = myid
                copper[1][idx(a[0], a[1])] = myid
                i += 1
                continue
            j = i + 1
            step_d = (b[0] - a[0], b[1] - a[1])
            while j + 1 < len(path) and path[j + 1][2] == a[2]:
                nxtp = path[j + 1]
                if (nxtp[0] - path[j][0], nxtp[1] - path[j][1]) == step_d:
                    j += 1
                else:
                    break
            add_track(*mm(a[0], a[1]), *mm(path[j][0], path[j][1]), a[2], netname)
            i = j
        paint_path_cells(path, myid)

    def stitch(p, ix, iy, layer, netname):
        if p.get("tip"):
            return
        x, y = mm(ix, iy)
        # Stay on the pad centreline. A diagonal off a 0.4 mm pad clips the next pin.
        maxx = max(p["hw"] - TRACK_W / 2 - 0.03, 0.0)
        maxy = max(p["hh"] - TRACK_W / 2 - 0.03, 0.0)
        dx = min(max(x - p["x"], -maxx), maxx)
        dy = min(max(y - p["y"], -maxy), maxy)
        if abs(dx) >= abs(dy):
            add_track(p["x"], p["y"], p["x"] + dx, p["y"], layer, netname)
        else:
            add_track(p["x"], p["y"], p["x"], p["y"] + dy, layer, netname)

    unrouted = []

    def plane_fallback():
        # Plane pads that did not get a via still need a copper path to a pad that did.
        for pnet, fails in plane_fail.items():
            if not fails:
                continue
            print(
                f"  {pnet} via fail "
                + ", ".join(f"{p['x']:.1f},{p['y']:.1f}" for p in fails),
                flush=True,
            )
            group = by_net.get(pnet, [])
            myid = ids[pnet]
            targets = []
            failed_ids = {id(p) for p in fails}
            for p in group:
                if id(p) in failed_ids:
                    continue
                targets.extend(copper_cells(p))
            for p in fails:
                starts = copper_cells(p)
                path = bfs(starts, targets, myid, 12 if diag else 20, 300000, 1 if diag else 3) if targets else None
                if not path:
                    unrouted.append(pnet)
                    continue
                draw(path, pnet, myid)
                stitch(p, path[0][0], path[0][1], path[0][2], pnet)
                targets.extend(path)
                targets.extend(starts)

    plane_fallback()

    nets = [n for n, ps in by_net.items() if n not in plane_nets and len(ps) >= 2]

    def span(n):
        xs = [p["x"] for p in by_net[n]]
        ys = [p["y"] for p in by_net[n]]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    power_names = {
        "+3V3", "+1V8", "+3V3A", "+3V3_MIC",
        "VSYS", "VSYS_IN", "VSYS_RAW", "VBUS", "DC", "AC1", "AC1F", "AC2",
    }
    power = [n for n in nets if n in power_names or n.startswith("+")]
    signal = [n for n in nets if n not in power]
    power.sort(key=span)
    signal.sort(key=span)

    # Multi-pad nets that stopped half way keep their tree; a later pass only
    # connects the pads that are still missing.
    resume = {}
    keep_partial = diag

    def route_nets(names, via_cost, limit, back_cost):
        failed = []
        for ni, n in enumerate(names):
            if ni % 15 == 0:
                print(f"  {board.name} {ni}/{len(names)} {n}", flush=True)
            group = list(by_net[n])
            myid = group[0]["id"]
            c_snap = (copper[0][:], copper[1][:])
            b_snap = (block[0][:], block[1][:])
            # KiCad returns a fresh Python wrapper per GetTracks() call, so id(t)
            # is unstable — rip-up by UUID or every prior net's copper vanishes.
            before = {t.m_Uuid.AsString() for t in board.b.GetTracks()}
            if n in resume:
                targets, pending = resume.pop(n)
            else:
                seed = max(group, key=lambda p: len(copper_cells(p)))
                targets = copper_cells(seed)
                if not targets:
                    failed.append(n)
                    continue
                stitch(seed, targets[0][0], targets[0][1], targets[0][2], n)
                pending = [p for p in group if p is not seed]
            while pending:
                def score(p, targets=targets):
                    cells = copper_cells(p)
                    if not cells:
                        return 10 ** 9
                    step_t = max(1, len(targets) // 30)
                    step_s = max(1, len(cells) // 3)
                    best = 10 ** 9
                    for sx, sy, _sl in cells[::step_s]:
                        for tx, ty, _tl in targets[::step_t]:
                            d = abs(sx - tx) + abs(sy - ty)
                            if d < best:
                                best = d
                    return best

                pending.sort(key=score)
                progressed = False
                still = []
                target_set = set(targets)
                for i, p in enumerate(pending):
                    starts = copper_cells(p)
                    if not starts:
                        still.append(p)
                        continue
                    # Pad copper already touches the grown net — only skip drawing
                    # when a start cell is literally already a target cell.
                    if any(s in target_set for s in starts):
                        targets.extend(starts)
                        progressed = True
                        still.extend(pending[i + 1 :])
                        break
                    path = bfs(starts, targets, myid, via_cost, limit, back_cost)
                    if not path:
                        still.append(p)
                        continue
                    # Always materialize the path. Skipping draw when the grid is
                    # already painted myid left HAT with "routed" nets and no copper.
                    draw(path, n, myid)
                    stitch(p, path[0][0], path[0][1], path[0][2], n)
                    targets.extend(path)
                    targets.extend(starts)
                    target_set = set(targets)
                    progressed = True
                    still.extend(pending[i + 1 :])
                    break
                pending = still
                if not progressed:
                    break
            if pending:
                pts = ", ".join(
                    f"{p['x']:.1f},{p['y']:.1f}" for p in pending[:8]
                )
                print(f"  open {n} {len(pending)}/{len(group)} {pts}", flush=True)
                if keep_partial and len(group) >= 3 and len(pending) < len(group) - 1:
                    resume[n] = (targets, pending)
                # Keep whatever copper did connect. Ripping it up left whole
                # nets open when only one pad was blocked.
                failed.append(n)
        return failed

    print(
        f"route {board.name}: {len(nets)} nets, {len(pads)} pads, gnd vias missing {len(plane_fail.get('GND', []))}",
        flush=True,
    )
    if "hat" in board.name:
        sig_lim, sig_retry, pwr_lim, pwr_retry = 400000, 900000, 350000, 800000
    else:
        sig_lim, sig_retry, pwr_lim, pwr_retry = 100000, 220000, 150000, 300000

    if diag:
        # B.Cu is a full signal layer; a via is a short detour. Signals first
        # so supply stubs next to fine-pitch outputs do not wall them in.
        first = [n for n in getattr(board, "route_first", []) if n in by_net and n in nets]
        power = [n for n in power if n not in first]
        signal = [n for n in signal if n not in first]
        order = first + signal + power
        missed = route_nets(order, 14, sig_lim, 1)
        for attempt, (vc, lim) in enumerate(((8, sig_retry), (5, sig_retry * 2)), start=1):
            if not missed:
                break
            print(f"  {board.name} retry {attempt} {missed}", flush=True)
            missed = route_nets(missed, vc, lim, 1)
        sig_miss = []
    else:
        # Local nets first, while the top is still open. Power then uses the back.
        sig_miss = route_nets(signal, 22, sig_lim, 6)
        if sig_miss:
            print(f"  {board.name} signal retry {sig_miss}", flush=True)
            sig_miss = route_nets(sig_miss, 8, sig_retry, 1)
        missed = route_nets(power, 5, pwr_lim, 1)
        if missed:
            print(f"  {board.name} power retry {missed}", flush=True)
            missed = route_nets(missed, 3, pwr_retry, 1)
    unrouted.extend(missed)
    unrouted.extend(sig_miss)

    # USB-C VBUS pads sit 0.8 mm from GND. Escape north to a bus under C3.
    if "VBUS" in by_net and board.name == "het68-pwr":
        group = [p for p in by_net["VBUS"] if p["y"] < 26]
        if len(group) >= 2:
            myid = group[0]["id"]
            bus_y = 20.8
            xs = sorted({round(p["x"], 2) for p in group})
            ok = True
            for x in xs:
                src = next(p for p in group if abs(p["x"] - x) < 0.05)
                if abs(src["y"] - bus_y) > 0.05:
                    if not segment_clear(src["x"], src["y"], x, bus_y, myid, 0, "VBUS"):
                        ok = False
                        break
                    add_track(src["x"], src["y"], x, bus_y, 0, "VBUS")
            if ok and len(xs) >= 2:
                for x1, x2 in zip(xs, xs[1:]):
                    if not segment_clear(x1, bus_y, x2, bus_y, myid, 0, "VBUS"):
                        ok = False
                        break
                    add_track(x1, bus_y, x2, bus_y, 0, "VBUS")
            if ok:
                print(f"  {board.name} VBUS bus y={bus_y}", flush=True)
                unrouted = [n for n in unrouted if n != "VBUS"]
            else:
                print(f"  {board.name} VBUS bus failed", flush=True)

    # Direct L-stitch for leftover nets with track clearance.
    still = []
    for n in list(dict.fromkeys(unrouted)):
        if n == "GND":
            still.append(n)
            continue
        group = list(by_net.get(n, []))
        if len(group) < 2:
            still.append(n)
            continue
        myid = group[0]["id"]
        hub = max(group, key=lambda p: p["hw"] * p["hh"])
        ok = True
        for p in group:
            if p is hub:
                continue
            paths = [
                [(p["x"], p["y"]), (hub["x"], p["y"]), (hub["x"], hub["y"])],
                [(p["x"], p["y"]), (p["x"], hub["y"]), (hub["x"], hub["y"])],
                [(p["x"], p["y"]), (hub["x"], hub["y"])],
            ]
            drawn = False
            for pts in paths:
                clear = True
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
                        continue
                    if not segment_clear(x1, y1, x2, y2, myid, 0, n):
                        clear = False
                        break
                if not clear:
                    continue
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    add_track(x1, y1, x2, y2, 0, n)
                drawn = True
                break
            if not drawn:
                ok = False
                break
        if ok:
            print(f"  {board.name} direct stitch {n}", flush=True)
        else:
            still.append(n)
    return still
