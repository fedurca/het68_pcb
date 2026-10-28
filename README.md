# het68_pcb

Zadání návrhu a výroby PCB pro **het68** (akustická detekce dronů).

Aktuální verze: **[v1.3.0](https://github.com/fedurca/het68_pcb/releases/tag/v1.3.0)** — viz [CHANGELOG.md](CHANGELOG.md).

Firmware, geometrie pole a stávající Grove zapojení: [fedurca/het68](https://github.com/fedurca/het68).

## Dokument k odeslání návrháři

**[docs/ZADANI_PCB.md](docs/ZADANI_PCB.md)** — zadání **v1.3.0** (česky, tag `v1.3.0`).

**Zmrazené:** HAT k [Pimoroni Pico Plus 2](https://shop.pimoroni.com/products/pimoroni-pico-plus-2) (nebo Plus 2 W). Na HAT:

- převodníky úrovní a **6× RJ45** (jeden UTP na mikrofon + RGB LED směru)
- budič **4× piezo** (firmware H-můstek GP6/GP7)
- **6×** `LED_DIN` (WS2812 / SK6812 u satelitů)
- I²C: powermanagement a environmentální senzor (tlak, teplota, vlhkost)

Vlastní MCU deska, SX126 a IPEX v této revizi nejsou.

Doplňky:

- [docs/PINOUT.csv](docs/PINOUT.csv) — GPIO firmware + HAT
- [docs/CHECKLIST_NAVRHAR.md](docs/CHECKLIST_NAVRHAR.md) — zhodnocení a odevzdání
