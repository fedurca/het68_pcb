"""2-layer router: signals on top, GND pour on the bottom.

Track centers stay clearance + half-width away from foreign copper, so a
via cannot land on the next pad of a fine-pitch part.
"""
from __future__ import annotations

import heapq
from array import array

import pcbnew

G = 0.2
TRACK_W = 0.25
POWER_W = 0.45
CLEAR = 0.2
# How far a track center must stay from foreign copper.
EXPAND = CLEAR + TRACK_W / 2
EDGE = 65000
TRACK = 64000


def route_board(board) -> list:
    nx = int(board.w / G) + 4
    ny = int(board.h / G) + 4
    own = [array("H", [0]) * (nx * ny) for _ in range(2)]
    ids = {}
    nxt = 1

    def nid(name: str) -> int:
        nonlocal nxt
        if name not in ids:
            ids[name] = nxt
            nxt += 1
        return ids[name]

    def idx(ix, iy):
        return iy * nx + ix

    def cell(x, y):
        return int(round(x / G)), int(round(y / G))

    def mm(ix, iy):
        return ix * G, iy * G

    def mark(layer, x0, y0, x1, y1, val, force=False):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        ix0 = max(0, int(xa / G))
        ix1 = min(nx - 1, int(xb / G))
        iy0 = max(0, int(ya / G))
        iy1 = min(ny - 1, int(yb / G))
        grid = own[layer]
        for iy in range(iy0, iy1 + 1):
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                cur = grid[row + ix]
                if force or cur == 0:
                    grid[row + ix] = val

    pads = []  # dicts
    holes = []
    for _part, fp in board.fps:
        fx = pcbnew.ToMM(fp.GetPosition().x)
        fy = pcbnew.ToMM(fp.GetPosition().y)
        for pad in fp.Pads():
            pos = pad.GetPosition()
            sz = pad.GetSize()
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            hw = pcbnew.ToMM(sz.x) / 2
            hh = pcbnew.ToMM(sz.y) / 2
            attr = pad.GetAttribute()
            net = pad.GetNetname()
            if attr == pcbnew.PAD_ATTRIB_NPTH or not net:
                holes.append((x, y, max(hw, hh) + 0.35))
                for layer in (0, 1):
                    mark(layer, x - hw - 0.45, y - hh - 0.45, x + hw + 0.45, y + hh + 0.45, EDGE, True)
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
                }
            )

    for p in pads:
        for layer in p["layers"]:
            mark(layer, p["x"] - p["hw"], p["y"] - p["hh"], p["x"] + p["hw"], p["y"] + p["hh"], p["id"], True)
    for p in pads:
        for layer in p["layers"]:
            mark(
                layer,
                p["x"] - p["hw"] - EXPAND,
                p["y"] - p["hh"] - EXPAND,
                p["x"] + p["hw"] + EXPAND,
                p["y"] + p["hh"] + EXPAND,
                p["id"],
            )
    for layer in (0, 1):
        mark(layer, -1, -1, board.w + 1, 0.6, EDGE, True)
        mark(layer, -1, board.h - 0.6, board.w + 1, board.h + 1, EDGE, True)
        mark(layer, -1, -1, 0.6, board.h + 1, EDGE, True)
        mark(layer, board.w - 0.6, -1, board.w + 1, board.h + 1, EDGE, True)

    by_net = {}
    for p in pads:
        by_net.setdefault(p["net"], []).append(p)

    def segment_hits(x1, y1, x2, y2, netname, width):
        need = CLEAR + width / 2
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) / 0.1) + 1
        for s in range(steps + 1):
            t = s / max(steps, 1)
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            for p in pads:
                if p["net"] == netname:
                    continue
                dx = max(abs(x - p["x"]) - p["hw"], 0)
                dy = max(abs(y - p["y"]) - p["hh"], 0)
                if dx * dx + dy * dy < need * need:
                    return True
            for hx, hy, hr in holes:
                dx = x - hx
                dy = y - hy
                if dx * dx + dy * dy < (hr + need) * (hr + need):
                    return True
        return False

    def add_track(x1, y1, x2, y2, layer, netname, width):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            return
        if segment_hits(x1, y1, x2, y2, netname, width):
            return
        t = pcbnew.PCB_TRACK(board.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNet(board.nets[netname])
        board.b.Add(t)

    def add_via(x, y, netname):
        v = pcbnew.PCB_VIA(board.b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(0.6))
        v.SetDrill(pcbnew.FromMM(0.3))
        v.SetNet(board.nets[netname])
        board.b.Add(v)

    def paint(ix, iy, layers):
        r = int(EXPAND / G) + 1
        for oy in range(-r, r + 1):
            for ox in range(-r, r + 1):
                if (ox * ox + oy * oy) > r * r:
                    continue
                jx, jy = ix + ox, iy + oy
                if not (0 <= jx < nx and 0 <= jy < ny):
                    continue
                for layer in layers:
                    i = idx(jx, jy)
                    if own[layer][i] == 0:
                        own[layer][i] = TRACK

    def walkable(layer, ix, iy, myid, targets):
        if not (0 <= ix < nx and 0 <= iy < ny):
            return False
        if (ix, iy, layer) in targets or (ix, iy) in targets:
            return True
        v = own[layer][idx(ix, iy)]
        return v == 0 or v == myid

    def bfs(start, targets, myid):
        sx, sy = start
        if not targets:
            return None
        tx, ty = next(iter(targets))[:2]
        heap = [(0, 0, sx, sy, 0)]
        prev = {}
        seen = set()
        best = None
        expands = 0
        while heap:
            _f, cost, ix, iy, layer = heapq.heappop(heap)
            key = (ix, iy, layer)
            if key in seen:
                continue
            seen.add(key)
            if cost > 0 and ((ix, iy) in targets or (ix, iy, layer) in targets):
                best = key
                break
            expands += 1
            if expands > 350000:
                return None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if not walkable(layer, jx, jy, myid, targets):
                    continue
                nk = (jx, jy, layer)
                if nk in seen:
                    continue
                step = cost + 1
                h = abs(jx - tx) + abs(jy - ty)
                prev[nk] = key
                heapq.heappush(heap, (step + h, step, jx, jy, layer))
            ol = 1 - layer
            if walkable(ol, ix, iy, myid, targets) and own[0][idx(ix, iy)] in (0, myid) and own[1][idx(ix, iy)] in (0, myid):
                nk = (ix, iy, ol)
                if nk not in seen:
                    step = cost + 8
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

    def copper_cells(p):
        cells = set()
        ix0 = max(0, int((p["x"] - p["hw"]) / G))
        ix1 = min(nx - 1, int((p["x"] + p["hw"]) / G))
        iy0 = max(0, int((p["y"] - p["hh"]) / G))
        iy1 = min(ny - 1, int((p["y"] + p["hh"]) / G))
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                cells.add((ix, iy))
        return cells

    def draw(path, netname, width):
        if not path or len(path) < 2:
            return
        # merge collinear runs on one layer
        run = [path[0]]
        for a, b in zip(path, path[1:]):
            if a[2] != b[2]:
                _flush(run, netname, width)
                add_via(*mm(a[0], a[1]), netname)
                paint(a[0], a[1], (0, 1))
                run = [b]
            else:
                run.append(b)
        _flush(run, netname, width)
        for ix, iy, layer in path:
            paint(ix, iy, (layer,))

    def _flush(run, netname, width):
        if len(run) < 2:
            return
        layer = run[0][2]
        x1, y1 = mm(run[0][0], run[0][1])
        x2, y2 = mm(run[-1][0], run[-1][1])
        # only if the run is straight; otherwise segment it
        straight = all(p[0] == run[0][0] or p[1] == run[0][1] for p in run)
        if straight:
            add_track(x1, y1, x2, y2, layer, netname, width)
            return
        for a, b in zip(run, run[1:]):
            add_track(*mm(a[0], a[1]), *mm(b[0], b[1]), a[2], netname, width)

    # GND vias, outward from the part, never on a foreign pad.
    for p in pads:
        if p["net"] != "GND" or not p["smd"]:
            continue
        dx, dy = p["x"] - p["fx"], p["y"] - p["fy"]
        nrm = (dx * dx + dy * dy) ** 0.5
        if nrm < 0.3:
            dx, dy, nrm = 0, -1, 1
        placed = False
        for dist in (1.8, 2.4, 3.0):
            for ux, uy in ((dx / nrm, dy / nrm), (0, 1), (0, -1), (1, 0), (-1, 0)):
                vx = p["x"] + ux * dist
                vy = p["y"] + uy * dist
                if not (1.2 < vx < board.w - 1.2 and 1.2 < vy < board.h - 1.2):
                    continue
                if segment_hits(p["x"], p["y"], vx, vy, "GND", TRACK_W):
                    continue
                ix, iy = cell(vx, vy)
                if own[0][idx(ix, iy)] not in (0, p["id"]):
                    continue
                if own[1][idx(ix, iy)] not in (0, p["id"]):
                    continue
                add_track(p["x"], p["y"], vx, vy, 0, "GND", TRACK_W)
                add_via(vx, vy, "GND")
                paint(ix, iy, (0, 1))
                placed = True
                break
            if placed:
                break

    unrouted = []
    nets = [n for n, ps in by_net.items() if n != "GND" and len(ps) >= 2]

    def span(n):
        xs = [p["x"] for p in by_net[n]]
        ys = [p["y"] for p in by_net[n]]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    powerish = {"+3V3", "+3V3A", "+3V3_MIC", "+1V8", "VSYS", "VSYS_IN", "VBUS", "DC"}
    nets.sort(key=lambda n: (0 if n in powerish else 1, span(n)))

    for n in nets:
        width = POWER_W if n in powerish else TRACK_W
        group = by_net[n]
        myid = group[0]["id"]
        targets = copper_cells(group[0])
        ok = True
        for p in group[1:]:
            start = cell(p["x"], p["y"])
            path = bfs(start, targets, myid)
            if not path:
                ok = False
                break
            draw(path, n, width)
            targets |= set((ix, iy) for ix, iy, _layer in path)
            targets |= copper_cells(p)
        if not ok:
            unrouted.append(n)
    return unrouted
