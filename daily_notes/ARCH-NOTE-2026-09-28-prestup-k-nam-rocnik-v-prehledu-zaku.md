# ARCH-NOTE: Žák přijatý přestupem se v přehledu žáků ukazoval „Bez ročníku"

**Datum:** 2026-09-28
**Modul:** [[Žáci]] — přehled `/dashboard/zaci`
**Soubory:** `app/dashboard/zaci/page.tsx`
**Commity:** `6dffa89` (fix(zaci): ročník přestupujícího žáka v přehledu /dashboard/zaci)

---

## Přehled

Po dotažení přestupu žáka k nám (zápis → rozhodnutí → propsání do matriky) se nový
žák na `/dashboard/zaci` zobrazoval bez ročníku, přestože se ročník v přestupové
registraci vyplňuje. Data byla v pořádku, chyba byla v tom, jak přehled vybíral
platný matriční záznam. Opraveno jen v UI dotazu, bez migrace.

---

## 1. Ročník přestupujícího žáka v přehledu

**Soubor:** `app/dashboard/zaci/page.tsx` — doplnění `rocnik` do rosteru

### Symptom
Přijatý přestupující žák se v přehledu žáků ocitl ve skupině „Bez ročníku".

### Příčina
Tok dat je správný: ročník z přihlášky (`enrollment_applications.budouci_rocnik`)
propíše migrační RPC (poslední verze v migraci 125) do matriky:

```sql
INSERT INTO student_education_mode (student_id, zpusob, valid_from, created_by, rocnik)
VALUES (v_student_id, '11', v_decision.datum_nastupu, …, v_app.budouci_rocnik);
```

`valid_from` = **datum nástupu**, u přestupu tedy v průběhu školního roku. Přehled
ale četl ročník k jedinému referenčnímu datu — 1. 9. zobrazovaného roku:

```ts
.lte('valid_from', refDate)                          // refDate = RRRR-09-01
.or(`valid_to.is.null,valid_to.gte.${refDate}`)
```

Záznam s `valid_from` např. 2026-10-01 tím vypadl → „Bez ročníku".

### Řešení
Bere se záznam platný **kdykoli během zobrazovaného roku** (1. 9. – 31. 8.):

```ts
.lte('valid_from', yearEnd)                          // (RRRR+1)-08-31
.or(`valid_to.is.null,valid_to.gte.${yearStart}`)    // RRRR-09-01
```

Při více záznamech v roce vyhrává nejnovější (řazení `valid_from DESC` zůstává).
Povýšení na příští rok (`valid_from` = 1. 9. dalšího roku) do přehledu letošního roku
nespadne, takže původní smysl „ne k dnešku, ale pro zobrazovaný rok" (viz
[[ARCH-NOTE-2026-08-14-rocniky-matrika-a-prechod-roku]]) zůstává zachován.

`/dashboard/rocniky` vybírá ročník jinak (nejnovější záznam bez filtru k datu) a CSV
export `/dashboard/zaci/csv` ročník nevypisuje — tuto chybu neměly, nezasahováno.

### Poučení
Verzované matriční záznamy nečíst k jednomu referenčnímu datu (1. 9.), pokud entita
může vzniknout v průběhu období — přestupy, pozdní nástupy. Pro „stav v daném roce"
filtrovat překryv intervalu platnosti s celým rokem a vybrat nejnovější.

---

## Ověření

- `tsc --noEmit` bez chyb v dotčeném souboru.
- V prohlížeči **neověřeno** (produkční data za přihlášením) — ověřit po nasazení, že
  přestupující žák na `/dashboard/zaci` spadne pod správný ročník.

## Související

- [[FIX-zapis-prestup-potvrzeni-prijeti-sql-2026-09-18]] — propsání přestupu do matriky
- [[ARCH-NOTE-2026-09-22-zapis-alert-student-prijat-zrusen]] — migrace 125 (aktuální verze migračního RPC)
- [[ARCH-NOTE-2026-08-14-rocniky-matrika-a-prechod-roku]] — verzování ročníku v `student_education_mode`
