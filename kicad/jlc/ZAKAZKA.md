# JLCPCB — podklady het68 v4.7.0

Hodnoty do formuláře jsou v [NASTAVENI.md](NASTAVENI.md). Core a satelit nepatří do jedné kalkulace se silovou deskou.

## Stav mědi

Nové spoje nemají zkrat ani podkročenou mezeru. Překryté pady na silových deskách jsou pryč.

| Deska | Otevřené měděné páry | Zkraty a mezery | Objednat osazení? |
|---|---|---|---|
| Satelit | 0 | 0 | ne, LCSC je prázdné a deska je oboustranná |
| Core | 17 | 0 | ne |
| Silová NN | 30 | 0 | ne |
| Silová VN | 36 | 0 | ne |
| Silová VVN | 26 | 0 | ne |

Satelit má jeden DRC záznam zóna–zóna GND na rohu obrysu zóny. Zemní prokovy mají prstenec v mědi na F.Cu, B.Cu, GND_L2, SIG_L3 i GND_L5. Signálové sítě satelitu včetně SD mikrofonu jsou spojené.

Core má 17 otevřených párů. Prokov je 0,30/0,15 mm a L4 je plocha `+3V3_DIG`. Zbylé páry končí v prstenci prokovů kolem QFN, kudy stopa 0,15 mm neprojde. Silové desky mají dál otevřené páry: na 2 vrstvách je prokov 1,00/0,50 mm.

## Košík

Společné: FR-4, tloušťka **1,6 mm**, zelená maska, bílý potisk, obrys frézováním (ne V-cut). Impedance se neobjednává.

| Deska | Soubor | Vrstvy | Povrch | Měď | Poznámka v objednávce |
|---|---|---|---|---|---|
| Core | `het68-core-gerber.zip` | 6 | ENIG | vnější 1 oz, vnitřní 0,5 oz | Faraday. Prokov 0,30/0,15 mm. Via Covering Epoxy Filled & Capped |
| Satelit ×6 | `het68-sat-gerber.zip` | 6 | ENIG | vnější 1 oz, vnitřní 0,5 oz | stejný prokov. Ven jen LED a port, elektronika zezadu |
| Silová NN | `het68-pwr-nn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | jen sekundár CT, žádné síťové napětí |
| Silová VN | `het68-pwr-vn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | |
| Silová VVN | `het68-pwr-vvn-gerber.zip` | 2 | ENIG nebo HASL bezolovnatý | **2 oz** | |

6 a více vrstev u JLC **nemá HASL** — Core a satelit jen ENIG. 2 oz na 2 vrstvách chce stopu ≥ 0,16 mm; pravidla desky jsou 0,20 mm.

Vrtání je rozdělené: `*-PTH.drl` pokovené, `*-NPTH.drl` nepokovené (M3 a akustický otvor T5848). Mapy vrtání v zipu nejsou, ať je JLC neplete s mědí.

## Osazení

`*-cpl.csv` je centroid z KiCadu (osa Y nahoru, mm). `*-bom.csv` má MPN a prázdný sloupec LCSC. Kódy LCSC se nedoplňují odhadem. Bez nich JLC osazení nepřijme. RP2350B, ADXL355, T5848 a LVDS budou nejspíš extended nebo consignment. Satelit se později osazuje z obou stran.

## DFM, které tahle řada drží

- Lišty mají pin 1 jako počátek pouzdra. Řada roste v +Y a na desce je otočená tak, aby poslední pin zůstal uvnitř obrysu. Držák článku je Keystone 1122 (21700).
- Prokov Core je 0,30/0,15 mm (JLCPCB 6L, vrtání 0,15 mm je příplatek). Satelit zůstává 0,60/0,20 mm.
- Silová deska 2 oz: prokov 1,00/0,50 mm (mezikruží 0,25 mm).
- Tloušťka 1,6 mm. Via covering Tented. Formulář po deskách je v NASTAVENI.md.
