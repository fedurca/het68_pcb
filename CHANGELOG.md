# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Historie gitu je přepsaná; veřejné tagy `v1.1.1`, `v1.2.0`.

## [1.2.0] — 2026-10-28

### Changed

- **6× RJ45 je požadavek** (F10 / §1.1): jeden CAT5e/CAT6 patch na mikrofon, ne 2× jack se třemi mikrofony na kabelu.
- I/O deska s konektory je větší než Pico 53 × 21 mm (prstenec / šestiúhelník); dutina 53 × 21 × 40 mm platí jen pro MCU.
- Na každém RJ45 i `LED_DIN` adresovatelné RGB (WS2812 / SK6812) pro indikaci detekovaného směru. Bez `DOUT` zpět — šest samostatných GPIO, ne daisy-chain.
- T568B mapa: oranžový SCK, zelený WS, modrý SD, hnědý 3V3 + LED_DIN. 1,8 V pro T5848 jen z LDO na satelitu.
- LED GPIO: GP10–14 a GP22. SX126 na variantě B proto na extra GPIO RP2350B (návrh GP30+), ne na tyhle piny a ne na Waveshare.

### Added

- Výroba: KiCad 8+, Gerber RS-274X pro JLC i printed.cz, LCSC Basic před Extended.

## [1.1.1] — 2026-10-28

### Added

- Zadání v Markdownu: [`docs/ZADANI_PCB.md`](docs/ZADANI_PCB.md).
- Předpoklady objednatele k posouzení (ne tvrdé požadavky): UTP k mikrofonům, nové MEMS a převodníky úrovní, compute A = Pimoroni Pico Plus 2 (8 MB PSRAM), compute B = vlastní deska s IPEX na Bluetooth a SX1262 pro MeshCore.
- GPIO tabulka [`docs/PINOUT.csv`](docs/PINOUT.csv) a checklist [`docs/CHECKLIST_NAVRHAR.md`](docs/CHECKLIST_NAVRHAR.md).
- Návrh GPIO pro SX1262, který nekoliduje s I²S.

[1.2.0]: https://github.com/fedurca/het68_pcb/releases/tag/v1.2.0
[1.1.1]: https://github.com/fedurca/het68_pcb/releases/tag/v1.1.1
