# Modul M-VP: Výchovné poradenství
*Doplněk TRD vilekula-is — navazuje na existující schema (students, staff, groups, school_year)*

---

## 1. Účel modulu a rozsah

Modul pokrývá veškerou dokumentaci výchovného poradce vyžadovanou § 4 vyhl. č. 72/2005 Sb.:
- evidenci žáků v péči VP (s PO i bez)
- záznamník intervencí (datované záznamy s přijatými opatřeními)
- kartu žáka — pohled VP (agregovaný přehled ze záznamníku)
- správu dokumentů (doporučení ŠPZ, informované souhlasy, zprávy)
- přehledovou evidenci s kontrolou lhůt (platnost doporučení ŠPZ, vyhodnocení PO)
- roční plán VP a jeho vyhodnocení

Modul **nesdílí data s třídní knihou ani s matrikou** — jedná se o citlivé poradenské záznamy s omezeným přístupem. Je však **propojen se `students`** jako zdrojovým registrem žáků.

---

## 2. Datový model

### 2.1 Přehled nových tabulek

```
vp_student_care         -- evidence žáků v péči VP (1 řádek per žák per školní rok)
vp_intervention_log     -- záznamník intervencí (N řádků per žák)
vp_document             -- uložiště odkazů na dokumenty (doporučení ŠPZ, souhlasy, zprávy)
vp_annual_plan          -- roční plán VP per školní rok
vp_annual_plan_eval     -- vyhodnocení ročního plánu
```

---

### 2.2 `vp_student_care`

```sql
CREATE TABLE vp_student_care (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  school_year     TEXT NOT NULL,                    -- např. "2025/2026"

  -- Klasifikace péče
  care_type       TEXT NOT NULL CHECK (care_type IN (
                    'po_1',   -- PO 1. stupně (PLPP, bez doporučení ŠPZ)
                    'po_2',   -- PO 2. stupně
                    'po_3',   -- PO 3. stupně
                    'po_4',   -- PO 4. stupně
                    'po_5',   -- PO 5. stupně
                    'watch'   -- sledování VP bez formálního PO
                  )),

  -- Doporučení ŠPZ (NULL pokud care_type = 'po_1' nebo 'watch')
  spz_recommendation_date   DATE,
  spz_recommendation_expiry DATE,     -- max. 2 roky od vydání
  spz_review_due_date       DATE,     -- datum plánovaného vyhodnocení ŠPZ (max. 1 rok)
  informed_consent_date     DATE,     -- datum podpisu informovaného souhlasu ZZ
  informed_consent_on_file  BOOLEAN NOT NULL DEFAULT FALSE,

  -- IVP (pokud doporučeno ŠPZ)
  ivp_required              BOOLEAN NOT NULL DEFAULT FALSE,
  ivp_created_date          DATE,
  ivp_guardian_signed_date  DATE,
  ivp_last_evaluated_date   DATE,

  -- Stav a správa záznamu
  reason_for_care   TEXT NOT NULL,    -- volný text: důvod zařazení do péče
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'transferred')),
  started_at        DATE NOT NULL DEFAULT CURRENT_DATE,
  closed_at         DATE,
  notes             TEXT,

  -- Metadat
  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (student_id, school_year)    -- jeden záznam péče per žák per rok
);

-- Trigger: updated_at
CREATE TRIGGER vp_student_care_updated_at
  BEFORE UPDATE ON vp_student_care
  FOR EACH ROW EXECUTE FUNCTION moddatetime(updated_at);
```

**Lhůtová logika** (viz sekce 5 — automatické alertování):
- `spz_recommendation_expiry` → alert 60 dní před vypršením
- `spz_review_due_date` → alert 30 dní před termínem
- `ivp_last_evaluated_date` → alert pokud starší než 365 dní a `ivp_required = TRUE`
- `informed_consent_on_file = FALSE` a `care_type != 'watch'` → blokující varování při ukládání

---

### 2.3 `vp_intervention_log`

Jádro záznamníku intervencí — každý řádek odpovídá jednomu datovanému záznamu (observace, schůzka, incident, kontakt s rodiči, kontakt s externím subjektem apod.).

```sql
CREATE TABLE vp_intervention_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  care_id         UUID NOT NULL REFERENCES vp_student_care(id) ON DELETE RESTRICT,
  student_id      UUID NOT NULL REFERENCES students(id),  -- denormalizováno pro RLS a dotazy

  -- Klasifikace záznamu
  entry_date      DATE NOT NULL,
  entry_type      TEXT NOT NULL CHECK (entry_type IN (
                    'observation',        -- pozorování pedagoga
                    'observation_positive', -- pozorování – pokrok
                    'intervention',       -- přímá intervence VP/pedagoga
                    'incident',           -- incident (standardní)
                    'incident_serious',   -- závažný incident (bezpečnost, sebepoškozování apod.)
                    'parent_contact',     -- kontakt s rodičem/zákonným zástupcem
                    'external_contact',   -- kontakt s externím subjektem (ŠPZ, OSPOD, psychiatrie…)
                    'meeting',            -- schůzka (s rodiči, externím subjektem)
                    'admin',              -- administrativní záznam (dokumenty, platnosti)
                    'annual_plan'         -- záznam k ročnímu plánu
                  )),
  area            TEXT,                   -- oblast (např. "bezpečnost", "emoční regulace", "spolupráce s rodinou")

  -- Obsah
  description     TEXT NOT NULL,         -- popis situace / pozorování
  action_taken    TEXT,                  -- přijaté opatření
  open_task       TEXT,                  -- otevřený úkol vyplývající z záznamu

  -- Kontext
  recorded_by_staff_id  UUID REFERENCES staff(id),   -- kdo zaznamenlal (pedagog, ne nutně VP)
  parent_contacted      BOOLEAN NOT NULL DEFAULT FALSE,
  parent_contact_notes  TEXT,
  external_contact_name TEXT,            -- název subjektu (PPP, OSPOD, psychiatrie…)
  external_contact_notes TEXT,

  -- Příznak citlivosti
  is_sensitive    BOOLEAN NOT NULL DEFAULT FALSE,   -- omezuje přístup jen na VP a ředitele

  -- Metadata
  created_by  UUID NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON vp_intervention_log (care_id, entry_date DESC);
CREATE INDEX ON vp_intervention_log (student_id, entry_date DESC);
CREATE INDEX ON vp_intervention_log (entry_type);

CREATE TRIGGER vp_intervention_log_updated_at
  BEFORE UPDATE ON vp_intervention_log
  FOR EACH ROW EXECUTE FUNCTION moddatetime(updated_at);
```

**Poznámka k `is_sensitive`:** záznamy označené jako citlivé (sebepoškozování, sexualizované chování, citlivé rodinné informace) jsou přístupné pouze uživatelům s rolí `vp` nebo `director`. Průvodci je nevidí, i když mají přístup k ostatním záznamům daného žáka.

---

### 2.4 `vp_document`

Neukládáme binární obsah do DB — ukládáme metadata a odkaz (Supabase Storage nebo Google Drive).

```sql
CREATE TABLE vp_document (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  care_id     UUID NOT NULL REFERENCES vp_student_care(id) ON DELETE RESTRICT,
  student_id  UUID NOT NULL REFERENCES students(id),

  doc_type    TEXT NOT NULL CHECK (doc_type IN (
                'spz_recommendation',     -- doporučení ŠPZ
                'informed_consent',       -- informovaný souhlas ZZ
                'ivp',                    -- IVP
                'ivp_evaluation',         -- vyhodnocení IVP
                'plpp',                   -- PLPP (PO 1. stupně)
                'psychiatric_report',     -- psychiatrická zpráva
                'psychological_report',   -- psychologická zpráva
                'neurological_report',    -- neurologická zpráva
                'court_order',            -- soudní rozhodnutí (opatrovnictví apod.)
                'ospod_communication',    -- komunikace s OSPOD
                'parent_meeting_notes',   -- zápis ze schůzky s rodiči
                'other'
              )),
  title           TEXT NOT NULL,
  document_date   DATE,
  file_ref        TEXT,        -- cesta v Supabase Storage nebo URL Drive
  storage_type    TEXT NOT NULL DEFAULT 'physical' CHECK (
                    storage_type IN ('physical', 'supabase_storage', 'drive_url')
                  ),
  notes           TEXT,
  uploaded_by     UUID REFERENCES staff(id),
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON vp_document (care_id);
CREATE INDEX ON vp_document (student_id, doc_type);
```

---

### 2.5 `vp_annual_plan`

```sql
CREATE TABLE vp_annual_plan (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  school_year TEXT NOT NULL UNIQUE,
  vp_staff_id UUID NOT NULL REFERENCES staff(id),
  content_md  TEXT NOT NULL,          -- obsah plánu v Markdownu
  approved_by UUID REFERENCES staff(id),
  approved_at DATE,
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'evaluated')),
  evaluation_md TEXT,                 -- vyhodnocení na konci roku
  evaluated_at  DATE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 3. Integrace se stávajícím schematem

### 3.1 Propojení na `students`

`vp_student_care.student_id` a `vp_intervention_log.student_id` jsou cizí klíče na `students.id`. Modul VP nikdy nevytváří vlastní záznamy o žácích — používá `students` jako jediný zdroj pravdy.

### 3.2 Pohled na kartě žáka (`students` detail page)

Na stránce žáka přibyde záložka **„Výchovné poradenství"** (viditelná pouze pro role `vp` a `director`). Záložka zobrazuje:

```
/students/[id]/counseling
  → vp_student_care (aktuální školní rok) — stav PO, platnosti, otevřené úkoly
  → vp_intervention_log (posledních 10, s tlačítkem „zobrazit vše")
  → vp_document (seznam dokumentů s možností nahrání)
  → shortcut: „Přidat záznam"
```

### 3.3 Tok dat: záznamník → karta žáka

Klíčový integrační bod: **záznam přidaný v záznamníku se okamžitě zobrazí na kartě žáka** (jsou to záznamy ze stejné tabulky `vp_intervention_log`, filtrované per `student_id`). Žádný manuální přepis — databáze je single source of truth.

```
Průvodce/VP přidá záznam do záznamníku
         ↓
vp_intervention_log INSERT (care_id + student_id)
         ↓
Karta žáka (záložka VP) okamžitě zobrazuje nový záznam
         ↓
Přehledová evidence (vp_student_care) aktualizuje updated_at
```

### 3.4 Propojení na `school_year`

`vp_student_care.school_year` musí být konzistentní s formátem `school_year` v ostatních tabulkách systému (dle TRD sekce 3: TEXT `"2025/2026"`).

---

## 4. Přístupová práva (RLS)

Modul zavádí nová přístupová pravidla navázaná na roli uživatele v `staff.role`.

### 4.1 Role a přístupy

| Role | `vp_student_care` | `vp_intervention_log` | `vp_document` | `vp_annual_plan` |
|---|---|---|---|---|
| `director` | READ/WRITE | READ/WRITE (vč. sensitive) | READ/WRITE | READ/WRITE |
| `vp` | READ/WRITE | READ/WRITE (vč. sensitive) | READ/WRITE | READ/WRITE |
| `guide` (průvodkyně) | READ (own entries only) | READ (non-sensitive) / WRITE own | — | READ |
| `assistant` | READ (non-sensitive) | WRITE own observations | — | — |
| `parent` | — | — | — | — |

**Vysvětlení `guide` / `assistant` přístupu:**  
Průvodci a asistenti mohou přidávat vlastní pozorování (`recorded_by_staff_id = auth.uid()`) — to je klíčový tok, protože pedagogové jsou primárním zdrojem dat. Nemohou však editovat záznamy jiných, měnit `is_sensitive`, ani vidět citlivé záznamy.

### 4.2 RLS politiky (ukázka)

```sql
-- Průvodce vidí jen non-sensitive záznamy žáků své skupiny
CREATE POLICY "guide_read_vp_log" ON vp_intervention_log
  FOR SELECT USING (
    is_sensitive = FALSE
    AND student_id IN (
      SELECT s.id FROM students s
      JOIN group_memberships gm ON gm.student_id = s.id
      JOIN staff_groups sg ON sg.group_id = gm.group_id
      WHERE sg.staff_id = auth.uid()
    )
  );

-- VP a director vidí vše
CREATE POLICY "vp_director_full_access" ON vp_intervention_log
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM staff
      WHERE id = auth.uid()
      AND role IN ('vp', 'director')
    )
  );

-- Průvodce může vložit záznam (jako recorded_by)
CREATE POLICY "guide_insert_own_observation" ON vp_intervention_log
  FOR INSERT WITH CHECK (
    recorded_by_staff_id = auth.uid()
    AND is_sensitive = FALSE
  );
```

---

## 5. Lhůtové alertování

Nová server-side logika (Supabase Edge Function nebo Next.js scheduled route) kontroluje lhůty a generuje alerty.

### 5.1 Typy alertů

| Trigger | Kdy | Příjemce |
|---|---|---|
| `spz_recommendation_expiry` blíží se | 60 dní před | VP + director |
| `spz_review_due_date` blíží se | 30 dní před | VP |
| `ivp_last_evaluated_date` > 365 dní | Průběžně | VP |
| `informed_consent_on_file = FALSE` a `care_type != 'watch'` | Při každém otevření karty žáka | VP (inline warning) |
| Žák s PO 2–5 bez dokumentu `spz_recommendation` | Průběžně | VP |

### 5.2 Implementace

```typescript
// Edge Function nebo cron route: GET /api/vp/deadline-check
// Spouštět 1× denně (Supabase pg_cron nebo Vercel cron)

const alerts = await supabase
  .from('vp_student_care')
  .select(`
    id, school_year, reason_for_care, care_type,
    spz_recommendation_expiry, spz_review_due_date,
    ivp_required, ivp_last_evaluated_date,
    informed_consent_on_file,
    students(full_name)
  `)
  .eq('status', 'active')
  .or(`
    spz_recommendation_expiry.lte.${addDays(today, 60)},
    spz_review_due_date.lte.${addDays(today, 30)},
    informed_consent_on_file.eq.false
  `);

// Výsledek: uložit do tabulky `system_alerts` (sdílená s ostatními moduly)
// nebo rovnou zobrazit v UI na dashboardu VP
```

---

## 6. API endpointy

Všechny endpointy pod `/api/vp/` vyžadují autentizaci; RLS je vynuceno na úrovni Supabase.

| Metoda | Endpoint | Popis |
|---|---|---|
| `GET` | `/api/vp/students` | Přehledová evidence žáků v péči VP (aktuální rok) |
| `GET` | `/api/vp/students/[id]` | Karta žáka VP — care record + posledních N intervencí |
| `POST` | `/api/vp/students` | Zařadit žáka do péče VP |
| `PATCH` | `/api/vp/students/[id]` | Aktualizovat care record (platnosti, stav, IVP…) |
| `GET` | `/api/vp/log` | Záznamník intervencí (filtrovat per student, typ, datum) |
| `POST` | `/api/vp/log` | Přidat záznam do záznamníku |
| `PATCH` | `/api/vp/log/[id]` | Editovat záznam (jen vlastní nebo role vp/director) |
| `GET` | `/api/vp/documents/[care_id]` | Seznam dokumentů k záznamu péče |
| `POST` | `/api/vp/documents` | Přidat dokument (metadata + upload do Storage) |
| `GET` | `/api/vp/deadlines` | Přehled blížících se lhůt (pro dashboard) |
| `GET` | `/api/vp/export/csv` | Export záznamníku intervencí do CSV |
| `GET` | `/api/vp/export/md/[student_id]` | Export karty žáka VP do Markdownu |
| `GET` | `/api/vp/annual-plan/[year]` | Načíst roční plán VP |
| `PUT` | `/api/vp/annual-plan/[year]` | Uložit / aktualizovat roční plán |

### 6.1 Export: CSV záznamník

`GET /api/vp/export/csv?year=2025/2026`

Exportuje všechny záznamy z `vp_intervention_log` pro daný školní rok ve stejné struktuře jako ručně generovaný CSV (viz dokument *Zaznamnik_intervenci_VP_2025_2026.csv*):

```
Datum, Žák, Typ záznamu, Oblast, Popis, Přijaté opatření, Zaznamenal/a,
Kontakt s rodiči, Kontakt s ext. subjektem, Otevřený úkol
```

Citlivé záznamy (`is_sensitive = TRUE`) jsou v exportu pro roli `guide` vynechány; pro `vp` a `director` exportovány celé s hlavičkou `⚠ CITLIVÝ ZÁZNAM`.

### 6.2 Export: Markdown karta žáka

`GET /api/vp/export/md/[student_id]?year=2025/2026`

Generuje Markdown ve struktuře shodné s ručně vytvořenými záznamy VP (oddíly 1–7: identifikace, kontext, chronologie, průřezová témata, spolupráce, závěr, podpis). Chronologická sekce je generována dynamicky z `vp_intervention_log`, ostatní sekce z `vp_student_care`.

---

## 7. UI — přehled obrazovek

### 7.1 Dashboard VP (`/vp`)

Viditelný pouze pro role `vp` a `director`.

```
┌─────────────────────────────────────────────────────┐
│  Výchovné poradenství — 2025/2026                   │
├──────────────────┬──────────────────────────────────┤
│ Žáci v péči (5) │  ⚠ Blížící se lhůty (3)          │
│                  │  • Vilém L. — platnost ŠPZ (45d) │
│ • Vilém L.  PO3 │  • Teodor V. — souhlas ZZ chybí  │
│ • Žofie L.  WCH │  • Radek T. — nesd. obava únosu  │
│ • Teodor V. PO2 ├──────────────────────────────────┤
│ • Radek T.  WCH │  Poslední záznamy                 │
│ • Sophia D. WCH │  • 14. 4. Vilém — exkurze ✓      │
│                  │  • 21. 4. Teodor — klíče         │
│ + Přidat žáka   │  • 19. 4. Radek — dohoda výpravy │
└──────────────────┴──────────────────────────────────┘
```

### 7.2 Karta žáka VP (`/students/[id]/counseling`)

Záložka na stránce žáka. Zobrazuje:
- hlavičku (stupeň PO, platnosti, stav souhlasu) s inline varováními
- timeline záznamů (filtrovat po typu; citlivé označeny ikonou)
- seznam dokumentů s možností nahrání
- tlačítka: „Přidat záznam" / „Exportovat MD" / „Exportovat CSV"

### 7.3 Záznamník (`/vp/log`)

Tabulkový pohled na všechny záznamy (všichni žáci, aktuální rok). Filtry: žák, typ, oblast, datum od–do, otevřený úkol ano/ne. Seřazeno sestupně dle data. Inline přidání záznamu.

---

## 8. Otevřené otázky pro rozhodnutí

1. **Notifikace lhůt e-mailem:** Má systém posílat e-mailový alert VP přes Resend, nebo stačí upozornění v UI dashboardu? Resend je pro auth e-maily již nakonfigurován — rozšíření na transakční alerty by bylo triviální.

2. **Schránka důvěry (z MPP):** Žáci mají fyzickou schránku důvěry. Bude digitální ekvivalent součástí vilekula-is, nebo zůstane mimo systém? Pokud ano, patří sem nebo do jiného modulu?

3. **Roční plán VP jako volný text (MD) vs. strukturovaný formulář:** Navrhuju MD editor (jednodušší), ale pokud bude potřeba strojové vyhodnocení cílů, dává smysl strukturovaný formulář s cíli jako záznamy v DB.

4. **Přístup průvodců k `vp_student_care`:** Mají průvodci vidět, zda je žák formálně v péči VP a jaký má stupeň PO? Nebo jen záznamy svých pozorování? (Stupeň PO je důležitý pro volbu pedagogického přístupu, ale je to poradenský údaj.)

5. **Archivace při přechodu školního roku:** `vp_student_care` má `UNIQUE (student_id, school_year)` — při přechodu do nového roku se vytvoří nový záznam, starý se uzavře (`status = 'closed'`). Historické záznamy v `vp_intervention_log` zůstávají přístupné přes starý `care_id`. Je to žádoucí chování?
