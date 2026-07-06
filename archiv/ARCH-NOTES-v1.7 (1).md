# vilekula-is — Architekturické poznámky a rozhodnutí

> Dokument zachycuje klíčová architekturická rozhodnutí, vzory a jejich zdůvodnění.
> Určen pro vývojáře (i pro budoucí Jakub+Claude session) — odpovídá na otázku "proč takhle?"
>
> Verze: 1.7 | Datum: 2026-05-08 | Navazuje na TRD v1.8

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

### 15.7 Aktuální stav (2026-05-08)

- Migrace 000–011 nasazeny a ověřeny v produkci (010 = multi-group DDL, 011 = RLS update)
- Magic link auth funkční na produkci (Vercel)
- Dashboard načítá správnou roli (`director`)
- RLS smoke test: `ok: true`
- `students`: 32 žáků importováno (2026-05-07); `guardians`: 50 kontaktů
- Skupiny: I./2025-2026 uzavřena, I./2026-2027 aktivní (32 zápisů)
- SVP: 2 záznamy v `student_matrika_a`; Polák Michael pending (viz sekce 16.5)
- Třídní kniha UI: seznam + formulář nového záznamu + detail nasazeny (viz sekce 17)
- `tridni_kniha_zaznamy`, `pruvodci_dny`, `pruvodci_pravidla`, `tridni_kniha_skolni_rok`
  mají `group_id` (nullable); viz sekce 18

---

*v1.0 — 2026-04-27 · v1.1 — 2026-04-27 (sekce 11) · v1.2 — 2026-04-28 (sekce 12, 13) · v1.3 — 2026-04-28 (oprava sekce 9, přidána sekce 14 — 007_fixes)*
*v1.4 — 2026-05-06 (sekce 15 — UI architektura, proxy.ts, staff.user_id)*
*v1.5 — 2026-05-07 (sekce 16 — import vzory, check_sma_msmt_kod, stav dat)*
*v1.6 — 2026-05-08 (sekce 17 — třídní kniha Fáze 3: RLS, UI stránky)*
*v1.7 — 2026-05-08 (sekce 18 — multi-třídní třídní kniha: migrace 010+011, workflow tříd)*

---

## 18. Multi-třídní třídní kniha (migrace 010 + 011)

### 18.1 Proč group_id a proč teď

ZŠ Vilekula od 2026/2027 rozdělí žáky do dvou tříd. §28/1/f školského zákona
vyžaduje jednu třídní knihu **per třída**. Migrace 009 navrhla třídní knihu jako
školní (ne per-skupinu) — správně pro jednu skupinu, ale nevhodné pro dvě.

`group_id` přidáno jako **nullable** (zpětně kompatibilní):
- Stávající seed data z 009 (`tridni_kniha_skolni_rok` pro 2025/2026 a 2026/2027)
  mají `group_id = NULL` a zůstávají platná bez jakékoli změny.
- Import historických záznamů třídní knihy 2025/2026 (182 ks) proběhne s
  `group_id = UUID skupiny I./2025-2026` — čistě, bez NULL záznamy.

**Stav nasazení (2026-05-08):** Migrace 010 + 011 nasazeny a ověřeny v produkci.
Sanity check potvrdil správnou sadu politik — viz výsledek níže.

```
pruvodci_dny         | pd_director_all                  | ALL
pruvodci_dny         | pruvodci_dny_write_director_vp   | ALL
pruvodci_dny         | pd_guide_insert_own_group        | INSERT  ← nová
pruvodci_dny         | pd_staff_select                  | SELECT
pruvodci_dny         | pruvodci_dny_read_all            | SELECT
pruvodci_dny         | pd_guide_update_own_group        | UPDATE  ← nová
tridni_kniha_zaznamy | tkz_director_all                 | ALL
tridni_kniha_zaznamy | tk_zaznamy_delete_director       | DELETE
tridni_kniha_zaznamy | tkz_guide_insert_own_group       | INSERT  ← nová
tridni_kniha_zaznamy | tkz_vp_insert                    | INSERT  ← nová
tridni_kniha_zaznamy | tk_zaznamy_read_all              | SELECT
tridni_kniha_zaznamy | tkz_guide_select                 | SELECT
tridni_kniha_zaznamy | tkz_vp_assistant_readonly_select | SELECT
tridni_kniha_zaznamy | tkz_guide_update_own_group       | UPDATE  ← nová
tridni_kniha_zaznamy | tkz_vp_update                    | UPDATE  ← nová
```

### 18.2 NULL sémantika — klíčové pravidlo

| `group_id` | Meaning |
|---|---|
| `NULL` | Školní záznam: prázdniny, ředitelské volno, celoškolní akce. Průvodce může editovat bez ohledu na skupinu. |
| `NOT NULL` | Záznam konkrétní třídy. Průvodce může editovat pouze pokud `staff_groups` obsahuje vazbu na tuto skupinu. |

**Od 2026/2027 vždy NOT NULL** pro záznamy výuky, průvodce dny i locking.

### 18.3 Workflow: vytvoření tříd pro nový školní rok

Spustit v Supabase SQL Editoru po rozhodnutí o rozdělení žáků.
Vzor předpokládá dvě třídy — přizpůsobit dle skutečného počtu.

```sql
DO $$
DECLARE
  v_staff       UUID;
  v_group_a     UUID;   -- např. "Mladší třída"
  v_group_b     UUID;   -- např. "Starší třída"
  v_guide_a     UUID;   -- průvodce třídy A
  v_guide_b     UUID;   -- průvodce třídy B
BEGIN

  -- 0. Staff lookup
  SELECT id INTO v_staff
    FROM staff WHERE email = 'jakub.mracek@zsvilekula.cz' LIMIT 1;
  IF v_staff IS NULL THEN
    RAISE EXCEPTION 'Staff nenalezen';
  END IF;

  -- 1. Průvodci (lookup podle emailu)
  SELECT id INTO v_guide_a FROM staff WHERE email = 'katerina.studnickova@zsvilekula.cz' LIMIT 1;
  SELECT id INTO v_guide_b FROM staff WHERE email = 'vaclava.pelcova@zsvilekula.cz'      LIMIT 1;

  -- 2. Vytvořit skupiny pro 2026/2027
  INSERT INTO groups (name, school_year)
  VALUES ('Mladší třída', '2026/2027')
  RETURNING id INTO v_group_a;

  INSERT INTO groups (name, school_year)
  VALUES ('Starší třída', '2026/2027')
  RETURNING id INTO v_group_b;

  -- 3. Přiřadit žáky do skupin
  --    Varianta A: ručně podle UUIDs (malý počet žáků)
  --    Viz sekce 18.4 pro hromadné přiřazení pomocí SELECT

  -- 4. Přiřadit průvodce ke skupinám
  INSERT INTO staff_groups (staff_id, group_id, school_year, valid_from)
  VALUES
    (v_guide_a, v_group_a, '2026/2027', '2026-09-01'),
    (v_guide_b, v_group_b, '2026/2027', '2026-09-01');

  -- 5. Soft lock řádky per třída (nový školní rok)
  --    Seed z 009 vytvořil řádek s group_id = NULL pro 2026/2027 — ponechat,
  --    přidat per-group řádky.
  INSERT INTO tridni_kniha_skolni_rok (school_year, group_id)
  VALUES
    ('2026/2027', v_group_a),
    ('2026/2027', v_group_b)
  ON CONFLICT DO NOTHING;

  -- 6. Opakující se pravidla průvodců (nepovinné — viz sekce 13)
  INSERT INTO pruvodci_pravidla
    (staff_id, group_id, den_v_tydnu, valid_from, created_by)
  VALUES
    -- Průvodce A: po, út, st, čt, pá u třídy A
    (v_guide_a, v_group_a, 1, '2026-09-01', v_staff),
    (v_guide_a, v_group_a, 2, '2026-09-01', v_staff),
    (v_guide_a, v_group_a, 3, '2026-09-01', v_staff),
    (v_guide_a, v_group_a, 4, '2026-09-01', v_staff),
    (v_guide_a, v_group_a, 5, '2026-09-01', v_staff),
    -- Průvodce B: po, út, st, čt, pá u třídy B
    (v_guide_b, v_group_b, 1, '2026-09-01', v_staff),
    (v_guide_b, v_group_b, 2, '2026-09-01', v_staff),
    (v_guide_b, v_group_b, 3, '2026-09-01', v_staff),
    (v_guide_b, v_group_b, 4, '2026-09-01', v_staff),
    (v_guide_b, v_group_b, 5, '2026-09-01', v_staff);

END $$;
```

### 18.4 Přiřazení žáků do tříd

Žáci jsou k 2026/2027 zapsáni v `group_memberships` do skupiny `I./2026-2027`
(hromadný import z 2026-05-07). Po rozhodnutí o rozdělení do tříd je potřeba:

1. **Uzavřít** stávající skupinu `I./2026-2027` (nastavit `valid_to`)
2. **Přesunout** každého žáka do jedné ze dvou nových tříd

```sql
DO $$
DECLARE
  v_group_stara  UUID;
  v_group_a      UUID;
  v_group_b      UUID;
  -- UUIDs žáků přiřazených do třídy A (doplnit)
  v_zaci_a       UUID[] := ARRAY[
    -- 'uuid-zaka-1', 'uuid-zaka-2', ...
  ];
  -- UUIDs žáků přiřazených do třídy B (doplnit)
  v_zaci_b       UUID[] := ARRAY[
    -- 'uuid-zaka-3', 'uuid-zaka-4', ...
  ];
BEGIN

  -- Lookup skupin
  SELECT id INTO v_group_stara
    FROM groups WHERE name = 'I.' AND school_year = '2026/2027' LIMIT 1;
  SELECT id INTO v_group_a
    FROM groups WHERE name = 'Mladší třída' AND school_year = '2026/2027' LIMIT 1;
  SELECT id INTO v_group_b
    FROM groups WHERE name = 'Starší třída' AND school_year = '2026/2027' LIMIT 1;

  -- 1. Uzavřít stará členství (I./2026-2027)
  UPDATE group_memberships
     SET valid_to = '2026-08-31'
   WHERE group_id    = v_group_stara
     AND school_year = '2026/2027'
     AND valid_to   IS NULL;

  -- 2. Nová členství — třída A
  INSERT INTO group_memberships (student_id, group_id, school_year, valid_from)
  SELECT unnest(v_zaci_a), v_group_a, '2026/2027', '2026-09-01';

  -- 3. Nová členství — třída B
  INSERT INTO group_memberships (student_id, group_id, school_year, valid_from)
  SELECT unnest(v_zaci_b), v_group_b, '2026/2027', '2026-09-01';

END $$;
```

**Poznámka k načasování:** Spustit nejdříve v srpnu 2026 po finálním rozhodnutí
o rozdělení. Stávající záznamy z `I./2026-2027` zůstávají v DB pro historii —
uzavřením `valid_to` pouze zneplatníme aktivní členství.

### 18.5 Import historických záznamů třídní knihy 2025/2026

Záznamy z `tridni_kniha.csv` (182 ks) půjdou s `group_id` skupiny `I./2025-2026`.
Přidat do DO bloku importu:

```sql
-- Na začátek DO bloku (za staff lookup):
SELECT id INTO v_group_2526
  FROM groups
 WHERE name = 'I.' AND school_year = '2025/2026'
 LIMIT 1;
IF v_group_2526 IS NULL THEN
  RAISE EXCEPTION 'Skupina I./2025-2026 nenalezena';
END IF;

-- Každý INSERT do tridni_kniha_zaznamy dostane:
--   group_id => v_group_2526
```

### 18.6 Dotaz pro ověření po nastavení tříd

```sql
-- Přehled skupin a počtu žáků per třída:
SELECT
  g.name                AS trida,
  g.school_year,
  COUNT(gm.student_id)  AS pocet_zaku,
  sg_count.pruvodci
FROM groups g
LEFT JOIN group_memberships gm
       ON gm.group_id = g.id AND gm.valid_to IS NULL
LEFT JOIN LATERAL (
  SELECT string_agg(s.last_name, ', ') AS pruvodci
    FROM staff_groups sg
    JOIN staff s ON s.id = sg.staff_id
   WHERE sg.group_id = g.id AND sg.valid_to IS NULL
) sg_count ON TRUE
GROUP BY g.name, g.school_year, sg_count.pruvodci
ORDER BY g.school_year DESC, g.name;
```

---

## 16. Hromadný import dat — vzory

#### 16.1 Strategie: SQL Editor místo Python

**Rozhodnutí (2026-05-07):** Veškeré hromadné importy matrikových dat se
provádějí jako PL/pgSQL `DO $$` blok v Supabase SQL Editoru — ne přes
Python skripty.

**Důvod:** Nevyžaduje lokální Python prostředí. Celý blok je atomický
(ROLLBACK při jakékoli chybě). FK chaining přes `DECLARE` proměnné je
přehledný a laditelný přímo v Editoru.

Python skripty (`import_matrika.py`) zůstávají jako záloha a reference,
ale nejsou primárním nástrojem.

#### 16.2 Vzor DO bloku

```sql
DO $$
DECLARE
  v_staff UUID;        -- povinné: pro created_by
  v_group UUID;
  v_s01   UUID;        -- student ID
  v_g01   UUID;        -- guardian ID
  v_g_existujici UUID; -- guardian z předchozího importu (lookup z DB)
BEGIN

  -- 0. Staff lookup — VŽDY PRVNÍ akce v bloku
  SELECT id INTO v_staff
    FROM staff WHERE email = 'jakub.mracek@zsvilekula.cz' LIMIT 1;
  IF v_staff IS NULL THEN
    RAISE EXCEPTION 'Staff nenalezen — spusť bootstrap ředitele';
  END IF;

  -- 0b. Lookup existujících guardianů (sdílení mezi školními roky)
  SELECT id INTO v_g_existujici
    FROM guardians WHERE email = 'priklad@email.cz' LIMIT 1;
  IF v_g_existujici IS NULL THEN
    RAISE EXCEPTION 'Guardian nenalezen — spusť nejdřív předchozí import';
  END IF;

  -- 1–7. INSERT ... RETURNING id INTO v_s01; atd.

END $$;

-- Oprava sekvence — VŽDY SAMOSTATNĚ mimo DO blok:
SELECT setval('kod_zaka_seq', 32);
```

**Klíčová pravidla:**

- `created_by NOT NULL` ověřeno v produkci na `student_education_mode`
  a `student_matrika_a`. Pravděpodobně platí i pro `student_guardian_links`
  a `group_memberships` — preventivně předávat.
- `setval` se volá **mimo DO blok**. Pokud by transakce byla rollbacknuta,
  sekvence by zůstala posunutá.
- Sdílení ZZ mezi sourozenci: vložit jednou, UUID do proměnné, použít vícekrát.
- Sdílení existujících ZZ mezi školními roky: `SELECT id INTO` podle emailu.
- Duplicitní emaily ZZ (Lisseovi, Rudová+Ruda): `guardians` **nemá** UNIQUE
  constraint na `email` — obě vložení projdou.

#### 16.3 Životní cyklus skupinových zápisů při přechodu roku

```sql
-- 1. Uzavřít záznamy starého roku
UPDATE group_memberships
   SET valid_to = '2026-08-31'
 WHERE school_year = '2025/2026' AND valid_to IS NULL;

-- 2. Nová skupina
INSERT INTO groups (name, school_year)
VALUES ('I.', '2026/2027') RETURNING id INTO v_group;

-- 3. Existující aktivní žáci (SELECT — nepsat ručně 20 UUIDs)
INSERT INTO group_memberships (student_id, group_id, school_year, valid_from)
SELECT id, v_group, '2026/2027', '2026-09-01'
  FROM students
 WHERE status = 'active' AND enrollment_date < '2026-09-01';

-- 4. Noví žáci (VALUES výčet)
INSERT INTO group_memberships (student_id, group_id, school_year, valid_from)
VALUES (v_n21, v_group, '2026/2027', '2026-09-01'), ...;
```

#### 16.4 Trigger `check_sma_msmt_kod`

Trigger na `student_matrika_a` blokuje INSERT s výjimkou pokud:
`pspo > 0` a `students.kod_zaka_msmt IS NULL`

**Konvence hodnoty:** rodné číslo bez lomítka, 10 číslic (např. `1705011341`).

**Vzor — vždy nastavit před INSERT do `student_matrika_a`:**

```sql
UPDATE students SET kod_zaka_msmt = '1705011341' WHERE id = v_s11;
INSERT INTO student_matrika_a (student_id, pspo, ..., created_by)
VALUES (v_s11, 3, ..., v_staff);
```

#### 16.5 Aktuální stav dat (po importu 2026-05-07)

| Počet | Co |
|-------|----|
| 32 | aktivních žáků (`kod_zaka_seq = 32`) |
| 50 | zákonných zástupců / kontaktů |
| 20 | skupinových zápisů 2025/2026 (uzavřeny `valid_to = 2026-08-31`) |
| 32 | skupinových zápisů 2026/2027 (aktivní) |
| 2  | SVP záznamy v `student_matrika_a` (Lebovič VIL-2017-011, Vondrák VIL-2018-019) |
| 1  | pending SVP: Polák Michael VIL-2016-032 — `has_svp = TRUE`, `matrika_a` čeká na pspo z PPP |

---

## 17. Třídní kniha — Fáze 3: RLS a UI architektura (2026-05-08)

### 17.1 Migrace `009_rls_tridni_kniha.sql`

Nová migrace pro všech 12 tabulek Fáze 3. Staví výhradně na helper funkcích
z `006_rls.sql` — žádné nové helper funkce (stávající hierarchie postačuje).

**Tabulky a přístupová pravidla:**

| Tabulka | SELECT | INSERT/UPDATE | DELETE |
|---------|--------|---------------|--------|
| `tridni_kniha_skolni_rok` | all staff | director | director |
| `tridni_kniha_zaznamy` | all staff | director, vp, guide | director |
| `tridni_kniha_changes` | all staff | director, vp, guide | — (RULE) |
| `pruvodci_dny` | all staff | director, vp | director, vp |
| `pruvodci_pravidla` | all staff | director | director |
| `svp_vystupy` | all staff | director | director |
| `svp_vazby` | all staff | director, vp, guide | director, vp |
| `hospitace` | all staff | director, vp | director, vp |
| `bozp_zaznamy` | all staff | director, guide | director |
| `bozp_attendance` | all staff | director, guide | director, guide |
| `attendance_records` | director/vp=vše; guide/assistant=vlastní skupina | dtto | director |
| `semester_attendance_summary` | director/vp=vše; guide=vlastní skupina | director | director |

**Poznámka k `tridni_kniha_zaznamy`:** Záznamy výuky jsou školní (ne per-skupina)
→ průvodce čte a zapisuje **všechny** záznamy, ne jen záznamy "své skupiny".
Omezení per-skupinu platí pouze pro `attendance_records` a `semester_attendance_summary`.

**Inicializace školních roků:** Migrace vkládá řádky pro '2025/2026' a '2026/2027'
do `tridni_kniha_skolni_rok` (ON CONFLICT DO NOTHING) — prerekvizita soft lock UI.

### 17.2 UI stránky třídní knihy

```
app/dashboard/tridni-kniha/
├── page.tsx              ← Server Component — seznam záznamů
├── novy/
│   └── page.tsx          ← Client Component — formulář nového záznamu
└── [id]/
    └── page.tsx          ← Server Component — detail záznamu + SVP vazby
```

Zatím chybí (další iterace):
- `[id]/upravit/page.tsx` — editační formulář
- `[id]/svp/page.tsx` — správa SVP vazeb (multi-select per ročník)
- `bozp/page.tsx` — BOZP záznamy + žáci bez proškolení

### 17.3 Server Actions (`app/actions/tridni-kniha.ts`)

Exportované funkce:
- `createZaznam(input)` → INSERT + redirect na `[id]`
- `updateZaznam(id, input)` → UPDATE (nezamčený rok)
- `deleteZaznam(id)` → DELETE + redirect na seznam
- `computeDenVTydnu(dateStr)` → utility, exportována i pro Client Components

**Gotcha: `computeDenVTydnu`**

```typescript
// ŠPATNĚ — parsuje jako UTC midnight → off-by-one při letním čase
new Date('2026-05-08').getDay()

// SPRÁVNĚ — přidáme T12:00 aby zůstala lokální interpretace
new Date('2026-05-08T12:00:00').getDay()
```

### 17.4 Locked-year edit — omezení Supabase JS klienta

`updateZaznam()` funguje pro nezamčený rok. Pro **zamčený rok** (ARCH-NOTES sekce 12)
je třeba obalit UPDATE do explicitní transakce se `SET LOCAL`:

```sql
BEGIN;
SET LOCAL app.audit_reason = 'důvod změny od průvodce';
SET LOCAL app.audit_by     = 'staff-uuid';
UPDATE tridni_kniha_zaznamy SET ... WHERE id = '...';
COMMIT;
```

**Supabase JS client toto neumí** — `supabase.from().update()` vždy jede
jako single statement bez transakce. Řešení: implementovat jako
**Route Handler** (`app/api/tridni-kniha/[id]/route.ts`) který zavolá
`supabase.rpc('update_tk_zaznam_locked', {...})` — PL/pgSQL funkce
která sama obalí do transakce.

Toto je **TODO pro implementaci editačního formuláře zamčeného roku**.
Funkce `updateZaznam()` v actions/tridni-kniha.ts má na toto místo komentář.
