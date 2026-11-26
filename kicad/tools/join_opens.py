"""Close the short gaps KiCad still reports on a finished board.

Uses the board's own track width, clearance and via. Does not invent layers:
a 2-layer board stays on F.Cu and B.Cu, a 6-layer board may also use SIG_L3.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_8l as c


def rules(board):
    nc = board.GetDesignSettings().m_NetSettings.GetDefaultNetclass()
    c.TRACK = c.mm(nc.GetTrackWidth())
    c.CLEAR = c.mm(nc.GetClearance())
    c.HALF = c.TRACK / 2
    c.VIA_D = c.mm(nc.GetViaDiameter())
    c.VIA_DRILL = c.mm(nc.GetViaDrill())
    c.VIA_R = c.VIA_D / 2
    c.HOLE_R = c.VIA_DRILL / 2
    c.HOLE_CLEAR = max(c.CLEAR, c.mm(board.GetDesignSettings().m_HoleClearance) or c.CLEAR)
    print(f"rules track {c.TRACK:.2f} clear {c.CLEAR:.2f} via {c.VIA_D:.2f}/{c.VIA_DRILL:.2f}", flush=True)


def layer_of(desc):
    if "F.Cu" in desc and "B.Cu" not in desc.split("on")[-1]:
        return c.F
    if "B.Cu" in desc:
        return c.B
    if "SIG_L3" in desc or "In2.Cu" in desc:
        return pcbnew.In2_Cu
    if "PWR_L4" in desc or "In3.Cu" in desc:
        return pcbnew.In3_Cu
    return None


def pos(item):
    p = item.get("pos")
    if not p:
        return None
    return (p["x"], p["y"])


def try_draw(model, board, net, pts, layer):
    code = net.GetNetCode()
    if not model.poly_ok(pts, layer, (code,), c.HALF):
        return False
    c.draw_poly(board, model, pts, layer, net)
    return True


def join_one(model, board, netname, a, b):
    net = board.FindNet(netname)
    if net is None or netname in ("GND", "") or netname.startswith("unconnected"):
        return False
    pa, pb = pos(a), pos(b)
    if pa is None or pb is None:
        return False
    if c.math.dist(pa, pb) > 40:
        return False
    la, lb = layer_of(a["description"]), layer_of(b["description"])
    layers = []
    for layer in (la, lb, c.F, c.B):
        if layer is not None and layer not in layers:
            if board.GetEnabledLayers().Contains(layer):
                layers.append(layer)
    for layer in layers:
        if try_draw(model, board, net, [pa, pb], layer):
            return True
        for mid in ((pb[0], pa[1]), (pa[0], pb[1])):
            if try_draw(model, board, net, [pa, mid, pb], layer):
                return True
        code = net.GetNetCode()
        free = model.free(layer, (code,), c.HALF)
        lab = c.regions(free)
        ca, cb = c.cell_of(pa), c.cell_of(pb)
        if lab(*ca) < 0 or lab(*ca) != lab(*cb):
            continue
        cells = c.astar(free, [(*ca, None)], [cb])
        if not cells:
            continue
        pts = [pa] + [c.xy_of(p) for p in cells] + [pb]
        slim = [pts[0]]
        for p in pts[1:]:
            if c.math.dist(slim[-1], p) < 0.05:
                continue
            if len(slim) >= 2:
                a0, b0 = slim[-2], slim[-1]
                if abs((b0[0] - a0[0]) * (p[1] - b0[1]) - (b0[1] - a0[1]) * (p[0] - b0[0])) < 1e-6:
                    slim[-1] = p
                    continue
            slim.append(p)
        if try_draw(model, board, net, slim, layer):
            return True
    # A via where the two ends sit on different layers.
    if la is not None and lb is not None and la != lb:
        for pt in (pa, pb):
            if model.via_ok(*pt, net.GetNetCode()):
                if try_draw(model, board, net, [pa, pt], la) and try_draw(model, board, net, [pt, pb], lb):
                    c.draw_via(board, model, *pt, net)
                    return True
    return False


def add_layers(board):
    """Give a stuck board one empty signal layer between grounds."""
    n = board.GetCopperLayerCount()
    if n >= 8:
        return pcbnew.In5_Cu
    if n == 4 and board.GetLayerName(pcbnew.In2_Cu) == "SIG_L3":
        return pcbnew.In2_Cu
    if n == 6:
        board.SetCopperLayerCount(8)
        board.SetLayerName(pcbnew.In5_Cu, "SIG_L6")
        board.SetLayerName(pcbnew.In6_Cu, "GND_L7")
        board.SetLayerType(pcbnew.In5_Cu, pcbnew.LT_SIGNAL)
        board.SetLayerType(pcbnew.In6_Cu, pcbnew.LT_SIGNAL)
        src = next(z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In4_Cu)
        sig = pcbnew.In5_Cu
    else:
        board.SetCopperLayerCount(4)
        board.SetLayerName(pcbnew.In1_Cu, "GND_L2")
        board.SetLayerName(pcbnew.In2_Cu, "SIG_L3")
        board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_SIGNAL)
        board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
        src = next(z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.B_Cu and z.GetNetname() == "GND")
        sig = pcbnew.In2_Cu
    z = src.Duplicate(False)
    z = z.Cast() if hasattr(z, "Cast") else z
    z.SetLayer(pcbnew.In6_Cu if n == 6 else pcbnew.In1_Cu)
    board.Add(z)
    z.thisown = 0
    return sig


def via_near(model, xy, code, layer):
    for radius in (0.0, 0.8, 1.2, 1.8, 2.6, 3.6, 5.0):
        steps = 1 if radius == 0 else 16
        for k in range(steps):
            ang = 0 if radius == 0 else 2 * c.math.pi * k / steps
            pt = (xy[0] + radius * c.math.cos(ang), xy[1] + radius * c.math.sin(ang))
            if not model.via_ok(*pt, code):
                continue
            if radius and not model.poly_ok([xy, pt], layer, (code,), c.HALF):
                continue
            return pt
    return None


def route_on(model, board, net, src, dst, layer):
    code = net.GetNetCode()
    free = model.free(layer, (code,), c.HALF)
    lab = c.regions(free)
    ca, cb = c.cell_of(src), c.cell_of(dst)
    if lab(*ca) < 0 or lab(*ca) != lab(*cb):
        return False
    cells = c.astar(free, [(*ca, None)], [cb])
    if not cells:
        return False
    pts = [src] + [c.xy_of(p) for p in cells] + [dst]
    return try_draw(model, board, net, pts, layer)


def finish(path):
    board = pcbnew.LoadBoard(str(path))
    rules(board)
    sig = add_layers(board)
    c.fill_zones(board)
    c.save(board, path)
    print("signal layer", board.GetLayerName(sig), "count", board.GetCopperLayerCount(), flush=True)
    for i in range(8):
        board = pcbnew.LoadBoard(str(path))
        report = c.drc(path)
        pairs = []
        for u in report.get("unconnected_items") or []:
            a, b = u["items"]
            name = a["description"]
            name = name[name.find("[") + 1:name.find("]")] if "[" in name else ""
            if not name or name == "GND" or "Zone" in a["description"] or "Zone" in b["description"]:
                continue
            if pos(a) and pos(b):
                pairs.append((name, a, b))
        if not pairs:
            print(f"pass {i}: signals done", flush=True)
            break
        model = c.Model(board)
        done = 0
        for name, a, b in pairs:
            net = board.FindNet(name)
            la = layer_of(a["description"]) or c.F
            lb = layer_of(b["description"]) or c.F
            va = via_near(model, pos(a), net.GetNetCode(), la)
            vb = via_near(model, pos(b), net.GetNetCode(), lb)
            if va is None or vb is None:
                continue
            if not route_on(model, board, net, va, vb, sig):
                continue
            if va != pos(a):
                try_draw(model, board, net, [pos(a), va], la)
            if vb != pos(b):
                try_draw(model, board, net, [pos(b), vb], lb)
            c.draw_via(board, model, *va, net)
            if c.math.dist(va, vb) > 0.05:
                c.draw_via(board, model, *vb, net)
            done += 1
        c.fill_zones(board)
        c.save(board, path)
        report = c.drc(path)
        err = sum(1 for v in report["violations"] if v["severity"] == "error")
        print(f"pass {i}: linked {done} of {len(pairs)}, errors {err}, unconn {len(report['unconnected_items'])}", flush=True)
        if err:
            print("stop: new clearance errors", flush=True)
            break
        if done == 0:
            break


def rounds(path, n=6):
    board = pcbnew.LoadBoard(str(path))
    rules(board)
    total = 0
    for i in range(n):
        report = c.drc(path)
        pairs = []
        for u in report.get("unconnected_items") or []:
            a, b = u["items"]
            name = a["description"]
            name = name[name.find("[") + 1:name.find("]")] if "[" in name else ""
            if name in ("GND", "") or "Zone" in a["description"] or "Zone" in b["description"]:
                continue
            pairs.append((name, a, b))
        if not pairs:
            print(f"round {i}: no signal gaps", flush=True)
            break
        model = c.Model(board)
        done = 0
        for name, a, b in pairs:
            if join_one(model, board, name, a, b):
                done += 1
        total += done
        c.fill_zones(board)
        c.save(board, path)
        print(f"round {i}: joined {done} of {len(pairs)}", flush=True)
        if done == 0:
            break
        board = pcbnew.LoadBoard(str(path))
    # Drop orphan ground pours. Pads left in the air show up as real opens.
    board = pcbnew.LoadBoard(str(path))
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    c.fill_zones(board)
    c.save(board, path)
    report = c.drc(path)
    err = sum(1 for v in report["violations"] if v["severity"] == "error")
    print(f"after: errors {err} unconn {len(report['unconnected_items'])} joined {total}", flush=True)
    return report


if __name__ == "__main__":
    finish(Path(sys.argv[1]))
