# ARCH-NOTES — Addendum 2026-06-07

Navazuje na ARCH-NOTES addendum 2026-06-05.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 55. Opravy přístupových práv — asistentka a adresy ZZ (2026-06-07)

### 55.1 Omluvenky — přidání role `assistant`

**Problém:** Asistentka (`role = 'assistant'`) nemohla zadávat omluvenky přes
`/dashboard/omluvenky/novy`. Blokovala ji dvě nezávislá místa:

1. **Server Action guard** v `app/actions/omluvenky.ts` — explicitní whitelist
   neobsahoval `'assistant'`
2. **RLS politika** `staff_absence_requests_insert` — ARRAY podmínka neobsahovala
   `'assistant'::staff_role`

**Oprava 1 — Server Action** (`app/actions/omluvenky.ts`):

```typescript
// BYLO:
if (!['director', 'vp', 'guide'].includes(staff.role)) {

// OPRAVENO NA:
if (!['director', 'vp', 'guide', 'assistant'].includes(staff.role)) {
```

**Oprava 2 — RLS politika** (spuštěno v Supabase SQL Editoru):

```sql
DROP POLICY IF EXISTS "staff_absence_requests_insert" ON absence_requests;

CREATE POLICY "staff_absence_requests_insert" ON absence_requests
  FOR INSERT
  WITH CHECK (
    (current_staff_id() IS NOT NULL)
    AND can_read_student(student_id)
    AND (current_staff_role() = ANY (ARRAY[
      'director'::staff_role,
      'vp'::staff_role,
      'guide'::staff_role,
      'assistant'::staff_role
    ]))
  );
```

**Poznámka k ostatním politikám:** `ar_select` již roli `assistant` obsahoval
(průvodce a asistentka vidí omluvenky žáků své skupiny). `ar_update` asistentku
neobsahuje záměrně — schvalování omluvenek asistentce nepřísluší.

**Ověření po nasazení:**

```sql
SELECT policyname, with_check
FROM pg_policies
WHERE tablename = 'absence_requests'
  AND policyname = 'staff_absence_requests_insert';
-- Očekáváno: with_check obsahuje 'assistant'::staff_role
```

### 55.2 Adresy zákonných zástupců — zobrazení na kartě žáka

**Problém:** Průvodkyně a VP neviděly adresy ZZ na kartě žáka
(`/dashboard/zaci/[id]`).

**Diagnostika:**
- RLS na `guardians` průvodkyni neblokuje — impersonační test potvrdil plný
  přístup k adresním sloupcům
- Adresy nejsou na tabulce `students` (jak předpokládal TRD) — jsou výhradně
  na tabulce `guardians`
- Příčina: chybějící sloupce v PostgREST embedded selectu a absence JSX renderování

**Oprava** (`app/dashboard/zaci/[id]/page.tsx`):

```typescript
// BYLO — select bez adresních sloupců:
guardians(first_name, last_name, email, phone_primary, phone_secondary)

// OPRAVENO NA:
guardians(first_name, last_name, email, phone_primary, phone_secondary,
          address_street, address_city, address_zip)
```

```tsx
// PŘIDÁNO do JSX sekce zákonných zástupců (za phone_secondary):
{(g?.address_street || g?.address_city) && (
  <span className="block text-gray-400 text-xs mt-1">
    {[g.address_street, g.address_city, g.address_zip].filter(Boolean).join(", ")}
  </span>
)}
```

**Poznámka k datovému modelu:** Sloupce `address_street`, `address_city`,
`address_zip`, `address_country`, `address_delivery` jsou na tabulce `guardians`,
nikoliv na `students`. TRD v2.1 sekce 3.4 uvádí adresní sloupce na `students` —
toto odpovídá původnímu návrhu, ale reálná DB se vyvinula jinak. TRD je třeba
opravit (viz TRD addendum níže).

**Žádná RLS změna nebyla potřeba.**

---

## Obecné pravidlo (aktualizace)

Při rozšiřování přístupových práv role zkontrolovat **vždy obě místa**:
1. Guard v Server Action (`staff.role` whitelist)
2. RLS politika (`current_staff_role() = ANY (ARRAY[...])`)

Obě místa musí být konzistentní. Nesoulad způsobí, že buď:
- Action selže na aplikační vrstvě (guard) dříve než se dotaz vůbec odešle
- Nebo RLS zamítne INSERT i když action guard prošel
