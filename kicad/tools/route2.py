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

    def via_ok(ix, iy, myid, lattice=True):
        # Signal vias sit on a 0.4 mm lattice. Dedicated GND vias may use any cell.
        if lattice and (ix & 1 or iy & 1):
            return False
        x, y = mm(ix, iy)
        if not (0.9 < x < board.w - 0.9 and 0.9 < y < board.h - 0.9):
            return False
        i = idx(ix, iy)
        if via_keep[i]:
            return False
        for layer in (0, 1):
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    if ox * ox + oy * oy > 5:
                        continue
                    if not walkable(layer, ix + ox, iy + oy, myid):
                        return False
        # A 0.6 mm via needs more room than a 0.25 mm track. The track halo
        # is not enough next to a 0.65 mm TSSOP pad.
        need = VIA_R + CLEAR + 0.06
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

    def add_track(x1, y1, x2, y2, layer, netname):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            return
        t = pcbnew.PCB_TRACK(board.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(TRACK_W))
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

    def segment_clear(x1, y1, x2, y2, myid):
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
        return True

    # Fine-pitch fingers (TSSOP, USB-C) are too close for a track to wander
    # off their centreline. Draw that centreline out past the pin field first.
    for p in pads:
        short = min(p["hw"], p["hh"])
        long = max(p["hw"], p["hh"])
        if not p["smd"] or short > 0.36 or long < short * 2.2:
            continue
        long_x = p["hw"] >= p["hh"]
        away = (p["x"] - p["fx"]) if long_x else (p["y"] - p["fy"])
        primary = 1 if away >= 0 else -1
        placed_escape = False
        for sign in (primary, -primary):
            if placed_escape:
                break
            for extra in (1.7, 0.9):
                if long_x:
                    ex = p["x"] + sign * (p["hw"] + extra)
                    ey = p["y"]
                else:
                    ex = p["x"]
                    ey = p["y"] + sign * (p["hh"] + extra)
                if not (1.2 < ex < board.w - 1.2 and 1.2 < ey < board.h - 1.2):
                    continue
                if not segment_clear(p["x"], p["y"], ex, ey, p["id"]):
                    continue
                ix, iy = cell(ex, ey)
                i = idx(ix, iy)
                if copper[0][i] not in (0, p["id"]) or block[0][i] == EDGE:
                    continue
                add_track(p["x"], p["y"], ex, ey, 0, p["net"])
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
                if not segment_clear(x1, y1, x2, y2, a["id"]):
                    continue
                if not line_cells_ok(x1, y1, x2, y2, 0, a["id"]):
                    continue
                add_track(x1, y1, x2, y2, 0, net)
                steps = int(abs(x2 - x1) / G) + 1
                cells = [(*cell(x1 + (x2 - x1) * (s / max(steps, 1)), y1), 0) for s in range(steps + 1)]
                paint_path_cells(cells, a["id"])

    # One via per SMD GND pad, outward from the part, onto the bottom pour.
    gnd_id = ids.get("GND")
    failed_gnd = []
    if gnd_id and "GND" in board.nets:
        for p in pads:
            if p["net"] != "GND" or not p["smd"]:
                continue
            sx, sy = p.get("tip_mm", (p["x"], p["y"]))
            dx, dy = p["x"] - p["fx"], p["y"] - p["fy"]
            nrm = math.hypot(dx, dy)
            if nrm < 0.4:
                dirs = ((0, -1), (0, 1), (1, 0), (-1, 0))
            else:
                dirs = (
                    (dx / nrm, dy / nrm),
                    (0, -1),
                    (0, 1),
                    (1, 0),
                    (-1, 0),
                    (0.7, 0.7),
                    (0.7, -0.7),
                    (-0.7, 0.7),
                    (-0.7, -0.7),
                )
            placed = False
            for dist in (1.5, 2.0, 2.6, 3.2):
                for ux, uy in dirs:
                    scale = math.hypot(ux, uy) or 1
                    vx = sx + ux / scale * dist
                    vy = sy + uy / scale * dist
                    ix, iy = cell(vx, vy)
                    if not via_ok(ix, iy, gnd_id, lattice=False):
                        continue
                    x, y = mm(ix, iy)
                    if not line_cells_ok(sx, sy, x, y, 0, gnd_id):
                        continue
                    add_track(sx, sy, x, y, 0, "GND")
                    add_via(x, y, "GND")
                    copper[0][idx(*cell(sx, sy))] = gnd_id
                    copper[0][idx(ix, iy)] = gnd_id
                    copper[1][idx(ix, iy)] = gnd_id
                    paint_disc(x, y, gnd_id, VIA_R + CLEAR + TRACK_W / 2 + MARGIN)
                    steps = int(math.hypot(x - sx, y - sy) / G) + 1
                    stub = []
                    for s in range(steps + 1):
                        tt = s / max(steps, 1)
                        stub.append((*cell(sx + (x - sx) * tt, sy + (y - sy) * tt), 0))
                    paint_path_cells(stub, gnd_id)
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                failed_gnd.append(p)

    by_net = {}
    for p in pads:
        by_net.setdefault(p["net"], []).append(p)

    def bfs(starts, targets, myid):
        if not starts or not targets:
            return None
        target_set = set(targets)
        heap = []
        prev = {}
        seen = set()
        tx, ty, _tl = targets[0]
        for sx, sy, sl in starts:
            if (sx, sy, sl) in target_set:
                return [(sx, sy, sl)]
            heapq.heappush(heap, (0, 0, sx, sy, sl))
            prev[(sx, sy, sl)] = None
        expands = 0
        best = None
        while heap:
            _f, cost, ix, iy, layer = heapq.heappop(heap)
            key = (ix, iy, layer)
            if key in seen:
                continue
            seen.add(key)
            if cost > 0 and key in target_set:
                best = key
                break
            expands += 1
            if expands > 600000:
                return None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if not walkable(layer, jx, jy, myid):
                    continue
                nk = (jx, jy, layer)
                if nk in seen or nk in prev:
                    continue
                step = cost + (1 if layer == 0 else 3)
                h = abs(jx - tx) + abs(jy - ty)
                prev[nk] = key
                heapq.heappush(heap, (step + h, step, jx, jy, layer))
            ol = 1 - layer
            if via_ok(ix, iy, myid) and walkable(ol, ix, iy, myid):
                nk = (ix, iy, ol)
                if nk not in seen and nk not in prev:
                    step = cost + 25
                    h = abs(ix - tx) + abs(iy - ty)
                    prev[nk] = key
                    heapq.heappush(heap, (step + h, step, ix, iy, ol))
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
            horiz = b[1] == a[1]
            vert = b[0] == a[0]
            while j + 1 < len(path) and path[j + 1][2] == a[2]:
                nxtp = path[j + 1]
                if horiz and nxtp[1] == a[1]:
                    j += 1
                elif vert and nxtp[0] == a[0]:
                    j += 1
                else:
                    break
            add_track(*mm(a[0], a[1]), *mm(path[j][0], path[j][1]), a[2], netname)
            i = j
        paint_path_cells(path, myid)

    unrouted = []
    # GND pads that did not get a via still need a copper path to a PTH pad.
    if failed_gnd:
        group = by_net.get("GND", [])
        myid = gnd_id
        targets = []
        failed_ids = {id(p) for p in failed_gnd}
        for p in group:
            if id(p) in failed_ids:
                continue
            targets.extend(copper_cells(p))
        for p in failed_gnd:
            starts = copper_cells(p)
            path = bfs(starts, targets, myid) if targets else None
            if not path:
                unrouted.append("GND")
                break
            draw(path, "GND", myid)
            targets.extend(path)
            targets.extend(starts)

    nets = [n for n, ps in by_net.items() if n != "GND" and len(ps) >= 2]

    def span(n):
        xs = [p["x"] for p in by_net[n]]
        ys = [p["y"] for p in by_net[n]]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

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

    nets.sort(key=span)

    print(f"route {board.name}: {len(nets)} nets, {len(pads)} pads, gnd vias missing {len(failed_gnd)}", flush=True)
    for ni, n in enumerate(nets):
        if ni % 20 == 0:
            print(f"  {board.name} {ni}/{len(nets)} {n}", flush=True)
        group = by_net[n]
        myid = group[0]["id"]
        # Seed is the pad with the most copper cells (usually a PTH pad).
        group = sorted(group, key=lambda p: -len(copper_cells(p)))
        targets = copper_cells(group[0])
        if targets:
            stitch(group[0], targets[0][0], targets[0][1], targets[0][2], n)
        ok = bool(targets) or len(group) == 1
        for p in group[1:]:
            starts = copper_cells(p)
            if not starts:
                ok = False
                break
            path = bfs(starts, targets, myid)
            if not path:
                ok = False
                break
            draw(path, n, myid)
            stitch(p, path[0][0], path[0][1], path[0][2], n)
            targets.extend(path)
            targets.extend(starts)
        if not ok:
            unrouted.append(n)
    return unrouted
