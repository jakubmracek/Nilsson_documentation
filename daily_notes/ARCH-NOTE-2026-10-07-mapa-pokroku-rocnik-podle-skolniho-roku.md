# ARCH-NOTE: Mapa pokroku po přechodu roku — vyplněný progress bar, ale prázdný detail

**Datum:** 2026-10-07
**Modul:** [[Mapa pokroku]] — přehled, detail žáka, hodnocení
**Soubory:** `lib/mapa-pokroku.ts`, `app/dashboard/mapa-pokroku/[studentId]/page.tsx`, `app/dashboard/mapa-pokroku/[studentId]/edit/page.tsx`
**Commity:** `bb748e7` (fix: ročník žáka podle zobrazeného školního roku)

---

## Přehled

Po přechodu na školní rok 2026/2027 ukazoval přehled Mapy pokroku u loňských dětí (rok 2025/2026) vyplněné kompetence, ale v detailu žáka nebylo nic vyplněného. Hodnocení v DB byla v pořádku — rozbité bylo párování ročníku. Opraveno v aplikační vrstvě, bez migrace.

---

## 1. Ročník žáka se četl k dnešku, ne k zobrazenému roku

**Soubor:** `lib/mapa-pokroku.ts` — `getStudentsWithProgress`, `getStudentInfo`

### Symptom
Přehled `/dashboard/mapa-pokroku?year=2025/2026`: progress bar loňských dětí vyplněný. Detail i „Hodnotit": všechny výstupy prázdné. Navíc z přehledu loňského roku zmizely děti, které mezitím odešly.

### Příčina
Ročník se bral ze `student_education_mode` platného k dnešnímu datu. Po 1. 9. už je žák povýšený (3. → 4. ročník), takže:

| Místo | Co počítá | Výsledek |
|---|---|---|
| Progress bar (`get_hodnoceni_counts`) | hodnocení za 2025/2026 bez ohledu na ročník | vyplněno (loňská hodnocení 3. r.) |
| Jmenovatel X/Y | výstupy dnešního ročníku | výstupy 4. r. |
| Detail / Hodnotit (`getVystupyWithHodnoceni`) | výstupy dnešního ročníku + hodnocení podle `vystup_id` | žádná shoda → prázdné |

Odešlé děti vypadly, protože jejich záznam k dnešku už neplatí.

### Řešení
- Nový helper `getRocnikyForSchoolYear(supabase, schoolYear, studentIds)`: záznam `student_education_mode` platný kdykoli během zobrazeného roku (1. 9. – 31. 8.), při více záznamech vyhrává nejnovější `valid_from`. Stejná logika jako `/dashboard/zaci` (`app/dashboard/zaci/page.tsx`).
- Používá ho přehled (`getStudentsWithProgress`) i `getStudentInfo(studentId, schoolYear)` (nový povinný parametr) → detail i Hodnotit.
- Detail a Hodnotit bez `?year=` berou rok z `getActiveSchoolYear()` (DB config), ne z kalendáře — sjednoceno s přehledem.

### Poučení
Cokoli, co zobrazuje data za zvolený školní rok, musí brát verzovaný matriční stav (`student_education_mode`) k tomu roku, ne k dnešku. Problém je neviditelný celý rok a vybuchne až 1. 9. Vzor je v `/dashboard/zaci`; nové moduly by měly sdílet helper.

---

## 2. Progress bar počítá jen výstupy žákova ročníku

**Soubor:** `lib/mapa-pokroku.ts` — `getStudentsWithProgress`, krok 4

### Příčina
RPC `get_hodnoceni_counts` sčítalo všechna hodnocení žáka v období bez ohledu na ročník výstupu → čitatel mohl nesedět se jmenovatelem (i X > Y).

### Řešení
Místo RPC stránkovaný dotaz (po 1000, PostgREST limit) na `mapa_pokroku_hodnoceni` (`student_id`, `vystup_id`); započítá se jen hodnocení aktivního výstupu, jehož ročník = ročník žáka v daném roce. X/Y teď sedí s detailem.

---

## Ověření

- `tsc --noEmit` čisté, ESLint na dotčených souborech čistý.
- Vizuální ověření na produkci (rozkliknout loňské dítě v 2025/2026) — na uživateli.

## Vedlejší nález (nezasahováno)

RPC `get_hodnoceni_counts` (migrace 147) aplikace už nevolá. V DB zůstává; případné odstranění = samostatná migrace, až se uživatel rozhodne.

## Související

- [[Žáci]] — vzor „ročník pro zobrazený rok" na přehledu žáků
- [[Nastavení]] — `school_year_config`, aktivní rok
