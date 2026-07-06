# TRD Dodatek — Modul Třídní kniha
## vilekula-is · verze 0.1 · 25. 4. 2026

> Tento dodatek vznikl na základě praktické tvorby třídní knihy ZŠ Vilekula pro školní rok 2025/2026 a zachycuje poznatky, které nebyly součástí původního PRD/TRD. Navazuje na existující specifikaci matriční evidence a modulu absence.

---

## 1. Datový model

### 1.1 Tabulka `tridni_kniha_zaznamy`

Primární zdroj dat: export Google Calendar (nebo budoucí nativní zadávání v IS).

```sql
CREATE TABLE tridni_kniha_zaznamy (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    datum         DATE NOT NULL,
    den_v_tydnu   CHAR(2) NOT NULL,          -- 'po','út','st','čt','pá'
    cas_od        TIME,                       -- NULL = celý den
    cas_do        TIME,
    nazev         TEXT NOT NULL,
    popis         TEXT,
    typ_zaznamu   TEXT NOT NULL               -- 'vyuka','expedice','projekt','prazdniny','reditelske_volno'
                  CHECK (typ_zaznamu IN ('vyuka','expedice','projekt','prazdniny','reditelske_volno','sportovni_kurz','kulturni_akce')),
    skolni_rok    CHAR(9) NOT NULL,           -- '2025/2026'
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON tridni_kniha_zaznamy (datum);
CREATE INDEX ON tridni_kniha_zaznamy (skolni_rok, datum);
```

**Poznatky z praxe:**
- Jeden den může mít více záznamů (ranní kruh + expedice + sebeřízený blok).
- Záznamy typu „celý den" (bez času) jsou nejčastější — konkrétní časy jsou výjimkou.
- Nutno odlišit záznamy vzdělávacího obsahu od provozních (schůzky ŽD, rezervace prostor) — viz filtrování níže.

---

### 1.2 Tabulka `pruvodci_dny`

Mapování průvodců na konkrétní dny (v IS nahrazuje ruční doplňování do PDF).

```sql
CREATE TABLE pruvodci_dny (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    datum         DATE NOT NULL,
    pedagog_id    UUID NOT NULL REFERENCES pedagogove(id),
    role_dne      TEXT DEFAULT 'průvodce'     -- 'průvodce','asistent','externista'
);

CREATE UNIQUE INDEX ON pruvodci_dny (datum, pedagog_id);
```

**Poznatky z praxe:**
- Složení průvodců se v průběhu roku mění (jiné na podzim, jiné od ledna, odlišné dle dne v týdnu).
- IS musí umět nastavit **opakující se pravidlo** (např. „čtvrtky od 1. 1. = Pelcová + Záhlava") s možností jednorázového přepsání.
- Pravidla pro rok 2025/2026 jsou zdokumentována v kódu generátoru PDF.

---

### 1.3 Tabulka `svp_vazby`

Propojení denního záznamu s očekávanými výstupy ŠVP pro konkrétní ročník.

```sql
CREATE TABLE svp_vazby (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zaznam_id       UUID NOT NULL REFERENCES tridni_kniha_zaznamy(id) ON DELETE CASCADE,
    rocnik          SMALLINT NOT NULL CHECK (rocnik BETWEEN 1 AND 9),
    predmet         TEXT NOT NULL,            -- 'Matematika','Jazyk a komunikace', ...
    vystup_text     TEXT NOT NULL,
    zdroj           TEXT DEFAULT 'ai'         -- 'ai','manual' (pro audit)
);

CREATE INDEX ON svp_vazby (zaznam_id);
CREATE INDEX ON svp_vazby (rocnik, predmet);
```

**Poznatky z praxe:**
- Průměr: ~2,6 výstupů na ročník na den (rozsah 0–6).
- AI párování je dobrý výchozí bod, ale pedagogové musí mít UI pro ruční úpravu.
- Výstupy pro Pohyb a Umění mají charakter tematického okruhu (jeden text pro celý předmět), ostatní jsou granulární.
- Atribut `zdroj` je důležitý — ČŠI může zajímat, zda vazba vznikla ručně nebo automaticky.

---

### 1.4 Tabulka `hospitace`

```sql
CREATE TABLE hospitace (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    datum           DATE NOT NULL,
    typ             TEXT NOT NULL CHECK (typ IN ('interní','externí')),
    hospitant_jmeno TEXT NOT NULL,
    hospitant_inst  TEXT,                     -- instituce externího hospitanta
    poznamka        TEXT,
    zaznam_id       UUID REFERENCES tridni_kniha_zaznamy(id)
);
```

**Poznatky z praxe:**
- Interní hospitace ředitele probíhají každé pondělí + ad hoc při vybraných akcích.
- Externí hospitanti přicházejí z jiných škol — IS by měl ukládat i instituci pro případné výkazy.
- Jeden den může mít více hospitantů (interní + externí současně — viz 30. 3. 2026).

---

### 1.5 Tabulka `bozp_zaznamy`

```sql
CREATE TABLE bozp_zaznamy (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    datum           DATE NOT NULL,
    popis           TEXT NOT NULL,
    zaci_ids        UUID[],                   -- NULL = celá třída, jinak konkrétní žáci
    skolni_rok      CHAR(9) NOT NULL
);
```

**Poznatky z praxe:**
- BOZP proškolení probíhá: (a) hromadně na začátku roku, (b) individuálně při nástupu žáka v průběhu roku.
- IS musí automaticky upozornit na nově nastoupivšího žáka bez záznamu o BOZP.

---

## 2. Filtrovací pravidla — co patří do třídní knihy

Toto byl nejnáročnější aspekt praktické tvorby. Google Calendar obsahuje směs vzdělávacích a provozních záznamů. IS musí rozlišovat:

### 2.1 Kategorie k vyloučení

| Kategorie | Příklady | Důvod |
|-----------|----------|-------|
| Statistické výkazy | ZMĚNOVÉ HLÁŠENKY, M 3, P 1-04 | Administrativa, ne výuka |
| Provoz Živého domu | Schůzka ŽD, Tvoření seniorky, rezervace prostor | Provozovatel budovy |
| Porady týmu | Schůzka celý tým, porada týmu | Interní provoz |
| Osobní záznamy | Narozeniny, svátky pracovníků/rodinných příslušníků | Irelevantní |
| Nepřítomnosti průvodců | „není Vendy – GOZO", „Míša sickday" | Personální, ne výuka |
| Span-event duplicity | „ukliďme Česko" jako vícedenní překryv | Obsah je v denních zápisech |

### 2.2 Hraniční případy — ponechat

| Záznamy | Důvod ponechání |
|---------|-----------------|
| Záznamy se jmény průvodců v titulku | Regulérní výuka, název je interní konvence |
| Šatlava, Opárno, adaptační pobyt | Legitimní vzdělávací akce (sportovní kurz, projekt) |
| Ředitelské volno | Relevantní pro evidenci nepřítomnosti žáků |
| Projektové dny se zaměstnanci ŽD | Vzdělávací obsah (finanční gramotnost, čajovna) |
| Víkendové akce (Zatmění Měsíce, Noc vědců) | Školní akce mimo povinnou docházku |

### 2.3 Doporučení pro IS

Namísto blacklistu klíčových slov (křehké řešení) implementovat **whitelist typů záznamů** — průvodci při zadávání vybírají typ (`výuka`, `expedice`, `projekt`, `sportovní kurz`, ...). Provozní záznamy zadávat do jiného kalendáře/modulu.

---

## 3. Evidence docházky

### 3.1 Datové zdroje (zkušenost 2025/2026)

V tomto školním roce existovaly tři oddělené datové zdroje:
1. **xlsx tabulka** — září–leden, formát: měsíc jako list, žáci v řádcích, dny ve sloupcích, hodnota = hodiny absence
2. **CSV omluvenky** — únor–duben, formulářový výstup (Google Forms), formát: jeden řádek = jedna omluvenka s rozsahem dat a důvodem
3. **Ruční záznamy** — pár položek doplněno ad hoc

### 3.2 Klíčová business logika

```
hodiny_absence_za_den:
  - Výchozí hodnota: 4 hod (standardní den), 6 hod (čtvrtek — terénní program)
  - Výjimka: částečná absence (např. příchod po obědě) — zadána explicitně v hodinách
  - POZOR: pole „počet hodin" v omluvenkovém formuláři obsahuje SOUČET za celé období,
    ne hodnotu na den — při importu ignorovat u vícedenních absencí

prázdniny_a_volno:
  - Nezapočítávat do absence žáka
  - Ředitelské volno = školní den bez výuky (žák nepřítomen = nezapočítáno)

žáci_mimo_evidenci:
  - Žáci před datem nástupu nebo po datu odchodu se v prezenčce zobrazují, ale s příznakem
  - Absence se pro ně nevykazuje
```

### 3.3 Prodloužená absence

Malvína Konopáčová měla v únoru–březnu prodlouženou absenci z rodinných důvodů (rekreace, postupně prodlužovaná). V IS to znamená:
- Jeden případ = jedna omluvenka s poznámkou o prodlužování
- Neopakovat jako 4 separátní záznamy
- UI by mělo umožnit „prodloužit stávající absenci" bez vytváření nového záznamu

---

## 4. Import dat pro školní rok 2025/2026

Pro migraci do produkčního IS jsou připraveny tyto soubory:

| Soubor | Obsah | Formát |
|--------|-------|--------|
| `tridni_kniha.csv` | 182 záznamů vzdělávacího obsahu | date, weekday, time, title, description |
| `dochazka_souhrn.csv` | Souhrn docházky po měsících, 20 žáků | kat_číslo, příjmení, jméno, ročník, měsíční sumy |
| `dochazka_detail.csv` | Každá absence zvlášť | žák, datum, den, hodiny, důvod, poznámka |
| `svp_parovani_komplet.csv` | 1 859 vazeb výstupů ŠVP | date, rocnik, predmet, vystup_text |
| `Vilekula_děti_do_20260424.csv` | Seznam žáků s daty | jméno, příjmení, ročník, příchod, odchod |
| `Katalogová_čísla.csv` | Katalog. čísla žáků | číslo, jméno, příjmení |

**Ano, data jsou připravena k importu.** Jakmile bude schéma databáze vilekula-is finalizováno, napíšu importní skripty (Python + Supabase client nebo přímé SQL INSERT).

---

## 5. UI/UX požadavky — poznatky z praxe

### 5.1 Denní záznam

- Průvodci musí být schopni zadat obsah dne **retrospektivně** (záznam vzniká po skončení dne, ne před).
- Výstupy ŠVP: AI návrh + možnost editace. Průvodce vybírá z číselníku výstupů pro svůj ročník, AI předvyplní.
- **Vícečtením vazby**: jeden den má záznamy pro různé ročníky (výstupy 1. ročníku ≠ výstupy 5. ročníku pro tentýž den).

### 5.2 Průvodci

- UI pro nastavení **opakujících se pravidel** (kdo učí v pondělí, kdo ve čtvrtek).
- Jednorázové přepsání pro konkrétní den (nemoc, záskok).

### 5.3 Docházka

- Průvodce eviduje absenci v reálném čase (ranní check-in).
- Rodič omlouvá přes formulář (existující Google Forms → nahradit nativním formulářem v IS).
- Automatické propojení omluvenky s absencí (párování přes jméno žáka a datum).
- Upozornění na neomluvené hodiny po uplynutí lhůty.

### 5.4 PDF export

- PDF třídní knihy generovat on-demand (pro ČŠI, archivaci, rodiče).
- Šablona je zdokumentována v `/home/claude/gen_tridnice_final.py`.
- Při prvním exportu za školní rok automaticky vložit BOZP záznamy pro nově nastoupivší žáky.

---

## 6. Otevřené otázky pro další TRD session

1. **Číselník výstupů ŠVP** — kde bude uložen? Jako tabulka v Supabase, nebo jako statický JSON? Jak se bude aktualizovat při změně ŠVP?
2. **Víceročníkové záznamy** — jak UI zobrazí, že tentýž program měl různé výstupy pro různé ročníky? Záložky? Rozbalitelné sekce?
3. **Pravidelnost hospitací** — implementovat jako opakující se pravidlo (analogie k průvodcům), nebo ruční zadávání?
4. **Archivace** — třídní kniha je školní dokument s povinnou dobou uchování. Jak zajistit immutabilitu po uzavření školního roku?
5. **Synchronizace s Google Calendar** — zachovat jako vstupní kanál (webhook nebo periodický import), nebo přejít na nativní zadávání v IS od 2026/2027?

---

*Dokument připravil: Claude Sonnet 4.6 na základě praktické tvorby třídní knihy ZŠ Vilekula, 25. dubna 2026.*
*Navazuje na PRD v0.7 a TRD session (matriční výkazy, absence).*
