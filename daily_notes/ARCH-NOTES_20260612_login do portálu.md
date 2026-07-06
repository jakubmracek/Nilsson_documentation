---

## §61 — Guardian lookup v portal layoutu přes SECURITY DEFINER RPC

**Symptom:** Rodič se po zadání OTP kódu přihlásil, ale byl přesměrován na `/[[Přehled]]` místo do [[Rodičovský portál]].

**Příčina:** `app/portal/layout.tsx` dělal lookup guardiana přímým `.from('guardians')` přes `createSupabaseServerClient()` — tři dotazy (lookup podle `user_id`, auto-link lookup podle emailu, UPDATE `user_id`). Všechny tiše selhaly kvůli RLS/JWT problému v SSR kontextu (§50–52): žádná chyba, jen prázdný výsledek. `guardian` zůstal `null` → fallback `redirect('/[[Přehled]]')`.

**Canonical fix:** SECURITY DEFINER RPC `get_or_link_guardian_self()` — migrace `033_guardian_self_rpc.sql`. Lookup i auto-link atomicky v jedné funkci:

```sql
CREATE OR REPLACE FUNCTION get_or_link_guardian_self()
RETURNS TABLE (id UUID, first_name TEXT, last_name TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
BEGIN
  -- 1) Už nalinkovaný guardian
  RETURN QUERY
    SELECT g.id, g.first_name, g.last_name
    FROM guardians g
    WHERE g.user_id = auth.uid();
  IF FOUND THEN RETURN; END IF;

  -- 2) Auto-link při prvním přihlášení (case-insensitive email)
  RETURN QUERY
    UPDATE guardians g
    SET user_id = auth.uid()
    WHERE lower(g.email) = lower(auth.email())
      AND g.user_id IS NULL
    RETURNING g.id, g.first_name, g.last_name;
END;
$fn$;

GRANT EXECUTE ON FUNCTION get_or_link_guardian_self() TO authenticated;
```

Bezpečnost: funkce nepřijímá žádné parametry, klíčuje výhradně na `auth.uid()` / `auth.email()` volajícího. Bonus oproti původnímu kódu: porovnání emailu je case-insensitive.

V `portal/layout.tsx`:

```typescript
const { data: guardianRows } = await (supabase as any)
  .rpc('get_or_link_guardian_self')

const guardian = (guardianRows as { id: string; first_name: string; last_name: string }[] | null)?.[0] ?? null

if (!guardian) redirect('/portal/login?error=not_guardian')
```

Fallback změněn z `redirect('/[[Přehled]]')` na `redirect('/portal/login?error=not_guardian')` — klíč `not_guardian` už v `ERROR_MESSAGES` portálového loginu existoval (pozor na duplicitu při patchování). Tímto je dřívější auto-link pattern v `portal/layout.tsx` (přímé `.from()` dotazy) **nahrazen** — starší zmínky o něm v těchto poznámkách už neplatí.

---

## §62 — trailingSlash: true a tvrdé redirecty

Projekt má v `next.config` nastaveno `trailingSlash: true`. Důsledky:

- **`window.location.href`** (tvrdé redirecty po OTP přihlášení, §57) **musí** mít lomítko na konci:
  - `/portal/[[Omluvenky]]/` — bez lomítka 404
  - `/[[Přehled]]/` — bez lomítka fungovalo jen díky 308 redirectu navíc, sjednoceno
- **Server-side `redirect()`** z `next/navigation` lomítko nepotřebuje — Next si URL normalizuje sám (`/portal/login` v layoutu je OK).

Pravidlo: každý nový tvrdý redirect (`window.location.href`, `Location` header v route handlerech) psát s koncovým lomítkem.