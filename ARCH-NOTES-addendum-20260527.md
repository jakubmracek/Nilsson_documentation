# ARCH-NOTES + TRD Addendum — 2026-05-27

Navazuje na addendum 2026-05-25. Popisuje změny provedené v session 2026-05-27.

---

## 1. Rebranding: Vilekula IS → Nilsson

### Rozhodnutí
Produkční název systému je **Nilsson**. Název školy (ZŠ Vilekula Teplice) se nemění.

### Provedené změny
Záměny provedeny přes PowerShell (`-Encoding UTF8`, `-LiteralPath`):

| Soubor | Typ změny |
|--------|-----------|
| `app/dashboard/msmt/page.tsx` | metadata title |
| `app/dashboard/msmt/kody-zaku/page.tsx` | metadata title (opraveno dodatečně) |
| `app/login/page.tsx` | nadpis, placeholder `jmeno@zsvilekula.cz`, logo div |
| `app/dashboard/layout.tsx` | mobile topbar logo + název |
| `components/nav/AppNav.tsx` | sidebar logo + název |

### Logo
- Komponenta: `components/NilssonLogo.tsx`
- SVG opice, `fill="#F97316"` (orange-500), `viewBox="-5.0 -10.0 110.0 115.0"`
- Export: `<NilssonLogo size={28} />`
- Použití: login (size 48), dashboard topbar (size 16), sidebar (size 28)
- Logo div: `bg-orange-50` (bylo `bg-emerald-700`)

### Záměny emailů
- `info@vilekula.cz` → `nilsson@zsvilekula.cz`
- `platby@vilekula.cz` → `nilsson@zsvilekula.cz`
- `jmeno@vilekula.cz` → `jmeno@zsvilekula.cz`
- Ověřená doména v Resend: `zsvilekula.cz`

---

## 2. Bug fix: párování plateb (fio-import)

### Příčina
`lib/fio-import/route.ts`, řádek 67:
```typescript
// BYLO — chybné:
const paddedVS = tx.variableSymbol.padStart(4, '0')
// OPRAVENO:
const paddedVS = tx.variableSymbol.padStart(3, '0')
```

VS `'014'` s `padStart(4)` → `'0014'`, LIKE query `'%-0014'` nenašel žádného žáka → `studentId = null` → auto-match nikdy nenastane.

### Správné chování
`kod_zaka` má formát `VIL-YYYY-NNN` (třímístný suffix). `padStart(3)` je kanonické.

### Dopad
Platby importované před opravou (match_status = 'unmatched') se **nepřepárovávají automaticky** — je třeba ruční párování přes detail transakce nebo přímý SQL.

---

## 3. Ruční párování transakcí — SQL konvence

Při ručním párování přes SQL (mimo UI `manualMatch`):

```sql
INSERT INTO payment_matches (transaction_id, obligation_id, matched_amount, matched_at, matched_by)
VALUES ('{tx_uuid}', '{obligation_uuid}', {částka}, now(), null);

UPDATE payment_transactions
SET match_status = 'manual_override'
WHERE id = '{tx_uuid}';
```

**Pozor:** `manualMatch` akce automaticky resolvuje `system_alerts`. Při přímém SQL INSERT je třeba alert resolvovat manuálně:

```sql
UPDATE system_alerts
SET resolved_at = now()
WHERE alert_type = 'unmatched_transaction'
  AND entity_id::uuid = '{tx_uuid}'
  AND resolved_at IS NULL;
```

---

## 4. Fix: manualMatch — alert resolve

### Příčina
`app/actions/payments.ts` — `manualMatch` používal `createSupabaseServerClient()` i pro UPDATE `system_alerts`. RLS blokovala update (staff nemá přímé UPDATE právo na `system_alerts`).

### Oprava
Alert resolve přepnut na admin klienta:

```typescript
// Import přidán:
import { createSupabaseAdmin } from '@/lib/supabase-server'

// V manualMatch():
const supabaseAdmin = createSupabaseAdmin()
const { error: alertErr } = await supabaseAdmin
  .from('system_alerts')
  .update({ resolved_at: new Date().toISOString(), resolved_by: user.id })
  .eq('entity_id', input.transactionId)
  .eq('alert_type', 'unmatched_transaction')
  .is('resolved_at', null)
```

### Poznámka k entity_id
`system_alerts.entity_id` je typ `text`. Při SQL dotazech je třeba explicitní cast:
```sql
entity_id::uuid IN (SELECT id FROM payment_transactions ...)
```

---

## 5. Cleanup system_alerts

### Provedeno
Jednorázový cleanup orphan a zastaralých alertů:

```sql
-- Resolvovat alerty na spárované transakce
UPDATE system_alerts
SET resolved_at = now()
WHERE alert_type = 'unmatched_transaction'
  AND resolved_at IS NULL
  AND entity_id::uuid IN (
    SELECT id FROM payment_transactions
    WHERE match_status IN ('matched', 'manual_override')
  );

-- Resolvovat orphan alerty (entita neexistuje)
UPDATE system_alerts
SET resolved_at = now()
WHERE alert_type = 'unmatched_transaction'
  AND resolved_at IS NULL
  AND entity_id::uuid NOT IN (
    SELECT id FROM payment_transactions
  );
```

### Stav po cleanup
- `unmatched_transaction`: 0 aktivních
- `missing_doc`: 32 aktivních (BOZP záznamy 2025/2026) — legitimní

---

## 6. Dashboard AlertsWidget — skupinování alertů

### Změna
`app/dashboard/page.tsx` — `AlertsWidget` přepracován ze zobrazení počtů po severity na skupinování po `alert_type`.

### Chování
- Alerty stejného typu = jeden řádek s počtem: `BOZP 32×`
- Jeden alert daného typu = proklik na konkrétní entitu
- Více alertů = proklik na sekci

### URL mapping (`alertGroupLink`)
| alert_type | count | URL |
|---|---|---|
| `unmatched_transaction` | 1 | `/dashboard/platby/transakce/{entity_id}` |
| `unmatched_transaction` | >1 | `/dashboard/platby` |
| `missing_doc` | any | `/dashboard/bozp` |

### Rozšíření
Pro nové typy alertů přidat:
1. Label do `alertLabel()` v `page.tsx`
2. URL do `alertGroupLink()` v `page.tsx`

### Severity skupiny
Skupina přebírá nejvyšší severity ze všech alertů daného typu (`highestSeverity()`).

---

## 7. Otevřené položky (aktualizovaný backlog)

### Vysoká priorita
- `kod_zaka_msmt` — doplnit pro všech 32 žáků před podzimním MŠMT XML sběrem
- Supabase TypeScript typy regenerovat — `supabase gen types typescript`

### Střední priorita
- `CURRENT_SCHOOL_YEAR` centralizovat do `lib/config.ts`
- Portál — mobilní navigace (`app/portal/layout.tsx` nemá bottom nav)
- Ověřit `column6` = SS na live Fio transakci

### Nízká priorita
- Storno pohledávky (zatím přímý SQL)
- Přeplatky UI
- `alertTypeLabel` rozšiřovat průběžně s novými typy alertů
