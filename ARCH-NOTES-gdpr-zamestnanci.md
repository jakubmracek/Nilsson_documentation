## Sekce NN+1 — GDPR souhlasy: zaměstnanecká větev

> Migrace `027_staff_consents.sql`. Navazuje na sekci o GDPR souhlasech (žákovská větev, migrace 026). Číslo sekce přiřaď podle nejvyšší stávající.

### Princip

Souhlasy zaměstnanců se zpracováním osobních údajů. Subjekt = **jeden zaměstnanec** (žádná agregace přes víc osob jako u žáků). Zaměstnanec uděluje sám za sebe v **Můj profil**; přehled za všechny vidí **jen ředitel** v **Správa školy**. Žádné cross-module propsání — stačí ředitelský přehled.

### Sdílené definice, oddělené records

Rozhodnutí: `consent_definitions` se **sdílí** (text, verzování, doba, append-only logika jsou identické), records se **oddělují**. `consent_definitions` dostal `subject_type` (`student` / `staff`, default `student` → stávajících 5 řádků = student). Nová tabulka `staff_consent_records` (FK na definici + `staff_id`, bez student/guardian). `consent_records` (žáci) zůstává beze změny.

### duration_type + while_employed

Přidán `while_employed` = `staff.employment_end IS NULL OR employment_end >= CURRENT_DATE` (analogie `while_enrolled`/`status='active'`). Retenční doložka ze souhlasu („uchování již zveřejněných údajů po dobu trvání účelu prezentace") **není zvláštní stav** — žije v textu definice. Oba CHECKy bylo nutné dropnout a znovu vytvořit pojmenované: inline column check z 026 měl auto-název `consent_definitions_duration_type_check`, plus `ck_consent_def_duration` rozšířen o `while_employed` ve větvi „oba NULL".

### ⚠ Kritická oprava žákovské větve

Přidání `subject_type` znamená, že **žákovská RPC a policy by jinak propustila zaměstnanecké definice rodičům**. Migrace 027 proto doplnila `subject_type = 'student'` do:
- `get_consents_for_guardian`, `get_consent_overview`, `get_student_consent_state` (CTE `active_defs`),
- guardian SELECT policy `consent_def_select_guardian` (přímé čtení).

Při jakékoli další práci s definicemi platí: **každý dotaz na „aktivní definice" musí filtrovat `subject_type`**, jinak větve protékají mezi sebou.

### staff_consent_records

Append-only — znovu používá trigger funkci `consent_records_no_mutate()` z 026. Klíč na `staff_id`, `status` granted/denied, `decided_at`, `decided_by` (DEFAULT `auth.uid()`), `valid_until` (jen fixed_date). **Bez agregace** — stav = poslední řádek pro (staff, code). FORCE RLS: SELECT vlastní (`staff_id = current_staff_id()`) + ředitel (`is_director()`). Žádná INSERT/UPDATE/DELETE policy → zápis jen přes `set_staff_consent`.

### RPC

- `get_my_staff_consents()` — aktivní zaměstnanecké účely + vlastní stav + `needs_reconsent`. Guard: `current_staff_id()`.
- `set_staff_consent(p_definition_id, p_status)` — self (žádné „za koho"). Hlídá `subject_type='staff'` (→ `wrong_subject`) a aktivnost definice. Textový stav jako u žáků.
- `get_staff_consent_overview()` — guard `is_director()`, jen zaměstnaní (`employment_end`). Matice zaměstnanec × účel, bez agregace.

### staff_role bez vychovatele

Enum `staff_role` = director / vp / guide / assistant / readonly. **`vychovatel` v enumu není** — žije jen v `staff_roles` junction (přes `has_role`). Zaměstnanecká RPC se proto opírají o `current_staff_id()` / `is_director()`, ne o porovnání role enumu.

### Frontend

- `lib/staff-consents.ts` — samostatný modul, sdílí typy z `lib/consents.ts` (nesahá do něj). Tři obálky, opět `(supabase as any).rpc(...)`.
- **Můj profil** (`app/dashboard/muj-profil`) — dostupné všem rolím, self-service trojpolový přepínač (bez výběru osoby), gray paleta, vzor VP. Server action `app/actions/staff-consents.ts`.
- **Správa školy** (`app/dashboard/sprava-skoly`) — director-only rozcestník, zatím přehled souhlasů zaměstnanců (matice, doplní se sloupce při dalších účelech). **Dvojí pojistka**: stránka kontroluje roli + RPC guarduje na DB.
- `AppNav`: Můj profil (role = všechny vč. vychovatel), Správa školy (role = director). Ikony recyklované (`Icons.students`, `Icons.lock`).

### Seed

Jeden účel `staff_media` (foto/AV zaměstnance, web + Instagram dohromady — na rozdíl od žáků, kde byl web a IG zvlášť), `subject_type='staff'`, `while_employed`, `special_category=false`, `legal_basis = 'GDPR čl. 6 odst. 1 písm. a)'`, text vč. retenční doložky.

### TODO (přetrvává z 026)

- Přegenerovat Supabase typy → odstranit `(supabase as any)` casty v obou consent vrstvách.
- Případné další zaměstnanecké účely — model i přehled je unesou bez změny schématu.
