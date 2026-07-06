# ARCH-NOTES — Addendum v2.1
# Připojit na konec ARCH-NOTES-v2.0.md
# Datum: 2026-05-15 | Navazuje na TRD v2.3

---

## 28. Discord webhook notifikace (2026-05-15)

### 28.1 Přehled

Implementován neblokující Discord webhook pro notifikace průvodci
při událostech v modulu omluvenek.

### 28.2 Soubory

```
lib/discord.ts                        ← helper + embed továrny
app/actions/portal-omluvenky.ts       ← Trigger 1: nová omluvenka od rodiče
app/actions/omluvenky.ts              ← Trigger 2: schválení / zamítnutí
```

### 28.3 Architekturické rozhodnutí

- `void notifyDiscord(...)` — záměrně bez `await`; Server Action nečeká
  na odpověď Discordu
- `try/catch` bez rethrow v `notifyDiscord()` — selhání webhoku nikdy
  neprobublá do akce a nepokazí uložení dat
- Chybějící `DISCORD_WEBHOOK_URL` → tichý no-op (bezpečné v localhostu
  bez `.env.local`)

### 28.4 Embed továrny

| Funkce | Barva | Trigger |
|--------|-------|---------|
| `embedNovaOmluvenka` | amber `#f59e0b` | `createGuardianOmluvenka()` |
| `embedOmluvenkaApproved` | green `#22c55e` | `approveOmluvenka()` |
| `embedOmluvenkaRejected` | red `#ef4444` | `rejectOmluvenka()` |

### 28.5 Změny v Server Actions oproti originálu

**`portal-omluvenky.ts`:**
- Přidán fetch `students(first_name, last_name)` před insert
  (extra query pro čitelnou notifikaci)

**`omluvenky.ts`:**
- `staff` select rozšířen o `first_name, last_name` v `approveOmluvenka`
  i `rejectOmluvenka`
- `absence_requests` select rozšířen o `students(first_name, last_name)`
  — Supabase PostgREST join přes FK, výsledek v `req.students` (objekt)

### 28.6 Env proměnné

| Proměnná | Popis |
|----------|-------|
| `DISCORD_WEBHOOK_URL` | URL Discord webhoku (sensitive) |

Nastaveno na Vercelu (production) + `.env.local`.

---

## 29. Fio banka — automatický import transakcí (2026-05-15)

### 29.1 Přehled

Denní automatický import bankovních transakcí z Fio API do
`payment_transactions`. Spouštěno Vercel Cron každý den v 6:00.

### 29.2 Soubory

```
lib/fio.ts                            ← Fio API client
app/api/cron/fio-import/route.ts      ← Next.js API route (Cron handler)
vercel.json                           ← Cron Job konfigurace
```

### 29.3 Fio API — klíčové poznatky

- Endpoint `/last/` vrátí transakce od posledního volání — Fio udržuje
  kurzor per token
- Limit: **1 volání per 30 sekund** na token (HTTP 422 při překročení)
- HTTP 409 = token používán jiným spojením nebo Fio IB na pozadí
- **První použití tokenu vyžaduje jednorázovou autorizaci** v Fio IB:
  Nastavení → API → Autorizovat. Platnost 10 minut.
- Produkční token nesmí být používán paralelně (IB + aplikace)

### 29.4 Matchování transakcí na žáky

```
transaction.variable_symbol → padStart(4, '0') → LIKE '%-NNNN' → students.kod_zaka
```

`kod_zaka` formát: `VIL-YYYY-NNNN` — VS odpovídá pořadovému číslu (4 číslice).
Nespárovaná transakce → `match_status = 'unmatched'`.

### 29.5 Duplicity

`fio_transaction_id` má UNIQUE constraint — duplicitní INSERT vrátí
chybu `23505`, transakce se přeskočí (idempotentní import).

### 29.6 System alerts

Nespárovaná transakce → INSERT do `system_alerts`:
- `entity_id` = UUID z `payment_transactions.id` (dvoustupňový insert —
  nejdřív transakce, pak alert s vráceným UUID)
- `alert_type = 'unmatched_transaction'`
- `severity = 'warning'`

Důvod dvoustupňového insertu: `system_alerts.entity_id` je UUID,
`fio_transaction_id` je TEXT — nelze použít přímo.

### 29.7 Ochrana endpointu

`Authorization: Bearer <CRON_SECRET>` header — Vercel Cron ho posílá
automaticky. Manuální volání vyžaduje stejný header.

### 29.8 Env proměnné

| Proměnná | Popis |
|----------|-------|
| `FIO_TOKEN` | API token Fio banky (sensitive) |
| `CRON_SECRET` | Tajný klíč pro ochranu Cron endpointu (sensitive) |

Obě nastaveny na Vercelu (production) + `.env.local`.

### 29.9 Vercel Cron

```json
{
  "crons": [
    {
      "path": "/api/cron/fio-import",
      "schedule": "0 6 * * *"
    }
  ]
}
```

Ověřeno v Vercel dashboard → Settings → Cron Jobs.

### 29.10 Otevřené TODO

- UI pro přehled `payment_transactions` v dashboardu (neexistuje)
- Manuální párování nespárovaných transakcí průvodcem
- Generátor pohledávek z `events` → `payment_obligations`
- `payment_matches` tabulka — logika párování pohledávek s transakcemi
