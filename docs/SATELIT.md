# Satelit — propojky, osazení a kontrola v7.4.2

Deska je čtverec 52 × 52 mm, 8 vrstev. Mikrofon T5848 je ve středu, kruh 8× SK6812 je na venkovní straně. Svislý RJ45, T5848 a všechny propojky jsou na zadní straně. Sever desky je hrana u RJ45.

Na každém hřebínku 2×3 je v jednu chvíli **jen jedna** vodorovná propojka. Dva řádky naráz spojí výstup přijímače s kabelem.

Pin 1 je čtvercový a je na severovýchodním rohu hřebínku. Řádky jdou od severu k jihu.

## Tři režimy linky

Současné Core mluví diferenciálně (LVDS, 3,3 V na budiči). Režim 1,8 V chce na druhém konci kabelu 1,8 V, GPIO RP2350B to není.

| Režim | `JP_SCK` a `JP_WS` | `JP_SD` | `JP_TSCK`, `JP_TWS` | `JP_SDN` | `JP_OE` |
|---|---|---|---|---|---|
| Diferenciální LVDS | sever, piny 1–2 | sever, piny 1–2 | osazené | 1–2 | volná |
| Jednostranných 3,3 V | střed, piny 3–4 | střed, piny 3–4 | volné | 2–3 | volná |
| Přímo 1,8 V | jih, piny 5–6 | jih, piny 5–6 | volné | 2–3 | osazená |

`JP_OE` spojuje `OE` překladače na GND, takže ho vypne. Bez ní drží `OE` nahoře rezistor 10 kΩ.

## Co která propojka dělá

Hodiny a word select jedou z Core na satelit. Data mikrofonu jedou opačně.

### `JP_SCK` a `JP_WS` — hřebínek 2×3

| Řádek | Piny | `JP_SCK` | `JP_WS` |
|---|---|---|---|
| sever | 1–2 | výstup přijímače `SCK_LVDS` na překladač `SCK_3V3` | totéž pro `WS` |
| střed | 3–4 | kladná žíla kabelu `SCK_P` na překladač | totéž pro `WS_P` |
| jih | 5–6 | kladná žíla kabelu přímo na vývod mikrofonu `SCK` | totéž pro `WS` |

Přijímač SN65LVDS2 je na páru pořád. Propojka jen rozhodne, jestli na mikrofon půjde jeho CMOS výstup, kabel přes překladač, nebo kabel přímo.

### `JP_SD` — hřebínek 2×3, data ven z mikrofonu

| Řádek | Piny | Spojí |
|---|---|---|
| sever | 1–2 | kladný výstup budiče `SD_Y` na kladnou žílu `SD_P` |
| střed | 3–4 | 3,3 V z překladače `SD_3V3` na kladnou žílu |
| jih | 5–6 | vývod mikrofonu `SD` přímo na kladnou žílu |

### `JP_SDN` — hřebínek 1×3, záporná žíla

Pin 1 je sever, `SD_Z`. Pin 2 je `SD_N`. Pin 3 je GND.

- 1–2: záporný výstup budiče na zápornou žílu. Jen diferenciální režim.
- 2–3: záporná žíla na GND. Jednostranné režimy, zpátečka je stínění a zem.

### `JP_TSCK` a `JP_TWS` — hřebínek 1×2

Spojí 100 Ω mezi `SCK_T` a `SCK_N`, respektive `WS_T` a `WS_N`. SN65LVDS2 nemá vnitřní zakončení. V jednostranném režimu propojka zůstane volná, ať budič nevidí 100 Ω.

### `JP_OE` — hřebínek 1×2

Pin 1 je GND, pin 2 je `OE`. Osazená jen v režimu 1,8 V.

Napájení T5848 je ve všech režimech 1,62–1,98 V z AP2112K-1.8. Na mikrofon se 3,3 V nedává.

## Postup osazení

1. Akustický otvor 0,8 mm uprostřed desky musí zůstat volný. Na otvor nepřijde pasta ani cín. Tělo T5848 má port proti desce, ne ven.
2. Nejdřív zadní strana. Je na ní víc součástek, včetně `MK1`. Šablona, osazení, přetavení. Pin 1 mikrofonu je západní ploška řady blíž k RJ45, síť `WS`. Bílá tečka na 3D těle je u tohoto rohu.
3. Pak venkovní strana: jen `D4`–`D11`. `D4` je pixel 0 a je to LED nejblíž RJ45. Řetěz jde po kruhu, poslední `DOUT` je volný.
4. Ručně svislý RJ45 `J1`. Osa zástrčky je kolmo k desce. Oba vývody stínění jsou GND a pájí se.
5. Ručně hřebínky. Do stroje nepatří `J1` ani žádný `JP_*`.
6. Propojky až podle tabulky režimů. Na 2×3 vždy jeden řádek. Diferenciální sada pro kabel na současné Core: severní řádek všech tří 2×3, obě 100 Ω, `JP_SDN` 1–2, `JP_OE` volná.
7. Kontrola: v otvoru mikrofonu není cín, stínění RJ45 má spoj na GND, na mikrofonu není 3,3 V.

Stroj osadí zbytek z obou stran. Rozpis LCSC je v [kicad/jlc/OSAZENI.md](../kicad/jlc/OSAZENI.md). SK6812 na 3,3 V je pod katalogovým rozsahem 3,7–5,5 V; na desce jiné napájení LED není.

## Vyrobitelnost, funkce, indukce a rušení

Rozměr 52 × 52 mm, 8 vrstev, ENIG, prokov 0,60/0,20 mm a tloušťka 1,6 mm jsou v běžné nabídce JLC. Otvor mikrofonu je nepokovený 0,8 mm. Oboustranné osazení je v nastavení zakázky.

Měď v7.4.2 je dotažená. DRC satelitu je 0 zkratů, 0 mezer a 0 otevřených párů. Delší spoje jdou po SIG_L6 mezi dvěma zemními plochami. Core a silové desky se tímto krokem neměnily.

Zapojení ve schématu je pro tři režimy soudržné, pokud je na každém 2×3 jen jeden řádek a T5848 zůstane na 1,8 V.

Odolnost proti indukci a vf rušení je v návrhu postavená takto:

- 8 vrstev, souvislá zem na L2, L5 a L7, signál mezi zememi.
- Diferenciální režim vozí hodiny a data po LVDS na STP. Stínění je GND na satelitu i na Core, jednostranný režim má kudy zpátky.
- Společná tlumivka na SCK, WS i SD, TVS s malou kapacitou napříč párem, 100 Ω jen když je propojka zakončení nasazená.
- 3,3 V do satelitu jde přes PPTC a ferit 600 Ω.
- RJ45 je u mikrofonu, smyčka na desce je krátká. Signál mezi zemními plochami tu smyčku ještě zkracuje.

Jednostranné režimy jsou proti indukci horší než LVDS. Režim 1,8 V se současným Core nepoužívá.
