# TRD Addendum — Ignorování transakcí
**Datum:** 2026-05-25
**Navazuje na:** TRD-addendum-payments-20260521.md

---

## Nová funkce: Soft delete transakcí

### Motivace
Některé importované transakce (státní dotace, bankovní poplatky apod.)
nikdy nebudou spárovány s pohledávkou. Místo opakovaného mazání (cron
by je re-importoval) zavádíme příznak `ignored`.

---

### Migrace 024_ignore_transactions.sql

- `payment_transactions` +1 sloupec: `ignored BOOLEAN NOT NULL DEFAULT FALSE`
- Partial index `idx_payment_transactions_ignored` (WHERE ignored = TRUE)
- Cron není třeba měnit — duplicate check přes `fio_transaction_id` funguje,
  protože ignorovaný řádek v DB brání re-importu automaticky.

---

### Server Actions (přidáno do app/actions/payments.ts)

#### ignoreTransaction(transactionId)
- Guard: `is_director()`
- Ochrana: spárovanou transakci (`matched` / `manual_override`) nelze ignorovat
- UPDATE `ignored = TRUE`
- `revalidatePath` na seznam i detail

#### restoreTransaction(transactionId)
- Guard: `is_director()`
- UPDATE `ignored = FALSE` WHERE `ignored = TRUE` (idempotentní)
- `revalidatePath` na seznam i detail

---

### UI — transakce/page.tsx

- Defaultní view: `WHERE ignored = FALSE`
- URL param `?zobrazit=vse` zobrazí i ignorované (zašedlé řádky, opacity-40)
- Počítadlo ignorovaných v odkazu "Zobrazit ignorované (N)"
- Filtry jako URL search params — zachovají se po refreshi, URL je sdílitelná
- Nový Client Component `_components/IgnoreButton.tsx`:
  - `useTransition` pro non-blocking pending state
  - Skrytý pro spárované transakce
  - Text: "Ignorovat" → "Obnovit" podle stavu

---

### Otevřené TODO (aktualizováno)

| Položka | Priorita | Poznámka |
|---|---|---|
| ~~Ověřit column6 = SS v Fio JSON~~ | ~~Vysoká~~ | Potvrzeno z Fio API dokumentace ✅ |
| Portál — mobilní navigace | Střední | layout.tsx nemá bottom nav pro mobile |
| Storno pohledávky | Nízká | Řeší ředitel přímo v DB |
| Přeplatky — UI pro vrácení | Nízká | Zobrazeno v dashboardu, řeší ředitel ručně |
