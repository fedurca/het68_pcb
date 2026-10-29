# het68 — KiCad (v4.1.0)

Náhledy a kontext: [README](../README.md) repozitáře.

v4 kreslí **Core 6L**, tři silové SKU a satelit LVDS.

| Projekt | Deska | Vrstvy | Obrys |
|---|---|---|---|
| [het68-core](het68-core/het68-core.kicad_pro) | RP2350B + J_MESH Heltec V3 + 6× RJ45 LVDS | 6 Faraday | 160 × 100 mm |
| [het68-sat](het68-sat/het68-sat.kicad_pro) | satelit 6L LVDS + T5848 + 8× SK6812 | 6 Faraday, ENIG | 50 × 80 mm |
| [het68-pwr-nn](het68-pwr-nn/het68-pwr-nn.kicad_pro) | silová NN, multiplex CT | 2, 70 µm | 140 × 80 mm |
| [het68-pwr-vn](het68-pwr-vn/het68-pwr-vn.kicad_pro) | silová VN, 15KP | 2, 70 µm | 140 × 80 mm |
| [het68-pwr-vvn](het68-pwr-vvn/het68-pwr-vvn.kicad_pro) | silová VVN, Rogowski | 2, 70 µm | 140 × 80 mm |

Generátor: `kicad/tools/gen_v4.py` (Python z KiCadu). 6L stackup: `kicad/tools/route6.py`. Kusovník sady: [`BOM_KIT.csv`](BOM_KIT.csv).

## Zapojení Core

- RP2350B QFN-80, W25Q128 SOIC-8, APS6404L SOIC-8, USB-C, krystal 12 MHz + C0G 15 pF.
- `+3V3_DIG` a `+1V8_AUDIO` hradluje `WAKE_DSP` (Heltec GPIO7). `+5V_ALWAYS` / `+3V3_RF` vždyživé.
- `J_MESH` 1×8: GND, 5V, UART TX/RX (22 Ω + ESD), WAKE_DSP, DSP_AWAKE, RST NC, rezerva. Stamp DNP paralelně na pinech 1–6.
- Šest RJ45 LVDS, mapa [`docs/PINOUT_SAT_v4.csv`](../docs/PINOUT_SAT_v4.csv). CMC na SCK/WS/SD, 100 Ω u RX SD, ferit na 3V3.
- GPIO: [`docs/PINOUT.csv`](../docs/PINOUT.csv).
- Interconnect: [`docs/INTERCONNECT_v4.md`](../docs/INTERCONNECT_v4.md).
- L1 SMT+GND, L2 GND, L3 stripline, L4 souvislá `+3V3_DIG`, L5 GND, L6 pomalé+GND. Prokov 0,30/0,15 mm. Stitch po obvodu.

## Silová deska

Jen sekundár CT/Rogowski. GDT, TVS, LC, THT burden 100 Ω, crowbar ~25 V, USB-C lab, CN3791, LiFePO4, boost 5 V, LDO 3V3_RF, INA3221, PT1000. NN má MOSFET multiplex burdenu. VN 15KP. VVN Rogowski + MCP6001.

## Satelit

6L Faraday. LVDS RX SCK/WS (SN65LVDS2 + 100 Ω), LVDS TX SD (SN65LVDS1 → Core SN65LVDS32), CMC, TVS, PPTC 0,5 A, ferit 600 Ω, TXS0104E 3,3↔1,8 V, T5848 ve středu, 8× SK6812 v kruhu. ENIG, ≥ 0603.

## Výroba

Gerbery z `kicad-cli pcb export gerbers` (ne `WriteDRCReport`). Core a satelit 6L ENIG u JLC. Silová 2L 70 µm.

v4.1.0: schémata elektricky uzavřená, BoM sady, 3D náhledy. Spoje 6L jsou v4.2.0.
