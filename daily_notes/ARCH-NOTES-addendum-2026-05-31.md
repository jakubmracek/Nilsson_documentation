# ARCH-NOTES — Addendum 2026-05-31

Navazuje na ARCH-NOTES addendum 2026-05-27.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 45. [[Třídní kniha]] — opravy a rozšíření (2026-05-31)

### 45.1 Editační stránka záznamu — přechod na Server Component

**Problém:** `app/[[Přehled]]/tridni-kniha/[id]/upravit/page.tsx` byl Client Component
který načítal záznam přes `createBrowserClient`. Způsobovalo dvě chyby:
- „Záznam nenalezen" — RLS blokovala čtení přes browser klienta bez spolehlivé session
- Rozbité kódování (soubor byl Windows-1250)

**Řešení:** Vzor Server Component + Client Component (identický s Mapou pokroku, sekce 35.1):

```
app/[[Přehled]]/tridni-kniha/[id]/upravit/
├── page.tsx                    ← Server Component; načte záznam server-side, předá do EditForm
└── _components/
    └── EditForm.tsx            ← Client Component; formulář editace
```

`page.tsx` používá `await params` (Next.js 15+) a `notFound()` místo chybové hlášky.

### 45.2 SVP editační stránka — nová implementace

`app/[[Přehled]]/tridni-kniha/[id]/svp/page.tsx` existoval jako stub s nesprávným obsahem.
Nahrazen plnou implementací:

```
app/[[Přehled]]/tridni-kniha/[id]/svp/
├── page.tsx                    ← Server Component; načte záznam + vazby + výstupy
└── _components/
    └── SvpEditForm.tsx         ← Client Component; toggle vazeb s optimistic update
```

**UI:** Filtry ročník (1–5) + předmět (5 možností) + fulltext hledání. Klik = okamžitý
optimistic toggle. Označené výstupy = invertované (tmavé pozadí). Rollback při chybě.

### 45.3 `group_id` povinný pro záznamy [[Třídní kniha]]

**Rozhodnutí:** Každý záznam v `tridni_kniha_zaznamy` musí mít `group_id`.

**Důvod:** Od školního roku 2026/2027 budou dvě třídy — bez `group_id` nelze
rozlišit záznamy per třída. Retroaktivně doplněno pro 9 historických záznamů
2025/2026 bez `group_id` (výsledek: UPDATE 9).

**Dopad na formulář `novy`:** Přechod na Server Component wrapper + Client Component
`NovyZaznamForm`. Server wrapper načte skupiny pro `CURRENT_SCHOOL_YEAR` a předá
jako props. Formulář zobrazí:
- 1 skupina → readonly badge
- Více skupin → toggle buttons (výběr povinný)

**Předvyplnění z URL:** `NovyZaznamForm` čte `?datum` a `?group_id` z URL přes
`useSearchParams` — umožňuje proklik z chybějících dní přímo na správně předvyplněný formulář.

**`CreateZaznamInput`** rozšířen o `group_id?: string`. `createZaznam` Server Action
ukládá `group_id` do DB.

### 45.4 UNIQUE constraint `(datum, group_id)`

```sql
ALTER TABLE tridni_kniha_zaznamy
  ADD CONSTRAINT tridni_kniha_zaznamy_datum_group_unique
  UNIQUE (datum, group_id);
```

Před přidáním ověřeno: žádné duplicity v datech.

**Zpracování v aplikační vrstvě:** `createZaznam` i `updateZaznam` zachytávají
chybu `23505` a vrací srozumitelnou hlášku:
```typescript
if (error.code === '23505') return { error: 'Pro tento den již záznam v [[Třídní kniha]] existuje.' };
```

### 45.5 Favicon a title

- `app/favicon.ico` nahrazen `app/icon.svg` (logo opice, `fill="#F97316"`)
- `app/layout.tsx`: `title: "IS Nilsson"`, `description: "Informacni system ZS Vilekula Teplice"`, `lang="cs"`
- `app/page.tsx` (root) zredukován na jednoduchý redirect:
  ```typescript
  import { redirect } from 'next/navigation'
  export default function RootPage() { redirect('/[[Přehled]]') }
  ```

---

## 46. Alert: Nedoplněná [[Třídní kniha]] (2026-05-31)

### 46.1 Architektura

Nový typ alertu v dashboardu — generován aplikační vrstvou, ne `system_alerts` tabulkou.
Počítá pracovní dny (Po–Pá) od 1. 9. školního roku do včerejška bez záznamu v [[Třídní kniha]],
per skupina, s vyloučením svátků z `school_holidays`.

```
lib/tridni-kniha-missing.ts        ← getMissingTKDays(), formatDateCZ()
app/[[Přehled]]/page.tsx              ← fetchMissingTKCount() + AlertsWidget rozšíření
app/[[Přehled]]/tridni-kniha/
  chybejici/page.tsx                ← seznam chybějících dní per třída + proklik Doplnit
```

### 46.2 `getMissingTKDays()` — signatura

```typescript
export function getMissingTKDays(
  schoolYear: string,        // '2025/2026'
  existujiciDny: Set<string>, // záznamy v DB
  holidayDays: Set<string>,   // ze school_holidays
): string[]                   // seznam 'YYYY-MM-DD'
```

Volající předává `holidayDays` jako `Set<string>` — funkce nemá přímou Supabase závislost.
Použití v dashboardu i na stránce chybějících dní.

### 46.3 [[Přehled]] widget

`AlertsWidget` rozšířen: alert „Nedoplněná [[Třídní kniha]] N×" s prolinkováním na
`/[[Přehled]]/tridni-kniha/chybejici`. Počet = součet chybějících dní přes všechny skupiny.
Všechny alerty jsou nyní klikatelné (Link s šipkou →).

**Poznámka k typování:** `(supabase as any).from('school_holidays')` — tabulka
vznikla migrací 026 po generování `types/database.ts`. Standardní workaround
dokud se typy neregenerují (viz sekce 33.4).

---

## 47. `school_holidays` — tabulka školních prázdnin (migrace 026)

### 47.1 Schéma

```sql
CREATE TABLE school_holidays (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum       DATE NOT NULL UNIQUE,
  nazev       TEXT NOT NULL,
  typ         TEXT NOT NULL CHECK (typ IN ('statni_svatek', 'skolni_prazdniny', 'reditelske_volno')),
  school_year TEXT NOT NULL
);
```

### 47.2 RLS

- SELECT: všichni přihlášení staff (`current_staff_id() IS NOT NULL`)
- ALL: pouze director (`is_director()`)

### 47.3 Data

Naplněno pro 2025/2026 a 2026/2027:
- Státní svátky (pevné + pohyblivé — Velikonoce 2026: 3.4. a 6.4.; 2027: 26.3. a 29.3.)
- Podzimní, vánoční, pololetní, jarní, velikonoční prázdniny
- Jarní prázdniny Teplice: 2.–6. 3. 2026 a 8.–12. 3. 2027

**Správa:** Ředitel edituje přímo v DB nebo přes budoucí UI. Při přidání nového školního
roku vložit nové řádky — kód se nemění.

**Nahrazuje:** Hardcoded konstantu `STATNI_SVATKY_PEVNE` v původní verzi
`lib/tridni-kniha-missing.ts`.

---

## 48. Systémové alerty — resolve konvence (2026-05-31)

### Problém

Alert `unmatched_transaction` zůstal aktivní i po spárování transakce — transakce
byla spárována/ignorována přímo přes SQL mimo UI, `manualMatch` Server Action
(která resolve provádí automaticky) nebyla volána.

### Pravidlo

Každá operace která mění `match_status` transakce MIMO `manualMatch` Server Action
musí manuálně resolvovat příslušný alert:

```sql
UPDATE system_alerts
SET resolved_at = now()
WHERE alert_type = 'unmatched_transaction'
  AND resolved_at IS NULL
  AND entity_id::uuid = '{transaction_uuid}';
```

### Cleanup dotaz (spustit kdykoli po přímých SQL operacích)

```sql
UPDATE system_alerts
SET resolved_at = now()
WHERE alert_type = 'unmatched_transaction'
  AND resolved_at IS NULL
  AND entity_id::uuid IN (
    SELECT id FROM payment_transactions
    WHERE match_status IN ('matched', 'manual_override')
       OR ignored = true
  );
```
