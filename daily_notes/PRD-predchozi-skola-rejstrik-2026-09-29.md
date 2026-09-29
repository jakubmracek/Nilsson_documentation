# PRD: Předchozí škola dítěte ze školského rejstříku (IZO do matriky MŠMT)

**Datum:** 2026-09-29
**Stav:** Návrh k rozhodnutí (PRD, kód nenapsán)
**Moduly:** [[Žáci]] (matrika, zápis/přestup), [[MŠMT výkazy]]; spotřebitel [[Katalogový list]]
**Trigger:** export matriky MŠMT (ZS.025) odmítl všech 33 žáků — chybí ODHL a IZOP; škola je dosud vyplňovala ručně mimo IS. Viz [[ARCH-NOTE-2026-09-29-msmt-export-zs025-a-udaje-zaku]].

---

## 1. Problém

Matrika MŠMT vyžaduje u každého žáka:

| Položka | Význam | Kde by se měla vzít |
|---|---|---|
| **IZOP** | IZO školy, ze které se žák přihlásil (MŠ při zápisu, ZŠ při přestupu); `000000000` = nechodil do školy, `999999xxx` = zahraniční škola, `000000203` = zaniklá škola v ČR | zápis / přestup |
| **ODHL** | předchozí vzdělávání (číselník RAPD, 3 znaky) | odvoditelné z typu přijetí a ročníku |
| **KOD_ZAH** | kód zahájení docházky (RAZD: 1 řádný nástup, 2 po odkladu, E přestup…) | odvoditelné ze zápisu (odklad) / přestupu |

### Současný stav (ověřeno 2026-09-29)

- **Zápis do 1. ročníku:** `enrollment_applications.dosavadni_skola` existuje (detail přihlášky ve správě ho zobrazuje), ale **formulář (`EnrollmentWizard`) nemá vstupní pole** → vždy prázdné. RPC přijetí (`enrollment_migrate_to_student`, migrace 125) ho zapisuje do `students.predchozi_skola_izo` — tedy prázdnou hodnotu, a navíc by to byl název, ne IZO.
- **Přestup:** formulář má „Současná škola“ / „Současná třída“ (`soucasna_skola`, `soucasna_trida`) jako volný text. RPC přijetí je **do žáka nepřenáší vůbec**.
- **ODHL / KOD_ZAH** se ve formuláři nesbírají; ředitel je dnes doplňuje ručně na `/dashboard/msmt/udaje-zaku` (sloupce `students.msmt_odhl`, `students.msmt_izop`, `students.kod_zahajeni`, migrace 130).
- `students.predchozi_vzdelavani` je volná poznámka, kterou tiskne [[Katalogový list]] — pro kód nepoužitelná.

---

## 2. Cíl

1. Rodič při zápisu / přestupu **vybere předchozí školu ze školského rejstříku** (našeptávač) → IS má jisté **IZO**, žádná ruční validace.
2. Při přijetí se IZOP, ODHL a KOD_ZAH **předvyplní do žáka**; ředitel je na `/dashboard/msmt/udaje-zaku` jen zkontroluje.
3. Opravit dnešní chyby: chybějící pole `dosavadni_skola` ve formuláři, nepřenášená přestupová škola.

**Mimo rozsah:** změny exportu MŠMT (už čte `msmt_izop` / `msmt_odhl`); historické žáky (doplněni ručně / ze souborů MŠMT 2026-09-28).

---

## 3. Zdroj dat — školský rejstřík

### Co existuje (první průzkum 2026-09-29)

- **Otevřená data MŠMT:** datová sada „Rejstřík škol a školských zařízení — celá ČR“ v Národním katalogu otevřených dat (NKOD), publikovaná po rocích; katalog MŠMT `lkod.msmt.gov.cz` má ~18 sad k rejstříkům.
- **Webové vyhledávání:** `rejstriky.msmt.cz/rejskol`, nově `isv.gov.cz/rssz` (rejstřík škol) a `isv.gov.cz/rspo` (právnické osoby). **Veřejné dotazovací API zatím nenalezeno.**

### Otázky k ověření (fáze 0)

| # | Otázka |
|---|---|
| Z1 | Formát sady (XML / CSV / JSON-LD), struktura: IZO, RED_IZO, název, druh (MŠ, ZŠ, …), adresa/obec, datum vzniku/zániku |
| Z2 | Četnost aktualizace (roční? průběžná?) a stabilní URL ke stažení |
| Z3 | Obsahuje sada i **zaniklé** školy (přestup ze školy, která mezitím zanikla → `000000203`)? |
| Z4 | Má ISV (`isv.gov.cz`) strojové rozhraní? Pokud ano, zvážit místo lokální kopie. |
| Z5 | Licence otevřených dat (očekávání: CC BY 4.0 / bez omezení) |

### Doporučená varianta: lokální kopie (vzor RÚIAN)

IS už drží lokální číselník obcí z RÚIAN (`ruian_obce`) pro validaci adres. Stejně:

- tabulka `skolsky_rejstrik` (IZO PK, red_izo, nazev, druh_kod, druh_nazev, obec, ulice, zanikla_k NULL…), jen MŠ a ZŠ (případně vše — řádově desítky tisíc řádků),
- import skriptem / cronem z otevřených dat (ročně + ručně na vyžádání), idempotentní upsert,
- RPC / route `hledej_skolu(q, druh)` pro našeptávač (fulltext přes název + obec, limit 20).

Alternativa (jen pokud Z4 = ano): dotaz na ISV API za běhu — bez lokální kopie, ale závislost na dostupnosti externí služby při zápisu.

---

## 4. Návrh — formulář a přenos

### 4.1 Formulář zápisu (1. ročník)

- Nové pole **„Mateřská škola, kterou dítě navštěvuje“** — našeptávač z rejstříku (druh MŠ).
- Volby místo školy: **„Dítě nechodilo do mateřské školy“** (→ IZOP `000000000`), **„Mateřská škola v zahraničí“** (→ `999999` + kód státu podle RAST).
- Ukládá se IZO + název (název pro zobrazení / dokumenty).

### 4.2 Formulář přestupu

- „Současná škola“ → našeptávač z rejstříku (druh ZŠ), + volba „škola v zahraničí“.
- „Současná třída“ zůstává textem (ročník je v `budouci_rocnik`).

### 4.3 Přenos při přijetí (RPC `enrollment_migrate_to_student`)

| Pole žáka | Zdroj |
|---|---|
| `msmt_izop` | IZO vybrané školy / speciální kód |
| `msmt_odhl` | zápis → `010`; přestup do n-tého ročníku → `10(n−1)` (odvozeno z přijatých souborů MŠMT — **ověřit proti číselníku RAPD**) |
| `kod_zahajeni` | zápis bez odkladu → `1`; po odkladu (`melo_odklad`) → `2`; přestup → `E` (přijaté soubory — **ověřit proti RAZD**) |
| `predchozi_skola_izo` | **přestat zneužívat pro název** — buď IZO (a sloupec sjednotit s `msmt_izop`), nebo sloupec zrušit; rozhodnutí R3 |

### 4.4 Stávající přihlášky

Rozpracované a odeslané přihlášky bez IZO: pole v detailu přihlášky ve správě (ředitel dohledá a vybere), případně se doplní až na `/dashboard/msmt/udaje-zaku`.

---

## 5. Rozhodnutí k potvrzení

| # | Otázka | Návrh |
|---|---|---|
| R1 | Lokální kopie rejstříku vs. dotaz na ISV za běhu | lokální kopie (vzor RÚIAN), pokud Z4 nepřinese spolehlivé API |
| R2 | Je výběr MŠ při zápisu povinný? | ano, s volbou „nechodilo do MŠ“ (matrika IZOP vyžaduje vždy) |
| R3 | `predchozi_skola_izo` — sjednotit s `msmt_izop`, nebo zrušit? | sjednotit: jeden sloupec IZO, název školy do nového `predchozi_skola_nazev` |
| R4 | Mapování ODHL / KOD_ZAH | ověřit proti oficiálním číselníkům RAPD / RAZD před implementací |

---

## 6. Fáze

- **F0 — průzkum zdroje** (Z1–Z5), stažení vzorku, rozhodnutí R1.
- **F1 — rejstřík v IS:** migrace tabulky, import, RPC našeptávače.
- **F2 — formulář + přenos:** pole v zápisu / přestupu, RPC přijetí (IZOP, ODHL, KOD_ZAH), oprava `dosavadni_skola` / `soucasna_skola`.
- **F3 — správa:** výběr školy v detailu přihlášky pro ředitele; na `/dashboard/msmt/udaje-zaku` našeptávač místo ručního IZO.

## Související

- [[ARCH-NOTE-2026-09-29-msmt-export-zs025-a-udaje-zaku]] — proč ODHL/IZOP chybí, migrace 130
- [[ARCH-NOTE-2026-09-28-msmt-rodc-a-kod-zaka-poradove-cislo]] — identifikátory v matrice
- [[PRD-adresni-model-2026-09-20]] — vzor práce s RÚIAN (lokální číselník + validace)
