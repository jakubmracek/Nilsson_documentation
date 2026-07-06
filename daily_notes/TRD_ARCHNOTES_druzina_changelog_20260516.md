# TRD + ARCH-NOTES — Záznamy z implementace modulu Školní [[Školní družina]]
**Datum:** 2026-05-16
**Migrace:** 020_druzina.sql + 021_rls_druzina.sql
**Status:** Nasazeno v produkci

Tento soubor obsahuje:
1. TRD changelog — nová sekce 13 (Školní [[Školní družina]])
2. ARCH-NOTES addendum — sekce 32 (multi-role) + sekce 33 (produkční nálezy)

---

## TRD — Changelog

**Changelog 2026-05-16:** Implementován modul Školní [[Školní družina]].
Migrace 020 (tabulky + funkce + triggery) a 021 (RLS politiky) nasazeny v produkci.
Aplikační vrstva: Server Actions (`app/actions/druzina.ts`), UI stránky
(`/[[Přehled]]/druzina/`, `/prihlaseni/`, `/tridnice/`, `/dochazka/`).
`staff_roles` junction tabulka + `has_role()` helper funkce pro multi-role zaměstnance.
`AppNav` rozšířen o `AllRoles` typ a `extraRoles` filtr.
Viz sekce 13 níže a ARCH-NOTES sekce 32–33.

---

## TRD — Sekce 13: Modul Školní [[Školní družina]]

### 13.1 [[Přehled]] tabulek

```
staff_roles              ← sekundární role zaměstnanců (multi-role Varianta A)
druzina_oddeleni         ← oddělení (nyní 1, připraveno na více)
druzina_enrollments      ← přihlášení a odhlášení [[Žáci]]
druzina_skolni_rok       ← soft lock per školní rok + oddělení
druzina_zaznamy          ← [[Třídní kniha]] ([[Přehled]] výchovně vzdělávací práce)
druzina_zaznamy_changes  ← immutabilní audit [[Třídní kniha]] (append-only)
druzina_dochazka         ← evidence příchodů a odchodů
```

### 13.2 Multi-role zaměstnance (`staff_roles`)

`staff.role` = primární role (DB ENUM `staff_role`, MŠMT, RLS — beze změny).
`staff_roles` = additivní sekundární role (TEXT s CHECK constraintem).
`has_role(p_role TEXT)` = SECURITY DEFINER + STABLE helper funkce,
kontroluje obě místa. Viz ARCH-NOTES sekce 32.

**Správa v1:** SQL Editor (2 admini). Přidat vychovatele:
```sql
INSERT INTO staff_roles (staff_id, role)
SELECT id, 'vychovatel' FROM staff WHERE email = '...';
```

### 13.3 Přístupová práva

| Oblast | director | vychovatel | ostatní staff |
|--------|----------|------------|---------------|
| Přihlášení [[Žáci]] | R/W | R | R |
| [[Třídní kniha]] | R/W | R/W | R |
| [[Docházka]] | R/W | R/W | R |
| [[Nastavení]] oddělení | R/W | — | — |

### 13.4 Školní rok

Konstanta `'2026/2027'` definována lokálně v každém souboru.
**TODO:** centralizovat do `lib/config.ts` → `CURRENT_SCHOOL_YEAR`.
Budoucí vylepšení: načítat z DB (tabulka `groups` — nejnovější `school_year`).

### 13.5 UI architektura

```
app/actions/druzina.ts                          ← Server Actions
app/[[Přehled]]/druzina/
├── page.tsx                                    ← [[Přehled]] (widgety)
├── prihlaseni/
│   ├── page.tsx                               ← director only
│   └── _components/EnrollmentRow.tsx          ← modal přihlásit/odhlásit
├── tridnice/
│   ├── page.tsx                               ← seznam záznamů
│   ├── novy/
│   │   ├── page.tsx
│   │   └── _components/NovyDruzinaZaznamForm.tsx
│   └── [id]/
│       ├── page.tsx
│       └── _components/DeleteZaznamButton.tsx
└── dochazka/
    ├── page.tsx                               ← date picker + enrolled students
    └── _components/DochazkaTable.tsx          ← inline editace příchod/odchod
```

### 13.6 Server Actions (`app/actions/druzina.ts`)

| Akce | Kdo | Popis |
|------|-----|-------|
| `enrollStudent` | director | INSERT druzina_enrollments |
| `unenrollStudent` | director | UPDATE date_to + unenrolled_by |
| `createDruzinaZaznam` | director / vychovatel | INSERT druzina_zaznamy |
| `updateDruzinaZaznam` | director / vychovatel | UPDATE (soft lock aware) |
| `deleteDruzinaZaznam` | director | DELETE |
| `recordDochazka` | director / vychovatel | UPSERT druzina_dochazka |

### 13.7 Navigace

```typescript
// components/nav/AppNav.tsx — nová položka
{ href: '/[[Přehled]]/druzina', label: '[[Školní družina]]',
  icon: Icons.druzina, roles: ['director', 'vychovatel'], bottomNav: false }
```

`NavItem.roles` je typován jako `AllRoles[]` (nový typ v [[Přehled]] layout).
`visibleItems` filtr kontroluje `staff.role` i `staff.extraRoles`.

### 13.8 Otevřené položky (future scope)

| Položka | Poznámka |
|---------|----------|
| Rodičovský pohled na [[Docházka]] | RLS politika guardian na `druzina_dochazka` |
| Správa `staff_roles` v UI | `/[[Přehled]]/nastaveni/role` |
| Více oddělení | Schéma připraveno, UI předpokládá 1 oddělení |
| `lib/config.ts` | Centrální `CURRENT_SCHOOL_YEAR` |
| Trigger: ověření enrollment při [[Docházka]] | V1 = aplikační vrstva |
| `_01b.xml` zaměstnanci | Vychovatel jako ped. zaměstnanec |

---

## ARCH-NOTES — Sekce 32: Multi-role staff (`staff_roles`)

### Rozhodnutí: Varianta A — junction tabulka

`staff.role` zůstává primární rolí beze změny ([[MŠMT výkazy]], UI, stávající RLS).
`staff_roles` přidává sekundární role additivně bez zásahu do existujících migrací.

### `has_role(p_role TEXT)` — klíčová oprava při nasazení

`staff.role` je **DB ENUM typ `staff_role`**, ne TEXT.
Porovnání `role = p_role` (TEXT) způsobuje chybu:
```
operator does not exist: staff_role = text
```

Správný zápis v `has_role()`:
```sql
role::TEXT = p_role   -- nutný explicit cast ENUM → TEXT
```

### `AllRoles` typ v Next.js aplikaci

`StaffRole` je generován z DB ENUM (`Database['public']['Enums']['staff_role']`).
`'vychovatel'` v DB ENUM není — existuje pouze v `staff_roles.role` (TEXT).
Proto nový typ v `app/[[Přehled]]/layout.tsx`:

```typescript
export type StaffRole = Database['public']['Enums']['staff_role']
export type AllRoles  = StaffRole | 'vychovatel'
```

`NavItem.roles: AllRoles[]` — umožní položky viditelné pro vychovatele.
`visibleItems` filtr:
```typescript
const extraRoles: string[] = (staff as any).extraRoles ?? []
const visibleItems = NAV_ITEMS.filter(item =>
  item.roles.includes(staff.role) ||
  extraRoles.some(r => item.roles.includes(r as StaffRole))
)
```

### `staff_roles` v generovaných typech

Tabulka `staff_roles` vznikla migrací 020 — po vygenerování `types/database.ts`.
Supabase typový klient ji nezná → `supabase.from('staff_roles')` způsobí TS chybu.
Workaround: `(supabase as any).from('staff_roles')`.
**TODO:** Regenerovat typy: `npx supabase gen types typescript --project-id <id> > types/database.ts`

---

## ARCH-NOTES — Sekce 33: Produkční nálezy — Školní [[Školní družina]] (2026-05-16)

### 33.1 `'use server'` — export konstanty zakázán

```typescript
// CHYBA: 'use server' soubor nesmí exportovat neAsync hodnoty
export const DRUZINA_SCHOOL_YEAR = '2026/2027'

// SPRÁVNĚ: bez export, nebo přesunout do lib/config.ts
const DRUZINA_SCHOOL_YEAR = '2026/2027'
```

Chyba: `Only async functions are allowed to be exported in a "use server" file.`

### 33.2 `pg_tables` nemá sloupec `forcerowsecurity`

Správný dotaz pro ověření FORCE RLS (viz sanity check vzor pro všechny migrace):

```sql
-- ŠPATNĚ (pg_tables nemá forcerowsecurity):
SELECT tablename, rowsecurity, forcerowsecurity FROM pg_tables ...

-- SPRÁVNĚ (JOIN s pg_class):
SELECT t.tablename,
       c.relrowsecurity      AS rowsecurity,
       c.relforcerowsecurity AS forcerowsecurity
  FROM pg_tables t
  JOIN pg_class c ON c.relname = t.tablename
 WHERE t.schemaname = 'public'
 ORDER BY t.tablename;
```

**Pravidlo:** Sanity check dotazy v migracích NESMÍ obsahovat `forcerowsecurity`
přímo z `pg_tables`. Vždy JOIN s `pg_class` přes `relforcerowsecurity`.

### 33.3 Supabase SQL Editor — transakční chování

SQL Editor spouští celý skript jako **jednu transakci**. Chyba kdekoliv
(včetně závěrečného sanity check SELECT) způsobí rollback celého skriptu.

**Pravidlo:** Sanity check dotazy NIKDY nevkládat do migračního souboru.
Spouštět je vždy samostatně jako nový query po úspěšné migraci.

### 33.4 `(supabase as any)` pro nové tabulky

Dokud nejsou regenerovány typy (`types/database.ts`), všechny nové tabulky
z migrací 020+ vyžadují cast:

```typescript
// Nové tabulky (020+) — nutný cast dokud nejsou v types/database.ts:
await (supabase as any).from('staff_roles')
await (supabase as any).from('druzina_enrollments')
await (supabase as any).from('druzina_oddeleni')
await (supabase as any).from('druzina_zaznamy')
await (supabase as any).from('druzina_dochazka')
```

Globální nahrazení ve VS Code: Ctrl+H
- Hledat: `await supabase.from(`
- Nahradit: `await (supabase as any).from(`

### 33.5 PowerShell — kopírování souborů

Nikdy `Copy-Item` pro soubory s českou diakritikou — zapíše Windows-1250.
Vždy:
```powershell
Get-Content -LiteralPath "zdroj.tsx" -Encoding UTF8 |
  Set-Content -LiteralPath "cil.tsx" -Encoding UTF8
```

Nebo editovat přímo ve VS Code a ukládat Ctrl+S.
