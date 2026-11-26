# JLCPCB — podklady het68

Hodnoty do formuláře jsou v [NASTAVENI.md](NASTAVENI.md). Core a satelit nepatří do jedné kalkulace se silovou deskou.

## Stav mědi

Nové spoje nemají zkrat ani podkročenou mezeru. Překryté pady na silových deskách jsou pryč.

| Deska | Otevřené měděné páry | Zkraty a mezery | Objednat osazení? |
|---|---|---|---|
| Satelit | 2, oba roh zemní zóny | 0 | ano, obě strany, 40 součástek |
| Core | 0 | 0 | ano, horní strana, 111 součástek |
| Silová NN | 0 | 0 | ano, horní strana, 48 součástek |
| Silová VN | 0 | 0 | ano, horní strana, 49 součástek |
| Silová VVN | 0 | 0 | ano, horní strana, 47 součástek |

Satelit je 8 vrstev. Signálové sítě jsou spojené. Dva záznamy DRC jsou roh zemních zón na (1,2, 1,2). Prokov GND má prstenec ve výplni na všech šesti zemních vrstvách. Režim linky volí propojka 2×3 na zadní straně. RJ45 je svislý.

Core má 8 vrstev, 0 zkratů a 0 otevřených párů. Silové desky jsou 6 vrstev, 0 otevřených párů. Silové stopy jsou na vnější mědi, I2C a sense na vnitřní signálové vrstvě mezi zemními plochami.

## Košík

Společné: FR-4, tloušťka **1,6 mm**, zelená maska, bílý potisk, obrys frézováním (ne V-cut). Impedance se neobjednává.

| Deska | Soubor | Vrstvy | Povrch | Měď | Poznámka v objednávce |
|---|---|---|---|---|---|
| Core | `het68-core-gerber.zip` | 8 | ENIG | vnější 1 oz, vnitřní 0,5 oz | Faraday. Prokov 0,30/0,15 mm. Via Covering Epoxy Filled & Capped |
| Satelit ×6 | `het68-sat-gerber.zip` | 8 | ENIG | vnější 1 oz, vnitřní 0,5 oz | prokov 0,60/0,20 mm. SIG_L6 mezi GND_L5 a GND_L7. Ven jen LED a port |
| Silová NN | `het68-pwr-nn-gerber.zip` | 6 | ENIG | vnější 2 oz pokud kalkulace umí, jinak 1 oz; vnitřní 0,5 oz | jen sekundár CT, žádné síťové napětí |
| Silová VN | `het68-pwr-vn-gerber.zip` | 6 | ENIG | stejně jako NN | |
| Silová VVN | `het68-pwr-vvn-gerber.zip` | 6 | ENIG | stejně jako NN | |

6 a více vrstev u JLC **nemá HASL**. 2 oz chce stopu ≥ 0,16 mm; pravidla desky jsou 0,20 mm. Na silové desce je stitch prokov 1,00/0,50 mm a nový únik 0,80/0,40 mm.

Vrtání je rozdělené: `*-PTH.drl` pokovené, `*-NPTH.drl` nepokovené (M3 a akustický otvor T5848). Mapy vrtání v zipu nejsou, ať je JLC neplete s mědí.

## Osazení

`*-bom.csv` a `*-cpl.csv` mají stejné reference. Každý kód LCSC je z katalogu. Centroid je z KiCadu, osa Y je otočená (JLC má Y dolů). Co stroj neosadí a proč, je v [OSAZENI.md](OSAZENI.md).

| Deska | Soubory | Počet | Strana |
|---|---|---|---|
| Core | `het68-core-bom.csv`, `het68-core-cpl.csv` | 111 | Top |
| Satelit | `het68-sat-bom.csv`, `het68-sat-cpl.csv` | 40 | Both |
| Silová NN | `het68-pwr-nn-bom.csv`, `het68-pwr-nn-cpl.csv` | 48 | Top |
| Silová VN | `het68-pwr-vn-bom.csv`, `het68-pwr-vn-cpl.csv` | 49 | Top |
| Silová VVN | `het68-pwr-vvn-bom.csv`, `het68-pwr-vvn-cpl.csv` | 47 | Top |

## DFM, které tahle řada drží

- Lišty mají pin 1 jako počátek pouzdra. Řada roste v +Y a na desce je otočená tak, aby poslední pin zůstal uvnitř obrysu. Držák článku je Keystone 1122 (21700).
- Prokov Core je 0,30/0,15 mm (vrtání 0,15 mm je příplatek). Satelit zůstává 0,60/0,20 mm.
- Silová deska: stitch prokov 1,00/0,50 mm (mezikruží 0,25 mm), únik z jemného rastru 0,80/0,40 mm (mezikruží 0,20 mm).
- Tloušťka 1,6 mm. Via covering Tented. Formulář po deskách je v NASTAVENI.md.
