# het68_pcb

Zadání návrhu a výroby PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v1.1.1](https://github.com/fedurca/het68_pcb/releases/tag/v1.1.1)** — viz [CHANGELOG.md](CHANGELOG.md).

Firmware, geometrie pole a stávající Grove zapojení: [fedurca/het68](https://github.com/fedurca/het68).

## Dokument k odeslání návrháři

**[docs/ZADANI_PCB.md](docs/ZADANI_PCB.md)** — zadání **v1.1.1** (česky, tag `v1.1.1`).

§1 jsou **předpoklady k posouzení**, ne tvrdé požadavky: UTP k mikrofonům, nové MEMS + převodníky úrovní, varianta Pimoroni Pico Plus 2 (8 MB PSRAM) nebo vlastní deska s IPEX na Bluetooth a SX1262 pro MeshCore.

Doplňky:

- [docs/PINOUT.csv](docs/PINOUT.csv) — GPIO firmware + návrh SX126
- [docs/CHECKLIST_NAVRHAR.md](docs/CHECKLIST_NAVRHAR.md) — zhodnocení a odevzdání
