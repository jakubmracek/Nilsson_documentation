# ARCH-NOTES addendum — session 2026-05-12
# Integrovat do ARCH-NOTES-v1.8 jako sekce 21+

---

## Sekce 21 — Karta žáka (Fáze 5)

### 21.1 Nové soubory
- `app/dashboard/zaci/page.tsx` — seznam žáků, RPC `get_students_in_school_year`
- `app/dashboard/zaci/[id]/page.tsx` — karta žáka (Server Component)

### 21.2 Datový model karty žáka
Karta fetchuje 6 sekcí sekvenčně (ne paralelně — RLS závislosti):
1. `students` — základní data
2. `group_memberships` + `groups(name)` — skupinová příslušnost, historie
3. `student_guardian_links` + `guardians` — zákonní zástupci
4. `bozp_zaznamy` → `bozp_attendance` — BOZP status (dvoustupňový dotaz)
5. `semester_attendance_summary` — souhrn docházky
6. `system_alerts` WHERE module='vp' — VP alerty (pouze director/vp)

### 21.3 Klíčové vzory
- `group_memberships`: filtrovat POUZE přes `school_year`, NE přes `valid_to IS NULL`
  (produkční konvence: `valid_to = '2026-08-31'` pro aktivní záznamy)
- `guardian_links`: `platnost_do IS NULL` = stále platné
- `activeSchoolYear` se bere z nejnovějšího membershipu (valid_from DESC)
- Odkaz na třídní knihu předává `?group_id=<uuid>` — filtr implementován v tridni-kniha/page.tsx

### 21.4 RPC get_students_in_school_year — TODO ověřit sloupce
Používá se na: dashboard widget, zaci/page.tsx
Vrací (dle migrace 017): `id, first_name, last_name, kod_zaka, status`
TODO: ověřit zda vrací i `group_name` — pokud ano, zobrazit badge skupiny v seznamu

---

## Sekce 22 — TypeScript stub database.ts

### 22.1 Situace
`types/database.ts` obsahuje pouze stub (plné typy nebyly vygenerovány):
```typescript
export type Database = {
  public: {
    Tables: Record<string, any>
    Views: Record<string, any>
    Functions: Record<string, any>
    Enums: Record<string, any>
  }
}
```

### 22.2 Důsledky
Supabase klient vrací `SelectQueryError<"Invalid Relationships...">` místo skutečných typů
pro všechny dotazy s joiny nebo `.single()`. Workaround: `(data as any)` nebo `(data as any[])`.

### 22.3 Vzory workaroundu
```typescript
// Staff role
const { data: staffRaw } = await supabase.from('staff').select('id, role').eq(...).single()
const staff = staffRaw as any
const role = staff.role

// Array výsledky
const { data } = await supabase.from('...').select('...')
const items = (data as any[]) ?? []

// Joinované tabulky
const currentMembership = (memberships as any[])?.[0] ?? null
const groupName = currentMembership?.groups?.name
```

### 22.4 TODO — vygenerovat skutečné typy
```powershell
npx supabase gen types typescript --project-id <project-id> > types/database.ts
```
Po vygenerování odstranit všechny `as any` casty (systematicky přes grep).

---

## Sekce 23 — Next.js 15+ params jako Promise

### 23.1 Problém
V Next.js 15+ jsou `params` v Server Components typovány jako `Promise<{ id: string }>`.
Bez `await` je `params.id === undefined` → dotaz nenajde záznam → `notFound()` → 404.

### 23.2 Správný vzor
```typescript
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>   // Promise, ne { id: string }
}) {
  const { id } = await params        // await povinný
  // ...
}
```

### 23.3 Opravené soubory
- `app/dashboard/zaci/[id]/page.tsx`
- `app/dashboard/tridni-kniha/[id]/page.tsx`
- `app/dashboard/bozp/[id]/page.tsx`
- `app/dashboard/tridni-kniha/[id]/svp/page.tsx` (Client Component — params přímo)
- `app/dashboard/tridni-kniha/[id]/upravit/page.tsx` (Client Component — params přímo)

---

## Sekce 24 — PowerShell encoding

### 24.1 Pravidlo
`Set-Content` bez `-Encoding UTF8` zapíše Windows-1250 → Turbopack/Next.js spadne:
```
invalid utf-8 sequence of 1 bytes from index N
```

### 24.2 Správný vzor
```powershell
... | Set-Content -LiteralPath "soubor.tsx" -Encoding UTF8
```

### 24.3 Bezpečná alternativa pro čisté přepsání souboru
Stáhnout soubor z Claude jako artifact → zkopírovat přes `Copy-Item`:
```powershell
Copy-Item -LiteralPath "downloaded.tsx" -Destination "app/dashboard/.../page.tsx"
```
`Copy-Item` zachová encoding originálu (UTF-8).
