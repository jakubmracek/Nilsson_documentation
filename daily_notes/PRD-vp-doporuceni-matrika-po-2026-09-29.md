# PRD: Doporučení ŠPZ ve VP jako jediný zdroj pro matriku „a“ a soubor „b“

**Datum:** 2026-09-29
**Stav:** Schváleno 2026-09-29 — rozhodnutí R1–R6 „jak navrhuješ“ (ředitel); kód nenapsán, realizace v samostatné konverzaci
**Moduly:** [[Výchovný poradce (VP)]] (zdroj), [[MŠMT výkazy]] (spotřebitel); dotčeno [[Žáci]]
**Trigger:** přehled `/dashboard/msmt` hlásí „Matrika ‚a‘ žáků s PO: 2 / 3 připraveno (bez stupně PO: Polák Michael)“, přestože modul VP stupeň PO u žáka má. Rozhodnutí ředitele (2026-09-29): „Udělejme to pořádně hned“ — VP jako jediný zdroj, ne jednorázová SQL záplata.

---

## 1. Problém

Údaje o podpůrných opatřeních (PO) žijí ve **dvou nepropojených zdrojích**:

| | Tabulka | Obsah | Kdo plní |
|---|---|---|---|
| Modul VP | `vp_student_care` | `typ_pece` (`watch`, `po_1`–`po_5`), školní rok, stav, `spz_valid_until`, `spz_review_due`, `ivp_required`, `ivp_evaluated_at`, checklist `dokumenty` (existuje / platnost / soukromé) | výchovný poradce ručně v `/dashboard/vp` |
| Matrika „a“ | `student_matrika_a` | `pspo`, `id_znev`, `typ_tr`, `indi`, `nadani`, `uvp`, `sz`, `zz`, `prodl_dv`, `upr_vyst`, `zvj`, `jaz_podp`, `jaz_prip` (verzované `valid_from/valid_to`) | **nikdo** — naplněno jednou při založení IS (2 žáci), žádné UI |

Důsledky:
- Nový stupeň PO ve VP se do matriky nepropíše → přehled MŠMT i export „a“ žáka vynechají.
- VP neeviduje **obsah doporučení ŠPZ** (identifikátor znevýhodnění, IZO poradny, datum vydání, konkrétní PO), jen že dokument existuje a do kdy platí.
- Podzimní **soubor „b“** (PO 2.–5. stupně s normovanou finanční náročností, vzor `ZSb.22`) nemá v IS žádná data ani generátor.
- Příznak `students.has_svp` je třetí, ručně udržovaný zdroj pravdy.

---

## 2. Cíl

1. **Doporučení ŠPZ se eviduje ve VP** — jednou, strukturovaně, s historií (nové doporučení = nový záznam).
2. Z toho se **odvodí**: stupeň PO (i `typ_pece`), věty matriky „a“, věty souboru „b“, příznak „žák s SVP“.
3. Přehled MŠMT a export čtou **jen** VP; `student_matrika_a` zaniká (data se převedou).

**Mimo rozsah:** PLPP a PO 1. stupně bez doporučení nad rámec příznaku (do „a“ jdou, do „b“ ne); vykazování R 44-01.

---

## 3. Co matrika potřebuje (podle přijatých souborů MŠMT)

### Soubor „a“ (ZSa, vedle společných položek žáka)

| Položka | Význam | Zdroj v novém modelu |
|---|---|---|
| `PSPO` | převažující stupeň PO (1–5) | doporučení |
| `ID_ZNEV` | identifikátor znevýhodnění z doporučení (7 znaků, např. `06T0000`, `04M6M00`) | doporučení |
| `INDI` | IVP (číselník RAIP) | doporučení / VP (`ivp_required`) |
| `UPR_VYST` | upravené očekávané výstupy | doporučení |
| `PRODL_DV` | prodloužená délka vzdělávání (0/1/2) | doporučení |
| `UVP` | vzdělávání podle upraveného RVP (RAUP) | doporučení |
| `NADANI` | nadaný / mimořádně nadaný | doporučení |
| `ZZ` | zdravotní znevýhodnění (0/1) | odvodit z `ID_ZNEV` nebo zadat |
| `SZ` | sociální znevýhodnění definované **školou** (od 2026/27 jen `0` / sedmimístný kód) | VP (škola) |
| `TYP_TR` | typ třídy + asistent (`100A0`/`A1`/`A2`) | **třída**, ne žák (R1) |
| `ZVJ`, `JAZ_PODP`, `JAZ_PRIP` | znalost vyučovacího jazyka, jazyková podpora / příprava | žák (cizinci) — R4 |

### Soubor „b“ (ZSb.22, jen podzim, stav k 30. 9.) — jedna věta za každé PO

`RED_IZO`, `IZO`, `CAST`, `KOD_ZAKA`, `TT` (typ PO), `OBOR`, `IZO_SPZ` (poradna), `DAT_VYD` (vydání doporučení), `DAT_KPD` (konec platnosti), `PSPO`, `KOD_NFN` (kód normované finanční náročnosti, např. `03B501A30`), `FPP` (forma pořízení pomůcky), `FN` (finanční náročnost), `DAT_ZAH` / `DAT_UKON` (zahájení / ukončení poskytování), `ID_ZNEV`, `KOD_ZMEN`, `ZMENDAT`, `PLAT_ZAC`, `PLAT_KON`.

---

## 4. Návrh datového modelu

### 4.1 `vp_doporuceni` — doporučení ŠPZ (nové)

| Sloupec | Typ | Pozn. |
|---|---|---|
| `id` | uuid PK | |
| `student_id` | uuid FK students | |
| `care_id` | uuid FK vp_student_care NULL | vazba na péči |
| `izo_spz` | text(9) | IZO poradny (PPP / SPC) |
| `cislo_jednaci` | text NULL | pro dohledání |
| `datum_vydani` | date | `DAT_VYD` |
| `platnost_do` | date | `DAT_KPD` — nahrazuje `vp_student_care.spz_valid_until` |
| `pspo` | smallint 1–5 | převažující stupeň |
| `id_znev` | text(7..13) | kontrola tvaru |
| `indi`, `uvp`, `nadani` | text (kódy číselníků) | |
| `upr_vyst` | boolean | |
| `prodl_dv` | smallint 0–2 | |
| `zz` | boolean | odvoditelné z `id_znev` (R3) |
| `platnost_od` | date | od kdy škola podle doporučení postupuje (začátek věty „a“) |
| `stav` | enum `platne` / `nahrazeno` / `ukonceno` | |

Věty „a“ = intervaly platnosti doporučení (`platnost_od` → další doporučení / ukončení).

### 4.2 `vp_podpurna_opatreni` — konkrétní PO z doporučení (nové, pro „b“)

`id`, `doporuceni_id` FK, `tt` (typ: personální / materiální / … — číselník), `kod_nfn`, `fpp`, `fn`, `datum_zahajeni`, `datum_ukonceni`, `poznamka`.

### 4.3 Odvozené a zanikající

- `vp_student_care.typ_pece` — stupeň PO se **odvozuje** z platného doporučení (`po_<pspo>`); `watch` a péče bez doporučení (PLPP) zůstávají ručně.
- `students.has_svp` — odvodit (má platné doporučení / PLPP) — view nebo trigger; ruční příznak zrušit (R5).
- `student_matrika_a` — převést 2 stávající záznamy do `vp_doporuceni`, pak **zrušit** (i trigger `check_sma_msmt_kod`).
- `SZ` (sociální znevýhodnění dle školy), `ZVJ`/`JAZ_*` — pole u žáka nebo u péče VP (R4).
- `TYP_TR` asistent — u třídy (`groups`) nebo odvozený z přiřazených asistentů (R1).

---

## 5. UI

- **Karta péče ve VP (`/dashboard/vp/[id]`):** sekce „Doporučení ŠPZ“ — seznam doporučení (aktuální nahoře), formulář nového doporučení (poradna přes IZO — viz [[PRD-predchozi-skola-rejstrik-2026-09-29]] našeptávač, pokud bude), identifikátor znevýhodnění s kontrolou tvaru, stupeň, IVP / výstupy / délka; pod ním seznam PO s kódy NFN.
- Checklist `dokumenty.doporuceni_spz` se vyplní automaticky z existence platného doporučení.
- **Přehled MŠMT:** prerekvizita „Žáci s PO: doporučení kompletní N / M“ s odkazem na kartu VP konkrétního žáka.
- Přístup: **VP + ředitel** (údaje o zdravotním postižení = zvláštní kategorie osobních údajů, GDPR čl. 9) — RLS jako `vp_student_care`, průvodce/asistent jen stupeň, ne `id_znev`.

---

## 6. Rozhodnutí k potvrzení

| # | Otázka | Návrh |
|---|---|---|
| R1 | `TYP_TR` (asistent ve třídě) — u třídy, nebo u žáka? | u třídy (`groups.msmt_asistent` A0/A1/A2); matrika i dosud posílala stejné `100A1` všem žákům třídy |
| R2 | Kdo smí doporučení zadávat? | výchovný poradce + ředitel |
| R3 | `ZZ` zadávat, nebo odvodit z `ID_ZNEV`? | ověřit strukturu identifikátoru (metodika ŠPZ); do té doby zadávat |
| R4 | `SZ`, `ZVJ`, `JAZ_PODP`, `JAZ_PRIP` — kde? | u žáka (týká se i žáků bez PO — cizinci); výchozí 0 / 1 |
| R5 | `has_svp` odvodit, nebo nechat ruční? | odvodit (platné doporučení nebo PLPP) |
| R6 | Stupeň PO u péče bez doporučení (PLPP = 1. stupeň) | `typ_pece = po_1` ručně, do „a“ jde s `PSPO 1` bez `ID_ZNEV` — ověřit proti metodice |

---

## 7. Fáze

- **F1 — model + převod:** migrace `vp_doporuceni`, `vp_podpurna_opatreni`; převod 2 záznamů ze `student_matrika_a`; odvození `typ_pece`.
- **F2 — UI ve VP:** doporučení + PO na kartě péče; zadání doporučení pro Michaela Poláka.
- **F3 — matrika „a“:** export a přehled MŠMT čtou VP; zrušení `student_matrika_a`.
- **F4 — soubor „b“:** generátor podle `ZSb.22` (vzor mezi přijatými soubory), jen podzimní sběr.

**Termín:** podzimní sběr 2026 (odevzdání v říjnu) — F1–F3 přednostně; F4 ideálně také (soubor „b“ je na podzim povinný pro školy s PO 2.–5. stupně s NFN).

## Související

- [[ARCH-NOTE-2026-09-29-msmt-export-zs025-a-udaje-zaku]] — export ZS.025, soubor „a“
- [[PRD-predchozi-skola-rejstrik-2026-09-29]] — našeptávač ze školského rejstříku (IZO poradny)
- [[Výchovný poradce (VP)]], [[MŠMT výkazy]]
