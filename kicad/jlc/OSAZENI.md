# Osazení v7.1.0

`*-bom.csv` a `*-cpl.csv` mají stejné reference. Každý kód LCSC je ze stránky katalogu. Centroid je poloha z KiCadu, osa Y je otočená, rotace je kičadovská. JLC u QFN, SOT a SOD rotaci při kontrole často opraví.

## Core

111 součástek, jen horní strana. Akcelerometr na desce není. Proti 6.0.0 je ve stroji navíc `J_USB` (`TYPE-C-31-M-12`, C165948).

Mimo stroj:

| Proč | Součástky |
|---|---|
| Do not populate | `J_STAMP` |
| Vývodové, pájejí se ručně | `J1`–`J6` (svislý RJ45), `J_MESH`, `J_PWR`, `J_SWD`, `J11`–`J14` |
| Katalog ten SOIC-16 nemá | `U13` `U14` SN65LVDS32D, dodat a osadit ručně |

## Satelit

40 součástek. Horní strana: `D4`–`D11` (SK6812). Dolní strana: ostatní, včetně `MK1` T5848 (`MMICT5848-00-012`, C20344623).

Mimo stroj jsou svislý RJ45 `J1` a propojky `JP_SCK`, `JP_WS`, `JP_SD`, `JP_SDN`, `JP_TSCK`, `JP_TWS`, `JP_OE`. Propojka se připájí až podle režimu linky.

Úpravy proti původnímu MPN, protože pouzdro na desce je jiné, nebo katalog ten řetězec nemá:

| Na desce | Objednává se | LCSC | Proč |
|---|---|---|---|
| SOD-323 | ESD05V32D-LC | C5180093 | PESD5V0X1BT je SOT-23. |
| ferit 600 Ω | BLM18AG601SN1D | C19330 | Stejná 0603, 600 Ω na 100 MHz. |
| společná tlumivka | ACM2012-900-2P-T001 | C307642 | 2012, 4 vývody, 90 Ω. |
| PPTC 0,5 A | 0603L050/6V | C49318280 | 0603, drží 500 mA, maximum 6 V. |
| SK6812 | SK6812 | C5378720 | Pouzdro 5050 sedí. Katalog chce 3,7–5,5 V, satelit je krmí z 3,3 V. |

## Silové desky

Jen horní strana. NN 49, VN 50 (druhá GDT), VVN 48. USB-C `J2` je ve stroji (`TYPE-C-31-M-12`, C165948), stínicí vývody se pájejí s ním. `U_BST` je `FP6291LR-G12` (C18701). Vývod 6 (`OC`) je volný.

Společné náhrady, vybrané podle pouzdra na desce:

| Původní popis | Objednává se | LCSC | Proč |
|---|---|---|---|
| BZX84-C24 | BZX384-C24-QX | C7508119 | 24 V, SOD-323. BZX84-C24 v katalogu je SOT-23. |
| GDT | SMD4532-090NF | C9235 | 1812, zápal 90 V. Napětí v návrhu nebylo určené. |
| pojistka 1812 0,5 A | 1812L050PR | C151169 | 1812, drží 500 mA. |
| 1 µF 100 V | CL31B105KCHNNNE | C13832 | 1206, X7R, 100 V. |
| 10 Ω 0,1 % | RT1206BRD0710RL | C309661 | 1206, 10 Ω, 0,1 %. |
| 0,1 Ω | RTT05R100FTP | C125639 | 0805, 100 mΩ, 1 %. Přesné Yageo MPN v katalogu není. |
| 10 µH | MTQH201210S100MBT | C17701180 | 0805, 10 µH, 1 A, sytí při 1,2 A. Běžná 0805 10 µH v katalogu má 15 mA. |
| LED | KT-0603R | C2286 | Červená 0603. Barva ve schématu není. |
| FP6291 | FP6291LR-G12 | C18701 | SOT-23-6. Přesné FP6291 má 0 kusů. Vývod 6 je `OC` a je volný. |

Mimo stroj na všech třech:

| Proč | Součástky |
|---|---|
| Vývodové | `J1`, `J3`, `J_CORE`, `J_SOL`, `J_RTD`, `C1`, `L1`, `R4`. Na VVN ještě `J_ROGO`. |
| Vývodové P600, díra 1,6 mm, rozteč 15,24 mm | `DTVS`. NN: 5KP36A, C152046. VN a VVN: 15KP36A, C52993809. Pájet ručně. |
| Keystone 1122 v katalogu LCSC pro tohle pouzdro není | `BT1` |
| Skutečné pouzdro je SSOP-10, deska má SOIC-8 | `U_MPPT` CN3791, C154992 se na tuto desku nedá položit |

`X0202MN` je ve stroji jako `X0202MN 5BA4`, C221522, SOT-223.
