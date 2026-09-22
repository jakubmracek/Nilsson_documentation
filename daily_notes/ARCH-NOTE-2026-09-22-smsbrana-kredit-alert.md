# ARCH-NOTE: Hlídání kreditu SMSbrány + Discord alert pod 50 Kč

**Datum:** 2026-09-22
**Modul:** [[Provoz služeb]] — `/dashboard/provoz-sluzeb` + denní cron `usage-snapshot`
**Soubory:** `lib/sms.ts`, `lib/usage-monitor.ts`, `app/api/cron/usage-snapshot/route.ts`, `app/dashboard/provoz-sluzeb/page.tsx`, `app/dashboard/provoz-sluzeb/_components/ThresholdRow.tsx`, `supabase/migrations/bez migrace/124_usage_monitoring_smsbrana_credit.sql`
**Commity:** `40534ae` (feat(monitoring): hlídání kreditu SMSbrány + Discord alert pod 50 Kč)

---

## Přehled

Předplacený kredit na smsbrana.cz je kritický: když dojde, přestanou chodit ranní SMS jídelně (počty obědů, `lunch-report`). Uživatel chtěl notifikaci do Discordu, jakmile kredit klesne **pod 50 Kč**. Kredit byl přidán jako nová metrika do stávajícího provozního monitoringu (tabulky `usage_snapshots` / `usage_thresholds`, denní cron, Discord webhook). Monitoring ale uměl jen metriky typu „spotřeba vůči stropu" — kredit je obrácený (čím méně, tím hůř), proto vznikl nový typ metriky **„minimum"**.

---

## 1. Čtení kreditu z brány

**Soubor:** `lib/sms.ts` — `getSmsCredit()`

Akce `credit_info` služby SMS Connect (dokumentace v3.0, 11. 3. 2026, §3.2). Autentizace stejná jako u odesílání — AUTH_HASH (`login/time/sul/hash`) přes sdílený `buildAuth()`. Nestojí kredit.

Odpověď dle dokumentace **nemá `<err>`**:

```xml
<result> <credit>1523.32</credit> </result>
```

Stávající `parseErr()` už tohle pokrývá (bez `<err>`, ale s `<result>` = úspěch — kvůli akci `inbox`). Hodnota se tahá regexem `<credit>` a při chybě funkce **hází výjimku** — adaptér v monitoringu ji převede na `ok=false`.

## 2. Metriky typu „minimum" (floor)

**Soubor:** `lib/usage-monitor.ts` — `FLOOR_METRICS`, `isFloorMetric()`, `evaluateMetric()`, `buildAlertMessage()`, `fetchSmsbrana()`

### Problém
`evaluateMetric` počítá `ratio = value / limit` a alertuje při `ratio >= warn/crit` — tj. když se hodnota blíží stropu. U kreditu by 20 Kč / 50 Kč = 40 % vyšlo jako „OK".

### Řešení
- `FLOOR_METRICS = new Set(['smsbrana|credit_czk'])` — seznam v kódu, **bez nového sloupce v DB** (nebylo nutné regenerovat `types/database.ts`).
- U floor metriky je `manual_limit` **spodní hranice**: `value < limit` → `crit`, jinak `ok`; `enabled=false` → `info`. Poměry warn/crit se neuplatní, `ratio = null`.
- Alertová řádka má vlastní znění: *„Zbývající kredit: 49,9 Kč (pod minimem 50 Kč) — dobít, jinak přestanou chodit SMS jídelně"*. Nadpis sekce zkrácen z „Kritické (blízko limitu)" na „Kritické" (platí pro oba typy).
- Adaptér `fetchSmsbrana(getCredit)` — callback vzor jako `fetchSupabase`, aby `usage-monitor.ts` (importovaný i stránkou) nezávisel na `node:crypto` z `lib/sms.ts`.

### Chování alertu
Cron nemá anti-flap → pod minimem chodí alert **každý den, dokud se kredit nedobije**. U kreditu je to žádoucí (připomínka).

## 3. Cron, UI, migrace

- **Cron** `usage-snapshot/route.ts`: `fetchSmsbrana(getSmsCredit)` v `Promise.all`; testovací režim `?test=1` obsahuje ukázkový řádek kreditu (38 Kč / min. 50 Kč).
- **UI** `/dashboard/provoz-sluzeb`: sloupec Limit ukazuje „min. 50 Kč", místo progress baru „hlídá se minimum"; v editoru prahů (`ThresholdRow`, prop `floor`) jsou procentní pole nahrazena textem „alert pod minimem", ruční limit má placeholder „minimum". Minimum je tak editovatelné bez migrace.
- **Migrace 124** (`124_usage_monitoring_smsbrana_credit.sql`): jen seed řádku `usage_thresholds` (`smsbrana`, `credit_czk`, `Zbývající kredit`, `Kč`, manual_limit **50**, poradi 5), `ON CONFLICT DO NOTHING`, v `BEGIN/COMMIT`. Původně očíslována 121 — uživatel opravil, že další volné číslo je **124**.

### Poučení
- Monitoring dřív předpokládal „vyšší = horší". Pro zásoby (kredit, zbývající kvóta) je potřeba obrácená logika — teď stačí přidat klíč do `FLOOR_METRICS` + seed prahu.
- Číslo migrace **neodvozovat z `ls` složky `bez migrace/`** — souběžné větve/PR mohou mít rezervovaná vyšší čísla; ověřit u uživatele.
- `credit_info` nevrací `<err>` — parser nesmí vyžadovat `<err>`, jinak by byl úspěch vyhodnocen jako chyba.

---

## Ověření

- `tsc --noEmit` čistý.
- Jednorázový skript přes `tsx`: `evaluateMetric` pro 120 / 50 / 49,9 Kč → `ok` / `ok` / `crit`, text alertu zkontrolován.
- Po nasazení (Vercel `success` na `40534ae`) a spuštění migrace 124 ručně spuštěn workflow **Usage Snapshot** (run 35775662575): `collected: 3`, vše `ok`, **`smsbrana.credit_czk = 77,78 Kč`** — kredit se z brány reálně načítá, alert se (správně) neposlal.
- Vizuální kontrola stránky `/dashboard/provoz-sluzeb` neproběhla (vyžaduje přihlášení ředitele).

## Vedlejší nález (nezasahováno)

- Na modulové stránce `Provoz služeb.md` jsou existující embedy rozbité autolinkem: `![[PRD-[[Provoz služeb]]-infra-2026-08-03]]` místo `![[PRD-monitoring-infra-2026-08-03]]` (a obdobně FIX). `autolink.py` zřejmě přepisuje slovo „monitoring" i uvnitř `![[…]]`. Proto slug tohoto zápisu slovo „monitoring" neobsahuje.
- Kredit 77,78 Kč je ~28 Kč nad hranicí — při ~1 SMS/pracovní den alert zhruba za 5–6 týdnů.

## Související

- [[FIX-monitoring-provoz-2026-08-12]] — předchozí troubleshooting dlaždice (vyřazení CF/Railway, GitHub billing)
- [[PRD-monitoring-infra-2026-08-03]] — původní návrh monitoringu
- [[FIX-obedy-sms-cron-github-delay-2026-09-02]] — ranní SMS jídelně, kterou kredit chrání
- [[ARCH-NOTE-2026-09-01-obedy-sms-vekove-kategorie-a-mesicni-vyuctovani]] — text SMS reportu jídelně
- [[Obědy]] — modul, jehož SMS závisí na kreditu
