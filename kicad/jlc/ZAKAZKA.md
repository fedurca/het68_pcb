# JLCPCB — podklady het68 v4.3.0

## Signály jsou částečně spojené

Router spojil většinu sítí na F.Cu a B.Cu. Stopy, které DRC označilo jako zkrat nebo podkročenou mezeru, jsou smazané. Core má 126 nepřipojených párů (hlavně QFN-80, rozteč 0,4 mm, bez fanoutu). Satelit 20. Silové desky kolem 75 a navíc překryté pady z rozmístění (desítky shorting_items mezi pady, ne mezi stopami).

Objednávka z těchto gerberů vyrobí desku se spojenou většinou signálů. MCU a několik LVDS párů se nezapne, dokud nebudou ty pady vyvedené.

## Košík

Společné: FR-4, tloušťka **1,6 mm**, zelená maska, bílý potisk, obrys frézováním (ne V-cut). Impedance se neobjednává (páry ještě nejsou na mědi).

| Deska | Soubor | Vrstvy | Povrch | Měď | Poznámka v objednávce |
|---|---|---|---|---|---|
| Core | `het68-core-gerber.zip` | 6 | ENIG | vnější 1 oz, vnitřní 0,5 oz | Faraday. Prokov 0,60/0,20 mm. QFN thermal via 0,50/0,20 mm (mezikruží 0,15 mm = minimum JLC) |
| Satelit ×6 | `het68-sat-gerber.zip` | 6 | ENIG | vnější 1 oz, vnitřní 0,5 oz | stejný prokov. Panel 6 ks až při osazení |
| Silová NN | `het68-pwr-nn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | jen sekundár CT, žádné síťové napětí |
| Silová VN | `het68-pwr-vn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | |
| Silová VVN | `het68-pwr-vvn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | |

6 a více vrstev u JLC **nemá HASL** — Core a satelit jen ENIG. 2oz na 2 vrstvách chce stopu ≥ 0,16 mm; pravidla desky jsou 0,20 mm.

Vrtání je rozdělené: `*-PTH.drl` pokovené, `*-NPTH.drl` nepokovené (M3 a akustický otvor T5848). Mapy vrtání v zipu nejsou, ať je JLC neplete s mědí.

## Osazení

`*-cpl.csv` je centroid z KiCadu (osa Y nahoru, mm, Top). `*-bom.csv` má MPN a prázdný sloupec LCSC. Kódy LCSC se nedoplňují odhadem. Bez nich JLC osazení nepřijme. RP2350B, ADXL355, T5848 a LVDS budou nejspíš extended nebo consignment.

## DFM, které tahle revize srovnala

- Lišty mají pin 1 jako počátek pouzdra. Řada roste v +Y a na desce je otočená tak, aby poslední pin zůstal uvnitř obrysu. Držák článku je Keystone 1122 (21700).
- Prokov 6L byl 0,45/0,20 mm, mezikruží 0,125 mm. JLC u vícevrstvé 1 oz chce ≥ 0,15 mm, doporučuje 0,20 mm. Teď 0,60/0,20 mm.
- Silová deska 2 oz: prokov pro budoucí router 1,00/0,50 mm (mezikruží 0,25 mm, minimum JLC pro 2 oz je 0,254 mm).
- Tloušťka 1,6 mm. 1,5 mm JLC v řadě tlouštěk nemá.
