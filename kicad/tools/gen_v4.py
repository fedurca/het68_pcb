#!/usr/bin/env python3
"""Generate het68 v4: 6L Core (RP2350B + J_MESH), LVDS satellite, three power SKUs.

HAT v3.0.0 is not regenerated here. Run with KiCad's Python.
"""
from __future__ import annotations

import csv
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pcbnew
import wx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_boards import (  # noqa: E402
    Board,
    Sch,
    base_libs,
    bom,
    box_symbol,
    conn_symbol,
    design_rules,
    load_std,
    R,
    C,
    ROOT,
    PRETTY,
    uid,
    write_t5848_fp,
    write_rj45_fp,
)
from route2 import route_board  # noqa: E402
from route6 import faraday_planes, route_stripline, set_stackup  # noqa: E402

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

GPIO_PAD = {
    0: "77", 1: "78", 2: "79", 3: "80", 4: "1", 5: "2", 6: "3", 7: "4",
    8: "6", 9: "7", 10: "8", 11: "9", 12: "11", 13: "12", 14: "13", 15: "14",
    16: "16", 17: "17", 18: "18", 19: "19", 20: "20", 21: "21", 22: "22", 23: "23",
    24: "25", 25: "26", 26: "27", 27: "28", 28: "36", 29: "37", 30: "38", 31: "39",
    32: "40", 33: "42", 34: "43", 35: "44", 36: "45", 37: "46", 38: "47", 39: "48",
    40: "49", 41: "52", 42: "53", 43: "54", 44: "55", 45: "56", 46: "57", 47: "58",
}
IOVDD_PADS = ("5", "15", "24", "29", "41", "50", "60", "76")
DVDD_PADS = ("10", "32", "51")


class SchV4(Sch):
    def __init__(self, name, title, rails, rev="A"):
        super().__init__(name, title)
        self.rails = rails
        self.rev = rev

    def emit(self) -> str:
        self.pack()
        libs = "\n".join(self.symbols.values())
        body = []
        fx = 20
        for i, net in enumerate(self.rails):
            if f"het68:{net}" not in self.symbols:
                continue
            fy = 30 + i * 12
            body.append(self._pwr(net, fx, fy, i))
            body.append(self._glabel(net, fx + 10, fy, 0))
            body.append(self._wire(fx, fy, fx + 10, fy))
        for part in self.parts:
            body.append(self._part(part))
        page_w, page_h = self.page
        return f'''(kicad_sch
  (version 20250114)
  (generator "het68-gen-v4")
  (generator_version "10.0")
  (uuid "{self.root}")
  (paper "User" {page_w:.0f} {page_h:.0f})
  (title_block
    (title "{self.title}")
    (date "2026-10-29")
    (rev "{self.rev}")
    (comment 1 "het68 v4 — Core 6L + silova deska, KiCad 10")
  )
  (lib_symbols
{libs}
  )
{chr(10).join(body)}
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
'''


def add_power_syms(sch: Sch, nets):
    for net in nets:
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
        from gen_boards import symbol_pins
        sch.add_lib(f"het68:{net}", raw, symbol_pins(raw))


def add_box(sch, maker):
    raw, pins = maker()
    lib_id = re.search(r'\(symbol "([^"]+)"', raw).group(1)
    sch.add_lib(lib_id, raw, pins)
    return lib_id


def v4_libs(sch: Sch, extra_rails):
    base_libs(sch)
    add_power_syms(sch, extra_rails)
    for n, lib_id, fp in [
        (8, "het68:Conn_1x08", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical"),
        (3, "het68:Conn_1x03", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"),
        (20, "het68:Conn_2x10", "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical"),
    ]:
        raw, pins = conn_symbol(n, lib_id, fp)
        sch.add_lib(lib_id, raw, pins)
    for maker in (
        rp2350_symbol,
        rj_lvds_symbol,
        flash_symbol,
        psram_symbol,
        ldo_symbol,
        lvds047_symbol,
        lvds32_symbol,
        lvds1_symbol,
        lvds2_symbol,
        txs0104_symbol,
        cmc_symbol,
        adxl_symbol,
        nmos_symbol,
        pmos_symbol,
        opamp_symbol,
        cn3791_symbol,
        boost_symbol,
        xtal_symbol,
        gdt_symbol,
    ):
        add_box(sch, maker)
    try:
        load_std(sch, "Device.kicad_sym", "D_TVS", "Device")
    except SystemExit:
        pass
    try:
        load_std(sch, "Device.kicad_sym", "Crystal", "Device")
    except SystemExit:
        pass
    try:
        load_std(sch, "Device.kicad_sym", "Battery", "Device")
    except SystemExit:
        pass


def rp2350_symbol():
    left, right = [], []
    for g in range(0, 24):
        left.append({"num": GPIO_PAD[g], "name": f"GPIO{g}", "type": "bidirectional", "side": "L"})
    for g in range(24, 48):
        right.append({"num": GPIO_PAD[g], "name": f"GPIO{g}", "type": "bidirectional", "side": "R"})
    extras_l = [
        ("66", "USB_DM", "bidirectional"),
        ("67", "USB_DP", "bidirectional"),
        ("30", "XIN", "input"),
        ("31", "XOUT", "output"),
        ("33", "SWCLK", "input"),
        ("34", "SWDIO", "bidirectional"),
        ("35", "RUN", "input"),
        ("75", "QSPI_SS", "output"),
        ("71", "QSPI_SCLK", "output"),
        ("72", "QSPI_SD0", "bidirectional"),
        ("74", "QSPI_SD1", "bidirectional"),
        ("73", "QSPI_SD2", "bidirectional"),
        ("70", "QSPI_SD3", "bidirectional"),
    ]
    extras_r = [
        ("5", "IOVDD", "power_in"),
        ("10", "DVDD", "power_in"),
        ("59", "ADC_AVDD", "power_in"),
        ("61", "VREG_AVDD", "power_in"),
        ("62", "VREG_PGND", "power_in"),
        ("63", "VREG_LX", "passive"),
        ("64", "VREG_VIN", "power_in"),
        ("65", "VREG_FB", "passive"),
        ("68", "USB_OTP_VDD", "power_in"),
        ("69", "QSPI_IOVDD", "power_in"),
        ("81", "GND", "power_in"),
    ]
    for num, name, typ in extras_l:
        left.append({"num": num, "name": name, "type": typ, "side": "L"})
    for num, name, typ in extras_r:
        right.append({"num": num, "name": name, "type": typ, "side": "R"})
    for p in IOVDD_PADS:
        if p == "5":
            continue
        right.append({"num": p, "name": f"IOVDD_{p}", "type": "power_in", "side": "R"})
    for p in DVDD_PADS:
        if p == "10":
            continue
        right.append({"num": p, "name": f"DVDD_{p}", "type": "power_in", "side": "R"})
    return box_symbol(
        "het68:RP2350B",
        "U",
        "RP2350B",
        "Package_DFN_QFN:QFN-80-1EP_10x10mm_P0.4mm_EP3.4x3.4mm_ThermalVias",
        left + right,
        w=30.48,
    )


def rj_lvds_symbol():
    pins = [
        {"num": n, "name": name, "type": "passive", "side": "L"}
        for n, name in (
            ("1", "SCK_P"), ("2", "SCK_N"), ("3", "WS_P"), ("4", "SD_P"),
            ("5", "SD_N"), ("6", "WS_N"), ("7", "3V3"), ("8", "LED"), ("SH", "SHIELD"),
        )
    ]
    return box_symbol("het68:RJ45_LVDS", "J", "RJ45_LVDS", "het68:RJ45_RJHSE5380_het68", pins, w=15.24)


def flash_symbol():
    pins = [
        {"num": "1", "name": "CS", "type": "input", "side": "L"},
        {"num": "2", "name": "DO", "type": "bidirectional", "side": "L"},
        {"num": "3", "name": "WP", "type": "bidirectional", "side": "L"},
        {"num": "4", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "5", "name": "DI", "type": "bidirectional", "side": "R"},
        {"num": "6", "name": "CLK", "type": "input", "side": "R"},
        {"num": "7", "name": "HOLD", "type": "bidirectional", "side": "R"},
        {"num": "8", "name": "VCC", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:W25Q128", "U", "W25Q128", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", pins)


def psram_symbol():
    pins = [
        {"num": "1", "name": "CE", "type": "input", "side": "L"},
        {"num": "2", "name": "SO", "type": "bidirectional", "side": "L"},
        {"num": "3", "name": "SIO2", "type": "bidirectional", "side": "L"},
        {"num": "4", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "5", "name": "SI", "type": "bidirectional", "side": "R"},
        {"num": "6", "name": "SCLK", "type": "input", "side": "R"},
        {"num": "7", "name": "SIO3", "type": "bidirectional", "side": "R"},
        {"num": "8", "name": "VCC", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:APS6404L", "U", "APS6404L", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", pins)


def ldo_symbol():
    pins = [
        {"num": "1", "name": "VIN", "type": "passive", "side": "L"},
        {"num": "2", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "3", "name": "EN", "type": "input", "side": "L"},
        {"num": "4", "name": "NC", "type": "no_connect", "side": "R"},
        {"num": "5", "name": "VOUT", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:AP2112K", "U", "AP2112K", "Package_TO_SOT_SMD:SOT-23-5", pins)


def lvds047_symbol():
    # SN65LVDS047 TSSOP-16
    pins = [
        {"num": "1", "name": "DIN1", "type": "input", "side": "L"},
        {"num": "6", "name": "DIN2", "type": "input", "side": "L"},
        {"num": "8", "name": "DIN3", "type": "input", "side": "L"},
        {"num": "13", "name": "DIN4", "type": "input", "side": "L"},
        {"num": "15", "name": "EN", "type": "input", "side": "L"},
        {"num": "16", "name": "ENn", "type": "input", "side": "L"},
        {"num": "7", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "2", "name": "Y1n", "type": "output", "side": "R"},
        {"num": "3", "name": "Y1p", "type": "output", "side": "R"},
        {"num": "5", "name": "Y2n", "type": "output", "side": "R"},
        {"num": "4", "name": "Y2p", "type": "output", "side": "R"},
        {"num": "9", "name": "Y3n", "type": "output", "side": "R"},
        {"num": "10", "name": "Y3p", "type": "output", "side": "R"},
        {"num": "12", "name": "Y4n", "type": "output", "side": "R"},
        {"num": "11", "name": "Y4p", "type": "output", "side": "R"},
        {"num": "14", "name": "VCC", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:SN65LVDS047", "U", "SN65LVDS047", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", pins, w=20.32)


def lvds32_symbol():
    pins = [
        {"num": "1", "name": "1B", "type": "passive", "side": "L"},
        {"num": "2", "name": "1A", "type": "passive", "side": "L"},
        {"num": "6", "name": "2A", "type": "passive", "side": "L"},
        {"num": "7", "name": "2B", "type": "passive", "side": "L"},
        {"num": "10", "name": "3A", "type": "passive", "side": "L"},
        {"num": "9", "name": "3B", "type": "passive", "side": "L"},
        {"num": "14", "name": "4A", "type": "passive", "side": "L"},
        {"num": "15", "name": "4B", "type": "passive", "side": "L"},
        {"num": "4", "name": "G", "type": "passive", "side": "L"},
        {"num": "12", "name": "Gn", "type": "passive", "side": "L"},
        {"num": "8", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "3", "name": "1Y", "type": "output", "side": "R"},
        {"num": "5", "name": "2Y", "type": "output", "side": "R"},
        {"num": "11", "name": "3Y", "type": "output", "side": "R"},
        {"num": "13", "name": "4Y", "type": "output", "side": "R"},
        {"num": "16", "name": "VCC", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:SN65LVDS32", "U", "SN65LVDS32", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", pins, w=20.32)


def lvds1_symbol():
    pins = [
        {"num": "1", "name": "DIN", "type": "input", "side": "L"},
        {"num": "2", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "5", "name": "VCC", "type": "power_in", "side": "R"},
        {"num": "3", "name": "Y", "type": "output", "side": "R"},
        {"num": "4", "name": "Z", "type": "output", "side": "R"},
    ]
    return box_symbol("het68:SN65LVDS1", "U", "SN65LVDS1", "Package_TO_SOT_SMD:SOT-23-5", pins)


def lvds2_symbol():
    pins = [
        {"num": "2", "name": "RIN_P", "type": "input", "side": "L"},
        {"num": "3", "name": "RIN_N", "type": "input", "side": "L"},
        {"num": "4", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "1", "name": "VCC", "type": "power_in", "side": "R"},
        {"num": "5", "name": "ROUT", "type": "output", "side": "R"},
    ]
    return box_symbol("het68:SN65LVDS2", "U", "SN65LVDS2", "Package_TO_SOT_SMD:SOT-23-5", pins)


def txs0104_symbol():
    pins = [
        {"num": "1", "name": "VCCA", "type": "power_in", "side": "L"},
        {"num": "2", "name": "A1", "type": "bidirectional", "side": "L"},
        {"num": "3", "name": "A2", "type": "bidirectional", "side": "L"},
        {"num": "4", "name": "A3", "type": "bidirectional", "side": "L"},
        {"num": "5", "name": "A4", "type": "bidirectional", "side": "L"},
        {"num": "6", "name": "NC", "type": "no_connect", "side": "L"},
        {"num": "7", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "8", "name": "OE", "type": "input", "side": "R"},
        {"num": "9", "name": "B4", "type": "bidirectional", "side": "R"},
        {"num": "10", "name": "B3", "type": "bidirectional", "side": "R"},
        {"num": "11", "name": "B2", "type": "bidirectional", "side": "R"},
        {"num": "12", "name": "B1", "type": "bidirectional", "side": "R"},
        {"num": "13", "name": "NC2", "type": "no_connect", "side": "R"},
        {"num": "14", "name": "VCCB", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:TXS0104E", "U", "TXS0104E", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", pins, w=17.78)


def cmc_symbol():
    pins = [
        {"num": "1", "name": "1", "type": "passive", "side": "L"},
        {"num": "2", "name": "2", "type": "passive", "side": "L"},
        {"num": "4", "name": "4", "type": "passive", "side": "R"},
        {"num": "3", "name": "3", "type": "passive", "side": "R"},
    ]
    return box_symbol(
        "het68:CMC",
        "FL",
        "CMC_0805",
        "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
        pins,
        w=10.16,
    )


def adxl_symbol():
    pins = [
        {"num": "11", "name": "CS", "type": "input", "side": "L"},
        {"num": "14", "name": "SCLK", "type": "input", "side": "L"},
        {"num": "12", "name": "MOSI", "type": "input", "side": "L"},
        {"num": "13", "name": "MISO", "type": "output", "side": "L"},
        {"num": "2", "name": "VDDIO", "type": "power_in", "side": "R"},
        {"num": "6", "name": "VDD", "type": "power_in", "side": "R"},
        {"num": "4", "name": "GND", "type": "power_in", "side": "R"},
        {"num": "5", "name": "GND2", "type": "power_in", "side": "R"},
        {"num": "8", "name": "INT2", "type": "output", "side": "R"},
        {"num": "9", "name": "INT1", "type": "output", "side": "R"},
        {"num": "1", "name": "NC1", "type": "no_connect", "side": "L"},
        {"num": "3", "name": "NC3", "type": "no_connect", "side": "L"},
        {"num": "7", "name": "AUX", "type": "passive", "side": "R"},
        {"num": "10", "name": "NC10", "type": "no_connect", "side": "L"},
        {"num": "15", "name": "NC15", "type": "no_connect", "side": "R"},
        {"num": "16", "name": "NC16", "type": "no_connect", "side": "R"},
        {"num": "17", "name": "EP", "type": "power_in", "side": "R"},
    ]
    return box_symbol(
        "het68:ADXL355",
        "U",
        "ADXL355",
        "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
        pins,
        w=17.78,
    )


def nmos_symbol():
    pins = [
        {"num": "1", "name": "G", "type": "input", "side": "L"},
        {"num": "2", "name": "S", "type": "passive", "side": "L"},
        {"num": "3", "name": "D", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:NMOS", "Q", "AO3400A", "Package_TO_SOT_SMD:SOT-23", pins)


def pmos_symbol():
    pins = [
        {"num": "1", "name": "G", "type": "input", "side": "L"},
        {"num": "2", "name": "S", "type": "passive", "side": "L"},
        {"num": "3", "name": "D", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:PMOS", "Q", "AO3401A", "Package_TO_SOT_SMD:SOT-23", pins)


def opamp_symbol():
    pins = [
        {"num": "1", "name": "OUT", "type": "output", "side": "R"},
        {"num": "2", "name": "VSS", "type": "power_in", "side": "L"},
        {"num": "3", "name": "IN+", "type": "input", "side": "L"},
        {"num": "4", "name": "IN-", "type": "input", "side": "L"},
        {"num": "5", "name": "VDD", "type": "power_in", "side": "R"},
    ]
    return box_symbol("het68:MCP6001", "U", "MCP6001", "Package_TO_SOT_SMD:SOT-23-5", pins)


def cn3791_symbol():
    pins = [
        {"num": "1", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "2", "name": "VIN", "type": "passive", "side": "L"},
        {"num": "3", "name": "CS", "type": "passive", "side": "L"},
        {"num": "4", "name": "TEMP", "type": "passive", "side": "L"},
        {"num": "5", "name": "COMP", "type": "passive", "side": "R"},
        {"num": "6", "name": "FB", "type": "input", "side": "R"},
        {"num": "7", "name": "DRV", "type": "passive", "side": "R"},
        {"num": "8", "name": "VCC", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:CN3791", "U", "CN3791", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", pins)


def boost_symbol():
    pins = [
        {"num": "1", "name": "SW", "type": "passive", "side": "L"},
        {"num": "2", "name": "GND", "type": "power_in", "side": "L"},
        {"num": "3", "name": "FB", "type": "input", "side": "L"},
        {"num": "4", "name": "EN", "type": "input", "side": "R"},
        {"num": "5", "name": "VIN", "type": "passive", "side": "R"},
        {"num": "6", "name": "VIN2", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:FP6291", "U", "FP6291", "Package_TO_SOT_SMD:SOT-23-6", pins)


def xtal_symbol():
    pins = [
        {"num": "1", "name": "XIN", "type": "passive", "side": "L"},
        {"num": "2", "name": "GND1", "type": "power_in", "side": "L"},
        {"num": "3", "name": "XOUT", "type": "passive", "side": "R"},
        {"num": "4", "name": "GND2", "type": "power_in", "side": "R"},
    ]
    return box_symbol(
        "het68:XTAL_3225",
        "Y",
        "12MHz",
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        pins,
    )


def gdt_symbol():
    pins = [
        {"num": "1", "name": "1", "type": "passive", "side": "L"},
        {"num": "2", "name": "2", "type": "passive", "side": "R"},
    ]
    return box_symbol("het68:GDT", "GDT", "GDT", "Fuse:Fuse_1812_4532Metric", pins)


def tvs(sch, ref, nets, value="PESD5V0X1BT"):
    lib = "Device:D_TVS" if "Device:D_TVS" in sch.symbols else "Device:D"
    sch.add(lib, ref, value, "Diode_SMD:D_SOD-323", {"1": nets[0], "2": nets[1]}, value)


def usb_c(sch, ref, vbus, gnd="GND"):
    usb = {p: None for p in [
        "A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12",
        "B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12", "SH",
    ]}
    for p in ("A1", "A12", "B1", "B12", "SH"):
        usb[p] = gnd
    for p in ("A4", "A9", "B4", "B9"):
        usb[p] = vbus
    usb["A5"] = "CC1"
    usb["B5"] = "CC2"
    sch.add(
        "Connector:USB_C_Receptacle_USB2.0_16P",
        ref,
        "USB_C",
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        usb,
        "TYPE-C-31-M-12",
    )


PWR_MAP = {
    1: "+5V_ALWAYS", 2: "GND", 3: "+5V_ALWAYS", 4: "GND",
    5: "+3V3_RF", 6: "GND", 7: "I2C0_SDA", 8: "I2C0_SCL",
    9: "ADC_I", 10: "ADC_ROGO", 11: "ADC_HARVEST", 12: "ADC_PT1000",
    13: "BURDEN_EN", 14: "PG_5V", 15: "PT1000_RTN", 16: "EN_RF",
    17: "I2C0_ALERT", 18: "SHIELD", 19: "GND", 20: "GND",
}


def rp_nets():
    n = {str(i): None for i in range(1, 82)}
    for p in IOVDD_PADS:
        n[p] = "+3V3_DIG"
    for p in DVDD_PADS:
        n[p] = "DVDD"
    n.update({
        "59": "+3V3_DIG", "61": "+3V3_DIG", "62": "GND",
        "63": "VREG_LX", "64": "+3V3_DIG", "65": "DVDD",
        "66": "USB_DM", "67": "USB_DP",
        "68": "+3V3_DIG", "69": "+3V3_DIG",
        "70": "QSPI_SD3", "71": "QSPI_SCLK", "72": "QSPI_SD0",
        "73": "QSPI_SD2", "74": "QSPI_SD1", "75": "QSPI_SS",
        "30": "XIN", "31": "XOUT", "33": "SWCLK", "34": "SWDIO", "35": "RUN",
        "81": "GND",
        GPIO_PAD[0]: "UART_TX_MCU", GPIO_PAD[1]: "UART_RX_MCU",
        GPIO_PAD[2]: "I2C1_SDA", GPIO_PAD[3]: "I2C1_SCL",
        GPIO_PAD[4]: "I2C0_SDA", GPIO_PAD[5]: "I2C0_SCL",
        GPIO_PAD[6]: "PIEZO_IN1", GPIO_PAD[7]: "PIEZO_IN2",
        GPIO_PAD[8]: "I2S_WS", GPIO_PAD[9]: "I2S_SCK",
        GPIO_PAD[10]: "LED4_DIN", GPIO_PAD[11]: "LED5_DIN", GPIO_PAD[12]: "LED6_DIN",
        GPIO_PAD[13]: "I2S_SD4", GPIO_PAD[14]: "I2S_SD5", GPIO_PAD[15]: "I2S_SD6",
        GPIO_PAD[16]: "I2S_SD3", GPIO_PAD[17]: "I2S_SD2", GPIO_PAD[18]: "I2S_SD1",
        GPIO_PAD[19]: "LED3_DIN", GPIO_PAD[20]: "LED2_DIN", GPIO_PAD[21]: "LED1_DIN",
        GPIO_PAD[22]: "DSP_AWAKE",
        GPIO_PAD[23]: "SPI0_SCK", GPIO_PAD[24]: "SPI0_MOSI", GPIO_PAD[25]: "SPI0_MISO",
        GPIO_PAD[26]: "ADC_I", GPIO_PAD[27]: "ADC_ROGO",
        GPIO_PAD[28]: "ADC_PT1000", GPIO_PAD[29]: "ADC_HARVEST",
        GPIO_PAD[30]: "SPI0_CS", GPIO_PAD[31]: "BURDEN_EN",
        GPIO_PAD[32]: "PSRAM_CE", GPIO_PAD[33]: "PSRAM_SO",
        GPIO_PAD[34]: "PSRAM_SI", GPIO_PAD[35]: "PSRAM_SCLK",
        GPIO_PAD[36]: "PG_5V",
    })
    return n


def build_core(sch: Sch):
    sch.add(
        "het68:RP2350B", "U1", "RP2350B",
        "Package_DFN_QFN:QFN-80-1EP_10x10mm_P0.4mm_EP3.4x3.4mm_ThermalVias",
        rp_nets(), "RP2350B",
    )
    sch.add("het68:W25Q128", "U2", "W25Q128JVSIQ", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            {"1": "QSPI_SS", "2": "QSPI_SD1", "3": "QSPI_SD2", "4": "GND",
             "5": "QSPI_SD0", "6": "QSPI_SCLK", "7": "QSPI_SD3", "8": "+3V3_DIG"},
            "W25Q128JVSIQ")
    sch.add("het68:APS6404L", "U3", "APS6404L", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            {"1": "PSRAM_CE", "2": "PSRAM_SO", "3": "+3V3_DIG", "4": "GND",
             "5": "PSRAM_SI", "6": "PSRAM_SCLK", "7": "+3V3_DIG", "8": "+3V3_DIG"},
            "APS6404L-3SQR-SN")
    sch.add("het68:XTAL_3225", "Y1", "12MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
            {"1": "XIN", "2": "GND", "3": "XOUT", "4": "GND"}, "12MHz 3225")
    C(sch, "C_X1", ("XIN", "GND"), "15p")
    C(sch, "C_X2", ("XOUT", "GND"), "15p")
    sch.add("Device:L", "L_VREG", "2.2uH", "Inductor_SMD:L_0805_2012Metric",
            {"1": "VREG_LX", "2": "DVDD"}, "2.2uH VREG")
    C(sch, "C_DVDD", ("DVDD", "GND"), "2.2u", "Capacitor_SMD:C_0805_2012Metric", "CL21A225KOQNNNE")

    # Gated 3V3 and 1V8. EN = WAKE_DSP from Heltec.
    sch.add("het68:AP2112K", "U4", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+5V_ALWAYS", "2": "GND", "3": "WAKE_DSP", "4": None, "5": "+3V3_DIG"},
            "AP2112K-3.3TRG1")
    sch.add("het68:AP2112K", "U5", "AP2112K-1.8", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+5V_ALWAYS", "2": "GND", "3": "WAKE_DSP", "4": None, "5": "+1V8_AUDIO"},
            "AP2112K-1.8TRG1")
    C(sch, "C3V3A", ("+3V3_DIG", "GND"), "1u", mpn="CL10A105KA8NNNC")
    C(sch, "C3V3B", ("+3V3_DIG", "GND"), "100n")
    C(sch, "C18A", ("+1V8_AUDIO", "GND"), "1u", mpn="CL10A105KA8NNNC")
    C(sch, "C18B", ("+1V8_AUDIO", "GND"), "100n")
    R(sch, "R_RUN", ("RUN", "+3V3_DIG"), "10k", mpn="RC0603FR-0710KL")
    R(sch, "R_WK", ("WAKE_DSP", "GND"), "100k", mpn="RC0603FR-07100KL")

    usb_c(sch, "J_USB", "VBUS")
    R(sch, "R_CC1", ("CC1", "GND"), "5.1k", mpn="RC0603FR-075K1L")
    R(sch, "R_CC2", ("CC2", "GND"), "5.1k", mpn="RC0603FR-075K1L")
    sch.add("Device:D", "D_USB", "SS34", "Diode_SMD:D_SMC", {"1": "+5V_ALWAYS", "2": "VBUS"}, "SS34")
    C(sch, "C_VBUS", ("VBUS", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")

    mesh = {
        "1": "GND", "2": "+5V_ALWAYS", "3": "UART_TX", "4": "UART_RX",
        "5": "WAKE_DSP", "6": "DSP_AWAKE", "7": "HELTEC_RST", "8": None,
    }
    sch.add("het68:Conn_1x08", "J_MESH", "J_MESH",
            "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", mesh, "PinHeader 1x8 Heltec V3")
    sch.add("het68:Conn_1x08", "J_STAMP", "J_STAMP_DNP",
            "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
            {**mesh, "2": "+3V3_RF"}, "DNP stamp RAK class")
    R(sch, "R_TX", ("UART_TX_MCU", "UART_TX"), "22")
    R(sch, "R_RX", ("UART_RX", "UART_RX_MCU"), "22")
    tvs(sch, "D_TX", ("UART_TX", "GND"))
    tvs(sch, "D_RX", ("UART_RX", "GND"))
    sch.add("het68:Conn_1x03", "J_SWD", "SWD",
            "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
            {"1": "SWCLK", "2": "GND", "3": "SWDIO"}, "SWD")

    sch.add("het68:Conn_2x10", "J_PWR", "J_PWR",
            "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
            {str(k): v for k, v in PWR_MAP.items()}, "interconnect 2x10")
    R(sch, "R_SDA0", ("I2C0_SDA", "+3V3_DIG"), "4.7k", mpn="RC0603FR-074K7L")
    R(sch, "R_SCL0", ("I2C0_SCL", "+3V3_DIG"), "4.7k", mpn="RC0603FR-074K7L")
    R(sch, "R_SDA1", ("I2C1_SDA", "+3V3_DIG"), "4.7k", mpn="RC0603FR-074K7L")
    R(sch, "R_SCL1", ("I2C1_SCL", "+3V3_DIG"), "4.7k", mpn="RC0603FR-074K7L")
    R(sch, "R_PT", ("+3V3_DIG", "ADC_PT1000"), "1k", mpn="RC0603FR-071KL")
    R(sch, "R_PT2", ("ADC_PT1000", "PT1000_RTN"), "0", mpn="RC0603FR-070RL")
    R(sch, "R_SH", ("SHIELD", "GND"), "0", mpn="RC0603FR-070RL")
    R(sch, "R_ENRF", ("EN_RF", "+3V3_RF"), "10k", mpn="RC0603FR-0710KL")
    R(sch, "R_ALRT", ("I2C0_ALERT", "+3V3_DIG"), "10k", mpn="RC0603FR-0710KL")

    sch.add("Sensor_Pressure:BMP280", "U7", "DPS310",
            "Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering",
            {"1": "GND", "2": "+3V3_DIG", "3": "I2C1_SDA", "4": "I2C1_SCL",
             "5": "+3V3_DIG", "6": "+3V3_DIG", "7": "GND", "8": "+3V3_DIG"}, "DPS310")
    sch.add("Sensor_Humidity:SHT4x", "U8", "SHT40",
            "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
            {"1": "I2C1_SDA", "2": "I2C1_SCL", "3": "+3V3_DIG", "4": "GND"}, "SHT40-AD1B-R2")
    sch.add("het68:ADXL355", "U9", "ADXL355",
            "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
            {"1": None, "2": "+1V8_AUDIO", "3": None, "4": "GND", "5": "GND",
             "6": "+1V8_AUDIO", "7": "GND", "8": None, "9": None, "10": None,
             "11": "SPI0_CS", "12": "SPI0_MOSI", "13": "SPI0_MISO", "14": "SPI0_SCK",
             "15": None, "16": None, "17": "GND"}, "ADXL355BCCZ")
    C(sch, "C_ADX", ("+1V8_AUDIO", "GND"), "100n")

    sch.add("Driver_Motor:DRV8837C", "U6", "DRV8837C",
            "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
            {"1": "+3V3_DIG", "2": "PIEZO_P", "3": "PIEZO_N", "4": "GND",
             "5": "PIEZO_IN2", "6": "PIEZO_IN1", "7": "+3V3_DIG", "8": "+3V3_DIG", "9": "GND"},
            "DRV8837CDSGR")
    C(sch, "C_PZ", ("+3V3_DIG", "GND"), "100n")
    for i, ref in enumerate(("J11", "J12", "J13", "J14"), start=1):
        sch.add("het68:Conn_1x02", ref, f"PZ{i}",
                "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                {"1": "PIEZO_P", "2": "PIEZO_N"}, "PS1240")

    # Three quad LVDS drivers: jacks 1-2, 3-4, 5-6.
    for idx, (ref, jacks) in enumerate((
        ("U10", (1, 2)), ("U11", (3, 4)), ("U12", (5, 6)),
    ), start=1):
        a, b = jacks
        sch.add("het68:SN65LVDS047", ref, "SN65LVDS047",
                "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
                {
                    "1": "I2S_SCK", "6": "I2S_WS", "8": "I2S_SCK", "13": "I2S_WS",
                    "15": "+3V3_DIG", "16": "GND", "7": "GND", "14": "+3V3_DIG",
                    "3": f"SCK{a}_P", "2": f"SCK{a}_N",
                    "4": f"WS{a}_P", "5": f"WS{a}_N",
                    "10": f"SCK{b}_P", "9": f"SCK{b}_N",
                    "11": f"WS{b}_P", "12": f"WS{b}_N",
                }, "SN65LVDS047PW")
        C(sch, f"C_LV{idx}", ("+3V3_DIG", "GND"), "100n")

    sch.add("het68:SN65LVDS32", "U13", "SN65LVDS32",
            "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            {
                "2": "SD1_P", "1": "SD1_N", "3": "I2S_SD1",
                "6": "SD2_P", "7": "SD2_N", "5": "I2S_SD2",
                "10": "SD3_P", "9": "SD3_N", "11": "I2S_SD3",
                "14": "SD4_P", "15": "SD4_N", "13": "I2S_SD4",
                "4": "+3V3_DIG", "12": "GND", "8": "GND", "16": "+3V3_DIG",
            }, "SN65LVDS32D")
    sch.add("het68:SN65LVDS32", "U14", "SN65LVDS32",
            "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            {
                "2": "SD5_P", "1": "SD5_N", "3": "I2S_SD5",
                "6": "SD6_P", "7": "SD6_N", "5": "I2S_SD6",
                "10": "GND", "9": "GND", "11": None,
                "14": "GND", "15": "GND", "13": None,
                "4": "+3V3_DIG", "12": "GND", "8": "GND", "16": "+3V3_DIG",
            }, "SN65LVDS32D")
    C(sch, "C_RX1", ("+3V3_DIG", "GND"), "100n")
    C(sch, "C_RX2", ("+3V3_DIG", "GND"), "100n")

    led = {1: "LED1_DIN", 2: "LED2_DIN", 3: "LED3_DIN", 4: "LED4_DIN", 5: "LED5_DIN", 6: "LED6_DIN"}
    for i in range(1, 7):
        sch.add("het68:RJ45_LVDS", f"J{i}", f"MIC{i}",
                "het68:RJ45_RJHSE5380_het68",
                {
                    "1": f"SCK{i}_PJ", "2": f"SCK{i}_NJ",
                    "3": f"WS{i}_PJ", "6": f"WS{i}_NJ",
                    "4": f"SD{i}_PJ", "5": f"SD{i}_NJ",
                    "7": f"MIC{i}_3V3", "8": led[i], "SH": "GND",
                }, "RJHSE-5380")
        sch.add("het68:CMC", f"FL{i}A", "CMC",
                "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
                {"1": f"SCK{i}_P", "4": f"SCK{i}_PJ", "2": f"SCK{i}_N", "3": f"SCK{i}_NJ"}, "ACM2012")
        sch.add("het68:CMC", f"FL{i}B", "CMC",
                "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
                {"1": f"WS{i}_P", "4": f"WS{i}_PJ", "2": f"WS{i}_N", "3": f"WS{i}_NJ"}, "ACM2012")
        tvs(sch, f"DT{i}A", (f"SCK{i}_PJ", f"SCK{i}_NJ"))
        tvs(sch, f"DT{i}B", (f"WS{i}_PJ", f"WS{i}_NJ"))
        tvs(sch, f"DT{i}C", (f"SD{i}_PJ", f"SD{i}_NJ"))
        sch.add("Device:Polyfuse", f"F{i}", "0.25A", "Fuse:Fuse_0603_1608Metric",
                {"1": "+3V3_DIG", "2": f"MIC{i}_3V3"}, "PPTC 0603")

    C(sch, "C_IO1", ("+3V3_DIG", "GND"), "100n")
    C(sch, "C_IO2", ("+3V3_DIG", "GND"), "100n")
    C(sch, "C_IO3", ("+3V3_DIG", "GND"), "1u", mpn="CL10A105KA8NNNC")


def _drop_self_shorts(sch: Sch):
    sch.parts = [p for p in sch.parts if not (
        p["lib_id"] == "Device:R" and len(set(p["nets"].values())) == 1
    )]


def build_sat(sch: Sch):
    sch.add("het68:RJ45_LVDS", "J1", "RJ45",
            "het68:RJ45_RJHSE5380_het68",
            {
                "1": "SCK_PJ", "2": "SCK_NJ", "3": "WS_PJ", "6": "WS_NJ",
                "4": "SD_PJ", "5": "SD_NJ", "7": "3V3_F", "8": "LED", "SH": None,
            }, "RJHSE-5380")
    sch.add("het68:CMC", "FL1", "CMC",
            "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
            {"1": "SCK_PJ", "4": "SCK_P", "2": "SCK_NJ", "3": "SCK_N"}, "ACM2012")
    sch.add("het68:CMC", "FL2", "CMC",
            "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
            {"1": "WS_PJ", "4": "WS_P", "2": "WS_NJ", "3": "WS_N"}, "ACM2012")
    tvs(sch, "D1", ("SCK_P", "SCK_N"))
    tvs(sch, "D2", ("WS_P", "WS_N"))
    tvs(sch, "D3", ("SD_P", "SD_N"))
    sch.add("Device:Polyfuse", "F1", "0.5A", "Fuse:Fuse_0603_1608Metric",
            {"1": "3V3_F", "2": "+3V3"}, "PPTC 0603")
    sch.add("het68:SN65LVDS2", "U2", "SN65LVDS2", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+3V3", "2": "SCK_P", "3": "SCK_N", "4": "GND", "5": "SCK_3V3"}, "SN65LVDS2DBVR")
    sch.add("het68:SN65LVDS2", "U3", "SN65LVDS2", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+3V3", "2": "WS_P", "3": "WS_N", "4": "GND", "5": "WS_3V3"}, "SN65LVDS2DBVR")
    sch.add("het68:SN65LVDS1", "U4", "SN65LVDS1", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "SD_3V3", "2": "GND", "5": "+3V3", "3": "SD_P", "4": "SD_N"}, "SN65LVDS1DBVR")
    sch.add("het68:TXS0104E", "U5", "TXS0104E", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
            {
                "1": "+1V8", "2": "SCK", "3": "WS", "4": "SD", "5": None, "6": None,
                "7": "GND", "8": "+3V3", "9": None, "10": "SD_3V3", "11": "WS_3V3",
                "12": "SCK_3V3", "13": None, "14": "+3V3",
            }, "TXS0104EDR")
    sch.add("het68:AP2112K", "U1", "AP2112K-1.8", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+3V3", "2": "GND", "3": "+3V3", "4": None, "5": "+1V8"}, "AP2112K-1.8TRG1")
    sch.add("het68:T5848", "MK1", "T5848", "het68:T5848",
            {"1": "WS", "2": "GND", "3": "GND", "4": None, "5": None,
             "6": "SCK", "7": "+1V8", "8": "SD"}, "MMICT5848-00-012")
    # 8× SK6812 daisy-chain, pixel 0 = north. Last DOUT is NC (no return to Core).
    led_in = "LED"
    for i in range(8):
        dout = f"LED{i + 2}" if i < 7 else None
        sch.add("LED:WS2812B", f"D{4 + i}", "SK6812",
                "LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm",
                {"1": "+3V3", "2": dout, "3": "GND", "4": led_in},
                "SK6812 (5050, 3.3 V)")
        C(sch, f"C_L{i + 1}", ("+3V3", "GND"), "100n")
        led_in = dout
    C(sch, "C1", ("+3V3", "GND"), "1u", mpn="CL10A105KA8NNNC")
    C(sch, "C2", ("+1V8", "GND"), "1u", mpn="CL10A105KA8NNNC")
    C(sch, "C3", ("+1V8", "GND"), "100n")
    C(sch, "C4", ("+3V3", "GND"), "100n")
    C(sch, "C5", ("+3V3", "GND"), "100n")
    R(sch, "R1", ("SD", "GND"), "100k", mpn="RC0603FR-07100KL")
    sch.add("het68:CMC", "FL3", "CMC",
            "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
            {"1": "SD_PJ", "4": "SD_P", "2": "SD_NJ", "3": "SD_N"}, "ACM2012")


def build_pwr(sch: Sch, sku: str):
    """sku in NN, VN, VVN. Common CT secondary front-end; no mains on copper."""
    tvs_mpn = "5KP36A" if sku == "NN" else "15KP36A"
    tvs_fp = "Diode_THT:D_DO-201_P15.24mm_Horizontal"
    sch.add("het68:Conn_1x02", "J1", "CT_SEC",
            "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "AC1", "2": "AC2"}, "sekundar CT, NE sit")
    R(sch, "R4", ("AC1", "AC2"), "100",
      "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", "100R THT burden")
    sch.add("het68:GDT", "GDT1", "GDT", "Fuse:Fuse_1812_4532Metric",
            {"1": "AC1", "2": "AC2"}, "GDT secondary")
    if sku == "VN":
        sch.add("het68:GDT", "GDT2", "GDT", "Fuse:Fuse_1812_4532Metric",
                {"1": "AC1", "2": "AC2"}, "GDT secondary extra")
    sch.add("Device:L", "L1", "470uH", "Inductor_THT:L_Radial_D10.0mm_P5.00mm_Fastron_07P",
            {"1": "AC1", "2": "AC1L"}, "470uH radial")
    C(sch, "C4", ("AC1L", "AC2"), "1u/100V", "Capacitor_SMD:C_1206_3216Metric", "1uF 100V X7R LC")
    sch.add("Device:Polyfuse", "F1", "0.5A", "Fuse:Fuse_1812_4532Metric",
            {"1": "AC1L", "2": "AC1F"}, "polyfuse 1812 0.5 A")
    sch.add("Device:D", "D1", "SS14", "Diode_SMD:D_SMA", {"1": "DC", "2": "AC1F"}, "SS14")
    sch.add("Device:D", "D2", "SS14", "Diode_SMD:D_SMA", {"1": "AC1F", "2": "GND"}, "SS14")
    sch.add("Device:D", "D3", "SS14", "Diode_SMD:D_SMA", {"1": "DC", "2": "AC2"}, "SS14")
    sch.add("Device:D", "D4", "SS14", "Diode_SMD:D_SMA", {"1": "AC2", "2": "GND"}, "SS14")
    sch.add("Device:C_Polarized", "C1", "470u/50V",
            "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", {"1": "DC", "2": "GND"}, "electrolytic 470u 50V")
    sch.add("Triac_Thyristor:X0202MN", "Q1", "X0202MN", "Package_TO_SOT_SMD:SOT-223",
            {"1": "GND", "2": "DC", "3": "SCR_G", "4": "DC"}, "X0202MN")
    sch.add("Device:D", "D5", "BZX84-C24", "Diode_SMD:D_SOD-323", {"1": "SCR_G", "2": "GND"}, "BZX84-C24")
    R(sch, "R5", ("DC", "SCR_G"), "1k", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-071KL")
    sch.add("Device:D", "DTVS", tvs_mpn, tvs_fp, {"1": "DC", "2": "GND"}, tvs_mpn)
    sch.add("Device:D", "D6", "SS34", "Diode_SMD:D_SMC", {"1": "VHARV", "2": "DC"}, "SS34")

    if sku in ("NN", "VN"):
        R(sch, "RPREC", ("AC1", "PREC_D"), "10", "Resistor_SMD:R_1206_3216Metric", "10R 0.1pct burden")
        sch.add("het68:NMOS", "Q2", "AO3400A", "Package_TO_SOT_SMD:SOT-23",
                {"1": "BURDEN_EN", "2": "AC2", "3": "PREC_D"}, "AO3400A")
        R(sch, "R_BG", ("BURDEN_EN", "GND"), "100k", mpn="RC0603FR-07100KL")
        sch.add("het68:PMOS", "Q3", "AO3401A", "Package_TO_SOT_SMD:SOT-23",
                {"1": "CHG_G", "2": "DC", "3": "VHARV"}, "AO3401A")
        R(sch, "R_PGATE", ("DC", "CHG_G"), "100k", mpn="RC0603FR-07100KL")
        sch.add("het68:NMOS", "Q4", "AO3400A", "Package_TO_SOT_SMD:SOT-23",
                {"1": "BURDEN_EN", "2": "GND", "3": "CHG_G"}, "AO3400A")
        R(sch, "R_IS", ("DC", "ADC_I"), "10k", mpn="RC0603FR-0710KL")
        R(sch, "R_IG", ("ADC_I", "GND"), "10k", mpn="RC0603FR-0710KL")
        # ADC_ROGO unused: tie to GND so ERC/pin has a net
        R(sch, "R_ROGO_NC", ("ADC_ROGO", "GND"), "100k", mpn="RC0603FR-07100KL")
    else:
        sch.add("het68:Conn_1x02", "J_ROGO", "ROGOWSKI",
                "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                {"1": "ROGO_P", "2": "ROGO_N"}, "Rogowski secondary, NE sit")
        R(sch, "R_RN", ("ROGO_N", "GND"), "0", mpn="RC0603FR-070RL")
        R(sch, "R_INT", ("ROGO_P", "INT_IN"), "10k", mpn="RC0603FR-0710KL")
        C(sch, "C_INT", ("INT_IN", "ADC_ROGO"), "100n")
        sch.add("het68:MCP6001", "U_INT", "MCP6001", "Package_TO_SOT_SMD:SOT-23-5",
                {"1": "ADC_ROGO", "2": "GND", "3": "GND", "4": "INT_IN", "5": "+3V3_RF"},
                "MCP6001T-OT")
        C(sch, "C_OA", ("+3V3_RF", "GND"), "100n")
        R(sch, "R_IS", ("DC", "ADC_I"), "10k", mpn="RC0603FR-0710KL")
        R(sch, "R_IG", ("ADC_I", "GND"), "10k", mpn="RC0603FR-0710KL")
        R(sch, "R_BEN_NC", ("BURDEN_EN", "GND"), "100k", mpn="RC0603FR-07100KL")

    usb_c(sch, "J2", "VBUS")
    R(sch, "R1", ("CC1", "GND"), "5.1k", mpn="RC0603FR-075K1L")
    R(sch, "R2", ("CC2", "GND"), "5.1k", mpn="RC0603FR-075K1L")
    sch.add("Device:D", "D7", "SS34", "Diode_SMD:D_SMC", {"1": "+5V_ALWAYS", "2": "VBUS"}, "SS34")
    C(sch, "C3", ("VBUS", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")

    sch.add("het68:Conn_1x02", "J_SOL", "SOLAR",
            "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "SOL_P", "2": "GND"}, "panel Voc 6-18 V")
    sch.add("het68:CN3791", "U_MPPT", "CN3791", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            {"1": "GND", "2": "SOL_P", "3": "SOL_P", "4": "GND",
             "5": "MPPT_C", "6": "BAT", "7": "BAT", "8": "SOL_P"}, "CN3791")
    C(sch, "C_MP", ("SOL_P", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")
    C(sch, "C_MC", ("MPPT_C", "GND"), "100n")
    sch.add("Device:D", "D_HV", "SS34", "Diode_SMD:D_SMC", {"1": "BAT", "2": "VHARV"}, "SS34")

    if "Device:Battery" in sch.symbols:
        sch.add("Device:Battery", "BT1", "LiFePO4_1S",
                "Battery:BatteryHolder_Keystone_1042_1x18650",
                {"1": "BAT", "2": "GND"}, "LiFePO4 / LTO 1S")
    else:
        sch.add("het68:Conn_1x02", "BT1", "BAT",
                "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                {"1": "BAT", "2": "GND"}, "LiFePO4 / LTO 1S")

    sch.add("het68:FP6291", "U_BST", "FP6291", "Package_TO_SOT_SMD:SOT-23-6",
            {"1": "BST_SW", "2": "GND", "3": "BST_FB", "4": "BAT", "5": "BAT", "6": "BAT"},
            "FP6291")
    sch.add("Device:L", "L_BST", "10uH", "Inductor_SMD:L_0805_2012Metric",
            {"1": "BST_SW", "2": "+5V_ALWAYS"}, "10uH boost")
    R(sch, "R_FB1", ("+5V_ALWAYS", "BST_FB"), "100k", mpn="RC0603FR-07100KL")
    R(sch, "R_FB2", ("BST_FB", "GND"), "20k", mpn="RC0603FR-0720KL")
    C(sch, "C_5V", ("+5V_ALWAYS", "GND"), "10u", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KOQNNNE")
    R(sch, "R_PG", ("+5V_ALWAYS", "PG_5V"), "10k", mpn="RC0603FR-0710KL")
    R(sch, "R_PG2", ("PG_5V", "GND"), "10k", mpn="RC0603FR-0710KL")

    sch.add("het68:AP2112K", "U_RF", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
            {"1": "+5V_ALWAYS", "2": "GND", "3": "EN_RF", "4": None, "5": "+3V3_RF"},
            "AP2112K-3.3TRG1")
    R(sch, "R_RFEN", ("EN_RF", "+5V_ALWAYS"), "10k", mpn="RC0603FR-0710KL")
    C(sch, "C_RF", ("+3V3_RF", "GND"), "1u", mpn="CL10A105KA8NNNC")

    sch.add("Power_Management:INA3221", "U_INA", "INA3221",
            "Package_DFN_QFN:Texas_RGV0016A_VQFN-16-1EP_4x4mm_P0.65mm_EP2.1x2.1mm",
            {
                "1": "GND", "2": "GND", "3": "GND", "4": "+3V3_RF", "5": "GND",
                "6": "I2C0_SCL", "7": "I2C0_SDA",
                "8": "I2C0_ALERT", "9": None, "10": None,
                "11": "+5V_ALWAYS", "12": "5V_IN",
                "13": None, "14": "VHARV", "15": "DC", "16": "+3V3_RF", "17": "GND",
            }, "INA3221AIRGVR")
    R(sch, "R_SH5", ("5V_IN", "+5V_ALWAYS"), "0.1", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-070R1L")
    C(sch, "C_INA", ("+3V3_RF", "GND"), "100n")
    R(sch, "R_HS", ("VHARV", "ADC_HARVEST"), "10k", mpn="RC0603FR-0710KL")
    R(sch, "R_HG", ("ADC_HARVEST", "GND"), "10k", mpn="RC0603FR-0710KL")

    sch.add("het68:Conn_1x02", "J_RTD", "PT1000",
            "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "ADC_PT1000", "2": "PT1000_RTN"}, "PT1000 on conductor")
    R(sch, "R_RTN", ("PT1000_RTN", "GND"), "0", mpn="RC0603FR-070RL")

    pwr_nets = {str(k): v for k, v in PWR_MAP.items()}
    sch.add("het68:Conn_2x10", "J_CORE", "J_CORE",
            "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
            pwr_nets, "interconnect 2x10")
    R(sch, "R_SH", ("SHIELD", "GND"), "0", mpn="RC0603FR-070RL")
    R(sch, "R_SDA", ("I2C0_SDA", "+3V3_RF"), "4.7k", mpn="RC0603FR-074K7L")
    R(sch, "R_SCL", ("I2C0_SCL", "+3V3_RF"), "4.7k", mpn="RC0603FR-074K7L")

    sch.add("Device:LED", "D8", "LED", "LED_SMD:LED_0603_1608Metric",
            {"1": "LED_A", "2": "GND"}, "LED 0603")
    R(sch, "R3", ("+5V_ALWAYS", "LED_A"), "2.2k", mpn="RC0603FR-072K2L")
    sch.add("het68:Conn_1x02", "J3", "VOUT",
            "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "+5V_ALWAYS", "2": "GND"}, "5V lab")


def place_remaining(board: Board, sch: Sch, placed: set, x0=8.0, y0=20.0, dx=5.0, dy=6.0):
    x, y = x0, y0
    for p in sch.parts:
        if p["ref"] in placed:
            continue
        if x > board.w - 8:
            x = x0
            y += dy
        if y > board.h - 6:
            y = y0 + 3
            x0 += 2
            x = x0
        board.place(p, x, y, 0)
        placed.add(p["ref"])
        x += dx


def holes(board, pts):
    hole_fp = "MountingHole:MountingHole_3.2mm_M3"
    for i, (x, y) in enumerate(pts, start=1):
        board.place({"ref": f"H{i}", "value": "M3", "footprint": hole_fp, "nets": {}, "mpn": ""}, x, y, 0)


def place_core(board: Board, sch: Sch):
    by = {p["ref"]: p for p in sch.parts}
    placed = set()

    def P(ref, x, y, rot=0):
        board.place(by[ref], x, y, rot)
        placed.add(ref)

    xs = (14, 40, 66, 92, 118, 144)
    for i, x in enumerate(xs, start=1):
        P(f"J{i}", x, 10, 0)
        P(f"FL{i}A", x - 4, 24, 0)
        P(f"FL{i}B", x + 4, 24, 0)
        P(f"DT{i}A", x - 4, 30, 0)
        P(f"DT{i}B", x, 30, 0)
        P(f"DT{i}C", x + 4, 30, 0)
        P(f"F{i}", x, 36, 0)
    P("U1", 80, 58, 0)
    P("U2", 96, 58, 0)
    P("U3", 64, 58, 0)
    P("Y1", 80, 48, 0)
    P("L_VREG", 88, 48, 0)
    P("U4", 50, 70, 0)
    P("U5", 58, 70, 0)
    P("J_USB", 16, 70, 0)
    P("J_MESH", 80, 92, 0)
    P("J_STAMP", 102, 92, 0)
    P("J_PWR", 16, 92, 0)
    P("J_SWD", 50, 92, 0)
    P("U10", 40, 48, 0)
    P("U11", 120, 48, 0)
    P("U12", 140, 48, 0)
    P("U13", 40, 80, 0)
    P("U14", 58, 80, 0)
    P("U6", 120, 80, 0)
    P("U7", 130, 70, 0)
    P("U8", 138, 70, 0)
    P("U9", 80, 70, 0)
    for ref, x in (("J11", 118), ("J12", 126), ("J13", 134), ("J14", 142)):
        P(ref, x, 92, 0)
    holes(board, ((4, 4), (4, 96), (156, 4), (156, 96)))
    place_remaining(board, sch, placed, 8, 40, 4.5, 5)
    board.text("het68 CORE rev A  6L Faraday", 80, 98, size=1.0)
    board.text("J_MESH Heltec V3 868  pin1 GND", 80, 2, size=0.7)
    board.text("USB Heltec odpojit po flash", 50, 98, size=0.6)
    board.text("LVDS 1/2 SCK  3/6 WS  4/5 SD  7 3V3  8 LED", 80, 42, size=0.55)


def place_sat(board: Board, sch: Sch):
    by = {p["ref"]: p for p in sch.parts}
    placed = set()

    def P(ref, x, y, rot=0):
        board.place(by[ref], x, y, rot)
        placed.add(ref)

    cx, cy, led_r = 25.0, 58.0, 12.0
    P("J1", 14, 16, 0)
    P("F1", 34, 18, 90)
    P("FL1", 8, 27, 0)
    P("FL2", 18, 27, 0)
    P("FL3", 28, 27, 0)
    P("D1", 8, 32, 0)
    P("D2", 18, 32, 0)
    P("D3", 28, 32, 0)
    P("U2", 8, 38, 0)
    P("U3", 18, 38, 0)
    P("U4", 8, 44, 0)
    P("U5", 36, 30, 0)
    P("U1", 40, 40, 0)
    P("C5", 44, 30, 90)
    P("C1", 44, 36, 90)
    P("C4", 44, 42, 90)
    P("MK1", cx, cy, 0)
    P("C2", 23.4, 61.4, 0)
    P("C3", 26.6, 61.4, 0)
    P("R1", 29.6, 61.4, 90)
    for i in range(8):
        phi = math.radians(i * 45.0)
        x = cx + led_r * math.sin(phi)
        y = cy - led_r * math.cos(phi)
        P(f"D{4 + i}", x, y, i * 45)
        cap_r = led_r + 5.2
        P(f"C_L{i + 1}", cx + cap_r * math.sin(phi), cy - cap_r * math.cos(phi), i * 45)
    holes(board, ((4, 4), (46, 4), (4, 76), (46, 76)))
    place_remaining(board, sch, placed, 8, 22, 4, 5)
    board.text("het68 SAT v4 6L LVDS", 25, 4, size=0.8)
    board.text("1/2 SCK  3/6 WS  4/5 SD  8x SK6812", 25, 8, size=0.45)
    board.text("D4=N  daisy CW  DOUT NC", 25, 78, size=0.45)


def sat_prewire(api):
    """Escape RJ45 pin 3 (WS_P) south between the 1.3 mm rear-row lands.

    T5848 north-row VDD/SD would otherwise stay boxed in after WS routes
    north from pad 1. SD runs north at pad 8 X to the U5 LVDS-side stub;
    +1V8 stubs north then west to C2 so WS can still reach U5 on F.Cu.
    """
    draw, set_tip = api["draw_poly"], api["set_tip"]
    for net in ("WS_PJ", "SD_PJ", "SD_NJ", "SCK_PJ", "SCK_NJ"):
        pads = list(api["by_net"].get(net, []))
        if len(pads) < 2:
            continue
        jack = min(pads, key=lambda p: p["y"])
        fl = max(pads, key=lambda p: p["y"])
        x = jack["x"]
        draw([(jack["x"], jack["y"]), (x, fl["y"]), (fl["x"], fl["y"])], 0, net)
        set_tip(jack, x, fl["y"])
        set_tip(fl, fl["x"], fl["y"])

    def pad_of(ref, num):
        for group in api["by_net"].values():
            for p in group:
                if p["ref"] == ref and str(p["num"]) == str(num):
                    return p
        return None

    mk_sd = pad_of("MK1", "8")
    mk_vdd = pad_of("MK1", "7")
    c_vdd = pad_of("C2", "1")
    mk_ws = pad_of("MK1", "1")
    if mk_sd:
        x_esc, y_esc = mk_sd["x"] + 1.6, mk_sd["y"] - 1.8
        draw([(mk_sd["x"], mk_sd["y"]), (x_esc, mk_sd["y"]), (x_esc, y_esc)], 0, "SD", width=0.25)
        set_tip(mk_sd, x_esc, y_esc)
    if mk_ws:
        x_esc, y_esc = mk_ws["x"] + 0.2, mk_ws["y"] - 1.8
        draw([(mk_ws["x"], mk_ws["y"]), (x_esc, y_esc)], 0, "WS", width=0.25)
        set_tip(mk_ws, x_esc, y_esc)
    for i in range(7):
        a = pad_of(f"D{4 + i}", "2")
        b = pad_of(f"D{5 + i}", "4")
        if not (a and b):
            continue
        net = f"LED{i + 2}"
        draw([(a["x"], a["y"]), (b["x"], b["y"])], 0, net, width=0.25)
        set_tip(a, b["x"], b["y"])
        set_tip(b, b["x"], b["y"])
    if mk_vdd and c_vdd:
        y_bus = mk_vdd["y"] - 1.15
        draw(
            [
                (mk_vdd["x"], mk_vdd["y"]),
                (mk_vdd["x"], y_bus),
                (c_vdd["x"], y_bus),
                (c_vdd["x"], c_vdd["y"]),
            ],
            0, "+1V8", width=0.25,
        )
        set_tip(mk_vdd, mk_vdd["x"], y_bus)
        set_tip(c_vdd, c_vdd["x"], c_vdd["y"])


def place_pwr(board: Board, sch: Sch, sku: str):
    by = {p["ref"]: p for p in sch.parts}
    placed = set()

    def P(ref, x, y, rot=0):
        if ref in by:
            board.place(by[ref], x, y, rot)
            placed.add(ref)

    P("J2", 16, 40, 0)
    P("J1", 128, 50, 0)
    P("R4", 114, 56, 0)
    P("GDT1", 114, 44, 0)
    P("GDT2", 114, 38, 0)
    P("L1", 100, 50, 0)
    P("C4", 90, 56, 0)
    P("F1", 90, 48, 0)
    P("D1", 78, 44, 0)
    P("D2", 78, 38, 180)
    P("D3", 86, 44, 0)
    P("D4", 86, 38, 180)
    P("C1", 64, 22, 0)
    P("Q1", 78, 20, 0)
    P("DTVS", 70, 20, 0)
    P("U_MPPT", 40, 22, 0)
    P("BT1", 40, 50, 0)
    P("U_BST", 54, 40, 0)
    P("U_RF", 54, 56, 0)
    P("U_INA", 28, 22, 0)
    P("J_CORE", 16, 70, 0)
    P("J_SOL", 40, 70, 0)
    P("J_RTD", 54, 70, 0)
    P("J3", 128, 22, 0)
    P("J_ROGO", 128, 70, 0)
    P("U_INT", 100, 70, 0)
    holes(board, ((4, 4), (4, 76), (136, 4), (136, 76)))
    place_remaining(board, sch, placed, 70, 8, 4.2, 5.5)
    board.text(f"het68 PWR {sku}  JEN SEKUNDAR", 70, 4, size=0.9)
    board.text("NE 230 V / NE 22 kV / NE 110 kV", 70, 77, size=0.7)


def finish_v4(board: Board, sch: Sch, out: Path, power_nets, six=False, skip_route=False):
    _drop_self_shorts(sch)
    board.outline()
    board.assign_nets()
    if six:
        board.via_d, board.via_drill = 0.45, 0.2
        ds = board.b.GetDesignSettings()
        ds.m_MinClearance = pcbnew.FromMM(0.1)
        ds.m_TrackMinWidth = pcbnew.FromMM(0.1)
        ds.m_ViasMinSize = pcbnew.FromMM(0.4)
        ds.m_ViasMinDrill = pcbnew.FromMM(0.2)
        ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
        try:
            nc = ds.m_NetSettings.m_DefaultNetClass
            nc.SetClearance(pcbnew.FromMM(0.1))
            nc.SetTrackWidth(pcbnew.FromMM(0.15))
            nc.SetViaDiameter(pcbnew.FromMM(0.45))
            nc.SetViaDrill(pcbnew.FromMM(0.2))
        except Exception:
            pass
        set_stackup(board)
        splits = getattr(board, "l4_splits", [
            ("+3V3_DIG", 1.2, 62),
            ("+5V_ALWAYS", 64, 110),
            ("+1V8_AUDIO", 112, 158.8),
        ])
        faraday_planes(board, splits, l3_gnd=getattr(board, "l3_gnd", False))
        island = getattr(board, "l4_island", None)
        if island:
            net, x0, y0, x1, y1 = island
            board.add_zone(
                net, pcbnew.In3_Cu,
                pts=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                priority=2, clearance=0.3, islands="always",
            )
    else:
        design_rules(board)
        board.add_zone("GND", pcbnew.B_Cu, islands="area")
    missing = []
    if not skip_route:
        if six and not getattr(board, "outer_route", False):
            board.plane_nets = {n: None for n in power_nets or []}
            missing = route_stripline(board)
        else:
            if six:
                board.plane_nets = {n: None for n in power_nets or []}
            missing = route_board(board)
    board.fill()
    try:
        board.b.BuildConnectivity()
        board.b.GetConnectivity().RecalculateRatsnest()
    except Exception:
        pass
    out.mkdir(parents=True, exist_ok=True)
    pcb_path = out / f"{board.name}.kicad_pcb"
    board.save(pcb_path)
    (out / f"{board.name}.kicad_sch").write_text(sch.emit())
    via_d = getattr(board, "via_d", 0.8)
    via_drill = getattr(board, "via_drill", 0.5)
    (out / f"{board.name}.kicad_pro").write_text(
        """{
  "board": {"design_settings": {"rules": {"min_clearance": %s, "min_track_width": %s, "min_via_diameter": %s, "min_via_drill": %s, "min_through_hole_diameter": %s, "min_hole_clearance": 0.2, "min_copper_edge_clearance": 0.3}, "rule_severities": {"lib_footprint_mismatch": "ignore"}}},
  "meta": {"filename": "%s.kicad_pro", "version": 3},
  "sheets": [["%s.kicad_sch", ""]],
  "text_variables": {}
}
"""
        % (0.1 if six else 0.2, 0.1 if six else 0.2, via_d, via_drill, via_drill, board.name, board.name)
    )
    (out / "fp-lib-table").write_text(
        """(fp_lib_table
  (version 7)
  (lib (name "het68")(type "KiCad")(uri "${KIPRJMOD}/../lib/het68.pretty")(options "")(descr "het68"))
)
"""
    )
    bom(sch, out / "bom.csv")
    return missing


def kicad_cli(*args):
    cmd = [KICAD_CLI, *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def export_fab(pcb: Path, fab: Path, layers):
    fab.mkdir(parents=True, exist_ok=True)
    r = kicad_cli("pcb", "export", "gerbers", "--output", str(fab), "--layers", ",".join(layers),
                  str(pcb))
    if r.returncode:
        print("gerber", pcb.name, (r.stderr or r.stdout)[-1500:], flush=True)
    r = kicad_cli("pcb", "export", "drill", "--output", str(fab) + "/", "--format", "excellon",
                  "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", str(pcb))
    if r.returncode:
        print("drill", pcb.name, (r.stderr or r.stdout)[-800:], flush=True)
    kicad_cli("pcb", "export", "pos", "--output", str(fab / (pcb.stem + "-pos.csv")),
              "--format", "csv", "--units", "mm", "--side", "front", str(pcb))
    kicad_cli("pcb", "export", "svg", "--output", str(fab / (pcb.stem + "-F.svg")),
              "--layers", "F.Cu,F.SilkS,Edge.Cuts", str(pcb))
    kicad_cli("pcb", "export", "svg", "--output", str(fab / (pcb.stem + "-B.svg")),
              "--layers", "B.Cu,B.SilkS,Edge.Cuts", "--mirror", str(pcb))


def sch_erc(sch_path: Path) -> str:
    out = sch_path.with_suffix(".erc.json")
    r = kicad_cli("sch", "erc", "--format", "json", "--output", str(out), str(sch_path))
    return (r.stdout or "") + (r.stderr or "")


def pcb_drc(pcb_path: Path) -> str:
    out = pcb_path.with_suffix(".drc.json")
    r = kicad_cli("pcb", "drc", "--format", "json", "--output", str(out),
                  "--severity-error", "--exit-code-violations", str(pcb_path))
    return (r.stdout or "") + (r.stderr or "")


def write_vyroba(path: Path, text: str):
    path.write_text(text)


def main():
    app = wx.App(False)
    PRETTY.mkdir(parents=True, exist_ok=True)
    write_t5848_fp(PRETTY / "T5848.kicad_mod")
    write_rj45_fp(PRETTY / "RJ45_RJHSE5380_het68.kicad_mod")

    core_rails = ["GND", "+5V_ALWAYS", "+3V3_DIG", "+3V3_RF", "+1V8_AUDIO", "VBUS", "DVDD"]
    core = SchV4("het68-core", "het68 Core 6L RP2350B + J_MESH Heltec V3", core_rails)
    v4_libs(core, core_rails)
    build_core(core)
    _drop_self_shorts(core)
    cb = Board("het68-core", 160, 100, 6)
    cb.via_d, cb.via_drill = 0.45, 0.2
    cb.route_skip_refs = {"U1", "U9", "U7", "U8", "U6"}
    place_core(cb, core)
    cout = ROOT / "het68-core"
    cmiss = finish_v4(
        cb, core, cout,
        {"GND", "+5V_ALWAYS", "+3V3_DIG", "+3V3_RF", "+1V8_AUDIO", "DVDD", "VBUS"},
        six=True, skip_route=True,
    )
    print("CORE unrouted", len(cmiss), cmiss[:20], flush=True)

    sat = SchV4("het68-sat", "het68 satelit 6L LVDS + T5848 + 8x SK6812", ["GND", "+3V3", "+1V8"])
    v4_libs(sat, ["GND", "+3V3", "+1V8"])
    build_sat(sat)
    _drop_self_shorts(sat)
    sb = Board("het68-sat", 50, 80, 6)
    sb.via_d, sb.via_drill = 0.45, 0.2
    sb.outer_route = True
    sb.l3_gnd = True
    sb.l4_splits = [("+3V3", 1.2, 48.8)]
    sb.l4_island = ("+1V8", 22.2, 55.0, 27.8, 63.6)
    sb.prewire = sat_prewire
    place_sat(sb, sat)
    sout = ROOT / "het68-sat"
    smiss = finish_v4(sb, sat, sout, {"GND", "+3V3", "+1V8"}, six=True, skip_route=True)
    print("SAT unrouted", len(smiss), smiss, flush=True)

    sheets = [("core", core, 1), ("sat", sat, 6)]
    for sku, folder, title in (
        ("NN", "het68-pwr-nn", "het68 silova NN multiplex CT"),
        ("VN", "het68-pwr-vn", "het68 silova VN 15KP"),
        ("VVN", "het68-pwr-vvn", "het68 silova VVN Rogowski"),
    ):
        rails = ["GND", "+5V_ALWAYS", "+3V3_RF", "VBUS", "BAT", "DC"]
        psch = SchV4(folder, title, rails)
        v4_libs(psch, rails)
        build_pwr(psch, sku)
        _drop_self_shorts(psch)
        pb = Board(folder, 140, 80, 2)
        pb.via_d, pb.via_drill = 0.8, 0.5
        place_pwr(pb, psch, sku)
        pout = ROOT / folder
        pmiss = finish_v4(
            pb, psch, pout,
            {"GND", "+5V_ALWAYS", "+3V3_RF", "VBUS", "BAT", "DC", "VHARV", "AC1", "AC2"},
            skip_route=True,
        )
        print(f"PWR {sku} unrouted", len(pmiss), pmiss[:20], flush=True)
        sheets.append((folder, psch, 1))
        (pout / "fab").mkdir(exist_ok=True)
        write_vyroba(
            pout / "fab" / "VYROBA.txt",
            f"het68 silova {sku} v4.0.0\n140 x 80 mm, 2 vrstvy, mer 70 um. NE printed.cz PROTOTYP.\n"
            "Jen sekundar CT/Rogowski. NE 230 V / 22 kV / 110 kV na med.\n"
            "HASL nebo ENIG dle TPV. Stopa >= 0.25 mm, prokovy 0.8/0.5 mm.\n",
        )

    with (ROOT / "BOM_v4.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Board", "Qty", "Value", "MPN", "Refs"])
        for board_name, sch, mult in sheets:
            groups = {}
            for p in sch.parts:
                key = (p["value"], p["mpn"])
                groups.setdefault(key, []).append(p["ref"])
            for (value, mpn), refs in groups.items():
                w.writerow([board_name, len(refs) * mult, value, mpn, " ".join(refs)])

    # ERC / DRC / gerbers
    projects = [
        (ROOT / "het68-core" / "het68-core.kicad_sch", ROOT / "het68-core" / "het68-core.kicad_pcb",
         ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "Edge.Cuts"]),
        (ROOT / "het68-sat" / "het68-sat.kicad_sch", ROOT / "het68-sat" / "het68-sat.kicad_pcb",
         ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "Edge.Cuts"]),
        (ROOT / "het68-pwr-nn" / "het68-pwr-nn.kicad_sch", ROOT / "het68-pwr-nn" / "het68-pwr-nn.kicad_pcb",
         ["F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "Edge.Cuts"]),
        (ROOT / "het68-pwr-vn" / "het68-pwr-vn.kicad_sch", ROOT / "het68-pwr-vn" / "het68-pwr-vn.kicad_pcb",
         ["F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "Edge.Cuts"]),
        (ROOT / "het68-pwr-vvn" / "het68-pwr-vvn.kicad_sch", ROOT / "het68-pwr-vvn" / "het68-pwr-vvn.kicad_pcb",
         ["F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "Edge.Cuts"]),
    ]
    for schp, pcbp, layers in projects:
        print("ERC", schp.name, flush=True)
        print(sch_erc(schp)[-2000:], flush=True)
        print("DRC", pcbp.name, flush=True)
        print(pcb_drc(pcbp)[-2000:], flush=True)
        export_fab(pcbp, pcbp.parent / "fab", layers)

    write_vyroba(ROOT / "het68-core" / "fab" / "VYROBA.txt",
                 "het68 Core v4.0.0\n160 x 100 mm, 6 vrstev Faraday, ENIG (QFN-80 + LGA).\n"
                 "NE printed.cz PROTOTYP. JLC / standardni TPV.\n"
                 "J_MESH 1x8 Heltec V3 868. Stamp DNP. USB Heltec odpojit po flash.\n")
    write_vyroba(ROOT / "het68-sat" / "fab" / "VYROBA.txt",
                 "het68 satelit v4.0.0 6L Faraday LVDS\n"
                 "50 x 80 mm, 6 vrstev, ENIG. >= 0603. Ne BGA. NE printed.cz PROTOTYP.\n"
                 "T5848 uprostred. 8x SK6812 kruh (D4=N, daisy CW). SN65LVDS1 = SD sat->Core.\n"
                 "LVDS RX SCK/WS (SN65LVDS2), CMC + TVS + PPTC 0.5 A. RGB 3.3 V.\n")
    print("done")


if __name__ == "__main__":
    main()
