# ARCH-NOTES — Addendum v2.2
# Aplikovat na ARCH-NOTES v2.1
# Datum: 2026-05-21

---

## SEKCE 32 — Fio import: diagnostika a opravy (2026-05-21)

### 32.1 Kontext

Po nasazení (2026-05-15) cron job neprobíhal. Diagnostika odhalila tři nezávislé příčiny.

---

### 32.2 Bug #1 — Vercel Free tier nepodporuje Cron Jobs

**Příznak:** `vercel.json` s `crons` konfigurací byl syntakticky správný,
job se ale nikdy nespustil.

**Příčina:** Vercel Cron Jobs jsou dostupné pouze na **Pro plánu** ($20/měs).
Na Free tieru je konfigurace ignorována bez chybové hlášky.

**Řešení: GitHub Actions jako náhradní scheduler**

Soubor `.github/workflows/fio-import.yml`:

```yaml
name: Fio Import
on:
  schedule:
    - cron: '0 6 * * *'   # 6:00 UTC = 7:00/8:00 SEČ/SELČ
  workflow_dispatch:        # manuální spuštění z GitHub UI
jobs:
  import:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Fio import
        run: |
          curl -f -X GET \
            -H "Authorization: Bearer ${{ secrets.CRON_SECRET }}" \
            https://nilsson-two.vercel.app/api/cron/fio-import
```

`CRON_SECRET` přidán do GitHub → repo → Settings → Secrets and variables → Actions.
`vercel.json` ponechán beze změny (nebrání, ale nemá efekt na Free tieru).

**Poznámka k časovým pásmům:**
GitHub Actions `cron` běží vždy v UTC. `0 6 * * *` = 7:00 v zimě / 8:00 v létě.
Pro konzistentní čas použít `0 4 * * *` (vždy 6:00 SELČ).

---

### 32.3 Bug #2 — CRON_SECRET se speciálními znaky způsoboval selhání autorizace

**Příznak:** Endpoint vracel `{"error":"Unauthorized"}` i při správně zadaném secretu.

**Příčina:** Původní `CRON_SECRET` byl generován jako base64 (`openssl rand -base64 32`)
a obsahoval znaky `/`, `+`, `=`. Tyto znaky mohou způsobit problémy při porovnávání
v HTTP hlavičkách nebo při předávání v shellu.

Kontrola v `route.ts`:
```ts
if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) { ... }
```

**Řešení:** Secret přegenerován jako čistý hex (pouze `0-9a-f`):

```powershell
# PowerShell (Windows — openssl není vždy dostupný)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
```

Nový secret aktualizován na třech místech:
1. Vercel → Settings → Environment Variables → `CRON_SECRET` → Edit + Redeploy
2. GitHub → Settings → Secrets → `CRON_SECRET` → Update
3. `.env.local` lokálně

**Pravidlo:** `CRON_SECRET` generovat vždy jako hex, nikoli base64.

---

### 32.4 Bug #3 — RLS blokovala INSERT v cron kontextu (error 42501)

**Příznak:** Vercel Logs:
```
[fio-import] INSERT chyba: {
  code: '42501',
  message: 'new row violates row-level security policy for table "payment_transactions"'
}
```

**Příčina:** `app/api/cron/fio-import/route.ts` používal `createSupabaseServerClient()`,
který běží pod session přihlášeného uživatele (anon key + cookie). Cron nemá žádnou
uživatelskou session → `auth.uid()` = null → RLS zamítne INSERT.

**Řešení:** Přidána funkce `createSupabaseAdmin()` do `lib/supabase-server.ts`:

```ts
import { createClient } from '@supabase/supabase-js'

export function createSupabaseAdmin() {
  return createClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  )
}
```

`route.ts` upraven: `createSupabaseServerClient()` → `createSupabaseAdmin()`
(synchronní volání, bez `await`).

Prerekvizita: env proměnná `SUPABASE_SERVICE_ROLE_KEY` musí být nastavena na Vercelu
(Supabase → Project Settings → API → service_role → Reveal).

**Obecné pravidlo:**
Cron joby, migrace a seed skripty vždy používají `createSupabaseAdmin()`.
`createSupabaseServerClient()` pouze v kontextech s uživatelskou session (Route Handlers,
Server Components, Server Actions volané přihlášeným uživatelem).

---

### 32.5 Endpoint `/last/` vs. `/periods/` — zpětný import

**Problém:** Fio endpoint `/last/` vrátí transakce od posledního volání.
Pokud byl token volán manuálně (diagnostika), kurzor se posune a nové automatické
volání vrátí prázdný seznam.

**Řešení:** Do `lib/fio.ts` přidán volitelný parametr `from?: string`:

```ts
export async function fetchFioTransactions(token: string, from?: string): Promise<FioTransaction[]> {
  const today = new Date().toISOString().slice(0, 10)
  const url = from
    ? `https://fioapi.fio.cz/v1/rest/periods/${token}/${from}/${today}/transactions.json`
    : `https://fioapi.fio.cz/v1/rest/last/${token}/transactions.json`
  // ...
}
```

`route.ts` čte query parametr `from`:
```ts
const from = req.nextUrl.searchParams.get('from') ?? undefined
transactions = await fetchFioTransactions(token, from)
```

**Použití pro zpětný import:**
```powershell
curl.exe -s -H "Authorization: Bearer <SECRET>" `
  "https://nilsson-two.vercel.app/api/cron/fio-import?from=2026-05-01"
```

Bez `?from` se chování nemění — produkční cron používá `/last/` jako dříve.

---

### 32.6 Env proměnné — kompletní seznam pro platební modul

| Proměnná | Kde nastavit | Popis |
|----------|-------------|-------|
| `FIO_TOKEN` | Vercel + `.env.local` | API token Fio banky |
| `CRON_SECRET` | Vercel + GitHub Secrets + `.env.local` | Ochrana cron endpointu (hex) |
| `SUPABASE_SERVICE_ROLE_KEY` | Vercel + `.env.local` | Service role pro RLS bypass v cronu |

---

### 32.7 Upravené soubory

```
lib/
├── fio.ts                  ← přidán parametr from? + /periods/ URL
└── supabase-server.ts      ← přidána funkce createSupabaseAdmin()

app/api/cron/fio-import/
└── route.ts                ← čte ?from query param, používá createSupabaseAdmin

.github/workflows/
└── fio-import.yml          ← nový soubor (GitHub Actions scheduler)
```
