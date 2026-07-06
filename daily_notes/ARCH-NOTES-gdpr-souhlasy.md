## Sekce NN — Modul GDPR [[Souhlasy]]

> Migrace `026_gdpr_consents.sql`. Go-live společně s ostatními moduly (září 2026).
> Číslo sekce přiřaď podle nejvyšší stávající.

### Účel a větve

Evidence [[Souhlasy]] zákonných zástupců se zpracováním osobních údajů [[Žáci]], prokazatelně (čl. 7/1 GDPR). Dvě větve: **guardian** (rodič uděluje/odvolává v [[Rodičovský portál]]) a **staff** (read-only [[Přehled]]). Sběr je výhradně digitální — žádná papírová evidence, žádné maily z tohoto modulu.

`guardians.gdpr_consent_at` / `gdpr_consent_version` jsou [[Souhlasy]] *samotného rodiče* s podmínkami [[Rodičovský portál]] — ortogonální věc, modulu se netýká a nemění se.

### Drop legacy

Stará tabulka `gdpr_consents` (nullable guardian/student, update-in-place `granted`+`revoked_at`, volný text typu/verze) byla **prázdná a bez odkazů v kódu** → v migraci `DROP TABLE`. S novým modelem byla nekompatibilní, rename na `_legacy` postrádal smysl.

### Datový model

**`consent_definitions`** — verzovaná definice účelu. `code` = stabilní identita účelu, pod ním 1..n verzí (`version`). Aktivní verze = `is_active` (partial unique index `uq_consent_def_active_code ON (code) WHERE is_active` garantuje jednu aktivní verzi na code). Pole: `duration_type` (CHECK `while_enrolled` / `fixed_date` / `indefinite` / `years_after_leaving`), `duration_years` (jen years_after_leaving), `fixed_until` (jen fixed_date), `special_category`, `requires_reconsent`, `legal_basis`, `sort_order`. CHECK `ck_consent_def_duration` hlídá konzistenci duration_type ↔ pomocná pole. `updated_at` přes konvenční `set_updated_at`.

**`consent_records`** — append-only vrstva vyjádření. FK `definition_id` míří na **konkrétní verzi** (jádro prokazatelnosti), `status` ∈ {`granted`,`denied`}, `decided_at`, `decided_by` (DEFAULT `auth.uid()`), `valid_until` (zamraženo jen u fixed_date). Index `(student_id, guardian_id, definition_id, decided_at DESC)`.

### Append-only — dvojité jištění

Žádná UPDATE/DELETE policy **a** trigger `consent_records_no_mutate` (BEFORE UPDATE OR DELETE → `RAISE EXCEPTION`), který zařve i na SECURITY DEFINER cestě. Odvolání [[Souhlasy]] = nový řádek `denied`, nikdy úprava. Aktuální stav dvojice (zástupce, code) = poslední řádek dle `decided_at`.

### Zápis jen přes RPC

`consent_records` **nemá INSERT policy**. Jediná zapisovací cesta je `set_consent` (SECURITY DEFINER, owner postgres → BYPASSRLS přebíjí FORCE RLS, identický vzor jako `reserve_tripartita_slot`). Přímý `.from().insert()` klienta neprojde. Editace textů a zakládání nových verzí v `consent_definitions` se dělá **na úrovni DB** (migrace/admin) — proto ani tam nejsou write policy.

### RLS

FORCE RLS na obou tabulkách. `consent_definitions`: SELECT pro personál (`current_staff_role() IS NOT NULL`) i rodiče (`is_guardian() AND is_active`). `consent_records`: SELECT pro personál (všichni) a pro vlastní řádky rodiče (`guardian_id = current_guardian_id()`).

### Čtyři RPC

- `get_consents_for_guardian(p_student_id)` — aktivní účely + vlastní stav přihlášeného rodiče + `needs_reconsent`. Guard: `current_guardian_id()` + ověření legal-rep vazby na [[Žáci]].
- `set_consent(p_definition_id, p_student_id, p_status)` — vrací textový stav (`ok` / `not_guardian` / `invalid_status` / `not_your_child` / `definition_not_found` / `definition_not_active`). Ověří legal-rep vazbu a aktivnost definice, u fixed_date zamrazí `valid_until`.
- `get_consent_overview(p_school_year)` — staff read-only, agregovaný stav per žák × účel. Guard: `current_staff_role() IS NOT NULL`.
- `get_student_consent_state(p_student_id)` — sdílená, agregovaný třístav per účel pro jednoho [[Žáci]]. Guard: personál **nebo** zástupce [[Žáci]] (`guardian_can_access_student`). Používá karta [[Žáci]] i [[Výchovný poradce (VP)]].

### Agregační pravidlo (stav za dítě)

`bool_or` nad **posledním** vyjádřením každého legal-rep zástupce (`DISTINCT ON (code, guardian_id) ORDER BY decided_at DESC` — napříč verzemi vyhrává nejnovější klik):

1. jakýkoli explicitní `denied` → **denied** (přebíjí),
2. jinak aspoň jeden `granted` → **granted**,
3. jinak **none** (neuděleno).

Bezpečná interpretace dle § 876 OZ (rodičovská odpovědnost ve shodě): na kladný [[Souhlasy]] stačí jeden zástupce, nesouhlas jediného blokuje.

### Doba platnosti

`while_enrolled` se neřídí datem, ale `students.status = 'active'` (konzistentní s `get_students_in_school_year`, `generate_bozp_alerts`). `valid_until` se počítá/zamrazuje **jen** u `fixed_date`. Typy `indefinite` a `years_after_leaving` jsou v modelu připravené, ale v seedu se nepoužívají.

### Verzování textu

Stará verze zůstává **účinná**, dokud se rodič nevyjádří k nové. `needs_reconsent` = rodič se vyjádřil ke starší verzi a existuje novější (`responded_version < active_version`); [[Rodičovský portál]] pak zobrazí výzvu, ale dosavadní stav platí dál.

### Trojpolový přepínač — pozor

`set_consent` přijímá **jen** `granted`/`denied`. „Neuděleno" je pouze výchozí stav (absence řádku), **nelze ho zvolit zpět**. UI proto segment Neuděleno po prvním vyjádření deaktivuje. Žádný stav `withdrawn` neexistuje — odvolání = nový `denied`.

### Legal-rep platnost — sjednoceno

Všude v modulu: `je_zakonny_zastupce = true AND (platnost_do IS NULL OR platnost_do >= CURRENT_DATE)` — varianta z `bulletin_resolve_recipients` / `reserve_tripartita_slot` / `get_tridni_kniha_for_guardian`. Pozor na pre-existující nekonzistenci: `guardian_can_access_student()` testuje jen `platnost_do IS NULL` (přísnější). Portálová stránka `[[Souhlasy]]` replikuje mírnější podmínku už v dotazu na děti, aby `get_consents_for_guardian` nedostal [[Žáci]], kterého by RPC odmítl (jinak `Promise.all` spadne).

### Cross-module

- **FR-X1 (karta [[Žáci]], modul [[Žáci]]):** `<StudentConsentNotice studentId={student.id} />` — vypíše všechny aktuálně platné `denied`.
- **FR-X2 ([[Výchovný poradce (VP)]] detail):** `<StudentConsentNotice studentId={care.student_id} onlyCodes={['counseling_special']} />`. **Jiný [[Souhlasy]]** než `missing_souhlas_zz` v `generate_vp_alerts()` — ten je [[Souhlasy]] ZZ s podpůrnými opatřeními v checklistu (`dokumenty->'souhlas_zz'`), nemíchat.
- Komponenta `app/[[Přehled]]/_components/StudentConsentNotice.tsx` je server-side, čte `get_student_consent_state`, filtruje `denied` (volitelně přes `onlyCodes`), při žádném platném nesouhlasu vrací `null`.

### Seed (5 účelů, verze 1)

`name_premises`, `name_website`, `media_website`, `media_instagram` — `while_enrolled`, `legal_basis = 'GDPR čl. 6 odst. 1 písm. a)'`. `counseling_special` — `while_enrolled`, `special_category = true`, `legal_basis = 'GDPR čl. 9 odst. 2 písm. a)'` (poradenské služby, vč. doporučení ŠPZ). Pořadí = `sort_order` 1–5.

### Frontend konvence

- [[Rodičovský portál]]: stone paleta + `dark:` varianty, akcent orange-500, server wrapper + client komponenta (vzor Tripartita), browser klient `createClient()` z `@/lib/supabase`.
- [[Přehled]]: gray paleta **bez** `dark:` (vzor [[Výchovný poradce (VP)]]), `CURRENT_SCHOOL_YEAR` z `lib/config`.
- Alias `@/` → kořen projektu (`@/app/...` = `./app/...`).
- Datová vrstva `lib/consents.ts` zatím přes `(supabase as any).rpc(...)` — viz TODO.
- Navigace: [[Rodičovský portál]] desktop (`PortalNavLink`) + bottom (`PortalBottomNav`, 7. položka); [[Přehled]] `components/nav/AppNav.tsx` (`bottomNav: false`, role = všechny → spadne do „Více" draweru).

### TODO

- Přegenerovat Supabase typy (`npx supabase gen types …`) → odstranit `(supabase as any)` casty v `lib/consents.ts` a stránkách.
- Staff [[Přehled]]: filtrování per žák/účel a export (PRD je zmiňoval jako možnost, v1 jen matice).
- Případné zaměstnanecké [[Souhlasy]] a `indefinite`/`years_after_leaving` účely — model je připravený, neseedováno.
