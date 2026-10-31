# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Tento soubor drží řadu **4.x**. Starší tagy `v1.1.1` … `v3.0.0` zůstávají v gitu.

## [4.8.0] — 2026-10-31

### Added

- Satelit volí režim linky propojkou na desce. `JP_SCK`, `JP_WS` a `JP_SD` jsou hřebínky 2×3. Pin 1 je severovýchodní. Severní řádek je diferenciální LVDS, prostřední je jednostranných 3,3 V přes `TXS0104E`, jižní je 1,8 V přímo na T5848.
- `JP_TSCK` a `JP_TWS` doplní 100 Ω jen v diferenciálním režimu. `JP_SDN` 1–2 je záporný vývod budiče, 2–3 dává zápornou žílu na zem. `JP_OE` se nasazuje jen v režimu 1,8 V.
- Stínění RJ45 je na satelitu na GND. Napájení T5848 zůstává 1,62–1,98 V.

### Known

- DRC satelitu nemá zkrat ani mezeru. Vzdušné jsou `OE`, krátká mezera `SD_3V3` u `U5`, `WS_LVDS`, `WS_P`, `WS_T` a `WS_N`. Dva záznamy jsou roh zemních zón. Režim 1,8 V chce na druhém konci kabelu 1,8 V.

## [4.7.0] — 2026-10-29

### Changed

- Core používá prokov 0,30/0,15 mm. JLCPCB na 6 vrstvách vrtá od 0,15 mm; ploška je o 0,15 mm větší než díra (doporučené mezikruží). Vrtání 0,15 mm je v kalkulaci příplatek.
- L4 na Core je jedna plocha `+3V3_DIG`. Dřív ležel RP2350 na ostrůvku `+5V_ALWAYS`, takže prokov 3,3 V plochu minul. `+5V_ALWAYS` a `+1V8_AUDIO` jsou stopy.
- Únik QFN-80 je schod po ose pinu a prokov až tam, kde má L3 volný krok ven. Tlumivka měniče a kondenzátor `DVDD` jsou u pinu VREG, kondenzátory 1,8 V u LDO a ADXL355.
- DRC Core: 0 zkratů a 0 mezer. Otevřených párů je 17 (bylo 42). Pořád otevřené jsou `LED1/2/5/6_DIN`, `SCK3`/`WS3`, `I2C0_SCL`, `PIEZO_IN1/2`, `ADC_I`, `ADC_ROGO`, `ADC_HARVEST`, `BURDEN_EN`, `PG_5V`, `STATUS_DIN`. Jejich prokovy leží v prstenci, kudy stopa 0,15 mm už neprojde.
- Via Covering u Core je Epoxy Filled & Capped, protože tepelné prokovy jsou v ploše QFN a díra 0,15 mm se zalije.

## [4.6.0] — 2026-10-29

### Changed

- Doplněné trasy na všech pěti deskách. Žádná deska nemá zkrat ani podkročenou mezeru.
- Satelit má signálové sítě uzavřené. U2 (LVDS) je mimo montážní díru, SD mikrofonu je spojené s R1 a U5. DRC zbývá jeden záznam zóna–zóna GND; 153 zemních prokovů má prstenec v mědi na všech zemních vrstvách.
- Core klesl z 65 otevřených párů na 42. Montážní díra H1 je na (5, 71), mimo RJ45. Měď v keepoutu u konektoru je pryč.
- Silové desky: otevřené páry 30 (NN), 36 (VN) a 26 (VVN). Solární jack je na (127, 48), mimo držák 21700. Courtyard ani PTH už do sebe nezasahují.
- Náhledy: [`docs/img/v460/`](docs/img/v460/). Gerbery v `kicad/jlc/` sedí na tuhle měď. Osazení zůstává vypnuté, LCSC se nedoplňuje odhadem.

### Known

- Core a silové desky ještě nejsou elektricky úplné. Konce zbylých párů leží v mědi, kam se nevejde prokov 0,60/0,20 mm (na 2 vrstvách 1,00/0,50 mm). Objednávat jako funkční osazenou desku zatím ne.

## [4.5.1] — 2026-10-29

### Added

- Nastavení JLCPCB pro každou desku: [kicad/jlc/NASTAVENI.md](kicad/jlc/NASTAVENI.md). Core a satelit jsou 6L ENIG s prokovem 0,20 mm a via covering Tented. Silové desky jsou samostatná 2L zakázka s mědí 2 oz.

## [4.5.0] — 2026-10-29

### Changed

- Satelit je oboustranný. Ven (F.Cu) kouká jen akustický otvor T5848 a osm SK6812. Tělo mikrofonu, RJ45 a ostatní elektronika jsou na B.Cu.
- Silové desky už nemají zkrat pad–pad. DO-201, FP6291 a AP2112 jsou mimo lištu a diodový můstek, zbytek součástek se nesmí courtyardem překrývat.
- QFN-80 má schodovitý únik na F.Cu. Prokov 0,60 mm se do rozteče 0,40 mm nevejde.

### Known

- Core má pořád desítky otevřených párů (QSPI SD2/SD3, část I²S, LED, SWD, UART, pár LVDS). Satelit má otevřené části LVDS a dvě LED. Deska se ještě celá nezapne.

## [4.4.0] — 2026-10-29

### Added

- Fanout QFN-80: z každého signálového pinu vede 0,15 mm stopa po jeho ose. Prokov 0,60 mm se do rozteče 0,40 mm nevejde, takže zbytek trasy pokračuje mimo svazek.
- Krystal 12 MHz, jeho kondenzátory a tlumivka měniče jsou odsunuté od severní hrany QFN, aby měla řada pinů kudy ven. Sériové 33 Ω pro I²S jsou u západní hrany, mimo PSRAM.
- Core klesl ze 126 nepřipojených párů na 67, satelit z 20 na 13, silové desky zhruba ze 75 na 50. Nové spoje nemají zkrat. Otevřené zůstávají hlavně QSPI SD2/SD3, část LED a SWD/UART, protože z rovnoběžného svazku 0,40 mm odbočí jen krajní piny.

## [4.3.0] — 2026-10-29

### Added

- Signálové spoje na Core, satelitu a silových deskách. Router nechá měď, která se spojila, a stopy označené DRC jako zkrat nebo podkročená mezera jsou smazané.
- Core klesl ze 321 nepřipojených párů na 126. Satelit z 70 na 20. Silová deska zhruba ze 126 na 75. Zbývají vývody QFN-80 a několik LVDS párů u tlumivek.

## [4.2.0] — 2026-10-29

### Added

- Core: jedna stavová SK6812 (GP37, `STATUS_DIN`) a tři mikrospínače PTS645 — RESET (`RUN`), BOOT (`QSPI_SS`) a USER (GP38, aktivní v nule).
- Silová deska: držák **Keystone 1122** na článek 21700 (LiFePO4/LTO v tom rozměru). 18650 Keystone 1042 končí.
- K zakázce: masky, schéma PDF a gerber zip v `kicad/jlc/` a `docs/img/`.

## [4.1.0] — 2026-10-29

Produktový strom je jen Core 6L + satelit 6L + tři silové SKU. Z aktuální verze pryč HAT/Pico a historický 2L satelit/power v3.

### Added

- LVDS best practice pro silné rušení: **100 Ω** u přijímačů (Core SD, satelit SCK/WS), **CMC na SD** i na Core, **ferit 600 Ω** na 3V3 každého jacku a na satelitu.
- C0G 15 pF u krystalu 12 MHz (`CL10C150JB8NNNC`). Sériové 33 Ω na I²S u MCU. UART 22 Ω s korektním MPN.
- Kusovník sady [`kicad/BOM_KIT.csv`](kicad/BOM_KIT.csv) (1 Core + 6 satelitů + 1 silová NN).
- 3D náhledy prototypu: [`docs/img/core-3d.png`](docs/img/core-3d.png), [`docs/img/sat-3d.png`](docs/img/sat-3d.png), [`docs/img/pwr-nn-3d.png`](docs/img/pwr-nn-3d.png). STEP v `kicad/*/fab/`.
- Via fence GND 1,5 mm po obvodu.

### Changed

- README, zadání a checklist popisují jen 4.x. Generátor v3 (`gen_boards.py` main) odmítá spuštění, aby nepřepsal 6L satelit.

### Removed

- Z working tree: `kicad/het68-hat`, `kicad/het68-pwr`, `docs/PINOUT_HAT_v3.csv`, náhledy HAT/Pico a 2L satelitu v3. Historie zůstává v tagu `v3.0.0`.

### Notes

- ERC 0 chyb na všech pěti schématech. Satelit courtyard DRC 0. Doroutování stop je v4.2.0.

## [4.0.0] — 2026-10-29

Nativní RP2350B na 6L Faraday Core, MeshCore na Heltec V3 (`J_MESH`) se spánkem DSP, tři vyměnitelné silové SKU, satelit LVDS 6L s 8× SK6812. Na měď nejde síť.

### Added

- **Core** `kicad/het68-core`: RP2350B, 16 MB flash, 8 MB PSRAM, USB-C, 6× RJ45 LVDS, ADXL355, DPS310+SHT40, DRV8837, `J_MESH` 1×8 na Heltec WiFi LoRa 32 V3 868 MHz, DNP stamp land, interconnect 2×10. `WAKE_DSP` hradluje `+3V3_DIG` a `+1V8_AUDIO`.
- **Silové SKU** `het68-pwr-nn` / `vn` / `vvn`. Společný sekundár: GDT, TVS, LC, burden THT, crowbar, CN3791, LiFePO4/LTO, boost 5 V, LDO `+3V3_RF`, INA3221, PT1000.
- Satelit LVDS 6L Faraday 50 × 80 mm: CMC, TVS, PPTC 0,5 A, SN65LVDS2×2 + SN65LVDS1, TXS0104E, T5848 1,8 V ve středu, 8× SK6812 v kruhu.
- Generátor `kicad/tools/gen_v4.py`, 6L helper `kicad/tools/route6.py`.

### Changed

- Compute už není Pico Plus 2 + HAT. GP0/GP1 jsou UART MeshCore.
- T568B jednovodičové I²S na UTP končí; na kabelu je LVDS.

[4.8.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.8.0
[4.7.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.7.0
[4.6.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.6.0
[4.5.1]: https://github.com/fedurca/het68_pcb/releases/tag/v4.5.1
[4.5.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.5.0
[4.4.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.4.0
[4.3.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.3.0
[4.2.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.2.0
[4.1.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.1.0
[4.0.0]: https://github.com/fedurca/het68_pcb/releases/tag/v4.0.0
