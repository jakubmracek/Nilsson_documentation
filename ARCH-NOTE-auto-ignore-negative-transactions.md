# ARCH-NOTE: Auto-ignore záporných transakcí

**Datum:** 2026-06-24  
**Modul:** Platby — `payment_transactions`  
**Soubory:** `app/actions/payments.ts`, `app/dashboard/platby/page.tsx`

---

## Kontext

Fio API importuje všechny pohyby na účtu, včetně odchozích (záporný `amount`):
bankovní poplatky, vrácení dotací, odchozí převody apod. Tyto transakce
nikdy neodpovídají pohledávkám žáků a zbytečně znečišťují seznam nespárovaných.

## Řešení

Server action `autoIgnoreNegativeTransactions` označí všechny záporné
nespárované transakce příznakem `ignored = true`.

**Podmínky filtru (kumulativní):**

| Sloupec        | Podmínka      | Důvod                                              |
|----------------|---------------|----------------------------------------------------|
| `amount`       | `< 0`         | záporný obrat = odchozí platba                     |
| `ignored`      | `= false`     | idempotence — neopakujeme již ignorované            |
| `match_status` | `= unmatched` | spárované záporné transakce necháváme na manuální řešení |

## Kde volat

Po každém Fio importu, na konci importního pipeline — až po `insert` nových
řádků do `payment_transactions`. Alternativně lze podmínku `ignored: amount < 0`
přidat přímo do `insert` řádku v importním kódu (čistší, TODO).

## Co se nestane

- Spárované záporné transakce (edge case) **nejsou** dotčeny — vyžadují
  manuální posouzení.
- Fyzické mazání neproběhne — `ignored = true` je soft flag, řádek zůstává
  v DB pro auditní stopu a ochranu před re-importem.
- Ignorované transakce lze obnovit přes `restoreTransaction` (nebo
  `?zobrazit=vse` v UI).

## Související

- Migration 024 — sloupec `ignored` na `payment_transactions`
- `ignoreTransaction` / `restoreTransaction` — manuální varianta téhož
- `?zobrazit=vse` — URL param pro zobrazení ignorovaných v `/transakce`
