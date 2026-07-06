# TRD — Addendum: Produkční nálezy Mapa pokroku
**Datum:** 2026-06-20
**Navazuje na:** TRD v1.4 addendum (sekce 7, Mapa pokroku)

---

## Changelog

- Přidána migrace `009_fix_staff_can_access_student.sql` — oprava RLS helperu
- Přidána migrace `010_rpc_hodnoceni_count.sql` — RPC agregace pro Mapu pokroku
- Aktualizována sekce 7.4 — opravená `staff_can_access_student()`
- Aktualizována sekce 7.7 — datová vrstva používá RPC místo přímého dotazu
- Viz ARCH-NOTES sekce 34 pro zdůvodnění a obecný vzor

---

## Aktualizace sekce 7.4 — RLS: opravená `staff_can_access_student()`

Původní funkce kontrolovala `gm.valid_to IS NULL`, čímž odfiltrovala žáky
s `valid_to = 2026-08-31` (standardní konec školního roku). Opravená verze:

```sql
-- migrace 009_fix_staff_can_access_student.sql
CREATE OR REPLACE FUNCTION public.staff_can_access_student(p_student_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM staff_groups sg
      JOIN group_memberships gm ON gm.group_id = sg.group_id
     WHERE sg.staff_id    = current_staff_id()
       AND gm.student_id  = p_student_id
       AND (sg.valid_to IS NULL OR sg.valid_to >= CURRENT_DATE)
       AND (gm.valid_to IS NULL OR gm.valid_to >= CURRENT_DATE)
  );
$$;
```

**Pravidlo:** Všude v Nilssonu platí konvence `valid_to IS NULL OR valid_to >= CURRENT_DATE`
pro aktivní záznamy. `IS NULL` samotné je chyba — záznamy s explicitním datem konce
(např. konec školního roku 31. 8.) jsou platné až do tohoto data.

---

## Aktualizace sekce 7.7 — RPC `get_hodnoceni_counts`

Datová vrstva (`lib/mapa-pokroku.ts`) nepoužívá přímý dotaz na `mapa_pokroku_hodnoceni`
pro agregaci počtů, ale RPC funkci. Důvod: PostgREST limit 1000 řádků.
Viz ARCH-NOTES sekce 34.

```sql
-- migrace 010_rpc_hodnoceni_count.sql
CREATE OR REPLACE FUNCTION public.get_hodnoceni_counts(
  p_school_year TEXT,
  p_semester    SMALLINT,
  p_student_ids UUID[]
)
RETURNS TABLE (student_id UUID, cnt BIGINT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT student_id, COUNT(*) AS cnt
  FROM mapa_pokroku_hodnoceni
  WHERE school_year = p_school_year
    AND semester    = p_semester
    AND student_id  = ANY(p_student_ids)
  GROUP BY student_id;
$$;
```

Volání z TypeScript:

```typescript
const { data: hodnoceniCounts, error: hodError } = await supabase
  .rpc('get_hodnoceni_counts', {
    p_school_year: schoolYear,
    p_semester: semester,
    p_student_ids: studentIds,
  })
```

**Po každé nové RPC funkci:** regenerovat `types/database.ts`:
```powershell
echo y | npx supabase gen types typescript --project-id <id> --schema public > types/database.ts
```
