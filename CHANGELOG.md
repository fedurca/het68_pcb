# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Historie gitu je přepsaná; veřejné tagy `v1.1.1`, `v1.2.0`, `v1.3.0`.

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

[1.3.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.3.0
[1.2.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.2.0
[1.1.1]: https://github.com/fedurca/het68_pcb/releases/tag/v1.1.1
