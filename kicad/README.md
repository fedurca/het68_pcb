# het68 — KiCad (v1.5.0)

Náhledy návrhu i osazených desek jsou v [README](../README.md) repozitáře.

Tři desky podle zmrazeného zadání (Pimoroni Pico Plus 2 + HAT, 6× RJ45, 4× piezo, I²C).

| Projekt | Deska | Vrstvy | Obrys |
|---|---|---|---|
| [het68-hat](het68-hat/het68-hat.kicad_pro) | HAT pod Pico Plus 2 / Plus 2 W | 2 (signál / GND) | 99 × 96 mm |
| [het68-sat](het68-sat/het68-sat.kicad_pro) | satelit, 6× stejný | 2, ENIG | 28 × 52 mm |
| [het68-pwr](het68-pwr/het68-pwr.kicad_pro) | napájení ze sekundáru split-core | 2 | 90 × 50 mm |

Schémata prošla ERC bez chyb (KiCad 10). Otevři `*.kicad_pro` v KiCadu.

Generátor (umístění i routování): `kicad/tools/gen_boards.py` (Python z KiCadu).

## Zapojení

**HAT**

- Patice `RaspberryPi_Pico_Common_THT`. Firmware piny beze změny: WS GP8, SCK GP9, SD GP16/18/20/26/27/28, piezo GP6/GP7, I²C1 GP2/GP3, I²C0 GP4/GP5.
- Tři `SN74LVC8T245`: SCK a WS z 3,3 V na 1,8 V, každý výstup na jeden jack (šest zátěží). SD opačně, 1,8 V z kabelu na 3,3 V do GPIO. `DIR`/`~OE` vůči VCCA. 1,8 V jen pro budiče, LDO `AP2112K-1.8` na HAT.
- RJ45 **bez magnetik** (Amphenol RJHSE-5380). T568B: pin 1 SCK, 2 GND, 3 WS, 4 SD, 5 GND, 6 GND, 7 3V3, 8 LED. Stínění na GND jen na HAT.
- `DRV8837` na VSYS, vstupy GP6/GP7. Čtyři PS1240 paralelně na `J11`–`J14` (10 Ω v sérii).
- I²C1: DPS310 (adresa 0x77, SDO a CSB na 3V3) + SHT40 (0x44). I²C0: INA3221 (A0 na GND → 0x40), bočníky 0,1 Ω na VSYS a na 3V3 k mikrofonům.
- `J10` = VSYS ze power desky. `J17` = UART GP0/GP1.

**Satelit**

- Stejná mapa RJ45. `AP2112K-1.8` krmí T5848. LR na GND (levý slot). 100 kΩ na SD, 33 Ω v sérii se SD. WS2812/SK6812 5050 na 3,3 V, `DOUT` nezapojený. Díra 0,8 mm pod akustickým portem.

**Power**

- Kleště **YHDC SCT-013-000** na jeden izolovaný vodič 230 V / 10 A. Sekundár je 50 mA při 100 A, při 10 A asi 5 mA. Na desku nepřijde 230 V.
- Dál: panel (MPPT **CN3791**), jeden článek **21700**, výstup 5 V přes **BQ25895**. Měření V/I čtyř větví je **PAC1934**, teploty NTC přes **ADS1115**. Kusovník: [het68-pwr/BOM_ZDROJE.csv](het68-pwr/BOM_ZDROJE.csv).
- Starý návrh v KiCadu je pořád jen usměrnění a USB-C. PMIC, MPPT a 21700 v něm ještě nejsou.

## Výroba

V `*/fab/` jsou Gerbery RS-274X, Excellon (PTH a NPTH zvlášť), mapy děr a CSV pozic. `bom.csv` má MPN.

**Tyto Gerbery zatím neposílej do výroby.** Plošný spoj je autoroutovaný první návrh a DRC hlásí zkraty, vůle a nepřipojené pady (HAT stovky, satelit a power desítky). Schéma je v pořádku; layout je potřeba v PCB editoru dočistit (hlavně vějíř od převodníků k jackům a via u T5848) a znovu vyexportovat Gerbery.

Až DRC projde:

- HAT: JLCPCB nebo printed.cz, 2 vrstvy, 1,6 mm, HASL. Obrys je těsně pod 100 × 100 mm.
- Satelit: 2 vrstvy, ENIG (MEMS). Objednat 6 kusů na jedno zařízení.
- Power: 2 vrstvy, 1,6 mm, HASL.
- SMT: LCSC kódy v `bom.csv` doplnit (soubor má výrobní označení). RJ45 a hřebínky jsou THT.

Před panelem zkontroluj v 3D náhledu footprint T5848 (DS-000479, obr. 3 a 33) a DPS310. DPS310 sedí na pouzdru LGA-8 2,0 × 2,5 mm se stejným číslováním pinů jako BMP280 (GND, CSB, SDA, SCL, SDO, VDDIO, GND, VDD).
