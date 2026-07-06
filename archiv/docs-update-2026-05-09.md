# Aktualizace dokumentace — konec session 2026-05-09
# Aplikuj na ARCH-NOTES v1.8 a TRD v1.9
# ─────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# ARCH-NOTES — doplnění sekce 20 (BOZP implementační poznámky)
# Přidej na konec sekce 20, za odstavec "Server Actions — návratový vzor"
# ══════════════════════════════════════════════════════════════════════════════

### `group_memberships.valid_to` — produkční zjištění

`valid_to` v tabulce `group_memberships` **není NULL pro aktivní záznamy**.
Vilekula používá konvenci: `valid_to = poslední den školního roku` (např. `2026-08-31`)
i pro aktuálně platné záznamy. NULL by znamenalo "bez stanoveného konce".

**Důsledek pro všechny dotazy filtrující "aktuální žáci školního roku":**

```sql
-- ŠPATNĚ — vrátí 0 řádků (valid_to nikdy není NULL):
WHERE gm.school_year = '2025/2026'
  AND gm.valid_to IS NULL

-- SPRÁVNĚ — filtrovat pouze přes school_year:
WHERE gm.school_year = '2025/2026'
```

Funkce `get_students_in_school_year` a `get_students_without_bozp` byly opraveny
při nasazení (SQL Editor, 2026-05-09) — migrace 017 na disku tento fix ještě
neobsahuje, **oprav lokálně před příštím `db push`** (viz TRD sekce níže).

**Obecné pravidlo:** Při filtrování žáků per školní rok vždy použij pouze
`gm.school_year = p_school_year` bez dalšího filtru na `valid_to`.


### Dashboard — počet žáků

`StudentsOverviewWidget` počítá žáky přes RPC `get_students_in_school_year`,
ne přes `students WHERE status='active'`. Důvod: `status='active'` vrací žáky
ze všech školních roků (32 místo 20 pro 2025/2026).


# ══════════════════════════════════════════════════════════════════════════════
# TRD v1.9 — doplnění (přidej do changelogu v záhlaví jako "Produkční opravy")
# ══════════════════════════════════════════════════════════════════════════════

**Produkční opravy 2026-05-09:**
- Migrace 015: RLS politika `staff_bozp_attendance_insert` opravena —
  `can_read_student(bozp_attendance.student_id)` místo `can_read_student(student_id)`
  (syntax error při použití bez kvalifikace tabulky ve WITH CHECK).
- Migrace 017: `get_students_in_school_year` a `get_students_without_bozp`
  opraveny — odstraněn filtr `AND gm.valid_to IS NULL` (v produkci je
  `valid_to = 2026-08-31`, ne NULL). **Lokální soubor 017 je třeba opravit.**
- `app/dashboard/page.tsx`: `studentCount` počítán přes
  `get_students_in_school_year` RPC místo `students WHERE status='active'`.
- `app/dashboard/bozp/novy/page.tsx` a `[id]/page.tsx`: výběr žáků přes
  `get_students_in_school_year` RPC místo přímého dotazu na `students`.


# ══════════════════════════════════════════════════════════════════════════════
# TRD — oprava migrace 017 lokálně (před příštím db push)
# V souboru supabase/migrations/017_fix_school_year_filter.sql
# odstraň řádek "AND gm.valid_to IS NULL" na třech místech:
# ══════════════════════════════════════════════════════════════════════════════

# 1. Ve funkci get_students_in_school_year:
#    SMAZAT:  AND gm.valid_to IS NULL

# 2. Ve funkci get_students_without_bozp:
#    SMAZAT:  AND gm.valid_to IS NULL

# 3. Ve funkci generate_bozp_alerts:
#    SMAZAT:  AND gm.valid_to IS NULL

# PS příkaz pro opravu:
# (Get-Content -LiteralPath "supabase/migrations/017_fix_school_year_filter.sql") |
#   Where-Object { $_ -notmatch 'valid_to IS NULL' } |
#   Set-Content -LiteralPath "supabase/migrations/017_fix_school_year_filter.sql"
