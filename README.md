# het68_pcb

Zadání a KiCad návrh PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v4.4.0](https://github.com/fedurca/het68_pcb/releases/tag/v4.4.0)** — viz [CHANGELOG.md](CHANGELOG.md). Kusovník sady: [kicad/BOM_KIT.csv](kicad/BOM_KIT.csv). Po deskách: [kicad/BOM_v4.csv](kicad/BOM_v4.csv).

Firmware a geometrie pole: [fedurca/het68](https://github.com/fedurca/het68). Zadání: [docs/ZADANI_PCB.md](docs/ZADANI_PCB.md). Projekty v KiCadu: [kicad/README.md](kicad/README.md).

## Co to je

v4 je sada **Core 6L + vyměnitelná silová deska + šest satelitů**. Na měď nepřijde 230 V, 22 kV ani 110 kV.

**Core** (`kicad/het68-core`) nese nativní RP2350B, flash, PSRAM, USB-C, šest RJ45 s LVDS, piezo, env senzor, ADXL355, stavovou SK6812, tlačítka RESET / BOOT / USER a `J_MESH` na Heltec WiFi LoRa 32 V3 (868 MHz). MeshCore běží na Heltecu, takže uzel v síti žije, i když DSP spí. `WAKE_DSP` zapíná `+3V3_DIG`.

**Silová deska** má tři SKU se stejným interconnectem 2×10: NN (multiplex CT), VN (silnější GDT/TVS), VVN (harvest CT + Rogowski). Společný front-end je jen sekundár: GDT, TVS, LC, burden, crowbar, MPPT, článek 21700 (LiFePO4/LTO), 5 V a vždyživý `+3V3_RF`.

**Satelit** je šest destiček 6L: T5848 uprostřed, **8× SK6812** v kruhu, na kabelu LVDS. SD z mikrofonu jede párem (`SN65LVDS1` na satelitu, `SN65LVDS32` na Core, 100 Ω u přijímače). Mapa [`docs/PINOUT_SAT_v4.csv`](docs/PINOUT_SAT_v4.csv).

## Prototyp (v4.4.0)

![Core 6L](docs/img/core-3d.png)

Maska a schéma: [Core](docs/img/core-mask.svg) · [schéma](docs/img/core-sch.pdf) · [satelit](docs/img/sat-mask.svg) · [silová](docs/img/pwr-nn-mask.svg). Gerbery pro osazení: [`kicad/jlc/`](kicad/jlc/).

![Satelit 6L, 8× SK6812](docs/img/sat-3d.png)

![Silová NN](docs/img/pwr-nn-3d.png)

Vrchní měď: [Core](docs/img/core-pcb.svg) · [Satelit](docs/img/sat-lvds.svg) · [Silová NN](docs/img/pwr-nn.svg)

![Sestava](docs/img/sestava.svg)

## Vyrobitelnost

Na měď nejde 230 V / 22 kV / 110 kV. Gerbery z `kicad-cli` v `kicad/*/fab/`. TPV: JLC / standardní výroba, ENIG na 6L, ≥ 0603, ne BGA. QFN-80 0,4 mm a LGA chtějí ENIG.

| Deska | Rozměr | ERC error | DRC | Objednat? |
|---|---|---|---|---|
| Core | 160 × 100 mm, 6L Faraday, ENIG | 0 | 0 zkratů na nových spojích, 67 nepřipojených | ne, část QSPI a GPIO ještě nekončí u cíle |
| Satelit | 50 × 80 mm, 6L Faraday, ENIG | 0 | 0 zkratů, 13 nepřipojených | ne, několik LVDS sítí je otevřených |
| Silová NN/VN/VVN | 140 × 80 mm, 2L 70 µm | 0 | ~29 zkratů pad–pad z rozmístění, ~50 nepřipojených | ne |

Schémata jsou elektricky uzavřená (ERC 0 chyb). QFN-80 má únik 0,15 mm po ose pinu. Krystal je odsunutý od severní hrany, aby ta řada měla koridor. Z rovnoběžného svazku o rozteči 0,40 mm odbočí jen krajní vodiče, proto několik pinů uprostřed řady zůstává otevřených.

## VF / EMC (silné rušení)

- 6L Faraday: L2/L5 souvislá GND, L4 split napájení, stitch 1,5 mm po obvodu.
- I²S na kabelu je LVDS (T568B páry), ne jednovodič. Stínění STP na GND jen na Core.
- CMC na SCK, WS i SD na obou koncích; nízko-kapacitní TVS napříč párem; 100 Ω u přijímače (SN65LVDS2 / SN65LVDS32 nemají vnitřní zakončení).
- Ferit 600 Ω na 3V3 každého jacku a na satelitu za PPTC.
- Krystal 12 MHz s C0G 15 pF (ne X7R 100 nF). Sériové 33 Ω na I²S u MCU, 22 Ω + ESD na UART MeshCore.
- Rádio (SX1262) je na Heltecu mimo DSP; `+3V3_RF` je vždyživé a oddělené od hradlovaného `+3V3_DIG`.

## Co je ještě potřeba

1. **Firmware.** DSP = RP2350B. MeshCore na Heltecu: `Heltec_lora32_v3`, UART GPIO5/6, WAKE GPIO7.
2. **Dokončit střední piny QFN-80** (QSPI SD2/SD3, část LED, SWD, UART) a zbylé LVDS páry. Silová deska má překryté pady z rozmístění.
3. **Heltec je lab.** ~40–80 mA. Stamp nRF52 později. LTO povinná, minimální SOC repeateru 30 %.
4. **110 kV.** Žádný externí kabel ze sféry. Anténa U.FL do slotu u stampu.
5. **RGB na 3,3 V.** Firmware svítí nejvýš dvěma pixely naráz.

## Sestava

Kleště / CT jsou na jednom izolovaném vodiči. Na desku jde jen sekundár (burden, LC, crowbar). Panel a článek LiFePO4/LTO jsou u silové desky, výstup `+5V_ALWAYS` jde na Core, šest satelitů je na RJ45.
