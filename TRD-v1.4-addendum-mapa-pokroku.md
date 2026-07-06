# TRD v1.4 — Addendum: Modul Mapa pokroku

**Verze:** 1.4
**Datum:** 2026-05-18
**Navazuje na:** TRD v1.3

**Changelog v1.4:**
- Přidána sekce 7 — Modul Mapa pokroku (migrace z vilekula-pokrok, tabulka
  `mapa_pokroku_hodnoceni`, RLS)
- Aktualizována sekce 1.3 — přidán `008_mapa_pokroku.sql` do schématu souborů
- Aktualizována sekce 9.2 — přidány řádky pro hodnocení a mapping soubory
- Aktualizovány sekce 9.1 a 10 — vilekula-pokrok migrován, otázka O4 uzavřena

---

## Změny v sekci 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
├── 007_fixes.sql             ← opravy migrací 001–006 (existující)
└── 008_mapa_pokroku.sql      ← Modul Mapa pokroku (nový)
```

Do `scripts/` přidat:

```
├── import_svp_vystupy.py     ← číselník výstupů ŠVP (existující, nyní hotovo)
├── vystup_mapping.csv        ← audit: pokrok_vystup_id → nilsson_vystup_id
├── zak_mapping.csv           ← audit: pokrok_zak_id → nilsson_student_id
└── import_mapa_pokroku.sql   ← 1 077 INSERT hodnocení (hotovo, spustit po 008)
```

---

## Nová sekce 7 — Modul Mapa pokroku

*(Původní sekce 7–10 se posouvají na 8–11.)*

### 7.1 Účel a kontext

Mapa pokroku (také Mapa růstu) sleduje míru zvládnutí konkrétních výstupů ŠVP
jednotlivými žáky. Modul byl původně provozován jako samostatná aplikace
(vilekula-pokrok, React + Supabase). V květnu 2026 migrován do Nilssonu jako integrovaný
modul — důvod: žáci, průvodkyně, skupiny i výstupy ŠVP jsou v Nilssonu, duplicitní
udržování Auth a dat ve dvou projektech nebylo udržitelné.

**Zdroj importovaných dat:** vilekula-pokrok Supabase (export: 1 pololetí, 18 žáků,
1 077 záznamů hodnocení). Mapování UUID provedeno Python skriptem; auditní CSV uložena
v `scripts/`.

### 7.2 Enum `stupen_zvladnuti`

```sql
CREATE TYPE stupen_zvladnuti AS ENUM (
  's_jistotou',   -- 1 zvládá samostatně a jistě
  'castecne',     -- 2 zvládá částečně
  's_dopomoci',   -- 3 zvládá s dopomocí
  'nezacali',     -- 4 zatím nezačali
  'nezvlada'      -- 5 nezvládá
);
```

Pořadí: nižší index = lepší výsledek (konvence školního prostředí, analogie ke
stupnici 1–5). Viz ARCH-NOTES sekce 14.1 pro zdůvodnění a důsledky pro SQL dotazy.

### 7.3 Tabulka `mapa_pokroku_hodnoceni`

```sql
CREATE TABLE mapa_pokroku_hodnoceni (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

  student_id    UUID        NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  vystup_id     UUID        NOT NULL REFERENCES svp_vystupy(id) ON DELETE RESTRICT,

  stupen        stupen_zvladnuti NOT NULL,

  school_year   TEXT        NOT NULL,               -- formát '2025/2026'
  semester      SMALLINT    NOT NULL CHECK (semester IN (1, 2)),

  hodnotil_id   UUID        REFERENCES staff(id),   -- NULL = import bez záznamu
  poznamka      TEXT,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (student_id, vystup_id, school_year, semester)
);
```

**Indexy:**

```sql
CREATE INDEX ON mapa_pokroku_hodnoceni (student_id, school_year, semester);
CREATE INDEX ON mapa_pokroku_hodnoceni (vystup_id);
CREATE INDEX ON mapa_pokroku_hodnoceni (school_year, semester);
```

**Klíčová návrhová rozhodnutí:**

- **Jeden záznam per (žák, výstup, rok, pololetí)** — UNIQUE constraint. Hodnocení
  se aktualizuje přes UPDATE, ne novými INSERT záznamy. Model je aktuální stav,
  ne historický log. Viz ARCH-NOTES sekce 14.4.
- **`hodnotil_id` nullable** — importované záznamy mají NULL (průvodkyně neměla Auth
  účet v době importu). Viz ARCH-NOTES sekce 14.3.
- **`poznamka TEXT`** (ne `TEXT[]`) — v pokroku bylo pole vždy prázdné. Viz
  ARCH-NOTES sekce 14.2.
- **`school_year` TEXT '2025/2026'** — konzistentní s celým Nilssonem (viz sekce 2.1
  a ARCH-NOTES sekce 9).

### 7.4 RLS politiky

Vzor identický s ostatními moduly Nilssonu.

```sql
ALTER TABLE mapa_pokroku_hodnoceni ENABLE ROW LEVEL SECURITY;
ALTER TABLE mapa_pokroku_hodnoceni FORCE ROW LEVEL SECURITY;

-- Ředitel a VP: plný přístup
CREATE POLICY "director_vp_full"
  ON mapa_pokroku_hodnoceni FOR ALL
  USING (is_director_or_vp());

-- Průvodce: čte záznamy žáků své skupiny
CREATE POLICY "guide_select"
  ON mapa_pokroku_hodnoceni FOR SELECT
  USING (staff_can_access_student(student_id));

-- Průvodce: vkládá záznamy žáků své skupiny (jen vlastní hodnotil_id)
CREATE POLICY "guide_insert"
  ON mapa_pokroku_hodnoceni FOR INSERT
  WITH CHECK (
    staff_can_access_student(student_id)
    AND (hodnotil_id IS NULL OR hodnotil_id = current_staff_id())
  );

-- Průvodce: edituje záznamy žáků své skupiny
CREATE POLICY "guide_update"
  ON mapa_pokroku_hodnoceni FOR UPDATE
  USING (staff_can_access_student(student_id))
  WITH CHECK (
    staff_can_access_student(student_id)
    AND (hodnotil_id IS NULL OR hodnotil_id = current_staff_id())
  );

-- Mazání: jen director/VP (pokryto policy "director_vp_full")
```

### 7.5 Vztah k `svp_vystupy` a ročníku žáka

`svp_vystupy.rocnik` definuje, pro jaký ročník je výstup určen. Žák v Nilssonu
je v jedné skupině (I./2025-2026) bez explicitního `rocnik` atributu — ročník se
odvozuje z `birth_date` a `enrollment_date`.

**Dopad na UI:** zobrazení Mapy pokroku per žák musí filtrovat výstupy podle
odvozeného ročníku, ne podle skupiny. Viz ARCH-NOTES sekce 14.5.

**Vilekula je smíšená škola** — žák může být hodnocen i na výstupech vyššího nebo
nižšího ročníku. UNIQUE constraint ani RLS toto neomezují; filtrování je záležitost
UI/aplikační logiky.

### 7.6 Migrace z vilekula-pokrok — shrnutí

| Fáze | Popis | Výsledek |
|---|---|---|
| Párování výstupů | `(rocnik, oblast→prefix, poradi)` → `(kod)` | 600/600, 0 sirotků, texty identické |
| Párování žáků | `(jmeno, prijmeni)` → `(first_name, last_name)` | 18/18, 0 sirotků |
| Normalizace | `'2025/26'` → `'2025/2026'`, `[]` → `NULL` | OK |
| Import | `import_mapa_pokroku.sql` — 1 077 INSERT | 0 duplicit |

Postup nasazení:
```
1. supabase db push  →  008_mapa_pokroku.sql
2. SQL editor        →  scripts/import_mapa_pokroku.sql
3. Ověřit:
   SELECT stupen, COUNT(*) FROM mapa_pokroku_hodnoceni
   GROUP BY stupen ORDER BY stupen;
   -- s_jistotou: 868, castecne: 145, s_dopomoci: 47, nezvlada: 17
```

### 7.7 Frontend — plánovaný rozsah

Modul `/app/mapa-pokroku/` (Next.js App Router) nahrazuje vilekula-pokrok SPA.
Vilekula-pokrok Supabase projekt lze po ověření migrace dekomisionovat.

Plánované stránky (OUT OF SCOPE pro go-live září 2026 — P2):

| Stránka | Popis |
|---|---|
| `/mapa-pokroku` | Přehled třídy — kdo má co zvládnuté |
| `/mapa-pokroku/[studentId]` | Detail žáka — výstupy per oblast/ročník |
| `/mapa-pokroku/[studentId]/edit` | Zadávání hodnocení průvodcem |

---

## Změny v sekci 9.1 — stávající skripty

Přidat řádek do tabulky:

| Skript | Modul | Funkce | Nahrazuje ho v IS | Stav |
|---|---|---|---|---|
| vilekula-pokrok (React SPA) | Mapa pokroku | Zadávání a zobrazení míry zvládnutí | `/app/mapa-pokroku/` — P2 | **Data migrována; SPA dočasně v provozu** |

---

## Změny v sekci 9.2 — import dat pro školní rok 2025/2026

Přidat řádky do tabulky:

| Soubor | Obsah | Cílová tabulka | Skript |
|---|---|---|---|
| `scripts/vystup_mapping.csv` | 600 párů pokrok UUID → nilsson UUID | — (auditní soubor) | — |
| `scripts/zak_mapping.csv` | 18 párů pokrok UUID → nilsson UUID | — (auditní soubor) | — |
| `scripts/import_mapa_pokroku.sql` | 1 077 hodnocení, 18 žáků, 1. pololetí 2025/2026 | `mapa_pokroku_hodnoceni` | spustit ručně v SQL editoru |

---

## Změny v sekci 10 — rozhodnuté otázky

Uzavřít otázku O4 a přidat nový řádek:

**O4** (Číselník výstupů ŠVP): **UZAVŘENO — IMPLEMENTOVÁNO.** `svp_vystupy` naplněna
(600 řádků, kódy JK-/M-/OVS-/PH-/UM-, ŠVP verze "Kořeny a křídla 1.0"). Párování
s vilekula-pokrok ověřeno (600/600, texty identické). Import dokončen.

Přidat nový řádek:

| # | Otázka | Rozhodnutí | Dopad na TRD |
|---|---|---|---|
| O11 | Integrace vilekula-pokrok (Mapa pokroku) do Nilssonu | Plná integrace: data migrována do `mapa_pokroku_hodnoceni`, frontend P2. vilekula-pokrok SPA dočasně v provozu. | Přidána sekce 7; aktualizovány 1.3, 9.1, 9.2 |
