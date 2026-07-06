---

## 10. Addendum: Poznatky z přípravy na inspekci ČŠI (27. 4. 2026)

Toto addendum vzniklo při konsolidaci matrikových dat pro kontrolu ČŠI. Doplňuje sekci 8 o nové databázové požadavky.

---

### 10.1 Katalogové listy z předchozích škol

**Legislativní základ:** §28 odst. 3 školského zákona — při přestupu škola obdrží výpis z dokumentace a ten se stává součástí školní matriky.

**Požadavky na IS:**

- Tabulka `student_documents` (nebo sloupce v `students`): evidence existence katalogu z předchozí školy
- Sloupce: `kat_list_stav` (ENUM: `k_dispozici` / `chybí` / `nevyžadováno`), `kat_list_drive_url` (nullable text), `kat_list_poznamka` (text)
- Stav `nevyžadováno` pro žáky přijaté prvozápisem (KOD_ZAH ≠ E)
- UI: v kartě žáka zobrazit odkaz + stav, upozornění pokud `chybí` u přestupujícího žáka

---

### 10.2 Audit trail změn matrikových dat

**Motivace:** ČŠI kontroluje průkaznost evidence. Musí být doložitelné, kdy a jak ke změně došlo.

**Nová tabulka: `student_matrika_changes`**

```sql
CREATE TABLE student_matrika_changes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  timestamptz NOT NULL DEFAULT now(),
  student_id  uuid REFERENCES students(id) ON DELETE RESTRICT,
  datum_zmeny date NOT NULL,                     -- datum reálné události (ne datum zápisu)
  pole        text NOT NULL,                     -- název sloupce / oblasti (adresa, zz, pece...)
  hodnota_pred text,                             -- NULL = nový záznam (přidání)
  hodnota_po  text NOT NULL,
  zdroj_zmeny text NOT NULL,                    -- 'oznámení ZZ', 'rozsudek soudu', 'interní korekce'...
  dokument_ref text,                             -- volitelně odkaz na dokladový soubor
  zaznamenal  text NOT NULL                      -- jméno uživatele IS
);
```

**Chování IS:**
- Každá editace matrikového pole přes UI vytvoří automaticky záznam v `student_matrika_changes`
- Pole `hodnota_pred` se automaticky vyplní ze stavu před uložením
- Datum_zmeny uživatel zadá ručně (reálný datum události, ne technický timestamp)
- Záznamy jsou immutable — nelze mazat, pouze přidávat opravný záznam
- Export do PDF karty žáka zahrnuje sekci „Zaznamenané změny"

---

### 10.3 Zákonní zástupci vs. osoby v péči

**Motivace:** Případ Sophia Dani (19. 11. 2025) — svěřena do péče babičky, zákonnou zástupkyní zůstává matka. Stávající datový model nerozlišoval tyto dvě role.

**Úprava tabulky `guardians` / `student_guardian_links`:**

```sql
-- Typ vazby mezi žákem a osobou
CREATE TYPE guardian_role AS ENUM (
  'matka',
  'otec',
  'poručník',
  'opatrovník',
  'pěstoun',
  'svěřená_péče',     -- péče soudem, ale NENÍ zákonný zástupce
  'jiný_zz',
  'kontaktní_osoba'   -- bez právního titulu, pouze kontakt
);

ALTER TABLE student_guardian_links ADD COLUMN IF NOT EXISTS
  je_zakonny_zastupce boolean NOT NULL DEFAULT true;

ALTER TABLE student_guardian_links ADD COLUMN IF NOT EXISTS
  je_primarni_kontakt boolean NOT NULL DEFAULT false;

ALTER TABLE student_guardian_links ADD COLUMN IF NOT EXISTS
  platnost_od date;

ALTER TABLE student_guardian_links ADD COLUMN IF NOT EXISTS
  platnost_do date;   -- NULL = stále platné

ALTER TABLE student_guardian_links ADD COLUMN IF NOT EXISTS
  pravni_titul text;  -- 'rozsudek č. ...', 'rodný list', 'soudní příkaz'...
```

**Validace:**
- Každý žák musí mít alespoň jednoho zákonného zástupce (`je_zakonny_zastupce = true`)
- UI varuje pokud `je_zakonny_zastupce = false` u všech vazeb žáka
- Osoby se `svěřená_péče` a `kontaktní_osoba` mají `je_zakonny_zastupce = false` povinně
- Export XML (MŠMT) zahrnuje pouze zákonné zástupce

---

### 10.4 Identifikátory žáka — mapovací tabulka

**Motivace:** V systému koexistují tři různé identifikátory; IS musí všechny udržovat konzistentní.

| Identifikátor | Zdroj | Mutable | Použití |
|---|---|---|---|
| `id` (UUID) | vilekula-is (Supabase) | NE | interní FK |
| `kod_zaka` (VIL-RRRR-NNN) | vilekula-is | NE | lidsky čitelný kód pro komunikaci |
| `vs_interni` | historický interní číselník | NE | párování s historickými Google Sheets |
| `rodc` | MŠMT (XML výkazy) | jen §28/4 | XML výkazy, párování s MŠMT |
| `kod_zaka_msmt` | MŠMT soubor „a" (KOD_ZAKA) | NE | anonymizované výkazy SVP |

```sql
-- Všechny identifikátory přímo na tabulce students:
ALTER TABLE students ADD COLUMN IF NOT EXISTS kod_zaka text UNIQUE NOT NULL;
ALTER TABLE students ADD COLUMN IF NOT EXISTS vs_interni text UNIQUE;         -- historický kód
ALTER TABLE students ADD COLUMN IF NOT EXISTS kod_zaka_msmt text UNIQUE;      -- z „a" souboru
-- rodc je již evidováno jako citlivý údaj (šifrovaný sloupec)
```

---

### 10.5 Export PDF karet žáků

**Motivace:** ČŠI i jiné kontroly mohou vyžadovat fyzický nebo PDF výstup matrikové karty.

**Požadavky:**
- API endpoint `GET /api/students/:id/karta.pdf` generující PDF kartu žáka
- Karta obsahuje: identifikace, adresa, vzdělávání, zákonní zástupci, zdravotní info, SVP, historické změny
- RODC se v PDF nezobrazuje (citlivý údaj) — zobrazí se pouze v zabezpečeném interním pohledu
- Hromadný export: `POST /api/students/karty-export` (pole student_ids nebo `all`) → ZIP s PDF soubory
- Patička PDF: datum generování, jméno uživatele, GDPR upozornění
- Dočasná alternativa do spuštění IS: Apps Script `KartaZaka.gs` (v repozitáři)

---

### 10.6 Datový model — souhrnný přehled nových/upravených tabulek

```
students                    ← přidat: kod_zaka, vs_interni, kod_zaka_msmt,
                                       kat_list_stav, kat_list_drive_url, kat_list_poznamka

student_guardian_links      ← přidat: je_zakonny_zastupce, je_primarni_kontakt,
                                       platnost_od, platnost_do, pravni_titul
                              upravit: role → guardian_role ENUM (rozšíření)

student_matrika_changes     ← NOVÁ TABULKA (viz 10.2)
```

---

*Addendum zpracoval: Ing. Jakub Mráček | 27. 4. 2026 | Podklad: příprava na inspekci ČŠI ZŠ Vilekula*
