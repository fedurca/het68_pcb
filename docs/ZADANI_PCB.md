# het68 — zadání návrhu a výroby PCB

**Projekt:** akustická detekce dronů (het68)
**Firmware:** [github.com/fedurca/het68](https://github.com/fedurca/het68)
**Tento dokument:** [github.com/fedurca/het68_pcb](https://github.com/fedurca/het68_pcb)
**Verze zadání:** 4.0.0 · 29. 10. 2026 (Europe/Prague)
**Git tag:** `v4.0.0`
**Jazyk:** čeština

Dokument vychází z provozu prototypu, z firmware v `fedurca/het68` a z elektrického zmrazení v §1. Osoby, kontakty a termíny protistrany v něm **nejsou**.

**Jak číst tento brief**

| Sekce | Váha |
|---|---|
| §1 | **zmrazené** — nativní RP2350B, 6L Faraday Core, `J_MESH` na Heltec V3 (teď) / stamp (později), tři silové SKU, zákaz sítě na měď, LVDS k satelitům |
| §2 | omezení z firmware / fyziky — měnit jen s vědomím, že padne PIO, USB audio, DOA nebo piezo PHY |
| §3+ | technický podklad; výběr konkrétního MPN (LVDS, GDT, MPPT) je na kusovníku, ne na vymýšlení LCSC kódů |

v3.0.0 (Pico HAT 140 × 140 mm, 2L, printed.cz PROTOTYP) zůstává poslední vyrobitelnou Pico-revizí. HAT v `kicad/het68-hat` se v4 **nepřekresluje**.

---

## 0. Účel zařízení

Šestinásobné I²S mikrofonní pole. RP2350B počítá směr (DOA / SRP-PHAT), klasifikuje dron, posílá 6kanálové USB audio 48 kHz / 24 bit a mezi nody si povídá akustickým chirpem přes piezo. MeshCore žije na **samostatném rádiovém MCU**, takže uzel v síti zůstane, i když DSP spí.

Nasazení: NN (izolovaný vodič 230 V lab), VN (22 kV třída, Al obal) a VVN (110 kV sféra). **Na měď desky nepřijde 230 V, 22 kV ani 110 kV** — jen sekundár CT / Rogowski.

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

Poloměr pole (střed → mikrofon) = `hrana / 2`. Firmware default hrana **128 mm**. I²S na kabelu je teď **LVDS po STP**; PIO na MCU zůstává I²S.

---

## 1. Zmrazené zadání (v4.0.0)

### 1.1 Compute — nativní RP2350B na Core 6L

Ne Pico Plus 2, ne HAT. SoM je součást `kicad/het68-core`:

- RP2350B (QFN-80), 16 MB flash (WSON/SOIC, ne BGA), 8 MB PSRAM (USON/SOIC, ne BGA), USB-C.
- Doména `+3V3_DIG` / PSRAM / audio / LVDS se při spánku **vypíná** (EN LDO z `WAKE_DSP`).
- `+3V3_RF` a `+5V_ALWAYS` jsou vždyživé (MeshCore + později stamp).
- 0402 **jen** RF matching na Core. Jinak ≥ 0603. Žádné BGA.
- Piezo chirp (`DRV8837`, 4× PS1240) a env senzor (DPS310 + SHT40) zůstávají na Core.
- ADXL355 na SPI, 1,8 V, u středu / upevnění (eolické kmitání 10–100 Hz → ANC).

GPIO I²S / LED / piezo / I²C1 drží mapu z HAT rev E, aby PIO a `PIN_I2S_SD` v `fedurca/het68` padly na stejná čísla. Debug UART z GP0/GP1 jde pryč — na těch pinech je UART MeshCore. Konzole je USB CDC.

Mapa: [`docs/PINOUT.csv`](PINOUT.csv). HAT v3: [`docs/PINOUT_HAT_v3.csv`](PINOUT_HAT_v3.csv).

### 1.2 MeshCore — teď Heltec V3, později stamp

SX1262 **sám mesh nestaví**. Stack musí běžet, i když DSP spí.

**Teď:** konektor `J_MESH` 1×8 / 2,54 mm na **Heltec WiFi LoRa 32 V3, 868 MHz** (HTIT-WB32LA). Anténa na IPEX Heltecu.

**Později:** stejné sítě 1–6 na land pattern stampu třídy RAK4631 (DNP, neosazovat). Heltec se odpojí. U.FL stampu ven z Faraday (ESD na bulkhead, slot v plášti nebo puck). Chip anténa ve 110 kV Al sféře je mrtvá.

Stejná elektrická smlouva: `GND`, napájení rádia, UART 115200, `WAKE_DSP`, `DSP_AWAKE`, nRESET. SPI rádia zůstává na Heltecu/stampu, ne na RP2350.

Heltec napájet z pinu **5V** (`+5V_ALWAYS`), ne z hradlovaného `+3V3_DIG`. USB Heltecu jen na flash; po zapnutí 5 V z Core USB Heltecu odpojit (nespojovat dva 5V zdroje). Heltec je lab (~40–80 mA s OLED), ne harvest repeater.

`J_MESH` (silkscreen, 22 Ω v sérii na UART, ESD, GND vedle signálů), 3,3 V logika:

| Pin | Core | Heltec V3 | Směr |
|---|---|---|---|
| 1 | GND | J2-1 GND | — |
| 2 | `+5V_ALWAYS` | J2-2 5V | Core → Heltec |
| 3 | UART TX (GP0) | GPIO5 (J3-16) RX | Core → Heltec |
| 4 | UART RX (GP1) | GPIO6 (J3-17) TX | Heltec → Core |
| 5 | `WAKE_DSP` / EN `+3V3_DIG` | GPIO7 (J3-18) out | Heltec → Core |
| 6 | `DSP_AWAKE` (GP22) | GPIO4 (J3-15) in | Core → Heltec |
| 7 | Heltec RST (OD, NC default) | J2-7 RST | Core → Heltec |
| 8 | NC | — | rezerva stamp |

GPIO 43/44 (USB UART Heltecu) a 8–14 (SX1262) **nesahat**. MeshCore: oficiální `Heltec_lora32_v3`, `SERIAL_RX=5`, `SERIAL_TX=6` (ne USB console). GPS 47/48 ve variantě nechat volné.

Land stamp sdílí pin 1–6 s `J_MESH`. Pin 2 u stampu v sérii přejde na `+3V3_RF` (DNP 0 Ω).

#### Spánek DSP

Když uspíš MCU, které rádio ovládá, uzel ze sítě zmizí. Heltec (později stamp) visí na `+5V_ALWAYS` / `+3V3_RF`.

- UART 115200, framing MeshCore companion: host→radio `<` + u16le délka + payload, radio→host `>` + u16le + payload.
- `WAKE_DSP`: Heltec GPIO7 → EN LDO `+3V3_DIG` a `+1V8_AUDIO` (a tím RUN přes pull-up na 3V3).
- `DSP_AWAKE`: RP2350 GP22 → Heltec GPIO4 (UART jen když host žije).
- Stock `companion_radio` neforwarduje; `simple_repeater` nebudí hosta. Tenká role ve firmware: repeater, unicast / `WAKE` / poplach → GPIO7. Cizí flood DSP **nebudí**.

| Režim | Chování | Odběr rádia | Kdy |
|---|---|---|---|
| Repeater | SX1262 pořád RX, uzel routuje i bez DSP | Heltec desítky mA; nRF52 stamp ~8–15 mA | LTO nabitá; default VN/VVN |
| Sleepy list | bez forwardu; RxDutyCycle / CAD, DIO1 → případně WAKE_DSP | stovky µA až ~2 mA (stamp) | NN se slabým CT; přepnout při nízkém SOC |

SCT-013 při 10 A dává jednotky mW — **samotný harvest repeater neuživí**. Vždyživý MeshCore visí na LTO/LiFePO4 (+ panel). Minimální SOC pro repeater: **30 %** (firmware; pod tím sleepy list).

CZ MeshCore preset (ne nutně EU Narrow 869,618 MHz). Duty cycle repeateru **10 %** kvůli CEPT.

### 1.3 Žádné síťové napětí na měď

Zkrat 16 kA / 40 kA je na **primáru**. Na desku jde odražený sekundár (`I_pri / n`). U SCT-013-000 100 A : 50 mA je 16 kA → ~8 A, 40 kA → ~20 A. Crowbar a stopy se dimenzují na ten proud, ne na 16 kA v mědi.

Žádný odporový dělič 230 V, žádný kapacitní dělič na fázi, žádný VN vývod na plošný spoj.

### 1.4 Tři silové SKU, jeden interconnect

2 vrstvy, měď 70 µm, stíněný konektor k Core. Společný front-end: **jen sekundár** — GDT + TVS (5KP/15KP na sekundární napětí), LC, usměrňovač, crowbar, MPPT, LTO/LiFePO4, 5 V pro Core.

| SKU | Projekt | Měření | Mechanika (docs, ne na měď) |
|---|---|---|---|
| NN | `kicad/het68-pwr-nn` | time-multiplex CT: GPIO odpojí nabíječ a přepne přesný burden (harmonické) | AES, plovoucí stínění; **bez** děliče 230 V |
| VN | `kicad/het68-pwr-vn` | stejné multiplex CT, silnější GDT/TVS a crowbar | Al obal R ≥ 10 mm, ekvipotenciál fáze, Mu-metal přepážka 50 Hz |
| VVN | `kicad/het68-pwr-vvn` | saturační CT jen harvest + Rogowski + analogový integrátor na ADC Core | sféra R ≥ 50 mm, korónové prstence; žádný externí kabel |

PT1000 na svorce vodiče u všech SKU (2vodič na interconnect). Článek mrazuvzdorný **LiFePO4 / LTO** (21700 Li-ion z v3 končí).

Pinout: [`docs/INTERCONNECT_v4.md`](INTERCONNECT_v4.md). `+3V3_RF` drží LDO na silové desce, i když je DSP pryč.

### 1.5 Satelit — 6L Faraday, LVDS, T5848, 8× RGB

Evoluce `kicad/het68-sat`. Stejný Faraday stackup jako Core (L2/L3/L5 GND, L4 `+3V3` s ostrovem `+1V8` pod MEMS). T5848 1,8 V uprostřed, **8× SK6812** v kruhu (daisy-chain, pixel 0 = sever, poslední `DOUT` NC). LDO, **LVDS + CMC + TVS &lt; 1 pF + PPTC 0,5 A**. T568B jednovodičové I²S končí. Mapa: [`docs/PINOUT_SAT_v4.csv`](PINOUT_SAT_v4.csv).

Data mikrofonu na Core jdou **diferenciálně**: T5848 SD 1,8 V → TXS0104E → **SN65LVDS1** (Y/Z = `SD_P`/`SD_N`) → CMC → RJ45 4/5. Na Core pár přijímá **SN65LVDS32**. SCK/WS opačně: Core SN65LVDS047 → satelit SN65LVDS2.

110 kV satelity jako samostatné krabičky **nejsou**: MEMS uvnitř sféry, krátký vnitřní STP do stejných RJ45 na Core. Jacky zůstanou, kabely **neopustí** sféru.

### 1.6 Faraday stackup Core (6L)

| Vrstva | Funkce |
|---|---|
| L1 F.Cu | SMT, krátké spoje, GND výplň |
| L2 In1.Cu | souvislá GND, bez štěrbin pod I²S/SPI/RF |
| L3 In2.Cu | stripline: I²S/PDM 1,8 V, SPI (ADXL355, flash), UART, LVDS páry |
| L4 In3.Cu | split power: `+3V3_DIG` (hradlované), `+3V3_RF` / `+5V_ALWAYS` (vždyživé), `+1V8_AUDIO` (hradlované) |
| L5 In4.Cu | souvislá GND |
| L6 B.Cu | pomalé GPIO, GND výplň |

Stopy na L3 **nekřižují** mezeru ostrovů na L4. Via stitching GND L1–L2–L5–L6 po obvodu, rozteč 1,5–2 mm. Ostrov `+3V3_RF` **není** hradlovaný.

---

## 2. Omezení z firmware a fyziky

| # | Omezení | Proč |
|---|---|---|
| F1 | 6× digitální MEMS **I²S**, ne PDM | firmware PIO |
| F2 | Jeden společný `SCK` + `WS` z MCU, každý mikrofon vlastní `SD` | 100% sync |
| F3 | 48 kHz, I²S 24 bit, 64 SCK/frame → **SCK = 3,072 MHz**; rezerva 192 kHz | USB UAC2 + T5848 HQ 2,0–3,7 MHz |
| F4 | GPIO SD/LED/piezo/I²C1 jako HAT rev E (`PIN_I2S_SD`, `buzzer.c`) | firmware v `fedurca/het68` |
| F5 | GP0/GP1 = UART MeshCore, ne debug | companion 115200 |
| F6 | Environment na I²C1 GP2/GP3; DPS310 0x77 | `c(T,p,RH)` pro TDOA |
| F7 | Piezo PHY GP6/GP7, 4 elementy paralelně za H-můstkem | `buzzer.c` |
| F8 | DSP neovládá SX1262 | MeshCore na Heltecu/stampu |
| F9 | Na měď nejde síť | isolace, koróna, 16 kA je na primáru |
| F10 | **6× RJ45**, 1 mikrofon + 8× RGB v kruhu na satelitu | prostor kostky + indikace směru |
| F11 | Compute = nativní RP2350B | tato revize |

USB audio a I²S jen v `+3V3_DIG`. Po detekci RP2350 požádá o spánek; Heltec shodí EN.

---

## 3. Sada desek

```
        ┌─────────────────────────────────────┐
        │  SILOVÁ PCB  (NN / VN / VVN, výměnná)
        │  sekundár CT/Rogowski → GDT TVS LC crowbar
        │  MPPT + LTO/LiFePO4 → +5V_ALWAYS + +3V3_RF
        └──────────────┬──────────────────────┘
                       │ J_PWR stíněný 2×10
        ┌──────────────▼──────────────────────┐
        │  CORE 6L                            │
        │  RP2350B, flash, PSRAM, 6× RJ45 LVDS│
        │  piezo, env, ADXL355, J_MESH        │
        │     ┌──────────────┐                │
        │     │ Heltec V3    │  teď na J_MESH │
        │     │ (později stamp DNP)           │
        │     └──────────────┘                │
        └──────────────┬──────────────────────┘
                       │ 6× STP RJ45: LVDS + 3V3 + LED_DIN
              ┌────┬───┼───┬───┬───┐
           sat1  sat2 sat3 sat4 sat5 sat6
```

### 3.1 Core

- 6× RJ45 + nízko-kapacitní TVS (&lt; 1 pF), CMC, PPTC.
- 6× I²S k LVDS budičům (SCK, WS, 6× SD); sériové 22–33 Ω u čipu; 100 nF + 1 µF u každého 1,8 V pinu MEMS cesty (na satelitu).
- Interconnect viz [`INTERCONNECT_v4.md`](INTERCONNECT_v4.md): `+5V_ALWAYS`, GND, I²C0, ADC (proud, Rogowski, harvest, PT1000), GPIO burden-window, enable/PG.
- USB-C laboratoř na Core; nespojovat s 5 V Heltecu.

### 3.2 Silová deska

Tři vstupy, jeden výstup `+5V_ALWAYS` na Core a Heltec.

| Vstup | Dílek | Co z něj jde |
|---|---|---|
| Indukce | **YHDC SCT-013-000** (NN/VN) nebo saturační harvest CT (VVN) | usměrněný sekundár. Na desku nepřijde síť |
| Rogowski | jen VVN | analogový integrátor → ADC Core |
| Slunce | malý panel, Voc 6–18 V (CN3791 je snižující MPPT) | nabíjení LiFePO4/LTO |
| Baterie | 1× LiFePO4 nebo LTO, držák na desce | vždyživý MeshCore |

Na desce musí být:

1. **Burden** 100 Ω trvale na svorkách J1 (THT), ještě před LC a pojistkou.
2. **GDT** paralelně na sekundáru.
3. **LC filtr** před usměrňovačem.
4. **TVS** (5KP NN, 15KP VN/VVN) a **tyristorový crowbar** na usměrněném sekundáru (~25 V).
5. NN/VN: MOSFET multiplex přesného burdenu + odpojení nabíječe na `BURDEN_EN`.
6. VVN: Rogowski + integrátor; CT jen harvest (smí saturovat).

### 3.3 Satelit × 6

| Položka | Návrh |
|---|---|
| MEMS | T5848 bottom port, VDD 1,8 V, 100 nF + 1 µF, střed desky |
| LR / SEL | GND |
| SD | 100 kΩ pulldown; **SN65LVDS1** = budič páru sat → Core |
| LED | 8× WS2812B / SK6812 @ 3,3 V, kruh, daisy-chain z pinu 8; `DOUT` poslední NC |
| PCB | 50 × 80 mm, **6L Faraday**, ENIG (ne printed.cz PROTOTYP) |
| Kabel | STP, mapa [`PINOUT_SAT_v4.csv`](PINOUT_SAT_v4.csv) |
| PHY | LVDS RX SCK/WS (SN65LVDS2), LVDS TX SD (SN65LVDS1), CMC, TVS, PPTC 0,5 A |
| Úroveň | TXS 3,3 V LVDS-CMOS ↔ 1,8 V MEMS |

Žádný rozbočovač 3+3. Žádný `DOUT` zpět na Core.

---

## 4. I²S a STP (LVDS)

PIO na MCU je pořád I²S master (GP9 SCK, GP8 WS). Na kabelu jsou diferenciální páry.

| Pár T568B | Piny | Signál |
|---|---|---|
| 2 oranžový | 1, 2 | SCK_P, SCK_N |
| 3 zelený | 3, 6 | WS_P, WS_N |
| 1 modrý | 4, 5 | SD_P, SD_N |
| 4 hnědý | 7, 8 | **3V3**, **LED_DIN** |

Stínění STP na GND **jen na Core**. Na satelitu `SH` NC.

---

## 5. GPIO (RP2350B — držet)

| Funkce | GPIO | Směr | Poznámka |
|---|---|---|---|
| Mesh UART TX | GP0 | out | Heltec GPIO5 RX, 22 Ω |
| Mesh UART RX | GP1 | in | Heltec GPIO6 TX, 22 Ω |
| Env SDA | GP2 | I²C1 | DPS310 0x77, SHT40 0x44 |
| Env SCL | GP3 | I²C1 | |
| PM SDA | GP4 | I²C0 | přes interconnect |
| PM SCL | GP5 | I²C0 | |
| Piezo A | GP6 | out | DRV8837 IN1 |
| Piezo B | GP7 | out | DRV8837 IN2 |
| I²S WS | GP8 | out | společné, za LVDS |
| I²S SCK | GP9 | out | 3,072 MHz |
| LED4–6 DIN | GP10–12 | out | MIC4–6 |
| Mic 4–6 SD | GP13–15 | in | za LVDS RX |
| Mic 3–1 SD | GP16–18 | in | |
| LED3–1 DIN | GP19–21 | out | MIC3–1 |
| DSP_AWAKE | GP22 | out | Heltec GPIO4 |
| ADXL SPI | GP23–25, 30 | SPI0 | 1,8 V |
| ADC I / Rogowski / PT1000 / harvest | GP26–29 | analog | interconnect |
| BURDEN_EN | GP31 | out | NN/VN multiplex |
| PSRAM | GP32–35 | SPI | APS6404L |
| PG_5V | GP36 | in | silová deska |

`WAKE_DSP` není GPIO MCU — je to EN LDO. QSPI flash na dedicated pinech RP2350B.

---

## 6. Výroba

| Deska | Vrstvy | Povrch | Kam |
|---|---|---|---|
| Core | 6L ENIG (QFN-80, LGA) | ENIG | JLC / standardní TPV printed.cz, **ne** SKU PROTOTYP |
| Satelit | 6L Faraday ENIG | ENIG | JLC / standardní TPV, **ne** SKU PROTOTYP |
| Silová | 2L, 70 µm | HASL nebo ENIG dle TPV | ne PROTOTYP |

Gerbery z `kicad-cli`, ne `WriteDRCReport` (segfault v KiCad 10). KiCad 10, ne downgrade na 8/9.

v4.0.0 = Core schéma + stackup + interconnect pinout + NN silová elektricky uzavřená + satelit 6L (8× LED, LVDS TX SD). 6L DRC 0 Core může být v4.1.0.

---

## 7. Mimo tuto revizi

- Diskrétní nRF52+SX1262 kreslené na Core (SAW, CPWG) — zamítnuto.
- Volná MeshCore krabička na UART kabelu — zakázáno u 110 kV, špatný výrobek jinde.
- 230 V dělič na měď.
- PTFE a déšť (není SMT).
- 3D model pouzdra (tiskař); STEP desky ano.
- Firmware (objednatel) — board file Heltec + WAKE GPIO7 v `fedurca/het68`.

---

## 8. Podklady (bez jmen)

Technický obsah pochází z provozu prototypu, z firmware het68 a z v4 architektury Core + silová deska. Osoby, kontakty, nabídky a pracnosti v tomto dokumentu **nejsou**.

Konec zadání v4.0.0.
