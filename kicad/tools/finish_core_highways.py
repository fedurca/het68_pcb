"""Join the Core nets the maze left open, on B.Cu around the edge.

Each QFN via already has an L3 stub, but neighbouring vias wall that stub
in. The bottom and side margins of the board are empty enough for an
orthogonal track from that via to the far pad. Clearance is 0.18 mm, above
the 0.10 mm netclass and JLCPCB's 0.09 mm minimum.
"""
from __future__ import annotations

import math
import sys

import pcbnew

GAP = 0.18
WIDTH = 0.15


def mm(v):
    return pcbnew.ToMM(v)


def dist_point_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def dist_seg_seg(a, b, c, d):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])

    if ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d):
        return 0.0
    return min(
        dist_point_seg(a[0], a[1], c[0], c[1], d[0], d[1]),
        dist_point_seg(b[0], b[1], c[0], c[1], d[0], d[1]),
        dist_point_seg(c[0], c[1], a[0], a[1], b[0], b[1]),
        dist_point_seg(d[0], d[1], a[0], a[1], b[0], b[1]),
    )


class Hwy:
    def __init__(self, board):
        self.b = board
        self.items = []  # (netcode, kind, geometry)
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if not (pad.IsOnLayer(pcbnew.B_Cu) or pad.IsOnLayer(pcbnew.F_Cu)):
                    continue
                # Through-holes and back-side pads block a B.Cu highway.
                if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH and not pad.IsOnLayer(pcbnew.B_Cu):
                    continue
                pos = pad.GetPosition()
                sz = pad.GetSize()
                self.items.append((
                    pad.GetNetCode(),
                    "rect",
                    mm(pos.x), mm(pos.y), mm(sz.x) / 2, mm(sz.y) / 2,
                ))
        for t in board.GetTracks():
            code = t.GetNetCode()
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                self.items.append((code, "via", mm(p.x), mm(p.y), mm(t.GetWidth(pcbnew.F_Cu)) / 2))
            elif t.GetLayer() == pcbnew.B_Cu:
                a, c = t.GetStart(), t.GetEnd()
                self.items.append((
                    code, "seg",
                    mm(a.x), mm(a.y), mm(c.x), mm(c.y), mm(t.GetWidth()) / 2,
                ))

    def clear_seg(self, x1, y1, x2, y2, code):
        if min(x1, x2) < 0.6 or max(x1, x2) > 159.4 or min(y1, y2) < 0.6 or max(y1, y2) > 99.4:
            return False
        need = WIDTH / 2 + GAP
        for item in self.items:
            if item[0] == code:
                continue
            kind = item[1]
            if kind == "via":
                d = dist_point_seg(item[2], item[3], x1, y1, x2, y2) - item[4]
            elif kind == "seg":
                d = dist_seg_seg((x1, y1), (x2, y2), (item[2], item[3]), (item[4], item[5])) - item[6]
            else:
                # Axis-aligned pad. Distance from the segment to the rectangle.
                cx, cy, hx, hy = item[2], item[3], item[4], item[5]
                d = self._seg_rect(x1, y1, x2, y2, cx - hx, cy - hy, cx + hx, cy + hy)
            if d < need:
                return False
        return True

    def _seg_rect(self, x1, y1, x2, y2, rx0, ry0, rx1, ry1):
        def inside(px, py):
            return rx0 <= px <= rx1 and ry0 <= py <= ry1

        if inside(x1, y1) or inside(x2, y2):
            return 0.0
        corners = ((rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1))
        edges = ((corners[0], corners[1]), (corners[1], corners[2]), (corners[2], corners[3]), (corners[3], corners[0]))
        best = min(
            dist_point_seg(x1, y1, rx0, ry0, rx1, ry0) if False else 1e9,
            dist_point_seg(x1, y1, *edges[0][0], *edges[0][1]),
        )
        best = 1e9
        for p, q in edges:
            best = min(best, dist_seg_seg((x1, y1), (x2, y2), p, q))
        # Segment may pass the box without crossing an edge if it is outside.
        # dist_seg_seg is 0 on a crossing. Also measure endpoint-to-box.
        for px, py in ((x1, y1), (x2, y2)):
            dx = max(rx0 - px, 0.0, px - rx1)
            dy = max(ry0 - py, 0.0, py - ry1)
            best = min(best, math.hypot(dx, dy))
        return best

    def add(self, x1, y1, x2, y2, code):
        if math.hypot(x2 - x1, y2 - y1) < 0.05:
            return
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(WIDTH))
        t.SetLayer(pcbnew.B_Cu)
        t.SetNetCode(code)
        self.b.Add(t)
        self.items.append((code, "seg", x1, y1, x2, y2, WIDTH / 2))

    def try_path(self, pts, code):
        for a, b in zip(pts, pts[1:]):
            if not self.clear_seg(a[0], a[1], b[0], b[1], code):
                return False
        for a, b in zip(pts, pts[1:]):
            self.add(a[0], a[1], b[0], b[1], code)
        return True

    def launches(self, x, y, code):
        """Points a short clear run away from a boxed via."""
        out = [(x, y)]
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            hit = None
            for dist in (5.0, 9.0, 14.0):
                nx = x + dist * math.cos(rad)
                ny = y + dist * math.sin(rad)
                if self.clear_seg(x, y, nx, ny, code):
                    hit = (nx, ny)
                else:
                    break
            if hit and hit not in out:
                out.append(hit)
        return out

    def connect(self, a, b, code):
        starts = self.launches(a[0], a[1], code)
        ends = self.launches(b[0], b[1], code)
        highways_y = (97.2, 2.8, 93.5, 6.5)
        highways_x = (2.6, 157.4, 6.0, 154.0)
        for sa in starts:
            for sb in ends:
                paths = []
                for hy in highways_y:
                    paths.append([a, sa, (sa[0], hy), (sb[0], hy), sb, b])
                for hx in highways_x:
                    paths.append([a, sa, (hx, sa[1]), (hx, sb[1]), sb, b])
                for pts in paths:
                    # Drop duplicate consecutive points.
                    clean = [pts[0]]
                    for p in pts[1:]:
                        if abs(p[0] - clean[-1][0]) > 0.05 or abs(p[1] - clean[-1][1]) > 0.05:
                            clean.append(p)
                    if len(clean) >= 2 and self.try_path(clean, code):
                        return True
        return self.bfs_connect(a, b, code)

    def bfs_connect(self, a, b, code):
        """Grid route on B.Cu. Used when the via is boxed and no highway fits."""
        g = 0.20
        nx = int(160 / g) + 6
        ny = int(100 / g) + 6
        blocked = bytearray(nx * ny)
        reach = WIDTH / 2 + GAP

        def mark_disk(x, y, rad):
            rc = int(rad / g) + 1
            ix, iy = int(round(x / g)), int(round(y / g))
            r2 = (rad / g) ** 2
            for dy in range(-rc, rc + 1):
                for dx in range(-rc, rc + 1):
                    if dx * dx + dy * dy > r2:
                        continue
                    xx, yy = ix + dx, iy + dy
                    if 0 <= xx < nx and 0 <= yy < ny:
                        blocked[yy * nx + xx] = 1

        for item in self.items:
            if item[0] == code:
                continue
            if item[1] == "via":
                mark_disk(item[2], item[3], item[4] + reach)
            elif item[1] == "seg":
                x1, y1, x2, y2, hw = item[2], item[3], item[4], item[5], item[6]
                steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / g))
                for i in range(steps + 1):
                    t = i / steps
                    mark_disk(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, hw + reach)
            else:
                cx, cy, hx, hy = item[2], item[3], item[4], item[5]
                x0, x1 = cx - hx - reach, cx + hx + reach
                y0, y1 = cy - hy - reach, cy + hy + reach
                ix0, ix1 = int(x0 / g), int(x1 / g) + 1
                iy0, iy1 = int(y0 / g), int(y1 / g) + 1
                for yy in range(max(0, iy0), min(ny, iy1 + 1)):
                    row = yy * nx
                    for xx in range(max(0, ix0), min(nx, ix1 + 1)):
                        blocked[row + xx] = 1
        # Board edge.
        for ix in range(nx):
            for iy in (0, 1, ny - 2, ny - 1):
                if 0 <= iy < ny:
                    blocked[iy * nx + ix] = 1
        for iy in range(ny):
            blocked[iy * nx + 0] = 1
            blocked[iy * nx + nx - 1] = 1

        def cell(x, y):
            return int(round(x / g)), int(round(y / g))

        sx, sy = cell(*a)
        tx, ty = cell(*b)
        if not (0 <= sx < nx and 0 <= sy < ny and 0 <= tx < ny or True):
            pass
        start = (sx, sy)
        goal = (tx, ty)
        blocked[sy * nx + sx] = 0
        blocked[ty * nx + tx] = 0
        from collections import deque
        dq = deque([start])
        parent = {start: None}
        found = None
        while dq:
            ix, iy = dq.popleft()
            if (ix, iy) == goal:
                found = (ix, iy)
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxp, nyp = ix + dx, iy + dy
                if not (0 <= nxp < nx and 0 <= nyp < ny):
                    continue
                if blocked[nyp * nx + nxp] or (nxp, nyp) in parent:
                    continue
                parent[(nxp, nyp)] = (ix, iy)
                dq.append((nxp, nyp))
        if found is None:
            print(f"  bfs explored {len(parent)} blocked-start {blocked[start[1]*nx+start[0]]}", flush=True)
            return False
        path = []
        cur = found
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        pts = [(ix * g, iy * g) for ix, iy in path]
        clean = [pts[0]]
        for p in pts[1:]:
            if len(clean) >= 2:
                a0, b0 = clean[-2], clean[-1]
                if (b0[0] - a0[0]) * (p[1] - b0[1]) == (b0[1] - a0[1]) * (p[0] - b0[0]):
                    clean[-1] = p
                    continue
            clean.append(p)
        for p, q in zip(clean, clean[1:]):
            self.add(p[0], p[1], q[0], q[1], code)
        return True


def components(board, net):
    """Copper endpoints grouped by what already touches."""
    code = None
    pts = []
    links = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != net:
                continue
            code = pad.GetNetCode()
            p = pad.GetPosition()
            pts.append((mm(p.x), mm(p.y), "pad"))
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        code = t.GetNetCode()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            pts.append((mm(p.x), mm(p.y), "via"))
        else:
            a, c = t.GetStart(), t.GetEnd()
            i = len(pts)
            pts.append((mm(a.x), mm(a.y), "end"))
            pts.append((mm(c.x), mm(c.y), "end"))
            links.append((i, i + 1))
    n = len(pts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in links:
        union(a, b)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(pts[i][0] - pts[j][0]) > 0.5 or abs(pts[i][1] - pts[j][1]) > 0.5:
                continue
            if math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) < 0.45:
                union(i, j)
    blobs = {}
    for i, p in enumerate(pts):
        blobs.setdefault(find(i), []).append(p)
    centers = []
    for g in blobs.values():
        vias = [p for p in g if p[2] == "via"]
        pads = [p for p in g if p[2] == "pad"]
        pick = vias[0] if vias else (pads[0] if pads else g[0])
        centers.append((pick[0], pick[1]))
    return code, centers


def main(path):
    board = pcbnew.LoadBoard(path)
    # Nets the maze reported open. Recomputed from pads so a rerun is safe.
    wanted = []
    seen = set()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = pad.GetNetname()
            if name and name not in seen:
                seen.add(name)
    hwy = Hwy(board)
    done = 0
    open_nets = {
        "SCK3_N", "SCK3_P", "WS3_P", "WS3_N", "I2C0_SCL", "PIEZO_IN1", "PIEZO_IN2",
        "LED5_DIN", "LED6_DIN", "LED2_DIN", "LED1_DIN", "ADC_I", "ADC_ROGO",
        "ADC_HARVEST", "BURDEN_EN", "PG_5V", "STATUS_DIN",
    }
    for name in sorted(open_nets):
        code, centers = components(board, name)
        if code is None or len(centers) < 2:
            print("skip", name, flush=True)
            continue
        # Greedy: join the closest pair, then recompute.
        guard = 0
        while len(centers) >= 2 and guard < 6:
            guard += 1
            best = None
            for i in range(len(centers)):
                for j in range(i + 1, len(centers)):
                    d = abs(centers[i][0] - centers[j][0]) + abs(centers[i][1] - centers[j][1])
                    if best is None or d < best[0]:
                        best = (d, i, j)
            d, i, j = best
            if hwy.connect(centers[i], centers[j], code):
                done += 1
                print(f"joined {name} {d:.0f} mm", flush=True)
                code, centers = components(board, name)
            else:
                print(f"fail {name}", flush=True)
                break
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    print(f"highways {done}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
