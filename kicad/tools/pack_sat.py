#!/usr/bin/env python3
"""Pack the satellite into a square centred on the microphone.

The vertical RJ45 and the mode headers move as close to the mic as their
bodies allow. Everything else on the back fills the nearest free cell.
The outline is the smallest square that still clears every courtyard.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
PCB = Path(os.environ.get("SAT_PCB", ROOT / "het68-sat" / "het68-sat.kicad_pcb"))
MIC = (25.0, 58.0)
LED_R = 16.0
CAP_R = 20.6
MARGIN = 1.6


def mm(v):
    return pcbnew.ToMM(v)


def xy(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def fp_by(board):
    return {fp.GetReference(): fp for fp in board.GetFootprints()}


def courtyard(fp, margin=0.2):
    layer = pcbnew.B_CrtYd if fp.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd
    bb = None
    try:
        shape = fp.GetCourtyard(layer)
        if shape is not None:
            cand = shape.BBox()
            if cand.GetWidth() > 0 and cand.GetHeight() > 0:
                bb = cand
    except Exception:
        bb = None
    if bb is None:
        bb = fp.GetBoundingBox(False, False)
    return (mm(bb.GetLeft()) - margin, mm(bb.GetTop()) - margin,
            mm(bb.GetRight()) + margin, mm(bb.GetBottom()) + margin)


def hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def pth_boxes(fp, margin=0.35):
    boxes = []
    for pad in fp.Pads():
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        drill = pad.GetDrillSize()
        if drill.x <= 0 and pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
            continue
        bb = pad.GetBoundingBox()
        boxes.append((mm(bb.GetLeft()) - margin, mm(bb.GetTop()) - margin,
                      mm(bb.GetRight()) + margin, mm(bb.GetBottom()) + margin))
    return boxes


def place(fp, x, y):
    fp.SetPosition(xy(x, y))


def center_on(fp, cx, cy):
    box = courtyard(fp, margin=0.0)
    mx = (box[0] + box[2]) / 2
    my = (box[1] + box[3]) / 2
    pos = fp.GetPosition()
    place(fp, mm(pos.x) + cx - mx, mm(pos.y) + cy - my)


def led_pos(i, radius):
    phi = math.radians(i * 45.0)
    return MIC[0] + radius * math.sin(phi), MIC[1] - radius * math.cos(phi)


def same_fp(a, b):
    return a.GetReference() == b.GetReference()


def overlaps(fp, others, side_only=True):
    box = courtyard(fp)
    pths = pth_boxes(fp)
    for other in others:
        if same_fp(other, fp):
            continue
        same = other.GetLayer() == fp.GetLayer()
        if same and hit(box, courtyard(other)):
            return other.GetReference()
        if pths:
            for pb in pth_boxes(other) + ([courtyard(other)] if not same else []):
                for mine in pths:
                    if hit(mine, pb):
                        return other.GetReference()
        if not side_only and not same and hit(box, courtyard(other)):
            return other.GetReference()
    return None


def search(fp, others, prefer):
    """Nearest free spot to prefer, then to the microphone."""
    origin = fp.GetPosition()
    best = None
    px, py = prefer
    for radius in [i * 0.8 for i in range(0, 40)]:
        steps = 1 if radius == 0 else max(8, int(radius * 4))
        for step in range(steps):
            ang = 2 * math.pi * step / steps
            x = px + radius * math.cos(ang)
            y = py + radius * math.sin(ang)
            place(fp, x, y)
            if overlaps(fp, others):
                continue
            box = courtyard(fp, margin=0.0)
            if max(abs(box[0] - MIC[0]), abs(box[2] - MIC[0]),
                   abs(box[1] - MIC[1]), abs(box[3] - MIC[1])) > 26.0:
                continue
            dist = (x - MIC[0]) ** 2 + (y - MIC[1]) ** 2
            if best is None or dist < best[0]:
                best = (dist, x, y)
        if best is not None and radius > 1:
            break
    if best is None:
        fp.SetPosition(origin)
        return False
    place(fp, best[1], best[2])
    return True


def rebuild_outline(board, x0, y0, x1, y1):
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(drawing)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, c in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(xy(*a))
        seg.SetEnd(xy(*c))
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def resize_zones(board, x0, y0, x1, y1):
    m = 1.2
    full = [(x0 + m, y0 + m), (x1 - m, y0 + m), (x1 - m, y1 - m), (x0 + m, y1 - m)]
    for zone in list(board.Zones()):
        if not hasattr(zone, "GetIsRuleArea") or zone.GetIsRuleArea():
            continue
        outline = zone.Outline().Outline(0)
        if outline.PointCount() != 4:
            continue
        xs, ys = [], []
        for i in range(4):
            p = outline.CPoint(i)
            xs.append(mm(p.x))
            ys.append(mm(p.y))
        if max(xs) - min(xs) < 30:
            continue
        for i, (x, y) in enumerate(full):
            outline.SetPoint(i, xy(x, y))
        zone.UnFill()


def drop_tracks(board):
    for track in list(board.GetTracks()):
        board.Remove(track)


def drop_stray_text(board, x0, y0, x1, y1):
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            continue
        try:
            pos = drawing.GetPosition()
        except Exception:
            continue
        x, y = mm(pos.x), mm(pos.y)
        if x < x0 or x > x1 or y < y0 or y > y1:
            board.Remove(drawing)


def main():
    board = pcbnew.LoadBoard(str(PCB))
    xs, ys = [], []
    for drawing in board.GetDrawings():
        if drawing.GetLayer() != pcbnew.Edge_Cuts:
            continue
        for point in (drawing.GetStart(), drawing.GetEnd()):
            xs.append(mm(point.x))
            ys.append(mm(point.y))
    if xs and abs((max(xs) - min(xs)) - 52) < 0.5 and abs((max(ys) - min(ys)) - 52) < 0.5:
        print("satellite is already the 52 mm square")
        return
    board = pcbnew.LoadBoard(str(PCB))
    by = fp_by(board)

    for i in range(8):
        x, y = led_pos(i, LED_R)
        place(by[f"D{4 + i}"], x, y)
        cx, cy = led_pos(i, CAP_R)
        if i == 0:
            continue
        place(by[f"C_L{i + 1}"], cx, cy)

    # Centres relative to the microphone. +y is south. The jack body sits
    # immediately north of the mic; the mode headers hug the mic on the
    # other three sides. SMD parts fill the rest of the back.
    centres = {
        "J1": (0.0, -15.6),
        "JP_SCK": (-7.0, 0.0),
        "JP_WS": (7.0, 0.0),
        "JP_SD": (0.0, 7.6),
        "C_L1": (11.0, -20.0),
    }
    for ref, (dx, dy) in centres.items():
        center_on(by[ref], MIC[0] + dx, MIC[1] + dy)

    fixed = set(centres) | {"MK1"} | {f"D{i}" for i in range(4, 12)} | {f"C_L{i}" for i in range(2, 9)}
    order = ["JP_TSCK", "JP_TWS", "JP_SDN", "JP_OE", "U5", "U1", "U2", "U3", "U4",
             "FL1", "FL2", "FL3", "D1", "D2", "D3", "F1", "FB1",
             "C2", "C3", "R1", "R_OE", "R_SD3", "R_SCK", "R_WS", "C1", "C4", "C5"]
    parked = [by[ref] for ref in fixed]
    for ref in order:
        prefer = (MIC[0], MIC[1] - 6) if ref.startswith("JP_") else (MIC[0], MIC[1])
        ok = search(by[ref], parked, prefer)
        print(("ok  " if ok else "FAIL"), ref)
        if ok:
            parked.append(by[ref])

    fps = list(board.GetFootprints())
    for fp in fps:
        if fp.GetReference().startswith("H"):
            continue
        other = overlaps(fp, fps)
        if other:
            print(f"clash {fp.GetReference()} x {other}")

    # Square from the courtyards, equal on both axes about the mic.
    reach = 0.0
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H"):
            continue
        box = courtyard(fp, margin=0.0)
        reach = max(reach, abs(box[0] - MIC[0]), abs(box[2] - MIC[0]),
                    abs(box[1] - MIC[1]), abs(box[3] - MIC[1]))
    half = math.ceil((reach + MARGIN) * 2) / 2
    x0, y0 = MIC[0] - half, MIC[1] - half
    x1, y1 = MIC[0] + half, MIC[1] + half
    print(f"square {x1 - x0:.1f} mm  origin {x0:.1f},{y0:.1f}")

    inset = 4.2
    holes = {
        "H1": (x1 - inset, y0 + inset),
        "H2": (x0 + inset, y0 + inset),
        "H3": (x1 - inset, y1 - inset),
        "H4": (x0 + inset, y1 - inset),
    }
    for ref, (x, y) in holes.items():
        place(by[ref], x, y)
        other = overlaps(by[ref], board.GetFootprints())
        print(f"hole {ref} {x:.1f},{y:.1f} clash {other}")

    rebuild_outline(board, x0, y0, x1, y1)
    pcbnew.SaveBoard(str(PCB), board)
    print("saved placement", PCB, f"{x1 - x0:.1f}mm")
    try:
        resize_zones(board, x0, y0, x1, y1)
        pcbnew.SaveBoard(str(PCB), board)
        print("saved zones")
    except Exception as exc:
        print("zone resize failed", exc)


if __name__ == "__main__":
    sys.exit(main() or 0)
