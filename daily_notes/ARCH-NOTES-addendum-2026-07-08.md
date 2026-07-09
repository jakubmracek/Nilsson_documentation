# ARCH-NOTES Addendum — 2026-07-08
# Supabase Security Advisor: kompletní průchod nálezů, migrace 049–055

Navazuje na §1–91 (poslední: ARCH-NOTES-addendum-2026-07-07.md, enrollment
frontend + produkční smoke test). Tahle session neřešila enrollment
funkčnost, ale prošla celý výstup Supabase Database Linter / Security
Advisor a odstranila nalezené bezpečnostní nálezy jednu kategorii po
druhé. Zapsáno v jednom addendu, protože nálezy na sebe navazují (dvě
migrace musely být přepsány poté, co se ukázalo, že neproběhly, nebo
proběhly a přesto neměly efekt).

---

## §92 — Migrace 049: RLS na RÚIAN referenčních tabulkách

`ruian_okresy`, `ruian_obce`, `ruian_adresni_mista` (import ČÚZK CSV,
§ viz předchozí addenda k RÚIAN adresní validaci) neměly zapnutou RLS
vůbec — linter `rls_disabled_in_public`. Jde o veřejná, pouze ke čtení
určená referenční data (validace adresy v zápisu), takže řešením není
uzavřít je, ale zapnout RLS a přidat permissive `SELECT` politiku pro
`anon`+`authenticated`, se zachováním konvence **FORCE RLS everywhere**:

```sql
ALTER TABLE public.ruian_okresy ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ruian_okresy FORCE ROW LEVEL SECURITY;
CREATE POLICY "ruian_okresy_select_public" ON public.ruian_okresy
  FOR SELECT TO anon, authenticated USING (true);
-- totéž pro ruian_obce, ruian_adresni_mista
```

Žádné INSERT/UPDATE/DELETE politiky — zápis dělá jen import job pod
`service_role` (RLS bypass), `anon`/`authenticated` k zápisu nemají
důvod.

---

## §93 — Migrace 050 → 052: `search_path` mutable na 21 funkcích

21 funkcí (většinou trigger funkce — audit, soft lock, `set_updated_at`,
`essl_generuj_*`, plus pár utilit jako `generate_kod_zaka`,
`is_school_holiday`) nemělo nastavený `search_path`, lint
`function_search_path_mutable`.

**Dvě selhané iterace, než to prošlo:** první pokus (migrace 050) použil
`DO $$ ... $$` blok s cyklem přes `pg_proc` (dynamické `ALTER FUNCTION`
podle jména, ne ručně psané signatury) — v Supabase SQL editoru se
spustil bez chyby, ale **neměl žádný efekt** (`proconfig` zůstal `null`
u všech 21). Příčina nikdy nebyla s jistotou zjištěna (podezření na to,
že SQL editor `DO` blok s více statementy uvnitř nezpracoval podle
očekávání) — spíš než to ladit dál, migrace 052 přepsala totéž jako
21 explicitních, ručně vypsaných `ALTER FUNCTION ... SET search_path`
příkazů (žádné cykly, žádné dynamické SQL). Ta prošla napoprvé.

```sql
ALTER FUNCTION public.is_school_holiday(date) SET search_path = public, pg_temp;
-- + 20 dalších, viz 052_security_fixes_explicit.sql
```

**Obecné poučení:** `DO` bloky s cyklem přes `pg_proc` v Supabase SQL
editoru jsou nespolehlivé pro hromadné DDL opravy — nekonzistentně
"tiše neudělají nic", aniž by vyhodily chybu. Pro budoucí hromadné
opravy psát explicitní staticky vypsané příkazy (i když je jich 20+),
ne dynamické `EXECUTE format(...)` cykly. Diagnostikovat přes
`pg_proc.oid::regprocedure` (přesná signatura včetně přetížení) a
`pg_proc.proconfig`/`has_function_privilege(...)` PŘED i PO každé dávce,
ne věřit "proběhlo bez chyby" = "udělalo se".

---

## §94 — Migrace 053: `PUBLIC` execute grant — stejná past jako §82, jinde

Po 052 zůstalo 24 z 25 `SECURITY DEFINER` funkcí (kategorie "admin/
interní RPC", viz §98) pořád volatelných rolí `anon`, přestože migrace
050/052 explicitně dělala `REVOKE EXECUTE ... FROM anon`. Diagnostika
přes `pg_proc.proacl` potvrdila: všech 24 mělo `=X/postgres` záznam —
tedy `EXECUTE` udělené roli `PUBLIC`, kterou `anon` dědí bez ohledu na
jakýkoli přímý `REVOKE` cílený na `anon` samotné.

**Tohle je přesně stejná past jako §82** (migrace 045, enrollment
bootstrap RPC) — jen objevená nezávisle na jiné sadě funkcí o pár týdnů
později. Řešení identické:

```sql
REVOKE EXECUTE ON FUNCTION public.admin_unlock_semester_record(uuid) FROM PUBLIC;
-- + 23 dalších, viz 053_revoke_public_execute.sql
-- authenticated/service_role měly už explicitní pojmenované granty,
-- takže revoke PUBLIC je neovlivnil — žádný re-GRANT nebyl potřeba
```

Jedna funkce (`bulletin_resolve_recipients`) `PUBLIC` grant neměla od
začátku (jen pojmenované granty pro `authenticated`/`service_role`) —
proto jako jediná fungovala už po migraci 050/052.

**Poučení (doplnění k §82, teď potvrzené podruhé nezávisle):** `REVOKE
EXECUTE ... FROM anon` bez odpovídajícího `REVOKE ... FROM PUBLIC` je
**systematicky nespolehlivé**, ne ojedinělá náhoda. Standardní vzor pro
nové `SECURITY DEFINER` funkce v tomhle projektu od teď:

```sql
CREATE FUNCTION public.nazev(...) ... SECURITY DEFINER ...;
REVOKE EXECUTE ON FUNCTION public.nazev(...) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.nazev(...) TO authenticated;  -- jen pokud má být volatelná
```
Nikdy nespoléhat na to, že `REVOKE FROM anon` samo o sobě něco uzavírá.

---

## §95 — Migrace 051: `email_events.ee_insert` — PUBLIC INSERT policy

`ee_insert` politika (`WITH CHECK (true)`) platila pro `PUBLIC` (tedy
i `anon`) — kdokoli se znalostí veřejného `anon` klíče mohl vložit
libovolný falešný email event (např. tvrdit, že rodič otevřel email,
který nikdy nedostal). Lint: `rls_policy_always_true`.

Prošetření všech zápisových cest v kódu (`grep "from('email_events')"`)
odhalilo tři různé role:
- `app/api/bulletin/posts/route.ts`, `.../[id]/send/route.ts` —
  `createSupabaseServerClient()` s `auth.getUser()` kontrolou → `authenticated`
- `app/api/webhooks/resend/route.ts` — `createSupabaseAdmin()` →
  `service_role` (RLS bypass, nepotřebuje policy vůbec)
- `lib/enrollment/send-guardian-invite.tsx` — **nikde nevolaná, nezapojený
  kód** (viz TODO níže), žádná runtime role k řešení teď

Řešení: zúžit politiku na `TO authenticated` (ne úplně zrušit — zrušení
by rozbilo oba živé bulletin endpointy) + odebrat `anon` INSERT grant
na úrovni tabulky jako defense-in-depth:

```sql
DROP POLICY IF EXISTS ee_insert ON public.email_events;
CREATE POLICY ee_insert ON public.email_events
  FOR INSERT TO authenticated WITH CHECK (true);
REVOKE INSERT ON public.email_events FROM anon;
```

**Očekávaný trvalý WARN:** lint `rls_policy_always_true` kontroluje jen
literální `WITH CHECK (true)`, nekouká na omezení role — takže tenhle
nález zůstane v Security Advisoru viditelný natrvalo, i když je teď
bezpečně omezený na `authenticated`. Vědomě přijato, nejde o
nedokončenou práci.

---

## §96 — Migrace 054: `unaccent` extension mimo `public` schéma

Lint `extension_in_public`. Jediný nalezený "spotřebitel" extension byl
vlastní `IMMUTABLE` wrapper `immutable_unaccent(text)` (RÚIAN adresní
validace, `enrollment_validate_address`, migrace 041) — a ten měl už
od svého vzniku nastavený `SET search_path TO 'extensions', 'public',
'pg_temp'`, tedy s předstihem počítal přesně s tímhle přesunem, i když
schéma `extensions` do teď neexistovalo (Postgres neexistující schéma
v `search_path` tiše přeskočí, bez chyby).

```sql
CREATE SCHEMA IF NOT EXISTS extensions;
ALTER EXTENSION unaccent SET SCHEMA extensions;
```

Nulová úprava potřebná u volajících funkcí. Ověřeno end-to-end smoke
testem formuláře zápisu s diakritikou v adrese po nasazení.

---

## §97 — Migrace 055: `resolve_bozp_alerts` — přehlédnuto v původní triáži

Po vyřešení §94 zůstalo 29 `anon_security_definer_function_executable`
nálezů (očekávaně, viz §98 kategorie "záměrně veřejné") — až na dvě
výjimky, které do žádné z původních kategorií nezapadaly čistě.
`staff_can_access_student` posouzeno jako neškodný boolean helper
(stejná rodina jako `can_read_student`, `guardian_can_access_student`)
a ponecháno beze změny. `resolve_bozp_alerts(p_student_id uuid)` ale je
podle názvu i účelu **staff akce** (označení BOZP alertu jako
vyřešeného) — stejná kategorie jako `generate_bozp_alerts`, který už
byl uzavřen v §94. Doplněno:

```sql
REVOKE EXECUTE ON FUNCTION public.resolve_bozp_alerts(uuid) FROM PUBLIC;
```

---

## §98 — Zbývající stav Security Advisoru: co je vědomě ponecháno

Po migracích 049–055 klesl počet WARN z ~130 na 86, které se dále
nesnižují — rozpad:

**1× `rls_policy_always_true`** (`email_events.ee_insert`) — viz §95,
očekávaný trvalý nález, funkčně bezpečný.

**29× `anon_security_definer_function_executable`** — funkce záměrně
volatelné nepřihlášeným návštěvníkem (guardian self-service před
napojením účtu — `is_guardian()`, `current_guardian_id()`,
`enrollment_classify_age`, `get_lunch_menu_week`, `set_consent`, atd.).
Tyhle si samy hlídají identitu volajícího uvnitř těla funkce
(`auth.uid()`, `current_guardian_id()`) místo spoléhání na GRANT vrstvu
— to je záměrná architektura, ne mezera. Neprocházeno jednotlivě kód
po kódu v týhle session (viz TODO níže).

**56× `authenticated_security_definer_function_executable`** — v
podstatě nevyhnutelný zbytek dané architektury. Lint takhle označí
*každou* `SECURITY DEFINER` funkci volatelnou `authenticated` rolí, a
Nilsson jich má desítky záměrně (RLS + `SECURITY DEFINER` helpery s
interní `is_director()`/`has_role()`/vlastnickou kontrolou, ne syrové
RLS politiky všude). Level `WARN`, ne `ERROR` — Supabase to sám
kvalifikuje jako běžný, často správný vzor. Úplné odstranění by
vyžadovalo převod na `SECURITY INVOKER` u všech, což by u funkcí
potřebujících obejít RLS mezi tabulkami (typicky cross-table `EXISTS`
kontroly, viz §83) rozbilo funkčnost. **Vědomě přijaté architektonické
riziko, ne dluh k doplacení.**

---

## Shrnutí migrací týhle session

| Migrace | Obsah |
|---|---|
| 049 | RLS enable + force na 3 RÚIAN tabulkách |
| 050 | (nahrazeno 052 — `DO` blok neměl efekt, viz §93) |
| 051 | `email_events.ee_insert` zúžen na `authenticated`, `anon` INSERT grant odebrán |
| 052 | `search_path` fix na 21 funkcích (explicitní přepis 050) |
| 053 | `REVOKE EXECUTE ... FROM PUBLIC` na 24 admin/interních RPC (viz §94) |
| 054 | `unaccent` extension přesunuta do schématu `extensions` |
| 055 | `resolve_bozp_alerts` — `REVOKE FROM PUBLIC`, přehlédnuto v původní triáži |

---

## TODO do budoucna (nerozhodnuto/neopraveno v týhle session)

1. **`auth_leaked_password_protection`** — blokováno: dostupné jen od
   Supabase Pro plánu výš. Zjistit, na jakém plánu Nilsson projekt běží;
   pokud Free, jde o vědomě přijaté riziko do případného upgradu.
2. **`lib/enrollment/send-guardian-invite.tsx`** — hotový, ale nikde
   nezapojený kód (§95). Až se bude zapojovat do route, doplnit
   `auth.getUser()` kontrolu po vzoru obou bulletin routes (teď chybí).
   RLS na `email_events` už počítá s `authenticated` rolí, takže by
   žádná další DB změna neměla být potřeba.
3. Projít jednotlivě 29 `anon_security_definer_function_executable`
   nálezů (§98) kód po kódu, ne jen podle názvu funkce — potvrdit, že
   každá skutečně validuje volajícího uvnitř těla, ne jen podle
   pravděpodobného účelu z názvu.
4. Zvážit standardizaci vzoru `REVOKE FROM PUBLIC` + explicitní `GRANT`
   (§94) do šablony/checklistu pro každou novou `SECURITY DEFINER`
   funkci od teď — ideálně vynutit review krokem, ne spoléhat na to, že
   si to příště někdo vzpomene ručně.
