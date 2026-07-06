# TRD — Addendum 2026-06-05

Navazuje na TRD v2.1 + addenda 2026-05-31.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-06-05

- **Modul [[Výchovný poradce (VP)]] — plná implementace:** Migrace 030 + 031 nasazeny.
  Nové schéma `vp_student_care` (zahozeny staré stuby). Aplikační vrstva,
  UI stránky, cron endpoint a GitHub Actions workflow.
  Viz ARCH-NOTES sekce 49.

---

## Náhrada sekce 6 — Modul [[Výchovný poradce (VP)]] (výchovné poradenství)

Původní sekce 6 TRD v2.1 popisovala čtyři tabulky dle vyhlášky č. 72/2005 Sb.
Implementovaný scope je zúžen — viz ARCH-NOTES sekce 49.1.

### 6.1 [[Přehled]]

| Komponenta | Stav |
|------------|------|
| `vp_student_care` (migrace 030) | ✅ Nasazeno |
| RLS politiky (migrace 031) | ✅ Nasazeno |
| `lib/[[Výchovný poradce (VP)]]-shared.ts` | ✅ Nasazeno |
| `lib/[[Výchovný poradce (VP)]].ts` | ✅ Nasazeno |
| `app/actions/[[Výchovný poradce (VP)]].ts` | ✅ Nasazeno |
| `app/api/cron/[[Výchovný poradce (VP)]]-alerts/route.ts` | ✅ Nasazeno |
| `.github/workflows/[[Výchovný poradce (VP)]]-alerts.yml` | ✅ Nasazeno |
| UI stránky (`/[[Přehled]]/[[Výchovný poradce (VP)]]/`) | ✅ Nasazeno |
| `vp_intervention_log` | P2 — Discord export |
| `vp_annual_plan` | Vypuštěno |

### 6.2 Tabulka `vp_student_care`

Viz ARCH-NOTES sekce 49.3 pro úplné schéma. Klíčové vlastnosti:

- UNIQUE `(student_id, school_year)` — jeden záznam per žák per rok
- `typ_pece` — ENUM `typ_vp_pece`: `watch | po_1 | po_2 | po_3 | po_4 | po_5`
- `dokumenty` JSONB — checklist 10 typů dokumentů, každý s `exists`, `valid_until`, `in_private`
- `drive_url_public` + `drive_url_private` — dvě složky na Google Drive
- `status` — `active | closed | transferred`

### 6.3 Schéma souborů

```
supabase/migrations/
├── 030_vp.sql           ← DROP stub tabulek, CREATE vp_student_care,
│                           generate_vp_alerts(), rollover_vp_care()
└── 031_rls_vp.sql       ← RLS politiky (5 politik)

lib/
├── [[Výchovný poradce (VP)]]-shared.ts         ← Shared: typy, DOKUMENT_META, filterPrivateDokumenty()
└── [[Výchovný poradce (VP)]].ts                ← Server-only: dotazy, maskSensitiveFields()

app/
├── actions/[[Výchovný poradce (VP)]].ts        ← Server Actions: createVpCare, updateVpCare,
│                           closeVpCare, resolveVpAlert, rolloverVpCare
├── api/cron/[[Výchovný poradce (VP)]]-alerts/
│   └── route.ts         ← Cron endpoint (CRON_SECRET)
└── [[Přehled]]/[[Výchovný poradce (VP)]]/
    ├── page.tsx          ← Seznam záznamů
    ├── novy/
    │   ├── page.tsx      ← Server wrapper
    │   └── _components/
    │       └── NovyVpForm.tsx
    └── [id]/
        ├── page.tsx      ← Detail záznamu + alerty
        └── _components/
            ├── VpEditForm.tsx
            └── DokumentyChecklist.tsx

.github/workflows/
└── [[Výchovný poradce (VP)]]-alerts.yml        ← GitHub Actions, každé pondělí 5:00 UTC
```

### 6.4 Checklist dokumentů — typy a defaulty

Viz ARCH-NOTES sekce 49.4 pro úplnou tabulku. Citlivé typy
(psychiatrie, psychologie, neurologie, OSPOD) mají `default_private: true`,
ale zadavatel může přepnout per dokument.

### 6.5 Lhůtové alerty

Generovány funkcí `generate_vp_alerts()`, volána týdenně z cronu.
Sdílí `CRON_SECRET` s Fio import cron jobem — žádný nový secret.

Viz ARCH-NOTES sekce 49.6 pro tabulku typů alertů.

[[Přehled]] `alertLabel` a `alertGroupLink` rozšířeny o 6 [[Výchovný poradce (VP)]] typů.
Alerty odkazují na konkrétní záznam (`/[[Přehled]]/[[Výchovný poradce (VP)]]/{id}`) pokud je jen jeden,
jinak na seznam (`/[[Přehled]]/[[Výchovný poradce (VP)]]`).

### 6.6 Přechod školního roku

```typescript
// Server Action — pouze director
const result = await rolloverVpCare('2025/2026', '2026/2027')
// result.count = počet zkopírovaných záznamů
```

Lhůty se přenáší (jsou nezávislé na školním roce).
Záznamy se statusem `closed` nebo `transferred` se nepřenáší.

### 6.7 Přístupová práva

Viz ARCH-NOTES sekce 49.8. Citlivá pole filtrována v aplikační vrstvě
(`lib/[[Výchovný poradce (VP)]].ts`), ne v RLS.

### 6.8 Navigace

`AppNav.tsx` — [[Výchovný poradce (VP)]] položka:
```typescript
{ href: '/[[Přehled]]/[[Výchovný poradce (VP)]]', label: '[[Výchovný poradce (VP)]]', icon: Icons.[[Výchovný poradce (VP)]],
  roles: ['director', '[[Výchovný poradce (VP)]]', 'guide', 'assistant'], bottomNav: false }
```

### 6.9 Otevřené TODO

| Položka | Priorita | Poznámka |
|---------|----------|----------|
| `vp_intervention_log` | P2 | Import z Discord exportů |
| Rollover UI | P2 | Tlačítko v `/[[Přehled]]/nastaveni` |
| [[Rodičovský portál]] — [[Výchovný poradce (VP)]] [[Přehled]] pro rodiče | P3 | Zobrazit typ PO, odkaz na veřejnou složku |

---

## Aktualizace sekce 10.2 — import dat

| Akce | Obsah | Stav |
|------|-------|------|
| `030_vp.sql` | DROP stubů, CREATE `vp_student_care`, funkce | ✅ 2026-06-05 |
| `031_rls_vp.sql` | RLS politiky (5 politik, FORCE RLS) | ✅ 2026-06-05 |

---

## Aktualizace sekce 11 — Rozhodnuté otázky

| # | Otázka | Rozhodnutí | Dopad na TRD |
|---|--------|------------|--------------|
| O19 | Scope [[Výchovný poradce (VP)]] modulu — kolik tabulek? | Jedna tabulka `vp_student_care` + JSONB dokumenty; `vp_intervention_log` P2; `vp_annual_plan` vypuštěno | Sekce 6 přepsána |
| O20 | Dokumenty [[Výchovný poradce (VP)]] — samostatná tabulka nebo JSONB? | JSONB checklist na záznamu péče; 10 pevných typů + „jiné"; `in_private` per položka s defaultem | ARCH-NOTES 49.4 |
| O21 | Citlivá pole — RLS nebo aplikační vrstva? | Aplikační vrstva (`maskSensitiveFields` v `lib/[[Výchovný poradce (VP)]].ts`); RLS řeší přístup k řádkům | ARCH-NOTES 49.5 |
| O22 | [[Výchovný poradce (VP)]] alerty — cron nebo on-demand? | Cron (GitHub Actions), týdně v pondělí; sdílí `CRON_SECRET` | ARCH-NOTES 49.6 |
