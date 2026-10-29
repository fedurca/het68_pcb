# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Tento soubor drží řadu **4.x**. Starší tagy `v1.1.1` … `v3.0.0` zůstávají v gitu.

## [4.1.0] — 2026-10-29

Produktový strom je jen Core 6L + satelit 6L + tři silové SKU. Z aktuální verze pryč HAT/Pico a historický 2L satelit/power v3.

### Added

- LVDS best practice pro silné rušení: **100 Ω** u přijímačů (Core SD, satelit SCK/WS), **CMC na SD** i na Core, **ferit 600 Ω** na 3V3 každého jacku a na satelitu.
- C0G 15 pF u krystalu 12 MHz (`CL10C150JB8NNNC`). Sériové 33 Ω na I²S u MCU. UART 22 Ω s korektním MPN.
- Kusovník sady [`kicad/BOM_KIT.csv`](kicad/BOM_KIT.csv) (1 Core + 6 satelitů + 1 silová NN).
- 3D náhledy prototypu: [`docs/img/core-3d.png`](docs/img/core-3d.png), [`docs/img/sat-3d.png`](docs/img/sat-3d.png), [`docs/img/pwr-nn-3d.png`](docs/img/pwr-nn-3d.png). STEP v `kicad/*/fab/`.
- Via fence GND 1,5 mm po obvodu.

### Changed

- README, zadání a checklist popisují jen 4.x. Generátor v3 (`gen_boards.py` main) odmítá spuštění, aby nepřepsal 6L satelit.

### Removed

- Z working tree: `kicad/het68-hat`, `kicad/het68-pwr`, `docs/PINOUT_HAT_v3.csv`, náhledy HAT/Pico a 2L satelitu v3. Historie zůstává v tagu `v3.0.0`.

### Notes

- ERC 0 chyb na všech pěti schématech. Satelit courtyard DRC 0. Doroutování stop je v4.2.0.

## [4.0.0] — 2026-10-29

Nativní RP2350B na 6L Faraday Core, MeshCore na Heltec V3 (`J_MESH`) se spánkem DSP, tři vyměnitelné silové SKU, satelit LVDS 6L s 8× SK6812. Na měď nejde síť.

### Added

- **Core** `kicad/het68-core`: RP2350B, 16 MB flash, 8 MB PSRAM, USB-C, 6× RJ45 LVDS, ADXL355, DPS310+SHT40, DRV8837, `J_MESH` 1×8 na Heltec WiFi LoRa 32 V3 868 MHz, DNP stamp land, interconnect 2×10. `WAKE_DSP` hradluje `+3V3_DIG` a `+1V8_AUDIO`.
- **Silové SKU** `het68-pwr-nn` / `vn` / `vvn`. Společný sekundár: GDT, TVS, LC, burden THT, crowbar, CN3791, LiFePO4/LTO, boost 5 V, LDO `+3V3_RF`, INA3221, PT1000.
- Satelit LVDS 6L Faraday 50 × 80 mm: CMC, TVS, PPTC 0,5 A, SN65LVDS2×2 + SN65LVDS1, TXS0104E, T5848 1,8 V ve středu, 8× SK6812 v kruhu.
- Generátor `kicad/tools/gen_v4.py`, 6L helper `kicad/tools/route6.py`.

### Changed

- Compute už není Pico Plus 2 + HAT. GP0/GP1 jsou UART MeshCore.
- T568B jednovodičové I²S na UTP končí; na kabelu je LVDS.

[4.1.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.1.0
[4.0.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.0.0
