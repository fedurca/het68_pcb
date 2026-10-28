# het68 — zadání návrhu a výroby PCB

**Projekt:** akustická detekce dronů (het68)
**Firmware a mechanika:** [github.com/fedurca/het68](https://github.com/fedurca/het68)
**Tento dokument:** [github.com/fedurca/het68_pcb](https://github.com/fedurca/het68_pcb)
**Stav:** proof-of-concept běží; toto je zadání další hardwarové iterace
**Verze zadání:** 1.2.0 · 28. 10. 2026 (Europe/Prague)  
**Git tag:** `v1.2.0`
**Jazyk:** čeština (k odeslání návrháři)

Dokument vychází z provozu prototypu, z firmware v `fedurca/het68`, z vazby na pouzdro a z **předpokladů objednatele v §1**.

**Jak číst tento brief**

| Sekce | Váha |
|---|---|
| §1.1 / F10 | **zmrazené** — 6× RJ45, jeden kabel = jeden mikrofon + jedna RGB LED. Počet jacků se neposuzuje. |
| §1 (kromě 1.1) | **návrh k posouzení** — ne tvrdé požadavky. Návrhář smí navrhnout jinak, musí zdůvodnit (místo, EMI, cena, GPIO). |
| §2 Omezení z běžícího firmware / fyziky | měnit jen s vědomím, že padne firmware nebo akustika |
| §3+ | technický podklad k těm dvěma vrstvám |

---

## 0. Účel zařízení

Šestinásobné I²S mikrofonní pole na kostce stojící na vrcholu. RP2350 počítá směr (DOA / SRP-PHAT), klasifikuje dron, posílá 6kanálové USB audio 48 kHz / 24 bit, skenuje BLE OpenDroneID a mezi nody si povídá akustickým chirpem přes piezo.

Cíl další desky: **dostat elektroniku dovnitř konstrukce**, pryč od Grove Shield bastlu 56 × 56 mm, za **minimální cenu kusu** v sérii. Nasazení u vedení: nejdřív hobby lab na **230 V** venkovním vedení, indukční napájení split-core transformátorem. 22 kV a vysokonapěťové zkoušky **nejsou** součástí této zakázky.

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

Poloměr pole (střed → mikrofon) = `hrana / 2`. Firmware default hrana **128 mm** (poloměr 64 mm). Ve starší geometrii 384 mm je poloměr **192 mm** — údaj „finální model ~192 mm“ z dřívějších konverzací. I²S počítat na **UTP do ~30 cm** (ověřeno 25 cm na současném kabelu).

---

## 1. Předpoklady objednatele — k posouzení

Kromě §1.1 (počet RJ45) je toto záměr, ne kusovník. Návrhář má **zhodnotit proveditelnost, cenu a rizika** a vrátit doporučení (klidně s DNP / dvěma layouty).

### 1.1 Mikrofony po UTP — **6× RJ45 (požadavek)**

Každý mikrofon má **vlastní** kroucený CAT5e/CAT6 patch a **vlastní 8P8C**. Ne 2× jack se třemi mikrofony na kabelu, ne daisy-chain mezi satelity.

Důvody:

- **Prostor:** šest kabelů jde radiálně k šesti stěnám kostky, každý bajonet samostatně.
- **LED směru:** na stejném RJ45 jede i data adresovatelné RGB (WS2812 / SK6812) u mikrofonu. Bez zpětného `DOUT` v osmi vodičích má každý jack **vlastní `LED_DIN`**.

Délka řádově 20–30 cm. Stínění UTP na GND jen na compute.

Standardní 8P8C má šířku ~15–16 mm. **Šest jacků se na Pico 53 × 21 mm nevejde.** Pico modul zůstane 53 × 21; deska s konektory je větší (prstenec / šestiúhelník / dvě řady), jacky míří k příslušným stěnám. Dutina 53 × 21 × 40 mm platí jen pro MCU, ne pro I/O.

K posouzení zůstává: SMT vs THT jack, magjack vs holý 8P8C, vertikál vs pravoúhlý. Ne počet jacků.

Flex jako RPi CAM1 je záloha, ne výchozí.

### 1.2 Nové mikrofony + převodníky úrovní

Opustit ICS-43434 (NRND, prototyp na 3,3 V). Nová generace MEMS + obvod, který zároveň **posune úroveň** a **budí kabel**.

Výchozí návrh k posouzení:

| Role | Návrh | Proč jen návrh |
|---|---|---|
| MEMS | TDK InvenSense **T5848** (I²S, VDD 1,62–1,98 V, SNR 68 dBA, ~310 µA) | kandidát z výběru; alternativa DMM-4026-B-I2S-R; Sensibel SBM140B je lepší, zatím se nesežene |
| Převod / budič | **TXS0108E** (8 bit = SCK+WS+6×SD, 1,8 ⇔ 3,3 V) | kandidát z výběru; alternativa I²S line driver / 74LVC, který umí i level shift a delší linku. TXS má one-shot a nesnáší velkou kapacitu — na UTP 30 cm to **musí návrhář posoudit**, ne slepě osadit |

Pokud TXS na UTP nestojí: unidirekční 74LVC / TXU / SN74LVC8T245 / dedicated I²S line driver. Stejně tak jiný I²S MEMS ve stejném footprintu, pokud vyhraje cena/SNR.

### 1.3 Dvě varianty compute — vybrat po zhodnocení, ne obě vyrábět naslepo

Obě mají **8 MB PSRAM** (echo cancel + mezilehlá sync). Ne 16 MB PSRAM — to byla záměna s 16 MB flash.

**Varianta A — Pimoroni Pico Plus 2 (8 MB PSRAM) jako modul**

- Reference: [Pico Plus 2](https://shop.pimoroni.com/products/pimoroni-pico-plus-2) (bez rádia) nebo [Pico Plus 2 W](https://shop.pimoroni.com/products/pimoroni-pico-plus-2-w) (RM2 = Wi-Fi + BT, **anténa na modulu, bez IPEX**).
- K tomu vlastní shield: UTP jacky, buffery/shiftery, DPS310, piezo, napájecí vstup.
- Plus 2 W stačí na dnešní BLE OpenDroneID, ale anténa uvnitř kovem/uhlíkem stíněného pouzdra u vedení bude slabá — to je důvod varianty B.
- Standardní Pico 2 / Pico 2 W **nemá** 8 MB PSRAM, na A se nehodí.

**Varianta B — vlastní deska: BT na IPEX + SX126 pro MeshCore**

- RP2350B + 16 MB flash + 8 MB PSRAM na jedné desce (elektricky ~ Plus 2, ne mechanicky XL 77 mm).
- **IPEX (U.FL) na 2,4 GHz** pro Bluetooth (CYW43439 / RM2 s externí anténou místo PCB antény). OpenDroneID BLE a případné Wi-Fi ven z pouzdra kabelem.
- **Semtech SX1262** (EU **868 MHz**, MeshCore default ~869,618 MHz) jako mesh místo / vedle akustického chirpu a Wi-Fi sync. Referenční moduly: Wio-SX1262, Ebyte E22-900M22S, nebo čip + matching; MeshCore už SX1262 umí (`USE_SX1262`, RadioLib).
- SX126 má **vlastní IPEX 868 MHz** — 2,4 GHz a 868 MHz se na jeden konektor bez diplexeru nesdílí. Posoudit **dva IPEX** (BT + LoRa) vs. jen LoRa IPEX a BT onboard.
- Napájecí/PMIC část dál **zvlášť** (indukční rušení).

Posoudit mimo jiné: místo vs. 53 × 21 × 40 mm dutina, koexistence CYW43439 SPI + SX126 SPI + 6× I²S DMA, spotřeba vs. split-core, certifikace ISM 868, zda MeshCore na RP2350 (upstream varianty jsou spíš RP2040 — firmware práce objednatele, deska má jen vyvést čip).

```
  Varianta A                         Varianta B
  ┌──────────────┐                   ┌──────────────────┐
  │ Pico Plus 2  │                   │ RP2350B+PSRAM    │
  │ (+ W / RM2)  │                   │ CYW43 → IPEX 2.4 │
  └──────┬───────┘                   │ SX1262 → IPEX 868│
         │ shield                    └────────┬─────────┘
  ┌──────▼───────┐                   ┌────────▼─────────┐
  │ UTP + shift  │                   │ UTP + shift      │
  │ DPS310 piezo │                   │ DPS310 piezo     │
  └──────────────┘                   └──────────────────┘
```

---

## 2. Omezení z firmware a fyziky

Tyto body měnit jen vědomě (PIO, USB audio, DOA).

| # | Omezení | Proč |
|---|---|---|
| F1 | 6× digitální MEMS **I²S**, ne PDM (PDM jen výhled) | firmware PIO |
| F2 | Jeden společný `SCK` + `WS` z MCU, každý mikrofon vlastní `SD` | 100% sync |
| F3 | 48 kHz, I²S 24 bit, 64 SCK/frame → **SCK = 3,072 MHz**; rezerva návrhu 192 kHz | USB UAC2 + T5848 HQ okno 2,0–3,7 MHz |
| F4 | Pinout I²S/periferií v §5 držet u varianty A (Pico header). U B lze přemapovat, ale stojí to firmware. | `wiring_and_bom.md` |
| F5 | GP23/24/25/29 na W deskách = Wi-Fi — nepoužít na I²S ani SX126 | RM2/CYW43 |
| F6 | DPS310 (nebo kompatibil) na I²C, firmware dnes GP2/GP3 | rychlost zvuku pro DOA |
| F7 | Piezo dnes GP6/GP7 (1× PS1240 H-můstek); 4 kusy jsou přání z konverzací | akustický node link |
| F8 | Hobby / 230 V lab, ne VN zkoušky, ne SPDIF | rozsah zakázky |
| F9 | Cena kusu, JLC/LCSC | celý projekt |
| F10 | **6× RJ45**, 1 mikrofon + 1 RGB LED na kabel | prostor kostky + indikace směru |

53 × 21 × 40 mm platí pro **Pico / MCU**. Deska s 6× RJ45 je záměrně větší; tiskař upraví dutinu / nosný prstenec podle STEP.

---

## 3. Sada desek

Power se nemíchá s I²S. Počet a tvar compute desek vypadne ze zhodnocení A vs. B.

```
        ┌─────────────────────────────────────┐
        │  POWER PCB  (volný tvar, u split-core)
        │  split-core → usměrnění → TVS → VSYS
        └──────────────┬──────────────────────┘
                       │ silové + I2C sense
        ┌──────────────▼──────────────────────┐
        │  COMPUTE  (A: Pico+shield / B: SoM) │
        │  8 MB PSRAM, buffery, UTP, senzory  │
        │  B navíc: IPEX 2.4 + SX126 + IPEX 868│
        └──────────────┬──────────────────────┘
                       │ 6× UTP RJ45: I²S + 3V3 + LED_DIN
              ┌────┬───┼───┬───┬───┐
           sat1  sat2 sat3 sat4 sat5 sat6
```

### 3.1 Varianta A — shield na Pimoroni Plus 2

Protikus k Pimoroni Plus 2: uprostřed Pico 53 × 21 mm, okolo **6× RJ45** (ne 56 × 56 Grove a ne 53 × 21).

- Header stoh Pico; výška MCU části ≤ 40 mm.
- Šest jacků, shiftery, DPS310, piezo, VSYS. Jacky směřují k mic 1–6.
- 5 V na MEMS nikdy (na kabelu 3,3 V, 1,8 V jen lokální LDO na satelitu).
- SX126 na A nepočítat.

### 3.2 Varianta B — vlastní SoM

RP2350B, W25Q128, APS6404L-3SQR-ZR (PSRAM CS jako u Pimoroni na GP47, pokud se pin zachová), USB-C, CYW43439/RM2 → **IPEX 2,4 GHz**, SX1262 → **IPEX 868 MHz**.

Pimoroni Pico LiPo 2 XL W (77 × 21 mm) je jen elektrická reference MCU+PSRAM, ne tvar.

**SX1262 — co posoudit**

| Položka | Návrh k posouzení |
|---|---|
| Čip | SX1262 HF 868 MHz, TCXO, DIO2 jako RF switch, DIO3 = 1,8 V TCXO (MeshCore `SX126X_DIO3_TCXO_VOLTAGE=1.8`) |
| Výkon | 14–22 dBm; u vedení a 230 V lab držet se EU 868 limitů (návrhář nenařizuje ERP, jen footprint a PA) |
| SPI | vlastní SPI1, **ne** piny Waveshare RP2040-LoRa (DIO1=GP16, BUSY=GP18, MISO=GP24 — kolidují s I²S a Wi-Fi) |
| Návrh GPIO | viz §5.2 |
| Anténa | IPEX-1 + pigtail ven z pouzdra; 50 Ω, GND stínicí šití, keep-out |
| Koexistence | LoRa TX vs. MEMS / 3,072 MHz I²S — filtr na VCC rádia, vzdálenost IPEX od UTP jacků |

### 3.3 Power PCB

Samostatně, tvar volný.

- Vstup sekundár split-core, usměrnění, bulk, TVS podle 230 V lab, pojistka.
- Lab USB-C / 5 V, diodový OR s harvestem.
- VSYS 3,3–5,5 V na compute, stíněný kablík.
- I²C PMIC / INA219–3221 (firmware s nimi počítá jako s plánem).
- LC/CM na výstupu, ať 50 Hz a buck neleze do 1V8 mikrofonů.

Mimo rozsah: vlastní split-core, VN izolace, 22 kV.

### 3.4 Satelit mikrofonu × 6

Bajonet v pouzdru, řada pinů / RJ45 **směrem k zemi**.

| Položka | Výchozí návrh k posouzení |
|---|---|
| MEMS | T5848 bottom port 3,50 × 2,65 × 0,98 mm (nebo vybraný ekvivalent) |
| VDD | 1,8 V, 100 nF X7R u VDD |
| LR / SEL | GND (firmware čte levý slot) |
| SD | 100 kΩ pulldown |
| WAKE, THSEL | NC |
| Port | TDK land pattern; nic před membránou |
| Déšť | PTFE později, není SMT rev. 1 |
| Napájení z UTP | **3,3 V** (LED + vstup LDO) |
| LDO na satelitu | 3,3 V → 1,8 V pro T5848 |
| LED | WS2812B / SK6812 @ 3,3 V, jeden pixel, `DIN` z UTP (vlastní GPIO jacku) |
| Konektor | **RJ45 8P8C**, piny k zemi, mapa §4.2 |

Žádný rozbočovač 3+3. Žádný `DOUT` zpět na compute (není volný vodič) — proto 6× `LED_DIN`, ne jeden daisy-chain.

---

## 4. I²S a UTP

### 4.1 Topologie hodin

```
RP2350 PIO master
    GP9  SCK ──► buffer ──┬── RJ45-1 · 2 · 3 · 4 · 5 · 6   (stejný SCK)
    GP8  WS  ──► buffer ──┘
GP16 SD1  ◄── RJ45-1  mic1     GP10 LED1 ──► RJ45-1
GP18 SD2  ◄── RJ45-2  mic2     GP11 LED2 ──► RJ45-2
GP20 SD3  ◄── RJ45-3  mic3     GP12 LED3 ──► RJ45-3
GP26 SD4  ◄── RJ45-4  mic4     GP13 LED4 ──► RJ45-4
GP27 SD5  ◄── RJ45-5  mic5     GP14 LED5 ──► RJ45-5
GP28 SD6  ◄── RJ45-6  mic6     GP22 LED6 ──► RJ45-6
```

SCK a WS se **větví na compute** do šesti jacků (stejná délka cest). MCU master. SD ani LED se mezi satelity nedaisy-chainují. Buffer SCK/WS dimenzovat na 6 zátěží (klidně 2× budič po třech).

### 4.2 Mapování UTP — 1 mic = 1× 8P8C (zmrazené)

Platí pro všechny čtyři páry T568B. Není to Ethernet; barvy jen kvůli patch kabelu.

| Pár T568B | Piny | Signál | Poznámka |
|---|---|---|---|
| 2 oranžový | 1, 2 | SCK , GND | hodinový pár, 1,8 V I²S |
| 3 zelený | 3, 6 | WS , GND | word select, 1,8 V I²S |
| 1 modrý | 4, 5 | SD , GND | data mikrofonu → MCU, 1,8 V |
| 4 hnědý | 7, 8 | **3V3** , **LED_DIN** | napájení satelitu + WS2812; 1,8 V jen z LDO na satelitu |

LED GND bere z párů 1–3. `LED_DIN` je 3,3 V z MCU (SK6812 / WS2812B-V5 3,3 V). T5848 na 3,3 V z páru 4 **nepřipojovat**.

Stejná tabulka na silkscreenu u každého jacku (`MIC1` … `MIC6`).

### 4.3 Integrita a EMI

230 V indukce, harvest, I²S na UTP. Proto buffer, ne holé GPIO.

Na každém I²S ven z compute (k posouzení, ne dogma):

1. sériový 22–33 Ω u budiče,
2. ESD TVS,
3. CM choke na párech SCK a WS,
4. stínění UTP na GND **jen na compute**.

Doporučený stackup compute: 4L SIG / GND / napájení / SIG.

---

## 5. GPIO

### 5.1 Stávající firmware (varianta A — držet)

Z [wiring_and_bom.md](https://github.com/fedurca/het68/blob/main/wiring_and_bom.md).

| Funkce | GPIO | Směr | Poznámka |
|---|---|---|---|
| Debug UART TX | GP0 | out | UART0, 115200 |
| Debug UART RX | GP1 | in | |
| DPS310 SDA | GP2 | I²C1 | |
| DPS310 SCL | GP3 | I²C1 | |
| Qw/ST SDA | GP4 | I²C0 | PMIC/INA sem, ne na GP8/9 |
| Qw/ST SCL | GP5 | I²C0 | |
| Piezo A | GP6 | out | SW H-můstek |
| Piezo B | GP7 | out | |
| I²S WS | GP8 | out | společné |
| I²S SCK | GP9 | out | společné, 3,072 MHz |
| Mic 1 SD | GP16 | in | TFC sever +35°, USB ch 1 |
| Mic 2 SD | GP18 | in | TRR 120° +35° |
| Mic 3 SD | GP20 | in | TSL 240° +35° |
| Mic 4 SD | GP26 | in | BC 180° −35° |
| Mic 5 SD | GP27 | in | RLC 300° −35° |
| Mic 6 SD | GP28 | in | RRC 60° −35° |
| Wi-Fi (W) | GP23, 24, 25, 29 | — | nesahat |
| PSRAM CS | GP47 | — | Plus 2 / B |
| BOOT | GP45 | — | Plus 2 W |

WS2812 ve firmware **není**. Šest `LED_DIN` je návrh k zápisu sem.

| Funkce | GPIO | Poznámka |
|---|---|---|
| LED1 DIN (mic1 / TFC) | GP10 | 3,3 V, RJ45-1 pin 8 |
| LED2 DIN | GP11 | RJ45-2 |
| LED3 DIN | GP12 | RJ45-3 |
| LED4 DIN | GP13 | RJ45-4 |
| LED5 DIN | GP14 | RJ45-5 |
| LED6 DIN | GP22 | RJ45-6 |

### 5.2 Varianta B — SX126 (k posouzení)

GP10–14 a GP22 žerou LED. SX126 proto **ne** na ně a **ne** na Waveshare (GP16/18/24). Na Plus 2 headeru zbývá GP15, 17, 19, 21 — na plné SPI+IRQ+BUSY+RST to nestačí. U B vzít **extra GPIO RP2350B** (mimo 40pin Pico). Návrh v `PINOUT.csv`: SCK GP30, MOSI GP31, MISO GP32, NSS GP33, DIO1 GP34, BUSY GP35, NRESET GP36, RXEN GP37.

Piezo: 4× paralelně na GP6/GP7.

---

## 6. Komponenty na compute (výchozí návrh)

- DPS310 nebo SPL06, adresa 0x77.
- Level shift / UTP budič — TXS0108E **nebo** to, co obstojí §1.2 (I²S na kabelu 1,8 V).
- 3,3 V na pár 4 každého RJ45; **1,8 V LDO na každém satelitu**, 100 nF u MEMS.
- ESD na off-board I²S a RJ45.
- Varianta B: CYW43/RM2 + IPEX 2,4 GHz; SX1262 + IPEX 868 MHz; π-matching dle datasheetu modulu.

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

1. MCU (Pico) v hranolu **53 × 21 × 40 mm**.
2. I/O deska s **6× RJ45** mimo ten hranol — radiálně k stěnám, jack `MIC1` = sever.
3. Bajonet mikrofonů, RJ45 **piny k zemi**.
4. LED ve stejném bajonetu jako MEMS (otvor / čirý tisk).

MEMS ±1 mm (1 vzorek TDOA ≈ 7,15 mm). IPEX pigtaily ven, antény ne uvnitř u transformátoru.

---

## 8. Výroba a cena

| Položka | Požadavek |
|---|---|
| Prototyp | po výběru A/B: pár compute + power + 6 satelitů na kus |
| CAD | KiCad 8+ (plugin jlcpcb-tools na BOM/CPL) |
| Gerber | RS-274X + drill; stejný balík na JLCPCB i na tisk v EU (printed.cz) |
| Výrobce | JLC SMT + LCSC (Basic přednostně před Extended); nebo EU tisk desek + ruční/SMT osazení |
| Vrstvy | compute 4L; satelit 2L; power 2L |
| Povrch | HASL; satelit ENIG kvůli MEMS |
| BOM | LCSC C-code, DNP, orientační cena @10 a @100 ks |

Počet RJ45 je daný (6). Zhodnocení A vs. B a volba jacku (SMT/THT) je součást kusovníku. Kompletní výkresová dokumentace je podmínkou odevzdání.

---

## 9. Dodávky od návrháře

1. **Zhodnocení §1** (1–2 strany): tvar desky pro 6× RJ45, shifter vs. buffer, A vs. B, dva IPEX. Doporučení jedné cesty.
2. Schéma PDF + zdroj (KiCad 8+ / Altium).
3. Layout + Gerber + drill + IPC-356.
4. BOM LCSC, DNP, cena.
5. CPL + STEP osazené desky.
6. Pinout konektorů = silkscreen (T568B mapování!).
7. Stackup, I²S pravidla, u B: RF keep-out.
8. JLC nastavení.

Návrhář nepíše firmware. GPIO mimo §5.1 jen po zápisu sem.

---

## 10. Mimo tuto zakázku

- VN izolace, 22 kV, certifikace.
- SPDIF / optika (úvaha pro linky >5 m — tady UTP ≤ 0,3 m).
- PTFE a déšť (objednatel).
- 3D model pouzdra (tiskař); STEP desky ano.
- Port MeshCore na RP2350 (objednatel); deska jen vyvede SX1262.
- RF certifikace 868 / 2,4 GHz.

---

## 11. Otázky, které má zhodnocení uzavřít

1. Varianta **A** (Plus 2 / Plus 2 W + I/O deska) nebo **B** (vlastní + IPEX BT + SX126)?
2. Jaký 8P8C jack (SMT/THT, orientace), aby šest kusů sedělo na prstenec kostky?
3. T5848 + TXS0108E, nebo jiný MEMS + line driver?
4. Tvar I/O desky vs. tisk pouzdra (STEP).
5. Dva IPEX, nebo LoRa IPEX a BT nechat na modulu?
6. Čtyři pieza paralelně na GP6/GP7?
7. Je změřený split-core (V, I)? Jinak široký vstup na Power PCB.
8. Power PCB: jen harvest + USB, nebo i LiPo?

---

## 12. Podklady (bez jmen)

Technický obsah zadání pochází z provozu prototypu, z firmware het68 (`wiring_and_bom.md`, pinout, 48 kHz/24 bit) a z předpokladů objednatele v §1. Osoby, kontakty, nabídky a pracnosti v tomto dokumentu **nejsou**.

Konec zadání v1.2.0.
