# Checklist — het68 PCB (HAT k Pimoroni Pico Plus 2)

## Před kreslením

- [ ] Compute je **Pimoroni Pico Plus 2 / Plus 2 W** + HAT. Žádné vlastní SoM, SX126, IPEX
- [ ] **6× RJ45** (1 mic + 1 RGB LED na kabel). Posoudit jen typ jacku a T568B mapu §4.2
- [ ] Tvar HAT: Pico 53 × 21 mm uprostřed, šest jacků mimo ten obrys, USB-C/BOOT přístupné
- [ ] MEMS + budič: T5848+TXS0108E vs jiný I²S + line driver (6 zátěží SCK/WS)
- [ ] Env: DPS310+SHT4x vs BME280 (P+T+RH na I²C1 GP2/GP3)
- [ ] PM: INA219 vs INA3221 na I²C0 GP4/GP5; nesežrat Qw/ST pull-upy
- [ ] Piezo: H-můstek na GP6/GP7, **4× PS1240 paralelně**
- [ ] Písemné zhodnocení čipů a tvaru (1–2 strany)

## Elektrika

- [ ] I²S: GP8 WS, GP9 SCK, SD MIC1–6 = GP18/17/16/13/14/15 (rev E, od v2.0.0)
- [ ] SCK/WS buffer na 6 jacků, stejná délka větví
- [ ] 6× `LED_DIN`: MIC1–6 = GP21/20/19/10/11/12 (rev E); žádný daisy-chain `DOUT`
- [ ] T568B: oranžový SCK, zelený WS, modrý SD, hnědý 3V3 + LED_DIN
- [ ] Satelit: 3,3 V z UTP → LDO 1,8 V pro T5848; WS2812/SK6812 @ 3,3 V
- [ ] I²C1 env GP2/GP3; I²C0 PM GP4/GP5; adresy bez kolize
- [ ] Piezo budič (ne holé GPIO) → 4 elementy
- [ ] GP23/24/25/29 volné (Plus 2 W)
- [ ] MEMS VDD podle čipu (T5848 = 1,8 V), LR/SEL = GND
- [ ] 100 nF u VDD MEMS, 100 kΩ na SD
- [ ] ESD + sériové R na I²S do UTP
- [ ] Power PCB oddělená; na HAT jen INA

## Dokumentace

- [ ] Schéma PDF + zdroj (KiCad 8+) HAT + satelit + power
- [ ] Gerber RS-274X + drill + IPC-356 (JLC i printed.cz)
- [ ] BOM LCSC (Basic před Extended), DNP, cena @10 a @100 (bez Pico)
- [ ] CPL + STEP (HAT se zasunutým Plus 2)
- [ ] T568B / pinout na silkscreenu u každého `MIC1`…`MIC6`
- [ ] JLC nastavení / jlcpcb-tools
- [ ] printed.cz PROTOTYP: 2 vrstvy, ≥ 0603, ne BGA, ENIG, zelená maska, bílý potisk, frézovaný obrys, ≤ 200 × 250 mm
