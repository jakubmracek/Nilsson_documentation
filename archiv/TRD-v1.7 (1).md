# Vilekula IS — Technical Requirements Document (TRD)

**Verze:** 1.7  
**Datum:** 2026-05-08  
**Autoři:** Ing. Jakub Mráček + Claude Sonnet 4.6  
**Navazuje na:** PRD v0.7, matrika TRD, matrika addendum 2026-04-27, třídní kniha addendum, VP addendum  
**Status:** Fáze 3 zahájena — RLS třídní knihy nasazeno (009), UI stránky třídní knihy v kódu.

**Changelog v1.7:** Migrace 009_rls_tridni_kniha.sql — RLS pro všech 12 tabulek Fáze 3. Schéma souborů rozšířeno o `app/dashboard/tridni-kniha/` (seznam, nový záznam, detail) a `app/actions/tridni-kniha.ts`. Sekce 1.3 aktualizována. Viz ARCH-NOTES sekce 17.

**Changelog v1.6:** Sekce 9.2 přepsána — import dat proveden přes SQL Editor (DO bloky), Python skripty jsou sekundární záloha. Zachyceny produkční poznatky: `created_by NOT NULL` na `student_education_mode` a `student_matrika_a`, trigger `check_sma_msmt_kod`. Viz ARCH-NOTES sekce 16.

**Changelog v1.5:** Aplikační vrstva — magic link auth, dashboard, proxy middleware (Next.js 16). Opraveno: `staff.user_id` místo `staff.id` pro `auth.uid()` vazbu, odstraněn neexistující sloupec `staff.is_active`. Přidána migrace `008_rls_staff_own.sql`. Schéma souborů rozšířeno o `app/`, `components/`, `lib/supabase-server.ts`, `proxy.ts`. Viz ARCH-NOTES sekce 15.

**Changelog v1.4:** Opraveny konzistenční chyby nalezené při review (007_fixes.sql). `tridni_kniha_zaznamy.skolni_rok CHAR(9)` → `school_year TEXT` (+ `bozp_zaznamy`, indexy, triggery). `generate_vp_alerts()`: `jmeno/prijmeni` → `first_name/last_name`, `ref_id` → `entity_id`, doplněn `alert_type` (NOT NULL) do INSERT. `is_vp()`: doplněn `SET search_path = public`. Schéma souboru rozšířeno o `007_fixes.sql`. Kód sekce 2.4 opraven (`OLD.school_year`). Viz také ARCH-NOTES sekce 14.

**Changelog v1.3:** Přidán `absence_request_id` FK do `attendance_records` (nullable, `ON DELETE SET NULL`) — propojení denního záznamu docházky s žádostí o omluvu. Sloučen `confirmed_by`/`locked_by` v `semester_attendance_summary` do jednoho kroku. Přidána sekce 5.12 `injury_reports` jako stub pro budoucí fázi (P3). Zahrnuty `pruvodci_pravidla` + generátor (Fáze 3). Uzavřena architektura soft lock triggeru (session variables — viz ARCH-NOTES sekce 12).

**Changelog v1.2:** Přidána tabulka `events` (sekce 4.2) jako prerekvizita platebního modulu. Doplněn FK `payment_obligations.reference_event_id → events(id)`. Rozšířen platební modul: `created_by` na `payment_obligations`, `updated_at` na platebních tabulkách, `note` na `payment_transactions`. Přidána tabulka `absence_requests.entered_by_staff_id` (rozhodnutí z implementace 002_communication.sql — viz ARCH-NOTES sekce 11). Prerekvizity 006_rls.sql aktualizovány na Fáze 1+2.

**Changelog v1.1:** Zapracována rozhodnutí O1–O10 (TRD review session 2026-04-27). Přidána tabulka `svp_vystupy`, aktualizovány migrační cesty, notifikační architektura VP, sekce 10 uzavřena.

---

## Obsah

1. [Technologický stack a architektura](#1-technologický-stack-a-architektura)
2. [Průřezová infrastruktura](#2-průřezová-infrastruktura)
3. [Fáze 1 — Matrika](#3-fáze-1--matrika)
4. [Fáze 2 — Komunikace, platby, omluvenky](#4-fáze-2--komunikace-platby-omluvenky)
   - 4.1 Komunikační modul
   - 4.2 Tabulka `events`
   - 4.3 Platební modul
   - 4.4 Omluvenky
5. [Fáze 3 — Třídní kniha a výkazy](#5-fáze-3--třídní-kniha-a-výkazy)
6. [Modul VP — Výchovné poradenství](#6-modul-vp--výchovné-poradenství)
7. [Integrace externích systémů](#7-integrace-externích-systémů)
8. [Bezpečnost a přístupová práva](#8-bezpečnost-a-přístupová-práva)
9. [Migrační cesty](#9-migrační-cesty)
10. [Otevřené otázky](#10-otevřené-otázky)

---

## 1. Technologický stack a architektura

### 1.1 Stack

| Vrstva | Technologie | Poznámka |
|--------|-------------|----------|
| Databáze | Supabase (PostgreSQL) | Nový projekt oddělený od vilekula-pokrok |
| Backend logika | Supabase Edge Functions (Deno) | Triggery, notifikace, exporty |
| Frontend | Next.js (App Router) + React | Admin rozhraní pro pedagogy — App Router potvrzen ✅ |
| PDF generátor | `@react-pdf/renderer` | Karta žáka + třídní kniha — potvrzen ✅. Puppeteer na Deno/Edge Functions nedostupný. |
| Hosting frontend | Vercel | Free tier |
| Email | Resend | Jediný emailový výstupní kanál — auth i komunikace s rodiči |
| Storage | Supabase Storage | Dokumenty VP, fotky, PDF exporty |
| Interní notifikace | Discord Webhooks | Pro pedagogický tým |
| Platební data | Fio API (REST) | Automatický import transakcí |

### 1.2 Autentizace

**Metoda:** Magic link (email OTP) přes Supabase Auth.

**Kritická konfigurace:** Supabase free tier má limit 2 magic linky/hodinu na adresu, který nelze zvýšit. Řešení: nakonfigurovat vlastní SMTP přes Resend (Supabase → Project Settings → Auth → SMTP Settings: `smtp.resend.com`, port 465, API key jako heslo). Toto je **prerekvizita nasazení** — bez vlastního SMTP nelze provozovat magic link v produkci.

**Výsledek:** Resend je jediný emailový provider pro celý systém — auth i komunikace s rodiči. Žádný druhý provider.

### 1.3 Schéma souborů projektu

```
vilekula-is/
├── supabase/
│   └── migrations/
│       ├── 000_init.sql          ← infrastruktura (triggery, sekvence, typy)
│       ├── 001_matrika.sql       ← Fáze 1
│       ├── 002_communication.sql ← Fáze 2
│       ├── 003_payments.sql      ← Fáze 2
│       ├── 004_tridni_kniha.sql  ← Fáze 3
│       ├── 005_vp.sql            ← Modul VP
│       ├── 006_rls.sql           ← všechny RLS politiky (matrika, komunikace, platby, VP)
│       ├── 007_fixes.sql         ← konzistenční opravy (school_year, entity_id, is_vp)
│       ├── 008_rls_staff_own.sql ← staff_read_own_by_user_id politika ✅ nasazeno
│       └── 009_rls_tridni_kniha.sql ← RLS Fáze 3 (12 tabulek) ✅ nasazeno
├── proxy.ts                      ← Next.js 16 middleware (dříve middleware.ts) ✅
├── lib/
│   ├── tridni-kniha-utils.ts        ← computeDenVTydnu utility (bez 'use server') ✅
│   ├── supabase.ts               ← createBrowserClient (Client Components)
│   └── supabase-server.ts        ← createServerClient (Server Components, Route Handlers) ✅
├── app/
│   ├── login/page.tsx            ← magic link přihlášení ✅
│   ├── auth/callback/route.ts    ← PKCE callback + staff check ✅
│   ├── dashboard/
│   │   ├── layout.tsx            ← shell, sidebar/bottom nav ✅
│   │   ├── page.tsx              ← přehled s widgety ✅
│   │   ├── zaci/
│   │   │   ├── page.tsx          ← seznam žáků ✅ (napsáno, neověřeno na datech)
│   │   │   └── [id]/page.tsx     ← detail žáka ✅ (napsáno, neověřeno na datech)
│   │   └── tridni-kniha/
│   │       ├── page.tsx          ← seznam záznamů ✅
│   │       ├── novy/page.tsx     ← formulář nového záznamu ✅
│   │       └── [id]/
│   │           ├── page.tsx      ← detail záznamu + SVP vazby ✅
│   │           ├── upravit/      ← TODO — editační formulář
│   │           └── svp/          ← TODO — správa SVP vazeb
│   ├── actions/
│   │   └── tridni-kniha.ts       ← Server Actions (create/update/delete + computeDenVTydnu) ✅
│   └── api/debug/rls-check/      ← smoke test (dev only) ✅
├── components/
│   ├── nav/AppNav.tsx            ← sidebar + bottom nav (role-based) ✅
│   └── dashboard/StudentSearchWidget.tsx ← live hledání žáka ✅
├── types/
│   └── database.ts               ← generované Supabase typy ✅
├── scripts/
│   ├── import_matrika.py         ← CSV import ze Sheets (sekundární záloha)
│   └── import_tridni_kniha.py    ← migrace dat 2025/2026
└── docs/
    ├── ADMIN-GUIDE.md
    ├── ARCH-NOTES-v1.6.md
    ├── TRD-v1.7.md
    └── DEPLOY-GUIDE.md           ← průvodce nasazením ✅
```

---

## 2. Průřezová infrastruktura

Soubor `000_init.sql` — spouští se jako první, definuje sdílené prvky pro všechny moduly.

### 2.1 Funkce `set_updated_at()`

Vlastní implementace bez závislosti na `pg_moddatetime` extension. Aplikuje se na všechny tabulky s `updated_at`.

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Použití (příklad — opakovat pro každou tabulku s `updated_at`):
```sql
CREATE TRIGGER trg_students_updated_at
  BEFORE UPDATE ON students
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 2.2 Sekvence `kod_zaka_seq`

Globální sekvence pro generování identifikátorů žáků. Nikdy se neresetuje.

```sql
CREATE SEQUENCE kod_zaka_seq START 1;

CREATE OR REPLACE FUNCTION generate_kod_zaka(rok_narozeni INT)
RETURNS TEXT AS $$
DECLARE
  seq_val  INT;
  candidate TEXT;
BEGIN
  seq_val   := nextval('kod_zaka_seq');
  candidate := 'VIL-' || rok_narozeni::TEXT || '-' || lpad(seq_val::TEXT, 4, '0');

  -- Pojistka: duplicita by nikdy neměla nastat (sekvence + UNIQUE), ale pro jistotu
  IF EXISTS (SELECT 1 FROM students WHERE kod_zaka = candidate) THEN
    RAISE EXCEPTION 'Duplicitní kod_zaka: %. Toto by nemělo nikdy nastat — zkontrolujte sekvenci.', candidate;
  END IF;

  RETURN candidate;
END;
$$ LANGUAGE plpgsql;
```

**Trojitá ochrana proti duplicitě:**
1. PostgreSQL sekvence (monotónní, nikdy se neopakuje)
2. `IF EXISTS` check s explicitní výjimkou
3. `UNIQUE` constraint na sloupci `students.kod_zaka`

### 2.3 Tabulka `system_alerts`

Sdílená průřezová tabulka pro všechny moduly. Zdroje: VP lhůty, platby po splatnosti, GDPR platnosti, BOZP upozornění.

```sql
CREATE TABLE system_alerts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  module      TEXT NOT NULL,      -- 'vp' | 'payments' | 'gdpr' | 'bozp' | 'matrika'
  alert_type  TEXT NOT NULL,      -- 'deadline' | 'missing_doc' | 'overdue' | 'missing_consent'
  severity    TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  entity_type TEXT NOT NULL,      -- 'student' | 'guardian' | 'staff'
  entity_id   UUID NOT NULL,
  message     TEXT NOT NULL,
  resolved_at TIMESTAMPTZ,        -- NULL = aktivní alert
  resolved_by UUID REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON system_alerts (module, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX ON system_alerts (entity_id);
```

### 2.4 Vzor "soft lock + audit trail"

Designový vzor aplikovaný konzistentně v třídní knize a matrice. Princip:
- Zámek per školní rok (`locked = true`), potvrzuje ředitel
- Po zamčení jsou editace stále technicky možné, ale **každá změna vytvoří immutabilní záznam** v příslušné `_changes` tabulce
- UI vyžaduje vyplnění důvodu změny
- Odemčení: pouze role `director`, také se zaloguje

Implementační vzor (sdílený trigger):
```sql
-- Příklad pro tridni_kniha — analogicky pro ostatní moduly
CREATE OR REPLACE FUNCTION check_locked_before_edit()
RETURNS TRIGGER AS $$
DECLARE
  is_locked BOOLEAN;
BEGIN
  SELECT locked INTO is_locked
  FROM tridni_kniha_skolni_rok
  WHERE school_year = OLD.school_year;

  IF is_locked THEN
    -- Neblokujeme, ale vyžadujeme audit — aplikační vrstva zajistí záznam v _changes
    -- Trigger slouží jako signál, aplikace musí předat duvod_zmeny
    RAISE WARNING 'Editace zamčeného záznamu školního roku %. Zajistěte záznam v audit logu.', OLD.school_year;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## 3. Fáze 1 — Matrika

### 3.1 Přehled tabulek

```
staff                        ← zaměstnanci (pedagogičtí i THP)
groups                       ← skupiny / třídy
students                     ← žáci (jádro systému)
guardians                    ← zákonní zástupci a kontaktní osoby
student_guardian_links       ← M:N vazba žák ↔ osoba s rolí
group_memberships            ← M:N vazba žák ↔ skupina (per školní rok)
staff_groups                 ← M:N vazba pedagog ↔ skupina (per školní rok)
student_contracts            ← smluvní dokumenty (append-only)
student_education_mode       ← způsob plnění PŠD s historií změn
student_matrika_a            ← data pro anonymizovaný soubor „a" (SVP, PO)
student_matrika_changes      ← právní dokladová vrstva změn matrikových dat
students_audit               ← technický audit trigger (JSON snapshot)
gdpr_consents                ← GDPR souhlasy zákonných zástupců
school_programs              ← evidence ŠVP a RVP
student_school_history       ← předchozí školy přestupujících žáků
```

### 3.2 Tabulka `staff`

```sql
CREATE TABLE staff (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL,
  first_name          TEXT NOT NULL,
  last_name           TEXT NOT NULL,
  birth_number        TEXT,                    -- rodné číslo (citlivý údaj)
  email               TEXT NOT NULL UNIQUE,
  role                TEXT NOT NULL CHECK (role IN (
                        'director',            -- ředitel — plný přístup
                        'vp',                  -- výchovný poradce
                        'guide',               -- průvodce (třídní učitel)
                        'assistant',           -- asistent pedagoga
                        'readonly'             -- kontrolní přístup
                      )),
  typ_zamestnance     TEXT NOT NULL CHECK (typ_zamestnance IN (
                        'pedagogicky',         -- zákon č. 563/2004 Sb.
                        'THP'                  -- technicko-hospodářský pracovník
                      )),
  employment_type     TEXT CHECK (employment_type IN (
                        'full_time', 'part_time', 'dpp', 'dpc'
                      )),
  qualification_code  TEXT,                    -- MŠMT číselník (pro výkaz zaměstnanců)
  subject_codes       TEXT[],                  -- vyučované předměty
  employment_start    DATE,
  employment_end      DATE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_staff_updated_at
  BEFORE UPDATE ON staff
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**Poznámka:** `user_id` propojuje záznam zaměstnance s Supabase Auth — nutné pro RLS (`auth.uid() = staff.user_id`). Při onboardingu pedagoga vznikají oba záznamy současně.

### 3.3 Tabulka `groups`

```sql
CREATE TABLE groups (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,         -- 'Modrá', 'Červená', ...
  school_year TEXT NOT NULL,         -- '2025/2026' (TEXT, konzistentní napříč systémem)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, school_year)
);
```

### 3.4 Tabulka `students`

```sql
CREATE TABLE students (
  -- Primární identifikátor
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identifikátory
  kod_zaka        TEXT UNIQUE NOT NULL,   -- VIL-{rok_nar}-{seq} — generováno triggerem
  vs_interni      TEXT UNIQUE,            -- historický kód z Google Sheets (import)
  kod_zaka_msmt   TEXT UNIQUE,            -- pro MŠMT anonymizovaný soubor „a" (max 10 znaků)

  -- Základní osobní data
  first_name      TEXT NOT NULL,
  last_name       TEXT NOT NULL,
  birth_date      DATE NOT NULL,
  birth_place     TEXT,
  birth_number    TEXT,                   -- rodné číslo (citlivý údaj — šifrovat na app vrstvě)
  nationality     TEXT,                   -- státní příslušnost (text)
  citizenship     TEXT,                   -- občanství (kód RAST, např. '203' pro CZ)

  -- Zdravotní a administrativní
  health_insurance_code   TEXT,           -- kód zdravotní pojišťovny
  health_fitness_note     TEXT,           -- zdravotní způsobilost / omezení
  has_svp                 BOOLEAN NOT NULL DEFAULT FALSE,
  svp_detail              TEXT,
  education_mode          TEXT CHECK (education_mode IN (
                            'standardni',
                            'jiny_zpusob',     -- §38
                            'domaci'           -- §41
                          )) DEFAULT 'standardni',

  -- MŠMT číselníky (pro XML výkazy)
  obec_bydliste_kod       TEXT,           -- kód obce RAUJ
  okres_bydliste_kod      TEXT,           -- kód okresu RAOR
  predchozi_skola_izo     TEXT,           -- IZO předchozí školy (IZOP)
  predchozi_vzdelavani    TEXT,           -- kód RAPD (010=MŠ, 030=ZŠ)
  kod_zahajeni            TEXT,           -- RAZD (1=řádný nástup, 2=odklad 1r, 3=odklad 2r)
  delka_programu          INTEGER DEFAULT 90,  -- v měsících (90 = 9letá ZŠ)
  cizi_jazyky             JSONB,          -- [{jazyk: 'AN', priznak: 'A'}, ...]
  zdroj_financovani       TEXT DEFAULT '1',    -- RAFZ (1=MŠMT)
  sp_obvod                TEXT DEFAULT '0',    -- spádový obvod (soukromé školy = 0)

  -- Katalogový list — dokumenty z předchozích škol
  kat_list_stav           TEXT CHECK (kat_list_stav IN (
                            'k_dispozici',
                            'chybi',
                            'nevyzadovano'     -- prvozápis (KOD_ZAH ≠ E)
                          )),
  kat_list_drive_url      TEXT,
  kat_list_poznamka       TEXT,

  -- Stav žáka
  enrollment_date         DATE NOT NULL,
  withdrawal_date         DATE,
  withdrawal_reason       TEXT,
  status                  TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                            'active', 'archived', 'withdrawn'
                          )),

  -- Metadata
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Automatické generování kod_zaka při INSERT
CREATE OR REPLACE FUNCTION trg_generate_kod_zaka()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.kod_zaka IS NULL THEN
    NEW.kod_zaka := generate_kod_zaka(EXTRACT(YEAR FROM NEW.birth_date)::INT);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_students_kod_zaka
  BEFORE INSERT ON students
  FOR EACH ROW EXECUTE FUNCTION trg_generate_kod_zaka();

CREATE TRIGGER trg_students_updated_at
  BEFORE UPDATE ON students
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX ON students (status);
CREATE INDEX ON students (last_name, first_name);
```

### 3.5 Tabulka `guardians`

```sql
CREATE TABLE guardians (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name            TEXT NOT NULL,
  last_name             TEXT NOT NULL,
  email                 TEXT,
  phone_primary         TEXT,
  phone_secondary       TEXT,
  address_street        TEXT,
  address_city          TEXT,
  address_zip           TEXT,
  address_country       TEXT DEFAULT 'CZ',
  address_delivery      TEXT,           -- doručovací adresa pokud jiná
  data_box_id           TEXT,           -- datová schránka (volitelné)
  gdpr_consent_at       TIMESTAMPTZ,
  gdpr_consent_version  TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_guardians_updated_at
  BEFORE UPDATE ON guardians
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 3.6 Typ `guardian_role` a tabulka `student_guardian_links`

```sql
CREATE TYPE guardian_role AS ENUM (
  'matka',
  'otec',
  'porucnik',
  'opatrovnik',
  'pestoun',
  'sverena_pece',        -- péče soudem, ale NENÍ zákonný zástupce
  'jiny_zz',
  'kontaktni_osoba'      -- bez právního titulu, pouze kontakt
);

CREATE TABLE student_guardian_links (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id            UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  guardian_id           UUID NOT NULL REFERENCES guardians(id) ON DELETE RESTRICT,
  role                  guardian_role NOT NULL,
  je_zakonny_zastupce   BOOLEAN NOT NULL DEFAULT TRUE,
  je_primarni_kontakt   BOOLEAN NOT NULL DEFAULT FALSE,
  platnost_od           DATE,
  platnost_do           DATE,           -- NULL = stále platné
  pravni_titul          TEXT,           -- 'rozsudek č. ...', 'rodný list', ...
  legal_document_ref    TEXT,           -- odkaz na naskenovaný dokument
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Validace: sverena_pece a kontaktni_osoba nemohou být zákonný zástupce
  CONSTRAINT check_role_zz CHECK (
    NOT (role IN ('sverena_pece', 'kontaktni_osoba') AND je_zakonny_zastupce = TRUE)
  )
);

CREATE INDEX ON student_guardian_links (student_id);
CREATE INDEX ON student_guardian_links (guardian_id);
```

**Validace na aplikační vrstvě:** Každý žák musí mít alespoň jednoho `je_zakonny_zastupce = TRUE`. UI varuje pokud podmínka není splněna.

### 3.7 Tabulka `group_memberships`

M:N vazba žák ↔ skupina s platností v čase. Nahrazuje přímý FK `students.group_id`.

```sql
CREATE TABLE group_memberships (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE RESTRICT,
  school_year TEXT NOT NULL,
  valid_from  DATE NOT NULL,
  valid_to    DATE,                     -- NULL = aktuálně platné
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, group_id, school_year)
);

CREATE INDEX ON group_memberships (student_id, school_year);
CREATE INDEX ON group_memberships (group_id, school_year);
```

### 3.8 Tabulka `staff_groups`

M:N vazba pedagog ↔ skupina. Základ pro RLS (pedagog vidí pouze žáky své skupiny).

```sql
CREATE TABLE staff_groups (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  staff_id    UUID NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
  group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE RESTRICT,
  school_year TEXT NOT NULL,
  valid_from  DATE NOT NULL,
  valid_to    DATE,                     -- NULL = aktuálně platné
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (staff_id, group_id, school_year)
);
```

### 3.9 Tabulka `student_contracts`

Append-only log smluvních dokumentů. Každý žák může mít více smluv v čase.

```sql
CREATE TABLE student_contracts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  contract_type   TEXT NOT NULL CHECK (contract_type IN (
                    'enrollment', 'amendment', 'termination'
                  )),
  signed_date     DATE NOT NULL,
  effective_date  DATE NOT NULL,
  end_date        DATE,
  document_url    TEXT,                 -- Supabase Storage nebo Google Drive
  version_number  INTEGER NOT NULL DEFAULT 1,
  notes           TEXT,
  created_by      UUID NOT NULL REFERENCES staff(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON student_contracts (student_id, effective_date DESC);
```

### 3.10 Tabulka `student_education_mode`

Způsob plnění PŠD s historií změn — potřebné pro správné generování vět v M3 XML.

```sql
CREATE TABLE student_education_mode (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  zpusob      CHAR(2) NOT NULL,         -- RAZD: '11'=klasická škola, '30'=§38, '40'=§41
  valid_from  DATE NOT NULL,
  valid_to    DATE,                     -- NULL = aktuálně platné
  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON student_education_mode (student_id, valid_from DESC);
```

### 3.11 Tabulka `student_matrika_a`

Data pro anonymizovaný soubor „a" (SVP, podpůrná opatření). Měnitelná v čase — vlastní věty s platností.

```sql
CREATE TABLE student_matrika_a (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id    UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,

  -- Podpůrná opatření
  pspo          INTEGER CHECK (pspo BETWEEN 0 AND 5) DEFAULT 0,  -- převažující stupeň PO
  indi          TEXT CHECK (indi IN ('0', '1', '5')),  -- IVP: 0=bez, 1=SVP, 5=nadání
  nadani        TEXT CHECK (nadani IN ('0', '1')),
  id_znev       TEXT,           -- kód z doporučení ŠPZ (zadává se ručně)
  uvp           BOOLEAN DEFAULT FALSE,   -- upravený vzdělávací plán
  prodl_dv      BOOLEAN DEFAULT FALSE,   -- prodloužená délka vzdělávání
  upr_vyst      BOOLEAN DEFAULT FALSE,   -- upravené výstupy vzdělávání

  -- Typ třídy a asistent
  typ_tr        TEXT DEFAULT '100A0',    -- '100A0'=bez, '100A1'=1 asistent, '100A2'=více

  -- Sociální/zdravotní znevýhodnění
  sz            TEXT CHECK (sz IN ('K', 'Z', 'V', '0')) DEFAULT '0',
  zz            TEXT CHECK (zz IN ('0', '1')) DEFAULT '0',

  -- Jazyková příprava (cizinci)
  zvj           TEXT CHECK (zvj IN ('0', '1')),
  jaz_podp      BOOLEAN DEFAULT FALSE,
  jaz_prip      BOOLEAN DEFAULT FALSE,

  -- Platnost věty
  valid_from    DATE NOT NULL,
  valid_to      DATE,                    -- NULL = aktuálně platné

  created_by    UUID NOT NULL REFERENCES staff(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  -- KOD_ZAKA pro MŠMT: přebíráme z students.kod_zaka_msmt
);

CREATE INDEX ON student_matrika_a (student_id, valid_from DESC);
```

**Aktuální stav Vilekuly (2025/2026):** 1 žák s PO 2, 1 žák s PO 3 (k němu přidělena asistentka Michaela Kruchlová → `TYP_TR = '100A1'` pro třídu). Soubor „a" je tedy aktivní — nelze generovat prázdný.

### 3.12 Dvojí audit mechanismus

#### 3.12.1 Technický audit trigger (`students_audit`)

Automatická pojistka na úrovni databáze — nelze obejít aplikační vrstvou.

```sql
CREATE TABLE students_audit (
  audit_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operation   TEXT NOT NULL,            -- 'INSERT' | 'UPDATE' | 'DELETE'
  changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  changed_by  UUID,                     -- auth.uid() z aplikační vrstvy
  old_data    JSONB,
  new_data    JSONB
);

CREATE OR REPLACE FUNCTION trg_students_audit_fn()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO students_audit (operation, changed_by, old_data, new_data)
  VALUES (
    TG_OP,
    auth.uid(),
    CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE row_to_json(OLD)::JSONB END,
    CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE row_to_json(NEW)::JSONB END
  );
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_students_audit
  AFTER INSERT OR UPDATE OR DELETE ON students
  FOR EACH ROW EXECUTE FUNCTION trg_students_audit_fn();
```

Analogický trigger aplikovat na: `guardians`, `student_guardian_links`, `student_contracts`, `gdpr_consents`.

#### 3.12.2 Právní dokladová vrstva (`student_matrika_changes`)

Sémanticky bohatá tabulka pro doložení změn při kontrole ČŠI. Immutabilní — záznamy nelze mazat.

```sql
CREATE TABLE student_matrika_changes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  student_id    UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  datum_zmeny   DATE NOT NULL,           -- datum reálné události (ne timestamp zápisu)
  pole          TEXT NOT NULL,           -- název sloupce / oblasti
  hodnota_pred  TEXT,                    -- NULL = nový záznam
  hodnota_po    TEXT NOT NULL,
  zdroj_zmeny   TEXT NOT NULL,           -- 'oznámení ZZ', 'rozsudek soudu', 'interní korekce'
  dokument_ref  TEXT,                    -- odkaz na dokladový soubor
  zaznamenal    TEXT NOT NULL            -- jméno uživatele IS
);

-- Immutabilita: zakázat UPDATE a DELETE
CREATE RULE no_update_matrika_changes AS ON UPDATE TO student_matrika_changes DO INSTEAD NOTHING;
CREATE RULE no_delete_matrika_changes AS ON DELETE TO student_matrika_changes DO INSTEAD NOTHING;

CREATE INDEX ON student_matrika_changes (student_id, datum_zmeny DESC);
```

**Vztah obou mechanismů:**
- `students_audit` = technická pojistka, JSON snapshot, automatický
- `student_matrika_changes` = právní dokladová vrstva, čitelná lidmi, vyplňuje uživatel při každé editaci v UI

### 3.13 Tabulka `gdpr_consents`

```sql
CREATE TABLE gdpr_consents (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  guardian_id      UUID REFERENCES guardians(id),
  student_id       UUID REFERENCES students(id),   -- pro žáky 16+
  consent_type     TEXT NOT NULL CHECK (consent_type IN (
                     'communication',
                     'photography',
                     'third_party_sharing',
                     'data_processing'
                   )),
  granted          BOOLEAN NOT NULL,
  granted_at       TIMESTAMPTZ,
  revoked_at       TIMESTAMPTZ,
  consent_version  TEXT NOT NULL,
  legal_basis      TEXT NOT NULL CHECK (legal_basis IN (
                     'consent',
                     'legitimate_interest',
                     'legal_obligation',
                     'contract'
                   )),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT check_subject CHECK (
    (guardian_id IS NOT NULL) OR (student_id IS NOT NULL)
  )
);
```

### 3.14 Tabulky pro katalogový list

```sql
CREATE TABLE school_programs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rvp_name        TEXT NOT NULL,
  svp_name        TEXT NOT NULL,
  svp_file_number TEXT,
  svp_valid_from  DATE,
  svp_valid_to    DATE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE student_school_history (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id     UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  school_name    TEXT NOT NULL,
  school_address TEXT,
  period_from    DATE NOT NULL,
  period_to      DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE disciplinary_measures (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id        UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  measure_date      DATE NOT NULL,
  school_year       TEXT NOT NULL,
  grade             INTEGER,
  measure_type      TEXT NOT NULL CHECK (measure_type IN (
                      'pochvala', 'napomenuti', 'dutka_tridniho',
                      'dutka_reditele', 'podmínene_vylouceni', 'jine'
                    )),
  justification_text TEXT NOT NULL,
  created_by        UUID NOT NULL REFERENCES staff(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE student_notes (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  note_text        TEXT NOT NULL,
  is_safety_relevant BOOLEAN NOT NULL DEFAULT FALSE,
  created_by       UUID NOT NULL REFERENCES staff(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Fáze 2 — Komunikace, platby, omluvenky

### 4.1 Tabulky komunikačního modulu

```sql
CREATE TABLE comm_campaigns (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL,
  subject     TEXT NOT NULL,
  body_html   TEXT,
  body_text   TEXT,
  -- Alespoň jeden z body_html / body_text musí být vyplněn (CHECK v 002_communication.sql)
  target_type TEXT NOT NULL CHECK (target_type IN ('all', 'group', 'individual')),
  target_ref  UUID,                     -- group_id pro 'group', NULL pro ostatní
  -- target_ref NOT NULL právě tehdy když target_type='group' (CHECK v 002_communication.sql)
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'cancelled')),
  created_by  UUID NOT NULL REFERENCES staff(id),
  sent_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Junction tabulka pro cílení na konkrétní jednotlivce
CREATE TABLE comm_campaign_recipients (
  campaign_id  UUID NOT NULL REFERENCES comm_campaigns(id) ON DELETE CASCADE,
  guardian_id  UUID NOT NULL REFERENCES guardians(id),
  PRIMARY KEY (campaign_id, guardian_id)
);

CREATE TABLE comm_log (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id        UUID NOT NULL REFERENCES comm_campaigns(id),
  guardian_id        UUID NOT NULL REFERENCES guardians(id),
  email_address      TEXT NOT NULL,     -- snapshot adresy v čase odeslání
  resend_message_id  TEXT,
  status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                       'queued', 'sent', 'delivered', 'bounced', 'failed'
                     )),
  error_detail       TEXT,              -- payload z Resend webhook při bounce/failure
  sent_at            TIMESTAMPTZ,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.2 Tabulka `events` (školní akce)

Prerekvizita platebního modulu — `payment_obligations.reference_event_id` referencuje tuto tabulku.

Akce mohou být jednodenní i vícedenní (výlety, kurzy). Vazba na platební pohledávky je 1:N — jedna akce generuje pohledávku per žák přes `payment_obligations`.

```sql
CREATE TABLE events (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           TEXT NOT NULL,
  description    TEXT,
  date_from      DATE NOT NULL,
  date_to        DATE,                    -- NULL = jednodenní akce
  school_year    TEXT NOT NULL,           -- '2025/2026'
  default_amount NUMERIC(10,2),           -- výchozí částka pro generování pohledávek
                                          -- NULL = akce bez standardní ceny (vstup zdarma apod.)
  created_by     UUID NOT NULL REFERENCES staff(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT check_event_dates CHECK (date_to IS NULL OR date_to >= date_from)
);

CREATE INDEX ON events (school_year, date_from);
CREATE INDEX ON events (date_from);

CREATE TRIGGER trg_events_updated_at
  BEFORE UPDATE ON events
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**Workflow generování pohledávek:**
1. Director/průvodce vytvoří akci v IS
2. UI nabídne „generovat pohledávky" — per žák INSERT do `payment_obligations` s `reference_event_id`
3. Generování je manuální krok (ne automatický trigger) — průvodce může vybrat jen část žáků

### 4.3 Tabulky platebního modulu

```sql
CREATE TABLE payment_obligations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id         UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  type               TEXT NOT NULL CHECK (type IN ('tuition', 'event', 'lunch', 'donation')),
  amount             NUMERIC(10,2) NOT NULL,
  currency           TEXT NOT NULL DEFAULT 'CZK',
  due_date           DATE NOT NULL,
  reference_event_id UUID REFERENCES events(id),   -- FK platný; NOT NULL pro type='event'
  school_year        TEXT NOT NULL,
  period             TEXT CHECK (period ~ '^\d{4}-(0[1-9]|1[0-2])$'),  -- 'YYYY-MM' pro měsíční typy
  created_by         UUID NOT NULL REFERENCES staff(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Logická konzistence: event musí mít reference_event_id
  CONSTRAINT check_event_ref CHECK (
    type != 'event' OR reference_event_id IS NOT NULL
  )
);

CREATE INDEX ON payment_obligations (student_id, due_date DESC);
CREATE INDEX ON payment_obligations (school_year, due_date);
CREATE INDEX ON payment_obligations (reference_event_id) WHERE reference_event_id IS NOT NULL;

CREATE TRIGGER trg_payment_obligations_updated_at
  BEFORE UPDATE ON payment_obligations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE payment_transactions (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fio_transaction_id   TEXT UNIQUE NOT NULL,
  student_id           UUID REFERENCES students(id),   -- NULL pokud nespárováno
  variable_symbol      TEXT,
  amount               NUMERIC(10,2) NOT NULL,
  currency             TEXT NOT NULL DEFAULT 'CZK',
  counterparty_name    TEXT,
  counterparty_account TEXT,
  transaction_date     DATE NOT NULL,
  note                 TEXT,                -- poznámka k manuálnímu override / interní komentář
  imported_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  match_status         TEXT NOT NULL DEFAULT 'unmatched' CHECK (match_status IN (
                         'matched', 'unmatched', 'manual_override'
                       ))
  -- matched_by není potřeba — rozlišení auto vs. manuál je v match_status:
  --   'matched'         = auto-match přes Fio Edge Function (variable_symbol = kod_zaka)
  --   'manual_override' = ručně spárováno/přepsáno staff v UI
  -- Kdo provedl manuální override: dohledatelné přes payment_matches.matched_by
);

CREATE INDEX ON payment_transactions (variable_symbol);
CREATE INDEX ON payment_transactions (match_status) WHERE match_status != 'matched';
CREATE INDEX ON payment_transactions (transaction_date DESC);
CREATE INDEX ON payment_transactions (student_id) WHERE student_id IS NOT NULL;

CREATE TRIGGER trg_payment_transactions_updated_at
  BEFORE UPDATE ON payment_transactions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE payment_matches (
  transaction_id  UUID NOT NULL REFERENCES payment_transactions(id),
  obligation_id   UUID NOT NULL REFERENCES payment_obligations(id),
  matched_amount  NUMERIC(10,2) NOT NULL,
  matched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  matched_by      UUID REFERENCES staff(id),  -- NULL = auto-match, NOT NULL = manuální
  PRIMARY KEY (transaction_id, obligation_id)
);

CREATE INDEX ON payment_matches (obligation_id);
```

**Fio API integrace** (Edge Function `import-fio-transactions`):
```
GET fio.cz/ib_api/rest/last/{token}/transactions.json
  → parse transactions
  → match na student přes variable_symbol = students.kod_zaka (4místné číslo)
  → INSERT do payment_transactions (match_status = 'matched'/'unmatched')
  → unmatched → INSERT do system_alerts (module='payments', severity='warning')
```

**Variabilní symbol:** Poslední 4 číslice `kod_zaka` (pořadové číslo ze sekvence `kod_zaka_seq`).

### 4.4 Tabulka `absence_requests` (omluvenky)

**Architektonické rozhodnutí (v1, bez rodičovského portálu):**
Zákonní zástupci nemají vlastní auth. Průvodce zadává omluvenku jménem rodiče.
Dva oddělené sloupce zajišťují právní původ i odpovědnost za zápis.
Migrační cesta k rodičovskému portálu: viz ARCH-NOTES sekce 11.

```sql
CREATE TABLE absence_requests (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id                UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  requested_by_guardian_id  UUID NOT NULL REFERENCES guardians(id),  -- právní původ žádosti
  entered_by_staff_id       UUID NOT NULL REFERENCES staff(id),      -- kdo zapsal do IS
  date_from                 DATE NOT NULL,
  date_to                   DATE NOT NULL,
  reason                    TEXT NOT NULL,
  status                    TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                              'pending', 'approved', 'rejected'
                            )),
  reviewed_by               UUID REFERENCES staff(id),
  reviewed_at               TIMESTAMPTZ,
  note_internal             TEXT,         -- interní poznámka (zákonný zástupce nevidí)
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT check_dates              CHECK (date_to >= date_from),
  CONSTRAINT check_review_consistency CHECK (
    (reviewed_by IS NULL) = (reviewed_at IS NULL)
  ),
  CONSTRAINT check_reviewed_when_decided CHECK (
    status = 'pending' OR reviewed_by IS NOT NULL
  )
);

CREATE INDEX ON absence_requests (student_id, status);
CREATE INDEX ON absence_requests (student_id, date_from DESC);
CREATE INDEX ON absence_requests (status) WHERE status = 'pending';
```

---

## 5. Fáze 3 — Třídní kniha a výkazy

### 5.1 Správa školního roku a soft lock

```sql
CREATE TABLE tridni_kniha_skolni_rok (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  school_year TEXT NOT NULL UNIQUE,
  locked      BOOLEAN NOT NULL DEFAULT FALSE,
  locked_at   TIMESTAMPTZ,
  locked_by   UUID REFERENCES staff(id),
  unlocked_at TIMESTAMPTZ,
  unlocked_by UUID REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Workflow uzavření:** Systém na konci školního roku vyzve ředitele k potvrzení → `locked = TRUE`. Po uzamčení jsou editace záznamů možné, ale každá musí projít `tridni_kniha_changes`.

### 5.2 Tabulka `tridni_kniha_zaznamy`

```sql
CREATE TABLE tridni_kniha_zaznamy (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum        DATE NOT NULL,
  den_v_tydnu  CHAR(2) NOT NULL CHECK (den_v_tydnu IN ('po','út','st','čt','pá')),
  cas_od       TIME,                     -- NULL = celý den (nejčastější případ)
  cas_do       TIME,
  nazev        TEXT NOT NULL,
  popis        TEXT,
  typ_zaznamu  TEXT NOT NULL CHECK (typ_zaznamu IN (
                 'vyuka', 'expedice', 'projekt', 'prazdniny',
                 'reditelske_volno', 'sportovni_kurz', 'kulturni_akce'
               )),
  school_year  TEXT NOT NULL,            -- '2025/2026'
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON tridni_kniha_zaznamy (datum);
CREATE INDEX ON tridni_kniha_zaznamy (school_year, datum);

CREATE TRIGGER trg_tridni_kniha_zaznamy_updated_at
  BEFORE UPDATE ON tridni_kniha_zaznamy
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 5.3 Audit trail třídní knihy (`tridni_kniha_changes`)

Aplikuje soft lock vzor — viz sekce 2.4.

```sql
CREATE TABLE tridni_kniha_changes (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zaznam_id    UUID NOT NULL REFERENCES tridni_kniha_zaznamy(id) ON DELETE RESTRICT,
  changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  changed_by   UUID NOT NULL REFERENCES staff(id),
  duvod_zmeny  TEXT NOT NULL,            -- povinný při editaci zamčeného roku
  pole         TEXT NOT NULL,
  hodnota_pred TEXT,
  hodnota_po   TEXT NOT NULL
);

CREATE RULE no_update_tk_changes AS ON UPDATE TO tridni_kniha_changes DO INSTEAD NOTHING;
CREATE RULE no_delete_tk_changes AS ON DELETE TO tridni_kniha_changes DO INSTEAD NOTHING;
```

### 5.4 Tabulky `pruvodci_dny` a `pruvodci_pravidla`

```sql
CREATE TABLE pruvodci_dny (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum       DATE NOT NULL,
  pedagog_id  UUID NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
  role_dne    TEXT NOT NULL DEFAULT 'průvodce' CHECK (role_dne IN (
                'průvodce', 'asistent', 'externista'
              )),
  UNIQUE (datum, pedagog_id)
);
```

**Opakující se pravidla** jsou implementována jako samostatná tabulka `pruvodci_pravidla`. Generátor vytváří záznamy v `pruvodci_dny` na základě pravidel — jednorázový záznam v `pruvodci_dny` pro konkrétní datum pravidlo přepíše.

```sql
CREATE TABLE pruvodci_pravidla (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  staff_id    UUID NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
  den_v_tydnu SMALLINT NOT NULL CHECK (den_v_tydnu BETWEEN 1 AND 5),
                                  -- 1=pondělí … 5=pátek (ISO: Monday=1)
  role_dne    TEXT NOT NULL DEFAULT 'průvodce' CHECK (role_dne IN (
                'průvodce', 'asistent', 'externista'
              )),
  valid_from  DATE NOT NULL,
  valid_to    DATE,               -- NULL = platí dále
  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT check_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX ON pruvodci_pravidla (staff_id, valid_from DESC);
CREATE INDEX ON pruvodci_pravidla (den_v_tydnu);
```

**Generátor `generate_pruvodci_dny(date_from DATE, date_to DATE)`:**

Edge Function (nebo DB funkce) iteruje přes každý pracovní den v zadaném rozsahu, dohledá aktivní pravidla (`valid_from <= datum AND (valid_to IS NULL OR valid_to >= datum)`) a vloží záznamy do `pruvodci_dny` — `ON CONFLICT (datum, pedagog_id) DO NOTHING` (existující záznamy nepřepisuje). Spouští ředitel manuálně na začátku pololetí nebo při změně rozvrhu.

### 5.5 Číselník `svp_vystupy`

Autoritativní seznam výstupů ŠVP Vilekuly s kódy. Primární klíčem pro logiku je `kod` (stabilní i při přeformulování textu při revizi ŠVP). Kompatibilní s kódy používanými v vilekula-pokrok (Mapa růstu).

```sql
CREATE TABLE svp_vystupy (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kod         TEXT NOT NULL UNIQUE,   -- stabilní kód, např. 'M-1-01', 'JK-3-05'
  rocnik      SMALLINT NOT NULL CHECK (rocnik BETWEEN 1 AND 9),
  predmet     TEXT NOT NULL,          -- 'Matematika', 'Jazyk a komunikace', ...
  vystup_text TEXT NOT NULL,          -- lidsky čitelný popis výstupu
  svp_version TEXT NOT NULL,          -- verze ŠVP (pro případ revize)
  aktivni     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON svp_vystupy (rocnik, predmet);
CREATE INDEX ON svp_vystupy (kod);
```

**Import:** Ze stávající databáze Mapy růstu (Supabase vilekula-pokrok) + ŠVP. Formát vstupního CSV: `kod, rocnik, predmet, vystup_text`. Skript: `scripts/import_svp_vystupy.py`.

**Kompatibilita s vilekula-pokrok:** Kódy musí být identické s kódy v Mapě růstu — toto je předpoklad budoucí integrace (Fáze 2 migrace, PRD sekce 4.2).

### 5.6 Tabulka `svp_vazby`

```sql
CREATE TABLE svp_vazby (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zaznam_id    UUID NOT NULL REFERENCES tridni_kniha_zaznamy(id) ON DELETE CASCADE,
  vystup_id    UUID NOT NULL REFERENCES svp_vystupy(id),   -- FK na číselník
  rocnik       SMALLINT NOT NULL CHECK (rocnik BETWEEN 1 AND 9),  -- denormalizováno pro rychlé dotazy
  zdroj        TEXT NOT NULL DEFAULT 'ai' CHECK (zdroj IN ('ai', 'manual')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON svp_vazby (zaznam_id);
CREATE INDEX ON svp_vazby (rocnik, vystup_id);
```

**Poznámka:** Jeden den má záznamy pro různé ročníky — výstupy 1. ročníku ≠ výstupy 5. ročníku pro tentýž den. UI zobrazí záložky per ročník. `rocnik` je denormalizován pro výkon (jinak by každý dotaz joinoval `svp_vystupy`).

### 5.7 Tabulka `hospitace`

```sql
CREATE TABLE hospitace (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum            DATE NOT NULL,
  typ              TEXT NOT NULL CHECK (typ IN ('interní', 'externí')),
  hospitant_jmeno  TEXT NOT NULL,
  hospitant_inst   TEXT,                -- instituce externího hospitanta
  poznamka         TEXT,
  zaznam_id        UUID REFERENCES tridni_kniha_zaznamy(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.8 Tabulky BOZP

Junction table design (viz rozhodnutí M5 — škáluje na 150+ žáků, umožňuje čisté dotazy "kdo ještě nemá BOZP").

```sql
CREATE TABLE bozp_zaznamy (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum       DATE NOT NULL,
  popis       TEXT NOT NULL,
  je_hromadne BOOLEAN NOT NULL DEFAULT TRUE,  -- hromadné (začátek roku) vs. individuální (nástup)
  school_year TEXT NOT NULL,
  created_by  UUID REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bozp_attendance (
  bozp_id    UUID NOT NULL REFERENCES bozp_zaznamy(id) ON DELETE RESTRICT,
  student_id UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  PRIMARY KEY (bozp_id, student_id)
);
```

**Klíčový dotaz — žáci bez BOZP záznamu:**
```sql
SELECT s.id, s.first_name, s.last_name
FROM students s
WHERE s.status = 'active'
  AND NOT EXISTS (
    SELECT 1 FROM bozp_attendance ba
    JOIN bozp_zaznamy bz ON bz.id = ba.bozp_id
    WHERE ba.student_id = s.id
      AND bz.school_year = '2025/2026'
  );
```

### 5.9 Evidence docházky

```sql
CREATE TABLE attendance_records (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id           UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  staff_id             UUID REFERENCES staff(id),
  date                 DATE NOT NULL,
  slot_id              UUID,                     -- FK → schedule_slots (P2)
  event_id             UUID,                     -- FK → events (P2)
  absence_request_id   UUID REFERENCES absence_requests(id) ON DELETE SET NULL,
                                                 -- nullable — doložení absence žádostí ZZ
                                                 -- 1 žádost : N denních záznamů (date_from..date_to)
                                                 -- NULL = absence bez doložené žádosti
  status      TEXT NOT NULL CHECK (status IN (
                'present', 'absent_excused', 'absent_unexcused', 'late', 'remote'
              )),
  hodiny      INTEGER,                  -- počet zameškaných hodin daný den (výchozí: 4, čtvrtek: 6)
  note        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON attendance_records (student_id, date);
CREATE INDEX ON attendance_records (date);
CREATE INDEX ON attendance_records (absence_request_id) WHERE absence_request_id IS NOT NULL;
```

**Propojení s `absence_requests`:**
Jeden záznam v `absence_requests` (date_from → date_to) odpovídá N záznamům v `attendance_records` — jeden na každý zameškaný den v daném rozsahu. Při zadávání absence v UI systém automaticky dohledá schválenou žádost pro daného žáka a datum (`status = 'approved'`, datum v rozsahu `date_from..date_to`) a předvyplní `absence_request_id`. Průvodce může propojení opravit ručně. Dotaz „má tato absence doloženou žádost?" = `WHERE absence_request_id IS NOT NULL`.

**Klíčová business logika:**
- Výchozí počet hodin za den: 4 (standardní), 6 (čtvrtek — terénní program)
- Prázdniny a ředitelské volno se nezapočítávají
- Žáci před `enrollment_date` nebo po `withdrawal_date` se zobrazují s příznakem, absence se nevykazuje
- Prodloužená absence = jeden záznam s možností "prodloužit" (ne nový záznam)

### 5.10 Uzavření pololetí (`semester_attendance_summary`)

Agregát docházky za 1. pololetí pro potřeby M3 XML výkazu. "Zamčeno" k 31. 1.

```sql
CREATE TABLE semester_attendance_summary (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id           UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  school_year          TEXT NOT NULL,
  semester             SMALLINT NOT NULL CHECK (semester IN (1, 2)),
  oml_h                INTEGER,          -- omluvené hodiny (NULL ≠ 0 — viz pravidla M3)
  neoml_h              INTEGER,          -- neomluvené hodiny
  transfer_hours_oml   INTEGER DEFAULT 0, -- hodiny převzaté z předchozí školy při přestupu
  transfer_hours_neoml INTEGER DEFAULT 0,
  locked_at            TIMESTAMPTZ,       -- NULL = dosud neuzavřeno
  locked_by            UUID REFERENCES staff(id),
                                          -- potvrzení správnosti a uzamčení = jeden krok
                                          -- ředitel spustí manuálně „Uzavřít pololetí" v UI
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, school_year, semester)
);
```

**Pravidla pro OML_H/NEOML_H (dle MŠMT metodiky):**
- Věty před `PLAT_ZAC = 01.02.` → prázdno (ne nula)
- Žáci s `zpusob ≠ 11` (§38, §41) → prázdno
- Žák přistoupivší po 1. 2. → prázdno
- Přestup: hodiny z předchozí školy se sčítají (`transfer_hours_*`)
- Výjimka: přechod §38 → §11 od 2. pololetí → **nuly jsou povinné** (ne prázdno)

### 5.11 Matriční výkazy — XML generátor

**Výstupní soubory:**

| Soubor | Kdy |
|--------|-----|
| `Z250002639_01.xml` | jarní i podzimní sběr |
| `Z250002639_01a.xml` | jarní i podzimní sběr |
| `Z250002639_01b.xml` | **pouze podzimní sběr** |

**Technické požadavky:**
- Kódování: **windows-1250** (ne UTF-8) — Edge Function musí konvertovat
- Formát datumů: **DD.MM.YYYY**
- Prázdno vs. 0: `oml_h` a `neoml_h` jsou `INTEGER NULLABLE` — v XML se `NULL` exportuje jako prázdné pole, `0` jako `0` — nikdy `DEFAULT 0`
- Verze struktury: ZS.025 (základní a „a"), ZSb.22 („b")

**Logika generování jarního sběru (Edge Function):**
1. Uzavřít věty s `PLAT_KON = 31.01.`
2. Vytvořit nové věty s `PLAT_ZAC = 01.02.` a vyplnit `OML_H`/`NEOML_H` ze `semester_attendance_summary`
3. Pro žáky s `zpusob ≠ 11` ponechat `OML_H`/`NEOML_H` prázdné
4. Pro žáky přistoupivší po 1. 2. ponechat prázdné
5. Výstup uložit do Supabase Storage + poskytnout ke stažení

### 5.12 Evidence úrazů — `injury_reports` *(stub — P3, nízká priorita)*

Tabulka `injury_reports` je **OUT OF SCOPE pro Fázi 3**. Implementace proběhne v samostatné migraci (`007_injury_reports.sql`) v rámci P3.

**Připravené propojení v existujících tabulkách:**
- `attendance_records.event_id` — nullable FK (P2 placeholder) umožní v budoucnu propojit absenci s úrazem přes `events`
- `bozp_zaznamy` + `bozp_attendance` jsou nezávislé na `injury_reports` a zůstanou beze změny

**Plánovaný obsah** (dle vyhl. 64/2005 Sb. o evidenci úrazů dětí, žáků a studentů):
- Identifikace žáka, datum, čas, místo úrazu
- Popis úrazu a okolností
- Svědci, ošetřující osoba
- Hlášení zákonným zástupcům (datum + způsob)
- Výstup: předvyplněný PDF / HTML pro manuální zadání do **InspIS SET**

**Propojení s `tridni_kniha_zaznamy`:** `injury_report_id` bude nullable FK v `attendance_records` (přidá se v `007_injury_reports.sql` přes `ALTER TABLE`). Nevyžaduje zpětnou změnu Fáze 3 schématu.

---

## 6. Modul VP — Výchovné poradenství

### 6.1 Přehled

Pokrývá dokumentaci výchovného poradce dle §4 vyhl. č. 72/2005 Sb. Citlivá data — omezený přístup (viz sekce 8).

### 6.2 Tabulka `vp_student_care`

```sql
CREATE TABLE vp_student_care (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  school_year     TEXT NOT NULL,

  care_type       TEXT NOT NULL CHECK (care_type IN (
                    'po_1', 'po_2', 'po_3', 'po_4', 'po_5', 'watch'
                  )),

  -- Doporučení ŠPZ (NULL pokud care_type IN ('po_1', 'watch'))
  spz_recommendation_date   DATE,
  spz_recommendation_expiry DATE,
  spz_review_due_date       DATE,
  informed_consent_date     DATE,
  informed_consent_on_file  BOOLEAN NOT NULL DEFAULT FALSE,

  -- IVP
  ivp_required              BOOLEAN NOT NULL DEFAULT FALSE,
  ivp_created_date          DATE,
  ivp_guardian_signed_date  DATE,
  ivp_last_evaluated_date   DATE,

  reason_for_care   TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                      'active', 'closed', 'transferred'
                    )),
  started_at        DATE NOT NULL DEFAULT CURRENT_DATE,
  closed_at         DATE,
  notes             TEXT,

  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (student_id, school_year)
);

CREATE TRIGGER trg_vp_student_care_updated_at
  BEFORE UPDATE ON vp_student_care
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 6.3 Tabulka `vp_intervention_log`

```sql
CREATE TABLE vp_intervention_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  care_id     UUID NOT NULL REFERENCES vp_student_care(id) ON DELETE RESTRICT,
  student_id  UUID NOT NULL REFERENCES students(id),   -- denormalizováno pro RLS

  entry_date  DATE NOT NULL,
  entry_type  TEXT NOT NULL CHECK (entry_type IN (
                'observation', 'observation_positive', 'intervention',
                'incident', 'incident_serious', 'parent_contact',
                'external_contact', 'meeting', 'admin', 'annual_plan'
              )),
  area        TEXT,

  description   TEXT NOT NULL,
  action_taken  TEXT,
  open_task     TEXT,

  recorded_by_staff_id  UUID REFERENCES staff(id),
  parent_contacted      BOOLEAN NOT NULL DEFAULT FALSE,
  parent_contact_notes  TEXT,
  external_contact_name TEXT,
  external_contact_notes TEXT,

  is_sensitive  BOOLEAN NOT NULL DEFAULT FALSE,

  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON vp_intervention_log (care_id, entry_date DESC);
CREATE INDEX ON vp_intervention_log (student_id, entry_date DESC);
CREATE INDEX ON vp_intervention_log (entry_type);

CREATE TRIGGER trg_vp_intervention_log_updated_at
  BEFORE UPDATE ON vp_intervention_log
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 6.4 Tabulka `vp_document`

```sql
CREATE TABLE vp_document (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  care_id       UUID NOT NULL REFERENCES vp_student_care(id) ON DELETE RESTRICT,
  student_id    UUID NOT NULL REFERENCES students(id),

  doc_type      TEXT NOT NULL CHECK (doc_type IN (
                  'spz_recommendation', 'informed_consent', 'ivp', 'ivp_evaluation',
                  'plpp', 'psychiatric_report', 'psychological_report',
                  'neurological_report', 'court_order', 'ospod_communication',
                  'parent_meeting_notes', 'other'
                )),
  title         TEXT NOT NULL,
  document_date DATE,
  file_ref      TEXT,
  storage_type  TEXT NOT NULL DEFAULT 'physical' CHECK (
                  storage_type IN ('physical', 'supabase_storage', 'drive_url')
                ),
  notes         TEXT,
  uploaded_by   UUID REFERENCES staff(id),
  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON vp_document (care_id);
CREATE INDEX ON vp_document (student_id, doc_type);
```

### 6.5 Tabulka `vp_annual_plan`

```sql
CREATE TABLE vp_annual_plan (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  school_year    TEXT NOT NULL UNIQUE,
  vp_staff_id    UUID NOT NULL REFERENCES staff(id),
  content_md     TEXT NOT NULL,
  approved_by    UUID REFERENCES staff(id),
  approved_at    DATE,
  status         TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                   'draft', 'approved', 'evaluated'
                 )),
  evaluation_md  TEXT,
  evaluated_at   DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.6 Lhůtové alerty (VP modul → `system_alerts`)

Denní cron (Vercel Cron nebo Supabase pg_cron) vkládá záznamy do `system_alerts`:

| Podmínka | Kdy | Severity |
|----------|-----|----------|
| `spz_recommendation_expiry` ≤ dnes + 60 dní | Průběžně | `warning` |
| `spz_review_due_date` ≤ dnes + 30 dní | Průběžně | `warning` |
| `ivp_last_evaluated_date` > dnes - 365 dní a `ivp_required = TRUE` | Průběžně | `warning` |
| `informed_consent_on_file = FALSE` a `care_type NOT IN ('po_1', 'watch')` | Průběžně | `critical` |
| PO 2–5 bez dokumentu `spz_recommendation` | Průběžně | `critical` |

**Doručovací kanály (potvrzeno):**
- **Email přes Resend** → VP (Mgr. Ludmila Mráčková)
- **Discord webhook** → pedagogický tým (stejný webhook jako ostatní systémové alerty)

Architektura: `system_alerts` INSERT → Edge Function (notification router) → Resend API + Discord Webhook POST. Konzistentní s notifikační architekturou ostatních modulů (sekce 5.16 PRD).

---

## 7. Integrace externích systémů

### 7.1 Resend (email)

Jediný emailový provider pro celý systém:
- **Auth:** Supabase magic link přes vlastní SMTP (`smtp.resend.com:465`)
- **Transakční emaily:** Edge Function volá Resend API
- **Delivery status:** Resend webhook → aktualizace `comm_log.status`

### 7.2 Fio API

```
Edge Function (scheduled — denně nebo manuální trigger)
  → GET https://www.fio.cz/ib_api/rest/last/{token}/transactions.json
  → parse transactions
  → match na student přes variabilní symbol (= students.kod_zaka jako 4místné číslo ze sekvence)
  → INSERT do payment_transactions
  → unmatched → INSERT do system_alerts
```

Token uložen jako Supabase Secret.

### 7.3 MŠMT — matriční výkazy

Viz sekce 5.10. Termíny:

| Sběr | RDAT | Deadline školy | Adresát |
|------|------|----------------|---------|
| Jarní | 31. 3. | **15. 4.** | KÚ Ústeckého kraje, datová schránka |
| Podzimní | 30. 9. | říjen | KÚ Ústeckého kraje |

Soubor „b" se předává **pouze při podzimním sběru**.

### 7.4 Discord

Výstupní notifikace: Incoming Webhook POST s JSON payloadem. Typy událostí: nezaplacené školné, nová omluvenka, nový úraz, alert z `system_alerts` se severity `critical`.

### 7.5 InspIS SET (ČŠI)

Evidence úrazů: předvyplněný výstup z `injury_reports` pro manuální zadání do InspIS SET. V první verzi PDF/HTML export, v pozdější verzi přímý import.

---

## 8. Bezpečnost a přístupová práva

### 8.1 Matice přístupů

| Role | Matrika | Třídní kniha | Platby | VP (základní) | VP (citlivé) | VP dokumenty |
|------|---------|--------------|--------|---------------|--------------|--------------|
| `director` | R/W | R/W | R/W | R/W | R/W | R/W všechny |
| `vp` | R | R/W | R | R/W | R/W | R/W všechny |
| `guide` | R (vlastní skupina) | R/W (vlastní skupina) | — | R (care_type + status) | ❌ | R (spz, ivp, plpp) |
| `assistant` | R (vlastní skupina) | WRITE vlastní obs. | — | ❌ | ❌ | ❌ |
| `readonly` | R | R | R | ❌ | ❌ | ❌ |

### 8.2 Klíčové RLS politiky

```sql
-- Průvodce vidí jen žáky své skupiny
CREATE POLICY "guide_read_students" ON students
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM staff_groups sg
      JOIN group_memberships gm ON gm.group_id = sg.group_id
      WHERE sg.staff_id = auth.uid()
        AND gm.student_id = students.id
        AND sg.valid_to IS NULL
        AND gm.valid_to IS NULL
    )
  );

-- VP a director vidí vše v VP modulu
CREATE POLICY "vp_director_full_access" ON vp_intervention_log
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM staff
      WHERE id = auth.uid() AND role IN ('vp', 'director')
    )
  );

-- Průvodce vidí non-sensitive záznamy žáků své skupiny
CREATE POLICY "guide_read_vp_log" ON vp_intervention_log
  FOR SELECT USING (
    is_sensitive = FALSE
    AND student_id IN (
      SELECT s.id FROM students s
      JOIN group_memberships gm ON gm.student_id = s.id
      JOIN staff_groups sg ON sg.group_id = gm.group_id
      WHERE sg.staff_id = auth.uid()
        AND sg.valid_to IS NULL
    )
  );

-- Průvodce může vložit vlastní (non-sensitive) pozorování
CREATE POLICY "guide_insert_own_observation" ON vp_intervention_log
  FOR INSERT WITH CHECK (
    recorded_by_staff_id = auth.uid()
    AND is_sensitive = FALSE
  );

-- Průvodce vidí pouze vybrané typy dokumentů VP
CREATE POLICY "guide_read_vp_documents" ON vp_document
  FOR SELECT USING (
    doc_type IN ('spz_recommendation', 'ivp', 'plpp')
    AND student_id IN (
      SELECT s.id FROM students s
      JOIN group_memberships gm ON gm.student_id = s.id
      JOIN staff_groups sg ON sg.group_id = gm.group_id
      WHERE sg.staff_id = auth.uid()
        AND sg.valid_to IS NULL
    )
  );
```

---

## 9. Migrační cesty

### 9.1 Stávající skripty → IS

| Skript | Modul | Funkce | Nahrazuje ho v IS | Stav |
|--------|-------|--------|-------------------|------|
| `KartaZaka.gs` (Apps Script) | Matrika | PDF karta žáka (1 žák = 1 PDF) | `GET /api/students/:id/karta.pdf` — Fáze 1–2 | Dočasný |
| `gen_tridnice_final.py` (Python) | Třídní kniha | PDF třídní knihy za zvolené období | PDF export třídní knihy — Fáze 3 | Dočasný |
| Google Calendar | Třídní kniha | Vstupní kanál záznamů výuky | Nativní zadávání v IS od 1. 9. 2026 | **Nahrazen od Fáze 3** |

**Princip:** Každý skript / kanál zůstává v provozu dokud IS nepřevezme jeho funkcionalitu. Žádné paralelní běhání — jasný předávací bod per modul.

### 9.2 Import dat — stav a skripty

#### Strategie

Hromadný import matrikových dat probíhá přes **Supabase SQL Editor**
(PL/pgSQL `DO $$` bloky). Python skripty zůstávají jako záloha a reference,
ale nejsou primárním nástrojem. Viz ARCH-NOTES sekce 16.

#### Provedené importy (2026-05-07)

| Skript | Obsah | Stav |
|--------|-------|------|
| `import_20_zaci.sql` | 20 žáků 2025/2026, 30 ZZ, skupinové zápisy, 2 SVP záznamy | ✅ hotovo |
| `import_12_novi_zaci.sql` | 12 nových žáků 2026/2027, 20 ZZ, přechod skupin | ✅ hotovo |

#### Zbývající importy

| Soubor | Cílová tabulka | Stav |
|--------|----------------|------|
| `tridni_kniha.csv` (182 záznamů) | `tridni_kniha_zaznamy` | čeká na Fázi 3 |
| `dochazka_souhrn.csv` | `semester_attendance_summary` | čeká na Fázi 3 |
| `dochazka_detail.csv` | `attendance_records` | čeká na Fázi 3 |
| `svp_parovani_komplet.csv` (1 859 vazeb) | `svp_vazby` | čeká na Fázi 3 + `svp_vystupy` |
| *(vilekula-pokrok export)* | `svp_vystupy` | čeká na Fázi 3 |

**Poznámka:** `svp_vazby` import musí proběhnout až po naplnění `svp_vystupy` (FK závislost).

#### Otevřené položky

| Položka | Žák | Priorita |
|---------|-----|----------|
| `student_matrika_a` záznam | Polák Michael VIL-2016-032 | P2 — doplnit po obdržení pspo/id_znev z PPP |
| `kod_zaka_msmt` pro všechny žáky | 32 žáků | P2 — nutné před generací MŠMT XML |

---

## 10. Rozhodnutá otázky (původně otevřené)

Všechny otázky byly uzavřeny v TRD review session 2026-04-27.

| # | Otázka | Rozhodnutí | Dopad na TRD |
|---|--------|------------|--------------|
| O1 | Žáci s PO, IVP, asistent | PO 2 (1×) + PO 3 (1×, k němu Michaela Kruchlová jako asistentka → `TYP_TR = '100A1'`) | Soubor „a" aktivní — nesmí být prázdný; viz sekce 3.11 |
| O2 | GDPR retention policy | Neblokuje Fázi 1. TODO: konzultace s GDPR poradcem před Fází 4. | Konzervativní výchozí: aktivní žák + 10 let |
| O3 | Spisový řád | Vilekula nemá schválený spisový řád. Neblokuje — modul Spisová služba je P3, OUT OF SCOPE. | Žádný |
| O4 | Číselník výstupů ŠVP | Tabulka `svp_vystupy` v Supabase s kódy z vilekula-pokrok (Mapa růstu). CSV export čeká na dodání. | Přidána tabulka `svp_vystupy`, `svp_vazby` dostala FK; viz sekce 5.5–5.6 |
| O5 | Google Calendar jako vstup | Nativní zadávání v IS od 1. 9. 2026. Google Calendar se nahrazuje, neintegruje. | Migrační cesta aktualizována; viz sekce 9.1 |
| O6 | Notifikace VP lhůt | Email přes Resend (VP) + Discord webhook (tým). | Aktualizována sekce 6.6 |
| O7 | Archivace VP záznamu při přechodu roku | Nový `vp_student_care` per školní rok. Historické záznamy přístupné přes starý `care_id`. | Potvrzeno `UNIQUE (student_id, school_year)`; viz sekce 6.2 |
| O8 | Schránka důvěry | Fyzická schránka, OUT OF SCOPE. Možné P3 rozšíření v budoucnu. | Žádný |
| O9 | App Router vs. Pages Router | App Router potvrzen. | Stack tabulka aktualizována; viz sekce 1.1 |
| O10 | PDF generátor | `@react-pdf/renderer` potvrzen. | Stack tabulka aktualizována; viz sekce 1.1 |

---

*TRD v1.7 — rozšiřuje v1.6 o migraci 009_rls_tridni_kniha.sql a UI stránky třídní knihy (Fáze 3 zahájena).*
