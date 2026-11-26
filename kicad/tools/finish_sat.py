#!/usr/bin/env python3
"""Close the open satellite nets and pull violating copper apart.

The board rule is 0.20 mm clearance, 0.15 mm tracks and 0.60/0.20 mm vias.
Short links stay on the pad's own layer. Longer links use SIG_L6, which sits
between GND_L5 and GND_L7, so the ground and power planes are not slotted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_8l as c

BOARD = Path(__file__).resolve().parents[1] / "het68-sat" / "het68-sat.kicad_pcb"
# Match the netclass clearance. A larger keep-out makes a legal track end
# look blocked, and the router then refuses to leave that end.
RULE_CLEAR = 0.20


def apply_rules():
    c.CLEAR = RULE_CLEAR
    c.HOLE_CLEAR = 0.20
    c.HOLE_TO_HOLE = 0.25
    c.EDGE_CLEAR = 0.30
    c.SLACK = 0.01
    c.TRACK = 0.15
    c.HALF = c.TRACK / 2
    c.VIA_D, c.VIA_DRILL = 0.60, 0.20
    c.VIA_R, c.HOLE_R = c.VIA_D / 2, c.VIA_DRILL / 2


def uuid(item):
    return item.m_Uuid.AsString()


def index(board):
    found = {}
    for track in board.GetTracks():
        found[uuid(track)] = track
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            found[uuid(pad)] = pad
    return found


def kind_of(desc):
    if desc.startswith("Via") or desc.startswith("PTH"):
        return "all"
    tail = desc.split(" on ")[-1]
    if "F.Cu" in tail and "B.Cu" not in tail:
        return "F"
    if "B.Cu" in tail:
        return "B"
    return "F"


def layer_of(kind):
    if kind == "F":
        return c.F
    if kind == "B":
        return c.B
    return None


def can_direct(kind, layer):
    if kind == "all":
        return True
    if layer == c.F and kind == "F":
        return True
    if layer == c.B and kind == "B":
        return True
    if layer == c.L6 and kind == "all":
        return True
    return False


def xy_of_item(item):
    p = item.GetPosition() if hasattr(item, "GetPosition") else None
    if p is None:
        return None
    return c.mm(p.x), c.mm(p.y)


def track_ends(track):
    a, b = track.GetStart(), track.GetEnd()
    return (c.mm(a.x), c.mm(a.y)), (c.mm(b.x), c.mm(b.y))


def delete_clearance_tracks(board, report):
    found = index(board)
    doomed = []
    via_pairs = []
    for violation in report.get("violations") or []:
        if violation.get("type") != "clearance" or violation.get("severity") != "error":
            continue
        items = violation["items"]
        vias = []
        tracks = []
        for item in items:
            desc = item.get("description", "")
            obj = found.get(item.get("uuid", ""))
            if obj is None:
                continue
            if desc.startswith("Via"):
                vias.append(obj)
            elif desc.startswith("Track") and obj.GetClass() != "PCB_VIA":
                tracks.append(obj)
        if len(vias) >= 2 and not tracks:
            via_pairs.append(vias[:2])
        elif tracks:
            tracks.sort(key=lambda t: c.math.hypot(*(d[0] - d[1] for d in zip(*track_ends(t)))))
            doomed.append(tracks[0])
    seen = set()
    gone = []
    for track in doomed:
        key = uuid(track)
        if key in seen:
            continue
        seen.add(key)
        gone.append(track)
    c.delete(board, gone)
    return len(gone), via_pairs


def attached(board, via):
    ox, oy = xy_of_item(via)
    code = via.GetNetCode()
    hits = []
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA" or track.GetNetCode() != code:
            continue
        a, b = track_ends(track)
        if c.math.dist(a, (ox, oy)) < 0.05 or c.math.dist(b, (ox, oy)) < 0.05:
            hits.append(track)
    return hits


def separate_vias(board, via_pairs):
    if not via_pairs:
        return 0
    apply_rules()
    model = c.Model(board)
    moved = 0
    seen = set()
    for left, right in via_pairs:
        key = tuple(sorted((uuid(left), uuid(right))))
        if key in seen:
            continue
        seen.add(key)
        # Slide the via with fewer tracks, then the other one if that spot is full.
        order = sorted((left, right), key=lambda v: (len(attached(board, v)), uuid(v)))
        other = order[1]
        done = False
        for via in order:
            other = left if via is right else right
            ox, oy = xy_of_item(other)
            sx, sy = xy_of_item(via)
            if c.math.dist((sx, sy), (ox, oy)) >= 0.92:
                done = True
                break
            spot = find_via_spot(model, via.GetNetCode(), (sx, sy), (ox, oy))
            if spot is None:
                continue
            retarget(board, model, via, spot)
            moved += 1
            done = True
            break
        if not done:
            print(f"via pair still tight at {xy_of_item(left)} / {xy_of_item(right)}", flush=True)
    return moved


def find_via_spot(model, code, old, other):
    away = c.math.atan2(old[1] - other[1], old[0] - other[0])
    for radius in (0.45, 0.7, 1.0, 1.4, 1.9, 2.5, 3.2):
        for step in range(16):
            ang = away + step * c.math.pi / 8
            pt = (old[0] + radius * c.math.cos(ang), old[1] + radius * c.math.sin(ang))
            pt = (round(pt[0], 2), round(pt[1], 2))
            if c.math.dist(pt, other) < 0.92:
                continue
            if model.via_ok(*pt, code):
                return pt
    return None


def retarget(board, model, via, spot):
    old = xy_of_item(via)
    code = via.GetNetCode()
    doomed = []
    for track in list(board.GetTracks()):
        if track.GetClass() == "PCB_VIA" or track.GetNetCode() != code:
            continue
        a, b = track_ends(track)
        hit_a = c.math.dist(a, old) < 0.05
        hit_b = c.math.dist(b, old) < 0.05
        if not hit_a and not hit_b:
            continue
        na = spot if hit_a else a
        nb = spot if hit_b else b
        layer = track.GetLayer()
        if c.math.dist(na, nb) < 0.05 or not model.seg_ok(na[0], na[1], nb[0], nb[1], layer, (code,), c.HALF):
            doomed.append(track)
            continue
        if hit_a:
            track.SetStart(c.vec(*spot))
        if hit_b:
            track.SetEnd(c.vec(*spot))
    via.SetPosition(c.vec(*spot))
    c.delete(board, doomed)
    model.add_track(via)


def pos(item):
    p = item.get("pos")
    if not p:
        return None
    return (p["x"], p["y"])


def try_draw(model, board, net, pts, layer):
    if len(pts) < 2:
        return True
    if not model.poly_ok(pts, layer, (net.GetNetCode(),), c.HALF):
        return False
    c.draw_poly(board, model, pts, layer, net)
    return True


def route_layer(model, board, net, start, end, layer, draw=True):
    if c.math.dist(start, end) < 0.05:
        return True
    code = net.GetNetCode()
    bends = [[start, end], [start, (end[0], start[1]), end], [start, (start[0], end[1]), end]]
    for pts in bends:
        if c.math.dist(pts[0], pts[1]) < 0.05 or (len(pts) == 3 and c.math.dist(pts[1], pts[2]) < 0.05):
            continue
        if not model.poly_ok(pts, layer, (code,), c.HALF):
            continue
        if draw:
            c.draw_poly(board, model, pts, layer, net)
        return True
    free = model.free(layer, (code,), c.HALF)
    starts = free_cells(model, free, layer, code, start)
    goals = free_cells(model, free, layer, code, end)
    if not starts or not goals:
        return False
    lab = c.regions(free)
    goal_labels = {lab(*cell) for _, cell, _ in goals}
    starts = [s for s in starts if lab(*s[1]) in goal_labels and lab(*s[1]) >= 0]
    if not starts:
        return False
    cells = c.astar(free, [(s[1][0], s[1][1], None) for s in starts[:6]], [g[1] for g in goals[:6]])
    if not cells:
        return False
    raw = [start] + [c.xy_of(p) for p in cells] + [end]
    slim = c.pull(free, raw)
    pts = slim if model.poly_ok(slim, layer, (code,), c.HALF) else raw
    if not model.poly_ok(pts, layer, (code,), c.HALF):
        return False
    if draw:
        c.draw_poly(board, model, pts, layer, net)
    return True


def free_cells(model, free, layer, code, pt, radius=2.4):
    ny, nx = free.shape
    ci, cj = c.cell_of(pt)
    found = []
    span = int(radius / c.GRID)
    for dj in range(-span, span + 1):
        for di in range(-span, span + 1):
            i, j = ci + di, cj + dj
            if not (0 <= i < nx and 0 <= j < ny) or not free[j, i]:
                continue
            xy = c.xy_of((i, j))
            if c.math.dist(xy, pt) > radius:
                continue
            if c.math.dist(xy, pt) > 0.02 and not model.poly_ok([pt, xy], layer, (code,), c.HALF):
                continue
            found.append((c.math.dist(xy, pt), (i, j), xy))
    found.sort(key=lambda row: row[0])
    return found[:10]


def via_near(model, board, net, pt, layer):
    code = net.GetNetCode()
    extra = []
    for radius in (0.0, 0.3, 0.45, 0.6, 0.8, 1.1, 1.5, 2.0, 2.8, 3.8, 5.0, 7.0, 10.0, 13.0):
        steps = 1 if radius == 0 else 24
        for step in range(steps):
            ang = 0 if radius == 0 else 2 * c.math.pi * step / steps
            spot = (round(pt[0] + radius * c.math.cos(ang), 2), round(pt[1] + radius * c.math.sin(ang), 2))
            if not model.via_ok(*spot, code):
                continue
            if radius == 0 or model.poly_ok([pt, spot], layer, (code,), c.HALF):
                return spot
            # A straight stub can be walled in. Remember a few sites and
            # see whether the same layer can reach them the long way.
            extra.append(spot)
            if len(extra) >= 8:
                break
        if len(extra) >= 8:
            break
    for spot in extra:
        if route_layer(model, board, net, pt, spot, layer, draw=False):
            return spot
    return None


def has_via(board, pt, code):
    for track in board.GetTracks():
        if track.GetClass() != "PCB_VIA" or track.GetNetCode() != code:
            continue
        if c.math.dist(xy_of_item(track), pt) < 0.08:
            return True
    return False


def anchors_of(found, item):
    """Track centres in the DRC report can sit on another net. Use the ends."""
    desc = item.get("description", "")
    obj = found.get(item.get("uuid", ""))
    if desc.startswith("Track") and obj is not None and obj.GetClass() != "PCB_VIA":
        return list(track_ends(obj))
    point = pos(item)
    return [point] if point else []


def join_points(model, board, net, pa, pb, ka, kb):
    shared = [layer for layer in (c.F, c.B, c.L6) if can_direct(ka, layer) and can_direct(kb, layer)]
    if c.math.dist(pa, pb) < 8:
        order = [layer for layer in (c.F, c.B, c.L6) if layer in shared]
    else:
        order = [layer for layer in (c.L6, c.F, c.B) if layer in shared]
    for layer in order:
        if route_layer(model, board, net, pa, pb, layer):
            return True
    la = layer_of(ka) or c.F
    lb = layer_of(kb) or c.F
    va = pa if ka == "all" else via_near(model, board, net, pa, la)
    vb = pb if kb == "all" else via_near(model, board, net, pb, lb)
    if va is None or vb is None:
        return False
    stub_a = ka != "all" and c.math.dist(pa, va) >= 0.05
    stub_b = kb != "all" and c.math.dist(pb, vb) >= 0.05
    if stub_a and not route_layer(model, board, net, pa, va, la):
        return False
    if stub_b and not route_layer(model, board, net, pb, vb, lb):
        return False
    for layer in (c.L6, c.F, c.B):
        if c.math.dist(va, vb) < 0.05 or route_layer(model, board, net, va, vb, layer):
            return add_escape_vias(board, model, net, va, vb, ka, kb)
    return False


def join_pair(model, board, net, a, b, found):
    ka, kb = kind_of(a["description"]), kind_of(b["description"])
    starts, ends = anchors_of(found, a), anchors_of(found, b)
    pairs = []
    for pa in starts:
        for pb in ends:
            pairs.append((c.math.dist(pa, pb), pa, pb))
    pairs.sort(key=lambda row: row[0])
    for _, pa, pb in pairs:
        if join_points(model, board, net, pa, pb, ka, kb):
            return True
    return False


def add_escape_vias(board, model, net, va, vb, ka, kb):
    """A through-hole pad or an existing via already joins the layers."""
    code = net.GetNetCode()
    for kind, spot in ((ka, va), (kb, vb)):
        if kind == "all" or has_via(board, spot, code):
            continue
        if not model.via_ok(*spot, code):
            return False
        c.draw_via(board, model, *spot, net)
    return True


def opens(report):
    pairs = []
    for item in report.get("unconnected_items") or []:
        a, b = item["items"]
        name = c.net_of(a.get("description", ""))
        if not name or name == "GND" or name.startswith("unconnected"):
            continue
        if "Zone" in a.get("description", "") or "Zone" in b.get("description", ""):
            continue
        if pos(a) and pos(b):
            pairs.append((c.math.dist(pos(a), pos(b)), name, a, b))
    pairs.sort(key=lambda row: row[0])
    return pairs


def fix_clearance(path):
    apply_rules()
    removed_total = 0
    moved = 0
    for _ in range(8):
        report = c.drc(path)
        board = pcbnew.LoadBoard(str(path))
        removed, via_pairs = delete_clearance_tracks(board, report)
        if removed:
            removed_total += removed
            c.fill_zones(board)
            c.save(board, path)
            continue
        moved += separate_vias(board, via_pairs)
        c.fill_zones(board)
        c.save(board, path)
        break
    print(f"clearance: removed {removed_total} tracks, moved {moved} vias", flush=True)
    return c.drc(path)


def route_pass(path):
    apply_rules()
    report = c.drc(path)
    pairs = opens(report)
    if not pairs:
        return 0, report
    board = pcbnew.LoadBoard(str(path))
    model = c.Model(board)
    found = index(board)
    done = 0
    for dist, name, a, b in pairs:
        net = board.FindNet(name)
        if net is None:
            continue
        if join_pair(model, board, net, a, b, found):
            done += 1
            print(f"  linked {name} {dist:.2f} mm", flush=True)
    c.fill_zones(board)
    c.save(board, path)
    report = c.drc(path)
    counts, nopen = c.drc_summary(report)
    print(f"pass linked {done} of {len(pairs)}; now {counts} opens {nopen}", flush=True)
    return done, report


def main(path):
    apply_rules()
    fix_clearance(path)
    for _ in range(8):
        report = c.drc(path)
        counts, nopen = c.drc_summary(report)
        print(f"before {counts} opens {nopen}", flush=True)
        if nopen == 0 and counts.get("clearance", 0) == 0:
            break
        if counts.get("clearance", 0):
            fix_clearance(path)
        done, report = route_pass(path)
        counts, nopen = c.drc_summary(report)
        if counts.get("shorting_items") or counts.get("hole_clearance") or counts.get("holes_co_located"):
            for violation in report.get("violations") or []:
                if violation.get("type") in ("shorting_items", "hole_clearance", "holes_co_located", "solder_mask_bridge"):
                    print(violation.get("type"), violation.get("description"), flush=True)
                    for item in violation["items"]:
                        print(" ", item.get("description"), item.get("pos"), flush=True)
            print("stop: new copper overlaps another net", flush=True)
            break
        if done == 0 and counts.get("clearance", 0) == 0:
            break
    report = c.drc(path)
    counts, nopen = c.drc_summary(report)
    print(f"result {counts} opens {nopen}", flush=True)
    Path("/tmp/sat-pass-drc.json").write_text(__import__("json").dumps(report))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else BOARD)
