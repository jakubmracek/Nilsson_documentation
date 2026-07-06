# ARCH-NOTES — Addendum 2026-06-23

Navazuje na ARCH-NOTES addendum 2026-06-12.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## §63 — ACTIVE_SCHOOL_YEARS: přechodné období zápisů (2026-06-23)

### Kontext

Od okamžiku zápisů nových žáků do konce školního roku nastává přechodné
období, kdy IS musí pracovat se dvěma školními roky současně:
- **Aktuální rok** (`CURRENT_SCHOOL_YEAR`) — stávající třídy v provozu
- **Příští rok** (`NEXT_SCHOOL_YEAR`) — nové třídy připravené pro září

Tento stav nastane každý rok typicky v období únor–srpen.

### Řešení: `ACTIVE_SCHOOL_YEARS` v `lib/config.ts`

```typescript
// lib/config.ts
export const CURRENT_SCHOOL_YEAR = '2025/2026' as const
export const NEXT_SCHOOL_YEAR    = '2026/2027' as const

export const SCHOOL_YEAR_OPTIONS: readonly string[] = [
  '2025/2026',
  '2026/2027',
] as const

// Přechodné období: skupiny viditelné ve výběrech (bulletin, třídní kniha…)
// Od září stačí pouze [CURRENT_SCHOOL_YEAR] — upravit při přechodu roku.
export const ACTIVE_SCHOOL_YEARS: readonly string[] = [
  CURRENT_SCHOOL_YEAR,
  NEXT_SCHOOL_YEAR,
] as const
```

### Dopad na `/api/groups/route.ts`

Výchozí dotaz (bez parametru nebo `?school_year=active`) načítá skupiny
přes `.in('school_year', ACTIVE_SCHOOL_YEARS)`, seřazené `school_year DESC`
(příští rok první). Zpětná kompatibilita zachována:
- `?school_year=current` → jen `CURRENT_SCHOOL_YEAR`
- `?school_year=2025%2F2026` → explicitní rok

### Dopad na UI výběrů skupin

Komponenty zobrazující výběr skupin (bulletin new, bulletin edit) načítají
skupiny bez parametru a zobrazují rok vedle jména skupiny:
- `Beta (2026/2027)`
- `I. (2025/2026)`

### Checklist přechodu školního roku (září)

1. Upravit `lib/config.ts`:
   ```typescript
   export const CURRENT_SCHOOL_YEAR = '2026/2027' as const
   export const NEXT_SCHOOL_YEAR    = '2027/2028' as const
   export const ACTIVE_SCHOOL_YEARS = [CURRENT_SCHOOL_YEAR] as const
   ```
2. `SCHOOL_YEAR_OPTIONS` rozšířit o `'2027/2028'`
3. Ostatní kód se nemění — `ACTIVE_SCHOOL_YEARS` automaticky zúží výběr.

---

## §64 — `bulletin_resolve_recipients`: valid_from nesmí filtrovat budoucí zápisy (2026-06-23)

### Problém

RPC funkce `bulletin_resolve_recipients` obsahovala podmínku:

```sql
AND gm.valid_from <= CURRENT_DATE
```

Tato podmínka způsobovala prázdnou množinu příjemců pro skupiny zapsané
do budoucna (Beta, Gamma s `valid_from = 2026-09-01`).

Symptom: UI zobrazilo skupinu v seznamu, ale příjemci byli prázdní.
RPC vrátila `Success, no rows returned` — bez chyby, pouze prázdný výsledek.

### Příčina

Nové třídy (Beta, Gamma) se vytvářejí před začátkem školního roku —
`valid_from = 2026-09-01`. Podmínka `valid_from <= CURRENT_DATE` je
proto v přechodném období vždy `FALSE` pro tyto záznamy.

### Oprava

Podmínka `valid_from <= CURRENT_DATE` odstraněna z RPC. Zachována pouze
podmínka na `valid_to` (ochrana před historickými členstvími):

```sql
CREATE OR REPLACE FUNCTION bulletin_resolve_recipients(
    p_group_ids             UUID[],
    p_excluded_guardian_ids UUID[],
    p_school_year           TEXT    -- zachován kvůli zpětné kompatibilitě
)
RETURNS TABLE (id UUID, first_name TEXT, last_name TEXT, email TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
    SELECT DISTINCT ON (g.id)
        g.id, g.first_name, g.last_name, g.email
    FROM group_memberships gm
    JOIN student_guardian_links sgl
        ON  sgl.student_id          = gm.student_id
        AND sgl.je_zakonny_zastupce = true
        AND (sgl.platnost_do IS NULL OR sgl.platnost_do >= CURRENT_DATE)
    JOIN guardians g ON g.id = sgl.guardian_id
    WHERE gm.group_id = ANY(p_group_ids)
      AND (gm.valid_to IS NULL OR gm.valid_to >= CURRENT_DATE)
      AND g.id != ANY(p_excluded_guardian_ids)
    ORDER BY g.id;
$$;
```

Parametr `p_school_year` zůstává v signatuře pro zpětnou kompatibilitu
s volajícím kódem, ale v těle funkce se ignoruje — `school_year` je
implicitní v `group_id` (každá skupina patří právě jednomu roku).

### Obecné pravidlo

> **`valid_from` v `group_memberships` nesmí být použit jako filtr
> pro operace pracující s budoucími zápisy** (bulletin, platby, GDPR
> souhlasy, tripartity). Tyto moduly potřebují oslovit rodiče žáků
> připravených pro příští rok stejně jako žáků stávajících.
>
> `valid_from <= CURRENT_DATE` je správný filtr pouze pro dotazy
> zjišťující **aktuální docházku nebo přítomnost** (kdo je dnes ve škole).

### Dotčené moduly — prověřit při rozšiřování

Při přidávání nových modulů pracujících s `group_memberships` ověřit,
zda podmínka `valid_from <= CURRENT_DATE` dává smysl pro daný use case:

| Modul | `valid_from` filtr | Zdůvodnění |
|---|---|---|
| Docházka (kdo je dnes přítomen) | ✅ ano | Chceme jen aktuálně zapsané |
| Bulletin (komu poslat zprávu) | ❌ ne | Chceme i budoucí žáky |
| Platby (komu vystavit pohledávku) | ❌ ne | Chceme i budoucí žáky |
| Tripartity (kdo si může rezervovat) | ❌ ne | Chceme i budoucí žáky |
| GDPR souhlasy (od koho sbírat) | ❌ ne | Chceme i budoucí žáky |
| MŠMT XML (kdo byl žákem v období) | ✅ ano | Historický výkaz |

---

## Aktualizace schématu souborů (§63–§64)

Upravené soubory:

```
lib/config.ts                                    ← přidán ACTIVE_SCHOOL_YEARS
app/api/groups/route.ts                          ← výchozí dotaz přes ACTIVE_SCHOOL_YEARS
app/dashboard/bulletin/new/page.tsx              ← fetch('/api/groups') bez parametru
app/dashboard/bulletin/[id]/edit/page.tsx        ← skupiny s rokem v názvu
```

Upravená DB funkce (Supabase SQL Editor, bez migračního souboru):

```
bulletin_resolve_recipients()                    ← odstraněn valid_from filtr
```

**TODO:** Přidat opravenou verzi `bulletin_resolve_recipients` do nového
migračního souboru (např. `034_bulletin_recipients_fix.sql`) pro
reprodukovatelnost při případném resetování DB.
