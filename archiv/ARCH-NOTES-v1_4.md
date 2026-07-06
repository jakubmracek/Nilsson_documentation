# vilekula-is — Architekturické poznámky a rozhodnutí

> Dokument zachycuje klíčová architekturická rozhodnutí, vzory a jejich zdůvodnění.
> Určen pro vývojáře (i pro budoucí Jakub+Claude session) — odpovídá na otázku "proč takhle?"
>
> Verze: 1.4 | Datum: 2026-05-06 | Navazuje na TRD v1.5

---

## 1. RLS — Helper funkce

### Proč `SECURITY DEFINER + STABLE`?

Bez `SECURITY DEFINER` by politiky na tabulce `staff` způsobily **nekonečnou rekurzi**:
politika čte `staff` → `staff` má RLS → politika volá politiku → ∞

`SECURITY DEFINER` funkce tuto smyčku přeruší — funkce běží s právy definujícího
uživatele a RLS na `staff` obchází.

`STABLE` zajistí, že výsledek se cachuje **per-query, ne per-row**.
Bez toho by `can_read_student()` volal databázi jednou za každý řádek výsledku
(při 20 žácích = 20 SQL dotazů místo 1).

### Hierarchie helper funkcí

```
current_staff_id()
current_staff_role()
    ↓
is_director()
is_director_or_vp()
staff_can_access_student()
    ↓
can_read_student()       ← používán ve většině politik
can_read_guardian()      ← odvozena ze student přístupu
```

Každá funkce na vyšší úrovni staví na těch níže — testovat zdola nahoru.

### Sanity check po každé migraci (sekce J v 006_rls.sql)

```sql
-- RLS zapnuté na všech tabulkách:
SELECT tablename, rowsecurity, forcerowsecurity
  FROM pg_tables WHERE schemaname = 'public'
 ORDER BY tablename;
-- Očekávaný výsledek: rowsecurity=true, forcerowsecurity=true pro všechny

-- Helper funkce mají správné atributy:
SELECT proname, prosecdef, provolatile FROM pg_proc
  JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
 WHERE pg_namespace.nspname = 'public'
   AND proname LIKE '%staff%' OR proname LIKE '%director%';
-- Očekávaný výsledek: prosecdef=true, provolatile='s' (STABLE)
```

---

## 2. Dvojí audit mechanismus

Dvě komplementární vrstvy — obě jsou nutné, každá slouží jinému účelu.

| | `students_audit` | `student_matrika_changes` |
|---|---|---|
| **Typ** | Technická pojistka | Právní dokladová vrstva |
| **Kdo plní** | Databázový trigger (automaticky) | Uživatel v UI (ručně) |
| **Obsah** | JSON snapshot před/po | Lidsky čitelný popis změny |
| **Datum** | Technický timestamp | Datum reálné události |
| **Immutabilní** | Ano | Ano (RULE) |
| **Pro koho** | Forenzní analýza, debugging | ČŠI, právní doložení |

**Klíčový rozdíl:** `datum_zmeny` v `student_matrika_changes` je datum **reálné události**,
ne technický timestamp. Příklad: rozsudek soudu ze dne 15. 3., zapsáno do IS 20. 3.
→ `datum_zmeny = 15. 3.`, `created_at = 20. 3.`

Stejný vzor aplikovat analogicky na: `tridni_kniha_changes` (viz sekce 4).

---

## 3. Soft lock vzor

Designový vzor aplikovaný konzistentně v třídní knize a matrice.

**Princip:**
- `locked = false` → normální editace, bez zvláštního záznamu
- `locked = true` → editace stále technicky možná, ale každá změna vyžaduje:
  1. záznam v příslušné `_changes` tabulce
  2. vyplnění `duvod_zmeny` v UI (povinné pole)
- Zamčení per školní rok (ne per záznam) — potvrzuje ředitel na konci roku
- Odemčení: pouze role `director`, také se zaloguje

**Implementace:**
```sql
-- Trigger varuje (neblokuje) — aplikační vrstva zajistí audit záznam
CREATE TRIGGER trg_soft_lock_check
  BEFORE UPDATE ON tridni_kniha_zaznamy
  FOR EACH ROW EXECUTE FUNCTION check_soft_lock_tridni_kniha();
```

**Kde se vzor používá:**
- `tridni_kniha_zaznamy` + `tridni_kniha_changes` + `tridni_kniha_skolni_rok`
- Analogicky: matriční data po uzavření školního roku

---

## 4. Append-only tabulky

Některé tabulky jsou záměrně append-only (nelze UPDATE ani DELETE):

| Tabulka | Důvod |
|---------|-------|
| `student_contracts` | Právní dokument |
| `disciplinary_measures` | Právní dokument (výchovná opatření) |
| `student_matrika_changes` | Immutabilní audit log |
| `tridni_kniha_changes` | Immutabilní audit log |

Implementace přes PostgreSQL RULE:
```sql
CREATE RULE no_update_X AS ON UPDATE TO X DO INSTEAD NOTHING;
CREATE RULE no_delete_X AS ON DELETE TO X DO INSTEAD NOTHING;
```

**Jak opravit chybu v append-only tabulce:**
Vložit nový záznam s opravou + poznámkou `zdroj_zmeny = 'interní korekce chyby'`.
Nikdy nemazat původní záznam.

---

## 5. Identifikátory žáka — tři různé, každý pro jiný účel

| Identifikátor | Formát | Mutable | Účel |
|---|---|---|---|
| `id` (UUID) | `uuid` | NE | Interní FK |
| `kod_zaka` | `VIL-{rok_nar}-{NNNN}` | NE | Komunikace, variabilní symbol |
| `vs_interni` | historický string | NE | Import ze Sheets, zpětná kompatibilita |
| `kod_zaka_msmt` | max 10 znaků | NE | MŠMT anonymizovaný soubor „a" |
| `birth_number` | RČ | jen §28/4 | XML výkazy (šifrovat!) |

**`kod_zaka` — trojitá ochrana proti duplicitě:**
1. PostgreSQL sekvence `kod_zaka_seq` (monotónní, `NO CYCLE`)
2. `IF EXISTS` check s `RAISE EXCEPTION` v `generate_kod_zaka()`
3. `UNIQUE` constraint na sloupci

**Formát:** `VIL-{rok_narozeni}-{NNNN}` kde NNNN je **globální** pořadové číslo
(ne per rok — jinak by mohly vzniknout kolize). Rok je jen informativní prefix.

---

## 6. `set_updated_at()` — vlastní trigger, žádná extension

`pg_moddatetime` extension **nepoužíváme** — závislost na třetí straně pro tak
základní věc není žádoucí. Pokud Supabase změní dostupnost extension, přestane
nám fungovat `updated_at` na všech tabulkách.

Místo toho vlastní funkce v `000_init.sql` — 5 řádků, plně pod kontrolou,
funguje na jakémkoliv PostgreSQL.

Aplikovat na každou tabulku s `updated_at`:
```sql
CREATE TRIGGER trg_{tabulka}_updated_at
  BEFORE UPDATE ON {tabulka}
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 7. Pořadí spouštění migrací

```
000_init.sql          ← extensions, ENUM typy, sdílené funkce, sekvence, system_alerts
001_matrika.sql       ← tabulky Fáze 1 (matrika)
006_rls.sql           ← RLS politiky Fáze 1
002_communication.sql ← Fáze 2 (komunikace, Resend)
003_payments.sql      ← Fáze 2 (platby, Fio API)
004_tridni_kniha.sql  ← Fáze 3 (třídní kniha, docházka)
005_vp.sql            ← VP modul
006_rls.sql           ← doplnit o VP politiky po spuštění 005_vp.sql
```

**Kritická závislost:** `006_rls.sql` musí běžet PO `001_matrika.sql`
(tabulky musí existovat před definicí politik).

`system_alerts.resolved_by` FK na `staff(id)` se přidává v `001_matrika.sql`
přes `ALTER TABLE` — `staff` v době `000_init.sql` ještě neexistuje.

---

## 8. Resend jako jediný emailový provider

Žádný druhý email provider. Resend obsluhuje:
- **Auth:** Supabase magic link přes vlastní SMTP
  (`smtp.resend.com:465`, API key jako heslo)
- **Transakční emaily:** Edge Function → Resend API
- **VP notifikace lhůt:** Resend + Discord webhook

**Proč vlastní SMTP pro Supabase Auth:**
Free tier Supabase má limit **2 magic linky/hodinu** na adresu, nelze změnit.
Vlastní SMTP tento limit ruší. Konfigurace:
`Supabase → Project Settings → Auth → SMTP Settings`

---

## 9. `school_year` — formát TEXT '2025/2026'

Konzistentní formát napříč **celým systémem** — ne integer, ne daterange.
Důvod: přirozeně čitelný, snadno filtrovatelný, konzistentní s MŠMT konvencí.

Příklady použití: `groups.school_year`, `group_memberships.school_year`,
`staff_groups.school_year`, `tridni_kniha_zaznamy.school_year`, `bozp_zaznamy.school_year`

> **Oprava (007_fixes.sql):** `tridni_kniha_zaznamy` i `bozp_zaznamy` původně
> používaly sloupec `skolni_rok CHAR(9)`. Přejmenováno na `school_year TEXT`
> pro konzistenci s touto sekcí. Dotčeny: definice tabulek, indexy,
> triggery `check_skolni_rok_exists` a `enforce_soft_lock_tridni_kniha`.

---

## 10. `FORCE ROW LEVEL SECURITY`

Všechny tabulky mají `FORCE ROW LEVEL SECURITY` (nejen `ENABLE`).

Bez `FORCE` by Supabase `service_role` (používaný v Edge Functions)
automaticky obcházel RLS. S `FORCE` platí politiky i pro `service_role`.

Edge Functions musí explicitně používat `supabase.auth.admin` klienta
s konkrétním `user_id` pokud potřebují elevated přístup.

---

## 14. VP alerty — architektura a deduplication vzor (007_fixes.sql)

### `generate_vp_alerts()` — správná struktura INSERT

Funkce plní `system_alerts` a musí respektovat skutečné schéma tabulky
(definované v TRD sekci 2.3). Tři časté chyby při zápisu alert-generátorů:

1. **Jméno žáka:** `students.first_name / last_name` — ne `jmeno / prijmeni`
   (MŠMT konvence, ale `students` tabulka používá anglické názvy sloupců).

2. **Sloupec pro odkaz na entitu:** `entity_id` — ne `ref_id`.
   `ref_id` není a nikdy nebylo součástí `system_alerts` schématu.

3. **`alert_type` je NOT NULL:** Každý INSERT musí předat `alert_type`
   (`'deadline'`, `'missing_doc'`, `'missing_consent'`, …).
   Opomenutí způsobí runtime chybu, ne compile-time.

### Deduplication vzor

Každý alert-generátor musí před INSERTem zkontrolovat duplikáty:

```sql
-- Správný vzor — deduplication přes (entity_id, alert_type, module, resolved_at):
IF NOT EXISTS (
  SELECT 1 FROM system_alerts
   WHERE entity_id  = v_ref_id
     AND alert_type = 'deadline'      -- konkrétní typ, ne generický
     AND module     = 'vp'
     AND resolved_at IS NULL          -- ignorovat vyřešené alerty
) THEN
  INSERT INTO system_alerts
    (module, alert_type, severity, entity_type, entity_id, message)
  VALUES (...);
END IF;
```

Kombinace `(entity_id, alert_type, module, resolved_at IS NULL)` je dostatečně
selektivní pro všechny dosavadní typy alertů. `message LIKE '%...%'` lze
přidat jako zpřesnění (viz alerty 1–3 s `alert_type = 'deadline'`
kde jeden `entity_id` může mít více deadline alertů různého druhu).

### `is_vp()` — `SET search_path = public`

Všechny SECURITY DEFINER helper funkce v `006_rls.sql` **musí** mít
`SET search_path = public`. Bez toho je funkce zranitelná vůči
`search_path` injection útokům (útočník vytvoří vlastní schéma s tabulkou
`staff` a podvrhne výsledek).

Kontrolní dotaz po každé migraci (rozšíření sanity checku ze sekce 1):

```sql
SELECT proname, proconfig
  FROM pg_proc
  JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
 WHERE pg_namespace.nspname = 'public'
   AND proname IN ('is_director', 'is_director_or_vp', 'is_vp',
                   'current_staff_role', 'current_staff_id',
                   'staff_can_access_student', 'can_read_student');
-- Očekávaný výsledek: proconfig obsahuje 'search_path=public' pro VŠECHNY funkce
```



---

## 11. Komunikační modul — klíčová rozhodnutí (Fáze 2)

### Absence_requests: Varianta A (bez rodičovského portálu)

Pro v1 (září 2026) zákonní zástupci **nemají vlastní auth**. Workflow:
1. ZZ nahlásí absenci (email, telefon, WhatsApp)
2. Průvodce zapíše do IS

Dva oddělené sloupce v `absence_requests`:
- `requested_by_guardian_id` = od koho žádost pochází (právní původ)
- `entered_by_staff_id` = kdo zapsal do IS (odpovědnost)

**Migrační cesta k rodičovskému portálu** (až přijde):
- `entered_by_staff_id` se stane `nullable`
- přidá se `guardian_user_id UUID REFERENCES auth.users(id)`
- INSERT politika se rozšíří o `auth.uid() = guardian_user_id`

Rodičovský portál je **OUT OF SCOPE** pro v1, bez konkrétního termínu v TRD.

### comm_log: bez přístupu pro průvodce

`comm_log` je interní delivery info (Resend status). Průvodci a asistenti
k němu přístup nemají — pro svou práci ho nepotřebují.

INSERT a UPDATE do `comm_log` provádí Edge Function (Resend odeslání
+ webhook callback). Edge Function běží v `service_role` kontextu
s `SECURITY DEFINER` — nepotřebuje explicitní INSERT/UPDATE RLS politiku.

### comm_campaigns: individual kampaně mimo dosah průvodce

`target_type = 'individual'` jsou kampaně na konkrétní ZZ — typicky
citlivé (jednání s konkrétní rodinou). Průvodci je nevidí.

Helper funkce `staff_can_read_campaign()` má stejnou strukturu jako
ostatní helper funkce: `SECURITY DEFINER + STABLE`, staví na `current_staff_id()`.

### Constraints přidané oproti TRD

`comm_campaigns`:
- `check_body_not_empty`: alespoň jeden z `body_html` / `body_text`
- `check_target_ref`: `target_ref NOT NULL` právě když `target_type='group'`

`absence_requests`:
- `check_dates`: `date_to >= date_from`
- `check_review_consistency`: `reviewed_by IS NULL = reviewed_at IS NULL`
- `check_reviewed_when_decided`: schválená/zamítnutá žádost musí mít reviewera

### Hierarchie helper funkcí po Fázi 2

```
current_staff_id()
current_staff_role()
    ↓
is_director()
is_director_or_vp()
staff_can_access_student()
    ↓
can_read_student()          ← většina politik students
can_read_guardian()         ← odvozena ze student přístupu
staff_can_read_campaign()   ← komunikační modul (Fáze 2)
```

---

## 12. Soft lock trigger — session variables (Fáze 3)

### Problém

Soft lock třídní knihy vyžaduje, aby trigger při editaci zamčeného záznamu vložil
záznam do `tridni_kniha_changes` — včetně `duvod_zmeny` a `changed_by`, které
pocházejí z aplikační vrstvy, ne z editovaného řádku.

Varianta A (pasivní `RAISE WARNING`) je design klinč — aplikace musí být spolehlivá,
trigger nezaručí nic.
Varianta B (pomocné sloupce na tabulce) je bastl — znečišťuje schema tabulky.

### Řešení: PostgreSQL session variables (`SET LOCAL`)

Aplikace nastaví session proměnné **v téže transakci** před UPDATE:

```sql
BEGIN;
SET LOCAL app.audit_reason = 'oprava překlepu — žádost průvodce Kateřiny';
SET LOCAL app.audit_by     = 'uuid-staff-id';
UPDATE tridni_kniha_zaznamy SET nazev = '...' WHERE id = '...';
COMMIT;
```

Trigger čte proměnné přes `current_setting('app.audit_reason', true)` a:
- Pokud rok **není zamčen** → normální průchod, žádný audit záznam.
- Pokud rok **je zamčen** a proměnná chybí nebo je prázdná → `RAISE EXCEPTION`
  (transakce se rollbackuje, editace se neprovede).
- Pokud rok **je zamčen** a proměnná je vyplněna → trigger vloží do
  `tridni_kniha_changes` per-sloupec záznamy pro každé změněné pole.

### Proč je to čisté

`SET LOCAL` platí **pouze do konce aktuální transakce** — automaticky zaniká
při COMMIT i ROLLBACK. Žádný state leak mezi requesty.
Vzor je etablovaný — Supabase interně používá `request.jwt.claims` stejným mechanismem.

### Per-sloupec diff v triggeru

Trigger porovnává OLD a NEW pro každé sledované pole zvlášť a vkládá jeden řádek
do `tridni_kniha_changes` per změněné pole. Výhoda: UI může zobrazit přesný diff
(„pole `nazev` změněno z X na Y"). Sledovaná pole: všechna editovatelná pole
`tridni_kniha_zaznamy` kromě `updated_at` a `created_at`.

### Design constraint pro aplikační vrstvu

**Každý UPDATE `tridni_kniha_zaznamy` po uzamčení roku MUSÍ:**
1. Být zabalen do explicitní transakce (`BEGIN` … `COMMIT`)
2. Před UPDATE nastavit `SET LOCAL app.audit_reason` a `SET LOCAL app.audit_by`

Toto je zdokumentovat v `ADMIN-GUIDE.md` i v komentářích Next.js API route.

---

## 13. `pruvodci_pravidla` — generátor opakujících se pravidel (Fáze 3)

Implementováno v Fázi 3 (ne odloženo). Architektura: pravidlo definuje opakování
průvodce pro daný den v týdnu v časovém rozsahu. Generátor vyplní `pruvodci_dny`
na zadané období — `ON CONFLICT DO NOTHING` zajistí, že ručně zadané výjimky
v `pruvodci_dny` nejsou přepsány.

**Priorita sloupce při konfliktu:**
`pruvodci_dny` (jednorázový záznam) vždy vítězí nad `pruvodci_pravidla` (pravidlo).
Generátor je tedy bezpečné pustit opakovaně.

**Kdy spustit generátor:**
- Začátek každého pololetí (ředitel manuálně)
- Po změně rozvrhu (nová pravidla s `valid_from`)
- Import historických dat 2025/2026: přímý INSERT do `pruvodci_dny` bez pravidel

---

*Dokument průběžně doplňovat při každé nové session.*

*v1.0 — 2026-04-27 · v1.1 — 2026-04-27 (sekce 11) · v1.2 — 2026-04-28 (sekce 12, 13) · v1.3 — 2026-04-28 (oprava sekce 9, přidána sekce 14 — 007_fixes)*

---

## 15. UI architektura — aplikační vrstva (auth + dashboard)

### 15.1 Dva Supabase klienti

| Soubor | Funkce | Kde použít |
|--------|--------|-----------|
| `lib/supabase.ts` | `createBrowserClient` | Client Components (`'use client'`) |
| `lib/supabase-server.ts` | `createServerClient` + cookies | Server Components, Route Handlers, Server Actions |

Záměna způsobí session leak, RLS bypass nebo runtime chybu.

### 15.2 Middleware → proxy (Next.js 16)

Next.js 16 přejmenoval konvenci `middleware.ts` → `proxy.ts`. Exportovaná funkce se musí jmenovat `proxy`. API je jinak identické.

### 15.3 `getUser()` vs `getSession()` v proxy

Proxy vždy volá `supabase.auth.getUser()` — ověří token proti Supabase Auth serveru. `getSession()` čte JWT z cookie bez server-side validace.

### 15.4 Staff tabulka — skutečné schéma (oprava oproti původnímu návrhu)

| Předpoklad v kódu | Skutečnost |
|---|---|
| `staff.id = auth.uid()` | `staff.user_id = auth.uid()` (separátní sloupec) |
| `staff.is_active` | Sloupec neexistuje |

Opravit ve všech dotazech na staff:
```typescript
// ŠPATNĚ
.eq('id', user.id).select('id, role, is_active')
// SPRÁVNĚ
.eq('user_id', user.id).select('id, role')
```

Dotčené soubory: `app/auth/callback/route.ts`, `app/dashboard/layout.tsx`, `app/dashboard/page.tsx`, `app/api/debug/rls-check/route.ts`.

### 15.5 RLS politiky pro staff (migrace 008)

```sql
CREATE POLICY "staff_read_own_by_user_id" ON staff
  FOR SELECT USING (user_id = auth.uid());
```

### 15.6 Časté problémy při nasazení

- `NEXT_PUBLIC_SUPABASE_URL` nesmí obsahovat `/rest/v1/`
- Redirect URLs v Supabase: přesně `http://localhost:3000/auth/callback`
- OTP link expiruje rychle — kliknout okamžitě po přijetí emailu

### 15.7 Aktuální stav (2026-05-06)

- Migrace 000–008 nasazeny
- Magic link auth funkční na produkci (Vercel)
- Dashboard načítá správnou roli (`director`)
- RLS smoke test: `ok: true`
- `students`: 0 žáků — import dat je další krok
