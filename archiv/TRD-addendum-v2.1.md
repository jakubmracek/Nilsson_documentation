# TRD — Addendum v2.1
# Aplikovat na TRD-v2.0.md:
# 1. Přidat changelog v2.1 na začátek (za řádek "Verze: 2.0")
# 2. Nahradit sekci 4.4 Omluvenky
# 3. Aktualizovat sekci 1.3 Schéma souborů
# Datum: 2026-05-13

---

## CHANGELOG — přidat za "Status:" na začátek dokumentu

Aktualizovat hlavičku:
```
Verze: 2.1
Datum: 2026-05-13
Status: Omluvenky + rodičovský portál nasazeny v produkci (migrace 018, 019).
```

Přidat changelog:
```
**Changelog v2.1 (2026-05-13):** Implementován komunikační modul Fáze 2 —
omluvenky a rodičovský portál. Migrace 018 (`absence_requests` tabulka, RLS pro staff)
a 019 (`guardians.user_id`, `entered_by_staff_id` nullable, guardian auth helpers,
rozšířené RLS pro `absence_requests` + `attendance_records`). Dashboard UI:
`/dashboard/omluvenky/` (seznam, nový, detail + ApprovalPanel). Rodičovský portál:
`/portal/` (login, omluvenky, docházka). Auth callback rozšířen o guardian auto-link.
`proxy.ts` opraven — export `proxy` (Next.js 16). Rozhodnutí: zprávy v IS ne,
email zůstává komunikačním kanálem. Dual-role (ředitel + rodič) = dva emaily.
Discord webhook notifikace TODO (Fáze 2b). Viz ARCH-NOTES v2.0 sekce 25–26.
```

---

## SEKCE 4.4 — Omluvenky (nahradit celou sekci)

### 4.4 Omluvenky (`absence_requests`)

**Status: Nasazeno v produkci (migrace 018 + 019, 2026-05-13)**

#### Schéma tabulky

```sql
CREATE TABLE absence_requests (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id                UUID NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  requested_by_guardian_id  UUID NOT NULL REFERENCES guardians(id),
  entered_by_staff_id       UUID REFERENCES staff(id),        -- NULL = rodič přes portál
  date_from                 DATE NOT NULL,
  date_to                   DATE NOT NULL,
  reason                    TEXT NOT NULL,
  status                    TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'approved', 'rejected')),
  reviewed_by               UUID REFERENCES staff(id),
  reviewed_at               TIMESTAMPTZ,
  note_internal             TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT check_dates              CHECK (date_to >= date_from),
  CONSTRAINT check_review_consistency CHECK (
    (reviewed_by IS NULL) = (reviewed_at IS NULL)
  ),
  CONSTRAINT check_reviewed_when_decided CHECK (
    status = 'pending' OR reviewed_by IS NOT NULL
  )
);
```

#### Workflow

```
Rodič (portál)          Průvodce (dashboard)
      │                        │
      ▼                        ▼
INSERT absence_request   INSERT absence_request
entered_by_staff = NULL  entered_by_staff = staff.id
      │                        │
      └──────────┬─────────────┘
                 ▼
        status = 'pending'
                 │
      Průvodce schválí / zamítne
                 │
         ┌───────┴────────┐
         ▼                ▼
    'approved'        'rejected'
         │            note_internal (nevidí rodič)
         ▼
  INSERT attendance_records
  pro každý pracovní den
  status = 'absent_excused'
  hodiny = 4 (čtvrtek = 6)
  absence_request_id = FK
```

#### Průpis do attendance_records

Po schválení Server Action `approveOmluvenka()` vygeneruje záznamy docházky:
- Iteruje přes pracovní dny (Po–Pá) v rozsahu `date_from`..`date_to`
- Čtvrtek (terénní program) = 6 hodin, ostatní dny = 4 hodiny
- `status = 'absent_excused'`
- `absence_request_id` = FK na omluvenku

**Poznámka:** `attendance_records` nemá UNIQUE na `(student_id, date)` — duplicity možné,
průvodce řeší ručně. Budoucí rozšíření: ON CONFLICT DO UPDATE.

#### RLS — 6 politik

Viz ARCH-NOTES v2.0 sekce 25.4.

#### Server Actions

| Akce | Soubor | Popis |
|------|--------|-------|
| `createOmluvenka` | `app/actions/omluvenky.ts` | Průvodce zadává za rodiče |
| `approveOmluvenka` | `app/actions/omluvenky.ts` | Schválení + průpis do attendance |
| `rejectOmluvenka` | `app/actions/omluvenky.ts` | Zamítnutí + interní poznámka |
| `createGuardianOmluvenka` | `app/actions/portal-omluvenky.ts` | Rodič zadává přímo |

---

## SEKCE 1.3 Schéma souborů — přidat do app/

```
app/
├── actions/
│   ├── omluvenky.ts             ← staff Server Actions (create, approve, reject)
│   └── portal-omluvenky.ts     ← guardian Server Actions (create)
├── auth/
│   ├── callback/route.ts        ← PKCE callback; staff + guardian auto-link
│   └── signout/route.ts         ← POST; redirect dle referer (portal/dashboard)
├── dashboard/
│   └── omluvenky/
│       ├── page.tsx             ← seznam omluvenek
│       ├── novy/
│       │   ├── page.tsx
│       │   └── _components/NovaOmluvenkaForm.tsx
│       └── [id]/
│           ├── page.tsx
│           └── _components/ApprovalPanel.tsx
└── portal/
    ├── layout.tsx               ← guardian shell; ověřuje is_guardian()
    ├── login/page.tsx           ← magic link pro rodiče
    ├── omluvenky/
    │   ├── page.tsx
    │   └── novy/
    │       ├── page.tsx
    │       └── _components/GuardianOmluvenkaForm.tsx
    └── dochazka/
        └── page.tsx             ← read-only; posledních 60 dní
```

Migrace:
```
supabase/migrations/
├── 018_omluvenky.sql            ← absence_requests + FK do attendance_records + staff RLS
└── 019_guardian_auth.sql        ← guardians.user_id, nullable entered_by_staff_id,
                                    guardian helpers, rozšířené RLS
```
