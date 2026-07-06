# ARCH-NOTES — Addendum 2026-05-19

Navazuje na ARCH-NOTES v2.0 + addendum-mapa-pokroku.md
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 34. `student_education_mode.rocnik` — ročník jako matriční údaj (migrace 009)

### Rozhodnutí

Ročník žáka je uložen jako explicitní sloupec `rocnik SMALLINT` v tabulce
`student_education_mode`, nikoliv odvozován z `birth_date` nebo jiného vypočteného
zdroje.

### Zdůvodnění

Alternativy byly zvažovány:

- **Výpočet z `birth_date`** — zamítnuto. Vilekula je alternativní škola se smíšeným
  věkem, žáci nepostupují striktně podle věku. Výpočet by vracel nesprávné hodnoty.
- **Odvozování z počtu let v systému** — zamítnuto. Žák mohl nastoupit v jiném ročníku
  (přestup, individuální vzdělávání), automatický postup by akumuloval chyby.
- **Explicitní `rocnik` v `student_education_mode`** — přijato. Ročník je matriční
  údaj (MŠMT), zadává se ručně každý školní rok ze spreadsheetu. Je vázán na konkrétní
  záznam `(student_id, school_year)`, tedy historicky správný.

### Schéma (migrace 009)

```sql
ALTER TABLE student_education_mode
  ADD COLUMN rocnik SMALLINT;
```

Data naplněna pro všech 52 záznamů (20 žáků 2025/2026 + 32 žáků od 2026-09-01).

### Důsledky

- `student_education_mode.rocnik` je **kanonický zdroj ročníku** pro veškeré moduly
  (Mapa pokroku, MŠMT XML, budoucí výkazy).
- UI pro zadání ročníku musí být součástí formuláře `student_education_mode`,
  ne karty žáka. Ročník se zadává při každém novém školním roce ručně.
- **Není automaticky povyšován** při přechodu školního roku — vyžaduje ruční zadání
  v rámci přechodu roku (viz TRD sekce 10.3).
- Hodnota `NULL` v existujících záznamech = ročník nebyl dosud zadán (stav před
  migrací 009). UI by mělo upozornit na nevyplněné záznamy.

### Dopad na Mapu pokroku

`svp_vystupy.rocnik` definuje, pro jaký ročník je výstup určen.
UI Mapy pokroku filtruje výstupy dle `student_education_mode.rocnik` pro daný
školní rok — ne dle `birth_date` ani dle skupiny. Viz sekce 14.5 (addendum-mapa-pokroku).

---

## 35. Mapa pokroku — frontend architektura

### 35.1 Soubory modulu

```
app/dashboard/mapa-pokroku/
├── page.tsx                        ← Server Component; přehled třídy
└── [studentId]/
    ├── page.tsx                    ← Server Component; detail žáka
    └── edit/
        ├── page.tsx                ← Server Component; wrapper pro formulář
        └── _components/
            └── EditForm.tsx        ← Client Component; zadávání hodnocení

lib/
├── mapa-pokroku.ts                 ← Server-only: Supabase dotazy, typy
└── mapa-pokroku-shared.ts          ← Shared: pure funkce, konstanty (bez Supabase)
```

### 35.2 Split `mapa-pokroku.ts` / `mapa-pokroku-shared.ts`

**Důvod rozdělení:** `EditForm.tsx` je Client Component — nemůže importovat server-only
kód (Supabase server klient, `'use server'`). Sdílené typy a pomocné funkce musí být
v souboru bez server závislostí.

| Soubor | Kde použitelný | Obsah |
|---|---|---|
| `lib/mapa-pokroku.ts` | Server Components, Server Actions | Supabase dotazy, fetch funkce |
| `lib/mapa-pokroku-shared.ts` | Client i Server | TypeScript typy, pure funkce, enum pořadí |

**Pravidlo:** Každý nový lib soubor pro modul s Client komponentami musí projít
stejným rozdělením. Importovat `mapa-pokroku.ts` z Client Component způsobí
runtime chybu Turbopack.

### 35.3 Navigace

Položka přidána do `components/nav/AppNav.tsx`:

```typescript
{ href: '/dashboard/mapa-pokroku', label: 'Mapa pokroku',
  roles: ['director', 'vp', 'guide'], bottomNav: false }
```

### 35.4 Stav nasazení

Frontend nasazen. `hodnotil_id` v nových hodnoceních zatím není plněn —
průvodkyně nemají Auth účty v Nilssonu. Viz sekce 14.3 (addendum-mapa-pokroku).
Blokováno: bude doplněn automaticky po vytvoření Auth účtů průvodkyň.

---

## 36. `lib/config.ts` — centralizace školního roku (2026-05-19)

### Rozhodnutí

Všechny hardcoded hodnoty `'2025/2026'` a `'2026/2027'` v aplikační vrstvě
centralizovány do `lib/config.ts`. Při přechodu školního roku stačí editovat
**jediný soubor**.

### Schéma souboru

```typescript
// lib/config.ts
export const CURRENT_SCHOOL_YEAR = '2025/2026' as const
export const NEXT_SCHOOL_YEAR    = '2026/2027' as const

export const SCHOOL_YEAR_OPTIONS: readonly string[] = [
  '2025/2026',
  '2026/2027',
] as const
```

### Rozsah centralizace

Celkem 18 souborů upraveno. Typy nahrazení:

| Vzor | Náhrada | Příklady |
|---|---|---|
| local `const SCHOOL_YEAR = '2025/2026'` | `import { CURRENT_SCHOOL_YEAR as SCHOOL_YEAR }` | `bozp.ts`, `msmt/page.tsx` |
| local `const DRUZINA_SCHOOL_YEAR = '2026/2027'` | `import { NEXT_SCHOOL_YEAR as DRUZINA_SCHOOL_YEAR }` | 5× druzina soubory |
| inline `.eq('school_year', '2025/2026')` | `CURRENT_SCHOOL_YEAR` | `omluvenky.ts` |
| fallback `?? '2025/2026'` | `?? CURRENT_SCHOOL_YEAR` | `route.ts`, `tridni-kniha/page.tsx` |
| `useState('2025/2026')` | `useState(CURRENT_SCHOOL_YEAR)` | `tridni-kniha/novy/page.tsx` |
| `['2025/2026', '2026/2027'].map(...)` | `SCHOOL_YEAR_OPTIONS.map(...)` | dropdown seznamy |

### Co nebylo centralizováno (záměrně)

- **JSDoc komentáře** — `app/api/msmt/xml/route.ts:8`, `lib/msmt-xml.ts:106`
- **UI labely** — `"Školní rok 2025/2026 ·"` v nadpisech (prezentační, ne logika)
- **`lib/config.ts` samotný** — je zdrojová pravda

### Checklist přechodu školního roku

Při přechodu na 2026/2027 editovat **pouze** `lib/config.ts`:

```typescript
export const CURRENT_SCHOOL_YEAR = '2026/2027' as const
export const NEXT_SCHOOL_YEAR    = '2027/2028' as const

export const SCHOOL_YEAR_OPTIONS: readonly string[] = [
  '2025/2026',
  '2026/2027',
  '2027/2028',
] as const
```

### `DRUZINA_SCHOOL_YEAR` — alias

Školní Družina používá `NEXT_SCHOOL_YEAR` (spouští se od 2026/2027). Alias
`import { NEXT_SCHOOL_YEAR as DRUZINA_SCHOOL_YEAR }` zachovává čitelnost kódu
bez vytváření nové konstanty.

### Produkční nález: `'use server'` + export konstanty

Pokus exportovat konstantu z `'use server'` souboru selhal:

```
Only async functions are allowed to be exported in a "use server" file.
```

**Řešení:** Konstanta musí být buď `const` bez `export` (lokální), nebo importována
z `lib/config.ts`. Viz také ARCH-NOTES sekce 33.1 (addendum druzina).
