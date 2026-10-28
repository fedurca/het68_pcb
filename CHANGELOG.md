# Changelog

Formát podle [Keep a Changelog](https://keepachangelog.com/cs/1.1.0/), verze podle [SemVer](https://semver.org/lang/cs/).

Historie gitu je přepsaná; veřejný tag je jen `v1.1.1`.

## [1.1.1] — 2026-10-28

### Added

- Zadání v Markdownu: [`docs/ZADANI_PCB.md`](docs/ZADANI_PCB.md).
- Předpoklady objednatele k posouzení (ne tvrdé požadavky): UTP k mikrofonům, nové MEMS a převodníky úrovní, compute A = Pimoroni Pico Plus 2 (8 MB PSRAM), compute B = vlastní deska s IPEX na Bluetooth a SX1262 pro MeshCore.
- GPIO tabulka [`docs/PINOUT.csv`](docs/PINOUT.csv) a checklist [`docs/CHECKLIST_NAVRHAR.md`](docs/CHECKLIST_NAVRHAR.md).
- Návrh GPIO pro SX1262, který nekoliduje s I²S.

[1.1.1]: https://github.com/fedurca/het68_pcb/releases/tag/v1.1.1
