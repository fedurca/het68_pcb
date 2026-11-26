# JLCPCB — nastavení formuláře

Každá deska je samostatná zakázka. Jeden gerber zip = jedno Different Design. Rozměr ber z obrysu, ne ze společné kalkulace 100 × 100 mm.

Core se osazuje z přední strany, 110 součástek. `het68-core-bom.csv` a `het68-core-cpl.csv` mají kódy LCSC z katalogu. Mimo stroj jsou svislé RJ45, lišty, piezo, `J_STAMP` a dva SN65LVDS32. Akcelerometr na desce není. Rozpis je v [OSAZENI.md](OSAZENI.md). Satelit a silové desky osazení nemají: mají otevřené páry a prázdné LCSC. RJ45 je svislý 8P8C bez magnetik (`RJ45-8P8C-VERT`), ne pravý úhel RJHSE-5380. Satelit je oboustranný, takže až se bude osazovat, volba strany je Both sides.

Na měď nepatří 230 V, 22 kV ani 110 kV.

## Core — `het68-core-gerber.zip`

160 × 100 mm, 8 vrstev. Počet kusů: 1. Deska má 0 zkratů, 0 mezer a 0 otevřených párů. Osazení zůstává vypnuté.

| Pole | Hodnota |
|---|---|
| Base Material | FR-4 |
| Material Type | FR4 TG155 |
| Layers | 8 |
| Dimensions | 160 × 100 mm |
| PCB Qty | 1 |
| Product Type | Industrial/Consumer electronics |
| Different Design | 1 |
| Delivery Format | Single PCB |
| PCB Thickness | 1.6 mm |
| PCB Color | Green |
| Silkscreen | White |
| Surface Finish | ENIG |
| Gold Thickness | 1 µ" |
| Outer Copper Weight | 1 oz |
| Inner Copper Weight | 0.5 oz |
| Specify Stackup | No |
| Via Covering | Epoxy Filled & Capped |
| Min via hole size/diameter | 0.15 mm / 0.30 mm |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ano (od 8 vrstev ho JLC chce) |
| Gold Fingers, Castellated Holes, Press-Fit, Edge Plating, Blind Slots, Backdrill, UL Marking, Humidity Indicator Card | No |
| PCB Assembly | On, jen Top |
| Stencil | On, spolu s osazením |

Prokov je 0,30/0,15 mm. Průměr plošky je o 0,15 mm větší než vrtání, což je doporučené mezikruží JLC (0,075 mm na stranu). Vrtání 0,15 mm je na vícevrstvé desce vyrobitelné a v kalkulaci je to příplatek (platí pro jakoukoli velikost plošky). Tepelné prokovy sedí v ploše QFN, proto Via Covering = Epoxy Filled & Capped. Díra 0,15 mm se zalít dá; dřívější 0,60 mm ne.

L4 je jedna plocha `+3V3_DIG` pod procesorem. `+5V_ALWAYS` a `+1V8_AUDIO` jsou stopy, ne ostrůvky, do kterých by prokov 3,3 V netrefil.

8 vrstev u JLC nemá HASL, proto ENIG. Impedance se neobjednává, Specify Stackup zůstává No. Čtyřbodový test je u 8 vrstev povinný. Flying probe stačí jako funkční test.

## Satelit — `het68-sat-gerber.zip`

50 × 80 mm, 8 vrstev. Počet kusů: 6. Měď, povrch a tloušťka jako Core. Prokov satelitu zůstává 0,60/0,20 mm a via covering se bere z tabulky satelitu, ne z prokovu Core.

Skladba je F.Cu / GND_L2 / SIG_L3 / PWR_L4 / GND_L5 / SIG_L6 / GND_L7 / B.Cu. SIG_L6 je signál mezi dvěma zemními plochami.

| Pole | Hodnota |
|---|---|
| Dimensions | 50 × 80 mm |
| PCB Qty | 6 |
| Layers | 8 |
| Material Type | FR4 TG155 |
| PCB Thickness | 1.6 mm |
| PCB Color / Silkscreen | Green / White |
| Surface Finish / Gold | ENIG / 1 µ" |
| Outer / Inner copper | 1 oz / 0.5 oz |
| Specify Stackup | No |
| Via Covering | Tented |
| Min via hole size/diameter | 0.2 mm / 0.6 mm |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ano, u 8 vrstev povinný |
| Gold Fingers a ostatní speciální otvory | No |
| PCB Assembly | Off |
| Stencil | Off |

Venkovní strana (Top) má jen otvor mikrofonu a 8× SK6812. Svislý RJ45, hřebínky propojek (`JP_SCK`, `JP_WS`, `JP_SD` a menší `JP_T*` / `JP_SDN` / `JP_OE`), T5848 a ostatní součástky jsou Bottom. Zástrčka RJ45 míří kolmo ze zadní strany. Až se bude osazovat, volba strany je Both sides. Propojka se do osazení nedává: režim se volí až na stole.

## Silová NN, VN, VVN

Tři samostatné zakázky: `het68-pwr-nn-gerber.zip`, `het68-pwr-vn-gerber.zip`, `het68-pwr-vvn-gerber.zip`.

140 × 80 mm, 6 vrstev. Každé SKU je vlastní kalkulace, ne společně s Core.

Skladba je F.Cu / GND_L2 / SIG_L3 / SIG_L4 / GND_L5 / B.Cu. Silové stopy zůstávají na vnější mědi. Vnitřní vrstvy vedou I2C, sense a řízení mezi zemními plochami.

| Pole | Hodnota |
|---|---|
| Dimensions | 140 × 80 mm |
| PCB Qty | 1 na každé SKU |
| Layers | 6 |
| Material Type | FR4 TG155 |
| PCB Thickness | 1.6 mm |
| PCB Color / Silkscreen | Green / White |
| Surface Finish | ENIG |
| Gold Thickness | 1 µ" |
| Outer Copper Weight | 2 oz, pokud to 6vrstvá kalkulace nabízí, jinak 1 oz |
| Inner Copper Weight | 0.5 oz |
| Specify Stackup | No |
| Via Covering | Tented |
| Min via hole size/diameter | 0.40 mm / 0.80 mm (v gerberu je i stitch 1,00/0,50 mm) |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ano |
| Gold Fingers a ostatní speciální otvory | No |
| PCB Assembly | Off |
| Stencil | Off |

2 oz chce stopu aspoň 0,16 mm. Pravidla desky jsou 0,20 mm. Stitch prokov 1,00/0,50 mm má mezikruží 0,25 mm. Nový únik z jemného rastru je 0,80/0,40 mm, mezikruží 0,20 mm. 6 vrstev u JLC nemá HASL, proto ENIG.
