# ARCH-NOTES addendum – `student_guardian_links`

_Datum: 2026-06-02_

## Schéma

| Sloupec | Typ | Poznámka |
|---|---|---|
| `student_id` | UUID FK | odkaz na `students.id` |
| `guardian_id` | UUID FK | odkaz na `guardians.id` |
| `je_zakonny_zastupce` | BOOLEAN | příznak zákonného zástupce; žije na `student_guardian_links`, **ne** na `guardians` |

## Vzorový dotaz – embedded select s FK hintem

Při dotazu přes Supabase JS klienta je nutné použít FK hint `guardian:guardian_id`,
protože název FK sloupce (`guardian_id`) neodpovídá implicitnímu názvu tabulky (`guardians`).

```typescript
const { data, error } = await (supabase as any)
  .from('student_guardian_links')
  .select(`
    guardian:guardian_id (
      id,
      first_name,
      last_name,
      email
    )
  `)
  .eq('student_id', studentId)
  .eq('je_zakonny_zastupce', true)
```

## Pravidla

- Filtr `je_zakonny_zastupce` patří jako `.eq()` na `student_guardian_links` (rodičovský dotaz).
- Supabase REST API **neumí** filtrovat podle sloupců vnořené tabulky přes `.eq()` na rodičovském dotazu – nested select slouží pouze pro výběr sloupců vzdálené tabulky.
- Výsledek mapovat přes `g.guardian` (ne `g.guardians`).

## Kontext

Chyba objevena při implementaci `sendNotifications` v `app/actions/payments.ts`.
Původní kód měl `je_zakonny_zastupce` chybně ve vnořeném selectu na `guardians`,
kde tento sloupec neexistuje.
