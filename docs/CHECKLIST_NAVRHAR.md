# Checklist — het68 PCB

## Zhodnocení předpokladů (§1 zadání) — před kreslením

- [ ] UTP: 6× vs 2× RJ45, typ jacku, mapa párů T568B
- [ ] MEMS + budič: T5848+TXS0108E vs jiný I²S + line driver (kapacita UTP)
- [ ] Varianta A (Pimoroni Plus 2 / Plus 2 W + shield) vs B (vlastní + IPEX BT + SX126)
- [ ] Dutina 53 × 21 × 40 mm drží, nebo se zvětší
- [ ] Dva IPEX (2,4 GHz + 868 MHz) vs jeden
- [ ] Písemné doporučení jedné cesty (1–2 strany)

## Elektrika (po výběru cesty)

- [ ] I²S: GP8 WS, GP9 SCK, SD GP16/18/20/26/27/28 (nebo zapsaný remap u B)
- [ ] DPS310 na I²C (dnes GP2/GP3)
- [ ] Piezo GP6/GP7
- [ ] GP23/24/25/29 volné na W / CYW43
- [ ] SX126 **ne** na Waveshare pinech GP16/18/24
- [ ] MEMS VDD podle zvoleného čipu (T5848 = 1,8 V)
- [ ] LR/SEL = GND
- [ ] 100 nF u VDD MEMS, 100 kΩ na SD
- [ ] ESD + sériové R na I²S do UTP
- [ ] Dvě hodinové větve stejné délky
- [ ] Power PCB oddělená

## Varianta B (jen pokud vyhraje)

- [ ] IPEX 2,4 GHz k BT, 50 Ω, keep-out
- [ ] SX1262 868 MHz + IPEX, TCXO/DIO2 dle modulu
- [ ] GPIO dle §5.2 nebo zapsaná odchylka

## Dokumentace

- [ ] Schéma PDF + zdroj
- [ ] Gerber + drill + IPC-356
- [ ] BOM LCSC, DNP, cena @10 a @100
- [ ] CPL + STEP
- [ ] T568B / pinout na silkscreenu
- [ ] JLC nastavení
