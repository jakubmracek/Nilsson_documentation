## 14. [[Mapa pokroku]] — architektonická rozhodnutí modulu

Modul integrován z vilekula-pokrok (samostatný Supabase projekt) do Nilssonu v květnu 2026.
Viz také sekce 15 (cross-project UUID remapping).

### 14.1 `stupen_zvladnuti` — pořadí hodnot enumu

```sql
CREATE TYPE stupen_zvladnuti AS ENUM (
  's_jistotou',   -- 1
  'castecne',     -- 2
  's_dopomoci',   -- 3
  'nezacali',     -- 4
  'nezvlada'      -- 5
);
```

**Záměrné pořadí: nižší index = lepší výsledek.** V školním prostředí asociuje nižší číslo
lepší hodnocení (konvence analogická ke školní stupnici 1–5). Zachováno identické
s vilekula-pokrok.

**Důsledek pro SQL dotazy:** `ORDER BY stupen ASC` vrátí nejprve nejlepší výsledky.
`WHERE stupen <= 'castecne'` vrátí zvládnuté výstupy. Je to intuitivní — ale opačné
k tomu, jak PostgreSQL obvykle enum pořadí používá (kde se předpokládá vzestupná "dobrota").
Každý dotaz pracující s relacemi `<` / `>` na tomto enumu musí být okomentován.

### 14.2 `poznamky TEXT[]` → `poznamka TEXT`

vilekula-pokrok má `poznamky TEXT[]` (pole řetězců). V exportu 1 076 záznamů je
**100 % hodnot `[]`** — pole nebylo nikdy použito.

V Nilssonu zjednodušeno na `poznamka TEXT NULL`. Důvod: YAGNI — pole (array) komplikuje
dotazy, ORM typy i UI bez jakéhokoli přínosu. Pokud v budoucnu vznikne potřeba více
komentářů na jedno hodnocení, řeší se samostatnou `mapa_pokroku_poznamky` tabulkou,
ne polem.

### 14.3 `hodnotil_id = NULL` u importovaných záznamů

Při importu z vilekula-pokrok byl `autor_id` (jediný autor všech 1 076 záznamů) UUID
z jiného Supabase projektu — v Nilssonu neexistuje odpovídající `staff` záznam s Auth.
Průvodkyně dosud nemají Auth účty v Nilssonu.

Rozhodnutí: importovat s `hodnotil_id = NULL`. Alternativy byly odmítnuty:

- Vytvořit "placeholder" staff záznam bez `user_id` — znečistí RLS a reporty
- Blokovat import dokud průvodkyně nemají účty — zbytečné zdržení

**Až průvodkyně dostanou Auth účty** v Nilssonu, lze doplnit zpětně:

```sql
UPDATE mapa_pokroku_hodnoceni
SET hodnotil_id = '<uuid-pruvodkyne>'
WHERE hodnotil_id IS NULL
  AND school_year = '2025/2026'
  AND semester = 1;
```

(Předpoklad: všechna importovaná hodnocení z jednoho pololetí zadala jedna průvodkyně —
ověřit před spuštěním UPDATE.)

### 14.4 UNIQUE constraint (student, výstup, rok, pololetí)

```sql
UNIQUE (student_id, vystup_id, school_year, semester)
```

Jeden aktivní záznam per žák per výstup per pololetí. **Není to historický log** —
změna hodnocení znamená UPDATE, ne nový INSERT. Důvod: [[Mapa pokroku]] zobrazuje
*aktuální stav*, ne historii změn. Pokud bude v budoucnu potřeba historický průběh,
přidá se `mapa_pokroku_hodnoceni_history` tabulka (append-only, vzor jako
`student_matrika_changes`).

### 14.5 Třída vs. ročník — dva různé koncepty

Nilsson rozlišuje:

- **Třída / skupina** (`groups`, `group_memberships`) — organizační jednotka, stejná pro
  všechny [[Žáci]] Vilekuly v daném školním roce (I./2025-2026)
- **Ročník** (`svp_vystupy.rocnik`) — pedagogická úroveň výstupu, závisí na věku [[Žáci]],
  ne na skupině

vilekula-pokrok měl [[Žáci]] rozdělené do 4 `trida` záznamů po ročnících — to byl
**aplikační workaround** pro filtrování výstupů per ročník, ne skutečná třídní
struktura. Nilsson tento workaround nepotřebuje: výstupy jsou přímo filtrovatelné
přes `svp_vystupy.rocnik`, [[Žáci]] jsou v jedné skupině.

**Dopad na UI Mapy pokroku:** zobrazení per žák musí dohledat ročník [[Žáci]]
z `birth_date` (nebo z `group_memberships.school_year` + věkový výpočet), ne ze skupiny.

---

## 15. Cross-project UUID remapping — vzor pro migraci mezi Supabase projekty

### Problém

Dva oddělené Supabase projekty (vilekula-pokrok, vilekula-is) mají stejné entity
([[Žáci]], výstupy ŠVP), ale různé UUID. Přímý datový přesun FK hodnot není možný.

### Řešení: textové párování + mapping CSV

**Krok 1 — najdi stabilní textový klíč** pro každou entitu:

| Entita | Textový klíč | Spolehlivost |
|---|---|---|
| Žák | `jmeno + prijmeni` | Dostatečná pro 18 [[Žáci]] (bez kolidujících jmen) |
| Výstup ŠVP | `(rocnik, oblast→prefix, poradi)` | 100 % — generuje deterministický kód |

**Krok 2 — generuj mapping CSV** (`pokrok_id → nilsson_id`) před samotným importem dat.

**Krok 3 — validuj mapping** před importem:
- Žádné sirotky na žádné straně
- Texty výstupů jsou identické (nezávislý check)
- UNIQUE constraint bude splněn (no duplicates)

**Výsledky pro tuto migraci:**

| Entita | Párů | Nespárováno |
|---|---|---|
| `svp_vystupy` | 600/600 | 0 |
| `students` | 18/18 | 0 |
| `hodnoceni` | 1 077/1 077 | 0 |

### Artefakty migrace (uložit pro audit)

```
scripts/
  vystup_mapping.csv      ← pokrok_vystup_id → nilsson_vystup_id + nilsson_kod
  zak_mapping.csv         ← pokrok_zak_id → nilsson_student_id + kod_zaka
  import_mapa_pokroku.sql ← 1 077 INSERT příkazů s přemapovanými UUID
supabase/migrations/
  008_mapa_pokroku.sql    ← enum + tabulka + RLS
```

### Kdy použít tento vzor znovu

Kdykoli migrujeme data mezi Supabase projekty (nebo z externího systému):
1. Identifikuj stabilní textový klíč (ne UUID)
2. Vygeneruj mapping CSV Python skriptem
3. Validuj 0 sirotků před importem
4. Ulož mapping CSV jako auditní stopu — UUID v DB se nemění, ale mapping
   umožní dohledat původ libovolného záznamu

**Nikdy neimportuj UUID přímo z jiného projektu** — kolize s existujícími záznamy,
porušení RLS, záhadné chyby v cizích klíčích.
