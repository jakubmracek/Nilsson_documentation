## Sekce XX — Přechod školního roku (school year rollover)

### Architektonický vzor

Školní rok je v celém systému reprezentován jako `TEXT` ve formátu `'YYYY/YYYY+1'`
(např. `'2025/2026'`). Tabulky `staff_groups` a `group_memberships` mají sloupce
`school_year`, `valid_from`, `valid_to` — což umožňuje souběžnou existenci dat
z více školních roků bez mazání historických záznamů.

### Skupiny (groups)

Každá třída existuje jako samostatný řádek v `groups` pro každý školní rok:

| name | school_year | id |
|------|-------------|-----|
| I.   | 2025/2026   | 3c3363fd-… |
| I.   | 2026/2027   | 0e41e50c-… |

Nové skupiny pro nový školní rok **vytváří ředitel ručně** v Supabase
(nebo přes budoucí admin UI) před spuštěním rollover RPC.

### RPC: new_school_year_rollover

**Soubor:** `migrations/014_school_year_rollover.sql`

Zkopíruje přiřazení průvodců (`staff_groups`) z aktuálního do nového školního roku.
Páruje skupiny přes `groups.name` (např. `'I.'`).

**Spouštět ručně v srpnu**, po vytvoření skupin pro nový rok:

```sql
SELECT new_school_year_rollover('2025/2026', '2026/2027');
```

Vrátí JSON se shrnutím:
```json
{
  "ok": true,
  "new_year": "2026/2027",
  "staff_groups_created": 5,
  "note": "group_memberships (žáci) je třeba zadat ručně přes enrollment workflow"
}
```

**Bezpečnost:** SECURITY DEFINER, pouze `staff.role = 'director'` může spustit.

**Kontrola před spuštěním:** RPC ověří, že pro každou skupinu z aktuálního roku
existuje odpovídající skupina v novém roce — pokud ne, vyhodí chybu se seznamem
chybějících skupin.

### Co rollover NEDĚLÁ (záměrně)

- **group_memberships (žáci)** — enrollment žáků do skupin nového roku
  probíhá separátním workflow (zápisový proces, přestupy). Žáci se
  nepřenášejí automaticky, protože každý rok může dojít ke změnám.
- **Vytváření skupin** — skupiny pro nový rok musí existovat před spuštěním.
- **Uzavření starého roku** — `valid_to` na starých `staff_groups` se nenastavuje
  automaticky; historická data zůstávají přístupná.

### Checklist přechodu školního roku (srpen)

1. Vytvořit nové skupiny v `groups` (name + school_year)
2. Spustit `SELECT new_school_year_rollover('YYYY/YYYY+1', 'YYYY+1/YYYY+2');`
3. Ověřit výsledek (staff_groups_created > 0)
4. Zadat enrollment žáků do nových skupin (`group_memberships`)
5. Ověřit přístup průvodců ve frontendu
