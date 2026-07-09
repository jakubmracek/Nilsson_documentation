# PRD + TRD Addendum — Modul Přihlášky do školní družiny

**Datum:** 2026-07-08
**Navazuje na:** TRD v1.3 (Školní družina, migrace 020/021), TRD Addendum eSSL v2.6 (migrace 036/037), Enrollment/Zápis modul (migrace 043–048)
**Autoři:** Ing. Jakub Mráček + Claude
**Status:** Návrh — čeká na schválení před psaním migrací

---

## 1. Cíl a kontext (PRD)

Dosavadní přihlašování do družiny je čistě ruční: ředitel v `/dashboard/druzina/prihlaseni` vidí žáky po třídách a sám zakládá `druzina_enrollments` přes `enrollStudent()`. Žádná žádost od zákonného zástupce, žádná spisová služba, žádné strukturované zachycení provozních údajů (dny docházky, způsob odchodu, osoby k vyzvednutí).

Cíl: zavést **self-service žádost přes rodičovský portál** (nilsson.zsvilekula.cz/portal), analogicky k modulu Zápis — s propisem do spisovky (věcná skupina **4.2.3**) a strukturovaným zachycením zákonných náležitostí přihlášky. Napojení na platby je **mimo scope tohoto kola** (jen připravit strukturu, ne automatické pohledávky).

Ředitel si zachovává možnost žáka **ručně dohlásit** (dnešní flow zůstává, jen se rozšíří o nová povinná pole).

---

## 2. Uživatelské role a flow (PRD)

- **Zákonný zástupce** — už je autentizovaný v rodičovském portálu (guardian auth, migrace `guardian_auth`). Žádný token/magic-link navíc není potřeba (na rozdíl od Zápisu, kde dítě ještě není v systému). V sekci „Družina" vyplní a odešle žádost.
- **Ředitel** — v `/dashboard/druzina/prihlaseni` (přepracovaná stránka) vidí frontu žádostí čekajících na rozhodnutí. Rozhoduje:
  - **jednotlivě** (nutné kvůli možnému převisu poptávky — částečné zamítnutí),
  - **hromadně** (bulk-schválení zbytku fronty najednou).
- Ředitel má dál k dispozici **ruční dohlášení** žáka (beze změny existující cesty, jen rozšířené formuláře o nová pole).

---

## 3. Datový model (TRD)

### 3.1 Nová tabulka `druzina_prihlasky` (žádost/dokument)

```sql
CREATE TABLE druzina_prihlasky (
  id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id                  UUID        NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
  school_year                 TEXT        NOT NULL,
  guardian_id                 UUID        NOT NULL REFERENCES guardians(id) ON DELETE RESTRICT,

  stav                        TEXT        NOT NULL DEFAULT 'rozpracovana'
                                CHECK (stav IN (
                                  'rozpracovana', 'odeslana',
                                  'prijato', 'zamitnuto', 'stornovano_rodicem'
                                )),

  -- Rozsah docházky (pevné okno po–pá 12:45–16:00, rodič vybírá jen dny)
  dny_dochazky                TEXT[]      NOT NULL DEFAULT '{}'
                                CHECK (dny_dochazky <@ ARRAY['po','ut','st','ct','pa']),

  -- Způsob odchodu — nezávislé checkboxy, oba false = vyzvedává ZZ osobně
  odchod_sam                  BOOLEAN     NOT NULL DEFAULT false,
  odchod_sam_cas               TIME,
  odchod_doprovod              BOOLEAN     NOT NULL DEFAULT false,

  -- Povinné souhlasy pro odeslání
  souhlas_uplata               BOOLEAN     NOT NULL DEFAULT false,
  souhlas_vnitrni_rad           BOOLEAN     NOT NULL DEFAULT false,
  souhlas_vnitrni_rad_verze     TEXT,        -- verze řádu platná v době odeslání
  souhlas_gdpr_rozsireni        BOOLEAN,     -- nepovinný scoped souhlas

  dokument_id                  UUID        REFERENCES dokumenty(id),  -- eSSL spis, věcná skupina 4.2.3

  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  submitted_at                 TIMESTAMPTZ,
  decided_at                   TIMESTAMPTZ,
  decided_by                   UUID        REFERENCES staff(id),

  CONSTRAINT chk_dp_odchod_sam_cas CHECK (
    odchod_sam = false OR odchod_sam_cas IS NOT NULL
  )
);

CREATE INDEX idx_dp_student_year ON druzina_prihlasky (student_id, school_year);
CREATE INDEX idx_dp_stav         ON druzina_prihlasky (school_year, stav);

CREATE TRIGGER trg_dp_updated_at
  BEFORE UPDATE ON druzina_prihlasky
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**Validace při odeslání (v RPC, ne jen v UI):**
- `dny_dochazky` neprázdné
- `souhlas_uplata = true`
- `souhlas_vnitrni_rad = true`
- pokud `odchod_doprovod = true` → musí existovat aspoň 1 řádek v `druzina_prihlaska_vyzvedavajici`

### 3.2 Nová tabulka `druzina_prihlaska_vyzvedavajici`

```sql
CREATE TABLE druzina_prihlaska_vyzvedavajici (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prihlaska_id  UUID NOT NULL REFERENCES druzina_prihlasky(id) ON DELETE CASCADE,
  jmeno         TEXT NOT NULL,
  telefon       TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dpv_prihlaska ON druzina_prihlaska_vyzvedavajici (prihlaska_id);
```

### 3.3 Rozšíření `druzina_enrollments` (provozní data — ALTER)

Tohle jsou živá data, která vychovatelka potřebuje po ruce celý rok — nejen v okamžiku podání žádosti. Proto se propisují do `druzina_enrollments`, ne jen do žádosti. Platí i pro **ruční dohlášení** ředitelem.

```sql
ALTER TABLE druzina_enrollments
  ADD COLUMN dny_dochazky    TEXT[]  NOT NULL DEFAULT '{}'
             CHECK (dny_dochazky <@ ARRAY['po','ut','st','ct','pa']),
  ADD COLUMN odchod_sam      BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN odchod_sam_cas  TIME,
  ADD COLUMN odchod_doprovod BOOLEAN NOT NULL DEFAULT false,
  ADD CONSTRAINT chk_de_odchod_sam_cas CHECK (
    odchod_sam = false OR odchod_sam_cas IS NOT NULL
  );
```

### 3.4 Nová tabulka `druzina_vyzvedavajici` (provozní, per enrollment)

Vázáno na `enrollment_id` (ne na žáka trvale) — zaniká při odhlášení/novém zápisu, nastavuje se znovu.

```sql
CREATE TABLE druzina_vyzvedavajici (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID NOT NULL REFERENCES druzina_enrollments(id) ON DELETE CASCADE,
  jmeno         TEXT NOT NULL,
  telefon       TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dv_enrollment ON druzina_vyzvedavajici (enrollment_id);
```

### 3.5 Rozšíření `gdpr_consents` (scoped souhlas pro družinu)

```sql
ALTER TABLE gdpr_consents
  DROP CONSTRAINT gdpr_consents_consent_type_check,
  ADD CONSTRAINT gdpr_consents_consent_type_check CHECK (consent_type IN (
    'communication', 'photography', 'third_party_sharing', 'data_processing',
    'druzina_provoz'   -- NOVÉ: rozšíření GDPR souhlasů i na provoz/akce družiny
  ));
```

Při zaškrtnutí `souhlas_gdpr_rozsireni` na žádosti se založí řádek `gdpr_consents(student_id, consent_type='druzina_provoz', granted=true, granted_at=now(), legal_basis='consent', consent_version=...)`.

---

## 4. Stavový automat žádosti

```
rozpracovana → odeslana → prijato
                        → zamitnuto
                        → stornovano_rodicem   (jen z 'rozpracovana' nebo 'odeslana')
```

Žádná analogie k `ceka_na_spoluzastupce` — družina nevyžaduje druhého zástupce (na rozdíl od Zápisu).

---

## 5. eSSL integrace

Analogicky k `enrollment_essl_open_spis`:

- **RPC `druzina_essl_open_spis(p_prihlaska_id UUID)`** — voláno při odeslání žádosti. Založí dokument v `dokumenty` s `vecna_skupina_id` odpovídající `spis_znak = '4.2.3'` (lookup, ne hardcoded UUID — nutno ověřit, že skupina 4.2.3 v produkční DB existuje), nastaví `smer = 'prijaty'`, `stav = 'prijat'`, propíše `dokument_id` na žádost, přepne `stav` žádosti na `odeslana`.
- Při rozhodnutí ředitele se dokument uzavírá (`zpusob_vyrizeni = 'rozhodnuti_vydano'` pro `prijato`/`zamitnuto`, `vzato_na_vedomi` pro `stornovano_rodicem`).

---

## 6. Rozhodovací flow ředitele

- Stránka `/dashboard/druzina/prihlaseni` nahrazena frontou žádostí ve stavu `odeslana`.
- **Jednotlivé rozhodnutí** — detail žádosti, tlačítka Přijmout/Zamítnout (kvůli možnému převisu poptávky).
- **Hromadné schválení** — akce nad zbytkem fronty najednou (vhodné, když převis nehrozí).
- Při `prijato`:
  1. vytvoří/rozšíří `druzina_enrollments` (přenos `dny_dochazky`, `odchod_sam`, `odchod_sam_cas`, `odchod_doprovod` ze žádosti)
  2. zkopíruje `druzina_prihlaska_vyzvedavajici` → `druzina_vyzvedavajici` (navázáno na nový `enrollment_id`)
  3. vygeneruje pohledávku `payment_obligations` (`type='druzina'`, 1000 Kč, splatnost +14 dní — viz sekce 9)
  4. uzavře eSSL dokument
- Při `zamitnuto` / `stornovano_rodicem` — žádný enrollment, jen uzavření dokumentu.

---

## 7. Ruční dohlášení ředitelem (zachování)

`enrollStudent()` (`app/actions/druzina.ts`) zůstává, ale je nutné rozšířit vstup/formulář o `dny_dochazky`, `odchod_sam`, `odchod_sam_cas`, `odchod_doprovod` a volitelně vyzvedávající osoby — je to tentýž `druzina_enrollments` záznam, jen jiná cesta vzniku (bez žádosti/eSSL spisu). Nově navíc generuje i pohledávku za úplatu do družiny — symetricky se schválenou přihláškou (viz 9.3).

---

## 8. RLS (návrh)

- `druzina_prihlasky`: guardian — SELECT/UPDATE vlastní žádosti (přes `student_guardian_links`), jen dokud `stav IN ('rozpracovana')`; `director` — ALL.
- `druzina_prihlaska_vyzvedavajici`: stejná vazba přes `prihlaska_id`.
- `druzina_vyzvedavajici`: `director` + `vychovatel` (via `has_role`) — SELECT (potřebují znát osoby k vyzvednutí); WRITE jen `director` (mění se při rozhodnutí/ručním zápisu).

---

## 9. Napojení na modul Platby (pohledávky)

Při přechodu žádosti do stavu `prijato` se automaticky vytváří pohledávka — analogicky ke generování pohledávek u `events`, ale bez manuálního kroku (přímý trigger na rozhodnutí, ne explicitní tlačítko).

### 9.1 Rozšíření `payment_obligations`

```sql
ALTER TABLE payment_obligations
  DROP CONSTRAINT payment_obligations_type_check,
  ADD CONSTRAINT payment_obligations_type_check CHECK (type IN (
    'tuition', 'event', 'lunch', 'donation', 'druzina'
  ));
```

### 9.2 Pravidla generování

- **Kdy:** při rozhodnutí `prijato` (jednotlivě i v rámci hromadného schválení).
- **Částka:** vždy celá **1000 Kč** — bez ohledu na to, kdy v průběhu školního roku byla žádost schválena (žádné poměrné krácení).
- **Splatnost (`due_date`):** `decided_at + 14 dní`.
- **`type`:** `'druzina'`, `reference_event_id` a `period` zůstávají `NULL` (nejde o akci ani měsíční školné).
- **Jednorázovost:** jedna pohledávka za `(student_id, school_year)` — přidat částečný unique index, aby opakované schválení/edge-case nevytvořilo duplicitní pohledávku:

```sql
CREATE UNIQUE INDEX uq_po_druzina_student_year
  ON payment_obligations (student_id, school_year)
  WHERE type = 'druzina';
```

### 9.3 Ruční dohlášení — symetrické chování

**Potvrzeno:** `enrollStudent()` (ruční dohlášení ředitelem, mimo přihlášku) generuje pohledávku stejně jako schválení přihlášky — jedna společná pomocná funkce/RPC pro vytvoření pohledávky za družinu, volaná z obou míst:
- z rozhodovacího flow (`prijato`)
- z `enrollStudent()` po úspěšném vytvoření `druzina_enrollments` záznamu

Platí stejná pravidla: 1000 Kč celá částka, `due_date = teď + 14 dní`, jednorázově per `(student_id, school_year)` (unique index `uq_po_druzina_student_year` chrání proti duplicitě i tady — např. když je žák nejprve ručně dohlášen a později "podá" zpětně přihlášku, druhý insert selže/ignoruje se podle ON CONFLICT).

---

## 10. Napojení na modul Omluvenky (docházka družiny)

V repu jsem nenašel konkrétní kód propojení omluvenka→oběd (buď je to v systému jídelny mimo Nilsson, nebo aplikováno přímo v Supabase) — princip ale přebírám a napojuji analogicky na `druzina_dochazka`.

### 10.1 Rozšíření `approveOmluvenka()` (`app/actions/omluvenky.ts`)

Po dnešním kroku 2 (vygenerování `attendance_records` pro pracovní dny v rozsahu) přidat krok 2b:

- Pro každý den v rozsahu omluvenky (`getWeekdays(date_from, date_to)`):
  1. Zjistit, zda má žák pro `school_year` aktivní `druzina_enrollments` záznam pokrývající daný den (`date_from <= den` a (`date_to IS NULL` nebo `date_to >= den`)).
  2. Pokud ano **a zároveň** den-v-týdnu (po/út/st/čt/pá) je obsažen v `dny_dochazky` daného zápisu → `UPSERT druzina_dochazka`:
     - `student_id`, `oddeleni_id` (ze zápisu), `datum = den`
     - `status = 'absent_excused'`
     - `note = 'Automaticky vygenerováno ze schválené omluvenky.'`
     - `recorded_by = staff.id`
     - `ON CONFLICT (student_id, datum) DO UPDATE` (kdyby už existoval ruční záznam docházky — přepíše se na omluvenou nepřítomnost)
- Pokud žák není v družině vůbec, nebo daný den nemá v `dny_dochazky` — nic se nevytváří (žádná falešná absence pro dny, kdy do družiny stejně nechodí).

### 10.2 Otevřená otázka

Co se stane, když je omluvenka **dodatečně zamítnuta/zrušena** po schválení? `rejectOmluvenka()` dnes řeší jen stav `pending → rejected`, ne zpětné rušení už schválené omluvenky. Pokud takový flow existuje/vznikne, bude potřeba analogicky vracet i `druzina_dochazka` zpět — navrhuju řešit až if/when takový requirement nastane.

---

## 11. Otevřené otázky / TODO před psaním migrací

1. Ověřit v produkční Supabase, že věcná skupina `4.2.3` skutečně existuje (v tomto repu není seedovaná — pravděpodobně vytvořena přímo v SQL editoru, stejně jako enrollment tabulky).
2. Notifikace rodičům o rozhodnutí (e-mail přes Resend?) — zatím neurčeno, navrhuji doplnit do dalšího kola.
3. Číslo migrace — dle potvrzení bude číslováno **56+** (repo si mezitím posunulo číselnou řadu mimo tento snapshot): `056_druzina_prihlasky.sql` + `057_rls_druzina_prihlasky.sql` + `058_druzina_platby_omluvenky.sql`.
4. UI wireframe formuláře na portálu — zatím nenavrženo.
5. ~~Má ruční dohlášení ředitelem také generovat pohledávku?~~ **Vyřešeno:** ano, symetricky (viz 9.3).
6. ~~Zpětné rušení `druzina_dochazka` při zrušení schválené omluvenky~~ **Vyřešeno:** mimo scope — takový flow (zrušení už schválené omluvenky) v systému vůbec neexistuje (`omluvenky.ts` má jen create/approve/reject), takže není co propojovat.

---

## 12. Souhrn nových/změněných objektů

| Objekt | Typ změny |
|---|---|
| `druzina_prihlasky` | nová tabulka |
| `druzina_prihlaska_vyzvedavajici` | nová tabulka |
| `druzina_enrollments` | ALTER (+4 sloupce) |
| `druzina_vyzvedavajici` | nová tabulka |
| `gdpr_consents` | ALTER (nová hodnota `consent_type`) |
| `payment_obligations` | ALTER (nová hodnota `type='druzina'` + unique index) |
| `druzina_essl_open_spis()` | nová RPC |
| `enrollStudent()` | rozšíření vstupu |
| `approveOmluvenka()` | rozšíření o propis do `druzina_dochazka` |
| `/dashboard/druzina/prihlaseni` | přepracování (fronta rozhodování) |
