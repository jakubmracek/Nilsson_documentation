# TRD — Addendum 2026-06-05

Navazuje na TRD addendum 2026-06-02b.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-06-05

- **Modul Tripartita:** rezervační systém tripartitních schůzek integrován
  do Nilssonu. Migrace 028, dashboard správa, portálová rezervační stránka,
  potvrzovací email přes Resend. Viz sekce 14 níže + ARCH-NOTES sekce 53.

---

## Nová sekce 14 — Modul Tripartita

### 14.1 Přehled

Rezervační systém tripartitních schůzek. Nahrazuje původní samostatnou
aplikaci (Railway + vlastní Supabase). Integrace přináší ověřenou identitu
guardiana, přímou vazbu na žáky a konsolidaci stacku.

**Status: Nasazeno v produkci (2026-06-05)**

### 14.2 Schéma tabulek (migrace 028)

```sql
CREATE TABLE tripartita_events (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  description TEXT,
  school_year TEXT        NOT NULL,
  active      BOOLEAN     NOT NULL DEFAULT TRUE,
  created_by  UUID        NOT NULL REFERENCES staff(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tripartita_slots (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id       UUID        NOT NULL REFERENCES tripartita_events(id) ON DELETE CASCADE,
  label          TEXT        NOT NULL,
  starts_at      TIMESTAMPTZ,
  ends_at        TIMESTAMPTZ,
  capacity       INTEGER     NOT NULL DEFAULT 1 CHECK (capacity >= 1),
  reserved_count INTEGER     NOT NULL DEFAULT 0 CHECK (reserved_count >= 0),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT check_slot_times CHECK (
    ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at
  ),
  CONSTRAINT check_reserved_not_over_capacity CHECK (
    reserved_count <= capacity
  )
);

CREATE TABLE tripartita_reservations (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  slot_id     UUID        NOT NULL REFERENCES tripartita_slots(id) ON DELETE RESTRICT,
  event_id    UUID        NOT NULL REFERENCES tripartita_events(id) ON DELETE RESTRICT,
  guardian_id UUID        NOT NULL REFERENCES guardians(id),
  student_id  UUID        NOT NULL REFERENCES students(id),
  note        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (slot_id, student_id),
  UNIQUE (event_id, student_id)
);
```

### 14.3 RPC `reserve_tripartita_slot`

Atomická rezervace s kontrolou kapacity a souběžnosti.

```
Vstup:  p_slot_id UUID, p_student_id UUID, p_note TEXT
Výstup: TEXT — 'ok' | 'slot_full' | 'already_reserved' | 'not_your_child' | 'event_not_active'
```

Volá se výhradně z `app/actions/portal-tripartita.ts` přes `supabase.rpc()`.
Viz ARCH-NOTES sekce 53.3 pro detaily implementace.

### 14.4 Přístupová práva

| Role | Dashboard | Portál |
|------|-----------|--------|
| director | Plná správa (CRUD události, sloty, přehled rezervací) | — |
| vp / guide | Pasivní pohled (read-only seznam + detail) | — |
| guardian | — | Rezervační stránka aktivní události |

### 14.5 Workflow — director

1. Vytvoří událost (`/dashboard/tripartita/nova`)
2. V detailu přejde na Upravit → přidá termíny (label, čas, kapacita)
3. Událost je automaticky aktivní → rodiče vidí v portálu
4. Po skončení tripartit: přepne `active = false` → zmizí z portálu

Termín lze smazat pouze pokud `reserved_count = 0`. Editace kapacity termínu
dolů je omezena na aktuální `reserved_count` (UI i Server Action).

### 14.6 Workflow — guardian (portál)

1. Přihlásí se do portálu → záložka Tripartity
2. Vidí název a popis aktivní události + dostupné termíny
3. Pokud má více dětí: vybere dítě (děti s rezervací jsou disabled)
4. Vybere volný termín → volitelná poznámka → Rezervovat
5. Potvrzovací obrazovka + email na guardian.email

Každé dítě může mít v rámci jedné události pouze jednu rezervaci
(`UNIQUE (event_id, student_id)`).

### 14.7 Potvrzovací email

Provider: Resend (`noreply@zsvilekula.cz`).
Obsah: název události, termín (label), jméno dítěte, poznámka (pokud vyplněna).
Best-effort: chyba emailu nezruší rezervaci.

### 14.8 Navigace

| Místo | Položka |
|-------|---------|
| Dashboard sidebar | Tripartity (director, vp, guide) |
| Portál desktop topbar | Tripartity |
| Portál mobile bottom nav | Tripartity (6. položka) |

### 14.9 Omezení v1 / budoucí rozvoj

| Položka | Stav | Poznámka |
|---------|------|----------|
| Max. 1 aktivní událost naráz | Konvence, ne DB constraint | Director zodpovídá; budoucí: UI varování |
| Zrušení rezervace | Není | Director řeší přímo v DB |
| ICS příloha v emailu | Není | Budoucí rozšíření (`starts_at`/`ends_at` jsou v DB) |
| Realtime aktualizace obsazenosti | Není | Portál je SSR; budoucí: Supabase Realtime na `tripartita_slots` |
| Export rezervací (CSV) | Není | Budoucí; vzor z původního rezervačního systému |

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
└── 028_tripartita.sql
```

Do `app/` přidat/upravit:

```
actions/
├── tripartita.ts               ← createEvent, updateEvent, createSlot, updateSlot, deleteSlot
└── portal-tripartita.ts        ← reserveSlot

dashboard/tripartita/
├── page.tsx
├── nova/page.tsx
└── [id]/
    ├── page.tsx
    └── upravit/
        ├── page.tsx
        └── _components/EditEventForm.tsx

portal/
├── layout.tsx                  ← přidán PortalNavLink Tripartity
├── tripartita/
│   ├── page.tsx
│   └── _components/TripartitaReservationForm.tsx
└── _components/
    └── PortalBottomNav.tsx     ← přidána 6. položka Tripartity

components/nav/AppNav.tsx       ← ikona calendar + položka Tripartity
```

---

## Aktualizace sekce 10.2 — import dat

| Akce | Obsah | Stav |
|------|-------|------|
| 028_tripartita.sql | Schema + RLS + RPC; sanity check 10 politik + prosecdef=true | ✅ 2026-06-05 |
