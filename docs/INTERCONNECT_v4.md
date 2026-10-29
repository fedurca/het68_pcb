# Interconnect Core ↔ silová deska (v4)

Stíněný konektor **2×10**, rozteč 2,54 mm (`J_PWR` na Core, `J_CORE` na silové desce). Same pinout u NN, VN i VVN. Neosazené funkce na daném SKU jsou NC na silové straně, na Core pad zůstane.

Mechanika: stíněný kryt na košili, `SHIELD` na pin 18. Kabely u 110 kV **neopustí** sféru.

Napájení rádia (`+5V_ALWAYS`, `+3V3_RF`) žije, i když je DSP vypnutý.

## Pinout (PinHeader 2×10, KiCad číslování)

```
 1  2
 3  4
 5  6
 7  8
 9 10
11 12
13 14
15 16
17 18
19 20
```

| Pin | Net | Směr | Poznámka |
|---:|---|---|---|
| 1 | `+5V_ALWAYS` | PWR → Core | USB-C lab **nebo** boost z LTO; Heltec 5V; VSYS Core |
| 2 | `GND` | — | |
| 3 | `+5V_ALWAYS` | PWR → Core | druhý silový pin |
| 4 | `GND` | — | |
| 5 | `+3V3_RF` | PWR → Core | LDO na silové desce, vždyživý (stamp později) |
| 6 | `GND` | — | |
| 7 | `I2C0_SDA` | bidir | PAC/INA na silové; pull-up 4,7 kΩ na Core `+3V3_DIG` |
| 8 | `I2C0_SCL` | bidir | totéž |
| 9 | `ADC_I` | PWR → Core | burden / CT sense, GP26 |
| 10 | `ADC_ROGO` | PWR → Core | výstup integrátoru; **NC na NN/VN** |
| 11 | `ADC_HARVEST` | PWR → Core | usměrněný sekundár / MPPT sense, GP29 |
| 12 | `ADC_PT1000` | PWR → Core | napěťový dělič PT1000, GP28 |
| 13 | `BURDEN_EN` | Core → PWR | GP31; **NC na VVN**. 1 = přesný burden, nabíječ pryč |
| 14 | `PG_5V` | PWR → Core | power-good 5 V, GP36 |
| 15 | `PT1000_RTN` | — | druhý vodič PT1000 (2vodič; 4vodič později na 15+16) |
| 16 | `EN_RF` | Core → PWR | rezerva; default pull-up na silové (LDO vždy on) |
| 17 | `I2C0_ALERT` | PWR → Core | INA/PAC ALERT, volitelné |
| 18 | `SHIELD` | — | košile konektoru, na GND u Core |
| 19 | `GND` | — | |
| 20 | `GND` | — | |

## Domény

| Net | Kdy žije | Kdo ho vyrábí |
|---|---|---|
| `+5V_ALWAYS` | vždy (USB, LTO, harvest) | silová deska; Core USB-C diodou OR |
| `+3V3_RF` | vždy | LDO na silové z `+5V_ALWAYS` |
| `+3V3_DIG` | jen když Heltec drží `WAKE_DSP` | LDO na Core |
| `+1V8_AUDIO` | totéž co DIG | LDO na Core, EN z `WAKE_DSP` |
| I²C0 | jen když DIG žije | pull-up na DIG — PM se čte po probuzení |

## PT1000

Svorka na vodiči (mechanika pouzdra, ne na měď fáze). 2vodič: pin 12 a 15. Dělič 1 kΩ z `+3V3_DIG` na Core; když DSP spí, ADC je pryč — teplota vodiče se čte po WAKE.

## Zkrat a crowbar

Dimenzovat stopy sekundáru a crowbaru na odražený proud (`I_pri / n`), ne na 16 kA. U SCT-013-000: 16 kA → ~8 A, 40 kA → ~20 A na sekundáru.
