# Osazení Core v5.1.0

Strojově se osazuje jen přední strana. Všechny součástky Core leží na F.Cu. `het68-core-bom.csv` a `het68-core-cpl.csv` mají stejné reference a u každého řádku je kód LCSC ověřený na stránce katalogu. Kód, který katalog neukázal, v souboru není.

Do stroje jde 85 součástek ve 31 položkách. Centroid je z KiCadu v milimetrech, osa Y nahoru, rotace tak, jak ji exportuje KiCad. U QFN, SOT a SOD ji JLC při kontrole náhledu může otočit.

## Mimo stroj

| Proč | Součástky |
|---|---|
| Do not populate | `J_STAMP` |
| Vývodové, pájejí se ručně | `J1`–`J6` (svislý RJ45), `J_MESH`, `J_PWR`, `J_SWD`, `J11`–`J14` (piezo) |
| Katalog nemá toto MPN v pouzdru na desce | `U13` `U14` SN65LVDS32D (SOIC-16), `U9` ADXL355BCCZ (na desce je QFN 3×3 mm, katalogové ADXL355 je LCC 6×6 mm), `F1`–`F6` (PPTC 0603 bez konkrétního MPN), `D_TX` `D_RX` `DT*` PESD5V0X1BT (katalogové pouzdro je SOT-23, na desce je SOD-323) |

## Co se v MPN změnilo, aby to šlo objednat

Původní řádek byl řada nebo jiné provedení. Nové MPN je to, které katalog uvádí, a sedí na stejné pouzdro.

| Bylo | Je | LCSC | Proč |
|---|---|---|---|
| 12MHz 3225 | CX3225SB12000H0FLJCC | C1985216 | 12 MHz, 3225, zátěž 12 pF. Dva kondenzátory 15 pF dají s parazitní kapacitou zhruba tu zátěž. |
| 2.2uH VREG | MLZ2012A2R2WTD25 | C404755 | 2,2 µH, 0805. Sytící proud je 210 mA. |
| ACM2012 | ACM2012-900-2P-T001 | C307642 | Tlumivka 2012, 90 Ω, 400 mA, čtyři vývody. |
| CL21A225KOQNNNE | CL21A225KOFNNNE | C1731 | 2,2 µF, 16 V, X5R, 0805. Původní kód v katalogu nebyl. |
| BLM18PG601SN1D | BLM18AG601SN1D | C19330 | 600 Ω na 100 MHz, 0603, 500 mA. Řada PG 601 v katalogu není. |
| PTS645SM43SMTR92 | PTS645SM43SMTR92LFS | C221880 | Stejné tlačítko 6×6 mm, výška 4,3 mm, bezolovnaté provedení. |
| SK6812 (5050, 3.3 V) | SK6812 | C5378720 | Pouzdro 5,4×5,0 mm. Katalog uvádí napájení 5 V, deska ho má na 3,3 V. |

Ostatní kódy patří přesně tomu MPN, které už v kusovníku bylo: RP2350B je C42415655, W25Q128JVSIQ je C97521, APS6404L-3SQR-SN je C5333729, AP2112K-3.3TRG1 je C51118, AP2112K-1.8TRG1 je C176944, DPS310 je C130156, DRV8837CDSGR je C191000, SHT40-AD1B-R2 je C2909890, SN65LVDS047PW je C2860344, TYPE-C-31-M-12 je C165948, SS34 je C717457. Rezistory RC0603 a kondenzátory CL10/CL21 mají kód své přesné položky.

Satelit a silové desky se neosazují. Mají otevřené páry a jejich `*-bom.csv` pořád nemá kódy LCSC.
