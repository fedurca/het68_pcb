# het68 — zadání návrhu a výroby PCB

**Projekt:** akustická detekce dronů (het68)
**Firmware a mechanika:** [github.com/fedurca/het68](https://github.com/fedurca/het68)
**Tento dokument:** [github.com/fedurca/het68_pcb](https://github.com/fedurca/het68_pcb)
**Stav:** proof-of-concept běží; toto je zadání další hardwarové iterace
**Verze zadání:** 1.5.0 · 28. 10. 2026 (Europe/Prague)
**Git tag:** `v1.5.0`
**Jazyk:** čeština (k odeslání návrháři)

Dokument vychází z provozu prototypu, z firmware v `fedurca/het68`, z vazby na pouzdro a z **zmrazeného compute + HAT v §1**.

**Jak číst tento brief**

| Sekce | Váha |
|---|---|
| §1 | **zmrazené** — Pimoroni Pico Plus 2 + HAT, 6× RJ45, převodníky úrovní, 4× piezo, 6× RGB LED, I²C (PM + P/T/RH). Architektura se neposuzuje. |
| §2 | omezení z běžícího firmware / fyziky — měnit jen s vědomím, že padne firmware nebo akustika |
| §3+ | technický podklad; výběr konkrétního čipu (shifter, piezo budič, BME vs DPS+SHT, jack) je na návrháři se zdůvodněním |

---

## 0. Účel zařízení

Šestinásobné I²S mikrofonní pole na kostce stojící na vrcholu. RP2350 počítá směr (DOA / SRP-PHAT), klasifikuje dron, posílá 6kanálové USB audio 48 kHz / 24 bit, skenuje BLE OpenDroneID a mezi nody si povídá akustickým chirpem přes piezo.

Cíl této desky: **HAT pod Pimoroni Pico Plus 2** uvnitř konstrukce, pryč od Grove Shield 56 × 56 mm, za **minimální cenu kusu** v sérii. Nasazení u vedení: nejdřív hobby lab na **230 V** venkovním vedení, indukční napájení split-core transformátorem. 22 kV a vysokonapěťové zkoušky **nejsou** součástí této zakázky.

```
                    mic1  sever, +35.26°
                      \
           mic3 ------ + ------ mic2     horní prstenec 120°
                      /|
                     / |   tři ortogonální základny
                mic4   mic6
                     \ |
                      \|
                    mic5               dolní prstenec −35.26°
```

Poloměr pole (střed → mikrofon) = `hrana / 2`. Firmware default hrana **128 mm** (poloměr 64 mm). Ve starší geometrii 384 mm je poloměr **192 mm**. I²S počítat na **UTP do ~30 cm** (ověřeno 25 cm na současném kabelu).

---

## 1. Zmrazené zadání

Toto se nekreslí jinak, jen se volí součástky a tvar, které to splní.

### 1.1 Compute — Pimoroni Pico Plus 2 + HAT

MCU **není** vlastní deska. HAT se vyrábí k hotovému modulu:

- [Pimoroni Pico Plus 2](https://shop.pimoroni.com/products/pimoroni-pico-plus-2) — RP2350B, **8 MB PSRAM**, 16 MB flash, USB-C, 53 × 21 mm, 40pin Pico header.
- Nebo [Pico Plus 2 W](https://shop.pimoroni.com/products/pimoroni-pico-plus-2-w) — totéž + RM2 (Wi-Fi + BT, anténa na modulu). Stejný HAT; na W **nesahat na GP23/24/25/29**.

Firmware (`PICO_BOARD`) umí Pico 2 / Pico 2 W / Plus 2 W. Standardní Raspberry Pi Pico 2 **nemá** 8 MB PSRAM; HAT je header-kompatibilní, ale objednatel bere **Pimoroni Plus 2 / Plus 2 W**.

HAT je stoh na 2× 20pin (samice na HAT, Pico zastrčí shora, nebo naopak — návrhář zvolí, ať USB-C a BOOT zůstanou přístupné). SX126, IPEX a vlastní SoM **nejsou** v této revizi.

### 1.2 Mikrofony po UTP — 6× RJ45

Každý mikrofon má **vlastní** CAT5e/CAT6 patch a **vlastní 8P8C**. Ne 2× jack se třemi mikrofony na kabelu, ne daisy-chain mezi satelity.

Důvody: radiální kabely ke stěnám kostky; na stejném RJ45 i `LED_DIN` adresovatelné RGB. Bez zpětného `DOUT` má každý jack vlastní GPIO.

Délka 20–30 cm. Stínění UTP na GND jen na HAT.

Šest 8P8C (~15–16 mm) se na 53 × 21 mm **nevejde**. Pico zůstane 53 × 21 uprostřed; HAT je větší (prstenec / šestiúhelník / dvě řady), jacky k příslušným stěnám. Dutina 53 × 21 × 40 mm platí jen pro sloupec MCU, ne pro celý HAT.

K posouzení: SMT vs THT, magjack vs holý, vertikál vs pravoúhlý. Ne počet jacků.

### 1.3 Převodníky úrovní / budiče I²S

Opustit ICS-43434 (NRND, prototyp na 3,3 V). Na HAT obvod, který **posune úroveň** 3,3 V MCU ⇔ 1,8 V MEMS a **budí šest UTP**.

| Role | Výchozí návrh | Volba návrháře |
|---|---|---|
| MEMS (na satelitu) | TDK InvenSense **T5848** (I²S, 1,62–1,98 V, SNR 68 dBA) | alternativa DMM-4026-B-I2S-R; Sensibel SBM140B se nesežene |
| Převod / budič (na HAT) | **TXS0108E** (SCK+WS+6×SD) | TXS nesnáší velkou kapacitu — na UTP 30 cm posoudit; jinak 74LVC / TXU / SN74LVC8T245 / I²S line driver |

### 1.4 Driver 4× piezo

Na HAT **budič čtyř** pasivních piezo (PS1240 nebo ekvivalent, rezonance ~4 kHz). Firmware je **jeden** software H-můstek: GP6 a GP7, stejný PWM slice, kanál B invertovaný, nosná ~4 kHz / FHSS.

Čtyři elementy **paralelně** za tím budičem. Ne čtyři nezávislé GPIO kanály (na to není firmware ani piny).

GPIO netahej přímo na čtyři PS1240 — na HAT MOSFET H-můstek / dual gate driver (TC4427/4428) / DRV8837 nebo ekvivalent, napájení z 3V3 (nebo VSYS, pokud návrhář zdůvodní hlasitost). Krátké vývody, ESD, případně sériové R.

### 1.5 6× adresovatelná RGB LED

Jeden pixel WS2812B / SK6812 u každého mikrofonu (indikace detekovaného směru). Data po RJ45 (`LED_DIN`, 3,3 V). HAT má šest samostatných GPIO, ne daisy-chain.

### 1.6 I²C periferie na HAT

Dvě funkce, dva byty — **nesdílet** s I²S (GP8/GP9) ani s piezem (GP6/GP7).

| Bus | GPIO | Zařízení | Účel |
|---|---|---|---|
| I²C1 | GP2 SDA, GP3 SCL | environmentální senzor | **tlak + teplota + vlhkost** → rychlost zvuku pro DOA |
| I²C0 | GP4 SDA, GP5 SCL | powermanagement | napětí / proud harvestu a VSYS (Plus 2 má Qw/ST na stejném I²C0) |

**Environment (návrh k výběru, funkce je daná):**

Firmware dnes čte **DPS310** na GP2/GP3 (0x77 / 0x76), vlhkost jen jako `BARO RH` default 50 %. Má se měřit.

1. **Doporučeno kvůli firmware:** DPS310 @ 0x77 + Sensirion SHT40/SHT45 @ 0x44 na stejném I²C1. Tlak a teplota beze změny; RH nahradí odhad.
2. **Jeden čip:** Bosch BME280 (P+T+H) @ **0x76** na I²C1. Vyžaduje nový firmware driver; neosazovat zároveň s DPS310 (kolize 0x76/0x77).

Otvory / vent v pouzdru k senzoru. Ne do proudu transformátoru.

**Powermanagement (návrh k výběru):**

INA219 (1× VSYS) nebo **INA3221** (až 3 kanály: harvest, 3V3, VSYS). Adresa mimo 0x76/0x77 a mimo SHT 0x44. Shunt podle změřeného split-core; pokud není V/I, široký rozsah a DNP varianty.

---

## 2. Omezení z firmware a fyziky

Tyto body měnit jen vědomě (PIO, USB audio, DOA, piezo PHY).

| # | Omezení | Proč |
|---|---|---|
| F1 | 6× digitální MEMS **I²S**, ne PDM | firmware PIO |
| F2 | Jeden společný `SCK` + `WS` z MCU, každý mikrofon vlastní `SD` | 100% sync |
| F3 | 48 kHz, I²S 24 bit, 64 SCK/frame → **SCK = 3,072 MHz**; rezerva návrhu 192 kHz | USB UAC2 + T5848 HQ okno 2,0–3,7 MHz |
| F4 | Pinout §5 držet (Pico header) | `wiring_and_bom.md` |
| F5 | GP23/24/25/29 na W = Wi-Fi — nepoužít | RM2/CYW43 |
| F6 | Environment na I²C1 GP2/GP3; firmware dnes DPS310 0x77 | `c(T,p,RH)` pro TDOA |
| F7 | Piezo PHY GP6/GP7, 4 elementy paralelně za H-můstkem | `buzzer.c` |
| F8 | Hobby / 230 V lab, ne VN, ne SPDIF | rozsah zakázky |
| F9 | Cena kusu, JLC/LCSC | celý projekt |
| F10 | **6× RJ45**, 1 mikrofon + 1 RGB LED na kabel | prostor kostky + indikace směru |
| F11 | Compute = Pimoroni Plus 2 / Plus 2 W + HAT | tato revize |

53 × 21 × 40 mm platí pro **sloupec Pico**. HAT s 6× RJ45 je větší; tiskař upraví nosný prstenec podle STEP.

---

## 3. Sada desek

Power se nemíchá s I²S. Compute je vždy Pico modul + HAT.

```
        ┌─────────────────────────────────────┐
        │  POWER PCB  (volný tvar, u split-core)
        │  split-core → usměrnění → TVS → VSYS
        └──────────────┬──────────────────────┘
                       │ silové (+ sense na I²C HAT)
        ┌──────────────▼──────────────────────┐
        │  HAT  (tato zakázka)                │
        │  6× RJ45, shiftery, 4× piezo driver │
        │  6× LED_DIN, I²C env + PM           │
        │     ┌──────────────┐                │
        │     │ Pico Plus 2  │  53 × 21 mm    │
        │     │ (+ W / RM2)  │                │
        │     └──────────────┘                │
        └──────────────┬──────────────────────┘
                       │ 6× UTP RJ45: I²S + 3V3 + LED_DIN
              ┌────┬───┼───┬───┬───┐
           sat1  sat2 sat3 sat4 sat5 sat6
```

### 3.1 HAT

- Uprostřed footprint Pico 53 × 21 mm, okolo **6× RJ45**.
- Výška stohu Pico+header+HAT: MCU sloupec ≤ 40 mm, USB-C a BOOT přístupné.
- 5 V na MEMS nikdy (na kabelu 3,3 V, 1,8 V jen LDO na satelitu).
- Piezo konektor / pájecí plošky × 4, nebo jeden 8pin, aby šly čtyři PS1240 ven z desky do pouzdra.
- I²C pull-upy 2,2–4,7 kΩ na 3V3, jednou na HAT (Qw/ST na Plus 2 už má pull-upy — nezdvojit naslepo).

### 3.2 Power PCB

Samostatná deska. Na HAT už není usměrnění ani nabíjení. Tři vstupy, jeden výstup 5 V na Pico VSYS a HAT (`J10`).

| Vstup | Dílek | Co z něj jde |
|---|---|---|
| Indukce | **YHDC SCT-013-000**, kleště na jeden izolovaný vodič obvodu 230 V / do 10 A | usměrněný sekundár, jen trickle a měření proudu. Na desku nepřijde 230 V |
| Slunce | malý panel, Voc 6–18 V (CN3791 je snižující MPPT, panel musí být výš než článek) | nabíjení 21700 |
| Baterie | 1× **21700** s ochranou článku, držák na desce | zdroj, když vedení a slunce nestačí |

Výstup: **BQ25895** (I²C, power-path, boost 5 V) na Pico a HAT. I²C na HAT (GP4/GP5): napětí a proud čtyř větví (panel, článek, harvest, výstup 5 V) přes **PAC1934**, teplota článku na TS pinu BQ25895, teploty panelu, kleští a výstupu přes NTC a **ADS1115**.

Split-core je **SCT-013-000** (100 A : 50 mA, bez vnitřního bočníku, dielektrikum jednotky kV, okno 13 mm). Ne SCT-013-010: ten má bočník uvnitř a je jen voltový senzor 10 A / 1 V. Při 10 A dává SCT-013-000 asi 5 mA, tedy jednotky miliwattů. HAT z něj sám nepojede. Na desce je zátěž 100 Ω ještě před pojistkou, ať vinutí nezůstane naprázdno.

Mimo rozsah: vlastní jádro, VN izolace, 22 kV, síť 230 V přivedená na desku.

### 3.3 Satelit mikrofonu × 6

Bajonet v pouzdru, RJ45 **piny k zemi**.

| Položka | Výchozí návrh |
|---|---|
| MEMS | T5848 bottom port 3,50 × 2,65 × 0,98 mm (nebo vybraný ekvivalent) |
| VDD | 1,8 V, 100 nF X7R u VDD |
| LR / SEL | GND (firmware čte levý slot) |
| SD | 100 kΩ pulldown |
| WAKE, THSEL | NC |
| Port | TDK land pattern; nic před membránou |
| Déšť | PTFE později, není SMT rev. 1 |
| Napájení z UTP | **3,3 V** (LED + vstup LDO) |
| LDO | 3,3 V → 1,8 V pro T5848 |
| LED | WS2812B / SK6812 @ 3,3 V, jeden pixel, `DIN` z UTP |
| Konektor | **RJ45 8P8C**, piny k zemi, mapa §4.2 |

Žádný rozbočovač 3+3. Žádný `DOUT` zpět na HAT.

---

## 4. I²S a UTP

### 4.1 Topologie hodin

```
RP2350 PIO master (Pico Plus 2)
    GP9  SCK ──► buffer na HAT ──┬── RJ45-1 · 2 · 3 · 4 · 5 · 6
    GP8  WS  ──► buffer na HAT ──┘
GP16 SD1  ◄── RJ45-1  mic1     GP10 LED1 ──► RJ45-1
GP18 SD2  ◄── RJ45-2  mic2     GP11 LED2 ──► RJ45-2
GP20 SD3  ◄── RJ45-3  mic3     GP12 LED3 ──► RJ45-3
GP26 SD4  ◄── RJ45-4  mic4     GP13 LED4 ──► RJ45-4
GP27 SD5  ◄── RJ45-5  mic5     GP14 LED5 ──► RJ45-5
GP28 SD6  ◄── RJ45-6  mic6     GP22 LED6 ──► RJ45-6
```

SCK a WS se větví **na HAT** do šesti jacků (stejná délka). MCU master. Buffer SCK/WS na 6 zátěží (klidně 2× budič po třech).

### 4.2 Mapování UTP — 1 mic = 1× 8P8C (zmrazené)

Není to Ethernet; barvy T568B kvůli patch kabelu.

| Pár T568B | Piny | Signál | Poznámka |
|---|---|---|---|
| 2 oranžový | 1, 2 | SCK , GND | hodinový pár, 1,8 V I²S |
| 3 zelený | 3, 6 | WS , GND | word select, 1,8 V I²S |
| 1 modrý | 4, 5 | SD , GND | data mikrofonu → MCU, 1,8 V |
| 4 hnědý | 7, 8 | **3V3** , **LED_DIN** | napájení satelitu + WS2812; 1,8 V jen z LDO na satelitu |

LED GND bere z párů 1–3. `LED_DIN` je 3,3 V (SK6812 / WS2812B-V5). T5848 na 3,3 V z páru 4 **nepřipojovat**.

Stejná tabulka na silkscreenu u každého jacku (`MIC1` … `MIC6`).

### 4.3 Integrita a EMI

230 V indukce, harvest, I²S na UTP. Proto buffer, ne holé GPIO.

Na každém I²S ven z HAT (k posouzení, ne dogma):

1. sériový 22–33 Ω u budiče,
2. ESD TVS,
3. CM choke na párech SCK a WS,
4. stínění UTP na GND **jen na HAT**.

Doporučený stackup HAT: 4L SIG / GND / napájení / SIG.

---

## 5. GPIO (Pico header — držet)

Z [wiring_and_bom.md](https://github.com/fedurca/het68/blob/main/wiring_and_bom.md). WS2812 ve firmware zatím **není** — šest `LED_DIN` se sem zapíše.

| Funkce | GPIO | Směr | Poznámka |
|---|---|---|---|
| Debug UART TX | GP0 | out | UART0, 115200 |
| Debug UART RX | GP1 | in | |
| Env SDA | GP2 | I²C1 | DPS310 / BME280 / SHT na stejném bytu |
| Env SCL | GP3 | I²C1 | |
| PM SDA | GP4 | I²C0 | INA; Qw/ST na Plus 2 |
| PM SCL | GP5 | I²C0 | |
| Piezo A | GP6 | out | PWM H-můstek → budič 4× PS1240 |
| Piezo B | GP7 | out | totéž, invertovaný kanál |
| I²S WS | GP8 | out | společné |
| I²S SCK | GP9 | out | společné, 3,072 MHz |
| LED1 DIN (mic1 / TFC) | GP10 | out | RJ45-1 pin 8 |
| LED2 DIN | GP11 | out | RJ45-2 |
| LED3 DIN | GP12 | out | RJ45-3 |
| LED4 DIN | GP13 | out | RJ45-4 |
| LED5 DIN | GP14 | out | RJ45-5 |
| (volné) | GP15, 17, 19, 21 | — | nenechat viset; test pad / DNP |
| Mic 1 SD | GP16 | in | TFC sever +35°, USB ch 1 |
| Mic 2 SD | GP18 | in | TRR 120° +35° |
| Mic 3 SD | GP20 | in | TSL 240° +35° |
| LED6 DIN | GP22 | out | RJ45-6 |
| Wi-Fi (W) | GP23, 24, 25, 29 | — | nesahat |
| Mic 4 SD | GP26 | in | BC 180° −35° |
| Mic 5 SD | GP27 | in | RLC 300° −35° |
| Mic 6 SD | GP28 | in | RRC 60° −35° |
| PSRAM CS | GP47 | — | na modulu Plus 2, ne na HAT |
| BOOT | GP45 | — | Plus 2 W |

Návrhář nepíše firmware. GPIO mimo tuto tabulku jen po zápisu sem.

---

## 6. Komponenty na HAT (výchozí návrh)

- Level shift / UTP budič — TXS0108E **nebo** to, co obstojí §1.3.
- 3,3 V na pár 4 každého RJ45; **1,8 V LDO na každém satelitu**.
- ESD na off-board I²S, RJ45 a piezo.
- Piezo H-můstek viz §1.4.
- I²C viz §1.6.

Nepoužívat 5 V na MEMS.

### 6.1 Mikrofony — podklad k výběru

| | ICS-43434 (prototyp) | T5848 (návrh) | DMM-4026-B-I2S-R | Sensibel SBM140B |
|---|---|---|---|---|
| Stav | NRND | navrhováno | alternativa | top, nesežene se |
| VDD | 1,65–3,63 V (teď 3,3 V) | 1,62–1,98 V | 1,5–3,6 V | 1,8 V třída |
| SNR | 65 dBA | 68 dBA | 64 dBA | vyšší |
| AOP | 120 dB | 133 dB | — | — |
| Proud HQ | 490 µA | 310 µA | 820–1000 µA | — |

Priorita objednatele: **cena/ks → SNR → I²S**.

---

## 7. Mechanika pouzdra (vazba, ne lock-in)

Požadavky tisku (ASA/PETG, UV, zelená):

1. Pico v hranolu **53 × 21 × 40 mm**.
2. HAT s **6× RJ45** mimo ten hranol — radiálně k stěnám, jack `MIC1` = sever.
3. Bajonet mikrofonů, RJ45 **piny k zemi**.
4. LED ve stejném bajonetu jako MEMS (otvor / čirý tisk).
5. Čtyři pieza v pouzdru, ne na membráně MEMS.

MEMS ±1 mm (1 vzorek TDOA ≈ 7,15 mm).

---

## 8. Výroba a cena

| Položka | Požadavek |
|---|---|
| Prototyp | pár HAT + power + 6 satelitů; Pico Plus 2 se kupuje hotový |
| CAD | KiCad 8+ (plugin jlcpcb-tools na BOM/CPL) |
| Gerber | RS-274X + drill; stejný balík na JLCPCB i na tisk v EU (printed.cz) |
| Výrobce | JLC SMT + LCSC (Basic přednostně před Extended); nebo EU tisk + osazení |
| Vrstvy | HAT 4L; satelit 2L; power 2L |
| Povrch | HASL; satelit ENIG kvůli MEMS |
| BOM | LCSC C-code, DNP, orientační cena @10 a @100 ks (bez ceny samotného Pico) |

Počet RJ45 je daný (6). Volba jacku, shifteru, piezo budiče a env čipu je součást kusovníku. Kompletní výkresová dokumentace je podmínkou odevzdání.

---

## 9. Dodávky od návrháře

1. Krátké zhodnocení (1–2 strany): tvar HAT, shifter vs. buffer, env čip, piezo budič, INA.
2. Schéma PDF + zdroj (KiCad 8+ / Altium) — **HAT + satelit + power**.
3. Layout + Gerber + drill + IPC-356.
4. BOM LCSC, DNP, cena.
5. CPL + STEP osazené desky (HAT se zasunutým Plus 2).
6. Pinout konektorů = silkscreen (T568B!).
7. Stackup, I²S pravidla.
8. JLC nastavení.

---

## 10. Mimo tuto zakázku

- Vlastní MCU deska, SX1262, MeshCore RF, IPEX / pigtaily.
- VN izolace, 22 kV, certifikace, RF certifikace 868 / 2,4 GHz.
- SPDIF / optika (UTP ≤ 0,3 m).
- PTFE a déšť (objednatel).
- 3D model pouzdra (tiskař); STEP desky ano.
- Firmware (objednatel) — vč. driveru SHT / BME a WS2812.

---

## 11. Otázky, které má zhodnocení uzavřít

1. Jaký 8P8C jack (SMT/THT, orientace), aby šest kusů sedělo na prstenec kostky?
2. T5848 + TXS0108E, nebo jiný MEMS + line driver?
3. Tvar HAT vs. tisk pouzdra (STEP), strana osazení Pico.
4. DPS310+SHT4x, nebo BME280?
5. Piezo budič: jaký čip, napájení 3V3 vs VSYS?
6. Na HAT je INA3221 (VSYS a 3V3). Split-core a V/I/T vstupů jsou na power desce, §3.2.
7. Power PCB: panel, 21700 a indukce, §3.2. USB-C na nakreslené desce je laboratorní vstup.
8. Plus 2, nebo Plus 2 W (BLE)? HAT musí sedět na oba.

---

## 12. Podklady (bez jmen)

Technický obsah zadání pochází z provozu prototypu, z firmware het68 (`wiring_and_bom.md`, `buzzer.c`, `dps310.c`, pinout, 48 kHz/24 bit) a ze zmrazeného HAT v §1. Osoby, kontakty, nabídky a pracnosti v tomto dokumentu **nejsou**.

Konec zadání v1.5.0.
