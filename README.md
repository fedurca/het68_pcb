# het68_pcb

Zadání a KiCad návrh PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v1.10.0](https://github.com/fedurca/het68_pcb/releases/tag/v1.10.0)** — viz [CHANGELOG.md](CHANGELOG.md). Kusovník: [kicad/BOM.csv](kicad/BOM.csv).

Firmware a geometrie pole: [fedurca/het68](https://github.com/fedurca/het68). Zadání pro návrháře: [docs/ZADANI_PCB.md](docs/ZADANI_PCB.md). Projekty v KiCadu: [kicad/README.md](kicad/README.md).

## Co to je

Tři desky.

**Power deska** (100 × 58 mm) bere sekundár CT / kleští (ne 230 V ani 22 kV na desku), USB-C jako laboratorní vstup, a později panel + 21700. Na nakreslené desce je teď: THT burden 100 Ω trvale na J1, LC filtr před usměrňovačem, můstek, crowbar ~25 V (SCR X0202MN + Zener BZX84-C24) a výstup přes ferit. MPPT, nabíječka a PAC1934 jsou v kusovníku, ve schématu ještě ne.

**Akustická deska** je HAT pod Pimoroni Pico Plus 2. Nese šest RJ45, převodníky I²S, budič čtyř piezoměničů, DPS310, SHT40 a INA3221. Piezoměniče jsou signalizace na téhle desce, ne v satelitech.

**Satelit** je šest stejných destiček, každá na vlastním kabelu. Na každé je mikrofon T5848, LDO 1,8 V a jedna adresovatelná RGB dioda.

## Co je ještě potřeba vyřešit

Schémata mají ERC 0. Gerbery jsou dvouvrstvé, 1,6 mm.

1. **HAT — pořád neobjednávat.** Zkraty a vůle DRC nehlásí, ale zbývají nepřipojené sítě (I²S, LED, část napájení a piezo mezi převodníky a jacky). Autorouter na 94 × 96 mm s šesti jacky a třemi TSSOP nestačí.
2. **Power — harvest front-end je DRC 0.** Burden, LC a crowbar jsou na desce. CN3791, BQ25895, držák 21700 a PAC1934 ve schématu ještě nejsou; bez nich to není kompletní napájení ze zadání.
3. **Stínění satelitu.** Plášť je na GND jen na HAT. Na satelitu je `SH` nezapojený.
4. **LED a I²S sdílejí země v kabelu.** Mapa T568B je zmrazená. Proud diody pořád jede po zemích hodin.
5. **RGB na 3,3 V.** Šest bílých diod se nevejde do 3,3 V z Pica. Footprint je 5050.
6. **DPS310.** Land pattern je z BMP280 — před výrobou HAT srovnat s C130156. T5848 chce ENIG. SS34 je SMC.
7. **Satelit** je elektricky uzavřený (DRC 0). Objednat s ENIG.

## Vyrobitelnost

Proces je běžný. Všechny tři desky jsou dvouvrstvé, do 100 × 100 mm. Jedna strana SMT, druhá zemní plocha. RJ45, hřebínky, Pico, THT burden, tlumivka a radiální kondenzátory jsou vývodové. QFN, LGA, DFN a SOT-223 crowbaru potřebují běžné SMT / rentgen podle pouzdra. Satelit chce ENIG, HAT a power stačí HASL.

| Deska | DRC error | Unconnected | Objednat Gerbery? |
|---|---|---|---|
| Satelit | 0 | 0 | ano, ENIG, 6× |
| Power | 0 | 0 | ano jen pro harvest front-end; bez MPPT/BQ |
| HAT | 0 (zkraty/vůle) | ano, desítky | ne |

## Odhad výrobní ceny

Jedna sada = 1 akustická deska + 1 power deska v dnešním zapojení + 6 satelitů + 1 Pico Plus 2. Ceny jsou USD bez dopravy a bez daně, říjen 2026. Nejsou to nabídka výrobce.

V ceně je plošný spoj, economic osazení a součástky na deskách. Mimo cenu jsou čtyři piezoměniče, šest kabelů, kleště SCT-013-000 (maloobchod kolem 9–12 USD) a článek 21700.

Podklady: JLCPCB, 2 vrstvy, do 100 × 100 mm, 5 ks za 2 USD a 10 ks za 5 USD. Od třiceti kusů asi 1,10 USD za desku 100 × 100 mm (srovnání z 23. 8. 2026). U 1000 kusů je v tabulce extrapolace 0,90 USD. ENIG na satelitu je přirážka odhadem 0,75 USD/ks do deseti kusů a 0,40 USD/ks dál. Osazení podle ceníku JLCPCB z 22. 10. 2026: setup 8,18 USD, šablona 1,53 USD a ruční pájení 3,58 USD za každou ze tří desek, 3,07 USD za extended součástku (počítáno 25 typů), 0,0016 USD za SMT spoj (odhad 480 na sadu), 0,0164 USD za vývodový spoj (odhad 140 na sadu), rentgen na 10 bezvývodových pouzder na sadu.

Součástky se známou cenou: Pico Plus 2 asi 14 USD v malém množství (The Pi Hut 12,90 GBP vč. DPH), T5848 podle Mouseru, RJHSE-5380 podle LCSC C464586, SN74LVC8T245PWR podle LCSC C27643. Ostatní pasiva, diody, konektory a senzory bez stažené ceny jsou paušál 8 USD na sadu do 20 kusů, 5,50 USD do 100 kusů a 4 USD při 1000 kusech.

U 1–4 sad se stejně objedná minimum desek (5 + 5 + 10), proto prvních pár kusů nese celý setup.

| Sad | Celkem USD | USD za sadu |
|---:|---:|---:|
| 1 | 200 | 200 |
| 2 | 250 | 125 |
| 3 | 320 | 105 |
| 4 | 380 | 95 |
| 5 | 440 | 88 |
| 10 | 710 | 71 |
| 20 | 1220 | 61 |
| 100 | 4900 | 49 |
| 1000 | 43300 | 43 |

U jednoho kusu je zhruba 16 USD desky, 140 USD osazení (skoro celé jsou to jednorázové poplatky) a 50 USD součástky včetně Pica. Od dvaceti sad začne cenu táhnout Pico, šest mikrofonů a dvanáct stíněných jacků. Rozptyl je klidně ±30 %, dokud není košík: poplatek za feeder závisí na tom, co JLCPCB vede jako Basic. Akustická deska je v téhle verzi 94 × 96 mm místo 99 × 96 mm. U JLCPCB je do 100 × 100 mm stejná cena, takže zmenšení samo o sobě tabulku nemění.

## Vlastní deska místo Pico Plus 2 W

Dnešní odhad počítá s koupeným Pico Plus 2 bez rádia, asi 14 USD v malém množství. Vlastní deska ve třídě Pico Plus 2 W znamená RP2350B, 16 MB flash, 8 MB PSRAM a CYW43439.

| Dílek | 1 ks | od 100 ks | od 1000 ks | Zdroj |
|---|---:|---:|---:|---|
| RP2350B | 1,20 | 1,00 | 0,90 | Raspberry Pi, ceník čipu |
| CYW43439KUBGT | 5,78 | 4,01 | 4,01 | LCSC C5359496, dál než 100 ks není uvedeno |
| flash 16 MB | 3,42 | 2,14 | 2,10 | LCSC, W25Q128JVPIQ |
| PSRAM 8 MB | 1,93 | 1,58 | 1,52 | LCSC C5360304, APS6404L |
| LDO, krystal, anténa, pasiva | 1,00 | 0,70 | 0,50 | odhad |
| **čipy celkem** | **13,30** | **9,40** | **9,00** | |

Proti 14 USD za koupený modul bez Wi-Fi jsou čipy při jednom kusu skoro stejně drahé a při tisíci kusech asi o 5 USD levnější. K tomu přibude osazení QFN-80 a rádia, rentgen a nejspíš čtyři vrstvy pod CYW43439. Čtyři vrstvy na desce 100 × 100 mm stály v srpnu 2026 u deseti kusů kolem 96 USD proti 5 USD za dvě vrstvy, tedy řádově +9 USD na kus v malé sérii. Když rádio sedí na vlastní malé desce a akustická deska zůstane dvouvrstvá, plošný spoj rádia spadne do stejného prototypového minima 2 USD za pět kusů a na kus vyjde levněji než přepočet celé akustické desky na čtyři vrstvy.

Nová anténa k CYW43439 nemá certifikaci modulů Pimoroni. Jednorázová zkouška rádia se běžně počítá v tisících USD. Při sto kusech je to desítky USD na sadu, při tisíci pořád víc než úspora na čipech.

Bez rádia, jen vlastní náhrada Pico Plus 2 (RP2350B, flash, PSRAM, bez CYW43439), jsou čipy asi 7,50 USD při jednom kusu a asi 5 USD při tisíci. Proti koupeným 14 USD je to úspora kolem 5–6 USD na sadu ještě před osazením QFN-80. Dvouvrstvá deska na to stačí. Rádio z té úspory udělá v malé sérii prodělek.

## Sestava

Kleště / CT jsou na jednom izolovaném vodiči. Na desku jde jen sekundár (burden, LC, crowbar). Panel a článek 21700 jsou u power desky, výstup 5 V jde na HAT, šest satelitů je na RJ45.

![Sestava het68](docs/img/sestava.png)

## HAT — 94 × 96 mm, 2 vrstvy

Pico Plus 2 uprostřed, šest RJ45, převodníky I²S, budič čtyř piez, DPS310, SHT40 a INA3221.

**Návrh PCB** (vrchní měď, potisk, maska):

![Návrh HAT](docs/img/hat-pcb.png)

**Osazená deska:**

![Osazený HAT](docs/img/hat-osazeno.png)

## Satelit — 28 × 52 mm, 2 vrstvy

Jeden mikrofon T5848, LDO 1,8 V a adresovatelná RGB dioda. Stejná mapa RJ45 jako na HAT.

**Návrh PCB:**

![Návrh satelitu](docs/img/sat-pcb.png)

**Osazená deska:**

![Osazený satelit](docs/img/sat-osazeno.png)

## Napájení — 100 × 58 mm, 2 vrstvy

Sekundár CT → THT burden 100 Ω → LC → můstek → crowbar ~25 V, plus USB-C laboratoř. Na desku nejde 230 V ani 22 kV. Panel, 21700 a BQ25895 jsou v `kicad/het68-pwr/BOM_ZDROJE.csv`, ve schématu ještě ne.

**Návrh PCB:**

![Návrh napájení](docs/img/pwr-pcb.png)

**Osazená deska:**

![Osazené napájení](docs/img/pwr-osazeno.png)
