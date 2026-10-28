# Checklist — het68 PCB

## Zhodnocení předpokladů (§1 zadání) — před kreslením

- [ ] **6× RJ45 je dané** (1 mic + 1 RGB LED na kabel). Posoudit jen typ jacku (SMT/THT, magjack vs holý, vertikál vs pravoúhlý) a T568B mapu §4.2
- [ ] Tvar I/O desky: prstenec / šestiúhelník / dvě řady; jacky k stěnám kostky. Pico 53 × 21 mm uprostřed, šest jacků **mimo** ten obrys
- [ ] MEMS + budič: T5848+TXS0108E vs jiný I²S + line driver (kapacita UTP, 6 zátěží SCK/WS)
- [ ] Varianta A (Pimoroni Plus 2 / Plus 2 W + shield) vs B (vlastní + IPEX BT + SX126)
- [ ] Dutina 53 × 21 × 40 mm platí jen pro MCU; tiskař upraví nosný prstenec podle STEP
- [ ] Dva IPEX (2,4 GHz + 868 MHz) vs jeden
- [ ] Písemné doporučení jedné cesty (1–2 strany)

## Elektrika (po výběru cesty)

- [ ] I²S: GP8 WS, GP9 SCK, SD GP16/18/20/26/27/28 (nebo zapsaný remap u B)
- [ ] SCK/WS buffer na 6 jacků, stejná délka větví
- [ ] 6× `LED_DIN`: GP10–14 a GP22; žádný daisy-chain `DOUT`
- [ ] T568B: oranžový SCK, zelený WS, modrý SD, hnědý 3V3 + LED_DIN
- [ ] Satelit: 3,3 V z UTP → LDO 1,8 V pro T5848; WS2812/SK6812 @ 3,3 V
- [ ] DPS310 na I²C (dnes GP2/GP3)
- [ ] Piezo GP6/GP7
- [ ] GP23/24/25/29 volné na W / CYW43
- [ ] SX126 **ne** na Waveshare pinech GP16/18/24 a **ne** na LED GP10–14/22; u B extra GPIO RP2350B (návrh GP30+)
- [ ] MEMS VDD podle zvoleného čipu (T5848 = 1,8 V)
- [ ] LR/SEL = GND
- [ ] 100 nF u VDD MEMS, 100 kΩ na SD
- [ ] ESD + sériové R na I²S do UTP
- [ ] Power PCB oddělená

## Varianta B (jen pokud vyhraje)

- [ ] IPEX 2,4 GHz k BT, 50 Ω, keep-out
- [ ] SX1262 868 MHz + IPEX, TCXO/DIO2 dle modulu
- [ ] GPIO dle §5.2 / `PINOUT.csv` (GP30+) nebo zapsaná odchylka

## Dokumentace

- [ ] Schéma PDF + zdroj (KiCad 8+)
- [ ] Gerber RS-274X + drill + IPC-356 (JLC i printed.cz)
- [ ] BOM LCSC (Basic před Extended), DNP, cena @10 a @100
- [ ] CPL + STEP
- [ ] T568B / pinout na silkscreenu u každého `MIC1`…`MIC6`
- [ ] JLC nastavení / jlcpcb-tools
