#!/usr/bin/env python3
"""Finish the het68 power boards on four layers.

The inner signal layer (SIG_L3) is wiped and used as one clear routing layer.
Outer 2 oz copper keeps the power pours. A missing SMD fanout gets a short
stub and a 0.8/0.4 mm via; only a narrow foreign track that blocks that stub
is removed, and that net is put back on the clear inner layer.
"""
from __future__ import annotations

import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_8l as c
import join_opens as j

SIG = pcbnew.In2_Cu
CELL = 2.0


def islands(board, name):
    """Copper islands of one net. Nearby items only, so a long net stays cheap."""
    items = []
    for t in board.GetTracks():
        if t.GetNetname() != name:
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            items.append(("via", (c.mm(p.x), c.mm(p.y)), c.ALL,
                          ("disc", c.mm(p.x), c.mm(p.y), c.mm(t.GetWidth(c.F)) / 2), t))
        else:
            a, b = t.GetStart(), t.GetEnd()
            s = ("stad", c.mm(a.x), c.mm(a.y), c.mm(b.x), c.mm(b.y), c.mm(t.GetWidth()) / 2)
            items.append(("seg", ((c.mm(a.x), c.mm(a.y)), (c.mm(b.x), c.mm(b.y))),
                          frozenset((t.GetLayer(),)), s, t))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != name:
                continue
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                layers = c.ALL
            else:
                layers = frozenset(l for l in (c.F, c.B) if pad.IsOnLayer(l))
            items.append(("pad", c.pad_xy(pad), layers, c.pad_shape(pad, c.F if c.F in layers else c.B), pad))
    bins = defaultdict(list)

    def cells(it):
        if it[0] == "seg":
            (x1, y1), (x2, y2) = it[1]
            n = max(1, int(math.hypot(x2 - x1, y2 - y1) / CELL) + 1)
            return {(int((x1 + (x2 - x1) * i / n) // CELL), int((y1 + (y2 - y1) * i / n) // CELL))
                    for i in range(n + 1)}
        return {(int(it[1][0] // CELL), int(it[1][1] // CELL))}

    cell_of = [cells(it) for it in items]
    for i, keys in enumerate(cell_of):
        for key in keys:
            bins[key].append(i)
    uf = c.UF(len(items))

    def anchors(it):
        return list(it[1]) if it[0] == "seg" else [it[1]]

    for i, it in enumerate(items):
        seen = set()
        for cx, cy in cell_of[i]:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for jn in bins.get((cx + dx, cy + dy), ()):
                        if jn <= i or jn in seen:
                            continue
                        seen.add(jn)
                        other = items[jn]
                        if not (it[2] & other[2]):
                            continue
                        if any(c.shape_dist(other[3], x, y) <= 0.002 for x, y in anchors(it)) or any(
                            c.shape_dist(it[3], x, y) <= 0.002 for x, y in anchors(other)
                        ):
                            uf.union(i, jn)
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[uf.find(i)].append(it)
    return list(groups.values())


def has_pad(isl):
    return any(it[0] == "pad" for it in isl)


def terminals(isl):
    out = []
    for it in isl:
        if it[0] == "via" or (it[0] == "pad" and it[2] == c.ALL):
            out.append(it[1])
    return out


def smd_pad(isl):
    for it in isl:
        if it[0] == "pad" and it[2] != c.ALL:
            pad = it[4]
            fp = pad.GetParentFootprint()
            return fp.GetReference(), pad.GetNumber()
    return None


def find_pad(board, ref, num):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == num:
                return fp, pad
    return None, None


def geom(fp, pad):
    x, y = c.pad_xy(pad)
    cx, cy = c.mm(fp.GetPosition().x), c.mm(fp.GetPosition().y)
    dx, dy = x - cx, y - cy
    n = math.hypot(dx, dy) or 1.0
    u = (dx / n, dy / n)
    return (x, y), u, (-u[1], u[0])


def try_escape(model, pad, origin, u, perp, max_lat=None):
    """A via the pad can reach on its own layer, including a bent escape."""
    layer = c.F if pad.IsOnLayer(c.F) else c.B
    code = pad.GetNetCode()
    px, py = perp
    x, y = origin

    def lateral(pt):
        return abs((pt[0] - x) * px + (pt[1] - y) * py)

    lats = (0, 0.3, -0.3) if max_lat is not None else (0, 0.45, -0.45, 0.9, -0.9, 1.4, -1.4, 2.0, -2.0, 2.6, -2.6, 3.2, -3.2)
    for dist in (i * 0.25 for i in range(1, 49)):
        for lat in lats:
            pt = (x + u[0] * dist + px * lat, y + u[1] * dist + py * lat)
            if model.via_ok(*pt, code) and model.poly_ok([origin, pt], layer, (code,), c.HALF):
                return [origin, pt], layer
    free = model.free(layer, (code,), c.HALF)
    lab = c.regions(free)
    starts = snaps(model, free, lab, layer, code, origin)
    if not starts:
        return None, None
    regs = {s[0] for s in starts}
    candidates = []
    for iy in range(-30, 31):
        for ix in range(-30, 31):
            pt = (origin[0] + ix * 0.4, origin[1] + iy * 0.4)
            if math.dist(origin, pt) > 12 or (max_lat is not None and lateral(pt) > max_lat):
                continue
            if not model.via_ok(*pt, code):
                continue
            i, j = c.cell_of(pt)
            if not (0 <= i < free.shape[1] and 0 <= j < free.shape[0]) or not free[j, i]:
                continue
            if lab(i, j) not in regs:
                continue
            candidates.append((math.dist(origin, pt), pt))
    candidates.sort()
    for _, pt in candidates[:8]:
        goals = [g for g in snaps(model, free, lab, layer, code, pt) if g[0] in regs]
        if not goals:
            continue
        s, g = starts[0], goals[0]
        cells = c.astar(free, [(s[1], s[2], None)], [(g[1], g[2])])
        if not cells:
            continue
        pts = slim([origin, s[3]] + [c.xy_of(p) for p in cells] + [g[3], pt])
        if model.poly_ok(pts, layer, (code,), c.HALF):
            return pts, layer
    return None, None


def nearest_blocker(board, origin, u, perp, code, protected, max_w):
    best = None
    px, py = perp

    def along(xx, yy):
        dx, dy = xx - origin[0], yy - origin[1]
        return dx * u[0] + dy * u[1], dx * px + dy * py

    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetCode() == code:
            continue
        if str(t.m_Uuid) in protected or c.mm(t.GetWidth()) > max_w:
            continue
        a, b = t.GetStart(), t.GetEnd()
        x0, y0, x1, y1 = c.mm(a.x), c.mm(a.y), c.mm(b.x), c.mm(b.y)
        hit = None
        for i in range(9):
            tt = i / 8
            xx, yy = x0 + (x1 - x0) * tt, y0 + (y1 - y0) * tt
            dist, side = along(xx, yy)
            if -0.3 <= dist <= 10 and abs(side) <= 0.9 and (hit is None or dist < hit):
                hit = dist
        if hit is not None and (best is None or hit < best[0]):
            best = (hit, t)
    return None if best is None else best[1]


def commit_escape(board, model, pad, origin, pts, layer, protected):
    net = pad.GetNet()
    drawn = c.draw_poly(board, model, pts, layer, net)
    end = pts[-1]
    via = c.draw_via(board, model, end[0], end[1], net)
    for t in drawn:
        if t is not None:
            protected.add(str(t.m_Uuid))
    protected.add(str(via.m_Uuid))


def escape_pad(path, ref, num, protected):
    """Stub a pad out to a via. Revert the file if the corridor cannot open."""
    snap = path + ".snap"
    shutil.copy(path, snap)
    board = pcbnew.LoadBoard(path)
    j.rules(board)
    for _ in range(36):
        fp, pad = find_pad(board, ref, num)
        if pad is None:
            break
        origin, u, perp = geom(fp, pad)
        model = c.Model(board)
        pt, layer = try_escape(model, pad, origin, u, perp)
        if pt is not None:
            commit_escape(board, model, pad, origin, pt, layer, protected)
            c.save(board, path)
            return True
        blocker = nearest_blocker(board, origin, u, perp, pad.GetNetCode(), protected, 0.35)
        if blocker is None:
            blocker = nearest_blocker(board, origin, u, perp, pad.GetNetCode(), protected, 0.8)
        if blocker is None:
            break
        board.Delete(blocker)
    shutil.copy(snap, path)
    return False


def slim(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(out[-1], p) >= 0.02:
            out.append(p)
    return out


def snaps(model, free, lab, layer, code, p):
    i0, j0 = c.cell_of(p)
    found = []
    for rad in range(0, 14):
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                if max(abs(dx), abs(dy)) != rad:
                    continue
                i, j = i0 + dx, j0 + dy
                if not (0 <= i < free.shape[1] and 0 <= j < free.shape[0]) or not free[j, i]:
                    continue
                xy = (i * c.GRID, j * c.GRID)
                if rad and not model.seg_ok(p[0], p[1], xy[0], xy[1], layer, (code,)):
                    continue
                found.append((lab(i, j), i, j, xy, p))
                if len(found) >= 3:
                    return found
    return found


def route_layers(board):
    # In3 is in the collision model (core_8l.L4). In4 is not, so it stays a plane.
    layers = [SIG]
    if board.GetCopperLayerCount() >= 6 and board.GetLayerName(pcbnew.In3_Cu).startswith("SIG"):
        layers.append(pcbnew.In3_Cu)
    layers.extend((c.F, c.B))
    return layers


def route_mark(model, board, net, srcs, dsts, protected):
    """Record the new tracks so a later escape does not rip them."""
    code = net.GetNetCode()
    for layer in route_layers(board):
        free = model.free(layer, (code,), c.HALF)
        lab = c.regions(free)
        starts, goals = [], []
        for p in srcs:
            starts += snaps(model, free, lab, layer, code, p)
        for p in dsts:
            goals += snaps(model, free, lab, layer, code, p)
        by_goal = defaultdict(list)
        for g in goals:
            by_goal[g[0]].append(g)
        seen = set()
        for s in starts:
            if s[0] not in by_goal or s[0] in seen:
                continue
            seen.add(s[0])
            g = by_goal[s[0]][0]
            cells = c.astar(free, [(s[1], s[2], None)], [(g[1], g[2])])
            if not cells:
                continue
            pts = slim([s[4], s[3]] + [c.xy_of(p) for p in cells] + [g[3], g[4]])
            before = {str(t.m_Uuid) for t in board.GetTracks()}
            if not j.try_draw(model, board, net, pts, layer):
                continue
            for t in board.GetTracks():
                uid = str(t.m_Uuid)
                if uid not in before:
                    protected.add(uid)
            return True
    return False


def clear_sig(path):
    board = pcbnew.LoadBoard(path)
    n = 0
    for t in list(board.GetTracks()):
        if t.GetClass() != "PCB_VIA" and t.GetLayer() == SIG:
            board.Delete(t)
            n += 1
    c.save(board, path)
    print(f"cleared {n} inner tracks", flush=True)


def drop_orphans(path, names):
    board = pcbnew.LoadBoard(path)
    doomed = []
    for name in names:
        if not name or name == "GND" or name.startswith("unconnected"):
            continue
        groups = islands(board, name)
        if not any(has_pad(g) for g in groups):
            continue
        for g in groups:
            if has_pad(g):
                continue
            for it in g:
                doomed.append(it[4])
    for it in doomed:
        board.Delete(it)
    if doomed:
        c.save(board, path)
    print(f"dropped {len(doomed)} orphan copper pieces", flush=True)
    return len(doomed)


def open_nets(path):
    report = c.drc(path)
    err = sum(1 for v in report["violations"] if v["severity"] == "error")
    nets = defaultdict(list)
    for u in report["unconnected_items"]:
        desc = u["items"][0]["description"]
        name = desc[desc.find("[") + 1:desc.find("]")] if "[" in desc else ""
        nets[name].append(u)
    return err, nets, report


def connect_signal(path, name, protected):
    board = pcbnew.LoadBoard(path)
    j.rules(board)
    groups = [g for g in islands(board, name) if has_pad(g)]
    if len(groups) < 2:
        return 0
    groups.sort(key=len, reverse=True)
    need = []
    for g in groups:
        if terminals(g):
            continue
        pad = smd_pad(g)
        if pad:
            need.append(pad)
    for ref, num in need:
        print(f"  escape {ref}.{num} {name}", flush=True)
        if not escape_pad(path, ref, num, protected):
            print(f"  escape failed {ref}.{num}", flush=True)
            return 0
    board = pcbnew.LoadBoard(path)
    j.rules(board)
    model = c.Model(board)
    net = board.FindNet(name)
    groups = [g for g in islands(board, name) if has_pad(g)]
    groups.sort(key=len, reverse=True)
    if len(groups) < 2:
        return 0
    main = terminals(groups[0])
    if not main:
        return 0
    linked = 0
    for g in groups[1:]:
        other = terminals(g)
        if not other:
            continue
        if route_mark(model, board, net, main, other, protected):
            linked += 1
            main = main + other
    if linked:
        c.save(board, path)
    print(f"  {name}: linked {linked} of {len(groups) - 1}", flush=True)
    return linked


def gnd_pads(path, report, protected):
    """Tie a GND pad that the pour does not reach to the inner plane with a via."""
    wanted = []
    for u in report["unconnected_items"]:
        for it in u["items"]:
            desc = it["description"]
            if not desc.startswith("Pad") and not desc.startswith("PTH"):
                continue
            if "[GND]" not in desc:
                continue
            # "Pad 2 [GND] of R_HG on F.Cu"
            ref = desc.split(" of ")[1].split()[0]
            num = desc.split()[1]
            wanted.append((ref, num))
    done = 0
    seen = set()
    for ref, num in wanted:
        if (ref, num) in seen:
            continue
        seen.add((ref, num))
        board = pcbnew.LoadBoard(path)
        fp, pad = find_pad(board, ref, num)
        if pad is None:
            continue
        print(f"  gnd escape {ref}.{num}", flush=True)
        if escape_pad(path, ref, num, protected):
            done += 1
    return done


def span_of(groups):
    main = terminals(groups[0])
    best = 0.0
    for group in groups[1:]:
        other = terminals(group)
        if not main or not other:
            continue
        best = max(best, min(math.dist(a, b) for a in main for b in other))
    return best


def route_all(path, names, protected):
    """Join every pad island on the still-open inner layer, longest gap first."""
    board = pcbnew.LoadBoard(path)
    j.rules(board)
    model = c.Model(board)
    jobs = []
    for name in names:
        if not name or name == "GND" or name.startswith("unconnected"):
            continue
        groups = [g for g in islands(board, name) if has_pad(g)]
        if len(groups) < 2 or any(not terminals(g) for g in groups):
            continue
        groups.sort(key=len, reverse=True)
        jobs.append((span_of(groups), name, groups))
    jobs.sort(reverse=True)
    linked = 0
    failed = []
    for _, name, groups in jobs:
        net = board.FindNet(name)
        main = terminals(groups[0])
        done = 0
        for group in groups[1:]:
            other = terminals(group)
            if route_mark(model, board, net, main, other, protected):
                done += 1
                main = main + other
        print(f"  {name}: linked {done} of {len(groups) - 1}", flush=True)
        linked += done
        if done < len(groups) - 1:
            failed.append(name)
    if linked:
        c.save(board, path)
    return linked, failed


def add_shield(path):
    """Second ground plane plus one empty signal layer for the gaps the first one cannot take."""
    board = pcbnew.LoadBoard(path)
    if board.GetCopperLayerCount() >= 6:
        return False
    board.SetCopperLayerCount(6)
    board.SetLayerName(pcbnew.In3_Cu, "SIG_L4")
    board.SetLayerName(pcbnew.In4_Cu, "GND_L5")
    board.SetLayerType(pcbnew.In3_Cu, pcbnew.LT_SIGNAL)
    board.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_SIGNAL)
    src = next(z for z in board.Zones()
               if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In1_Cu and z.GetNetname() == "GND")
    zone = src.Duplicate(False)
    zone = zone.Cast() if hasattr(zone, "Cast") else zone
    zone.SetLayer(pcbnew.In4_Cu)
    board.Add(zone)
    zone.thisown = 0
    c.fill_zones(board)
    c.save(board, path)
    print("added SIG_L4 and GND_L5", flush=True)
    return True


def ensure_escapes(path, name, protected):
    """Give every pad island of one net a through-via, ripping only a blocking track."""
    done = 0
    for _ in range(8):
        board = pcbnew.LoadBoard(path)
        j.rules(board)
        groups = [g for g in islands(board, name) if has_pad(g) and not terminals(g)]
        if not groups:
            return done
        pad = smd_pad(groups[0])
        if pad is None:
            return done
        ref, num = pad
        print(f"  escape {ref}.{num} {name}", flush=True)
        if not escape_pad(path, ref, num, protected):
            print(f"  escape failed {ref}.{num}", flush=True)
            return done
        done += 1
    return done


def fanout_chips(path):
    """One corridor per fine-pitch side, then a via kept in that pad's own column."""
    board = pcbnew.LoadBoard(path)
    j.rules(board)
    chips = []
    for fp in board.GetFootprints():
        pads = [p for p in fp.Pads() if p.GetNetname() and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        close = False
        for i, a in enumerate(pads):
            for bpad in pads[i + 1:]:
                if a.GetNetCode() != bpad.GetNetCode() and math.dist(c.pad_xy(a), c.pad_xy(bpad)) < 0.9:
                    close = True
                    break
            if close:
                break
        if close:
            chips.append(fp.GetReference())
    placed = 0
    for ref in chips:
        board = pcbnew.LoadBoard(path)
        j.rules(board)
        fp = next(f for f in board.GetFootprints() if f.GetReference() == ref)
        cx, cy = c.mm(fp.GetPosition().x), c.mm(fp.GetPosition().y)
        sides = defaultdict(list)
        for pad in fp.Pads():
            if not pad.GetNetname() or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            x, y = c.pad_xy(pad)
            dx, dy = x - cx, y - cy
            if math.hypot(dx, dy) < 0.4:
                continue
            if abs(dy) >= abs(dx):
                key = ("y", 1 if dy > 0 else -1)
            else:
                key = ("x", 1 if dx > 0 else -1)
            sides[key].append(pad)
        ripped = 0
        for group in sides.values():
            if len(group) < 2:
                continue
            origin0, u, perp = geom(fp, group[0])
            lats = []
            for pad in group:
                x, y = c.pad_xy(pad)
                lats.append((x - origin0[0]) * perp[0] + (y - origin0[1]) * perp[1])
            for t in list(board.GetTracks()):
                if t.GetClass() == "PCB_VIA" or c.mm(t.GetWidth()) > 0.35:
                    continue
                a, bend = t.GetStart(), t.GetEnd()
                hit = False
                for i in range(7):
                    tt = i / 6
                    x = c.mm(a.x) + (c.mm(bend.x) - c.mm(a.x)) * tt
                    y = c.mm(a.y) + (c.mm(bend.y) - c.mm(a.y)) * tt
                    along = (x - origin0[0]) * u[0] + (y - origin0[1]) * u[1]
                    lat = (x - origin0[0]) * perp[0] + (y - origin0[1]) * perp[1]
                    if -1.0 <= along <= 9 and min(lats) - 1.2 <= lat <= max(lats) + 1.2:
                        hit = True
                        break
                if hit:
                    board.Delete(t)
                    ripped += 1
        if ripped:
            c.save(board, path)
        board = pcbnew.LoadBoard(path)
        j.rules(board)
        model = c.Model(board)
        fp = next(f for f in board.GetFootprints() if f.GetReference() == ref)
        cx, cy = c.mm(fp.GetPosition().x), c.mm(fp.GetPosition().y)
        sides = defaultdict(list)
        for pad in fp.Pads():
            if not pad.GetNetname() or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            x, y = c.pad_xy(pad)
            dx, dy = x - cx, y - cy
            if math.hypot(dx, dy) < 0.4:
                continue
            if abs(dy) >= abs(dx):
                key = ("y", 1 if dy > 0 else -1)
            else:
                key = ("x", 1 if dx > 0 else -1)
            sides[key].append(pad)
        protected = set()
        for group in sides.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda p: c.pad_xy(p)[0] + c.pad_xy(p)[1])
            for pad in group:
                origin, u, perp = geom(fp, pad)
                pts, layer = try_escape(model, pad, origin, u, perp, max_lat=0.35)
                if not pts:
                    print(f"  fanout {ref}.{pad.GetNumber()} {pad.GetNetname()} no via", flush=True)
                    continue
                commit_escape(board, model, pad, origin, pts, layer, protected)
                placed += 1
                print(f"  fanout {ref}.{pad.GetNumber()} {pad.GetNetname()} -> {pts[-1][0]:.2f},{pts[-1][1]:.2f}", flush=True)
        if protected:
            c.save(board, path)
        print(f"fanout {ref}: ripped {ripped}, placed {placed}", flush=True)
    return placed


def finish(path):
    backup = path + ".bak"
    shutil.copy(path, backup)
    try:
        ok = _finish(path)
    except Exception:
        shutil.copy(backup, path)
        Path(backup).unlink(missing_ok=True)
        raise
    if ok:
        Path(backup).unlink(missing_ok=True)
        print("done", path, flush=True)
    else:
        # Keep a DRC-clean board even when a pad is still open; the backup remains.
        board = pcbnew.LoadBoard(path)
        c.fill_zones(board)
        c.save(board, path)
        err, nets, _ = open_nets(path)
        n_un = sum(len(v) for v in nets.values())
        if err == 0 and n_un <= 3:
            print(f"kept {path} with {n_un} open, backup {backup}", flush=True)
        else:
            shutil.copy(backup, path)
            Path(backup).unlink(missing_ok=True)
            print("restored", path, flush=True)
    return ok


def _finish(path):
    clear_sig(path)
    board = pcbnew.LoadBoard(path)
    c.fill_zones(board)
    c.save(board, path)
    err, nets, _ = open_nets(path)
    print(f"after wipe errors {err} unconn {sum(len(v) for v in nets.values())} nets {len(nets)}", flush=True)
    drop_orphans(path, list(nets))
    protected = set()
    shielded = False
    for rnd in range(6):
        err, nets, report = open_nets(path)
        n_un = sum(len(v) for v in nets.values())
        print(f"round {rnd}: errors {err} unconn {n_un}", flush=True)
        if err == 0 and n_un == 0:
            return True
        progress = 0
        if "GND" in nets:
            progress += gnd_pads(path, report, protected)
        for name in sorted((n for n in nets if n and n != "GND" and not n.startswith("unconnected")),
                           key=lambda n: (0 if n.endswith("SDA") else 1, n)):
            progress += ensure_escapes(path, name, protected)
        linked, failed = route_all(path, list(nets), protected)
        progress += linked
        if failed and not shielded:
            shielded = add_shield(path)
            if shielded:
                linked, failed = route_all(path, failed, protected)
                progress += linked
        _, nets, _ = open_nets(path)
        progress += drop_orphans(path, list(nets))
        if progress == 0:
            print("stuck", sorted(nets), flush=True)
            break
    board = pcbnew.LoadBoard(path)
    c.fill_zones(board)
    c.save(board, path)
    err, nets, _ = open_nets(path)
    print(f"result errors {err} unconn {sum(len(v) for v in nets.values())}", flush=True)
    for name, items in sorted(nets.items()):
        for u in items:
            print(" ", name, [(i["description"], i["pos"]) for i in u["items"]])
    return err == 0 and not nets


if __name__ == "__main__":
    ok = True
    for name in sys.argv[1:] or ["het68-pwr-nn", "het68-pwr-vn", "het68-pwr-vvn"]:
        path = f"kicad/{name}/{name}.kicad_pcb"
        print("\n====", name, flush=True)
        ok = finish(path) and ok
    sys.exit(0 if ok else 1)
