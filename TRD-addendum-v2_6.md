# TRD — Addendum v2.6
# Aplikovat na TRD v2.1
# Datum: 2026-05-21

---

## CHANGELOG — přidat za v2.5

```
**Changelog v2.6 (2026-05-21):** Opraven nefunkční Fio import cron.
Tři nezávislé příčiny: (1) Vercel Free tier nepodporuje Cron Jobs →
nahrazeno GitHub Actions schedulerem. (2) CRON_SECRET s base64 znaky
(/, +, =) způsoboval selhání autorizace → přegenerován jako hex.
(3) createSupabaseServerClient() bez session → RLS error 42501 →
přidána createSupabaseAdmin() do lib/supabase-server.ts.
Bonusově: přidán ?from=YYYY-MM-DD query param pro zpětný import přes
/periods/ endpoint. Viz ARCH-NOTES v2.2 sekce 32.
```

---

## SEKCE 4.6 — Automatický import bankovních transakcí (aktualizace)

Nahradit stávající sekci 4.6 tímto textem:

### 4.6 Automatický import bankovních transakcí

**Status: Nasazeno v produkci (2026-05-15), opraveno (2026-05-21)**

#### Architektura

```
GitHub Actions (0 6 * * * UTC)
    → curl GET /api/cron/fio-import
        → Fio API /last/ endpoint (nebo /periods/ při zpětném importu)
            → pro každou transakci:
                ├── match přes variable_symbol → students.kod_zaka
                ├── match přes specific_symbol → payment_obligations
                ├── INSERT payment_transactions (createSupabaseAdmin — RLS bypass)
                ├── matched → INSERT payment_matches
                └── unmatched → INSERT system_alerts
```

**Poznámka:** Vercel Cron Jobs nejsou na Free tieru dostupné.
Scheduler zajišťuje GitHub Actions (`.github/workflows/fio-import.yml`).

#### Soubory

```
lib/fio.ts                            ← Fio API client (podporuje /last/ i /periods/)
lib/supabase-server.ts                ← createSupabaseAdmin() pro RLS bypass
app/api/cron/fio-import/route.ts      ← Cron handler, GET chráněný CRON_SECRET
.github/workflows/fio-import.yml      ← GitHub Actions scheduler (náhrada Vercel Cron)
vercel.json                           ← ponechán, na Free tieru bez efektu
```

#### Fio API — klíčové poznatky

- Endpoint `/last/` vrátí transakce od posledního volání — Fio udržuje kurzor per token
- Endpoint `/periods/from/to/` vrátí transakce za konkrétní období — pro zpětný import
- Limit: 1 volání per 30 sekund na token (HTTP 422 při překročení)
- HTTP 409 = token používán jiným spojením
- **První použití tokenu vyžaduje jednorázovou autorizaci v Fio IB:**
  Nastavení → API → Autorizovat. Platnost 10 minut.
- Produkční token nesmí být používán paralelně (IB + aplikace)

#### Zpětný import (manuální)

```powershell
curl.exe -s -H "Authorization: Bearer <CRON_SECRET>" `
  "https://nilsson-two.vercel.app/api/cron/fio-import?from=2026-05-01"
```

Bez `?from` endpoint používá `/last/` (standardní chování pro cron).

#### Matchování transakcí

```
variable_symbol → padStart(4, '0') → LIKE '%-NNNN' → students.kod_zaka
specific_symbol + student_id → payment_obligations.ss_kod
```

| `match_status` | Podmínka |
|----------------|----------|
| `matched` | VS i SS sedí → INSERT payment_matches |
| `unmatched` | VS nebo SS nesedí → INSERT system_alerts |

#### Idempotence

`fio_transaction_id` UNIQUE — duplicitní import transakci přeskočí (kód `23505`).

#### Env proměnné

| Proměnná | Popis |
|----------|-------|
| `FIO_TOKEN` | API token Fio banky (sensitive) |
| `CRON_SECRET` | Ochrana cron endpointu — **generovat jako hex, nikoli base64** |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role pro RLS bypass (cron nemá session) |

#### Otevřené TODO (Fáze 2 — platební modul)

- UI pro přehled `payment_transactions` v dashboardu
- Manuální párování nespárovaných transakcí průvodcem
- Generátor pohledávek z `events` → `payment_obligations`
- `payment_matches` — UI párování pohledávek s transakcemi
