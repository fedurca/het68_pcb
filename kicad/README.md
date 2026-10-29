# het68 — KiCad (v3.0.0)

Náhledy návrhu i osazených desek jsou v [README](../README.md) repozitáře.

Tři desky podle zadání (Pimoroni Pico Plus 2 + HAT, 6× RJ45, 4× piezo, I²C). Všechny splňují printed.cz PROTOTYP.

| Projekt | Deska | Vrstvy | Obrys |
|---|---|---|---|
| [het68-hat](het68-hat/het68-hat.kicad_pro) | HAT pod Pico Plus 2 / Plus 2 W, rev F | 2 (F.Cu signál, B.Cu GND) | 140 × 140 mm |
| [het68-sat](het68-sat/het68-sat.kicad_pro) | satelit, 6× stejný | 2, ENIG | 28 × 52 mm |
| [het68-pwr](het68-pwr/het68-pwr.kicad_pro) | napájení ze sekundáru CT (burden, LC, crowbar) | 2 | 100 × 58 mm |

Schémata prošla ERC bez chyb (KiCad 10). Otevři `*.kicad_pro` v KiCadu.

Generátor (umístění i routování): `kicad/tools/gen_boards.py` (Python z KiCadu), router `kicad/tools/route2.py`.

## Zapojení

**HAT (rev F)**

- Pico Plus 2 leží naplocho na dvou zásuvkových lištách 1×20 (8,5 mm), USB-C na západní hraně. Footprint `RaspberryPi_Pico_Common_THT` včetně zakázané zóny pod anténou verze W.
- GPIO stejné jako v2.0.0: WS GP8, SCK GP9. SD MIC1–MIC6 = GP18, GP17, GP16, GP13, GP14, GP15. LED_DIN MIC1–MIC6 = GP21, GP20, GP19, GP10, GP11, GP12. Piezo GP6/GP7, I²C1 GP2/GP3, I²C0 GP4/GP5, UART GP0/GP1. Volné GP22 a GP26–GP28. Celá mapa: [`docs/PINOUT.csv`](../docs/PINOUT.csv).
- Šest RJ45 **bez magnetik** (Amphenol RJHSE-5380) ve dvou řadách, otvorem ven: MIC1–MIC3 na severní hraně, MIC4–MIC6 na jižní. T568B: pin 1 SCK, 2 GND, 3 WS, 4 SD, 5 GND, 6 GND, 7 3V3, 8 LED. Stínění na GND jen na HAT.
- Za každým jackem: ESD (PESD5V0S1BA) na SCK, WS, SD a LED, 33 Ω v sérii se SCK a WS, 100 Ω v sérii s LED a 100 kΩ pull-down na SD.
- Tři `SN74LVC8T245`. U2 budí SCK/WS pro MIC1–MIC3, U3 pro MIC4–MIC6 (3,3 V → 1,8 V). U4 převádí šest SD z 1,8 V na 3,3 V. 1,8 V jen pro budiče, LDO `AP2112K-1.8`.
- `DRV8837` na VSYS, vstupy GP6/GP7. Čtyři PS1240 paralelně na `J11`–`J14` (10 Ω v sérii).
- I²C1: DPS310 (0x77) + SHT40 (0x44). I²C0: INA3221 (0x40), bočníky 0,1 Ω na VSYS (R47) a na 3V3 k mikrofonům (R48).
- `J10` = VSYS ze power desky. `J17` = UART.
- Vrstvy: F.Cu signál, B.Cu GND výplň. `+3V3` a `+3V3_MIC` po B.Cu sběrnicích a prokovech (mezi patkami Pica B.Cu nesmí, SD2 jde po F.Cu).
- Pasiva od 0603 výš. Díry M3: [4; 4], [4; 136], [132; 50], [132; 90] mm.

**Satelit**

- Stejná mapa RJ45. `AP2112K-1.8` krmí T5848. LR na GND. 100 kΩ na SD, 33 Ω v sérii se SD. WS2812/SK6812 5050 na 3,3 V, `DOUT` nezapojený. Díra 0,8 mm pod akustickým portem.

**Power**

- Kleště / CT (**YHDC SCT-013-000** nebo VN ekvivalent) na izolovaný vodič. Na desku jen sekundár — ne 230 V ani 22 kV.
- Na desce: THT **burden 100 Ω** trvale na J1, **LC** (470 µH + 1 µF) před můstkem, **crowbar ~25 V** (X0202MN + BZX84-C24), USB-C laboratoř.
- Ještě dokreslit: panel (MPPT **CN3791**), **21700**, výstup 5 V (**BQ25895**), **PAC1934** / NTC. Kusovník: [het68-pwr/BOM_ZDROJE.csv](het68-pwr/BOM_ZDROJE.csv).

## Výroba

V `*/fab/` jsou Gerbery RS-274X (jen F.Cu a B.Cu), Excellon (PTH a NPTH zvlášť), mapy děr a CSV pozic. U HAT navíc IPC-D-356 a STEP osazené desky se zasunutým Pico. Poznámky k objednávce u printed.cz PROTOTYP jsou v `*/fab/VYROBA.txt`. Souhrnný kusovník je [`BOM.csv`](BOM.csv).

| Deska | Stav | Vrtání |
|---|---|---|
| HAT | DRC 0, parita 0; 2× zone-to-self na vrcholu GND výplně | 0,5 mm |
| Satelit | DRC 0, nepřipojené 0 — ENIG, 6× | 0,5 mm |
| Power | DRC 0, nepřipojené 0 pro harvest front-end | 0,5 mm |

Před panelem zkontroluj v 3D náhledu footprint T5848 (DS-000479, obr. 3 a 33) a DPS310. DPS310 sedí na pouzdru LGA-8 2,0 × 2,5 mm se stejným číslováním pinů jako BMP280.

V DRC HAT je vypnutá jen kontrola `lib_footprint_mismatch`: generátor záměrně skrývá reference malých pasiv na potisku (zůstávají na F.Fab), takže se footprinty liší od knihovny.
