# Checklist — het68 PCB v4.1.0 (Core 6L + silová SKU)

## Před kreslením

- [x] Compute je **nativní RP2350B** (flash + PSRAM na Core)
- [x] MeshCore teď = **Heltec WiFi LoRa 32 V3 868** na `J_MESH` 1×8; později DNP stamp na stejných sítích 1–6
- [x] **6× RJ45**, mapa LVDS v `docs/PINOUT_SAT_v4.csv`
- [x] Tři silové SKU, jeden interconnect `docs/INTERCONNECT_v4.md`
- [x] Na měď **nejde** 230 V / 22 kV / 110 kV
- [x] MEMS T5848 1,8 V; RGB 3,3 V; piezo 4× PS1240 na Core
- [x] Env DPS310+SHT40 na I²C1; PM na I²C0 přes interconnect
- [x] ADXL355 1,8 V SPI
- [x] Článek LiFePO4/LTO

## Elektrika Core

- [x] I²S: GP8 WS, GP9 SCK, 33 Ω, SD MIC1–6 = GP18/17/16/13/14/15
- [x] 6× `LED_DIN` MIC1–6 = GP21/20/19/10/11/12
- [x] UART MeshCore GP0/GP1, 22 Ω, ESD; Heltec GPIO5/6
- [x] `WAKE_DSP` = EN LDO `+3V3_DIG` a `+1V8_AUDIO` (Heltec GPIO7)
- [x] `DSP_AWAKE` = GP22 (Heltec GPIO4)
- [x] `+5V_ALWAYS` / `+3V3_RF` vždyživé; DIG/audio hradlované
- [x] 6L Faraday: L2/L5 GND, L4 split, L3 nekřižuje mezery
- [x] Via stitching GND 1,5 mm po obvodu
- [x] ≥ 0603; ne BGA; krystal C0G 15 pF
- [x] Stamp land DNP, sdílí pin 1–6 s `J_MESH`
- [x] LVDS 100 Ω u RX SD; CMC na SCK, WS i SD; ferit na 3V3 jacku

## Silová deska

- [x] Jen sekundár CT/Rogowski; GDT + TVS + LC + burden THT + crowbar
- [x] NN: multiplex burden (`BURDEN_EN`)
- [x] VN: silnější GDT/TVS (15KP)
- [x] VVN: harvest CT + Rogowski + integrátor; `BURDEN_EN` NC
- [x] MPPT (CN3791), LiFePO4/LTO, boost 5 V, LDO `+3V3_RF`
- [x] PT1000 2vodič na interconnect
- [x] INA3221 na I²C0

## Satelit

- [x] LVDS RX SCK/WS + 100 Ω, LVDS TX SD
- [x] CMC + TVS + PPTC + ferit 3V3
- [x] TXS 3,3 V ↔ 1,8 V k T5848
- [x] 8× SK6812/WS2812B @ 3,3 V v kruhu (D4 = sever, daisy CW); poslední `DOUT` NC
- [x] 6L Faraday, ENIG, ≥ 0603, ne BGA

## Dokumentace / fab

- [x] Zadání 4.1.0, pinout, interconnect
- [x] Schéma Core + tři silové SKU + satelit
- [x] BoM sady `kicad/BOM_KIT.csv`
- [x] 3D náhledy prototypu v `docs/img/`
- [x] Gerber z `kicad-cli` (ne `WriteDRCReport`)
- [x] Produktový strom bez HAT/Pico v3
