# ARCH-NOTES — addendum 2026-07-08
## Ředitelský pohled na Zápis/Přestup (`/dashboard/zapis`)

### §92 — Rozsah a umístění

Postaveno rovnou kompletní (seznam + detail/rozhodnutí + export + okno
zápisu), ne jen "napřed seznam", protože se ukázalo, že celý backend
(migrace 037) je už reálně nasazený a hotový — nebyl důvod dělit to na
menší kroky.

Umístění: **`/dashboard/zapis`**, ne `/portal` (rodičovský prostor) ani
zcela mimo `/dashboard` (zaměstnanecká sekce, samostatná od `/portal` —
tohle v předchozí session nebylo jasné a stálo by za doplnění do
"architektura, na kterou dát pozor": **`/dashboard` = personál,
`/portal` = rodiče, `/zapis` = veřejnost/noví žadatelé o zápis. Tři
oddělené stromy, tři oddělené auth kontexty.**

Přístup: `role === 'director'` only — ne `has_role()` multi-role check
jako jinde. RLS (`enrollment_app_staff_read` atd.) je širší (pustí i
guide/assistant/vp), ale UI gate je záměrně přísnější. Pokud se v
budoucnu má modul otevřít i pro `vp`, stačí upravit `role ===
'director'` check na stránkách + `roles: [...]` v `AppNav.tsx`.

### §93 — DŮLEŽITÉ: migrace 037 (základ enrollment schématu) není v repu

Celé jádro modulu Zápis — `enrollment_applications`, `enrollment_guardians`,
`enrollment_decisions`, `enrollment_settings`, `enrollment_legal_rules`,
RLS politiky, RPC `enrollment_record_decision`/`enrollment_migrate_to_student`/
`enrollment_classify_age` — **není nikde commitnuté**, ani ve složce
"bez migrace". Číslo 037 je tam obsazené jiným souborem
(`037_essl_isds.sql`, eSSL/ISDS integrace).

Zjištěno až po ověření přímo v produkční DB (`\df` + `pg_get_functiondef`
přes SQL editor) — draft soubor `037_enrollment_draft.sql`, který
existuje jen lokálně u Jakuba, odpovídá 1:1 tomu, co běží v produkci,
přestože má v hlavičce `STATUS: DRAFT k diskuzi`.

**Poučení pro příště:** cokoliv, co dokumentace/paměť tvrdí o
"pravděpodobně existujícím" backendu z migrace 037, se musí ověřit
přímo v DB (`pg_proc`, `information_schema.tables`, `pg_policies`) —
repo samo o sobě není spolehlivý zdroj pravdy pro tuhle část schématu.
Stálo by za zvážení `037_enrollment_draft.sql` konečně commitnout (i se
zpětným datem/poznámkou "retroaktivně zdokumentováno"), ať se tohle
příště neopakuje.

### §94 — `enrollment_record_decision` auto-migruje na studenta

RPC podpis:
```sql
enrollment_record_decision(
  p_application_id uuid,
  p_rozhodnuti enrollment_rozhodnuti,
  p_duvod text DEFAULT NULL,
  p_cilovy_school_year text DEFAULT NULL,
  p_datum_nastupu date DEFAULT NULL
) RETURNS bigint
```

Enum `enrollment_rozhodnuti`: `prijat`, `nepryjat_kapacita`,
`nepryjat_jiny_duvod`, `odklad`, `prestup_zamitnut`, `stornovano_rodicem`,
`nedostavili_se`, `autoremedura_prijat`, `autoremedura_nepryjat`. Trigger
`trg_enrollment_sync_stav` po INSERTu do `enrollment_decisions`
aktualizuje `enrollment_applications.stav` (veřejný stav má míň hodnot
než rozhodnutí — např. `nepryjat_kapacita`/`nepryjat_jiny_duvod` oba
mapují na `nepryjat`).

**Klíčové:** pokud `p_rozhodnuti IN ('prijat', 'autoremedura_prijat')`,
funkce **sama** zavolá `enrollment_migrate_to_student(p_application_id,
v_decision_id)` — uvnitř téže transakce. Frontend proto nemá (a nemá
mít) samostatné tlačítko "Migrovat na studenta" — kliknutí na "Přijmout"
dělá vše najednou. Pokud migrace spadne (např. chybějící RÚIAN záznam
pro danou adresu), celá transakce se rollbackne — rozhodnutí se
nezapíše, žádost zůstává v `k_rozhodnuti`, dá se to bezpečně zkusit
znovu po opravě příčiny.

`enrollment_migrate_to_student` počítá `obec_bydliste_kod`/
`okres_bydliste_kod` přes JOIN na `ruian_adresni_mista`/`ruian_obce` —
tyhle tabulky existují v produkci (ověřeno), i když nejsou v repu
(stejný "bez migrace" pattern jako u §93).

### §95 — `enrollment_applications` NEMÁ sloupec `rok_zapisu`

Rok zápisu se nikde neukládá na žádost — jen se počítá za běhu
(`odvodRokZapisu()` v `app/actions/enrollment.ts`, ze
`enrollment_settings.okno_od` nebo z aktuálního data). Pro filtrování v
řediteli pohledu jsem přidal `odvodRokZapisuZDatumu()`
(`lib/enrollment/dashboard-queries.ts`) — stejná logika (podání v
září+ míří na příští kalendářní rok), ale aplikovaná na `created_at`
žádosti místo na "teď". Funguje dobře pro typickou jarní vlnu zápisů,
ale je to heuristika, ne přesný záznam — hraniční případy (pozdě
podaná žádost mimo běžné okno) se můžou zařadit špatně.

**TODO do budoucna:** zvážit přidání `rok_zapisu smallint` přímo na
`enrollment_applications` (vyplněné při vzniku žádosti, ne dopočítávané)
— odstranilo by to tuhle nejednoznačnost napořád. Nekritické, dokud
škola dělá jen jednu vlnu zápisu ročně.

### §96 — Vzor pro export a alerty

CSV export (`/dashboard/zapis/csv`) — BOM (`\uFEFF`) na začátku, jinak
Excel na Windows diakritiku špatně rozpozná. Vlastní `role==='director'`
check navíc k RLS (protože RLS by jinak pustila i další personál).

Obecná sekce **Alerty** na `/dashboard` (`AlertsWidget` v
`app/dashboard/page.tsx`) — už existovala, poháněná `system_alerts` +
jeden ad-hoc zdroj (`missingTK`, počet chybějících záznamů třídní
knihy). Přidán druhý ad-hoc zdroj (`enrollmentPending`, počet
`k_rozhodnuti`) stejným vzorem — přímý COUNT dotaz, ne zápis do
`system_alerts`. **Vzor pro budoucí alerty:** pokud přibude další zdroj
(platby, bulletin…), stačí další `get*Count()` helper + řádek v
`AlertsWidget`, žádná změna schématu potřeba. Zobrazuje se jen
uživatelům s přístupem na cílovou stránku (enrollment alert jen
`director`), ať alert neláká na odkaz, který uživatel nemůže otevřít.

### §97 — Okno zápisu (`enrollment_settings`)

Singleton řádek `id=1`, sloupce `zapis_otevren` (boolean),
`okno_od`/`okno_do` (date). RLS: `enrollment_settings_director_write`
(UPDATE, director), `enrollment_settings_staff_read` (SELECT, personál),
`enrollment_settings_public_read` (SELECT `true` — migrace 048, viz
předchozí addendum, veřejné čtení nutné, protože zájemce o zápis
potřebuje vědět, jestli je okno otevřené, ještě než má guardian účet).

RPC `enrollment_create_application` kontroluje `zapis_otevren`
server-side, ale **jen pro `p_typ = 'zapis'`** — přestup na okně
nezávisí, jde podat kdykoli. Žádná nová RPC pro editaci nebyla potřeba,
šlo o prostý UPDATE (director má write policy).

Panel na `/dashboard/zapis` (`EnrollmentWindowPanel`): manuální
přepínač, ne automatický výpočet z dat. Při zapnutí ze zavřeného stavu
(nebo když je staré `okno_do` v minulosti) se předvyplní **dnes → +2
měsíce** jako výchozí návrh, ručně přepsatelné před uložením. Bez
historie změn (vědomé rozhodnutí — nekomplikovat).

**TODO do budoucna:** zvážit automatické zavření okna (cron na
`okno_do`), pokud se ukáže, že ředitel zapomíná okno ručně zavírat po
termínu. Zatím řešeno jako čistě manuální.

### Doplnění TODO seznamu

- GitHub token použitý v této session (write access) — **zvážit rotaci/revoke**,
  prošel přes konverzaci.
- `037_enrollment_draft.sql` a doprovodné "bez migrace" soubory
  (RÚIAN import, `enrollment_settings` CREATE TABLE) — zvážit
  retroaktivní commit do repa, ať `git grep` a budoucí review mají
  úplný obrázek.
- `enrollment_applications.rok_zapisu` jako perzistentní sloupec (§95).
- Automatické zavírání okna zápisu podle `okno_do` (§97), pokud se
  ukáže potřeba.
