#!/usr/bin/env python3
"""Generate het68 KiCad projects: HAT, microphone satellite, power PCB.

Implements the frozen brief: Pimoroni Pico Plus 2 + HAT, 6× RJ45
(one mic + one addressable RGB LED), 4× piezo on one H-bridge,
I²C environmental sensor (DPS310 + SHT40) and INA3221 power monitor.
"""
from __future__ import annotations

import csv
import heapq
import re
import uuid
from array import array
from pathlib import Path

import pcbnew
import wx

ROOT = Path(__file__).resolve().parents[1]
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
FP = LIB / "footprints"
SYM = LIB / "symbols"
PRETTY = ROOT / "lib" / "het68.pretty"

# ---------------------------------------------------------------------------
# sexp / symbols
# ---------------------------------------------------------------------------

def uid() -> str:
    return str(uuid.uuid4())


def extract_symbol(path: Path, name: str) -> str:
    text = path.read_text()
    key = f'(symbol "{name}"'
    i = text.find(key)
    if i < 0:
        raise SystemExit(f"symbol {name} not in {path}")
    depth = 0
    j = i
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
        j += 1
    raise SystemExit(f"unclosed symbol {name}")


def rename_symbol(raw: str, lib_id: str) -> str:
    return re.sub(r'^\(symbol "[^"]+"', f'(symbol "{lib_id}"', raw, count=1)


def _unit_body(raw: str) -> str:
    m = re.search(r'\(symbol "[^"]+_1_1"', raw)
    if not m:
        return raw
    i = m.start()
    depth = 0
    j = i
    while j < len(raw):
        if raw[j] == "(":
            depth += 1
        elif raw[j] == ")":
            depth -= 1
            if depth == 0:
                return raw[i : j + 1]
        j += 1
    return raw


def symbol_pins(raw: str):
    pins = []
    for m in re.finditer(
        r'\(pin\s+(\S+)\s+\S+\s+\(at\s+([\-0-9.]+)\s+([\-0-9.]+)\s+([\-0-9.]+)\)'
        r'[\s\S]*?\(name "([^"]*)"[\s\S]*?\(number "([^"]+)"',
        _unit_body(raw),
    ):
        pins.append(
            {
                "type": m.group(1),
                "x": float(m.group(2)),
                "y": float(m.group(3)),
                "ang": float(m.group(4)),
                "name": m.group(5),
                "num": m.group(6),
            }
        )
    # de-duplicate stacked alternate drawings: keep first occurrence of each number
    seen = set()
    out = []
    for p in pins:
        if p["num"] in seen:
            continue
        seen.add(p["num"])
        out.append(p)
    return out


def box_symbol(lib_id: str, ref: str, value: str, footprint: str, pins, w=12.7, h=None):
    """pins: list of dicts num, name, type, side (L/R), y optional."""
    left = [p for p in pins if p["side"] == "L"]
    right = [p for p in pins if p["side"] == "R"]
    n = max(len(left), len(right), 1)
    if h is None:
        h = max(10.16, (n - 1) * 2.54 + 5.08)
    top = h / 2
    short = lib_id.split(":")[-1]

    def place(group, side):
        out = []
        for i, p in enumerate(group):
            y = top - 2.54 - i * 2.54
            if side == "L":
                x, ang = -w / 2 - 2.54, 0
            else:
                x, ang = w / 2 + 2.54, 180
            q = dict(p)
            q.update(x=x, y=y, ang=ang)
            out.append(q)
        return out

    placed = place(left, "L") + place(right, "R")
    pin_txt = []
    for p in placed:
        pin_txt.append(
            f'''    (pin {p["type"]} line
      (at {p["x"]} {p["y"]} {int(p["ang"])})
      (length 2.54)
      (name "{p["name"]}" (effects (font (size 1.27 1.27))))
      (number "{p["num"]}" (effects (font (size 1.27 1.27)))))'''
        )
    raw = f'''(symbol "{lib_id}"
  (pin_names (offset 0.254) (hide no))
  (exclude_from_sim no)
  (in_bom yes)
  (on_board yes)
  (property "Reference" "{ref}" (at 0 {top + 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Value" "{value}" (at 0 {-top - 1.27} 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "{footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol "{short}_0_1"
    (rectangle (start {-w/2} {top}) (end {w/2} {-top})
      (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol "{short}_1_1"
{chr(10).join(pin_txt)}
  ))'''
    return raw, placed


class Sch:
    def __init__(self, name, title):
        self.name = name
        self.title = title
        self.root = uid()
        self.symbols = {}  # lib_id -> raw
        self.pin_geom = {}  # lib_id -> {num: pin}
        self.parts = []
        self.draw = []
        self.flags = []  # (net, x, y) added later

    def add_lib(self, lib_id, raw, pins):
        self.symbols[lib_id] = raw
        self.pin_geom[lib_id] = {p["num"]: p for p in pins}

    def add(self, lib_id, ref, value, footprint, nets, mpn="", at=None):
        self.parts.append(
            {
                "lib_id": lib_id,
                "ref": ref,
                "value": value,
                "footprint": footprint,
                "nets": nets,  # pin num -> net or None
                "mpn": mpn,
                "uuid": uid(),
                "at": at,
            }
        )

    def pack(self):
        x = 40.0
        y_top = 40.0
        y = y_top
        col_w = 90.0
        max_x = x
        max_y = y
        for part in self.parts:
            geom = self.pin_geom[part["lib_id"]]
            ys = [p["y"] for p in geom.values()] or [0]
            xs = [abs(p["x"]) for p in geom.values()] or [10]
            h = (max(ys) - min(ys)) + 18
            if y + h > 520:
                x += col_w
                y = y_top
            part["at"] = (x, -y)  # store schematic Y-up; we use negative to grow downward on the page
            # KiCad Y is up. Start near the top of a user sheet by using large Y and decreasing.
            part["at"] = (x, 500 - (y - y_top))
            y += h
            max_x = max(max_x, x + 80)
            max_y = max(max_y, 20)
        self.page = (max(max_x + 40, 420), 560)

    def emit(self) -> str:
        self.pack()
        libs = "\n".join(self.symbols.values())
        body = []
        # power flags, one per named power net, placed in the margin
        # One power-output symbol per rail. PWR_FLAG is a global power
        # symbol named PWR_FLAG, so several of them would short the rails.
        fx = 20
        rails = ["GND", "+3V3A", "VSYS", "VBUS"]
        if self.name == "het68-sat":
            rails.append("+3V3")
        for i, net in enumerate(rails):
            if f"het68:{net}" not in self.symbols:
                continue
            fy = 30 + i * 15
            body.append(self._pwr(net, fx, fy, i))
            body.append(self._glabel(net, fx + 10, fy, 0))
            body.append(self._wire(fx, fy, fx + 10, fy))

        for part in self.parts:
            body.append(self._part(part))
        page_w, page_h = self.page
        return f'''(kicad_sch
  (version 20250114)
  (generator "het68-gen")
  (generator_version "10.0")
  (uuid "{self.root}")
  (paper "User" {page_w:.0f} {page_h:.0f})
  (title_block
    (title "{self.title}")
    (date "2026-10-28")
    (rev "A")
    (comment 1 "het68 — vyrobitelny navrh, KiCad 10")
  )
  (lib_symbols
{libs}
  )
{chr(10).join(body)}
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
'''

    def _pwr(self, net, x, y, i):
        return f'''  (symbol
    (lib_id "het68:{net}")
    (at {x} {y} 0)
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{uid()}")
    (property "Reference" "#PWR{i:02d}" (at {x} {y + 3} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "{net}" (at {x} {y + 4} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (pin "1" (uuid "{uid()}"))
    (instances (project "{self.name}" (path "/{self.root}" (reference "#PWR{i:02d}") (unit 1))))
  )'''

    def _flag(self, x, y, i):
        return f'''  (symbol
    (lib_id "power:PWR_FLAG")
    (at {x} {y} 0)
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{uid()}")
    (property "Reference" "#FLG{i:02d}" (at {x} {y-2.54} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "PWR_FLAG" (at {x} {y+2.54} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (pin "1" (uuid "{uid()}"))
    (instances (project "{self.name}" (path "/{self.root}" (reference "#FLG{i:02d}") (unit 1))))
  )'''

    def _glabel(self, name, x, y, ang):
        just = "left" if ang == 0 else "right"
        return f'''  (global_label "{name}"
    (shape bidirectional)
    (at {x} {y} {ang})
    (effects (font (size 1.27 1.27)) (justify {just}))
    (uuid "{uid()}")
  )'''

    def _wire(self, x1, y1, x2, y2):
        return f'''  (wire (pts (xy {x1} {y1}) (xy {x2} {y2}))
    (stroke (width 0) (type solid)) (uuid "{uid()}"))'''

    def _nc(self, x, y):
        return f'  (no_connect (at {x} {y}) (uuid "{uid()}"))'

    def _part(self, part):
        x, y = part["at"]
        geom = self.pin_geom[part["lib_id"]]
        pins_s = []
        graphics = []
        for num, pin in geom.items():
            # Sheet Y grows downward; symbol-library Y grows upward.
            px = round(x + pin["x"], 4)
            py = round(y - pin["y"], 4)
            pins_s.append(f'    (pin "{num}" (uuid "{uid()}"))')
            net = part["nets"].get(num, None)
            if net is None:
                graphics.append(self._nc(px, py))
                continue
            ang = pin["ang"] % 360
            dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[int(ang)]
            ex, ey = round(px + dx * 1.27, 4), round(py + dy * 1.27, 4)
            graphics.append(self._wire(px, py, ex, ey))
            lab_ang = 0 if dx > 0 or (dx == 0 and ang == 270) else 180
            graphics.append(self._glabel(net, ex, ey, lab_ang))
        props = f'''    (property "Reference" "{part["ref"]}" (at {x} {y+2} 0) (effects (font (size 1.27 1.27))))
    (property "Value" "{part["value"]}" (at {x} {y-2} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "{part["footprint"]}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "MPN" "{part["mpn"]}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))'''
        return f'''  (symbol
    (lib_id "{part["lib_id"]}")
    (at {x} {y} 0)
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{part["uuid"]}")
{props}
{chr(10).join(pins_s)}
    (instances (project "{self.name}" (path "/{self.root}" (reference "{part["ref"]}") (unit 1))))
  )
{chr(10).join(graphics)}'''


# ---------------------------------------------------------------------------
# circuit
# ---------------------------------------------------------------------------

def load_std(sch: Sch, filename, name, lib):
    raw = extract_symbol(SYM / filename, name)
    lib_id = f"{lib}:{name}"
    sch.add_lib(lib_id, rename_symbol(raw, lib_id), symbol_pins(raw))
    return lib_id


def pico_symbol():
    names = {
        1: ("GP0_TX", "passive"),
        2: ("GP1_RX", "passive"),
        3: ("GND", "power_in"),
        4: ("GP2", "passive"),
        5: ("GP3", "passive"),
        6: ("GP4", "passive"),
        7: ("GP5", "passive"),
        8: ("GND", "power_in"),
        9: ("GP6", "passive"),
        10: ("GP7", "passive"),
        11: ("GP8_WS", "passive"),
        12: ("GP9_SCK", "passive"),
        13: ("GND", "power_in"),
        14: ("GP10", "passive"),
        15: ("GP11", "passive"),
        16: ("GP12", "passive"),
        17: ("GP13", "passive"),
        18: ("GND", "power_in"),
        19: ("GP14", "passive"),
        20: ("GP15", "passive"),
        21: ("GP16", "passive"),
        22: ("GP17", "passive"),
        23: ("GND", "power_in"),
        24: ("GP18", "passive"),
        25: ("GP19", "passive"),
        26: ("GP20", "passive"),
        27: ("GP21", "passive"),
        28: ("GND", "power_in"),
        29: ("GP22", "passive"),
        30: ("RUN", "passive"),
        31: ("GP26", "passive"),
        32: ("GP27", "passive"),
        33: ("AGND", "power_in"),
        34: ("GP28", "passive"),
        35: ("ADC_VREF", "passive"),
        36: ("3V3", "power_out"),
        37: ("3V3_EN", "passive"),
        38: ("GND", "power_in"),
        39: ("VSYS", "passive"),
        40: ("VBUS", "passive"),
    }
    pins = []
    for n in range(1, 21):
        pins.append({"num": str(n), "name": names[n][0], "type": names[n][1], "side": "L"})
    for n in range(21, 41):
        pins.append({"num": str(n), "name": names[n][0], "type": names[n][1], "side": "R"})
    return box_symbol(
        "het68:PicoPlus2",
        "U",
        "PicoPlus2",
        "Module:RaspberryPi_Pico_Common_THT",
        pins,
        w=20.32,
    )


def rj_symbol():
    left = [
        ("1", "SCK"),
        ("2", "GND"),
        ("3", "WS"),
        ("4", "SD"),
        ("5", "GND"),
        ("6", "GND"),
        ("7", "3V3"),
        ("8", "LED"),
        ("SH", "SHIELD"),
    ]
    pins = [
        {"num": n, "name": name, "type": "passive", "side": "L"} for n, name in left
    ]
    return box_symbol(
        "het68:RJ45_T568B",
        "J",
        "RJ45",
        "Connector_RJ:RJ45_Amphenol_RJHSE5380",
        pins,
        w=15.24,
    )


def ap2112_symbol():
    pins = [
        {"num": "1", "name": "VIN", "type": "power_in", "side": "L"},
        {"num": "2", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "3", "name": "EN", "type": "input", "side": "L"},
        {"num": "4", "name": "NC", "type": "no_connect", "side": "R"},
        {"num": "5", "name": "VOUT", "type": "power_out", "side": "R"},
    ]
    return box_symbol(
        "het68:AP2112K-1.8",
        "U",
        "AP2112K-1.8",
        "Package_TO_SOT_SMD:SOT-23-5",
        pins,
    )


def t5848_symbol():
    pins = [
        {"num": "1", "name": "WS", "type": "input", "side": "L"},
        {"num": "2", "name": "LR", "type": "input", "side": "L"},
        {"num": "6", "name": "SCK", "type": "input", "side": "L"},
        {"num": "8", "name": "SD", "type": "output", "side": "R"},
        {"num": "7", "name": "VDD", "type": "power_in", "side": "R"},
        {"num": "3", "name": "GND", "type": "power_in", "side": "R"},
        {"num": "4", "name": "WAKE", "type": "output", "side": "R"},
        {"num": "5", "name": "THSEL", "type": "input", "side": "R"},
    ]
    return box_symbol(
        "het68:T5848",
        "MK",
        "T5848",
        "het68:T5848",
        pins,
    )


def conn_symbol(n, lib_id, fp):
    pins = [
        {"num": str(i), "name": str(i), "type": "passive", "side": "L"}
        for i in range(1, n + 1)
    ]
    return box_symbol(lib_id, "J", lib_id.split(":")[-1], fp, pins, w=7.62)


def write_t5848_fp(path: Path):
    # Coordinates: top view, terminal side down (datasheet fig. 3 / land pattern).
    # Body 2.65 (X) × 3.50 (Y) mm after rotating the bottom-view drawing.
    pads = [
        ("1", 0.90, -1.364, 0.60, 0.522),   # WS
        ("8", 0.00, -1.364, 0.60, 0.522),   # SD
        ("7", -0.90, -1.364, 0.60, 0.522),  # VDD
        ("2", 0.90, -0.544, 0.60, 0.522),   # LR
        ("6", -0.90, -0.544, 0.60, 0.522),  # SCK
        ("4", 1.05, 1.473, 0.30, 0.30),     # WAKE
        ("5", -1.05, 1.473, 0.30, 0.30),    # THSEL
    ]
    port = (0.0, 0.708)
    lines = []
    lines.append('''(footprint "T5848"
  (version 20241229)
  (generator "het68-gen")
  (layer "F.Cu")
  (descr "TDK InvenSense T5848 bottom-port I2S MEMS. Land pattern from DS-000479 fig. 33/35, pinout fig. 3 top view. PCB hole 0.8 mm. Do not paste the sound hole.")
  (tags "T5848 microphone I2S")
  (property "Reference" "MK" (at 0 2.6 0) (layer "F.SilkS") (uuid "%s") (effects (font (size 0.6 0.6) (thickness 0.1))))
  (property "Value" "T5848" (at 0 -2.6 0) (layer "F.Fab") (uuid "%s") (effects (font (size 0.5 0.5) (thickness 0.08))))
  (attr smd)
  (duplicate_pad_numbers_are_jumpers yes)''' % (uid(), uid()))
    # fab body
    lines.append(
        f'  (fp_rect (start -1.325 -1.75) (end 1.325 1.75) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{uid()}"))'
    )
    lines.append(
        f'  (fp_circle (center {port[0]} {port[1]}) (end {port[0]+0.4} {port[1]}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{uid()}"))'
    )
    # pin 1 dot
    lines.append(
        f'  (fp_circle (center 1.1 -1.6) (end 1.2 -1.6) (stroke (width 0.12) (type solid)) (fill yes) (layer "F.SilkS") (uuid "{uid()}"))'
    )
    lines.append(
        f'  (fp_rect (start -1.7 -2.1) (end 1.7 2.1) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{uid()}"))'
    )
    for num, x, y, w, h in pads:
        lines.append(
            f'''  (pad "{num}" smd rect (at {x} {y}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15) (uuid "{uid()}"))'''
        )
    # GND ring as four paste pads + copper circle, number 3. NPTH in the middle, no paste on the hole.
    r = 0.85
    for dx, dy, w, h in ((0, r, 0.28, 0.32), (0, -r, 0.28, 0.32), (r, 0, 0.32, 0.28), (-r, 0, 0.32, 0.28)):
        lines.append(
            f'''  (pad "3" smd rect (at {port[0]+dx} {port[1]+dy}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))'''
        )
    lines.append(
        f'  (fp_circle (center {port[0]} {port[1]}) (end {port[0]+0.55} {port[1]}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{uid()}"))'
    )
    lines.append(
        f'''  (pad "" np_thru_hole circle (at {port[0]} {port[1]}) (size 0.8 0.8) (drill 0.8) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))'''
    )
    lines.append(")")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# PCB
# ---------------------------------------------------------------------------

class Board:
    def __init__(self, name, w, h, layers):
        self.name = name
        self.w = w
        self.h = h
        self.layers = layers
        self.b = pcbnew.BOARD()
        self.b.SetCopperLayerCount(layers)
        self.parts = []  # schematic parts that are on the board
        self.fps = []

    def place(self, part, x, y, rot=0):
        lib, fpname = part["footprint"].split(":", 1)
        if lib == "het68":
            pretty = str(PRETTY)
        else:
            pretty = str(FP / f"{lib}.pretty")
        if not Path(pretty).is_dir():
            raise SystemExit(f"footprint library missing: {pretty} ({part['footprint']})")
        fp = pcbnew.FootprintLoad(pretty, fpname)
        if fp is None:
            raise SystemExit(f"footprint not found {part['footprint']} in {pretty}")
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        fp.SetReference(part["ref"])
        fp.SetValue(part["value"])
        fp.Reference().SetVisible(True)
        fp.Value().SetVisible(False)
        self.b.Add(fp)
        self.fps.append((part, fp))
        return fp

    def assign_nets(self):
        cache = {}

        def net(name):
            if name not in cache:
                item = pcbnew.NETINFO_ITEM(self.b, name)
                self.b.Add(item)
                cache[name] = item
            return cache[name]

        for part, fp in self.fps:
            for pad in fp.Pads():
                num = pad.GetNumber()
                if not num:
                    continue
                n = part["nets"].get(num)
                if n:
                    pad.SetNet(net(n))
        self.nets = cache

    def outline(self):
        pts = [(0, 0), (self.w, 0), (self.w, self.h), (0, self.h)]
        for a, c in zip(pts, pts[1:] + pts[:1]):
            s = pcbnew.PCB_SHAPE(self.b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c[0]), pcbnew.FromMM(c[1])))
            s.SetWidth(pcbnew.FromMM(0.1))
            self.b.Add(s)

    def text(self, s, x, y, layer=pcbnew.F_SilkS, size=1.0):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        t.SetTextThickness(pcbnew.FromMM(max(0.12, size * 0.15)))
        self.b.Add(t)

    def add_zone(self, netname, layer):
        if netname not in self.nets:
            return
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetNet(self.nets[netname])
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetLocalClearance(pcbnew.FromMM(0.2))
        z.SetIsFilled(False)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        ol = z.Outline()
        ol.NewOutline()
        m = 0.8
        for x, y in ((m, m), (self.w - m, m), (self.w - m, self.h - m), (m, self.h - m)):
            ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        self.b.Add(z)

    def fill(self):
        filler = pcbnew.ZONE_FILLER(self.b)
        filler.Fill(self.b.Zones())

    def save(self, path: Path):
        self.b.Save(str(path))


def route(board: Board, power_nets, width=0.25):
    """Grid router on F.Cu and B.Cu. Power nets are left to zones + vias."""
    g = 0.2
    nx = int(board.w / g) + 2
    ny = int(board.h / g) + 2
    # 0 free, 1..65533 pad-owner net id, 65534 track/via, 65535 edge
    infl = [array("H", [0]) * (nx * ny) for _ in range(2)]
    net_id = {}
    nxt = 1

    def nid(name):
        nonlocal nxt
        if name not in net_id:
            net_id[name] = nxt
            nxt += 1
        return net_id[name]

    def idx(ix, iy):
        return iy * nx + ix

    def cell(x, y):
        return int(round(x / g)), int(round(y / g))

    def mm(ix, iy):
        return ix * g, iy * g

    inflate = 0.18  # keep a track-sized gap between 2.54 mm headers

    def mark_rect(layer, x0, y0, x1, y1, val, force=False):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        ix0 = max(0, int(xa / g))
        ix1 = min(nx - 1, int(xb / g) + 1)
        iy0 = max(0, int(ya / g))
        iy1 = min(ny - 1, int(yb / g) + 1)
        grid = infl[layer]
        for iy in range(iy0, iy1 + 1):
            row = iy * nx
            for ix in range(ix0, ix1 + 1):
                cur = grid[row + ix]
                if force or cur == 0:
                    grid[row + ix] = val

    def pad_bb(pad):
        pos = pad.GetPosition()
        sz = pad.GetSize()
        x = pcbnew.ToMM(pos.x)
        y = pcbnew.ToMM(pos.y)
        w = pcbnew.ToMM(sz.x) / 2 + inflate
        h = pcbnew.ToMM(sz.y) / 2 + inflate
        return x - w, y - h, x + w, y + h

    # Pass 1 claims each pad's copper. Pass 2 adds clearance only on still-free cells,
    # so a fine-pitch neighbour keeps its own centre.
    pad_pts = {}  # net -> list of (x,y)
    pad_info = []
    for part, fp in board.fps:
        for pad in fp.Pads():
            n = pad.GetNetname()
            pos = pad.GetPosition()
            sz = pad.GetSize()
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            hw = pcbnew.ToMM(sz.x) / 2
            hh = pcbnew.ToMM(sz.y) / 2
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                mark_rect(0, x - hw - 0.3, y - hh - 0.3, x + hw + 0.3, y + hh + 0.3, 65535, force=True)
                mark_rect(1, x - hw - 0.3, y - hh - 0.3, x + hw + 0.3, y + hh + 0.3, 65535, force=True)
                continue
            if not n:
                continue
            both = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or pad.IsOnLayer(pcbnew.B_Cu)
            layers = (0, 1) if both else (0,)
            owner = nid(n)
            pad_info.append((layers, x, y, hw, hh, owner))
            pad_pts.setdefault(n, []).append((x, y))
    for layers, x, y, hw, hh, owner in pad_info:
        for layer in layers:
            mark_rect(layer, x - hw, y - hh, x + hw, y + hh, owner, force=True)
    for layers, x, y, hw, hh, owner in pad_info:
        for layer in layers:
            mark_rect(layer, x - hw - inflate, y - hh - inflate, x + hw + inflate, y + hh + inflate, owner)

    # edge keepout
    for layer in (0, 1):
        mark_rect(layer, -1, -1, board.w + 1, 0.5, 65535, force=True)
        mark_rect(layer, -1, board.h - 0.5, board.w + 1, board.h + 1, 65535, force=True)
        mark_rect(layer, -1, -1, 0.5, board.h + 1, 65535, force=True)
        mark_rect(layer, board.w - 0.5, -1, board.w + 1.0, board.h + 1.0, 65535, force=True)

    def add_track(x1, y1, x2, y2, layer, netname):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            return
        t = pcbnew.PCB_TRACK(board.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(0.5 if netname in ("VSYS", "VBUS", "+3V3", "+3V3_MIC", "+1V8") else width))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNet(board.nets[netname])
        board.b.Add(t)

    def via_ok(x, y, netname):
        for _part, fp in board.fps:
            for pad in fp.Pads():
                if pad.GetNetname() == netname and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    continue
                pos = pad.GetPosition()
                px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
                hw = pcbnew.ToMM(pad.GetSize().x) / 2 + 0.45
                hh = pcbnew.ToMM(pad.GetSize().y) / 2 + 0.45
                if abs(x - px) <= hw and abs(y - py) <= hh:
                    return False
        return True

    def add_via(x, y, netname):
        v = pcbnew.PCB_VIA(board.b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(0.6))
        v.SetDrill(pcbnew.FromMM(0.3))
        v.SetNet(board.nets[netname])
        board.b.Add(v)
        # block both layers around via
        mark_rect(0, x - 0.45, y - 0.45, x + 0.45, y + 0.45, 65534)
        mark_rect(1, x - 0.45, y - 0.45, x + 0.45, y + 0.45, 65534)

    def occupy_segment(x1, y1, x2, y2, layer):
        # mark centerline neighborhood
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) / g) + 1
        for s in range(steps + 1):
            t = s / max(steps, 1)
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            mark_rect(layer, x - 0.35, y - 0.35, x + 0.35, y + 0.35, 65534)

    # vias under SMD power pads so the inner plane connects
    for part, fp in board.fps:
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n not in power_nets:
                continue
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                continue
            if not n:
                continue
            pos = pad.GetPosition()
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            placed = False
            for r in (1.3, 1.8, 2.4, 3.2):
                for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, r), (r, -r), (-r, -r)):
                    vx, vy = x + dx, y + dy
                    if not (1.0 < vx < board.w - 1.0 and 1.0 < vy < board.h - 1.0):
                        continue
                    if not via_ok(vx, vy, n):
                        continue
                    add_track(x, y, vx, vy, 0, n)
                    add_via(vx, vy, n)
                    placed = True
                    break
                if placed:
                    break

    def crowded(x, y, owner):
        free = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jx, jy = cell(x + dx * 1.4, y + dy * 1.4)
            if 0 <= jx < nx and 0 <= jy < ny:
                v = infl[0][idx(jx, jy)]
                if v == 0 or v == owner:
                    free += 1
        return free < 2

    for n, pts in list(pad_pts.items()):
        if n in power_nets:
            continue
        new = []
        owner = nid(n)
        for x, y in pts:
            if not crowded(x, y, owner):
                new.append((x, y))
                continue
            others = [p for p in pts if abs(p[0] - x) > 0.1 or abs(p[1] - y) > 0.1]
            if others:
                cx = sum(p[0] for p in others) / len(others) - x
                cy = sum(p[1] for p in others) / len(others) - y
            else:
                cx, cy = 1, 0
            dirs = ((-1, 0), (1, 0), (0, -1), (0, 1))
            dirs = tuple(sorted(dirs, key=lambda d: -(d[0] * cx + d[1] * cy)))
            escaped = None
            for dist in (2.8, 4.0, 5.2):
                for dx, dy in dirs:
                    ex, ey = x + dx * dist, y + dy * dist
                    if not (1.2 < ex < board.w - 1.2 and 1.2 < ey < board.h - 1.2):
                        continue
                    jx, jy = cell(ex, ey)
                    v = infl[0][idx(jx, jy)]
                    if v not in (0, owner):
                        continue
                    add_track(x, y, ex, ey, 0, n)
                    occupy_segment(x, y, ex, ey, 0)
                    for oy in range(-3, 4):
                        for ox in range(-3, 4):
                            cx, cy = jx + ox, jy + oy
                            if 0 <= cx < nx and 0 <= cy < ny and infl[0][idx(cx, cy)] == 65534:
                                infl[0][idx(cx, cy)] = 0
                    escaped = (ex, ey)
                    break
                if escaped:
                    break
            new.append(escaped or (x, y))
        pad_pts[n] = new

    unrouted = []
    signal = [n for n in board.nets if n not in power_nets and len(pad_pts.get(n, [])) >= 2]
    # short nets first
    def span(n):
        pts = pad_pts[n]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    signal.sort(key=span)

    def walkable(layer, ix, iy, owner, targets_set):
        if not (0 <= ix < nx and 0 <= iy < ny):
            return False
        if (ix, iy) in targets_set:
            return True
        v = infl[layer][idx(ix, iy)]
        return v == 0 or v == owner

    def bfs(start, targets_set, owner):
        sx, sy = start
        tgt = next(iter(targets_set))
        heap = [(0, 0, sx, sy, 0)]  # f, cost, ix, iy, layer
        prev = {}
        seen = set()
        best = None
        expands = 0
        while heap:
            f, cost, ix, iy, layer = heapq.heappop(heap)
            key = (ix, iy, layer)
            if key in seen:
                continue
            seen.add(key)
            if cost > 0 and (ix, iy) in targets_set:
                best = key
                break
            expands += 1
            if expands > 400000:
                return None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if not walkable(layer, jx, jy, owner, targets_set):
                    continue
                nk = (jx, jy, layer)
                if nk in seen:
                    continue
                step = cost + 1
                h = abs(jx - tgt[0]) + abs(jy - tgt[1])
                prev[nk] = key
                heapq.heappush(heap, (step + h, step, jx, jy, layer))
            ol = 1 - layer
            if walkable(ol, ix, iy, owner, targets_set):
                nk = (ix, iy, ol)
                if nk not in seen:
                    step = cost + 4
                    h = abs(ix - tgt[0]) + abs(iy - tgt[1])
                    prev[nk] = key
                    heapq.heappush(heap, (step + h, step, ix, iy, ol))
        if best is None:
            return None
        path = [best]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    for n in signal:
        pts = pad_pts[n]
        # connected target cells = first pad
        owner = nid(n)
        targets = set()
        ix, iy = cell(*pts[0])
        targets.add((ix, iy))
        ok = True
        for x, y in pts[1:]:
            six, siy = cell(x, y)
            path = bfs((six, siy), targets, owner)
            if not path:
                ok = False
                break
            # draw and add to targets
            for (ix, iy, layer), (jx, jy, jlayer) in zip(path, path[1:]):
                x1, y1 = mm(ix, iy)
                x2, y2 = mm(jx, jy)
                if layer != jlayer:
                    add_via(x1, y1, n)
                else:
                    add_track(x1, y1, x2, y2, layer, n)
                    occupy_segment(x1, y1, x2, y2, layer)
                targets.add((ix, iy))
                targets.add((jx, jy))
            # stitch exact pad center to snapped cell
            lx, ly, layer = path[0][0], path[0][1], path[0][2]
            add_track(x, y, *mm(lx, ly), layer, n)
        if not ok:
            unrouted.append(n)
    return unrouted


def design_rules(board: Board):
    ds = board.b.GetDesignSettings()
    ds.m_MinClearance = pcbnew.FromMM(0.2)
    ds.m_TrackMinWidth = pcbnew.FromMM(0.2)
    ds.m_ViasMinSize = pcbnew.FromMM(0.55)
    ds.m_ViasMinDrill = pcbnew.FromMM(0.3)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
    ds.m_HoleClearance = pcbnew.FromMM(0.2)
    try:
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetClearance(pcbnew.FromMM(0.2))
        nc.SetTrackWidth(pcbnew.FromMM(0.25))
        nc.SetViaDiameter(pcbnew.FromMM(0.6))
        nc.SetViaDrill(pcbnew.FromMM(0.3))
    except Exception as e:
        print("netclass", e)


# ---------------------------------------------------------------------------
# build projects
# ---------------------------------------------------------------------------

def base_libs(sch: Sch):
    for filename, name, lib in [
        ("Device.kicad_sym", "R", "Device"),
        ("Device.kicad_sym", "C", "Device"),
        ("Device.kicad_sym", "C_Polarized", "Device"),
        ("Device.kicad_sym", "D", "Device"),
        ("Device.kicad_sym", "LED", "Device"),
        ("Device.kicad_sym", "FerriteBead", "Device"),
        ("Device.kicad_sym", "Polyfuse", "Device"),
        ("Logic_LevelTranslator.kicad_sym", "SN74LVC8T245", "Logic_LevelTranslator"),
        ("Driver_Motor.kicad_sym", "DRV8837C", "Driver_Motor"),
        ("Power_Management.kicad_sym", "INA3221", "Power_Management"),
        ("Sensor_Humidity.kicad_sym", "SHT4x", "Sensor_Humidity"),
        ("Sensor_Pressure.kicad_sym", "BMP280", "Sensor_Pressure"),
        ("LED.kicad_sym", "WS2812B", "LED"),
        ("Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P", "Connector"),
    ]:
        load_std(sch, filename, name, lib)
    for maker in (pico_symbol, rj_symbol, ap2112_symbol, t5848_symbol):
        raw, pins = maker()
        lib_id = re.search(r'\(symbol "([^"]+)"', raw).group(1)
        sch.add_lib(lib_id, raw, pins)
    for net in ("GND", "+3V3", "+3V3A", "VSYS", "VBUS"):
        raw = f'''(symbol "het68:{net}"
  (power global)
  (pin_names (offset 0) (hide yes))
  (exclude_from_sim no) (in_bom yes) (on_board yes)
  (property "Reference" "#PWR" (at 0 2.54 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Value" "{net}" (at 0 3.81 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol "{net}_1_1"
    (pin power_out line (at 0 0 0) (length 0)
      (name "{net}" (effects (font (size 1.27 1.27))))
      (number "1" (effects (font (size 1.27 1.27)))))
  ))'''
        sch.add_lib(f"het68:{net}", raw, symbol_pins(raw))
    for n, lib_id, fp in [
        (2, "het68:Conn_1x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"),
        (4, "het68:Conn_1x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"),
    ]:
        raw, pins = conn_symbol(n, lib_id, fp)
        sch.add_lib(lib_id, raw, pins)


def R(sch, ref, nets, value="33", fp="Resistor_SMD:R_0402_1005Metric", mpn="RC0402FR-0733RL"):
    sch.add("Device:R", ref, value, fp, {"1": nets[0], "2": nets[1]}, mpn)


def C(sch, ref, nets, value="100n", fp="Capacitor_SMD:C_0402_1005Metric", mpn="CL05B104KB5NNNC"):
    sch.add("Device:C", ref, value, fp, {"1": nets[0], "2": nets[1]}, mpn)


def build_hat(sch: Sch):
    # Pico
    pico_nets = {str(i): None for i in range(1, 41)}
    gnd_pins = [3, 8, 13, 18, 23, 28, 33, 38]
    for p in gnd_pins:
        pico_nets[str(p)] = "GND"
    pico_nets.update(
        {
            "1": "UART_TX",
            "2": "UART_RX",
            "4": "I2C1_SDA",
            "5": "I2C1_SCL",
            "6": "I2C0_SDA",
            "7": "I2C0_SCL",
            "9": "PIEZO_IN1",
            "10": "PIEZO_IN2",
            "11": "WS_3V3",
            "12": "SCK_3V3",
            "14": "LED1_G",
            "15": "LED2_G",
            "16": "LED3_G",
            "17": "LED4_G",
            "19": "LED5_G",
            "21": "SD1_3V3",
            "24": "SD2_3V3",
            "26": "SD3_3V3",
            "29": "LED6_G",
            "30": "RUN",
            "31": "SD4_3V3",
            "32": "SD5_3V3",
            "34": "SD6_3V3",
            "35": "+3V3",
            "36": "+3V3",
            "39": "VSYS",
        }
    )
    sch.add(
        "het68:PicoPlus2",
        "U1",
        "Pico_Plus_2",
        "Module:RaspberryPi_Pico_Common_THT",
        pico_nets,
        "Pimoroni Pico Plus 2",
    )

    def lvc(ref, direction_net, a_nets, b_nets, mpn="SN74LVC8T245PWR"):
        # a_nets / b_nets: 8 entries, None = tie policy handled by caller
        nets = {
            "1": "+3V3",
            "2": direction_net,
            "11": "GND",
            "12": "GND",
            "13": "GND",
            "22": "GND",
            "23": "+1V8",
            "24": "+1V8",
        }
        for i in range(8):
            nets[str(3 + i)] = a_nets[i]  # A1..A8 pins 3..10
            # B8..B1 are pins 14..21
            nets[str(14 + (7 - i))] = b_nets[i]
        sch.add(
            "Logic_LevelTranslator:SN74LVC8T245",
            ref,
            "SN74LVC8T245",
            "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
            nets,
            mpn,
        )

    # SCK fanout A->B (DIR high). A1-A6 = SCK, A7 A8 = GND. B7 B8 NC.
    a = ["SCK_3V3"] * 6 + ["GND", "GND"]
    b = [f"SCK{i}_B" for i in range(1, 7)] + [None, None]
    lvc("U2", "+3V3", a, b)
    a = ["WS_3V3"] * 6 + ["GND", "GND"]
    b = [f"WS{i}_B" for i in range(1, 7)] + [None, None]
    lvc("U3", "+3V3", a, b)
    # SD B->A (DIR low). B inputs from jacks, A outputs to GPIO. Unused B tied GND.
    a = [f"SD{i}_3V3" for i in range(1, 7)] + [None, None]
    b = [f"SD{i}_18" for i in range(1, 7)] + ["GND", "GND"]
    lvc("U4", "GND", a, b)

    # 1V8 LDO for translator VCCB only
    sch.add(
        "het68:AP2112K-1.8",
        "U5",
        "AP2112K-1.8",
        "Package_TO_SOT_SMD:SOT-23-5",
        {"1": "+3V3", "2": "GND", "3": "+3V3", "4": None, "5": "+1V8"},
        "AP2112K-1.8TRG1",
    )
    C(sch, "C1", ("+3V3", "GND"), "1u", mpn="CL05A105KA5NQNC")
    C(sch, "C2", ("+1V8", "GND"), "1u", mpn="CL05A105KA5NQNC")
    C(sch, "C3", ("+3V3", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")
    C(sch, "C4", ("VSYS", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")

    # decoupling on translators
    for i, ref in enumerate(("C5", "C6", "C7")):
        C(sch, ref, ("+3V3", "GND"))
    for ref in ("C8", "C9", "C10"):
        C(sch, ref, ("+1V8", "GND"))

    # jacks, series resistors, ESD
    # T568B: 1 SCK, 2 GND, 3 WS, 4 SD, 5 GND, 6 GND, 7 3V3, 8 LED
    rnum = 10
    dnum = 1
    for i in range(1, 7):
        sch.add(
            "het68:RJ45_T568B",
            f"J{i}",
            f"MIC{i}",
            "Connector_RJ:RJ45_Amphenol_RJHSE5380",
            {
                "1": f"SCK{i}",
                "2": "GND",
                "3": f"WS{i}",
                "4": f"SD{i}_18",
                "5": "GND",
                "6": "GND",
                "7": "+3V3_MIC",
                "8": f"LED{i}",
                "SH": "GND",
            },
            "RJHSE-5380 (8P8C, bez magnetik)",
        )
        R(sch, f"R{rnum}", (f"SCK{i}_B", f"SCK{i}"), "33")
        rnum += 1
        R(sch, f"R{rnum}", (f"WS{i}_B", f"WS{i}"), "33")
        rnum += 1
        R(sch, f"R{rnum}", (f"LED{i}_G", f"LED{i}"), "100", mpn="RC0402FR-07100RL")
        rnum += 1
        for net in (f"SCK{i}", f"WS{i}", f"SD{i}_18", f"LED{i}"):
            # D pin 1 = K (cathode) on signal, pin 2 = A to GND
            sch.add(
                "Device:D",
                f"D{dnum}",
                "PESD5V0S1BA",
                "Diode_SMD:D_SOD-323",
                {"1": net, "2": "GND"},
                "PESD5V0S1BA,115",
            )
            dnum += 1

    # piezo driver, VSYS so it still works when USB is 5 V and when harvest is ~3.3 V
    sch.add(
        "Driver_Motor:DRV8837C",
        "U6",
        "DRV8837C",
        "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
        {
            "1": "VSYS",
            "2": "PIEZO_P",
            "3": "PIEZO_N",
            "4": "GND",
            "5": "PIEZO_IN2",
            "6": "PIEZO_IN1",
            "7": "+3V3",
            "8": "+3V3",
            "9": "GND",
        },
        "DRV8837CDSGR",
    )
    C(sch, "C11", ("VSYS", "GND"), "100n")
    R(sch, "R40", ("PIEZO_P", "PIEZO_A"), "10", "Resistor_SMD:R_1206_3216Metric", "RC1206FR-0710RL")
    R(sch, "R41", ("PIEZO_N", "PIEZO_B"), "10", "Resistor_SMD:R_1206_3216Metric", "RC1206FR-0710RL")
    for i in range(1, 5):
        sch.add(
            "het68:Conn_1x02",
            f"J{10+i}",
            f"PZ{i}",
            "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "PIEZO_A", "2": "PIEZO_B"},
            "PinHeader 1x2",
        )

    # environment: DPS310 (BMP280-compatible pinout) + SHT40
    sch.add(
        "Sensor_Pressure:BMP280",
        "U7",
        "DPS310",
        "Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering",
        {
            "1": "GND",
            "2": "+3V3A",  # CSB high = I2C
            "3": "I2C1_SDA",
            "4": "I2C1_SCL",
            "5": "+3V3A",  # SDO high = addr 0x77
            "6": "+3V3A",
            "7": "GND",
            "8": "+3V3A",
        },
        "DPS310",
    )
    sch.add(
        "Sensor_Humidity:SHT4x",
        "U8",
        "SHT40",
        "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
        {"1": "I2C1_SDA", "2": "I2C1_SCL", "3": "+3V3A", "4": "GND"},
        "SHT40-AD1B-R2",
    )
    sch.add(
        "Device:FerriteBead",
        "FB1",
        "600R",
        "Inductor_SMD:L_0603_1608Metric",
        {"1": "+3V3", "2": "+3V3A"},
        "BLM18PG601SN1D",
    )
    C(sch, "C12", ("+3V3A", "GND"), "100n")
    C(sch, "C13", ("+3V3A", "GND"), "1u", mpn="CL05A105KA5NQNC")
    R(sch, "R42", ("I2C1_SDA", "+3V3"), "4.7k", mpn="RC0402FR-074K7L")
    R(sch, "R43", ("I2C1_SCL", "+3V3"), "4.7k", mpn="RC0402FR-074K7L")
    R(sch, "R44", ("I2C0_SDA", "+3V3"), "4.7k", mpn="RC0402FR-074K7L")
    R(sch, "R45", ("I2C0_SCL", "+3V3"), "4.7k", mpn="RC0402FR-074K7L")
    R(sch, "R46", ("RUN", "+3V3"), "10k", mpn="RC0402FR-0710KL")

    # power monitor
    sch.add(
        "Power_Management:INA3221",
        "U9",
        "INA3221",
        "Package_DFN_QFN:Texas_RGV0016A_VQFN-16-1EP_4x4mm_P0.65mm_EP2.1x2.1mm",
        {
            "1": "GND",
            "2": "GND",
            "3": "GND",
            "4": "+3V3",
            "5": "GND",  # A0 -> 0x40
            "6": "I2C0_SCL",
            "7": "I2C0_SDA",
            "8": None,
            "9": None,
            "10": None,
            "11": "VSYS",
            "12": "VSYS_IN",
            "13": None,
            "14": "+3V3_MIC",
            "15": "+3V3",
            "16": "+3V3",
            "17": "GND",
        },
        "INA3221AIRGVR",
    )
    R(sch, "R47", ("VSYS_IN", "VSYS"), "0.1", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-070R1L")
    R(sch, "R48", ("+3V3", "+3V3_MIC"), "0.1", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-070R1L")
    C(sch, "C14", ("+3V3", "GND"), "100n")

    sch.add(
        "het68:Conn_1x02",
        "J10",
        "PWR",
        "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        {"1": "VSYS_IN", "2": "GND"},
        "PinHeader 1x2",
    )
    sch.add(
        "het68:Conn_1x04",
        "J17",
        "UART",
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        {"1": "UART_TX", "2": "UART_RX", "3": "GND", "4": "+3V3"},
        "PinHeader 1x4",
    )
    # mounting holes have no schematic pins; added only on the PCB


def build_sat(sch: Sch):
    sch.add(
        "het68:RJ45_T568B",
        "J1",
        "RJ45",
        "Connector_RJ:RJ45_Amphenol_RJHSE5380",
        {
            "1": "SCK",
            "2": "GND",
            "3": "WS",
            "4": "SD_J",
            "5": "GND",
            "6": "GND",
            "7": "+3V3",
            "8": "LED",
            "SH": None,
        },
        "RJHSE-5380",
    )
    sch.add(
        "het68:AP2112K-1.8",
        "U1",
        "AP2112K-1.8",
        "Package_TO_SOT_SMD:SOT-23-5",
        {"1": "+3V3", "2": "GND", "3": "+3V3", "4": None, "5": "+1V8"},
        "AP2112K-1.8TRG1",
    )
    sch.add(
        "het68:T5848",
        "MK1",
        "T5848",
        "het68:T5848",
        {
            "1": "WS",
            "2": "GND",
            "3": "GND",
            "4": None,
            "5": None,
            "6": "SCK",
            "7": "+1V8",
            "8": "SD",
        },
        "MMICT5848-00-012",
    )
    sch.add(
        "LED:WS2812B",
        "D1",
        "SK6812",
        "LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm",
        {"1": "+3V3", "2": None, "3": "GND", "4": "LED"},
        "SK6812 (5050, 3.3 V)",
    )
    C(sch, "C1", ("+3V3", "GND"), "1u", mpn="CL05A105KA5NQNC")
    C(sch, "C2", ("+1V8", "GND"), "1u", mpn="CL05A105KA5NQNC")
    C(sch, "C3", ("+1V8", "GND"), "100n")
    C(sch, "C4", ("+3V3", "GND"), "100n")
    R(sch, "R1", ("SD", "SD_J"), "33")
    R(sch, "R2", ("SD", "GND"), "100k", mpn="RC0402FR-07100KL")


def build_pwr(sch: Sch):
    sch.add(
        "het68:Conn_1x02",
        "J1",
        "AC_IN",
        "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        {"1": "AC1", "2": "AC2"},
        "sekundar split-core, NE sit 230 V",
    )
    sch.add(
        "Device:Polyfuse",
        "F1",
        "0.5A",
        "Fuse:Fuse_1812_4532Metric",
        {"1": "AC1", "2": "AC1F"},
        "polyfuse 1812 0.5 A",
    )
    # Always across the CT secondary, ahead of the fuse, so an open fuse
    # cannot leave the winding unloaded.
    R(sch, "R4", ("AC1", "AC2"), "100", "Resistor_SMD:R_1206_3216Metric", "RC1206FR-07100RL")
    # bridge: SS14
    sch.add("Device:D", "D1", "SS14", "Diode_SMD:D_SMA", {"1": "DC", "2": "AC1F"}, "SS14")
    sch.add("Device:D", "D2", "SS14", "Diode_SMD:D_SMA", {"1": "AC1F", "2": "GND"}, "SS14")
    sch.add("Device:D", "D3", "SS14", "Diode_SMD:D_SMA", {"1": "DC", "2": "AC2"}, "SS14")
    sch.add("Device:D", "D4", "SS14", "Diode_SMD:D_SMA", {"1": "AC2", "2": "GND"}, "SS14")
    sch.add(
        "Device:C_Polarized",
        "C1",
        "470u/25V",
        "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
        {"1": "DC", "2": "GND"},
        "electrolytic 470u 25V",
    )
    sch.add("Device:D", "D5", "SMBJ15A", "Diode_SMD:D_SMB", {"1": "DC", "2": "GND"}, "SMBJ15A")
    sch.add("Device:D", "D6", "SS34", "Diode_SMD:D_SMC", {"1": "VSYS_RAW", "2": "DC"}, "SS34")
    # USB-C power only
    usb = {p: None for p in [
        "A1","A4","A5","A6","A7","A8","A9","A12","B1","B4","B5","B6","B7","B8","B9","B12","SH"
    ]}
    for p in ("A1", "A12", "B1", "B12", "SH"):
        usb[p] = "GND"
    for p in ("A4", "A9", "B4", "B9"):
        usb[p] = "VBUS"
    usb["A5"] = "CC1"
    usb["B5"] = "CC2"
    sch.add(
        "Connector:USB_C_Receptacle_USB2.0_16P",
        "J2",
        "USB_C",
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        usb,
        "TYPE-C-31-M-12",
    )
    R(sch, "R1", ("CC1", "GND"), "5.1k", mpn="RC0402FR-075K1L")
    R(sch, "R2", ("CC2", "GND"), "5.1k", mpn="RC0402FR-075K1L")
    sch.add("Device:D", "D7", "SS34", "Diode_SMD:D_SMC", {"1": "VSYS_RAW", "2": "VBUS"}, "SS34")
    sch.add(
        "Device:FerriteBead",
        "FB1",
        "600R",
        "Inductor_SMD:L_0805_2012Metric",
        {"1": "VSYS_RAW", "2": "VSYS"},
        "BLM21PG601SN1D",
    )
    sch.add(
        "Device:C_Polarized",
        "C2",
        "100u/16V",
        "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
        {"1": "VSYS", "2": "GND"},
        "electrolytic 100u 16V",
    )
    C(sch, "C3", ("VBUS", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")
    R(sch, "R3", ("VSYS", "LED"), "2.2k", mpn="RC0402FR-072K2L")
    # LED pin 1 = K, pin 2 = A
    sch.add(
        "Device:LED",
        "D8",
        "LED",
        "LED_SMD:LED_0805_2012Metric",
        {"1": "GND", "2": "LED"},
        "LED 0805",
    )
    sch.add(
        "het68:Conn_1x02",
        "J3",
        "VSYS_OUT",
        "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        {"1": "VSYS", "2": "GND"},
        "PinHeader 1x2",
    )


def place_hat(board: Board, sch: Sch):
    by = {p["ref"]: p for p in sch.parts}
    W, H = board.w, board.h
    board.place(by["U1"], 40, 26, 0)
    # top jacks MIC3 MIC1 MIC2 (MIC1 = north, center)
    top_x = [16.5, 46.0, 69.0]
    for ref, x in zip(("J3", "J1", "J2"), top_x):
        board.place(by[ref], x, H - 10.5, 0)
    bot_x = [23.5, 53.0, 75.0]
    for ref, x in zip(("J4", "J5", "J6"), bot_x):
        board.place(by[ref], x, 10.5, 180)
    # translators on the right
    # Right of the Pico. Jacks and the module leave no strip between them,
    # so series resistors and ESD sit in the side channels, not on the Pico.
    board.place(by["U4"], 70, 32, 0)
    board.place(by["U3"], 70, 46, 0)
    board.place(by["U2"], 70, 60, 0)
    board.place(by["U5"], 82, 28, 0)
    board.place(by["C1"], 82, 24, 0)
    board.place(by["C2"], 86, 24, 0)
    board.place(by["C3"], 46, 21.4, 0)
    board.place(by["C4"], 52, 21.4, 0)
    for i, ref in enumerate(("C5", "C6", "C7", "C8", "C9", "C10")):
        board.place(by[ref], 83, 62 + i * 2.4, 90)
    rs = [p for p in sch.parts if p["ref"].startswith("R") and p["ref"][1:].isdigit() and int(p["ref"][1:]) < 40]
    for i, part in enumerate(rs):
        board.place(part, 64 + (i % 6) * 2.4, 67 + (i // 6) * 2.8, 90)
    ds = [p for p in sch.parts if p["ref"].startswith("D") and p["value"].startswith("PESD")]
    for i, part in enumerate(ds):
        board.place(part, 10 + (i % 6) * 4.0, 64.5 + (i // 6) * 2.7, 0)
    board.place(by["U6"], 82, 36, 0)
    board.place(by["C11"], 86, 36, 0)
    board.place(by["R40"], 80, 46, 90)
    board.place(by["R41"], 80, 52, 90)
    for i, ref in enumerate(("J11", "J12", "J13", "J14")):
        board.place(by[ref], 89, 28 + i * 8, 0)
    # sensors left
    board.place(by["U7"], 18, 55, 0)
    board.place(by["U8"], 18, 48, 0)
    board.place(by["FB1"], 12, 48, 90)
    board.place(by["C12"], 24, 48, 0)
    board.place(by["C13"], 24, 52, 0)
    board.place(by["R42"], 12, 58, 90)
    board.place(by["R43"], 15, 58, 90)
    board.place(by["R44"], 12, 62, 90)
    board.place(by["R45"], 15, 62, 90)
    board.place(by["R46"], 22, 62, 90)
    board.place(by["U9"], 18, 36, 0)
    board.place(by["R47"], 10, 36, 90)
    board.place(by["R48"], 10, 40, 90)
    board.place(by["C14"], 33, 36, 0)
    board.place(by["J10"], 10, 28, 0)
    board.place(by["J17"], 33, 44, 0)
    # holes
    hole_fp = "MountingHole:MountingHole_3.2mm_M3"
    for i, (x, y) in enumerate(((4, 4), (W - 4, 4), (4, H - 4), (W - 4, H - 4)), start=1):
        dummy = {
            "ref": f"H{i}",
            "value": "M3",
            "footprint": hole_fp,
            "nets": {},
            "mpn": "",
        }
        board.place(dummy, x, y, 0)


def place_sat(board: Board, sch: Sch):
    by = {p["ref"]: p for p in sch.parts}
    board.place(by["J1"], 10.5, 14, 0)
    board.place(by["U1"], 16, 28, 0)
    board.place(by["C1"], 8, 28, 90)
    board.place(by["C2"], 22, 28, 90)
    board.place(by["MK1"], 14, 40, 0)
    board.place(by["C3"], 8, 38, 0)
    board.place(by["R1"], 20, 36, 90)
    board.place(by["R2"], 22, 36, 90)
    board.place(by["D1"], 22, 42, 0)
    board.place(by["C4"], 22, 46, 0)


def place_pwr(board: Board, sch: Sch):
    by = {p["ref"]: p for p in sch.parts}
    board.place(by["J2"], 18, 28, 0)
    board.place(by["R1"], 32, 36, 90)
    board.place(by["R2"], 32, 32, 90)
    board.place(by["C3"], 32, 24, 0)
    board.place(by["D7"], 38, 38, 0)
    board.place(by["J1"], 70, 40, 0)
    board.place(by["F1"], 58, 40, 0)
    board.place(by["R4"], 64, 44, 0)
    board.place(by["D1"], 48, 34, 0)
    board.place(by["D2"], 48, 28, 180)
    board.place(by["D3"], 56, 34, 0)
    board.place(by["D4"], 56, 28, 180)
    board.place(by["C1"], 40, 16, 0)
    board.place(by["D5"], 52, 16, 0)
    board.place(by["D6"], 62, 22, 0)
    board.place(by["FB1"], 62, 14, 90)
    board.place(by["C2"], 72, 16, 0)
    board.place(by["R3"], 78, 28, 90)
    board.place(by["D8"], 78, 34, 0)
    board.place(by["J3"], 78, 22, 0)


def finish(board: Board, sch: Sch, out: Path, power_nets=None):
    board.outline()
    board.assign_nets()
    design_rules(board)
    board.add_zone("GND", pcbnew.B_Cu)
    from route2 import route_board
    missing = route_board(board)
    board.fill()
    pcb_path = out / f"{board.name}.kicad_pcb"
    board.save(pcb_path)
    sch_path = out / f"{board.name}.kicad_sch"
    sch_path.write_text(sch.emit())
    pro = out / f"{board.name}.kicad_pro"
    pro.write_text(
        """{
  "board": {"design_settings": {"rules": {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6, "min_via_drill": 0.3, "min_hole_clearance": 0.2}}},
  "meta": {"filename": "%s.kicad_pro", "version": 3},
  "sheets": [["%s.kicad_sch", ""]],
  "text_variables": {}
}
"""
        % (board.name, board.name)
    )
    (out / "fp-lib-table").write_text(
        """(fp_lib_table
  (version 7)
  (lib (name "het68")(type "KiCad")(uri "${KIPRJMOD}/../lib/het68.pretty")(options "")(descr "het68"))
)
"""
    )
    return missing


# LCSC codes checked against the catalog. Empty means not confirmed for this exact MPN.
LCSC = {
    "SN74LVC8T245PWR": "C27643",
    "AP2112K-1.8TRG1": "C176944",
    "DRV8837CDSGR": "C191000",
    "INA3221AIRGVR": "C181255",
    "DPS310": "C130156",
    "SHT40-AD1B-R2": "C2909890",
    "MMICT5848-00-012": "C20344623",
    "RC0402FR-0733RL": "C138002",
    "RC0402FR-07100RL": "C106232",
    "TYPE-C-31-M-12": "C165948",
    "RJHSE-5380": "C464586",
    "RJHSE-5380 (8P8C, bez magnetik)": "C464586",
    "SMBJ15A": "C49435193",
}


def bom(sch: Sch, path: Path):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ref", "Value", "Footprint", "MPN", "LCSC"])
        for p in sch.parts:
            w.writerow([p["ref"], p["value"], p["footprint"], p["mpn"], LCSC.get(p["mpn"], "")])


def order_bom(path: Path, sheets):
    """One line per MPN. Satellite quantity is already multiplied."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Board", "Qty", "Value", "MPN", "LCSC", "Refs", "Note"])
        for board, sch, mult in sheets:
            groups = {}
            for p in sch.parts:
                key = (p["value"], p["mpn"], p["footprint"])
                g = groups.setdefault(key, [])
                g.append(p["ref"])
            for (value, mpn, _fp), refs in groups.items():
                note = ""
                if mpn == "SS34":
                    note = "pouzdro SMC, ne SMA"
                elif not LCSC.get(mpn, "") and mpn:
                    note = "LCSC kod pro toto presne MPN neni overeny"
                if mpn.startswith("Pimoroni"):
                    note = "koupit u Pimoroni, neni na LCSC"
                w.writerow([board, len(refs) * mult, value, mpn, LCSC.get(mpn, ""), " ".join(refs), note])
        # Specified sources. Not placed on the drawn power sheet yet.
        extras = [
            ("zdroj", 1, "SCT-013-000", "YHDC SCT-013-000", "", "CT1", "kleště na 1 izolovaný vodič, není na nakreslené desce"),
            ("zdroj", 1, "CN3791", "CN3791", "C154992", "U_MPPT", "MPPT do 1S, není na nakreslené desce"),
            ("zdroj", 1, "BQ25895", "BQ25895RTWR", "C80200", "U_CHG", "I2C power-path a 5 V, není na nakreslené desce"),
            ("zdroj", 1, "21700 holder", "BH-21700-B1BJ001", "C20606791", "BT1", "SMT držák, článek musí mít ochranu"),
            ("zdroj", 1, "21700", "21700 s PCM", "", "BAT1", "chráněný článek, ne holý"),
            ("zdroj", 1, "PAC1934", "PAC1934T-I/JQ", "C623960", "U_MON", "4× V a I, není na nakreslené desce"),
            ("zdroj", 1, "ADS1115", "ADS1115IDGSR", "", "U_ADC", "teploty NTC, LCSC kod dohledat"),
            ("zdroj", 4, "NTC 10k", "NTC 10k", "", "TH1-4", "LCSC kod dohledat"),
        ]
        for row in extras:
            w.writerow(row)


def main():
    app = wx.App(False)
    PRETTY.mkdir(parents=True, exist_ok=True)
    write_t5848_fp(PRETTY / "T5848.kicad_mod")

    # HAT
    hat = Sch("het68-hat", "het68 HAT pro Pimoroni Pico Plus 2")
    base_libs(hat)
    build_hat(hat)
    hb = Board("het68-hat", 94, 96, 2)
    place_hat(hb, hat)
    hb.text("het68 HAT rev C  2L", 64, 23.2, size=0.7)
    hb.text("MIC1 sever", 64, 81, size=0.7)
    hb.text("T568B 1=SCK 3=WS 4=SD 7=3V3 8=LED", 64, 25.2, size=0.45)
    hb.text("PZ pin1 = +", 86, 56, size=0.6)
    out = ROOT / "het68-hat"
    out.mkdir(exist_ok=True)
    miss = finish(hb, hat, out, None)
    bom(hat, out / "bom.csv")
    print("HAT unrouted", len(miss), miss[:30])

    sat = Sch("het68-sat", "het68 satelit mikrofonu + LED")
    base_libs(sat)
    build_sat(sat)
    sb = Board("het68-sat", 28, 52, 2)
    place_sat(sb, sat)
    sb.text("het68 SAT rev A", 14, 4, size=0.8)
    sb.text("port vzhuru", 14, 48, size=0.7)
    sb.text("1 SCK 3 WS 4 SD 7 3V3 8 LED", 14, 8, size=0.45)
    out = ROOT / "het68-sat"
    out.mkdir(exist_ok=True)
    miss = finish(sb, sat, out, {"GND", "+3V3", "+1V8"})
    bom(sat, out / "bom.csv")
    print("SAT unrouted", len(miss), miss)

    pwr = Sch("het68-pwr", "het68 napajeni — jen sekundar split-core")
    base_libs(pwr)
    build_pwr(pwr)
    pb = Board("het68-pwr", 90, 50, 2)
    place_pwr(pb, pwr)
    pb.text("het68 PWR rev A", 45, 46, size=1.2)
    pb.text("JEN SEKUNDAR SPLIT-CORE", 45, 6, size=1.0)
    pb.text("NE 230 V", 45, 3.5, size=1.0)
    out = ROOT / "het68-pwr"
    out.mkdir(exist_ok=True)
    miss = finish(pb, pwr, out, {"GND", "VSYS", "VSYS_RAW", "VBUS", "DC"})
    bom(pwr, out / "bom.csv")
    print("PWR unrouted", len(miss), miss)
    order_bom(ROOT / "BOM.csv", [("hat", hat, 1), ("sat", sat, 6), ("pwr", pwr, 1)])
    print("done")


if __name__ == "__main__":
    main()
