# ARCH-NOTE: Kód žáka pro MŠMT se doplňuje sám z rodného čísla

**Datum:** 2026-09-28
**Modul:** [[MŠMT výkazy]] — export matriky, `/dashboard/msmt/kody-zaku`
**Soubory:** `supabase/migrations/bez migrace/127_msmt_kod_zaka_z_rodneho_cisla.sql`, `app/dashboard/msmt/kody-zaku/page.tsx`, `app/dashboard/msmt/kody-zaku/_components/KodZakaMsmtRow.tsx`, `types/database.ts`
**Commity:** `28db755` (feat(msmt): kód žáka MŠMT se doplňuje sám z rodného čísla (migrace 127))

> [!warning] Překonáno týž den migrací 128
> Premisa „KOD_ZAKA = rodné číslo" je podle metodiky MŠMT **chybná**: KOD_ZAKA patří
> do anonymizovaného souboru „a" místo rodného čísla; RČ jde jen do základního
> souboru jako RODC. Trigger a funkce z této migrace byly zrušeny, `kod_zaka_msmt` je
> nově pořadové číslo žáka. Viz [[ARCH-NOTE-2026-09-28-msmt-rodc-a-kod-zaka-poradove-cislo]].
> Platí dál: sekce 2 (SQL editor dashboardu a dollar-quoting).

---

## Přehled

Před exportem matriky pro MŠMT systém vyžadoval ručně zadaný „kód MŠMT" (KOD_ZAKA =
rodné číslo bez lomítka) pro každého žáka, přestože rodné číslo už v databázi je.
Nově se kód odvozuje z rodného čísla automaticky (migrace 127: funkce + trigger +
backfill); stránka kódů zůstává jako kontrola a ruční oprava. Vedlejším tématem bylo
spouštění migrace přes SQL editor Supabase dashboardu.

---

## 1. KOD_ZAKA z rodného čísla

### Symptom
`/dashboard/msmt` hlásil nesplněnou prerekvizitu (30 z 32 aktivních žáků bez kódu);
ředitel měl kódy opisovat ručně na `/dashboard/msmt/kody-zaku`.

### Příčina
Export XML (`app/api/msmt/xml/route.ts`, `lib/msmt-xml.ts`) i prerekvizita čtou jen
`students.kod_zaka_msmt`, který se plnil výhradně ručně (`updateKodZakaMsmt` v
`app/actions/students.ts`). Rodné číslo přitom žije v `students.birth_number` — plní
ho přijetí ze zápisu (`enrollment_applications.rodne_cislo` → migrační RPC, poslední
verze migrace 125) a čtou ho už studijní smlouva a katalogový list. Stav dat
(2026-09-28): 32 aktivních, všichni s platným RČ (10 číslic po odstranění
nečíslic), v DB jako čitelný text, ne ciphertext.

### Řešení
Migrace 127:
- `msmt_kod_z_rodneho_cisla(text)` — jen číslice, výsledek jen při přesně 10 číslicích,
  jinak NULL.
- Trigger `trg_students_fill_kod_zaka_msmt` (BEFORE INSERT / UPDATE OF
  `birth_number`, `kod_zaka_msmt`, funkce SECURITY DEFINER, EXECUTE odebrán): doplní
  prázdný kód, nebo opraví kód odvozený ze starého RČ při opravě RČ. **Ručně zadaný
  odlišný kód nepřepisuje.** Když kód z RČ drží jiný žák (UNIQUE), nic nedoplní —
  uložení žáka (např. přijetí ze zápisu) nesmí kvůli tomu spadnout.
- Backfill žáků bez kódu (DISTINCT ON + NOT EXISTS proti kolizi UNIQUE).

Stránka kódů nově u řádku upozorní „RČ v kartě žáka chybí / je neplatné / liší se od
RČ v kartě žáka". Na klienta jde jen odvozený kód, ne samotné RČ.

Export XML se neměnil — dál čte `kod_zaka_msmt`, jen už je vyplněný.

Výsledek po spuštění (aktivní žáci): `bez_kodu = 0`, `nesoulad = 0`, funkce i trigger
existují.

### Poučení
Než se po uživateli chce ruční vstup, ověřit, jestli ten údaj DB už nezná z jiného
toku (zde zápis → matrika). Odvozenou hodnotu držet v DB triggerem, ne v aplikaci —
pak ji dostanou všechny cesty zápisu (UI, RPC zápisu, ruční SQL).

---

## 2. SQL editor Supabase dashboardu a dollar-quoting

### Symptom
Spuštění migrace dvakrát spadlo na `42601: unterminated dollar-quoted string`, potřetí
„proběhlo", ale funkce v DB nebyla.

### Příčina
Do editoru se dostal **useknutý text** (končil `ELSE NULL`; za ním už jen metadata
`-- source: dashboard`, která si připojuje dashboard). Soubor na disku byl mezitím
přepsán zkrácenou verzí — nejspíš jiným editorem, který ho měl otevřený. Původní
verze navíc měla v těle funkce regex s kotvou konce řetězce (znak dolaru), což je
pro dělení příkazů v dashboardu rizikové.

### Řešení
Soubor zapsán znovu celý; těla funkcí v pojmenovaných značkách `$fn$`, regex nahrazen
kontrolou délky (žádný dolar mimo značky). Nakonec spuštěno po čtyřech samostatných
blocích (funkce → funkce triggeru → trigger → backfill), pak kontrolní dotaz.

### Poučení
- Chybová hláška dashboardu ukazuje, **co skutečně dostal** — když končí uprostřed
  těla funkce, je problém ve vloženém textu, ne v SQL.
- „Migrace proběhla" ověřovat dotazem na existenci objektů (`pg_proc`, `pg_trigger`),
  ne starým kontrolním dotazem (viz [[supabase-partial-migration]]).
- V migracích pro dashboard používat pojmenované dollar-quoting značky a vyhýbat se
  znaku dolaru v tělech/komentářích.

---

## Vedlejší nález (nezasahováno)

Komentáře ve schématu (`20260428000001_matrika.sql`) popisují `kod_zaka_msmt` jako
identifikátor pro **anonymizovaný** soubor „a", generovaný samostatně, a
`birth_number` jako údaj povinně šifrovaný na aplikační vrstvě. Praxe je jiná: KOD_ZAKA
= rodné číslo (potvrdil uživatel, stejně tak starší ARCH-NOTES 16.4) a RČ je v DB jako
čitelný text. Obojí stojí za ověření proti metodice MŠMT / rozhodnutí o šifrování;
komentáře ve schématu zatím odporují realitě.

---

## Ověření

- Kontrolní dotaz v Supabase: `bez_kodu = 0`, `nesoulad = 0`, `funkce_triggeru = 1`,
  `trigger_existuje = 1`.
- `npm run db:types` (nová funkce v typech), `tsc --noEmit` bez chyb.
- Stránka `/dashboard/msmt/kody-zaku` v prohlížeči neověřena (produkční data za
  přihlášením).

## Související

- [[ARCH-NOTE-2026-09-22-zapis-alert-student-prijat-zrusen]] — migrace 125, migrační RPC zápisu plní `birth_number`
- [[Žáci]] — matrika žáků
