# JLCPCB — nastavení formuláře (v4.5.1)

Každá deska je samostatná zakázka. Jeden gerber zip = jedno Different Design. Rozměr ber z obrysu, ne ze společné kalkulace 100 × 100 mm.

Osazení nech vypnuté. V `*-bom.csv` je sloupec LCSC prázdný a bez něj JLC osazení nepřijme. RP2350B, ADXL355, T5848 a LVDS budou extended nebo consignment. Část signálů je pořád otevřená, osazená deska by se nezapnula. Satelit je oboustranný, takže pozdější osazení musí být Both sides.

Šablona (stencil) zůstane vypnutá, dokud se nepájí ručně.

Na měď nepatří 230 V, 22 kV ani 110 kV.

## Core — `het68-core-gerber.zip`

160 × 100 mm, 6 vrstev. Počet kusů: 1.

| Pole | Hodnota |
|---|---|
| Base Material | FR-4 |
| Material Type | FR4 TG155 |
| Layers | 6 |
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
| Via Covering | Tented |
| Min via hole size/diameter | 0.2 mm / (0.3/0.35 mm) |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ne |
| Gold Fingers, Castellated Holes, Press-Fit, Edge Plating, Blind Slots, Backdrill, UL Marking, Humidity Indicator Card | No |
| PCB Assembly | Off |
| Stencil | Off |

Via Covering není Epoxy Filled & Capped. Nápověda JLC říká, že prokov nad 0,5 mm se nezalije. V gerberu jsou prokovy 0,60/0,20 mm. Tepelné prokovy pod QFN jsou 0,50/0,20 mm. Deska se zalévanými prokovy nepočítá. Tented je maska přes prokov.

Min. vrtání není 0,3 mm. Návrh vrtá 0,20 mm. Číslo v závorce je nejmenší ploška k tomu vrtu, ne horní mez. Plošky 0,60 mm jsou větší než 0,35 mm.

6 vrstev u JLC nemá HASL, proto ENIG. Impedance se neobjednává, Specify Stackup zůstává No. Kelvinův test měří miliohmy a tady není potřeba. Flying probe stačí.

## Satelit — `het68-sat-gerber.zip`

50 × 80 mm, 6 vrstev. Počet kusů: 6. Stejné vrstvy, měď, povrch, prokov a via covering jako Core.

| Pole | Hodnota |
|---|---|
| Dimensions | 50 × 80 mm |
| PCB Qty | 6 |
| Layers | 6 |
| Material Type | FR4 TG155 |
| PCB Thickness | 1.6 mm |
| PCB Color / Silkscreen | Green / White |
| Surface Finish / Gold | ENIG / 1 µ" |
| Outer / Inner copper | 1 oz / 0.5 oz |
| Specify Stackup | No |
| Via Covering | Tented |
| Min via hole size/diameter | 0.2 mm / (0.3/0.35 mm) |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ne |
| Gold Fingers a ostatní speciální otvory | No |
| PCB Assembly | Off |
| Stencil | Off |

Venkovní strana (Top) má jen otvor mikrofonu a 8× SK6812. RJ45, T5848 a ostatní součástky jsou Bottom. Až se bude osazovat, volba strany je Both sides.

## Silová NN, VN, VVN

Tři samostatné zakázky: `het68-pwr-nn-gerber.zip`, `het68-pwr-vn-gerber.zip`, `het68-pwr-vvn-gerber.zip`.

140 × 80 mm, 2 vrstvy, měď 2 oz. Do 6vrstvé kalkulace je nedávej.

| Pole | Hodnota |
|---|---|
| Dimensions | 140 × 80 mm |
| PCB Qty | 1 na každé SKU |
| Layers | 2 |
| Material Type | FR4 TG135 stačí; TG155 nevadí |
| PCB Thickness | 1.6 mm |
| PCB Color / Silkscreen | Green / White |
| Surface Finish | ENIG, nebo LeadFree HASL |
| Gold Thickness | 1 µ", jen když zůstane ENIG |
| Outer Copper Weight | 2 oz |
| Inner Copper Weight | pole u 2 vrstev není |
| Specify Stackup | No |
| Via Covering | Tented |
| Min via hole size/diameter | podle vrtáku 0,50 mm v gerberu (prokov 1,00/0,50 mm) |
| Board Outline Tolerance | ±0.2 mm (Regular) |
| Confirm Production file | Yes |
| Mark on PCB | Remove Mark |
| Electrical Test | Flying Probe Fully Test |
| 4-Wire Kelvin Test | ne |
| Gold Fingers a ostatní speciální otvory | No |
| PCB Assembly | Off |
| Stencil | Off |

2 oz chce stopu aspoň 0,16 mm. Pravidla desky jsou 0,20 mm. Prokov 1,00/0,50 mm má mezikruží 0,25 mm. Epoxy fill se na tak velký prokov nevztahuje.

LeadFree HASL je na 2 vrstvách levnější a gerber ho snese. ENIG nech, když má být povrch stejný jako u Core a satelitu.
