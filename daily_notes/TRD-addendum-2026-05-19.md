# TRD — Addendum 2026-05-19

Navazuje na TRD v1.4 (addendum-mapa-pokroku) + TRD v1.3 (Školní [[Školní družina]])
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-05-19

- **Migrace 009:** přidán `rocnik SMALLINT` do `student_education_mode`. Data naplněna
  pro 52 záznamů. Viz sekce níže + ARCH-NOTES sekce 34.
- **[[Mapa pokroku]] — frontend:** nasazeny stránky a lib soubory. Viz sekce níže + ARCH-NOTES
  sekce 35.
- **`lib/config.ts`:** centralizace `CURRENT_SCHOOL_YEAR`. 18 souborů upraveno.
  Viz sekce níže + ARCH-NOTES sekce 36.

---

## Aktualizace sekce 3.10 — tabulka `student_education_mode`

Přidat sloupec `rocnik`:

```sql
CREATE TABLE student_education_mode (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  zpusob      CHAR(2) NOT NULL,
  rocnik      SMALLINT,              -- ← nový sloupec (migrace 009)
  valid_from  DATE NOT NULL,
  valid_to    DATE,
  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`rocnik` — kanonický zdroj ročníku [[Žáci]]:**

| Vlastnost | Hodnota |
|---|---|
| Typ | `SMALLINT` (nullable — starší záznamy před migrací 009) |
| Zdroj | Zadáváno ručně ze spreadsheetu každý školní rok |
| Rozsah | 1–9 (ZŠ) |
| Automatický postup | NE — ruční zadání každý rok |
| Primární použití | [[Mapa pokroku]], MŠMT XML, budoucí výkazy |

**Proč ne `birth_date`:** Vilekula je alternativní škola se smíšeným věkem —
ročník neodpovídá věku. Viz ARCH-NOTES sekce 34 pro detailní zdůvodnění.

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
└── 009_rocnik.sql    ← ALTER TABLE student_education_mode ADD COLUMN rocnik SMALLINT
```

Do `lib/` přidat:

```
├── mapa-pokroku.ts           ← Server-only: Supabase dotazy pro Mapu pokroku
├── mapa-pokroku-shared.ts    ← Shared: typy a pure funkce (importovatelné z Client)
└── config.ts                 ← CURRENT_SCHOOL_YEAR, NEXT_SCHOOL_YEAR, SCHOOL_YEAR_OPTIONS
```

Do `app/[[Přehled]]/` přidat:

```
└── mapa-pokroku/
    ├── page.tsx              ← [[Přehled]] třídy
    └── [studentId]/
        ├── page.tsx          ← detail [[Žáci]]
        └── edit/
            ├── page.tsx
            └── _components/
                └── EditForm.tsx
```

---

## Aktualizace sekce 7.7 — [[Mapa pokroku]] frontend

Nahradit stávající sekci 7.7 (plánovaný rozsah) aktuálním stavem:

### 7.7 Frontend — stav nasazení (2026-05-19)

**Status: ✅ Nasazeno v produkci**

| Stránka | Soubor | Stav |
|---|---|---|
| [[Přehled]] třídy | `app/[[Přehled]]/mapa-pokroku/page.tsx` | ✅ |
| Detail [[Žáci]] | `app/[[Přehled]]/mapa-pokroku/[studentId]/page.tsx` | ✅ |
| Zadávání hodnocení | `app/[[Přehled]]/mapa-pokroku/[studentId]/edit/` | ✅ |

**Navigace:** Položka „[[Mapa pokroku]]" přidána do `AppNav` pro role `director`, `[[Výchovný poradce (VP)]]`, `guide`.

**Lib soubory:**

- `lib/mapa-pokroku.ts` — server-only (Supabase dotazy)
- `lib/mapa-pokroku-shared.ts` — shared typy a pure funkce (importovatelné z Client Components)

**Blokováno:** `hodnotil_id` v nových hodnoceních zatím NULL — průvodkyně nemají Auth
účty v Nilssonu. Bude doplněno zpětně po vytvoření účtů (viz ARCH-NOTES sekce 14.3).

---

## Nová sekce — `lib/config.ts` (centralizace školního roku)

### Schéma

```typescript
// lib/config.ts
export const CURRENT_SCHOOL_YEAR = '2025/2026' as const
export const NEXT_SCHOOL_YEAR    = '2026/2027' as const
export const SCHOOL_YEAR_OPTIONS: readonly string[] = [
  '2025/2026',
  '2026/2027',
] as const
```

### Použití

- `CURRENT_SCHOOL_YEAR` — ve všech Supabase dotazech, RPC voláních, fallback hodnotách
- `NEXT_SCHOOL_YEAR` — Školní [[Školní družina]] (spouští se 2026/2027), nové zápisy [[Žáci]]
- `SCHOOL_YEAR_OPTIONS` — dropdown `<select>` komponenty v UI

### Přechod školního roku

Editovat **pouze** `lib/config.ts`. Viz ARCH-NOTES sekce 36 pro detaily a checklist.

---

## Aktualizace sekce 10.2 — import dat

Přidat řádky do tabulky provedených importů:

| Soubor / akce | Obsah | Stav |
|---|---|---|
| `009_rocnik.sql` | `ADD COLUMN rocnik` + naplnění dat pro 52 záznamů | ✅ 2026-05-19 |
| `scripts/import_mapa_pokroku.sql` | 1 077 hodnocení, 18 [[Žáci]], 1. pololetí 2025/2026 | ✅ viz addendum-mapa-pokroku |
