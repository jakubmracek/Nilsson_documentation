# ARCH-NOTES — Addendum 2026-05-20

Navazuje na ARCH-NOTES v2.0 + addenda 2026-05-19
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 37. Import staff záznamů — vzor DO bloku

### Rozhodnutí

Staff záznamy se importují stejným vzorem jako žáci: PL/pgSQL `DO $$` blok
v Supabase SQL Editoru. Sekundární role (`staff_roles`) se vkládají ve stejném
bloku přes `RETURNING id INTO v_xxx`.

### Vzor

```sql
DO $$
DECLARE
  v_director UUID;
  v_vaclava  UUID;
  -- ...
BEGIN
  -- 0. Lookup ředitele pro audit (created_by, pokud tabulka vyžaduje)
  SELECT id INTO v_director
    FROM staff WHERE email = 'jakub.mracek@zsvilekula.cz' LIMIT 1;
  IF v_director IS NULL THEN
    RAISE EXCEPTION 'Ředitel nenalezen';
  END IF;

  -- INSERT staff záznamy
  INSERT INTO staff (first_name, last_name, email, role, typ_zamestnance, employment_type)
    VALUES ('Václava', 'Pelcová', 'vaclava.pelcova@zsvilekula.cz', 'guide', 'pedagogicky', 'part_time')
    RETURNING id INTO v_vaclava;

  -- Sekundární role (staff_roles) — ve stejném bloku
  INSERT INTO staff_roles (staff_id, role)
    VALUES (v_vaclava, 'vychovatel');

  RAISE NOTICE 'OK: Pelcová %', v_vaclava;
END $$;
```

### Aktuální stav staff tabulky (po importu 2026-05-20)

| Jméno | Role | employment_type | extra_roles |
|-------|------|-----------------|-------------|
| Ing. Jakub Mráček | director | full_time | — |
| Bc. Václava Pelcová | guide | part_time | vychovatel |
| Mgr. Kateřina Studničková | guide | full_time | — |
| Mgr. Ludmila Mráčková | vp | part_time | — |
| Michaela Kruchlová | assistant | part_time | — |
| Lenka Walterová | guide | full_time | — |
| Jana Švecová | director | part_time | — |
| Helena Ryklová | guide | part_time | vychovatel |

Všech 8 záznamů má `user_id` propojený s Supabase Auth (Auth účty vytvořeny
přes „Invite user" v Supabase Dashboard, UUID doplněna přes UPDATE).

### Propojení `staff.user_id`

Po vytvoření Auth účtů v Supabase Dashboard (Authentication → Users → Invite user):

```sql
UPDATE staff SET user_id = '<uuid-z-dashboardu>'
  WHERE email = 'katerina.studnickova@zsvilekula.cz';
-- opakovat pro každou novou osobu
```

Ověření: všichni staff musí mít `user_id IS NOT NULL`.

---

## 38. `hodnotil_id` backfill — vzor pro import s rozdělením per průvodkyně

### Problém

Při importu hodnocení z externího systému (vilekula-pokrok) nebyl `hodnotil_id`
k dispozici — průvodkyně neměly Auth účty v Nilssonu. Po vytvoření účtů je třeba
hodnotil_id doplnit zpětně.

V importovaných datech hodnotila každá průvodkyně jiný ročník/předmět —
nelze použít jeden slepý UPDATE přes celou tabulku.

### Klíčový princip

JOIN na `svp_vystupy` přes `vystup_id` umožňuje filtrovat hodnocení
podle `predmet` a `rocnik` — bez potřeby ukládat průvodkyni přímo do dat.

### Vzor UPDATE s diagnózu a pojistkou

```sql
DO $$
DECLARE
  v_kata  UUID := '<uuid-katerina-staff-id>';  -- staff.id, NE auth.uid()!
  v_lida  UUID := '<uuid-ludmila-staff-id>';
  v_vendy UUID := '<uuid-vaclava-staff-id>';
  n_kata  INT;
  n_lida  INT;
  n_vendy INT;
BEGIN
  -- Průvodkyně 1: dle ročníku + předmětu
  UPDATE mapa_pokroku_hodnoceni h
  SET hodnotil_id = v_kata
  FROM svp_vystupy v
  WHERE h.vystup_id = v.id
    AND h.hodnotil_id IS NULL
    AND h.school_year = '2025/2026'
    AND h.semester = 1
    AND (
      v.rocnik = 1
      OR (v.rocnik = 2 AND v.predmet = 'Umění a kultura')
    );
  GET DIAGNOSTICS n_kata = ROW_COUNT;

  -- ... analogicky pro další průvodkyně ...

  RAISE NOTICE 'Backfill: Káťa=%, Lída=%, Vendy=%', n_kata, n_lida, n_vendy;

  -- Pojistka: nesmí zůstat žádný NULL
  IF EXISTS (
    SELECT 1 FROM mapa_pokroku_hodnoceni
    WHERE hodnotil_id IS NULL
      AND school_year = '2025/2026'
      AND semester = 1
  ) THEN
    RAISE EXCEPTION 'Chyba: po backfillu zůstaly záznamy s hodnotil_id IS NULL';
  END IF;
END $$;
```

### Mapování hodnocení pro Vilekulu (1. pololetí 2025/2026)

| Ročník | Předmět | Průvodkyně |
|--------|---------|------------|
| 1 | všechny | Kateřina Studničková |
| 2 | Umění a kultura | Kateřina Studničková |
| 2 | ostatní předměty | Ludmila Mráčková |
| 3 | všechny | Ludmila Mráčková |
| 4 | všechny | Václava Pelcová |
| 5 | všechny | Václava Pelcová |

Výsledné počty: Studničková 509, Pelcová 417, Mráčková 151 = celkem 1 077 ✅

### Důležitá poznámka: `hodnotil_id` = `staff.id`

`hodnotil_id` odkazuje na `staff.id` (UUID z tabulky `staff`),
**ne** na `auth.uid()`. Tyto dvě hodnoty jsou různé — záměna způsobí
FK violation nebo nesprávné přiřazení.

---

## 39. Platební modul — architektonická rozhodnutí

### 39.1 Specifický symbol (SS) — schéma

Specifický symbol jednoznačně identifikuje pohledávku v platbě.
Formát: `PREFIX(2) + YYYY(4) + MM(2) + RANK(2)` = 10 číslic (limit české bankovní platby).

| Typ pohledávky | Prefix |
|----------------|--------|
| Obědy | `10` |
| Výjezdní akce | `20` |

Příklad: `2020270103` = akce, leden 2027, 3. pohledávka daného měsíce.

**RANK** je pořadové číslo per typ per měsíc — generován aplikační vrstvou
(ne DB sekvencí). DB sekvence nelze snadno resetovat per měsíc bez extra tabulky.

```typescript
// Server Action: zjisti MAX RANK pro prefix+YYYYMM a přičti 1
const { data } = await supabase
  .from('payment_obligations')
  .select('ss_kod')
  .like('ss_kod', `${prefix}${yyyymm}%`)
  .order('ss_kod', { ascending: false })
  .limit(1)

const lastRank = data?.[0]?.ss_kod
  ? parseInt(data[0].ss_kod.slice(-2))
  : 0
const ss = `${prefix}${yyyymm}${String(lastRank + 1).padStart(2, '0')}`
```

### 39.2 QR kód — Paylibo API

QR kód se generuje jako `<img>` tag odkazující na Paylibo API.
Žádná třetí strana library — jen URL sestavená z parametrů.

```typescript
// lib/paylibo.ts — shared (importovatelné z Client i Server)
export function payliboUrl(params: {
  amount: number
  vs: string      // kod_zaka — 4místné pořadové číslo
  ss: string      // ss_kod — 10místný specifický symbol
  message: string
}): string {
  return `http://api.paylibo.com/paylibo/generator/czech/image`
    + `?accountNumber=${process.env.BANK_ACCOUNT_NUMBER}`
    + `&bankCode=${process.env.BANK_CODE}`
    + `&amount=${params.amount.toFixed(2)}`
    + `&currency=CZK`
    + `&vs=${params.vs}`
    + `&ss=${params.ss}`
    + `&message=${encodeURIComponent(params.message)}`
}
```

Env proměnné (`.env.local` + Vercel) — fixní za runtime, snadno editovatelné:

```
BANK_ACCOUNT_NUMBER=2303305396
BANK_CODE=2010
```

### 39.3 Párování transakcí — rozšíření Fio importu

Stávající cron páruje přes VS (variabilní symbol → `students.kod_zaka`).
Rozšíření: párovat i přes SS (specifický symbol → `payment_obligations.ss_kod`).

Obě podmínky musí sedět pro automatické párování:
```
transaction.specific_symbol → payment_obligations.ss_kod
transaction.variable_symbol (padStart 4) → students.kod_zaka suffix
```

Výsledek: INSERT do `payment_matches` + UPDATE `match_status = 'matched'`.
Pokud chybí SS nebo nesedí: `match_status = 'unmatched'` + `system_alert`
(stávající chování zachováno).

### 39.4 Stav pohledávky — odvozený, ne uložený

`payment_obligations` nemá sloupec `status`. Stav se odvozuje v aplikační
vrstvě ze `SUM(payment_matches.matched_amount)`:

| Podmínka | Stav |
|----------|------|
| `SUM = 0` nebo žádný match | `pending` |
| `0 < SUM < amount` | `partial` |
| `SUM >= amount` | `paid` |

### 39.5 Workflow zadání pohledávek

Záměrně dvoufázový — notifikace se neposílají automaticky:

1. Ředitel zadá pohledávky (základní cena + individuální úpravy)
2. Ředitel zkontroluje přehled
3. Ředitel explicitně klikne „Odeslat notifikace"
4. Systém pošle email všem ZZ s `je_zakonny_zastupce = TRUE` + pohledávka
   se zobrazí v rodičovském portálu

Email obsahuje QR kód jako `<img src="{payliboUrl}">` (inline v HTML),
plus VS + SS + číslo účtu jako text (záloha pro případ nefunkčního obrázku).

Po odeslání: UPDATE `payment_obligations.notified_at = now()`.

### 39.6 Storno pohledávky

Není v UI — řeší ředitel přímo v DB (DELETE nebo soft delete).
Důvod: nízká frekvence, přidání UI by zvýšilo komplexitu bez reálného přínosu.

### 39.7 Split `lib/payments.ts` / `lib/paylibo.ts`

Stejný princip jako u `mapa-pokroku.ts` / `mapa-pokroku-shared.ts` (sekce 35.2):

| Soubor | Kde použitelný | Obsah |
|--------|---------------|-------|
| `lib/payments.ts` | Server Components, Server Actions | Supabase dotazy, typy |
| `lib/paylibo.ts` | Client i Server | `payliboUrl()` pure funkce |

`payliboUrl()` musí být dostupná v Client Components (portál zobrazuje QR kód
dynamicky) — proto separátní soubor bez Supabase závislostí.
