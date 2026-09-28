# ARCH-NOTE: Export matriky MŠMT zná jarní i podzimní sběr

**Datum:** 2026-09-28
**Modul:** [[MŠMT výkazy]] — `/dashboard/msmt`, `/api/msmt/xml`
**Soubory:** `lib/msmt-sber.ts` (nový), `lib/msmt-xml.ts`, `app/api/msmt/xml/route.ts`, `app/dashboard/msmt/page.tsx`, `app/dashboard/msmt/rodna-cisla/page.tsx`
**Commity:** `0339662` (feat(msmt): jarní/podzimní sběr matriky (?sber=), správné pololetí a výběr žáků)

---

## Přehled

Krok 2 přestavby exportu matriky (krok 1 = identifikátory, viz
[[ARCH-NOTE-2026-09-28-msmt-rodc-a-kod-zaka-poradove-cislo]]). Uživatel upozornil,
že prerekvizita „uzavřené 1. pololetí" nedává na podzim smysl. Ověřeno v metodice
MŠMT: 1. pololetí se vykazuje jen na jaře, na podzim 2. pololetí předchozího roku —
export byl celý natvrdo na jarní sběr. Nově se sběr
volí parametrem `?sber=jarni-RRRR | podzimni-RRRR`. Bez migrace.

---

## 1. Jarní vs. podzimní sběr

### Symptom
`/dashboard/msmt` chtěl na podzim 2026 „uzavřené 1. pololetí" školního roku
2026/2027 — to je nesplnitelné (pololetí teprve běží) a věcně špatně.

### Příčina
Stránka i export pracovaly s `CURRENT_SCHOOL_YEAR` + `semester = 1`, RDAT default =
dnes, jen `status = 'active'` a věty dělené k 1. 2. aktuálního roku (pro podzim by
vznikla věta od 1. 2. 2027 — v budoucnosti). Metodika MŠMT
([POKYNY.PDF](https://matrika.msmt.cz/matrikas/HELPY/POKYNY.PDF), položky OML_H/NEOML_H,
PLAT_ZAC, „Rozsah předávaných údajů"):

| | jarní | podzimní |
|---|---|---|
| RDAT | 31. 3. R | 30. 9. R |
| věty s platností v intervalu | 1. 9. (R-1) – 31. 3. R | 1. 10. (R-1) – 30. 9. R (i odešlí/vyšlí) |
| OML_H / NEOML_H za | 1. pololetí aktuálního roku | 2. pololetí **předchozího** roku |
| soubor „b" (PO 2.–5. st.) | ne | ano |

V obou případech jde o hodiny ze školního roku (R-1)/R.

### Řešení
- **`lib/msmt-sber.ts`:** `SberKontext` (RDAT, období, školní rok + pololetí OML,
  soubor „b", popis, orientační termín), `parseSber` z `?sber=`, výchozí = poslední
  uplynulé RDAT (říjen–prosinec → podzim R, duben–září → jaro R, leden–březen →
  podzim R-1), `zakVObdobi`.
- **`lib/msmt-xml.ts`:** `XmlConfig.sber` místo `school_year` + `rdat`; věty skládá
  `vetyZaka()` sdílená pro základní soubor i „a":
  - V1 = 1. 9. (R-1) / nástup → 31. 1. R; V2 = 1. 2. R / nástup → (jaro: aktuální,
    podzim: 31. 8. R); V3 (jen podzim) = 1. 9. R / nástup → aktuální.
  - Na podzim se vynechá věta, která končí před 1. 10. (R-1).
  - `PLAT_KON` = odchod jen pokud nastal do RDAT (budoucí konec se neuvádí).
  - OML nese V2 — jaro: žák přítomen v 1. pololetí; podzim: aspoň část 2. pololetí.
  - Oprava jara: V2 začínala vždy 1. 2., i když žák nastoupil později.
- **Export:** žáci `status in (active, withdrawn)` s docházkou zasahující do období;
  OML za `omlSkolniRok`/`omlPololeti` **+ `transfer_hours_*`** (metodika při
  přestupu hodiny sčítá; `recalculate_semester_summary` je do `oml_h` nepočítá).
  Parametr `rdat` zrušen — RDAT určuje sběr.
- **`/dashboard/msmt`:** přepínač tří posledních sběrů, rámeček s parametry sběru,
  prerekvizita „Uzavřené {N}. pololetí {rok}" počítaná jen ze žáků přítomných v tom
  pololetí, odkaz na `/dashboard/uzavreni-pololeti?year=…&semester=…`; soubor „b"
  jen na podzim; žáci s PO bez stupně vypsaní z dat (dřív natvrdo jedno jméno).
- **`/dashboard/msmt/rodna-cisla`:** stejný výběr žáků jako export (vč. odešlých,
  označených „odešel/a") — aby sedělo, co export odmítne s 422.

### Poučení
Úřední sběr s „rozhodným datem" je vždy parametr, ne konstanta — co se vykazuje
(období, pololetí, soubory), se podle něj mění. Výběr žáků pro výkaz podle
**platnosti v období**, ne podle dnešního `status`.

---

## Ověření

- `tsc --noEmit` bez chyb; eslint bez nových chyb (zbývá dřívější `cizi_jazyky as any`).
- Syntetický test věty (tsx) pro podzim 2026 a jaro 2026:

| žák | podzim 2026 | jaro 2026 |
|---|---|---|
| celý rok, pokračuje | 1. 9.–31. 1. · 1. 2.–31. 8. (OML) · od 1. 9. 2026 | 1. 9.–31. 1. · od 1. 2. (OML) |
| přišel 2. 3. 2026 | 2. 3.–31. 8. (OML) · od 1. 9. 2026 | od 2. 3. (bez OML) |
| odešel 30. 6. 2026 | 1. 9.–31. 1. · 1. 2.–30. 6. (OML) | 1. 9.–31. 1. · od 1. 2. (OML) |
| odešel 15. 9. 2025 | nic (mimo období) | 1. 9.–15. 9. 2025 |
| nový od 1. 9. 2026 | od 1. 9. 2026 | nic |
| přestup 1. 10. 2026 | nic (po RDAT) | nic |

- V prohlížeči neověřeno (produkční data za přihlášením).

---

## Vedlejší nálezy (nezasahováno)

- **Členění vět k 1. 2. a OML ve V2** je převzaté z původního kódu; metodika ho
  výslovně nepředepisuje (věta vzniká při změně údajů). Ověřit v kroku 3 proti
  dokumentu MŠMT „Datová rozhraní pro předávání dat" (spolu s názvy položek
  `RAZD/RAFZ/RAST/…` vs. `ZAHDAT/FIN/STPR/…`). Podklady zajišťuje uživatel.
- **`/dashboard/uzavreni-pololeti`** čte `searchParams` synchronně (bez `await`) —
  v Next 16 nemusí předvolba `?year=&semester=` fungovat.
- **Soubor „b"** (podpůrná opatření 2.–5. stupně k 30. 9.) — generátor chybí.

## Související

- [[ARCH-NOTE-2026-09-28-msmt-rodc-a-kod-zaka-poradove-cislo]] — krok 1 (RODC / KOD_ZAKA)
- [[Uzavření pololetí]] — zdroj `semester_attendance_summary`
