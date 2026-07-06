# ARCH-NOTES — Addendum 2026-06-02b

Navazuje na ARCH-NOTES addendum 2026-06-02.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 50. PostgREST `.from()` vs `.rpc()` — JWT předávání v @supabase/ssr (2026-06-02)

### Problém

`createSupabaseServerClient()` (z `lib/supabase-server.ts`) předává JWT správně
pro `.rpc()` volání, ale **ne** pro PostgREST `.from().select()` dotazy.

Symptom: `auth.uid()` v RLS politikách vrací NULL při `.from()` dotazech
ze Server Componentů, přestože:
- Session cookie existuje (`sb-*-auth-token`)
- `supabase.auth.getUser()` vrátí správného uživatele
- `.rpc('current_guardian_id')` vrátí správné UUID
- SQL Editor s `set_config('request.jwt.claims', ...)` funguje správně

### Diagnostika

Průběh debugování (pro budoucí referenci):

1. `is_guardian()` přes `.rpc()` → `true` ✅
2. `current_guardian_id()` přes `.rpc()` → správné UUID ✅
3. `.from('tridni_kniha_zaznamy').select()` → `count=0`, `error=null` ❌
4. Admin klient (service role) → záznamy viditelné ✅
5. Přímý SQL s `set_config(request.jwt.claims)` → 161 záznamů ✅
6. RLS politiky správné, SECURITY DEFINER, search_path=public ✅

Závěr: JWT token se k PostgREST REST endpointu (`/rest/v1/`) nedostane správně
ze server-side Next.js kontextu. Příčina není plně objasněna — může jít
o bug v `@supabase/ssr` nebo v interakci s Next.js 16 App Router RSC.

### Řešení

**Kanonický vzor pro guardian portál:** vždy používat `.rpc()` místo `.from()`
pro dotazy kde závisí na `auth.uid()` v RLS kontextu.

```typescript
// NEFUNGUJE pro guardiana v Server Component:
const { data } = await supabase
  .from('tridni_kniha_zaznamy')
  .select('...')
  .eq('school_year', CURRENT_SCHOOL_YEAR)

// FUNGUJE:
const { data } = await supabase
  .rpc('get_tridni_kniha_for_guardian', {
    p_school_year: CURRENT_SCHOOL_YEAR,
    p_datum_od: datumOd,
    p_datum_do: datumDo,
  })
```

**Poznámka:** Tento problém se týká pouze guardian portálu. Staff dashboard
používá stejný `createSupabaseServerClient()` a `.from()` funguje — pravděpodobně
proto že staff RLS politiky používají `current_staff_role()` která interně
čte `staff` tabulku přes `auth.uid()`, ale jiným mechanismem než guardian politiky.

### Obecné pravidlo pro portálové moduly

Každý nový portálový modul který potřebuje filtrovat data dle guardiana
**musí** používat SECURITY DEFINER RPC funkci místo přímého `.from()`.

Vzor RPC funkce:
```sql
CREATE OR REPLACE FUNCTION get_[modul]_for_guardian(...)
RETURNS TABLE (...)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ...
  FROM [tabulka]
  WHERE ...
    AND EXISTS (
      SELECT 1
      FROM student_guardian_links sgl
      JOIN guardians g ON g.id = sgl.guardian_id
      WHERE g.user_id = auth.uid()
      AND ...
    )
  ORDER BY ...;
$$;
```

---

## 51. RPC funkce `get_tridni_kniha_for_guardian` (2026-06-02)

### Schéma

```sql
CREATE OR REPLACE FUNCTION get_tridni_kniha_for_guardian(
  p_school_year TEXT,
  p_datum_od DATE,
  p_datum_do DATE
)
RETURNS TABLE (
  id UUID,
  datum DATE,
  den_v_tydnu CHAR(2),
  cas_od TIME,
  cas_do TIME,
  nazev TEXT,
  popis TEXT,
  typ_zaznamu TEXT,
  school_year TEXT,
  group_id UUID,
  svp_vystupy JSONB
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    tkz.id, tkz.datum, tkz.den_v_tydnu, tkz.cas_od, tkz.cas_do,
    tkz.nazev, tkz.popis, tkz.typ_zaznamu, tkz.school_year, tkz.group_id,
    COALESCE(
      (SELECT jsonb_agg(jsonb_build_object(
        'kod', sv.kod,
        'predmet', sv.predmet,
        'rocnik', sv.rocnik,
        'vystup_text', sv.vystup_text
      ))
      FROM svp_vazby vz
      JOIN svp_vystupy sv ON sv.id = vz.vystup_id
      WHERE vz.zaznam_id = tkz.id),
      '[]'::jsonb
    ) AS svp_vystupy
  FROM tridni_kniha_zaznamy tkz
  WHERE tkz.school_year = p_school_year
    AND tkz.datum BETWEEN p_datum_od AND p_datum_do
    AND (
      tkz.group_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM group_memberships gm
        JOIN student_guardian_links sgl ON sgl.student_id = gm.student_id
        JOIN guardians g ON g.id = sgl.guardian_id
        WHERE gm.group_id = tkz.group_id
          AND gm.school_year = tkz.school_year
          AND g.user_id = auth.uid()
          AND (sgl.platnost_do IS NULL OR sgl.platnost_do >= CURRENT_DATE)
      )
    )
  ORDER BY tkz.datum DESC;
$$;
```

### Poznámky k implementaci

- ŠVP výstupy jsou agregované jako `JSONB` (ne FK join) — obchází problém
  s PostgREST embedded select pro guardian kontext
- `group_id IS NULL` větev: záznamy bez skupiny (prázdniny, celoškolní akce)
  jsou viditelné všem guardianům
- `COALESCE(..., '[]'::jsonb)` zajistí že záznamy bez ŠVP výstupů vrátí
  prázdné pole místo NULL

### Nasazení

Funkce byla vytvořena přímo v Supabase SQL Editoru (ne jako migrační soubor).
Pro audit a reprodukovatelnost přidat do `supabase/migrations/027b_rpc_tridnice_guardian.sql`.

---

## 52. Aktualizace migrace 027 — `tkz_guardian_select` (2026-06-02)

Původní politika z migrace 027 používala `guardian_can_access_student()`:

```sql
-- PŮVODNÍ (nefunkční):
CREATE POLICY "tkz_guardian_select" ON tridni_kniha_zaznamy FOR SELECT
USING (
  is_guardian()
  AND (group_id IS NULL OR EXISTS (
    SELECT 1 FROM group_memberships gm
    WHERE gm.group_id = tridni_kniha_zaznamy.group_id
      AND gm.school_year = tridni_kniha_zaznamy.school_year
      AND guardian_can_access_student(gm.student_id)
  ))
);
```

Přepsána na přímý JOIN bez helper funkce:

```sql
-- AKTUÁLNÍ (funkční):
CREATE POLICY "tkz_guardian_select" ON tridni_kniha_zaznamy FOR SELECT
USING (
  is_guardian()
  AND (group_id IS NULL OR EXISTS (
    SELECT 1
    FROM group_memberships gm
    JOIN student_guardian_links sgl ON sgl.student_id = gm.student_id
    JOIN guardians g ON g.id = sgl.guardian_id
    WHERE gm.group_id = tridni_kniha_zaznamy.group_id
      AND gm.school_year = tridni_kniha_zaznamy.school_year
      AND g.user_id = auth.uid()
      AND (sgl.platnost_do IS NULL OR sgl.platnost_do >= CURRENT_DATE)
  ))
);
```

**Důvod:** `guardian_can_access_student()` volá `current_guardian_id()` která
volá `auth.uid()` — přidaná úroveň indirection pravděpodobně způsobovala
problém v RLS kontextu. Přímý `auth.uid()` v politice funguje.

**Poznámka:** Politika je pro portál fakticky nahrazena RPC funkcí (sekce 51),
ale zůstává v DB jako správná definice přístupu.

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat (doporučeno):

```
└── 027b_rpc_tridnice_guardian.sql  ← get_tridni_kniha_for_guardian RPC funkce
```

Aktualizovat `app/portal/tridnice/page.tsx`:
- Dotaz přepsán z `.from('tridni_kniha_zaznamy')` na `.rpc('get_tridni_kniha_for_guardian')`
- ŠVP výstupy čteny z `zaznam.svp_vystupy` (JSONB array) místo nested PostgREST joinu
