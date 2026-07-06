# TRD — Addendum 2026-05-20

Navazuje na TRD v2.1 + addenda 2026-05-19
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-05-20

- **Staff import:** 7 nových staff záznamů importováno, Auth účty propojeny.
  Viz ARCH-NOTES sekce 37.
- **`hodnotil_id` backfill:** 1 077 záznamů `mapa_pokroku_hodnoceni` přiřazeno
  správným průvodkyním dle ročníku + předmětu. Viz ARCH-NOTES sekce 38.
- **Platební modul — PRD + TRD:** Nová sekce 4.7 níže.
  Viz ARCH-NOTES sekce 39 pro architektonická rozhodnutí.

---

## Aktualizace sekce 10.2 — import dat

Přidat řádky do tabulky provedených importů:

| Soubor / akce | Obsah | Stav |
|---|---|---|
| DO blok staff import | 7 nových staff záznamů; Auth `user_id` propojeny | ✅ 2026-05-20 |
| DO blok hodnotil_id backfill | 1 077 záznamů; Studničková 509, Pelcová 417, Mráčková 151 | ✅ 2026-05-20 |

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat (pending):

```
├── 022_payments_ui.sql     ← ALTER payment_obligations + payment_transactions (ss_kod, popis, notified_at, specific_symbol)
└── 023_rls_payments.sql    ← RLS pro payment_obligations, payment_transactions, payment_matches
```

Do `lib/` přidat:

```
├── payments.ts             ← Server-only: Supabase dotazy a typy platebního modulu
└── paylibo.ts              ← Shared: payliboUrl() pure funkce (importovatelná z Client i Server)
```

Do `app/dashboard/` přidat:

```
└── platby/
    ├── page.tsx                          ← přehled: nesplacené, nespárované, přeplatky
    ├── pohledavky/
    │   ├── page.tsx                      ← seznam, filtr typ/stav/měsíc
    │   ├── nova/
    │   │   ├── page.tsx
    │   │   └── _components/
    │   │       └── NovaPohledavkaForm.tsx
    │   └── [id]/
    │       ├── page.tsx
    │       └── _components/
    │           └── NotifyButton.tsx
    └── transakce/
        ├── page.tsx
        └── [id]/
            ├── page.tsx
            └── _components/
                └── ManualMatchForm.tsx
```

Do `app/portal/` přidat:

```
└── platby/
    └── page.tsx             ← seznam pohledávek vlastních dětí + QR kód
```

Do `app/actions/` přidat:

```
└── payments.ts              ← createObligations, sendNotifications, manualMatch
```

---

## Nová sekce 4.7 — Platební modul UI

### 4.7.1 Přehled

Cíl: nahradit stávající Gmail mail merge + ruční QR kódy integrovaným modulem.
Ředitel zadá pohledávky v IS, rodiče obdrží email s QR kódem a vidí pohledávky
v rodičovském portálu. Platby se importují z Fio API a párují přes VS + SS.

**Status: Pending — migrace 022 + 023, viz checklist níže.**

### 4.7.2 Typy pohledávek

| Typ | Prefix SS | Periodicita |
|-----|-----------|-------------|
| Obědy | `10` | Měsíčně — částka se liší každý měsíc |
| Výjezdní akce | `20` | Ad hoc — základní cena + individuální úpravy |

Z pohledu IS jsou oba typy stejná entita — liší se prefixem SS a popiskem.

### 4.7.3 Změny v DB schématu (migrace 022)

```sql
-- payment_obligations: nové sloupce
ALTER TABLE payment_obligations
  ADD COLUMN ss_kod      TEXT UNIQUE,    -- specifický symbol (10 číslic)
  ADD COLUMN popis       TEXT,           -- „Obědy leden 2027", „Výjezd Krkonoše"
  ADD COLUMN notified_at TIMESTAMPTZ;   -- kdy byl odeslán email ZZ

-- payment_transactions: specifický symbol z Fio
ALTER TABLE payment_transactions
  ADD COLUMN specific_symbol TEXT;

-- Indexy pro párování
CREATE INDEX ON payment_obligations (ss_kod);
CREATE INDEX ON payment_transactions (specific_symbol);
```

### 4.7.4 Specifický symbol (SS)

Formát: `PREFIX(2) + YYYY(4) + MM(2) + RANK(2)` = 10 číslic

Příklady:
- `1020270100` — obědy, leden 2027, 1. pohledávka
- `2020270103` — akce, leden 2027, 3. pohledávka

RANK generován v Server Action (MAX stávajících + 1 per typ per měsíc).
Viz ARCH-NOTES sekce 39.1.

### 4.7.5 Workflow zadání pohledávek

**Obědy:**
1. Formulář: typ = Obědy, měsíc, popis
2. Tabulka aktivních žáků s polem pro částku (každý žák může mít jinou)
3. Potvrdit → vygenerovat pohledávky + SS per žák
4. Zkontrolovat → „Odeslat notifikace"
5. Resend email všem ZZ (`je_zakonny_zastupce = TRUE`) + pohledávka v portálu

**Výjezdní akce:**
1. Formulář: typ = Akce, název, popis, splatnost, **základní cena**
2. Tabulka žáků předvyplněná základní cenou — individuální úpravy dle potřeby
3. Dále stejně jako obědy (krok 3–5)

**Notifikace se odesílají až po explicitním potvrzení** — ne automaticky.

### 4.7.6 QR kód

Generován přes Paylibo API jako `<img>` tag. Viz ARCH-NOTES sekce 39.2.

Env proměnné:
```
BANK_ACCOUNT_NUMBER=2303305396
BANK_CODE=2010
```

### 4.7.7 Párování plateb

**Automatické** (rozšíření stávajícího Fio cronu):

```
specific_symbol → payment_obligations.ss_kod  (přesná shoda)
variable_symbol (padStart 4) → students.kod_zaka suffix
```

Obě podmínky musí sedět → INSERT `payment_matches` + `match_status = 'matched'`.
Nesoulad → `match_status = 'unmatched'` + `system_alert` (stávající chování).

**Ruční:**
- Dashboard zobrazí `unmatched` transakce
- Ředitel vybere žáka + pohledávku → `match_status = 'manual_override'` + resolve alert

**Stav pohledávky** (odvozený v aplikační vrstvě):

| Podmínka | Stav |
|----------|------|
| `SUM(matched_amount) = 0` | `pending` |
| `0 < SUM < amount` | `partial` |
| `SUM >= amount` | `paid` |

### 4.7.8 Rodičovský portál — záložka Platby

`/portal/platby/` — pro přihlášeného ZZ:
- Seznam pohledávek všech jeho dětí
- Stav per pohledávka (pending / partial / paid)
- QR kód pro každou nesplacenou pohledávku (kdykoliv znovu)
- Historie uhrazených plateb

RLS: guardian vidí pouze pohledávky vlastních dětí
(přes `student_guardian_links WHERE je_zakonny_zastupce = TRUE`).

### 4.7.9 Server Actions (`app/actions/payments.ts`)

| Akce | Kdo | Popis |
|------|-----|-------|
| `createObligations` | director | Generuje pohledávky pro seznam žáků; počítá SS kód |
| `sendNotifications` | director | Resend email ZZ; UPDATE `notified_at` |
| `manualMatch` | director | Ruční párování transakce ↔ pohledávka |

### 4.7.10 Přístupová práva

| Oblast | director | ostatní staff | guardian |
|--------|----------|---------------|---------|
| Dashboard platby | R/W | — | — |
| Pohledávky (správa) | R/W | — | — |
| Transakce | R/W | — | — |
| Portál — vlastní pohledávky | — | — | R |

### 4.7.11 Navigace

```typescript
// AppNav.tsx — dashboard
{ href: '/dashboard/platby', label: 'Platby',
  roles: ['director'], bottomNav: false }

// Portal nav
{ href: '/portal/platby', label: 'Platby' }
```

### 4.7.12 Otevřené TODO

| Položka | Poznámka |
|---------|----------|
| Ověřit název sloupce SS v Fio JSON response | `column6`? Ověřit v live datech |
| RLS migrace 023 | `payment_obligations`, `payment_transactions`, `payment_matches` |
| Storno pohledávky | Řeší ředitel přímo v DB, UI není třeba |
| Portál — zobrazit i uhrazené pohledávky | Historie plateb |
