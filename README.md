# het68_pcb

Zadání návrhu a výroby PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v1.2.0](https://github.com/fedurca/het68_pcb/releases/tag/v1.2.0)** — viz [CHANGELOG.md](CHANGELOG.md).

Firmware, geometrie pole a stávající Grove zapojení: [fedurca/het68](https://github.com/fedurca/het68).

## Dokument k odeslání návrháři

**[docs/ZADANI_PCB.md](docs/ZADANI_PCB.md)** — zadání **v1.2.0** (česky, tag `v1.2.0`).

**Zmrazené:** 6× RJ45 — každý mikrofon má vlastní UTP a na stejném kabelu i adresovatelnou RGB LED (indikace detekovaného směru). Deska s jacky je větší než Pico 53 × 21 mm.

Ostatní body §1 jsou **předpoklady k posouzení**, ne tvrdé požadavky: nové MEMS + převodníky úrovní, varianta Pimoroni Pico Plus 2 (8 MB PSRAM) nebo vlastní deska s IPEX na Bluetooth a SX1262 pro MeshCore.

Doplňky:

- [docs/PINOUT.csv](docs/PINOUT.csv) — GPIO firmware, 6× LED_DIN, návrh SX126 na extra pinech RP2350B
- [docs/CHECKLIST_NAVRHAR.md](docs/CHECKLIST_NAVRHAR.md) — zhodnocení a odevzdání
