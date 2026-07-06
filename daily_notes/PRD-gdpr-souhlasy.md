# PRD — Modul GDPR [[Souhlasy]] (IS Nilsson)

**Repo:** `jakubmracek/nilsson` · **Stav:** návrh k implementaci · **Cílový soubor v repu:** `docs/PRD-gdpr-[[Souhlasy]].md`

---

## 1. Cíl

Evidovat a spravovat [[Souhlasy]] zákonných zástupců se zpracováním osobních údajů [[Žáci]] **prokazatelně** — kdo, za koho, k jakému účelu, podle jaké verze textu, kdy uděleno a kdy případně odvoláno — aby škola unesla důkazní břemeno podle čl. 7 odst. 1 GDPR. Sběr probíhá výhradně elektronicky v [[Rodičovský portál]]; personál má pouze čtecí [[Přehled]].

## 2. Rozsah (v1)

**V rozsahu:**
- Rodičovská větev: udělování a odvolávání [[Souhlasy]] přes přepínač v [[Rodičovský portál]].
- Personální větev: read-only [[Přehled]] stavů napříč [[Žáci]] a účely.
- Verzování textů [[Souhlasy]] na úrovni databáze.
- Propsání aktuálně platného **Nesouhlasu** na kartu [[Žáci]] (modul [[Žáci]]) a u poradenského účelu i do modulu [[Výchovný poradce (VP)]].

**Mimo rozsah (v1, ponecháno otevřené pro budoucnost):**
- Zaměstnanecké GDPR [[Souhlasy]] (jiný subjekt, jiné účely).
- [[Souhlasy]] přetrvávající po ukončení [[Docházka]] (`indefinite`, `years_after_leaving`) — datový typ je připraven, ale žádný takový účel se neseeduje.
- Papírová evidence [[Souhlasy]]. Administrativa je čistě elektronická.
- Notifikační e-maily („máte nevyřízené [[Souhlasy]]"). Modul neposílá žádné maily.
- Editace textů [[Souhlasy]] ve frontendu. Provádí se na úrovni DB.

## 3. Aktéři

- **Zákonný zástupce (guardian):** přihlášený v [[Rodičovský portál]] (magic-link), uděluje/odvolává [[Souhlasy]] za své dítě. Každé dítě má alespoň jednoho zástupce s e-mailem.
- **Personál (staff):** libovolná staff role, read-only [[Přehled]]. Žádný zápis za rodiče.

## 4. Klíčová rozhodnutí (zafixovaná)

### 4.1 Subjekt a granularita
Subjektem [[Souhlasy]] je **žák**. Záznam se ukládá per trojici **(zástupce, žák, definice [[Souhlasy]])**. „Stav za dítě" se z jednotlivých vyjádření zástupců dopočítává agregací.

### 4.2 Agregační pravidlo (stav za dítě)
1. Jakýkoli explicitní **Nesouhlas** kteréhokoli zástupce → výsledně **Nesouhlas** (přebíjí).
2. Jinak alespoň jeden **Souhlas** → výsledně **Souhlas**.
3. Jinak **Neuděleno**.

Odůvodnění: rodičovská odpovědnost se vykonává ve vzájemné shodě (§ 876 OZ); při neshodě je pro školu bezpečné nezveřejňovat. Na kladný [[Souhlasy]] proto stačí jeden zástupce, nesouhlas jediného zástupce ale blokuje.

### 4.3 Sběr a stavy
- Sběr výhradně digitálně, trojpolový přepínač v [[Rodičovský portál]]: **souhlasím / nesouhlasím / (výchozí) neuděleno**.
- **Neuděleno** = pro danou dvojici (zástupce, definice) neexistuje žádný záznam. Není to ukládaný stav.
- Jakmile zástupce poprvé klikne, vždy existuje záznam se stavem `granted` nebo `denied`.
- **Odvolání [[Souhlasy]] = nový řádek `denied`.** Stejně tak změna názoru kterýmkoli směrem = nový řádek. Stavy se nikdy nepřepisují (UPDATE) — tabulka záznamů je **append-only**, aktuální stav je poslední řádek pro danou dvojici.

### 4.4 Verzování
- Každý **účel** má stabilní identitu (`code`). Pod jedním kódem existuje 1..n **verzí definice** (text, účel, doba platnosti, příznaky).
- Každý **záznam vyjádření** odkazuje FK na **konkrétní verzi definice**, ke které se zástupce vyjádřil — to je jádro prokazatelnosti.
- Změny textu i přidávání nových účelů se dělají **na úrovni DB**, nikdy ve frontendu.
- **Politika nové verze:** stará verze zůstává **účinná**, dokud se zástupce nevyjádří k nové. [[Rodičovský portál]] u takového účelu zobrazí výzvu k novému vyjádření, ale dosavadní stav z předchozí verze platí až do okamžiku nového vyjádření.

### 4.5 Doba platnosti
Na definici je `duration_type`:
- `while_enrolled` — platí, dokud je dítě žákem školy; konec řídí den ukončení [[Docházka]] (ne pevné datum).
- `fixed_date` — pevné datum; při udělení se **zamrazí** `valid_until` na záznam, aby pozdější změna definice zpětně neposouvala již udělené [[Souhlasy]].
- `indefinite` — bez časového omezení (v1 se neseeduje).
- `years_after_leaving` — N let po ukončení [[Docházka]] (v1 se neseeduje).

V seedu v1 mají **všechny účely typ `while_enrolled`**.

### 4.6 Architektura zápisu/čtení
- **Guardian větev:** čtení i zápis přes **SECURITY DEFINER RPC** (PostgREST `.from()` v SSR kontextu neprotlačí rodičům JWT správně pro RLS — kanonický vzor dle ARCH-NOTES sekcí 50–52).
- **Staff větev:** čtení přes `has_role()` RLS (SECURITY DEFINER + STABLE). **Read-only** ve v1.
- Tabulky: **FORCE RLS** všude; append-only pro vrstvu vyjádření; `set_updated_at` tam, kde dává smysl (definice).

### 4.7 Cross-module propsání
- **Modul [[Žáci]] (karta [[Žáci]]):** zobrazí se **aktuálně platný explicitní Nesouhlas** (`denied`). Neuděleno ani expirovaný [[Souhlasy]] se na kartu netlačí.
- **Modul [[Výchovný poradce (VP)]] (poradenství):** aktuálně platný Nesouhlas u účelu `counseling_special` (zvláštní kategorie, čl. 9 GDPR) se propíše do [[Výchovný poradce (VP)]] modulu, aby bylo při poskytování poradenských služeb zřejmé, že [[Souhlasy]] chybí/byl odepřen. Vazba na `vp_student_care`.

## 5. Účely k naseedování (zdroj: souhlasový formulář ZŠ Vilekula)

| # | Kód | Účel | `duration_type` | `special_category` |
|---|-----|------|-----------------|--------------------|
| 1 | `name_premises` | Zveřejnění jména a příjmení v prostorách školy, ve školním časopise, v místním tisku / zpravodaji za účelem prezentace činnosti školy | `while_enrolled` | ne |
| 2 | `name_website` | Zveřejnění jména a příjmení na oficiálních webových stránkách školy | `while_enrolled` | ne |
| 3 | `media_website` | Pořizování a zveřejnění fotografií, zvukových a obrazových záznamů na oficiálních webových stránkách školy | `while_enrolled` | ne |
| 4 | `media_instagram` | Pořizování a zveřejnění fotografií, zvukových a obrazových záznamů na oficiálním profilu na Instagramu | `while_enrolled` | ne |
| 5 | `counseling_special` | Zpracování osobních údajů a zvláštních kategorií osobních údajů pro poskytování poradenských služeb ([[Výchovný poradce ([[Výchovný poradce (VP)]])]], psycholog, speciální pedagog, asistent pedagoga, metodik prevence), vč. doporučení ŠPZ | `while_enrolled` | **ano** |

Pořadí v tabulce odpovídá pořadí ve formuláři a použije se jako výchozí `sort_order` v [[Rodičovský portál]].

**Poznámky k textům:**
- Pověřenec pro ochranu osobních údajů (DPO): Mgr. Jana Švecová, jana.svecova@zsvilekula.cz. Do modulu se nemodeluje samostatně; lze ji uvést v textu definice.
- Znění [[Souhlasy]] musí připustit **elektronické odvolání** v [[Rodičovský portál]] (administrativa je čistě elektronická), nikoli pouze písemné odvolání přes pověřence.

## 6. Konceptuální datový model

> Přesné názvy sloupců a typy se finalizují po kontrole stávajícího schématu Supabase (`guardians`, `students`, `student_education_mode`, auto-link v `portal/layout.tsx`). Níže je konceptuální vrstva.

- **`consent_definitions`** — verzovaná definice účelu.
  - `code` (stabilní identita účelu), `version`, `title`/`body` (text), `duration_type`, `special_category`, `requires_reconsent` (zda materiální změna vynucuje nové vyjádření), `sort_order`, `is_active`/účinnost verze, `set_updated_at`.
  - Aktivní verze účelu = nejnovější účinná verze daného `code`.
- **`consent_records`** — append-only vrstva vyjádření.
  - FK na konkrétní verzi definice, FK na [[Žáci]], FK na zástupce, `status` ∈ {`granted`,`denied`}, `decided_at`, `decided_by` (guardian user_id), případně zamražené `valid_until` u `fixed_date`.
  - Aktuální stav dvojice (zástupce, definice, žák) = poslední řádek dle `decided_at`.
- **Odvozený stav za dítě** — view nebo RPC, který nad `consent_records` aplikuje agregační pravidlo (4.2) a vrací třístavový výsledek pro kartu [[Žáci]] a [[Rodičovský portál]].

## 7. Funkční požadavky

**[[Rodičovský portál]] (guardian):**
- FR-G1: Zobrazit seznam aktivních účelů (dle `sort_order`) a u každého aktuální vyjádření přihlášeného zástupce za dané dítě (granted / denied / neuděleno).
- FR-G2: Umožnit překlik na souhlasím / nesouhlasím; každý překlik zapíše nový append-only řádek.
- FR-G3: Pokud existuje novější verze definice, než ke které se zástupce naposledy vyjádřil, zobrazit výzvu k novému vyjádření; dosavadní stav zůstává účinný do nového vyjádření.
- FR-G4: Veškerý zápis i čtení přes SECURITY DEFINER RPC.

**Personál (staff):**
- FR-S1: Read-only [[Přehled]] stavů s filtrem per žák a per účel.
- FR-S2: Export pro doložení (kdo, za koho, jaký účel, jaká verze, kdy uděleno/odvoláno).

**Cross-module:**
- FR-X1: Na kartě [[Žáci]] ([[Žáci]]) zobrazit aktuálně platný explicitní Nesouhlas (agregovaně dle 4.2).
- FR-X2: Ve [[Výchovný poradce (VP)]] modulu signalizovat aktuálně platný Nesouhlas u `counseling_special`.

## 8. Nefunkční požadavky a prokazatelnost

- Append-only historie vyjádření (žádné UPDATE/DELETE stavů).
- Každý záznam váže vyjádření na konkrétní verzi textu.
- Ukládá se časové razítko a identita zástupce. IP/User-Agent se v1 neukládá.
- FORCE RLS všude; guardian přístup výhradně přes RPC; staff čtení přes `has_role()`.

## 9. Otevřené body pro fázi návrhu schématu

- Ověřit reálné názvy/typy v `guardians`, `students`, `student_education_mode`; způsob auto-linku guardian `user_id` v `portal/layout.tsx`.
- Zjistit, zda už neexistuje jakákoli consent tabulka/sloupec a stav ARCH-NOTES (nad sekci 52).
- Navrhnout konkrétní RPC (čtení stavu za dítě, zápis vyjádření, staff [[Přehled]]) a migraci v souladu s konvencemi (`createSupabaseServerClient()` async, `school_year` TEXT, atd.).
