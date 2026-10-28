# het68_pcb

Zadání a KiCad návrh PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v1.8.0](https://github.com/fedurca/het68_pcb/releases/tag/v1.8.0)** — viz [CHANGELOG.md](CHANGELOG.md). Kusovník: [kicad/BOM.csv](kicad/BOM.csv).

Firmware a geometrie pole: [fedurca/het68](https://github.com/fedurca/het68). Zadání pro návrháře: [docs/ZADANI_PCB.md](docs/ZADANI_PCB.md). Projekty v KiCadu: [kicad/README.md](kicad/README.md).

## Co to je

Tři desky.

**Power deska** bere tři zdroje: kleště na jednom izolovaném vodiči 230 V (jen sekundár, síť na desku nejde), malý panel a jeden článek 21700. Na nakreslené desce je zatím jen usměrnění sekundáru a USB-C. MPPT, nabíječka a měření V/I/T jsou v kusovníku, ve schématu ještě ne.

**Akustická deska** je HAT pod Pimoroni Pico Plus 2. Nese šest RJ45, převodníky I²S, budič čtyř piezoměničů, DPS310, SHT40 a INA3221. Piezoměniče jsou signalizace na téhle desce, ne v satelitech.

**Satelit** je šest stejných destiček, každá na vlastním kabelu. Na každé je mikrofon T5848, LDO 1,8 V a jedna adresovatelná RGB dioda.

## Co je ještě potřeba vyřešit

Stav po v1.7.0. Schémata mají ERC 0. Gerbery jsou dvouvrstvé, 1,6 mm. Do výroby je neposílat.

1. **HAT, 29 nepřipojených padů.** Zkraty, vůle a měď v zakázané zóně už DRC nehlásí. Chybí část napájení, I²S a LED mezi převodníky a jacky.
2. **Power, jedna mezera na VBUS.** CC1 a CC2 jsou spojené. Dva piny VBUS na USB-C a kondenzátor za nimi ještě nejsou jeden net.
3. **Power deska není ta ze zadání.** CN3791, BQ25895, držák 21700 a PAC1934 nejsou ve schématu.
4. **Stínění je na GND na obou koncích.** Konektor je stíněný RJHSE-5380. U STP patří plášť na GND jen na HAT. Na satelitu se `SH` odpojí.
5. **LED a I²S sdílejí země v kabelu.** Proud diody a hrany dat jedou ve stejných párech jako hodiny mikrofonu.
6. **RGB na 3,3 V.** Šest bílých diod se nevejde do 3,3 V z Pica. Stopa na satelitu počítá s SK6812, footprint je 5050 a běžný WS2812 chce 5 V.
7. **Pár pouzder v kusovníku nesedí na stopu.** SS34 je ve schématu na pouzdru SMC. DPS310 používá land pattern BMP280 a před výrobou se musí srovnat s C130156. T5848 chce ENIG a díru pod portem.
8. **Layout je autorouter.** Satelit je elektricky uzavřený. HAT a VBUS ne.

## Mají se LED řídit z power desky?

Ne jako náhrada dat z akustické desky. Směr zná Pico na HAT. Dioda sedí na satelitu a jediný kabel k němu je RJ45 z HAT. Když data vyrobí power deska, musí je stejně dostat na ten kabel: šest vodičů navíc z power desky na HAT a dál do jacku. Hluk dat a zpětný proud diody v párech mikrofonu zůstanou.

Co dává smysl: napájení diod z power desky, data nechat na HAT. Boost 5 V přijde na HAT a na pin 7 jen tehdy, když dioda 5 V potřebuje. Pin 7 se pak nesmí spojit s 3,3 V Pica. Zem diody nemá jezdit po zemích párů SCK, WS a SD. Plášť STP na to není zpětný vodič. Data `LED_DIN` zůstanou GPIO na HAT (GP10–14 a GP22), protože tam vzniká rozhodnutí o směru.

## Vyrobitelnost

Proces je běžný. Všechny tři desky jsou dvouvrstvé, 1,6 mm, menší než 100 × 100 mm. Jedna strana SMT, druhá zemní plocha. RJ45, hřebínky, Pico a radiální kondenzátory jsou vývodové. QFN, LGA a DFN potřebují rentgen. Satelit kvůli mikrofonu chce ENIG, HAT a power stačí HASL.

Továrna by desky podle dnešních Gerberů vyrobila. Osazený kus by nefungoval: na HAT chybí spoje a power deska nemá obvod ze zadání.

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

U jednoho kusu je zhruba 16 USD desky, 140 USD osazení (skoro celé jsou to jednorázové poplatky) a 50 USD součástky včetně Pica. Od dvaceti sad začne cenu táhnout Pico, šest mikrofonů a dvanáct stíněných jacků. Rozptyl je klidně ±30 %, dokud není košík: poplatek za feeder závisí na tom, co JLCPCB vede jako Basic.

## Sestava

Kleště jsou na jednom izolovaném vodiči obvodu 230 V. Na desku jde jen sekundár. Panel a článek 21700 jsou u power desky, výstup 5 V jde na HAT, šest satelitů je na RJ45.

![Sestava het68](docs/img/sestava.png)

## HAT — 99 × 96 mm, 2 vrstvy

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

## Napájení — 90 × 50 mm, 2 vrstvy

Sekundár split-core, můstek, TVS a diodové OR s USB-C. Na desce není 230 V. Specifikace další revize (panel, 21700, výstup 5 V) je v zadání a v `kicad/het68-pwr/BOM_ZDROJE.csv`; na obrázku je pořád jen usměrnění.

**Návrh PCB:**

![Návrh napájení](docs/img/pwr-pcb.png)

**Osazená deska:**

![Osazené napájení](docs/img/pwr-osazeno.png)
