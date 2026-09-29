# ARCH-NOTE: Export matriky MŠMT podle ZS.025, kód žáka, ODHL/IZOP a kontrola RČ v zápisu

**Datum:** 2026-09-29
**Modul:** [[MŠMT výkazy]] — `/dashboard/msmt`, `/dashboard/msmt/udaje-zaku`, `/api/msmt/xml`; zasahuje [[Žáci]] (zápis/přestup)
**Soubory:** `lib/msmt-xml.ts`, `lib/msmt-sber.ts`, `lib/msmt-env.ts`, `lib/rodne-cislo.ts`, `app/api/msmt/xml/route.ts`, `app/dashboard/msmt/page.tsx`, `app/dashboard/msmt/_components/StahnoutXml.tsx`, `app/dashboard/msmt/udaje-zaku/page.tsx`, `app/dashboard/msmt/udaje-zaku/_components/UdajeZakaRow.tsx`, `app/actions/students.ts`, `app/actions/enrollment.ts`, `app/actions/dochazka.ts`, `app/dashboard/uzavreni-pololeti/page.tsx`, `app/zapis/[id]/_components/EnrollmentWizard.tsx`, `lib/katalogovy-list/pdf.tsx`, `lib/urazy-pdf.tsx`, `supabase/migrations/bez migrace/129_msmt_kod_zaka_rucni_hodnota.sql`, `130_msmt_odhl_izop.sql`, `131_msmt_kod_zaka_nahodny.sql`, `types/database.ts`
**Commity:** `a1db2da` (výchozí sběr + uzavření pololetí), `feeb377` (stažení přes fetch), `ff884ae` (ořezávání env), `cab1928` (RED_IZO), `d2ae2bb` (generátor ZS.025 + migrace 129), `7b3c63e` (ODHL/IZOP + stránka, migrace 130), `a9fff2c` (db:types), `b97d1db` (RČ do přihlášky), `17b01f0` (kontrola RČ v zápisu), `c3edc68` (povinné RČ + pohlaví), `ce2245e` (KOD_ZAKA náhodný, migrace 131)

---

## Přehled

Navazuje na [[ARCH-NOTE-2026-09-28-msmt-jarni-podzimni-sber]]. Cílem bylo dostat export matriky přes testovací server MŠMT (`profa.msmt.cz`). Cestou se ukázalo, že formát exportu neodpovídal MŠMT vůbec (krok 3), že v IS chybí povinné údaje ODHL/IZOP a že kód žáka pro soubor „a“ musí držet kontinuitu s předchozími sběry. Témata:

1. Oprava — výchozí sběr a uzavření pololetí.
2. Oprava — stažení XML maskovalo chybu exportu.
3. Oprava — env proměnné (bílý znak v IZO, chybné RED_IZO).
4. Nová implementace — generátor podle ZS.025 a přijatých souborů.
5. Rozhodnutí — KOD_ZAKA (kontinuita, pak náhodné pětimístné číslo).
6. Nová data — ODHL/IZOP + stránka Údaje žáků pro MŠMT.
7. Oprava RČ se propisuje do přihlášky ze zápisu.
8. Zápis — kontrola RČ, povinné RČ, kontrola pohlaví.

Plus poučení o SQL editoru Supabase dashboardu.

---

## 1. Výchozí sběr a uzavření pololetí

**Soubory:** `lib/msmt-sber.ts` (`vychoziSber`), `app/dashboard/uzavreni-pololeti/page.tsx`, `app/actions/dochazka.ts` (`getGroupsForUser`)

### Symptom
28. 9. nabízel přepínač jen „Jaro 2026“, ne „Podzim 2026“. Odkaz „Uzavřít →“ z přehledu MŠMT nepředvolil rok/pololetí a stránka nabízela jen letošní třídy.

### Příčina
- Výchozí sběr = *poslední uplynulé* RDAT — 30. 9. ještě nenastalo.
- `uzavreni-pololeti/page.tsx` četl `searchParams` synchronně; v Next 16 je to Promise → předvolba z URL se ignorovala.
- `getGroupsForUser()` vracel jen skupiny aktivního roku, ale 2. pololetí 2025/26 (podzimní OML) je vázané na loňské `group_id`.

### Řešení
Výchozí sběr = **nejbližší** RDAT (i nadcházející). `await searchParams`, `getGroupsForUser(schoolYear?)` + `key={rok}` na klientovi (změna roku = nové skupiny ze serveru).

### Poučení
Starší stránky mohou mít ještě synchronní `searchParams` — v Next 16 tiše nefungují (žádná chyba, jen `undefined`).

---

## 2. Stažení XML maskovalo chybu

**Soubor:** `app/dashboard/msmt/_components/StahnoutXml.tsx`

### Symptom
Klik na „Stáhnout“ stáhl `xml.json`, prohlížeč hlásil „web není k dispozici“.

### Příčina
`<a download>` na route, která při chybě vrací JSON `{ error }` — prohlížeč chybu „stáhne“.

### Řešení
Stažení přes `fetch`: úspěch → blob a uložení pod správným názvem, chyba → text chyby pod tlačítkem.

### Poučení
Download odkaz na API, které umí vrátit chybu, vždy přes fetch — jinak uživatel nevidí proč.

---

## 3. Env: bílý znak v IZO, chybné RED_IZO

**Soubory:** `lib/msmt-env.ts` (nový), export, přehled, PDF katalogového listu a úrazů

### Symptom
Soubor se jmenoval `Z_250002639_01.xml` (správně `Z250002639_01.xml`); stejný bílý znak byl v XML v `IZO`. V `.env.local` bylo `MSMT_RED_IZO=691012868    # komentář`, PDF dokumenty přitom používaly `691018901`.

### Příčina
Hodnota `MSMT_IZO` na Vercelu s bílým znakem na začátku (prohlížeč ho v názvu souboru nahradí podtržítkem). Dva zdroje RED_IZO s různými hodnotami.

### Řešení
`msmtEnv()` ořezává hodnoty a zahazuje případný komentář za `#`. Uživatel potvrdil správné **RED_IZO = 691018901**; jediný zdroj je `SCHOOL_RED_IZO` (výchozí 691018901), `MSMT_RED_IZO` se nečte. Nová volitelná `MSMT_TELEFON` pro hlavičku XML.

### Poučení
Hodnoty vložené do Vercelu ručně vždy `trim()`; jeden údaj = jedna proměnná.

---

## 4. Generátor podle ZS.025 (krok 3)

**Soubory:** `lib/msmt-xml.ts` (přepsán), `app/api/msmt/xml/route.ts` (přepsán)

### Symptom
Testovací server MŠMT: „Odkaz na objekt není nastaven na instanci objektu.“

### Příčina
Původní generátor (z TRD) posílal `<STATISTIKA>` s atributy, IZO/RDAT jen v hlavičce, názvy číselníků místo položek (`RAZD`, `RAST`, `RAUJ`, `RAOR`, `RAFZ`, `DELKAP`, `CJ1`…) a chybělo ~20 povinných položek (`POHLAVI`, `DAT_NAROZ`, `ROCNIK`, `TRIDA`, `KOD_VETY`…).

### Řešení
Podle `stru_ZS_025.pdf` (dodal uživatel) a **souborů, které škola MŠMT úspěšně předala** (podzim 2025, jaro 2026):
- `<Vykaz verze="ZS.025">` + hlavička (Vygen, autor, telefon, e-mail, soubor, vytvoreno), `<veta>` s vnořenými položkami, prázdné `<X/>`, data `DD.MM.RRRR`.
- Každá věta nese `RDAT`, `IZO`, `CAST` + všech 49 položek (základní) / položky ZSa (soubor „a“) — **pořadí prvků ověřeno proti přijatým souborům (shoda)**.
- Ročník, třída, způsob k datu věty (`student_education_mode`, `group_memberships` + `groups`, bez PostgREST embed); `POHLAVI` z RČ; `LET_PSD` = ročník − 1.
- Věty dělené k 1. 2., OML ve větě od 1. 2. — **potvrzeno jarním souborem 2026** (dosud převzatý předpoklad).
- `KOD_ZMEN 2` + `ZMENDAT` při příchodu z jiné školy; odchod = věta od dne po odchodu s `KOD_VETY 3`, `KOD_UKON 3`, `PRIZN_ST 7` (metodika: přestup; časové umístění **k ověření** na testovacím serveru).
- Kódy v `MSMT_KODY` (OBOR `7901C01`, JAZYK_O `10`, KSTPR `3`, JAZ1 `02/A`…) — hodnoty z přijatých souborů.
- Chybí-li v IS povinný údaj → **422 se seznamem žáků**, neúplný soubor se nevydá.

### Poučení
Nejlepší specifikace úředního formátu je **soubor, který úřad už přijal**. PDF struktura popisuje položky, ne tvar XML. U číselníků držet hodnoty z přijatých souborů, dokud nemáme oficiální číselník.

---

## 5. KOD_ZAKA — kontinuita a náhodné číslo

**Migrace:** 129, 131

### Příčina
Soubory „a“ z předchozích sběrů obsahovaly kódy **26788** a **38749**; migrace 128 je přepsala pořadovým číslem. Metodika: KOD_ZAKA „zůstává stejný během celé doby vzdělávání“. Oba kódy spárovány s RČ přes shodné údaje v přijatých souborech.

### Řešení
- **129:** trigger respektuje ruční hodnotu; oba kódy nastaveny jednorázovým UPDATE (mimo repo — obsahuje RČ).
- **131 (rozhodnutí ředitele):** „pro každé dítě náhodné, neduplicitní pětimístné číslo (preventivně pro každého, jako pravidlo)“. `msmt_novy_kod_zaka()` (10000–99999, SECURITY DEFINER), trigger přidělí chybějící kód jednou a nemění ho. Pořadová čísla (MŠMT nikdy neodešla) nahrazena; 26788 a 38749 zůstaly. Kontrola: bez kódu 0, ne-pětimístné 0, duplicity 0.

### Poučení
Identifikátor v anonymizovaných datech: náhodný, neměnný, a **před změnou schématu zjistit, co už úřad zná**.

---

## 6. ODHL / IZOP + Údaje žáků pro MŠMT

**Soubory:** migrace 130, `app/dashboard/msmt/udaje-zaku/*` (dřív `rodna-cisla`), `app/actions/students.ts` (`updateMsmtPole`), export, přehled MŠMT

### Symptom
Export odmítl 33 žáků: „chybí ODHL, IZOP“ (u jednoho i KOD_ZAH a občanství).

### Příčina
ODHL/IZOP v IS nikdy nebyly: `students.predchozi_vzdelavani` je volná poznámka (tiskne [[Katalogový list]]), `students.predchozi_skola_izo` plní zápis **názvem** školy. Škola je dosud vyplňovala mimo IS. Zápis ukládá občanství textem „ČR“, ne kódem 203.

### Řešení
- **130:** `students.msmt_odhl` (3 znaky), `students.msmt_izop` (9 číslic), kontroly tvaru.
- Doplnění 20 loňských žáků z přijatých souborů (SQL vygenerované mimo repo, obsahuje RČ); zbytek ručně.
- Stránka `/dashboard/msmt/udaje-zaku` (director-only): RČ, ODHL, IZOP, KOD_ZAH editovatelné, nabídky hodnot z přijatých souborů, u žáků ze zápisu název dosavadní školy pro dohledání IZO.
- `stprKod()` / `jeCeskeObcanstvi()`: „ČR“, „CZ“… → `203`.
- Přehled MŠMT: prerekvizita „Kompletní údaje žáků“.

### Poučení
Než použiješ sloupec pro nový účel, zkontroluj všechny zapisovatele i čtenáře — název sloupce (`predchozi_skola_izo`) nemusí odpovídat obsahu.

---

## 7. Oprava RČ se propisuje do přihlášky

**Soubor:** `app/actions/students.ts` (`updateRodneCislo`)

RČ je v IS u žáka jednou (`students.birth_number` — export, studijní smlouva, katalogový list), ale přihláška ze zápisu má vlastní kopii (`enrollment_applications.rodne_cislo`), ze které se tisknou dokumenty zápisu. Oprava na stránce MŠMT ji nově aktualizuje také (RLS `enrollment_app_director_all`). Opačný směr (rodič mění přihlášku po přijetí) se nepropisuje — záměrně.

---

## 8. Zápis — kontrola RČ, povinné RČ, pohlaví

**Soubory:** `app/actions/enrollment.ts`, `app/zapis/[id]/_components/EnrollmentWizard.tsx`, `lib/rodne-cislo.ts`

- `saveEnrollmentDite`: vyplněné RČ musí být platné (MODULO11, datum, cizinecký kód s X), sedět s datem narození a s pohlavím (měsíc +50 = dívka); ukládá se jednotně `RRMMDD/XXXX`.
- `submitEnrollmentApplication`: RČ povinné u **českého občanství** (výjimka pro cizince odvozená z pole občanství — bez nové volby a migrace); neplatné RČ z dřívějška odeslání zablokuje.
- Formulář: okamžitá nápověda pod polem, hvězdička u českého občanství.

---

## Poučení — SQL editor Supabase dashboardu

Migrace 127 i 131 spadly v editoru, i když SQL bylo v pořádku:
- 127: „unterminated dollar-quoted string“ — do editoru se dostal **useknutý text** (soubor na disku přepsal jiný editor); navíc `$` v regexu.
- 131: „syntax error at or near LANGUAGE“ — editor rozdělil hlavičku funkce; v komentářích byly **rovné uvozovky `"`**.

Pravidla (zapsaná i do paměti [[migracni-workflow]]): těla funkcí v `$fn$ … $fn$`, jinde žádný `$`; žádné rovné `"` (typografické „…“ OK); hlavička funkce na jednom řádku; „proběhla“ ověřovat dotazem na `pg_proc` / `pg_trigger`; při potížích dát migraci po blocích.

---

## Ověření

- `tsc --noEmit` bez chyb; lint bez nových chyb (dočasné `(supabase as any)` odstraněny po `db:types`).
- Generátor: syntetický žák → pořadí a názvy prvků **shodné** s přijatým jarním souborem (základní i „a“); podzimní věty, postup do vyššího ročníku a věta o odchodu podle metodiky.
- Validátor RČ na syntetických hodnotách (platné, s lomítkem, překlep, cizinec, špatný měsíc, 9 číslic, pohlaví).
- Migrace 129, 130, 131 spuštěné uživatelem, ověřené kontrolními dotazy.
- Uživatel ověřil: název souboru `Z250002639_01.xml` po opravě env.
- **Neověřeno:** stránky v prohlížeči; **výsledek testovacího serveru MŠMT s novým generátorem zatím nepřišel.**

## Vedlejší nálezy (nezasahováno)

- **Předchozí škola ve formuláři zápisu chybí** (`dosavadni_skola` nemá vstupní pole; přestupová „Současná škola“ se do žáka nepřenáší) → [[PRD-predchozi-skola-rejstrik-2026-09-29]] (našeptávač ze školského rejstříku, předvyplnění IZOP/ODHL/KOD_ZAH při přijetí).
- **Soubor „b“** (podpůrná opatření 2.–5. st., jen podzim) — generátor chybí; vzor `ZSb.22` mezi přijatými soubory.
- **KSTPR pro cizince**, **PRIZN_ST opakování ročníku** (IS neeviduje; `LET_PSD` = ročník − 1).
- **Změna identifikátoru** (cizinec X-kód → české RČ) by vyžadovala větu s `KOD_ZMEN 7` — export ji neumí.

## Související

- [[ARCH-NOTE-2026-09-28-msmt-jarni-podzimni-sber]] — krok 2
- [[ARCH-NOTE-2026-09-28-msmt-rodc-a-kod-zaka-poradove-cislo]] — krok 1 (RODC / KOD_ZAKA)
- [[PRD-predchozi-skola-rejstrik-2026-09-29]] — navazující zadání
- [[migracni-workflow]] — pravidla pro migrace v dashboardu
