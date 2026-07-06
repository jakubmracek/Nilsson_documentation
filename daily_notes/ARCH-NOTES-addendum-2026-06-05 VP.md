# ARCH-NOTES — Addendum 2026-06-05

Navazuje na ARCH-NOTES addendum 2026-05-31.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 49. [[Výchovný poradce (VP)]] modul — architektonická rozhodnutí (2026-06-05)

### 49.1 Scope — co bylo vypuštěno oproti původnímu TRD

Původní TRD v2.1 sekce 6 navrhoval čtyři tabulky:
`vp_student_care`, `vp_intervention_log`, `vp_document`, `vp_annual_plan`.

Po ladění scope (2026-06-05) bylo rozhodnuto:

| Entita | Rozhodnutí | Důvod |
|--------|------------|-------|
| `vp_student_care` | ✅ implementováno (nové schéma) | Jádro modulu |
| `vp_intervention_log` | ❌ P2 | Záznamy se vedou v Discordu, export v budoucnu |
| `vp_document` | ❌ nahrazeno | Drive URL + JSONB checklist na kartě péče |
| `vp_annual_plan` | ❌ vypuštěno | Generovat z exportů |

### 49.2 Zahození starých stubů

Tabulky `vp_student_care`, `vp_intervention_log`, `vp_document` existovaly
jako prázdné stuby z TRD v2.1. Migrace 030 je zahazuje přes:

```sql
DROP TABLE IF EXISTS vp_document CASCADE;
DROP TABLE IF EXISTS vp_intervention_log CASCADE;
DROP TABLE IF EXISTS vp_annual_plan CASCADE;
DROP TABLE IF EXISTS vp_student_care CASCADE;
```

Pořadí je záměrné — závislé tabulky musí jít před parentem.
`CASCADE` odstraní FK constraints a RLS politiky navázané na staré stuby.

Funkce `generate_vp_alerts()` také existovala jako stub s nekompatibilním
návratovým typem → `DROP FUNCTION IF EXISTS` před `CREATE OR REPLACE`.

### 49.3 Datový model — `vp_student_care`

Jedna tabulka místo čtyř. Klíčové rozhodnutí: dokumenty jako JSONB checklist
na záznamu péče, ne jako samostatná tabulka.

```sql
CREATE TABLE vp_student_care (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id        UUID        NOT NULL REFERENCES students(id),
  school_year       TEXT        NOT NULL,
  typ_pece          typ_vp_pece NOT NULL,   -- ENUM: watch | po_1..po_5
  status            TEXT        NOT NULL DEFAULT 'active',
  spz_valid_until   DATE,
  spz_review_due    DATE,
  ivp_required      BOOLEAN     NOT NULL DEFAULT FALSE,
  ivp_evaluated_at  DATE,
  drive_url_public  TEXT,
  drive_url_private TEXT,                   -- citlivé pole — viz sekce 49.5
  dokumenty         JSONB       NOT NULL DEFAULT '{}',
  poznamka          TEXT,
  started_at        DATE        NOT NULL DEFAULT CURRENT_DATE,
  closed_at         DATE,
  created_by        UUID        NOT NULL REFERENCES staff(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, school_year)
);
```

### 49.4 JSONB `dokumenty` — struktura

Pevný seznam klíčů s defaultními hodnotami citlivosti:

| Klíč | Label | `default_private` | `has_expiry` |
|------|-------|-------------------|--------------|
| `doporuceni_spz` | Doporučení ŠPZ | false | true |
| `souhlas_zz` | Souhlas zákonného zástupce | false | false |
| `ivp` | IVP | false | false |
| `plpp` | PLPP | false | false |
| `hodnoceni_ivp` | Hodnocení IVP | false | true |
| `zprava_psychiatrie` | Zpráva z psychiatrie | **true** | false |
| `zprava_psychologie` | Zpráva z psychologie | **true** | false |
| `zprava_neurologie` | Zpráva z neurologie | **true** | false |
| `soudni_prikaz_ospod` | Soudní příkaz / OSPOD | **true** | false |
| `jine` | Jiné | false | false |

Struktura každé položky:
```typescript
{
  exists:      boolean
  valid_until: string | null   // 'YYYY-MM-DD'
  in_private:  boolean         // zadavatel může přepsat default
  poznamka?:   string | null   // pouze pro klíč 'jine'
}
```

**Důvod JSONB místo samostatné tabulky:** Vilekula má 32 [[Žáci]], počet dokumentů
per žák je malý a pevně daný. JSONB eliminuje JOIN a zjednodušuje UI i dotazy.
Pokud by v budoucnu vznikla potřeba verzování nebo auditní stopy dokumentů,
přidá se `vp_dokumenty_history` tabulka (append-only vzor).

### 49.5 Citlivá pole — filtrování v aplikační vrstvě

`drive_url_private` a dokumenty s `in_private: true` jsou viditelné pouze
pro role `director` a `[[Výchovný poradce (VP)]]`. RLS zajišťuje přístup k řádkům tabulky,
ale **nefiltruje jednotlivá pole** — to je záměrně v aplikační vrstvě.

Funkce `maskSensitiveFields()` v `lib/[[Výchovný poradce (VP)]].ts`:
```typescript
function maskSensitiveFields(care, role) {
  if (role === 'director' || role === '[[Výchovný poradce (VP)]]') return care
  return {
    ...care,
    drive_url_private: null,
    dokumenty: filterPrivateDokumenty(care.dokumenty),
  }
}
```

`filterPrivateDokumenty()` v `lib/[[Výchovný poradce (VP)]]-shared.ts` odstraní položky
s `in_private: true` z JSONB mapy.

**Proč ne v RLS:** PostgreSQL neumí podmíněně maskovat jednotlivá JSONB pole
per role v SELECT politice. Alternativa (pohled + security barrier) by
zkomplikovala dotazy bez reálného bezpečnostního přínosu nad RLS + app layer.

### 49.6 Lhůtové alerty — funkce `generate_vp_alerts()`

SECURITY DEFINER funkce, volána z cron endpointu `/api/cron/[[Výchovný poradce (VP)]]-alerts`
(GitHub Actions, každé pondělí 5:00 UTC).

6 typů alertů s deduplication přes `entity_id + alert_type + resolved_at IS NULL`:

| `alert_type` | Podmínka | Severity |
|---|---|---|
| `spz_expiry` | `spz_valid_until <= dnes + 60 dní` | critical |
| `spz_review_due` | `spz_review_due <= dnes + 30 dní` | warning |
| `ivp_overdue` | `ivp_evaluated_at < dnes - 1 rok` AND `ivp_required` | warning |
| `missing_doporuceni_spz` | PO 2–5 AND `doporuceni_spz.exists = false` | critical |
| `missing_souhlas_zz` | PO 2–5 AND `souhlas_zz.exists = false` | critical |
| `missing_ivp` | `ivp_required` AND `ivp.exists = false` | warning |

**Deduplication:** `IF NOT EXISTS (SELECT 1 FROM system_alerts WHERE entity_id = ... AND alert_type = ... AND resolved_at IS NULL)` — stejný vzor jako [[Výchovný poradce (VP)]] alerty v původním TRD.

**`entity_id` = `vp_student_care.id`** (UUID castovaný na TEXT) — konzistentní
s konvencí `system_alerts.entity_id TEXT`.

### 49.7 Přechod školního roku — `rollover_vp_care()`

```sql
SELECT rollover_vp_care('2025/2026', '2026/2027');
```

- Pouze role `director` (kontrola přes `auth.uid()`)
- Kopíruje všechny `status = 'active'` záznamy do nového roku
- Lhůty (`spz_valid_until`, `spz_review_due`) se přenáší — jsou nezávislé na školním roce
- `ON CONFLICT (student_id, school_year) DO NOTHING` — bezpečná pro opakované spuštění
- Vrací `copied_count`

### 49.8 RLS — přístupová matice

| Operace | director | [[Výchovný poradce (VP)]] | guide | assistant |
|---------|----------|----|-------|-----------|
| SELECT | ✅ vše | ✅ vše | ✅ přes `can_read_student()` | ✅ přes `can_read_student()` |
| INSERT | ✅ | ✅ | ❌ | ❌ |
| UPDATE | ✅ | ✅ | ❌ | ❌ |
| DELETE | ✅ | ❌ | ❌ | ❌ |

Citlivá pole (`drive_url_private`, `in_private` dokumenty): guide + assistant
vidí `null` — filtrováno v `lib/[[Výchovný poradce (VP)]].ts`, ne v RLS.

### 49.9 Split `lib/[[Výchovný poradce (VP)]].ts` / `lib/[[Výchovný poradce (VP)]]-shared.ts`

Stejný vzor jako `mapa-pokroku.ts` / `mapa-pokroku-shared.ts` (sekce 35.2):

| Soubor | Kde použitelný | Obsah |
|--------|---------------|-------|
| `lib/[[Výchovný poradce (VP)]].ts` | Server Components, Server Actions | Supabase dotazy, `maskSensitiveFields()` |
| `lib/[[Výchovný poradce (VP)]]-shared.ts` | Client i Server | Typy, `DOKUMENT_META`, `filterPrivateDokumenty()`, pure funkce |

### 49.10 Produkční nález: DROP TABLE stub s CASCADE

Starý `vp_student_care` stub měl závislé tabulky (`vp_intervention_log`,
`vp_document`) s FK constraints. `DROP TABLE vp_student_care` bez `CASCADE`
selhal s chybou `2BP01`.

**Pravidlo:** Při zahazování tabulky se závislostmi vždy nejdřív zahodit
závislé tabulky, pak parent — nebo použít `CASCADE` na všech DROP příkazech.

### 49.11 `resolve_vp_alert` — admin klient

`resolveVpAlert()` Server Action používá `createSupabaseAdmin()` pro UPDATE
`system_alerts` — stejný vzor jako `manualMatch` u [[Platby]] (ARCH-NOTES
addendum 2026-05-27 sekce 4). RLS blokuje přímý UPDATE staff rolím.

---

## Aktualizace sekce 1 — RLS hierarchy

Přidat do [[Přehled]] helper funkcí:

```
generate_vp_alerts()     -- SECURITY DEFINER, cron kontext
rollover_vp_care()       -- SECURITY DEFINER, pouze director
```
