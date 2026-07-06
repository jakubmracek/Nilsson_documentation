# TRD Addendum — Platební modul
**Datum:** 2026-05-21
**Navazuje na:** TRD_20260515_v2_1.md sekce 4.3 + 4.6, PRD/TRD platební modul 2026-05-20

---

## 1. Migrace

### 022_payments_ui.sql
- `payment_obligations` +3 sloupce: `ss_kod TEXT UNIQUE`, `popis TEXT`, `notified_at TIMESTAMPTZ`
- `payment_transactions` +1 sloupec: `specific_symbol TEXT`
- Partial indexy: `idx_payment_obligations_ss_kod`, `idx_payment_transactions_specific_symbol`
  (WHERE IS NOT NULL — kompaktnější, párování probíhá jen nad řádky se SS)

### 023_rls_payments.sql
- RLS + FORCE RLS na `payment_obligations`, `payment_transactions`, `payment_matches`
- director: ALL přes `is_director()` helper
- guardian: SELECT vlastních pohledávek přes `student_guardian_links → guardians`
- `payment_transactions`: guardian nemá přístup ([[Rodičovský portál]] zobrazuje jen pohledávky + odvozený stav)

### 023b_rls_payments_cleanup.sql
- Odstraněny pozůstatky ze scaffoldingu: `po_vp_insert`, `po_vp_readonly_select`,
  `pt_vp_readonly_select`, `pm_vp_insert`, `pm_vp_readonly_select`
- [[Výchovný poradce (VP)]] nemá přístup k platebnímu modulu (dle PRD sekce 6)
- `readonly` odstraněn z `NAV_ITEMS` pro `/[[Přehled]]/[[Platby]]` v `AppNav.tsx`

---

## 2. Env proměnné (nové)

| Proměnná | Kde | Poznámka |
|---|---|---|
| `NEXT_PUBLIC_BANK_ACCOUNT_NUMBER` | `.env.local` + Vercel (všechna prostředí) | `NEXT_PUBLIC_` prefix — potřeba v Client Componentu ([[Rodičovský portál]]) |
| `NEXT_PUBLIC_BANK_CODE` | `.env.local` + Vercel (všechna prostředí) | `2010` |
| `NEXT_PUBLIC_APP_URL` | `.env.local` + Vercel | Odkaz na [[Rodičovský portál]] v emailu |

Rozhodnutí: `BANK_ACCOUNT_NUMBER` a `BANK_CODE` jsou `NEXT_PUBLIC_` (ne server-only),
protože `lib/paylibo.ts` je shared helper volaný i z Client Componentů.
Číslo účtu není tajemství — je viditelné na každém QR kódu a faktuře.

---

## 3. lib/paylibo.ts (nový)

```typescript
// Shared — importovatelný z Client i Server
export function payliboUrl(params: PayliboParams): string
```

- Sestavuje URL pro Paylibo QR API
- Pure funkce, žádné server-only importy
- VS = číslo z `kod_zaka` (suffix za posledním `-`)
- Používá `URLSearchParams` pro správné escapování `message`

---

## 4. lib/fio.ts (rozšíření)

- `FioTransaction` interface: +`specificSymbol: string | null`
- `FioApiTransaction` interface: +`column6: { value: string } | null`
- Mapping: `specificSymbol: t.column6?.value ?? null`
- TODO: ověřit `column6` na reálné transakci se SS — dle Fio API docs
  je to nejpravděpodobnější kandidát, ale neověřeno na live datech

---

## 5. app/api/cron/fio-import/route.ts (rozšíření)

Změny oproti původní verzi:

- `specific_symbol` uložen do `payment_transactions`
- Logika `matchStatus`: VS samo **nestačí** — `matched` pouze pokud sedí SS+VS obě
- VS bez SS: nastaví `student_id` na transakci (orientace v dashboardu),
  ale `match_status = 'unmatched'` + system_alert
- Po úspěšném SS+VS párování: INSERT `payment_matches` + `match_status = 'matched'`
- Degradace: pokud INSERT do `payment_matches` selže → UPDATE transakce zpět
  na `unmatched` + system_alert (žádná tichá ztráta)
- Alert message rozšířen o SS

---

## 6. app/actions/payments.ts (nový)

Tři Server Actions, všechny s `is_director()` guard:

### createObligations
- Generuje pohledávky pro seznam [[Žáci]]
- SS kód: **jeden sdílený** pro celou skupinu (obědy/akce v daném měsíci)
- RANK: `MAX + 1` per prefix+YYYYMM query (ne DB sekvence — reset při novém měsíci
  by byl složitý)
- Bulk INSERT přes Supabase `.insert(rows)`

### sendNotifications
- Příjemci: ZZ kde `je_zakonny_zastupce = TRUE` (filtr pro emaily, ne pro RLS)
- `notified_at` se uloží i při částečném úspěchu — `sent` count v response
  říká kolik emailů skutečně odešlo
- QR kód inline v HTML emailu jako `<img src="{payliboUrl}">`

### manualMatch
- INSERT `payment_matches` + UPDATE `match_status = 'manual_override'`
- Resolve `system_alert` pro danou transakci (nekritická chyba — match proběhl)
- `revalidatePath` na transakci + seznam transakcí

---

## 7. Stav pohledávky — odvození

Stav se **nepočítá v DB** (žádný computed column ani view).
Počítá se v aplikační vrstvě z `SUM(payment_matches.matched_amount)`:

| Stav | Podmínka |
|---|---|
| `pending` | `matched_total <= 0` |
| `partial` | `0 < matched_total < amount` |
| `paid` | `matched_total >= amount` |

Důvod: tabulka je malá (32 [[Žáci]]), agregace v JS je rychlejší než extra RPC.
Přehodnotit při růstu školy nebo přidání DB view.

---

## 8. UI — nové soubory

```
app/[[Přehled]]/[[Platby]]/
├── page.tsx                                    ← [[Přehled]] (Server Component)
├── pohledavky/
│   ├── page.tsx                                ← seznam + filtry URL search params
│   ├── nova/
│   │   ├── page.tsx                            ← Server wrapper
│   │   └── _components/NovaPohledavkaForm.tsx  ← Client
│   └── [id]/
│       ├── page.tsx                            ← detail + QR
│       └── _components/NotifyButton.tsx        ← Client, stavový automat
└── transakce/
    ├── page.tsx                                ← seznam + filtr match_status
    └── [id]/
        ├── page.tsx                            ← detail
        └── _components/ManualMatchForm.tsx     ← Client, inline vyhledávání

app/portal/[[Platby]]/
└── page.tsx                                    ← Server Component, QR per položka
```

### Architektonické vzory použité v UI

- **Filtry jako URL search params** — žádný client state, Server Components,
  URL sdílitelná a zachová se po refreshi
- **`<details>` pro historii** — splacené pohledávky v [[Rodičovský portál]] skryty za nativním
  HTML elementem, žádný JS state
- **`useTransition` + stavový automat** — `NotifyButton` a `ManualMatchForm`
  používají `startTransition` pro non-blocking pending state

---

## 9. Navigace

- `AppNav.tsx`: položka `[[Platby]]` existovala ze scaffoldingu,
  opravena role: `['director']` (odstraněn `readonly`)
- `app/portal/layout.tsx`: přidán `<PortalNavLink href="/portal/[[Platby]]">[[Platby]]</PortalNavLink>`

---

## 10. Otevřené TODO

| Položka | Priorita | Poznámka |
|---|---|---|
| Ověřit `column6` = SS v Fio JSON | Vysoká | Nutné před ostrým provozem |
| Storno pohledávky | Nízká | Řeší ředitel přímo v DB |
| [[Rodičovský portál]] — mobilní navigace | Střední | `layout.tsx` nemá bottom nav pro mobile |
| Přeplatky — UI pro vrácení | Nízká | Zobrazeno v dashboardu, řeší ředitel ručně |
