# TRD — Modul Obědy: jídelníček (scraper SOSTP)

> Addendum k TRD IS Nilsson — zařaď s příští verzí. Migrace **033**, stav: nasazeno.

## 1. Komponenty / soubory

| Soubor | Účel |
|---|---|
| `supabase/migrations/033_lunch_menu.sql` | tabulky, číselník alergenů, RLS, RPC |
| `scripts/scrape-lunch-menu.ts` | scraper: fetch → parse → upsert; čisté funkce exportované kvůli testu |
| `scripts/scrape-lunch-menu.test.ts` | testy parseru nad fixturou (bez sítě a secrets) |
| `.github/workflows/lunch-menu.yml` | denní cron + ruční `workflow_dispatch` |

## 2. Zdroj dat

- URL: `https://www.sostp.cz/jidelna-dobrovolcu-jidelni-listek` (override přes env `LUNCH_MENU_URL`).
- Server-rendered HTML; stránka ukazuje aktuální týden + prázdnou šablonu týdne příštího.

## 3. Env / secrets (GitHub Actions → Settings → Secrets → Actions)

| Proměnná | Povinná | Poznámka |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ano | stejná jako v aplikaci |
| `SUPABASE_SERVICE_ROLE_KEY` | ano | **service_role** klíč — obchází RLS, jen jako secret |
| `DISCORD_LUNCH_WEBHOOK_URL` | ne | alerty při pádu/anomálii |
| `LUNCH_MENU_URL` | ne | override zdrojové URL |

## 4. DB schéma (souhrn)

**`lunch_menu_days`**: `id`, `menu_date` UNIQUE, `weekday` (1–7), `soup`, `soup_allergens smallint[]`, `week_start`, `week_end`, `source_url`, `raw_text`, `scraped_at`.
**`lunch_menu_items`**: `id`, `day_id` → `lunch_menu_days` (CASCADE), `option_no` (1–9), `description`, `allergens smallint[]`, UNIQUE`(day_id, option_no)`.
**`lunch_allergens`**: `code` (1–14) PK, `name_cs`.

## 5. RPC (čtení pro portál/objednávky)

```
get_lunch_menu_week(p_week_start date default null)
  → table(menu_date date, weekday smallint, soup text,
          soup_allergens smallint[], items jsonb)
```

- `p_week_start = NULL` → pondělí aktuálního ISO týdne (`date_trunc('week', current_date)`).
- `items` = `jsonb` pole `{option_no, description, allergens}` seřazené dle `option_no`.
- SECURITY DEFINER, STABLE, `GRANT EXECUTE TO authenticated`.

## 6. Spuštění

- **Automaticky:** denně 04:00 UTC (≈ 06:00 CEST) — `cron: '0 4 * * *'`.
- **Ručně:** Actions → `lunch-menu` → Run workflow.
- **Lokálně (PowerShell):**
  ```powershell
  $env:NEXT_PUBLIC_SUPABASE_URL="…"; $env:SUPABASE_SERVICE_ROLE_KEY="…"
  npx tsx scripts/scrape-lunch-menu.ts
  ```
  Pozor: píše do **produkční** tabulky.
- **Test parseru bez sítě:** `npx tsx scripts/scrape-lunch-menu.test.ts`

## 7. Ověření po běhu

V logu kroku „Scrape lunch menu" musí být `Uloženo N dní (…)`. Pak:

```sql
select menu_date, weekday, soup, soup_allergens
from lunch_menu_days order by menu_date desc limit 10;

select * from get_lunch_menu_week();  -- aktuální ISO týden
```

## 8. Závislosti

- `cheerio` (runtime), `tsx` (dev), `@supabase/supabase-js` (už v projektu).
- **Node 22+** (kvůli nativnímu WebSocketu vyžadovanému supabase klientem) — viz ARCH-NOTES, sekce o gotchas.

## 9. Kontrakt chování

- Idempotentní upsert na `menu_date`; položky se per den mažou a vkládají znovu.
- Ukládá jen dny s ≥1 položkou (přeskočí prázdnou šablonu příštího týdne).
- Při chybě: `exit 1` + (volitelně) Discord alert s textem chyby.
- Varování (≠ 5 dní, den bez polévky, začátek týdne není pondělí) jdou do logu a na Discord, běh ale nezruší.
