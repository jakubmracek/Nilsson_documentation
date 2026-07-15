# ARCH-NOTES — Addendum 2026-07-10

**Kontext:** Debugging modulu Školní družina — `payment_obligations` FK, přehlcení
overloadu helperu, zobrazení družinových pohledávek v modulu Platby, přepínač
školního roku, a drift typových souborů blokující build.

> Číslování sekcí níže je lokální (1–8). Při zařazení do hlavních ARCH-NOTES
> přiřaď §-čísla dle konvence (pozor na dosud nevyřešený konflikt §92–§98).

---

## 1. `payment_obligations.created_by` → `auth.users(id)`, NIKOLIV `staff(id)`

**Kanonická konvence:** `created_by` v `payment_obligations` odkazuje na
`auth.users(id)`. Celý Platební modul plní `created_by = auth.uid()`.
Ověřeno na živých datech: **116 ze 116** existujících pohledávek matchuje
`auth.users`, 0 matchuje `staff`.

**Schema drift (k dořešení, viz §7):** zdrojová migrace
`20260428000003_payments.sql` definuje `created_by ... REFERENCES staff(id)`,
ale **živá DB má `REFERENCES auth.users(id)`**. `types.ts`/`supabase.ts` navíc
tvrdily `staff` — proto při debuggingu **nevěř typům ani migraci, ale ptej se
přímo DB**:

```sql
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'payment_obligations_created_by_fkey';
```

**Rozhodovací dotaz** (kterou konvenci brát za kanonickou při sporu migrace vs.
realita — vždy vyhrává to, co drží existující data):

```sql
SELECT
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staff s      WHERE s.id = po.created_by)) AS matchuje_staff,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM auth.users u WHERE u.id = po.created_by)) AS matchuje_auth,
  count(*) AS celkem
FROM payment_obligations po
WHERE po.created_by IS NOT NULL;
```

---

## 2. Overload trap: `druzina_vytvorit_pohledavku` — dvě přetížení

**Problém:** helper existoval ve dvou přetíženích:

- `druzina_vytvorit_pohledavku(uuid, text)` — bral `created_by` z `auth.uid()`.
  **NIKDO NEVOLAL** (mrtvý kód).
- `druzina_vytvorit_pohledavku(uuid, text, uuid)` — reálně volaný z
  `druzina_prihlaska_rozhodnout`, bral `created_by` z 3. parametru.

Migrace **059** omylem opravila dvouargumentovou (nevolanou) verzi → fix se
navenek neprojevil. Skutečná oprava je v migraci **060** na tříargumentové verzi.

**Lekce:** než opravíš „sdílený helper symetrický s ruční enrollment cestou",
ověř, **KTERÉ přetížení volající reálně používá**:

```sql
SELECT oid::regprocedure AS signatura, pronargs
FROM pg_proc WHERE proname = '<helper>' ORDER BY pronargs;
```

**Úklid (proveden):** mrtvá dvouargumentová verze dropnuta —
`DROP FUNCTION IF EXISTS druzina_vytvorit_pohledavku(uuid, text);`
(explicitní signatura cílí přesně jedno přetížení).

---

## 3. `decided_by` (staff.id) vs `created_by` (auth.users.id) — různé cíle FK

Konceptuálně podobné „kdo to udělal", ale **různé FK cíle**:

| Sloupec                              | Odkazuje na       | Zdroj hodnoty            |
| ------------------------------------ | ----------------- | ------------------------ |
| `druzina_prihlasky.decided_by`       | `staff(id)`       | `p_decided_by` (frontend posílá `staff.id`) |
| `druzina_enrollments.enrolled_by`    | `staff(id)`       | `p_decided_by`           |
| `payment_obligations.created_by`     | `auth.users(id)`  | **musí se přeložit** ze `staff.id` |

Frontend (`app/actions/druzina-prihlasky.ts`) posílá do RPC
`p_decided_by = staffId` (= `staff.id`). To je správně pro `decided_by`/`enrolled_by`,
ale **pro `created_by` je nutný překlad** `staff.id → staff.user_id`:

```sql
-- uvnitř druzina_vytvorit_pohledavku(uuid, text, uuid) — migrace 060
SELECT user_id INTO v_created_by FROM staff WHERE id = p_created_by;
IF v_created_by IS NULL THEN
  RAISE EXCEPTION '... staff.id % nemá odpovídající user_id', p_created_by;
END IF;
-- ... INSERT ... created_by = v_created_by
```

Rozhraní helperu (`uuid, text, uuid`) zůstalo beze změny → frontend ani
`druzina_prihlaska_rozhodnout` se nemusely upravovat.

---

## 4. `ObligationType` je hardcoded na ~5+ místech — přidání typu = touch všech

Union `'lunch' | 'event' | 'tuition'` byl zkopírovaný (žádný sdílený zdroj) v:

- `app/actions/payments.ts`
- `payments.ts` (druhá kopie — ověřit, jestli živá)
- `app/dashboard/platby/pohledavky/page.tsx`
- `app/dashboard/platby/pohledavky/[id]/page.tsx`
- (import do `NovaPohledavkaForm.tsx`)

Chybějící `'druzina'` způsobil: neviditelnost v UI, **pád `TypeBadge`** na
neznámém typu (`map[type]` → undefined → čtení `.className`), chybějící filtr, a
**špatný SS prefix** (`generateSsKod` fallback `'20'` místo `'30'`).

**Provedené opravy:**
- `'druzina'` doplněn do všech unionů
- `TypeBadge` má nyní fallback `?? { label: type, className: 'bg-stone-100 …' }`
  → neznámý typ už render neshodí
- filtr „Družina" v `FilterBar`
- `generateSsKod`: explicitní větev `type === 'druzina' ? '30'`
- `'druzina'` **NENÍ** v dropdownu `NovaPohledavkaForm` (záměrně — družina vzniká
  jen automaticky přes schválení přihlášky, 1000 Kč pevně)

**TODO (viz §7):** centralizovat `ObligationType` + label + SS-prefix do
`lib/config.ts` jako jediný zdroj:

```typescript
export const OBLIGATION_TYPES = {
  lunch:   { label: 'Obědy',         ssPrefix: '10' },
  tuition: { label: 'Školné',        ssPrefix: '70' },
  event:   { label: 'Výjezdní akce', ssPrefix: '20' },
  druzina: { label: 'Družina',       ssPrefix: '30' },
} as const
export type ObligationType = keyof typeof OBLIGATION_TYPES
```

**SS prefix schéma (canonical):** `10`=lunch, `70`=tuition, `20`=event/donation,
`30`=druzina.

---

## 5. Přepínač školního roku v seznamu pohledávek

**Problém:** `fetchObligations` filtroval `.eq('school_year', CURRENT_SCHOOL_YEAR)`
natvrdo. Družinové pohledávky jsou na `2026/2027` (jednorázový poplatek na příští
rok), ale `CURRENT_SCHOOL_YEAR` je `2025/2026` → pohledávky z dotazu vypadly a
v UI nebyly (žádný pád — prostě se nenačetly).

**Řešení (nedestruktivní):** do `page.tsx` přidán přepínač roku ve `FilterBar`,
místo hýbání globálním `CURRENT_SCHOOL_YEAR`:

- `Filters` rozšířen o `school_year` (default `CURRENT_SCHOOL_YEAR`, přepis přes
  `?school_year=`)
- `fetchObligations` filtruje `filters.school_year`
- nová `fetchAvailableSchoolYears()` (distinct roky z pohledávek + vždy aktuální)
- `fetchAvailableMonths(schoolYear)` bere rok parametrem
- řádek „Rok" v `FilterBar` (zobrazí se při `years.length > 1`); přepnutí roku
  resetuje filtr měsíce

**Vzor pro přechodné období (červenec–srpen):** kdy legitimně žiješ ve dvou
školních letech současně (dobíhá starý, plní se nový), je přepínač roku ve filtru
lepší než globální přepnutí configu — globální přepnutí `CURRENT_SCHOOL_YEAR`
skryje věci z dobíhajícího roku ve všech modulech. Config překlop až škola fakticky
přejde do nového roku; přepínač bude fungovat dál.

---

## 6. DVA typové soubory — `types/database.ts` vs `types/supabase.ts` (drift)

**Kritické zjištění:** repo má dva typové soubory a kód není konzistentní:

- `types/database.ts` — **kanonický**, importuje ho 8 souborů včetně
  `lib/supabase-server.ts`, `app/dashboard/layout.tsx`, všech login stránek
  (`app/login`, `app/portal/login`, `app/zapis/prihlaseni`), `app/actions/tridni-kniha.ts`,
  `types/bulletin.ts`. **Byl ale prázdný pahýl (62 B)** → build padal:
  `Type error: File '.../types/database.ts' is not a module.`
- `types/supabase.ts` — používá jen hrstka míst (mj. naše pohledávky). Plný.

Komentář v `lib/supabase-server.ts:21` (`// vygenerovat: npx supabase gen types…`)
potvrzuje, že `database.ts` se měl vygenerovat, ale nikdy nedotáhl.

**Provedeno:** regenerace `types/database.ts` (312 kB). Build odblokován.

**Regenerace — spolehlivý postup (PowerShell):**

```powershell
# 1) generuj do dočasného souboru (obejde pipe/BOM problémy)
npx supabase gen types typescript --project-id zrzknpamosnniuljjivg > types\database.tmp.ts
# 2) ověř velikost (desítky–stovky kB) a přítomnost typu
Get-Item "types\database.tmp.ts" | Select-Object Length
Select-String -Path "types\database.tmp.ts" -Pattern "export type Database"
# 3) přepiš ostrý soubor VYNUCENÝM UTF-8 (přímé '>' píše UTF-16 → rozbije build!)
Get-Content "types\database.tmp.ts" | Set-Content -Path "types\database.ts" -Encoding utf8
Remove-Item "types\database.tmp.ts"
```

- **project-id:** `zrzknpamosnniuljjivg`
- **UTF-8 caveat:** PowerShell `>` produkuje UTF-16 → vždy přes
  `Get-Content | Set-Content -Encoding utf8`
- CLI warning `config section [inbucket] is deprecated` jde na stderr, **neškodí**
  (typy jdou na stdout); do souboru se nepropíše

**TODO (viz §7):** sjednotit na jeden typový soubor. Doporučení: udělat kanonickým
`database.ts` (8 importů) a hrstku importů `supabase.ts` přesměrovat na něj, pak
`supabase.ts` smazat. Dva paralelní typové soubory = přesně ten drift, co dnes
zmátl diagnózu FK.

---

## 7. Otevřené TODO (drift na dvou koncích — jinak se bugy vrátí na čistém env)

1. **Zdrojová migrace `20260428000003_payments.sql`**: opravit
   `created_by ... REFERENCES staff(id)` → `REFERENCES auth.users(id)`, ať
   `supabase db reset` postaví FK stejně jako produkce (obě místa z grepu na
   `created_by ... REFERENCES staff(id)`).
2. **Zdrojová migrace `058`**: nahradit definici `druzina_vytvorit_pohledavku`
   finální tříargumentovou verzí (mapování `staff.id → user_id`), ať `db reset`
   nepostaví starou.
3. **Centralizovat `ObligationType`** + label + SS-prefix do `lib/config.ts`
   (viz §4). Odstraní ~5 kopií unionu.
4. **Sjednotit typové soubory** `database.ts` / `supabase.ts` (viz §6).
5. **`supabase/config.toml`**: přejmenovat sekci `[inbucket]` → `[local_smtp]`
   (deprecation warning).
6. **`Nilsson_documentation`** — rozbitý git submodul (Vercel:
   `Failed to fetch one or more git submodules`, non-fatal). Buď opravit, nebo
   odebrat z `.gitmodules`.

---

## 8. Migrace vzniklé v této session

| Migrace | Účel |
| ------- | ---- |
| `059_fix_druzina_created_by.sql` | Oprava DVOUargumentové verze helperu (`auth.uid()`) — jak se ukázalo, tato verze se nevolá; ponecháno jako historický patch |
| `060_fix_druzina_pohledavka_3arg.sql` | **Skutečná oprava** — tříargumentová verze mapuje `staff.id → user_id` do `created_by` |
| (ad-hoc SQL) | `DROP FUNCTION IF EXISTS druzina_vytvorit_pohledavku(uuid, text);` — úklid mrtvého přetížení |

**Doporučení k migracím:** jelikož `059` opravovala nevolanou funkci, zvaž její
sloučení s `060` do jediné migrace (nebo `059` ponech jako no-op s komentářem),
a hlavně srovnej zdrojovou `058` (bod §7.2), ať čistý `db reset` dá stejný výsledek
jako produkce.

---

## Změněné soubory (frontend/actions)

- `app/actions/payments.ts` — `ObligationType` + `'druzina'`, `generateSsKod` prefix `'30'`
- `app/dashboard/platby/pohledavky/page.tsx` — `ObligationType`, `TypeBadge` (družina + fallback), `FilterBar` (filtr Družina + přepínač roku), `fetchObligations`/`fetchAvailableMonths`/`fetchAvailableSchoolYears`
- `types/database.ts` — regenerováno (312 kB)
