# TRD — Addendum 2026-05-31

Navazuje na TRD v2.1 + addenda 2026-05-27.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-05-31

- **[[Třídní kniha]] — editace záznamu:** přechod na Server Component wrapper + Client EditForm.
  Viz ARCH-NOTES sekce 45.1.
- **SVP editační stránka:** nová plná implementace (stub nahrazen).
  Viz ARCH-NOTES sekce 45.2.
- **`group_id` povinný:** 9 historických záznamů doplněno; formulář nového záznamu
  rozšířen o výběr třídy. Viz ARCH-NOTES sekce 45.3.
- **UNIQUE constraint `(datum, group_id)`:** přidán na `tridni_kniha_zaznamy`.
  Viz ARCH-NOTES sekce 45.4.
- **Favicon + title:** logo opice, „IS Nilsson", `lang="cs"`. Viz ARCH-NOTES sekce 45.5.
- **Alert nedoplněná [[Třídní kniha]]:** nový alert v dashboardu + stránka chybějících dní.
  Viz ARCH-NOTES sekce 46.
- **`school_holidays` (migrace 026):** tabulka prázdnin a svátků pro 2025/2026 a 2026/2027.
  Viz ARCH-NOTES sekce 47.

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
└── 026_school_holidays.sql     ← tabulka school_holidays + data 2025/2026 + 2026/2027
```

Do `lib/` přidat/upravit:

```
├── tridni-kniha-missing.ts     ← getMissingTKDays(schoolYear, existujiciDny, holidayDays)
│                                  formatDateCZ(dateStr)
```

Do `app/[[Přehled]]/tridni-kniha/` přidat:

```
├── [id]/
│   ├── upravit/
│   │   ├── page.tsx            ← Server Component wrapper (bylo: Client Component)
│   │   └── _components/
│   │       └── EditForm.tsx    ← Client Component; editační formulář
│   └── svp/
│       ├── page.tsx            ← Server Component (bylo: stub)
│       └── _components/
│           └── SvpEditForm.tsx ← Client Component; toggle vazeb
└── chybejici/
    └── page.tsx                ← Server Component; seznam dní bez záznamu
```

Do `app/[[Přehled]]/tridni-kniha/novy/` přidat:

```
├── page.tsx                    ← Server Component wrapper (bylo: Client Component)
└── _components/
    └── NovyZaznamForm.tsx      ← Client Component; formulář s výběrem skupiny
```

Upravit:

```
app/page.tsx                    ← zredukován na redirect('/[[Přehled]]')
app/icon.svg                    ← favicon (nový; nahrazuje favicon.ico)
```

---

## Aktualizace sekce 4 — [[Třídní kniha]]

### Nová sekce 5.13 — `school_holidays`

```sql
CREATE TABLE school_holidays (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  datum       DATE NOT NULL UNIQUE,
  nazev       TEXT NOT NULL,
  typ         TEXT NOT NULL CHECK (typ IN ('statni_svatek', 'skolni_prazdniny', 'reditelske_volno')),
  school_year TEXT NOT NULL
);
```

Použití: výpočet chybějících dní [[Třídní kniha]] (`getMissingTKDays`), budoucí
využití v docházkových výkazech a MŠMT XML.

Správa: director edituje přímo v DB. Při přechodu školního roku vložit nové řádky.

### Aktualizace sekce 5.2 — `tridni_kniha_zaznamy`

Přidat constraint:

```sql
ALTER TABLE tridni_kniha_zaznamy
  ADD CONSTRAINT tridni_kniha_zaznamy_datum_group_unique
  UNIQUE (datum, group_id);
```

**Sémantika:** jeden záznam per (datum, třída). Pokus o duplicitu vrací chybu `23505`
→ aplikační vrstva zobrazí „Pro tento den již záznam v [[Třídní kniha]] existuje."

**`group_id` povinný od 2025/2026:** všechny záznamy musí mít `group_id`. Záznamy
bez `group_id` jsou chybou dat, ne školní záznam. UI formulář vždy vyžaduje výběr třídy.

### Aktualizace sekce 5 — formulář nového záznamu

`app/[[Přehled]]/tridni-kniha/novy/page.tsx` je Server Component wrapper — načte
skupiny pro `CURRENT_SCHOOL_YEAR` z DB a předá do `NovyZaznamForm` (Client Component).

`NovyZaznamForm` podporuje předvyplnění z URL parametrů:
- `?datum=YYYY-MM-DD` — předvyplní datum
- `?group_id=UUID` — předvyplní třídu

Použití: proklik z `/[[Přehled]]/tridni-kniha/chybejici` → formulář s předvyplněným
datem a třídou.

---

## Aktualizace sekce 7 — [[Přehled]]

### Nová sekce 7.8 — Alert: Nedoplněná [[Třídní kniha]]

Aplikační alert (ne `system_alerts`) — generován při každém načtení dashboardu.

**Logika:** pracovní dny (Po–Pá) od 1. 9. školního roku do včerejška, pro které
neexistuje záznam v `tridni_kniha_zaznamy` pro danou skupinu, s vyloučením
dní ze `school_holidays`.

**UI:** řádek „Nedoplněná [[Třídní kniha]] N×" v AlertsWidget, proklik na
`/[[Přehled]]/tridni-kniha/chybejici`.

**Stránka `/chybejici`:** seznam dní per třída. Každý den má tlačítko „Doplnit"
→ proklik na formulář nového záznamu s předvyplněným datem a třídou.

---

## Aktualizace sekce 10.2 — import dat

| Akce | Obsah | Stav |
|------|-------|------|
| `026_school_holidays.sql` | Tabulka + data svátků a prázdnin 2025/2026 a 2026/2027 | ✅ 2026-05-31 |
| UPDATE `group_id` | 9 záznamů 2025/2026 bez `group_id` doplněno na skupinu I. | ✅ 2026-05-31 |
| ALTER TABLE | UNIQUE constraint `(datum, group_id)` přidán | ✅ 2026-05-31 |

---

## Aktualizace sekce 11 — Rozhodnuté otázky

| # | Otázka | Rozhodnutí | Dopad na TRD |
|---|--------|------------|--------------|
| O16 | `group_id` v záznamu [[Třídní kniha]] — povinný? | Ano, od 2025/2026. UI vždy vyžaduje výběr třídy. | Sekce 5.2, 5.13; formulář nový |
| O17 | Duplicitní záznamy pro stejný den a třídu | UNIQUE constraint na `(datum, group_id)`; chyba `23505` → srozumitelná hláška | Sekce 5.2 |
| O18 | Státní svátky a prázdniny — kde uchovávat? | Tabulka `school_holidays` v DB; správa ředitelem | Sekce 5.13; migrace 026 |
