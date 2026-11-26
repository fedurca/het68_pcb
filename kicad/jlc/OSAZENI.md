# Osazení Core v6.0.0

Strojově se osazuje jen přední strana. `het68-core-bom.csv` a `het68-core-cpl.csv` mají stejné reference. Každý kód LCSC je ze stránky katalogu.

Do stroje jde 110 součástek ve 33 položkách. Akcelerometr na desce není.

## Mimo stroj

| Proč | Součástky |
|---|---|
| Do not populate | `J_STAMP` |
| Vývodové, pájejí se ručně | `J1`–`J6` (svislý RJ45), `J_MESH`, `J_PWR`, `J_SWD`, `J11`–`J14` |
| LCSC ten SOIC-16 nemá, pouzdro na desce sedí | `U13` `U14` SN65LVDS32D, dodat a osadit ručně |

## Díly, které se proti 5.1.0 změnily

| MPN | LCSC | Proč |
|---|---|---|
| ESD05V32D-LC | C5180093 | Obousměrná ochrana 5 V v SOD-323, typicky 0,6 pF. Nahrazuje PESD5V0X1BT, které je SOT-23. |
| 0603L025/6V | C49317890 | PPTC 0603, drží 250 mA, maximum 6 V. |
| DFE201210U-2R2M=P2 | C2049745 | 2,2 µH, 0805, sytící proud 2 A. Předchozí tlumivka se sytí při 210 mA. |
| BLM18AG601SN1D | C19330 | Ferit 600 Ω na 100 MHz, 0603, 500 mA. |
| ACM2012-900-2P-T001 | C307642 | Společná tlumivka 2012, 90 Ω, 400 mA. |
| CX3225SB12000H0FLJCC | C1985216 | Krystal 12 MHz, 3225, zátěž 12 pF. |
| CL21A225KOFNNNE | C1731 | 2,2 µF, 16 V, X5R, 0805. |
| PTS645SM43SMTR92LFS | C221880 | Tlačítko 6×6 mm, výška 4,3 mm. |
| SK6812 | C5378720 | Stavová LED 5050. Napájení je `+5V_ALWAYS`, ne 3,3 V. |

RP2350B je C42415655. Flash, PSRAM, oba LDO, DPS310, SHT40, DRV8837, tři SN65LVDS047, USB-C a SS34 mají kód svého MPN. Rezistory RC0603 a kondenzátory CL10/CL21 také.

Satelit a silové desky se neosazují.
