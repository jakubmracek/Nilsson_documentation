# TRD — Addendum v2.3
# Aplikovat na TRD-v2.0.md (po aplikaci addend v2.1 a v2.2)
# Datum: 2026-05-15

---

## CHANGELOG — přidat za v2.2

```
**Changelog v2.3 (2026-05-15):** Implementován Discord webhook modul (Fáze 2b)
a automatický import bankovních transakcí z Fio API. Discord: lib/discord.ts,
notifikace v portal-omluvenky.ts + omluvenky.ts. Fio: lib/fio.ts,
app/api/cron/fio-import/route.ts, vercel.json (Cron 6:00 denně).
Nasazeno v produkci. Viz ARCH-NOTES v2.1 sekce 28–29.
```

---

## SEKCE 4.5 — Discord webhook notifikace (nová sekce)

### 4.5 Discord webhook (`lib/discord.ts`)

**Status: Nasazeno v produkci (2026-05-15)**

Neblokující notifikační vrstva pro průvodce. Selhání webhoku
neovlivní výsledek žádné Server Action.

#### Triggery

| Událost | Akce | Embed |
|---------|------|-------|
| Nová omluvenka od rodiče | `createGuardianOmluvenka()` | amber |
| Schválení omluvenky | `approveOmluvenka()` | zelený |
| Zamítnutí omluvenky | `rejectOmluvenka()` | červený |

#### Env

```
DISCORD_WEBHOOK_URL    — URL Discord webhoku (sensitive, Vercel + .env.local)
```

---

## SEKCE 4.6 — Fio import (nová sekce)

### 4.6 Automatický import bankovních transakcí

**Status: Nasazeno v produkci (2026-05-15)**

#### Architektura

```
Vercel Cron (0 6 * * *)
    → GET /api/cron/fio-import
        → Fio API /last/ endpoint
            → pro každou transakci:
                ├── match přes variable_symbol → students.kod_zaka
                ├── INSERT payment_transactions
                └── unmatched → INSERT system_alerts
```

#### Soubory

```
lib/fio.ts
app/api/cron/fio-import/route.ts
vercel.json
```

#### Matchování

Variabilní symbol → `padStart(4, '0')` → `LIKE '%-NNNN'` na `students.kod_zaka`.

| `match_status` | Význam |
|----------------|--------|
| `matched` | Transakce spárována se žákem |
| `unmatched` | VS chybí nebo žák nenalezen → system_alert |

#### Idempotence

`fio_transaction_id` UNIQUE — duplicitní import transakci přeskočí (kód `23505`).

#### Env

```
FIO_TOKEN       — API token Fio banky (sensitive, Vercel + .env.local)
CRON_SECRET     — ochrana Cron endpointu (sensitive, Vercel + .env.local)
```

#### Otevřené TODO (Fáze 2 — platební modul)

- UI přehled transakcí v dashboardu
- Manuální párování nespárovaných transakcí
- Generátor pohledávek z `events` → `payment_obligations`
- `payment_matches` — logika párování pohledávek s transakcemi
- Fio API — platnost tokenu: první použití vyžaduje autorizaci v IB

---

## SEKCE 1.3 — aktualizovat soubory

```
lib/
├── discord.ts                        ← webhook helper + embed továrny
└── fio.ts                            ← Fio API client

app/api/
└── cron/
    └── fio-import/
        └── route.ts                  ← Cron handler, GET chráněný CRON_SECRET

vercel.json                           ← Cron Job: /api/cron/fio-import, 0 6 * * *
```
