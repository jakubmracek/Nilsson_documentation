## ARCH-NOTES — Sekce 34: PostgREST limit 1000 řádků — vzor RPC agregace

**Datum:** 2026-06-20
**Kontext:** Diagnostika Mapy pokroku — progress bary ukazovaly nesprávné hodnoty

---

### 34.1 Problém: skrytý limit PostgREST

Supabase PostgREST má globálně nastaven **`max-rows = 1000`**. Tento limit:

- Platí pro všechny přímé dotazy přes Supabase klienta (`.from(...).select(...)`)
- **Nelze překročit** přes `.limit()` z klienta — klientský limit může být pouze nižší
- Nevrací chybu — vrátí přesně 1000 řádků a tiše zahodí zbytek
- Neprojeví se v malých datasetech → bug se skryje při vývoji, projeví se v produkci

**Symptom:** Dotaz vrátí přesně 1000 řádků. Pokud výsledek závisí na kompletnosti
dat (agregace, počty), výsledek je silentně nesprávný.

**Diagnostika:** Pokud `data.length === 1000`, skoro jistě narazíš na limit.

---

### 34.2 Kdy je limit relevantní

| Situace | Relevantní? |
|---|---|
| Dotaz vrací entity (žáci, zaměstnanci) | Zřídka — Vilekula má desítky záznamů |
| Dotaz vrací řádkový log / audit trail | **ANO** — roste s časem |
| Dotaz vrací hodnocení (žák × výstup) | **ANO** — 20 žáků × 165 výstupů = 3 300 |
| Dotaz vrací transakce (Fio import) | **ANO** — roste s časem |
| RPC funkce | NE — RPC obchází PostgREST limit |

**Pravidlo:** Kdykoli dotaz vrací záznamy typu `(entita A) × (entita B)`,
spočítej maximální počet řádků. Pokud přesáhne 1000, použij RPC agregaci.

---

### 34.3 Vzor: RPC agregace místo přímého dotazu

Místo:
```typescript
// NEBEZPEČNÉ pokud rows > 1000:
const { data } = await supabase
  .from('tabulka')
  .select('foreign_id')
  .eq('school_year', year)
  // tiše vrátí max 1000 řádků
```

Použij RPC funkci která agreguje v DB:
```sql
CREATE OR REPLACE FUNCTION public.get_xxx_counts(...)
RETURNS TABLE (entity_id UUID, cnt BIGINT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT entity_id, COUNT(*) AS cnt
  FROM tabulka
  WHERE ...
  GROUP BY entity_id;
$$;
```

```typescript
// BEZPEČNÉ — RPC neomezuje PostgREST limit:
const { data } = await supabase.rpc('get_xxx_counts', { ... })
```

**RPC funkce v Nilssonu vždy:**
- `SECURITY DEFINER` + `SET search_path TO 'public'` — konzistentní RLS kontext
- `STABLE` — nezpůsobuje side effects, umožňuje cachování
- Vrací `TABLE` místo skalárů pokud výsledek má více řádků
- Pojmenovány `get_<tabulka>_counts` nebo `get_<tabulka>_summary`

---

### 34.4 Kdy regenerovat `types/database.ts`

Po každé nové RPC funkci nebo nové tabulce TypeScript klient nezná nové symboly
a build selže s chybou typu:

```
Argument of type '"get_hodnoceni_counts"' is not assignable to parameter of type ...
```

**Vždy regenerovat po migraci která přidává:**
- Novou RPC funkci (`CREATE FUNCTION`)
- Novou tabulku (`CREATE TABLE`)
- Nový enum (`CREATE TYPE ... AS ENUM`)

```powershell
echo y | npx supabase gen types typescript --project-id <project-id> --schema public > types/database.ts
git add types/database.ts
git commit -m "chore: regenerate supabase types"
```

Neregenerovat = workaround `(supabase as any)` nebo build failure na Vercelu.

---

### 34.5 `valid_to IS NULL` vs. `valid_to IS NULL OR valid_to >= CURRENT_DATE`

Diagnostika Mapy pokroku odhalila chybu v `staff_can_access_student()`:
funkce kontrolovala `gm.valid_to IS NULL`, čímž odfiltrovala všechny žáky
s explicitním datem konce členství (standardní konec školního roku = 31. 8.).

**Invariant Nilssonu:** Aktivní záznam = `valid_to IS NULL OR valid_to >= CURRENT_DATE`.
`valid_to IS NULL` samotné je neúplná podmínka — platné záznamy mohou mít
explicitní datum konce v budoucnosti.

Tato konvence platí pro všechny tabulky s časovou platností:
`group_memberships`, `staff_groups`, `student_education_mode`, `guardian_students`.

**Code review checklist:** Každý WHERE nebo JOIN filtr na `valid_to` musí obsahovat
obě větve:
```sql
-- SPRÁVNĚ:
AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)

-- CHYBA:
AND valid_to IS NULL
```
