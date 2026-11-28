# Otevřené body před výrobou

Stav k tagu **v7.4.2** (26. listopadu 2026, 21:30 SEČ). Měď satelitu v tom tagu má 0 zkratů, 0 mezer a 0 otevřených párů. Core a silové desky se od v7.3.0 nezměnily a jejich DRC je stejně čistá. Tohle jsou body, které je pořád potřeba vyřešit před zadáním do výroby, plus návrhy na testovatelnost a odolnost proti rušení.

## Než se zadá zakázka

Gerber satelitu v [kicad/jlc/het68-sat-gerber.zip](kicad/jlc/het68-sat-gerber.zip) je z 20:18 SEČ, tedy ze stavu před dotažením spojů ve v7.4.2. Ten zip se nesmí objednat. Nový gerber se musí vygenerovat z desky v tagu v7.4.2. Zipy Core a tří silových desek sedí na svou měď.

Ve formuláři nechat flying probe a u osmi vrstev i čtyřbodový Kelvin test. Ten ověří, že síť vede, ne že mikrofon nebo LVDS funguje.

SK6812 na satelitu je pořád na 3,3 V. Katalog chce 3,7–5,5 V, takže řetěz se nemusí rozsvítit ani když je měď v pořádku. Na desce jiné napájení LED není.

## Testovatelnost

Na žádné desce není testovací ploška ani fiducial. Jediný přístup k satelitu je RJ45 a hřebínky schované pod konektorem. Sonda se tam po osazení nedostane.

Na zadní stranu, k volné hraně, patří malé plošky s GND hned vedle: `+1V8`, `+3V3`, `SCK`, `WS`, `SD` na straně mikrofonu a `LED_DIN` u první diody. Tři fiducialy na každé straně (dva v rozích, jeden mimo úhlopříčku) chce osazovací stroj při oboustranném osazení. Na hedvábí u `JP_SCK`, `JP_WS` a `JP_SD` stačí písmena D / 3 / 1 u tří řádků, ať se propojka nasadí bez návodu.

Oživení jednoho kusu pak jde bez úpravy firmware: 3,3 V a 1,8 V na nových ploškách, hodiny na `SCK`, jeden tón do mikrofonu a průchod řetězu LED. Propojka jen v diferenciálním režimu. Dva řádky naráz spojí výstup přijímače s kabelem.

## Odolnost proti rušení

Satelit má 30 zemních prokovů a z nich jen 2 leží do 4 mm od hrany. Core má zem prošitou po obvodu po 1,5 mm. Stejný věnec na satelitu, plus prstenec kolem otvoru mikrofonu a kolem stínění RJ45, je největší změna, která se do dnešní skladby vejde. Rozteč do 5 mm zavře štěrbinu, kterou teď zemní plochy na L2, L5 a L7 nemají po obvodu spojenou.

Výroba by měla jezdit jen v diferenciálním režimu. Jednostranná 3,3 V a přímých 1,8 V vrací proud po stínění a po vnější mědi. LVDS, společné tlumivky, TVS a ferit 600 Ω na 3,3 V už na desce jsou a pro kabel mezi Core a satelitem stačí.

Data LED jedou po F.Cu bez sériového odporu. Hrana SK6812 je krátká a řetěz vede kolem mikrofonu. Odpor 22–33 Ω u `DIN` první diody a zemní prokov vedle té stopy omezí vyzáření víc než další vrstva.

Delší spoje z v7.4.2 jsou na SIG_L6 mezi dvěma zememi. Část starších stop ale zůstala na F.Cu a B.Cu a prořezává vnější zemní plochu. Před opakovanou sérií ty souběhy smazat, ať vnější měď zůstane souvislá. Impedanci 100 Ω u JLC neobjednávat na první sérii satelitu: na 52 mm rozhoduje kabel, ne stopa. Na Core, kde LVDS běží přes 160 mm, už kontrola geometrie páru proti skutečné osmivrstvé skladbě JLC smysl má.
