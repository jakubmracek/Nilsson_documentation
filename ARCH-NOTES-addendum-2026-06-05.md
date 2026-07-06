# ARCH-NOTES — Addendum 2026-06-05

Navazuje na ARCH-NOTES addendum 2026-06-02b.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 53. Modul Tripartita — architektonická rozhodnutí (2026-06-05)

### 53.1 Kontext a motivace

Rezervační systém tripartitních schůzek byl původně provozován jako samostatná
Next.js aplikace na Railway + vlastním Supabase projektu. Integrován do Nilssonu
z důvodu: rodiče jsou ověření přes guardian portál, žáci/ZZ jsou v DB, není třeba
druhý projekt ani druhá sada env proměnných.

Zvolena jednodušší varianta s pevným schématem (bez dynamických `event_fields`)
— pro tripartity stačí pevný formulář s volitelnou poznámkou.

### 53.2 Datový model — 3 tabulky (migrace 028)

```
tripartita_events        ← událost (název, popis, školní rok, active)
tripartita_slots         ← termíny s kapacitou a reserved_count
tripartita_reservations  ← rezervace (guardian + student + slot + poznámka)
```

**Klíčové constraints:**
- `UNIQUE (slot_id, student_id)` — jeden student na jeden termín
- `UNIQUE (event_id, student_id)` — jeden student na jednu událost celkem
- `CHECK (reserved_count <= capacity)` — DB pojistka přetečení kapacity
- `CHECK (ends_at > starts_at)` — validace časů slotu

**`reserved_count`** je denormalizovaný čítač na `tripartita_slots` — inkrementuje
se v RPC funkci atomicky. Důvod: výkon (žádný COUNT při každém zobrazení),
konzistence (FOR UPDATE zamkne řádek při souběžných rezervacích).

### 53.3 Atomická rezervace — RPC `reserve_tripartita_slot`

SECURITY DEFINER funkce — obchází RLS pro UPDATE `reserved_count` a INSERT
do `tripartita_reservations`. Ověřuje identitu guardiana přes `auth.uid()`.

```sql
reserve_tripartita_slot(p_slot_id UUID, p_student_id UUID, p_note TEXT)
RETURNS TEXT  -- 'ok' | 'slot_full' | 'already_reserved' | 'not_your_child' | 'event_not_active'
```

**Souběžnost:** `SELECT ... FOR UPDATE` na slotu zamkne řádek po dobu transakce.
Dva rodiče klikající ve stejnou chvíli → deterministický výsledek (jeden `ok`,
druhý `slot_full`).

**Proč RPC a ne přímý INSERT z aplikační vrstvy:**
- UPDATE `reserved_count` + INSERT `tripartita_reservations` musí být atomické
- RLS politika na `tripartita_slots` by blokovala UPDATE přes server klienta
- SECURITY DEFINER je správný vzor pro operace vyžadující elevated přístup
  s vlastní validační logikou

### 53.4 RLS strategie

| Role | tripartita_events | tripartita_slots | tripartita_reservations |
|------|-------------------|------------------|-------------------------|
| director | ALL | ALL | ALL |
| vp/guide/assistant/readonly | SELECT | SELECT | SELECT |
| guardian | SELECT (active=TRUE) | SELECT (active event) | SELECT vlastní + INSERT přes pojistku |

**Guardian INSERT politika** (`tr_guardian_insert`) je pojistka pro případ přímého
`.from().insert()` — fakticky se INSERT provádí výhradně přes RPC (SECURITY DEFINER),
takže politika se nevyhodnocuje. Ponechána pro explicitnost a budoucí bezpečnost.

### 53.5 Správa vs. pasivní pohled

| Role | Co vidí |
|------|---------|
| director | Plná správa: create/edit/delete událostí a slotů, přehled všech rezervací |
| vp/guide | Pasivní pohled: seznam událostí, detail se sloty a rezervacemi (read-only) |
| guardian | Portálová rezervační stránka (jen aktivní událost) |

Přesměrování `app/dashboard/tripartita/[id]/upravit/page.tsx` — pokud přistoupí
non-director, Server Component přesměruje na detail (ne 403).

### 53.6 Frontend architektura — dashboard

```
app/dashboard/tripartita/
├── page.tsx                          ← Server Component; seznam událostí
├── nova/
│   └── page.tsx                      ← Client Component; formulář nové události
└── [id]/
    ├── page.tsx                      ← Server Component; detail + sloty + rezervace
    └── upravit/
        ├── page.tsx                  ← Server Component wrapper; guard director
        └── _components/
            └── EditEventForm.tsx     ← Client Component; editace + správa slotů
```

**EditEventForm** — inline editace slotů (bez modálů). Editovaný slot se rozbalí
do formuláře přímo v seznamu. `router.refresh()` po mutaci slotu znovu načte
Server Component wrapper a aktualizuje seznam.

**Mazání slotu:** zakázáno pokud `reserved_count > 0` — tlačítko disabled +
vizuální hint. Dvojitá pojistka: UI + Server Action.

### 53.7 Frontend architektura — portál

```
app/portal/tripartita/
└── page.tsx                          ← Server Component; načte data, předá do formu
    └── _components/
        └── TripartitaReservationForm.tsx ← Client Component; interaktivní rezervace
```

**Tři stavy formuláře:**
1. Normální — výběr dítěte (skryto při 1 dítěti) + výběr termínu + poznámka
2. Vše rezervováno — přehled existujících rezervací místo formuláře
3. Potvrzení — po úspěšné rezervaci, info o potvrzovacím emailu

**Rodič s více dětmi:** každé dítě má vlastní rezervaci (UNIQUE event+student).
Děti s existující rezervací jsou v selectu disabled s označením „✓ Rezervováno".

**Žádná aktivní událost:** stránka zobrazí prázdný stav místo formuláře —
žádná chyba, jen informace.

### 53.8 Potvrzovací email

Odesílá se přes Resend po úspěšné RPC rezervaci. Best-effort — chyba emailu
nezruší rezervaci (try/catch bez rethrow).

```
from: ZŠ Vilekula <noreply@zsvilekula.cz>
subject: Potvrzení rezervace — {eventName}
obsah: událost, termín, dítě, poznámka (pokud vyplněna)
```

Data pro email se načtou samostatným dotazem po RPC — RPC vrací jen `'ok'`,
ne data záznamu.

### 53.9 Navigace

**Dashboard:** `AppNav.tsx` — přidána ikona `calendar` do `Icons` objektu +
položka `Tripartity` pro role `director`, `vp`, `guide`, `bottomNav: false`.

**Portál desktop:** `portal/layout.tsx` — `<PortalNavLink href="/portal/tripartita">`.

**Portál mobile:** `PortalBottomNav.tsx` — 6. položka s kalendářovou ikonou.

### 53.10 `(supabase as any)` — nové tabulky

Tabulky `tripartita_events`, `tripartita_slots`, `tripartita_reservations` vznikly
migrací 028 — po poslední regeneraci `types/database.ts`. Všechny dotazy na tyto
tabulky používají `(supabase as any).from(...)`.

**TODO:** Regenerovat typy: `npx supabase gen types typescript --project-id <id> > types/database.ts`

### 53.11 Pouze jedna aktivní událost naráz

Portálová stránka načítá vždy jen první aktivní událost (`active = true`,
`ORDER BY created_at DESC`, `LIMIT 1`). DB constraint na jedinečnost aktivní
události není — director zodpovídá za to, že aktivní je vždy max. jedna.

Budoucí vylepšení: trigger nebo CHECK constraint pro max. 1 aktivní událost,
nebo UI varování při aktivaci druhé.

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
└── 028_tripartita.sql    ← tripartita_events, tripartita_slots, tripartita_reservations,
                             RLS, RPC reserve_tripartita_slot
```

Do `app/dashboard/` přidat:

```
└── tripartita/
    ├── page.tsx
    ├── nova/page.tsx
    └── [id]/
        ├── page.tsx
        └── upravit/
            ├── page.tsx
            └── _components/EditEventForm.tsx
```

Do `app/portal/` přidat:

```
└── tripartita/
    ├── page.tsx
    └── _components/TripartitaReservationForm.tsx
```

Do `app/actions/` přidat:

```
├── tripartita.ts           ← createEvent, updateEvent, createSlot, updateSlot, deleteSlot
└── portal-tripartita.ts    ← reserveSlot (RPC + Resend email)
```

Upravit:

```
components/nav/AppNav.tsx              ← přidána ikona calendar + položka Tripartity
app/portal/layout.tsx                  ← přidán PortalNavLink Tripartity
app/portal/_components/
  PortalBottomNav.tsx                  ← přidána 6. položka Tripartity
```
