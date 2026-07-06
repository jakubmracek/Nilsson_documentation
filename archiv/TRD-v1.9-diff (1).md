# TRD — diff pro aktualizaci na v1.9
#
# Instrukce: Aplikuj níže popsané změny na TRD-v1.8.md → TRD-v1.9.md
# Každá sekce je označena akcí: [NAHRADIT], [PŘIDAT ZA], [PŘIDAT DO]
#
# ─────────────────────────────────────────────────────────────────────────────


# ── [NAHRADIT] Záhlaví dokumentu ─────────────────────────────────────────────

**Verze:** 1.9
**Datum:** 2026-05-09
**Autoři:** Ing. Jakub Mráček + Claude Sonnet 4.6
**Navazuje na:** PRD v0.7, matrika TRD, matrika addendum 2026-04-27, třídní kniha addendum, VP addendum
**Status:** Fáze 3 dokončena — Docházka UI + Uzavření pololetí + BOZP modul nasazeny.

**Changelog v1.9:** Migrace 015_bozp_rls.sql nasazena — RLS politiky pro
`bozp_zaznamy` a `bozp_attendance`, DB funkce `get_students_without_bozp()`.
BOZP UI implementováno (sekce 5.8 aktualizována). Schéma souborů rozšířeno
o `app/dashboard/bozp/`. ARCH-NOTES rozšířeny o sekce 19 (school year rollover)
a 20 (BOZP implementační poznámky).


# ── [PŘIDAT ZA] Changelog v1.8 (tj. za řádek začínající "**Changelog v1.8:**") ──
# (Changelog v1.9 je uveden v záhlaví výše — není třeba duplikovat)


# ── [PŘIDAT DO] Sekce 1.3 — schéma souborů, do bloku migrations/ ────────────
#
# Za řádek:  └── 011_rls_multigroup.sql
# Přidat:

│       ├── 012_docházka_ui.sql           ← Fáze 3 — Docházka UI ✅ nasazeno
│       ├── 013_uzavreni_pololeti.sql      ← Fáze 3 — Uzavření pololetí ✅ nasazeno
│       ├── 014_school_year_rollover.sql   ← RPC new_school_year_rollover ✅ nasazeno
│       └── 015_bozp_rls.sql              ← BOZP RLS + get_students_without_bozp() ✅ nasazeno

#
# Za blok migrations/, do kořene projektu přidat BOZP UI soubory:
# (Do sekce app/dashboard/ — za tridni-kniha/)

│   │   └── bozp/
│   │       ├── page.tsx                  ← přehled záznamů + alert widget ✅
│   │       ├── novy/page.tsx             ← nový záznam (Server wrapper) ✅
│   │       ├── [id]/page.tsx             ← detail záznamu + attendance ✅
│   │       └── _components/
│   │           ├── NovyBozpForm.tsx      ← interaktivní checklist (Client) ✅
│   │           └── AddStudentToRecord.tsx ← přidání žáka (Client) ✅


# ── [NAHRADIT] Sekce 5.8 — Tabulky BOZP ─────────────────────────────────────

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

**Klíčový dotaz — žáci bez BOZP záznamu** (implementován jako RPC `get_students_without_bozp`
v migrace 015 — viz ARCH-NOTES sekce 20):

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

**RLS (migrace 015):** `bozp_zaznamy` SELECT pro všechny staff (není citlivé); INSERT pro
director/vp/guide. `bozp_attendance` INSERT s `can_read_student(bozp_attendance.student_id)`
pojistkou — guide nemůže přidat žáka mimo svoji skupinu. Viz ARCH-NOTES sekce 20.

**UI:** Implementováno v `app/dashboard/bozp/` — přehled se status widgetem "N žáků bez BOZP",
formulář nového záznamu s interaktivním checklistem, detail s evidencí proškolených žáků.


# ── [NAHRADIT] Sekce 9.2 — tabulka "Zbývající importy" ──────────────────────
#
# Řádky dochazka_souhrn.csv a dochazka_detail.csv aktualizuj dle skutečného stavu.
# Pokud jsou importy hotové, změň "čeká na Fázi 3" → "✅ importováno (datum)".
# Pokud stále čekají, ponech beze změny.


# ── [PŘIDAT DO] Sekce 9.2 — tabulka migrací (provedené importy) ─────────────
#
# Do tabulky "Provedené importy" přidat řádek:

| `015_bozp_rls.sql`  | `bozp_zaznamy`, `bozp_attendance` (RLS + RPC) | ✅ nasazeno (2026-05-09) |
