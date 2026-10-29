"""Close ratsnest gaps that are two stubs of the same net.

The grid router stops a few tenths of a millimetre short, or leaves the
track on the opposite layer from a pad that was moved to the back.
This pass draws the missing segment, an L, or a via between those ends.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from heapq import heappop, heappush
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finish_route import Finish, _bbox, _bbox_gap, _gap, _hypot, _mm, dist_point_opad, dist_point_seg

CLEAR = 0.20
GSTEP = 0.25
MAX_DIST = 85.0


# Through-hole copper hits the outer layers and, on a 6-layer board, SIG_L3.
THROUGH = (0, 1, 6)


def _layers(it):
    if it[0] == "seg":
        return (it[6],)
    if it[0] == "via" or it[5] == 2:
        return THROUGH
    return (it[5],)


def _ends(it):
    if it[0] == "seg":
        return ((it[1], it[2], it[6]), (it[3], it[4], it[6]))
    if it[0] == "via":
        return ((it[1], it[2], 0), (it[1], it[2], 1))
    return tuple((it[1], it[2], layer) for layer in _layers(it))


class Space:
    def __init__(self, items, blocks, width, w, h, keepout):
        self.width = width
        self.half = width / 2
        self.need = self.half + CLEAR
        self.w, self.h = w, h
        self.keepout = keepout
        self.track_keep = []
        self.via_keep = []
        self.signal = None
        self.bins = defaultdict(list)
        self._add_all(items, None)
        for it in blocks:
            self._put(it, None)

    def _put(self, it, net):
        box = _bbox(it)
        x0, y0, x1, y1 = box
        for ix in range(int(x0 // 2) - 1, int(x1 // 2) + 2):
            for iy in range(int(y0 // 2) - 1, int(y1 // 2) + 2):
                self.bins[(ix, iy)].append((net, it))

    def _add_all(self, items, net):
        for it in items:
            self._put(it, net)

    def add(self, it, net):
        self._put(it, net)

    def _near(self, x, y):
        ix, iy = int(x // 2), int(y // 2)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from self.bins.get((ix + dx, iy + dy), ())

    def _dist(self, x, y, it):
        if it[0] == "pad":
            return dist_point_opad(x, y, it)
        if it[0] == "seg":
            return dist_point_seg(x, y, it[1], it[2], it[3], it[4]) - it[5]
        return _hypot(x - it[1], y - it[2]) - it[3]

    def blocked(self, x, y, layer, net):
        if x < 0.5 or y < 0.5 or x > self.w - 0.5 or y > self.h - 0.5:
            return True
        if layer == 6:
            for a, b in self.keepout:
                if a <= x <= b:
                    return True
        if _inside_keepout(self.track_keep, x, y, layer):
            return True
        for onet, it in self._near(x, y):
            if onet == net:
                continue
            if layer not in _layers(it):
                continue
            if self._dist(x, y, it) < self.need:
                return True
        return False

    def segment_ok(self, x1, y1, x2, y2, layer, net, slack=0.0):
        length = _hypot(x2 - x1, y2 - y1)
        n = max(1, int(length / 0.12))
        for i in range(n + 1):
            t = i / n
            if slack and length and min(t, 1 - t) * length < slack:
                continue
            if self.blocked(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, layer, net):
                return False
        return True

    def via_ok(self, x, y, net, via_r):
        if x < 0.8 or y < 0.8 or x > self.w - 0.8 or y > self.h - 0.8:
            return False
        for a, b in self.keepout:
            if a - via_r <= x <= b + via_r:
                return False
        if _inside_keepout(self.via_keep, x, y, None):
            return False
        need = via_r + CLEAR
        for onet, it in self._near(x, y):
            if onet == net:
                continue
            if self._dist(x, y, it) < need:
                return False
        return True


def _comps(items):
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i, a in enumerate(items):
        ba = _bbox(a)
        for j in range(i):
            if _bbox_gap(ba, _bbox(items[j])) > 0.5:
                continue
            la, lb = set(_layers(a)), set(_layers(items[j]))
            if not (la & lb):
                continue
            if _gap(a, items[j]) <= 0.0:
                union(i, j)
    groups = defaultdict(list)
    for i in range(len(items)):
        groups[find(i)].append(i)
    return list(groups.values())


def _draw_seg(board, x1, y1, x2, y2, layer, net, width):
    if _hypot(x2 - x1, y2 - y1) < 0.04:
        return None
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    t.SetWidth(pcbnew.FromMM(width))
    t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu if layer == 1 else layer)
    t.SetNet(net)
    board.Add(t)
    return ("seg", x1, y1, x2, y2, width / 2, layer)


def _draw_via(board, x, y, net, diameter, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetWidth(pcbnew.FromMM(diameter))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetNet(net)
    try:
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
    except Exception:
        pass
    board.Add(v)
    return ("via", x, y, diameter / 2)


def _astar(space, start, goal, layer, net, limit=20000, step=0.25):
    def cell(x, y):
        return int(round(x / step)), int(round(y / step))

    def xy(ix, iy):
        return ix * step, iy * step

    sx, sy = cell(*start)
    gx, gy = cell(*goal)
    if (sx, sy) == (gx, gy):
        return [start, goal]
    # The grid point nearest an endpoint can fall inside a neighbour's
    # clearance even when the endpoint itself is on its own copper.
    exact = {(sx, sy): start, (gx, gy): goal}
    heap = [(max(abs(sx - gx), abs(sy - gy)), 0, sx, sy)]
    seen = {(sx, sy): None}
    pops = 0
    found = None
    while heap and pops < limit:
        _, g, ix, iy = heappop(heap)
        pops += 1
        if abs(ix - gx) + abs(iy - gy) <= 1:
            found = (ix, iy)
            break
        px, py = exact.get((ix, iy), xy(ix, iy))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = ix + dx, iy + dy
            if (nx, ny) in seen:
                continue
            x, y = exact.get((nx, ny), xy(nx, ny))
            if not space.segment_ok(px, py, x, y, layer, net):
                continue
            seen[(nx, ny)] = (ix, iy)
            heap.append((g + 1 + max(abs(nx - gx), abs(ny - gy)), g + 1, nx, ny))
    if found is None:
        return None
    path = []
    cur = found
    while cur is not None:
        path.append(exact.get(cur, xy(*cur)))
        cur = seen[cur]
    path.reverse()
    path[0] = start
    path[-1] = goal
    return path


def _plan_same(space, x1, y1, x2, y2, layer, code):
    """A point list on one layer, or None. Does not draw."""
    dist = _hypot(x2 - x1, y2 - y1)
    if dist < 0.05:
        return [(x1, y1)]
    options = [
        [(x1, y1), (x2, y2)],
        [(x1, y1), (x1, y2), (x2, y2)],
        [(x1, y1), (x2, y1), (x2, y2)],
    ]
    for pts in options:
        if all(space.segment_ok(p[0], p[1], q[0], q[1], layer, code) for p, q in zip(pts, pts[1:])):
            return pts
    if dist <= 80:
        step = 0.8 if dist > 30 else 0.4
        limit = 40000 if dist > 10 else 12000
        path = _astar(space, (x1, y1), (x2, y2), layer, code, limit=limit, step=step)
        if path and all(space.segment_ok(p[0], p[1], q[0], q[1], layer, code) for p, q in zip(path, path[1:])):
            return path
    return None


def _commit_poly(board, space, pts, layer, net_item, width, code):
    drawn = []
    for a, b in zip(pts, pts[1:]):
        if not space.segment_ok(a[0], a[1], b[0], b[1], layer, code):
            return []
    for a, b in zip(pts, pts[1:]):
        seg = _draw_seg(board, a[0], a[1], b[0], b[1], layer, net_item, width)
        if seg:
            space.add(seg, code)
            drawn.append(seg)
    return drawn


def _own_via(space, x, y, code):
    for onet, it in space._near(x, y):
        if onet == code and it[0] == "via" and _hypot(it[1] - x, it[2] - y) < 0.25:
            return True
    return False


def _draw_via_unless(board, space, x, y, net_item, code, via_d, via_drill):
    if _own_via(space, x, y, code):
        return []
    via = _draw_via(board, x, y, net_item, via_d, via_drill)
    space.add(via, code)
    return [via]


def _realize(board, space, plans, net_item, width, code, via_d, via_drill):
    """plans is a list of ('via', x, y) or ('seg', layer, pts). Drawn only if every segment is still free."""
    for kind, *rest in plans:
        if kind == "seg":
            layer, pts = rest
            if len(pts) >= 2 and not all(
                space.segment_ok(p[0], p[1], q[0], q[1], layer, code) for p, q in zip(pts, pts[1:])
            ):
                return []
    drawn = []
    for kind, *rest in plans:
        if kind == "via":
            drawn.extend(_draw_via_unless(board, space, rest[0], rest[1], net_item, code, via_d, via_drill))
        else:
            layer, pts = rest
            drawn.extend(_commit_poly(board, space, pts, layer, net_item, width, code))
    return drawn


def _via_sites(x, y):
    yield x, y
    for radius in (0.8, 1.2, 1.6, 2.1, 2.8, 3.6):
        for k in range(16):
            ang = k * math.pi / 8
            yield x + radius * math.cos(ang), y + radius * math.sin(ang)


def _try_link(board, space, a, b, net_item, width, code, via_d, via_drill):
    x1, y1, l1 = a
    x2, y2, l2 = b
    dist = _hypot(x2 - x1, y2 - y1)
    if dist > MAX_DIST or (dist < 0.02 and l1 == l2):
        return []
    via_r = via_d / 2
    if l1 == l2:
        pts = _plan_same(space, x1, y1, x2, y2, l1, code)
        if pts:
            return _realize(board, space, [("seg", l1, pts)], net_item, width, code, via_d, via_drill)
    else:
        # A via at one end, then the rest of the route on the other layer.
        for sx, sy, gx, gy, gl in (
            (x1, y1, x2, y2, l2),
            (x2, y2, x1, y1, l1),
        ):
            if not space.via_ok(sx, sy, code, via_r):
                continue
            pts = _plan_same(space, sx, sy, gx, gy, gl, code)
            if pts:
                return _realize(
                    board, space,
                    [("via", sx, sy), ("seg", gl, pts)],
                    net_item, width, code, via_d, via_drill,
                )
        # Neither end accepts a via. Park one beside a short pair and reach both ends.
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for vx, vy in ([] if dist > 14 else _via_sites(mx, my)):
            if _hypot(vx - mx, vy - my) < 0.4:
                continue
            if not space.via_ok(vx, vy, code, via_r):
                continue
            p1 = _plan_same(space, x1, y1, vx, vy, l1, code)
            p2 = _plan_same(space, x2, y2, vx, vy, l2, code)
            if p1 and p2:
                return _realize(
                    board, space,
                    [("via", vx, vy), ("seg", l1, p1), ("seg", l2, p2)],
                    net_item, width, code, via_d, via_drill,
                )
    # Same-layer failures detour on the other outer layer. Long rats use SIG_L3
    # when that layer is not already a plane.
    alts = []
    if l1 == l2 and dist > 0.4:
        alts.append(1 - l1)
    if space.signal is not None and dist > 8:
        alts.append(space.signal)
    for lay in alts:
        starts = []
        for vx, vy in list(_via_sites(x1, y1))[:10]:
            if space.via_ok(vx, vy, code, via_r):
                p1 = _plan_same(space, x1, y1, vx, vy, l1, code)
                if p1:
                    starts.append((vx, vy, p1))
            if len(starts) >= 3:
                break
        ends = []
        for wx, wy in list(_via_sites(x2, y2))[:10]:
            if space.via_ok(wx, wy, code, via_r):
                p2 = _plan_same(space, wx, wy, x2, y2, l2, code)
                if p2:
                    ends.append((wx, wy, p2))
            if len(ends) >= 3:
                break
        if starts and ends:
            wx, wy, p2 = ends[0]
        else:
            wx = wy = p2 = None
        for vx, vy, p1 in (starts[:2] if p2 else []):
            mid = _plan_same(space, vx, vy, wx, wy, lay, code)
            if mid:
                return _realize(
                    board, space,
                    [("via", vx, vy), ("seg", l1, p1), ("seg", lay, mid), ("via", wx, wy), ("seg", l2, p2)],
                    net_item, width, code, via_d, via_drill,
                )
    return []


def _pip(x, y, pts):
    inside = False
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _inside_keepout(polys, x, y, layer):
    for play, pts in polys:
        if layer is not None and play != layer:
            continue
        if _pip(x, y, pts):
            return True
    return False


def _outline_points(zone):
    try:
        shape = zone.Outline()
    except Exception:
        return []
    if shape.OutlineCount() < 1:
        return []
    outline = shape.Outline(0)
    pts = []
    for i in range(outline.PointCount()):
        p = outline.CPoint(i)
        pts.append((_mm(p.x), _mm(p.y)))
    return pts


def _load_keepouts(board, space):
    zones = list(board.Zones())
    for fp in board.GetFootprints():
        try:
            zones.extend(fp.Zones())
        except Exception:
            pass
    for zone in zones:
        try:
            rule = zone.GetIsRuleArea()
        except Exception:
            rule = False
        if not rule:
            continue
        pts = _outline_points(zone)
        if len(pts) < 3:
            continue
        layer = zone.GetLayer()
        our = 0 if layer == pcbnew.F_Cu else 1 if layer == pcbnew.B_Cu else layer
        if zone.GetDoNotAllowTracks():
            space.track_keep.append((our, pts))
        if zone.GetDoNotAllowVias():
            space.via_keep.append((our, pts))


def _signal_layer(board):
    """SIG_L3. A ground pour already there pulls back around the track."""
    if board.GetCopperLayerCount() < 6:
        return None
    return 6


def _stitch_zone_pads(board, fin, space, width, via_d, via_drill):
    """A pad sitting in its own copper island gets a via down to the plane."""
    zone_nets = set()
    for zone in board.Zones():
        try:
            if zone.GetIsRuleArea():
                continue
        except Exception:
            pass
        if zone.GetNetCode():
            zone_nets.add(zone.GetNetCode())
    nets = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() in zone_nets:
                nets[pad.GetNetCode()] = pad.GetNet()
                break
    n = 0
    via_r = via_d / 2
    for code, state in fin.nets.items():
        if code not in zone_nets or code not in nets:
            continue
        vias = [(it[1], it[2]) for it in state.items if it[0] == "via"]
        for it in list(state.items):
            if it[0] != "pad":
                continue
            x, y = it[1], it[2]
            if any(_hypot(x - vx, y - vy) < 1.4 for vx, vy in vias):
                continue
            layer = 0 if it[5] != 1 else 1
            for vx, vy in list(_via_sites(x, y))[1:14]:
                if not space.via_ok(vx, vy, code, via_r):
                    continue
                pts = _plan_same(space, x, y, vx, vy, layer, code)
                if not pts:
                    continue
                drawn = _realize(board, space, [("via", vx, vy), ("seg", layer, pts)], nets[code], width, code, via_d, via_drill)
                if drawn:
                    state.items.extend(drawn)
                    vias.append((vx, vy))
                    n += 1
                    break
    print(f"stitched {n}", flush=True)
    return n


def join(board: pcbnew.BOARD) -> int:
    fin = Finish(board)
    fin.collect()
    layers = board.GetCopperLayerCount()
    width = 0.15 if layers >= 4 else 0.20
    via_d, via_drill = (0.60, 0.20) if layers >= 4 else (1.00, 0.50)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            via_d = _mm(t.GetWidth(pcbnew.F_Cu))
            via_drill = _mm(t.GetDrillValue())
            break
    bb = board.GetBoardEdgesBoundingBox()
    w = _mm(bb.GetX()) + _mm(bb.GetWidth())
    h = _mm(bb.GetY()) + _mm(bb.GetHeight())
    keepout = ((62.0, 64.0), (110.0, 112.0)) if layers >= 4 and w > 100 else ()
    signal = _signal_layer(board)
    space = Space([], fin.blocks, width, w, h, keepout)
    space.signal = signal
    _load_keepouts(board, space)
    for state in fin.nets.values():
        for it in state.items:
            space.add(it, state.code)
    _stitch_zone_pads(board, fin, space, width, via_d, via_drill)
    total = 0
    failed = set()
    for _round in range(6):
        added = 0
        obstacles = []
        for state in fin.nets.values():
            for it in state.items:
                obstacles.append((state.code, it))
        space = Space([], fin.blocks, width, w, h, keepout)
        space.signal = signal
        _load_keepouts(board, space)
        for code, it in obstacles:
            space.add(it, code)
        for code, state in list(fin.nets.items()):
            if not state.name or state.name.startswith("unconnected"):
                continue
            items = state.items
            groups = _comps(items)
            if len(groups) < 2:
                continue
            cands = []
            for i, ga in enumerate(groups):
                ea = []
                for idx in ga[:40]:
                    ea.extend(_ends(items[idx]))
                for gb in groups[i + 1:]:
                    eb = []
                    for idx in gb[:40]:
                        eb.extend(_ends(items[idx]))
                    pair = None
                    for e in ea:
                        for f in eb:
                            d = _hypot(e[0] - f[0], e[1] - f[1])
                            if pair is None or d < pair[0]:
                                pair = (d, e, f)
                    if pair and pair[0] <= 80:
                        key = (state.name, round(pair[1][0], 1), round(pair[1][1], 1), round(pair[2][0], 1), round(pair[2][1], 1))
                        if key not in failed:
                            cands.append(pair + (key,))
            if not cands:
                continue
            cands.sort(key=lambda c: c[0])
            net_item = None
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNetCode() == code:
                        net_item = pad.GetNet()
                        break
                if net_item:
                    break
            if net_item is None:
                continue
            linked = 0
            for dist, e, f, key in cands[:24]:
                drawn = _try_link(board, space, e, f, net_item, width, code, via_d, via_drill)
                if not drawn:
                    failed.add(key)
                    continue
                for it in drawn:
                    state.items.append(it)
                    space.add(it, code)
                added += 1
                linked += 1
                print(f"  join {state.name} {dist:.1f} mm", flush=True)
                if linked >= 6:
                    break
        print(f"round {_round} joined {added}", flush=True)
        total += added
        if added == 0:
            break
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    return total


def _desc_layer(desc: str) -> int:
    if desc.startswith("PTH") or desc.startswith("Via"):
        return 2
    if "SIG_L3" in desc or "In2.Cu" in desc:
        return 6
    if "B.Cu" in desc:
        return 1
    if "F.Cu" in desc:
        return 0
    return 2


def join_drc(board: pcbnew.BOARD, report: dict) -> int:
    """Connect the exact pairs KiCad DRC still calls unconnected."""
    fin = Finish(board)
    fin.collect()
    layers = board.GetCopperLayerCount()
    width = 0.15 if layers >= 4 else 0.20
    via_d, via_drill = (0.60, 0.20) if layers >= 4 else (1.00, 0.50)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            via_d = _mm(t.GetWidth(pcbnew.F_Cu))
            via_drill = _mm(t.GetDrillValue())
            break
    bb = board.GetBoardEdgesBoundingBox()
    w = _mm(bb.GetX()) + _mm(bb.GetWidth())
    h = _mm(bb.GetY()) + _mm(bb.GetHeight())
    keepout = ((62.0, 64.0), (110.0, 112.0)) if layers >= 4 and w > 100 else ()
    space = Space([], fin.blocks, width, w, h, keepout)
    space.signal = _signal_layer(board)
    _load_keepouts(board, space)
    for state in fin.nets.values():
        for it in state.items:
            space.add(it, state.code)
    by_name = {s.name: s for s in fin.nets.values()}
    nets = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode():
                nets[pad.GetNetname()] = pad.GetNet()
    n = 0
    for u in report.get("unconnected_items", []):
        items = u.get("items", [])
        if len(items) < 2:
            continue
        d0, d1 = items[0].get("description", ""), items[1].get("description", "")
        if d0.startswith("Zone") and d1.startswith("Zone"):
            continue
        if "unconnected-" in d0 or "unconnected-" in d1:
            continue
        p0, p1 = items[0].get("pos"), items[1].get("pos")
        if not p0 or not p1:
            continue
        net_name = None
        for desc in (d0, d1):
            if "[" in desc and "]" in desc:
                net_name = desc[desc.find("[") + 1:desc.find("]")]
                break
        if not net_name or net_name not in nets:
            continue
        l0, l1 = _desc_layer(d0), _desc_layer(d1)
        if l0 == 2 and l1 == 2:
            pairs = ((0, 0), (1, 1))
        elif l0 == 2:
            pairs = ((l1, l1),)
        elif l1 == 2:
            pairs = ((l0, l0),)
        else:
            pairs = ((l0, l1),)
        code = by_name[net_name].code if net_name in by_name else nets[net_name].GetNetCode()
        drawn = []
        for la, lb in pairs:
            drawn = _try_link(
                board, space,
                (p0["x"], p0["y"], la),
                (p1["x"], p1["y"], lb),
                nets[net_name], width, code, via_d, via_drill,
            )
            if drawn:
                break
        if drawn:
            n += 1
            print(f"  drc {net_name} {((p0['x']-p1['x'])**2+(p0['y']-p1['y'])**2)**0.5:.2f} mm", flush=True)
    print(f"drc joined {n}", flush=True)
    return n


def drop_unconnected_copper(board: pcbnew.BOARD) -> int:
    """Shield pads that were never assigned a net only create rats and hole hits."""
    n = 0
    for t in list(board.GetTracks()):
        name = t.GetNetname()
        if name.startswith("unconnected-"):
            board.Remove(t)
            n += 1
    return n


def _move_clear(board, ref, ox, oy, hw, hh):
    """Slide a footprint to the nearest spot whose body misses every other body."""
    fp = None
    boxes = []
    for other in board.GetFootprints():
        bb = other.GetBoundingBox(False, False)
        box = (
            _mm(bb.GetX()) - 0.4,
            _mm(bb.GetY()) - 0.4,
            _mm(bb.GetX()) + _mm(bb.GetWidth()) + 0.4,
            _mm(bb.GetY()) + _mm(bb.GetHeight()) + 0.4,
        )
        if other.GetReference() == ref:
            fp = other
        else:
            boxes.append(box)
    if fp is None:
        return
    edge = board.GetBoardEdgesBoundingBox()
    x0, y0 = _mm(edge.GetX()), _mm(edge.GetY())
    x1 = x0 + _mm(edge.GetWidth())
    y1 = y0 + _mm(edge.GetHeight())

    def hits(cx, cy):
        ax, ay, bx, by = cx - hw, cy - hh, cx + hw, cy + hh
        if ax < x0 + 0.6 or ay < y0 + 0.6 or bx > x1 - 0.6 or by > y1 - 0.6:
            return True
        for a, b, c, d in boxes:
            if ax < c and bx > a and ay < d and by > b:
                return True
        return False

    if not hits(ox, oy):
        return False
    best = None
    y = y0 + 2
    while y < y1 - 2:
        x = x0 + 2
        while x < x1 - 2:
            if not hits(x, y):
                score = (x - ox) ** 2 + (y - oy) ** 2
                # Mounting holes stay on the outline when a spot there is free.
                if ref.startswith("H"):
                    score += min(x - x0, x1 - x, y - y0, y1 - y) * 2000
                if best is None or score < best[0]:
                    best = (score, x, y)
            x += 1.0
        y += 1.0
    if best is None:
        print(f"no free spot for {ref}", flush=True)
        return False
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(best[1]), pcbnew.FromMM(best[2])))
    print(f"moved {ref} to {best[1]:.0f},{best[2]:.0f}", flush=True)
    return True


def nudge_parts(board: pcbnew.BOARD):
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    moved = []
    # Satellite LVDS receiver sits on the M3 hole.
    if "MK1" in refs and "U2" in refs:
        fp = refs["U2"]
        if _move_clear(board, "U2", _mm(fp.GetPosition().x), _mm(fp.GetPosition().y), 2.6, 2.3):
            moved.append("U2")
    # Core mounting hole under the RJ45.
    if "H1" in refs and "J_MESH" in refs:
        fp = refs["H1"]
        if _move_clear(board, "H1", _mm(fp.GetPosition().x), _mm(fp.GetPosition().y), 3.6, 3.6):
            moved.append("H1")
    # Solar jack through the 21700 holder.
    if "J_SOL" in refs and "BT1" in refs:
        fp = refs["J_SOL"]
        if _move_clear(board, "J_SOL", _mm(fp.GetPosition().x), _mm(fp.GetPosition().y), 2.2, 3.6):
            moved.append("J_SOL")
    return moved


def _seg_hits_pad(x1, y1, x2, y2, half, px, py, hw, hh):
    n = max(1, int(_hypot(x2 - x1, y2 - y1) / 0.25))
    for i in range(n + 1):
        t = i / n
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        dx = max(abs(x - px) - hw, 0.0)
        dy = max(abs(y - py) - hh, 0.0)
        if _hypot(dx, dy) < half + CLEAR:
            return True
    return False


def scrub_copper(board: pcbnew.BOARD, moved=()) -> int:
    """Drop shield rats, keepout copper, and tracks under a part that just moved."""
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname().startswith("unconnected-"):
                pad.SetNetCode(0)
    pads = []
    moved = set(moved)
    for fp in board.GetFootprints():
        if fp.GetReference() not in moved:
            continue
        for pad in fp.Pads():
            code = -1 if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else pad.GetNetCode()
            pos, sz = pad.GetPosition(), pad.GetSize()
            pads.append((code, _mm(pos.x), _mm(pos.y), max(_mm(sz.x) / 2, 0.05), max(_mm(sz.y) / 2, 0.05)))
    holder = Space([], [], 0.2, 1, 1, ())
    _load_keepouts(board, holder)
    kill = []
    for t in list(board.GetTracks()):
        if t.GetNetname().startswith("unconnected-"):
            kill.append(t)
            continue
        if t.GetClass() == "PCB_VIA":
            x, y = _mm(t.GetPosition().x), _mm(t.GetPosition().y)
            if _inside_keepout(holder.via_keep, x, y, None):
                kill.append(t)
            continue
        a, c = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = _mm(a.x), _mm(a.y), _mm(c.x), _mm(c.y)
        lid = t.GetLayer()
        layer = 0 if lid == pcbnew.F_Cu else 1 if lid == pcbnew.B_Cu else lid
        if any(_inside_keepout(holder.track_keep, x, y, layer) for x, y in ((x1, y1), (x2, y2), ((x1 + x2) / 2, (y1 + y2) / 2))):
            kill.append(t)
            continue
        half = _mm(t.GetWidth()) / 2
        for code, px, py, hw, hh in pads:
            if code == t.GetNetCode():
                continue
            if _seg_hits_pad(x1, y1, x2, y2, half, px, py, hw, hh):
                kill.append(t)
                break
    for t in kill:
        board.Remove(t)
    return len(kill)


def main(argv):
    if argv[1] == "--prep":
        path = argv[2]
        board = pcbnew.LoadBoard(path)
        moved = nudge_parts(board)
        dropped = scrub_copper(board, moved)
        pcbnew.SaveBoard(path, board)
        print(f"prepped {path} dropped {dropped}", flush=True)
        return
    if argv[1] == "--drc":
        global MAX_DIST
        path, report = argv[2], argv[3]
        if len(argv) > 4:
            MAX_DIST = float(argv[4])
        board = pcbnew.LoadBoard(path)
        n = join_drc(board, json.loads(Path(report).read_text()))
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        pcbnew.SaveBoard(path, board)
        print(f"saved {path} drc-joined {n}", flush=True)
        return
    path = argv[1]
    board = pcbnew.LoadBoard(path)
    n = join(board)
    pcbnew.SaveBoard(path, board)
    print(f"saved {path} joined {n}", flush=True)


if __name__ == "__main__":
    main(sys.argv)
