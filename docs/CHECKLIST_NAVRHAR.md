# Checklist — het68 PCB v4 (Core 6L + silová SKU)

## Před kreslením

- [x] Compute je **nativní RP2350B** (flash + PSRAM na Core). Pico Plus 2 + HAT je v3.0.0, dál se nekreslí
- [x] MeshCore teď = **Heltec WiFi LoRa 32 V3 868** na `J_MESH` 1×8; později DNP stamp na stejných sítích 1–6
- [x] **6× RJ45**, mapa LVDS v `docs/PINOUT_SAT_v4.csv` (T568B jednovodičové I²S z v3 končí)
- [x] Tři silové SKU, jeden interconnect `docs/INTERCONNECT_v4.md`
- [x] Na měď **nejde** 230 V / 22 kV / 110 kV
- [x] MEMS T5848 1,8 V; RGB 3,3 V; piezo 4× PS1240 na Core
- [x] Env DPS310+SHT40 na I²C1; PM na I²C0 přes interconnect
- [x] ADXL355 1,8 V SPI
- [x] Článek LiFePO4/LTO, ne 21700

## Elektrika Core

- [x] I²S: GP8 WS, GP9 SCK, SD MIC1–6 = GP18/17/16/13/14/15 (jako HAT rev E)
- [x] 6× `LED_DIN` MIC1–6 = GP21/20/19/10/11/12
- [x] UART MeshCore GP0/GP1, 22 Ω, ESD; Heltec GPIO5/6
- [x] `WAKE_DSP` = EN LDO `+3V3_DIG` a `+1V8_AUDIO` (Heltec GPIO7)
- [x] `DSP_AWAKE` = GP22 (Heltec GPIO4)
- [x] `+5V_ALWAYS` / `+3V3_RF` vždyživé; DIG/audio hradlované
- [x] 6L Faraday: L2/L5 GND, L4 split, L3 nekřižuje mezery
- [x] Via stitching GND 1,5–2 mm po obvodu
- [x] 0402 jen RF matching; jinak ≥ 0603; ne BGA
- [x] Stamp land DNP, sdílí pin 1–6 s `J_MESH`

## Silová deska

- [x] Jen sekundár CT/Rogowski; GDT + TVS + LC + burden THT + crowbar
- [x] NN: multiplex burden (`BURDEN_EN`)
- [x] VN: silnější GDT/TVS (15KP)
- [x] VVN: harvest CT + Rogowski + integrátor; `BURDEN_EN` NC
- [x] MPPT (CN3791), LiFePO4/LTO, boost 5 V, LDO `+3V3_RF`
- [x] PT1000 2vodič na interconnect
- [x] INA3221 na I²C0

## Satelit

- [x] LVDS RX SCK/WS, LVDS TX SD
- [x] CMC + TVS + PPTC
- [x] TXS 3,3 V ↔ 1,8 V k T5848
- [x] 8× SK6812/WS2812B @ 3,3 V v kruhu (D4 = sever, daisy CW); poslední `DOUT` NC
- [x] LVDS TX SD: SN65LVDS1 na satelitu, SN65LVDS32 na Core
- [x] 6L Faraday, ENIG, ≥ 0603, ne BGA (ne printed.cz PROTOTYP)

## Dokumentace / fab

- [x] Zadání 4.0.0, pinout, interconnect
- [x] Schéma Core + tři silové SKU + satelit
- [x] Gerber z `kicad-cli` (ne `WriteDRCReport`)
- [x] v3 HAT 140 × 140 2L nechat; úzký HAT WIP necommittovat
- [x] Tag v4.0.0 až Core schéma + NN silová + satelit elektricky uzavřené
