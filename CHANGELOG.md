# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Historie gitu je přepsaná; veřejné tagy `v1.1.1` až `v3.0.0`.

## [3.0.0] — 2026-10-29

Všechny tři desky jdou objednat jako printed.cz PROTOTYP (jedna osazená deska, 5 000 Kč, do týdne). Major verze proto, že HAT mění obrys, tloušťku a počet vrstev proti v2.0.0 — pouzdro z 100 × 100 mm nesedí. GPIO z v2.0.0 zůstává.

### Changed

- **HAT 140 × 140 mm, 2 vrstvy, FR4 1,5 mm (rev F).** F.Cu signál, B.Cu zemní výplň. Prokovy 0,8 / 0,5 mm. Ve v2.0.0 byl HAT 100 × 100 mm a 4 vrstvy — to PROTOTYP nebere.
- **Pasiva 0603** (kondenzátory 10 µF zůstávají 0805). Na žádné desce není 0402 ani BGA.
- **Povrch ENIG**, zelená lesklá maska, bílý potisk, obrys frézováním. HAL a drážkování u PROTOTYPu nejsou.
- Satelit a power: stejné prokovy 0,8 / 0,5 mm a 0603. Díry M3 na HAT: [4; 4], [4; 136], [132; 50], [132; 90] mm.

### Fixed

- HAT, satelit i power: DRC 0, ERC 0, parita schéma ↔ deska 0. Satelit a power mají 0 nepřipojených padů. HAT má všechny sítě spojené; KiCad 10 hlásí 2× zone-to-self na vrcholu GND výplně (stejný bod, není to pad).

### Removed

- Vnitřní vrstvy HAT (In1 GND, In2 3V3). Napájení `+3V3` a `+3V3_MIC` je na B.Cu sběrnicích a prokovech.

## [2.0.0] — 2026-10-28

HAT rev E je kompletně propojený a vyrobitelný. Major verze proto, že se mění GPIO pro SD a LED: firmware musí přepsat pole `PIN_I2S_SD` a doplnit LED piny.

### Changed

- **GPIO (nekompatibilní s předchozím pinoutem):** SD MIC1–MIC6 = GP18, GP17, GP16, GP13, GP14, GP15. LED_DIN MIC1–MIC6 = GP21, GP20, GP19, GP10, GP11, GP12. GP0–GP9 beze změny, GP22 a GP26–GP28 volné. Mapa je v [`docs/PINOUT.csv`](docs/PINOUT.csv) a v zadání §5.
- **HAT 100 × 100 mm, 4 vrstvy:** F.Cu signál, In1 plná GND, In2 3V3 s ostrovem `+3V3_MIC` pod jacky, B.Cu signál. Prokovy 0,9/0,5 mm, stopa ≥ 0,25 mm, mezera ≥ 0,2 mm.
- **Jacky ve dvou řadách:** MIC1–MIC3 na severní hraně, MIC4–MIC6 na jižní, otvorem ven. Ve v1.10.0 mířila horní řada otvorem do desky.
- Budiče hodin po řadách: U2 SCK/WS pro MIC1–MIC3, U3 pro MIC4–MIC6. Výstupy B jdou SCK/WS střídavě v pořadí jacků, takže se nekříží. U4 přijímá všech šest SD.
- Pico Plus 2 leží naplocho, USB-C na západní hraně desky. Na HAT jsou dvě zásuvkové lišty 1×20 (8,5 mm).
- Kontakty RJ45 mají plošku 1,3 mm (vrták 0,89 mm), aby se SCK a WS dostaly mezi zadní řadou kontaktů. 3D model jacku ukazuje skutečné pouzdro.

### Added

- 100 kΩ pull-down na každém SD u jacku (R50–R55). Prázdný jack nenechá vstup převodníku plavat.
- ESD diody a sériové odpory přímo za každým jackem, pevně vedené.
- Výroba HAT: Gerbery všech čtyř vrstev, vrtání PTH/NPTH, CPL, IPC-D-356 a STEP se zasunutým Pico Plus 2.
- Náhledy spodní mědi, obou vnitřních vrstev a izometrický render sestavy.
- Zásuvkové lišty pro Pico v souhrnném kusovníku.

### Fixed

- HAT: DRC 0, nepřipojené 0, parita schéma ↔ deska 0, ERC 0 chyb.
- `ADC_VREF` (pin 35) už není spojený s 3V3.
- Router mazal při neúspěchu jedné sítě i dříve položené spoje (porovnával Python wrappery místo UUID).

### Removed

- Pull-up na `RUN` (R46). Pico má vlastní.

## [1.10.0] — 2026-10-28

### Added

- Power deska: trvalý THT burden 100 Ω na J1, LC filtr (470 µH + 1 µF) před usměrňovačem, tyristorový crowbar ~25 V (X0202MN + BZX84-C24) na usměrněném sekundáru.
- Zadání §3.2 doplněné o tyto tři ochrany pro VN / CT harvest.

### Changed

- Power deska 100 × 58 mm (rev B). C1 je 470 µF / 50 V. SMBJ15A nahrazený crowbarem.
- Satelit a power: DRC error 0, nepřipojené 0. HAT pořád nemá všechny sítě.
- Obnovené náhledy PCB a osazených desek, Gerbery satelitu a power.

### Fixed

- VBUS u USB-C: sběrnice nad konektorem, ať stopy nejdou mezi VBUS a GND piny 0,8 mm od sebe.

## [1.9.0] — 2026-10-28

### Changed

- Akustická deska je 94 × 96 mm. Pravý pár RJ45 je posunutý, ať montážní díry nesedí v courtyardu jacku.
- Stínění RJ45 na satelitu není na GND. Plášť zůstává na GND jen na HAT.
- Z README je pryč úvaha o řízení LED z power desky.
- Odhad, o kolik vyjde vlastní deska místo koupeného Pico Plus 2, s rádiem CYW43439 i bez něj.

### Fixed

- SS34 v kusovníku má poznámku, že pouzdro na desce je SMC.

## [1.8.0] — 2026-10-28

### Added

- Na začátku README je popis tří desek, seznam otevřených problémů po v1.7.0, vyrobitelnost a odhad ceny sady pro 1 až 1000 kusů.
- Úvaha, proč data LED zůstanou na akustické desce a z power desky má přijít jen napájení diod.
- Do kusovníku přibyl LCSC kód stíněného RJ45 `C464586` (RJHSE-5380).

## [1.7.0] — 2026-10-28

### Fixed

- HAT už nemá zkraty, vůle ani spoje v zakázané zóně. Zůstává 29 nepřipojených padů (napájení, část I²S a LED).
- Power: CC1 a CC2 na USB-C jsou spojené. Zbývá jedna mezera na VBUS.
- Satelit zůstává bez chyb DRC.

### Changed

- Kusovník má sloupec LCSC u ověřených dílů. Souhrn objednávky je [`kicad/BOM.csv`](kicad/BOM.csv), včetně zdrojů (SCT-013-000, CN3791, BQ25895, 21700, PAC1934), které na nakreslené desce ještě nejsou.

## [1.6.0] — 2026-10-28

### Changed

- Routing na dvou vrstvách je znovu. Mřížka 0,1 mm, vůle 0,2 mm, zakázané zóny součástek (tělo SHT40, anténa Pico) se obcházejí. Součástky na HAT už nesedí na Pico ani na RJ45.
- Satelit mikrofonu prošel DRC bez chyb a bez nepřipojených padů.
- Napájecí deska nemá zkraty ani vůle. Nepřipojené zůstávají CC1, CC2 a propojení VBUS na USB-C (rozteč 0,5 mm).
- HAT klesl z několika set DRC chyb na desítky. Pořád není na výrobu: část sítí chybí a pár via je moc blízko padům převodníků.

### Added

- Náhledy desek jsou z tohoto layoutu, včetně osazení. Nově i sestava: kleště na jednom vodiči vedení, panel, článek 21700 a propojené desky. [`docs/img/sestava.png`](docs/img/sestava.png).

## [1.5.0] — 2026-10-28

### Changed

- HAT, satelit i napájení jsou dvouvrstvé: signál na vrchní mědi, GND zóna na spodní. Gerbery v `kicad/*/fab/` jsou z tohoto layoutu. DRC pořád není čisté, do výroby je neposílat.
- T5848: zemní pady dál od akustické díry.
- Na sekundáru proudového transformátoru je zátěž 100 Ω ještě před pojistkou. Piezo budič v kusovníku je `DRV8837CDSGR`.

### Added

- Napájecí deska ve specifikaci: kleště **YHDC SCT-013-000** (jeden izolovaný vodič 230 V / 10 A, na desku jen sekundár), malý panel s MPPT `CN3791`, jeden článek **21700**, výstup 5 V přes `BQ25895`, měření napětí a proudu `PAC1934`, teploty přes NTC a `ADS1115`. Kusovník: [`kicad/het68-pwr/BOM_ZDROJE.csv`](kicad/het68-pwr/BOM_ZDROJE.csv).
- Tyto obvody v KiCadu ještě nejsou. Nakreslené napájení je pořád usměrnění sekundáru a USB-C.

## [1.4.0] — 2026-10-28

### Added

- KiCad 10 rev A: HAT, satelit mikrofonu a napájecí deska v [`kicad/`](kicad/README.md).
- Náhledy návrhu PCB a osazených desek v [README](README.md) (`docs/img/`).
- Gerbery, vrtání a BOM v `kicad/*/fab/`. Layout ještě neprošel DRC, do výroby až po dočištění.

## [1.3.0] — 2026-10-28

### Changed

- Compute **zmrazený**: Pimoroni Pico Plus 2 / Plus 2 W + **HAT**. Varianta B (vlastní SoM, SX126, IPEX) je mimo tuto revizi.
- Na HAT povinně: převodníky úrovní, 6× RJ45, budič **4× piezo** (GP6/GP7, elementy paralelně), 6× `LED_DIN`, I²C powermanagement a environment (tlak + teplota + **vlhkost**).
- Environment: firmware DPS310 doplnit o měřenou RH (SHT4x na I²C1) nebo nahradit BME280. INA219/INA3221 na I²C0.

## [1.2.0] — 2026-10-28

### Changed

- **6× RJ45 je požadavek** (F10 / §1.1): jeden CAT5e/CAT6 patch na mikrofon, ne 2× jack se třemi mikrofony na kabelu.
- I/O deska s konektory je větší než Pico 53 × 21 mm (prstenec / šestiúhelník); dutina 53 × 21 × 40 mm platí jen pro MCU.
- Na každém RJ45 i `LED_DIN` adresovatelné RGB (WS2812 / SK6812) pro indikaci detekovaného směru. Bez `DOUT` zpět — šest samostatných GPIO, ne daisy-chain.
- T568B mapa: oranžový SCK, zelený WS, modrý SD, hnědý 3V3 + LED_DIN. 1,8 V pro T5848 jen z LDO na satelitu.
- LED GPIO: GP10–14 a GP22.

### Added

- Výroba: KiCad 8+, Gerber RS-274X pro JLC i printed.cz, LCSC Basic před Extended.

## [1.1.1] — 2026-10-28

### Added

- Zadání v Markdownu: [`docs/ZADANI_PCB.md`](docs/ZADANI_PCB.md).
- Předpoklady objednatele k posouzení: UTP k mikrofonům, nové MEMS a převodníky úrovní, compute A = Pimoroni Pico Plus 2, compute B = vlastní deska s IPEX a SX1262.
- GPIO tabulka [`docs/PINOUT.csv`](docs/PINOUT.csv) a checklist [`docs/CHECKLIST_NAVRHAR.md`](docs/CHECKLIST_NAVRHAR.md).

[3.0.0]: https://github.com/fedurca/het68_pcb/releases/tag/v3.0.0
[2.0.0]: https://github.com/fedurca/het68_pcb/releases/tag/v2.0.0
[1.10.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.10.0
[1.9.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.9.0
[1.8.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.8.0
[1.7.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.7.0
[1.6.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.6.0
[1.5.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.5.0
[1.4.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.4.0
[1.3.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.3.0
[1.2.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.2.0
[1.1.1]: https://github.com/fedurca/het68_pcb/releases/tag/v1.1.1
