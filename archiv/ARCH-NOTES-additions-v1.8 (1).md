# ARCH-NOTES — nové sekce pro v1.8
#
# Instrukce:
#   1. V záhlaví souboru změň: Verze: 1.7 → 1.8 | Datum: 2026-05-08 → 2026-05-09
#                              Navazuje na TRD v1.8 → TRD v1.9
#   2. Přidej obě sekce níže na konec dokumentu (za sekci 18).
#
# ─────────────────────────────────────────────────────────────────────────────

---

## 19. Přechod školního roku (school year rollover)

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
2. Spustit `SELECT new_school_year_rollover('2025/2026', '2026/2027');`
3. Ověřit výsledek (staff_groups_created > 0)
4. Zadat enrollment žáků do nových skupin (`group_memberships`)
5. Ověřit přístup průvodců ve frontendu

---

## 20. BOZP modul — implementační poznámky (migrace 015, 2026-05-09)

### RLS strategie

BOZP data nejsou citlivá — přístupová logika je proto záměrně jednodušší
než u VP modulu. Klíčová rozhodnutí:

| Operace | Kdo | Zdůvodnění |
|---------|-----|------------|
| SELECT bozp_zaznamy | všichni staff | Není citlivé; průvodce potřebuje přehled i napříč skupinami |
| SELECT bozp_attendance | všichni staff | Dtto |
| INSERT bozp_zaznamy | director, vp, guide | Guide spravuje BOZP pro svoji skupinu |
| INSERT bozp_attendance | director, vp, guide + `can_read_student()` | Pojistka: guide nemůže přidat cizího žáka |
| UPDATE bozp_zaznamy | director, vp | Oprava popisů po vytvoření |
| DELETE | director (záznamy), director+vp (attendance) | Oprava chyb; záznam se nemažu routinně |

**Důležité:** `can_read_student()` má parametr pojmenovaný `p_student_id uuid`.
Při použití ve WITH CHECK podmínce politiky musí být předán kvalifikovaný sloupec:

```sql
-- SPRÁVNĚ (bez ambiguity):
AND can_read_student(bozp_attendance.student_id)

-- ŠPATNĚ (způsobí syntax error v PostgreSQL):
AND can_read_student(student_id)   -- nelze začínat podmínku WITH CHECK
```

Chyba `42601: syntax error at or near "AND"` nastane pokud první výraz ve
`WITH CHECK` není booleovský — `current_staff_role() IN (...)` musí předcházet `AND`.

### DB funkce `get_students_without_bozp(p_school_year TEXT)`

Klíčový dotaz z TRD sekce 5.8 implementován jako SECURITY DEFINER RPC.
SECURITY DEFINER je zde záměrný: guide by přes RLS viděl jen žáky své skupiny,
ale ředitel potřebuje vidět všechny bez BOZP bez ohledu na skupinu.

```sql
-- Ověření po nasazení:
SELECT * FROM get_students_without_bozp('2025/2026');
-- Při prázdné bozp_attendance: vrátí všech 32 aktivních žáků
```

### UI architektura

```
app/dashboard/bozp/
├── page.tsx                        ← Server Component; seznam + alert widget
├── novy/page.tsx                   ← Server Component; fetch dat → předá do Client
└── [id]/page.tsx                   ← Server Component; detail + inline Server Action pro odebrání
    _components/
    ├── NovyBozpForm.tsx            ← Client Component ('use client'); interaktivní checklist
    └── AddStudentToRecord.tsx      ← Client Component; přidání žáka k existujícímu záznamu
```

**Vzor: Server Component jako data wrapper pro Client Component**

`novy/page.tsx` (Server) fetchuje seznam žáků + žáky bez BOZP, pak předá jako
`props` do `NovyBozpForm` (Client). Client Component tak nemusí fetchovat data
sám (žádný `useEffect` + API call) — dostane je hydratovaně při SSR.

`preselectedIds` logika: pokud všichni žáci nemají BOZP → předvyber všechny
(začátek roku); pokud jen někteří → předvyber jen ty (individuální doplnění).

**Inline Server Action pro odebrání žáka:**

```tsx
// V Server Componentě (detail page) — bez samostatného Client Componentu:
<form action={async () => {
  'use server'
  await removeStudentFromBozp(params.id, row.student_id)
}}>
  <button type="submit">✕</button>
</form>
```

Tento vzor (inline `'use server'` v JSX) funguje pouze v Server Componentách —
v Client Componentách by způsobil runtime chybu.

### Server Actions — návratový vzor

BOZP actions nepoužívají `redirect()` uvnitř action. Místo toho vrátí
`{ success: true, id }` nebo `{ success: false, error }` a redirect
provede Client Component přes `router.push()`. Důvod: zachycení chyb
v Client Componentě při volání Server Action je čistší bez nutnosti
rozlišovat `isRedirectError`.

```typescript
// Action:
export async function createBozpZaznam(formData: FormData): Promise<BozpActionResult>

// Client Component:
const result = await createBozpZaznam(formData)
if (result.success) router.push(`/dashboard/bozp/${result.id}`)
else setError(result.error)
```
