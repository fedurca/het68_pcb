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

6L Faraday. Režim linky volí jedna vodorovná propojka na satelitu. `JP_SCK`, `JP_WS` a `JP_SD` jsou hřebínky 2×3 na spodní straně, pin 1 (čtvercový) je severovýchodní. Severní řádek je diferenciální LVDS, prostřední je jednostranných 3,3 V přes `TXS0104E`, jižní je 1,8 V přímo na T5848. `JP_T*` jen u diferenciálního režimu (100 Ω). `JP_SDN` 1–2 je záporný vývod budiče, 2–3 dává zápornou žílu na zem. `JP_OE` se nasazuje jen v režimu 1,8 V a vypne překladač. T5848 zůstává na 1,62–1,98 V. Stínění RJ45 je na satelitu na GND. DRC desky je bez zkratů. Vzdušné zůstávají `OE`, krátká mezera `SD_3V3` u `U5`, `WS_LVDS`, `WS_P`, `WS_T` a `WS_N`. ENIG, ≥ 0603.

## Výroba

Gerbery z `kicad-cli pcb export gerbers` (ne `WriteDRCReport`). Core a satelit 6L ENIG u JLC. Silová 2L 70 µm.

v4.1.0: schémata elektricky uzavřená, BoM sady, 3D náhledy. Spoje 6L jsou v4.2.0.
