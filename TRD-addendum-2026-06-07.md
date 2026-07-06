# TRD — Addendum 2026-06-07

Navazuje na TRD addendum 2026-06-05.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## Changelog 2026-06-07

- **Omluvenky — role `assistant`:** asistentka může nyní zadávat omluvenky.
  Opravena RLS politika i Server Action guard. Viz ARCH-NOTES sekce 55.1.
- **Adresy ZZ na kartě žáka:** průvodkyně a VP nyní vidí adresy zákonných
  zástupců. Čistě UI oprava — žádná RLS změna. Viz ARCH-NOTES sekce 55.2.
- **Korekce TRD:** adresní sloupce jsou na `guardians`, nikoliv `students`.
  Viz aktualizace sekce 3.4 níže.

---

## Aktualizace sekce 4.4 — Omluvenky: matice přístupů

Aktualizovat tabulku RLS politik:

| Politika | Role | Operace |
|----------|------|---------|
| `staff_absence_requests_select` | staff přes `can_read_student` | SELECT |
| `guardian_absence_requests_select` | guardian (vlastní omluvenky) | SELECT |
| `staff_absence_requests_insert` | director / vp / guide / **assistant** | INSERT |
| `guardian_absence_requests_insert` | guardian (vlastní dítě) | INSERT |
| `staff_absence_requests_update` | director / vp / guide | UPDATE (schválení) |
| — | guardian | UPDATE zakázán |
| — | **assistant** | UPDATE záměrně zakázán |

**Zdůvodnění:** Asistentka může omluvenku zadat (je přítomna při komunikaci
s rodiči), ale nemůže ji schvalovat — to přísluší průvodci nebo vedení.

Aktualizovat také Server Action guard v `app/actions/omluvenky.ts`:

```typescript
// Aktuální stav po opravě:
if (!['director', 'vp', 'guide', 'assistant'].includes(staff.role)) {
  return { success: false, error: 'Nemáte oprávnění zadávat omluvenky.' }
}
```

---

## Aktualizace sekce 3.4 — Tabulka `students`: korekce adresních sloupců

**Korekce:** Původní TRD (sekce 3.4) uvádí adresní sloupce (`address_street`,
`address_city`, `address_zip`, `address_country`) na tabulce `students`.
Reálná DB tyto sloupce na `students` **nemá** — jsou výhradně na `guardians`.

**Skutečné schéma `guardians`** (relevantní sloupce):

```
address_street    TEXT
address_city      TEXT
address_zip       TEXT
address_country   TEXT
address_delivery  TEXT    ← doručovací adresa (navíc oproti TRD)
```

**Skutečné schéma `students`** neobsahuje žádné `address_*` sloupce.
Obsahuje místo toho: `obec_bydliste_kod`, `okres_bydliste_kod` (kódy pro
MŠMT výkazy), nikoliv volný text adresy.

**Dopad:** Kdykoli je v kódu potřeba adresa žáka, je třeba jít přes
`student_guardian_links → guardians.address_*`. Přímý dotaz na
`students.address_street` způsobí chybu `42703: column does not exist`.

---

## Aktualizace sekce 7 — Karta žáka: sekce Zákonní zástupci

Aktualizovat popis sekce — přidat adresu do zobrazovaných dat:

| Zobrazované pole | Zdroj |
|-----------------|-------|
| Jméno a příjmení | `guardians.first_name`, `last_name` |
| Role a příznaky | `student_guardian_links.role`, `je_zakonny_zastupce`, `je_primarni_kontakt` |
| Email | `guardians.email` |
| Telefon primární | `guardians.phone_primary` |
| Telefon sekundární | `guardians.phone_secondary` |
| **Adresa** | `guardians.address_street`, `address_city`, `address_zip` — **přidáno 2026-06-07** |

---

## Aktualizace sekce 10.2 — import dat

| Akce | Obsah | Stav |
|------|-------|------|
| Oprava RLS `staff_absence_requests_insert` | Přidána role `assistant` | ✅ 2026-06-07 |
| Oprava Server Action guard `createOmluvenka` | Přidána role `assistant` | ✅ 2026-06-07 |
| Oprava UI karty žáka | Adresy ZZ zobrazeny v sekci Zákonní zástupci | ✅ 2026-06-07 |

---

## Aktualizace sekce 11 — Rozhodnuté otázky

| # | Otázka | Rozhodnutí | Dopad na TRD |
|---|--------|------------|--------------|
| O19 | Může asistentka zadávat omluvenky? | Ano — stejná práva jako průvodce pro INSERT; schvalování (UPDATE) zůstává director/vp/guide | Sekce 4.4 aktualizována |
| O20 | Kde jsou uloženy adresy žáků/ZZ? | Na `guardians`, nikoliv `students` — TRD sekce 3.4 byla chybná | Sekce 3.4 opravena |
