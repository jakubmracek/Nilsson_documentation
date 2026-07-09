# ARCH-NOTES — addendum 2026-07-09
## Modul Přihlášky do školní družiny (migrace 056–058)

Navazuje na §1–91 (`ARCH-NOTES-addendum-2026-07-07.md`, enrollment
frontend + smoke test) a na dvě navazující session ze **stejného dne**
7-08, které si číslovaly sekce nezávisle na sobě:

> ⚠️ **Kolize číslování, kterou je potřeba vyřešit při slučování do
> hlavního dokumentu:** `ARCH-NOTES-addendum-2026-07-08.md` existuje ve
> **dvou verzích** se stejným rozsahem §92–§98, ale jiným obsahem —
> jedna z ranní session "Bezpečnostní patche" (migrace 049–055,
> Security Advisor), druhá z odpolední session "Enrollment, admin
> funkce pro ředitele" (migrace 037 chybí v repu, auto-migrace na
> studenta, `rok_zapisu`). Než je sloučíš do jednoho živého dokumentu,
> jedna z nich musí být přečíslovaná. Tahle session pokračuje od
> **§99**, aby se kolize dál nekumulovala.

---

## §99 — Migrace 049–055 (Security Advisor) nejsou v repu

Při přípravě téhle session jsem procházel `supabase/migrations/bez
migrace/` a očekávaná čísla 049–055 (Security Advisor RLS/grant fixy,
zmíněné v ARCH-NOTES-addendum-2026-07-08.md ze session "Bezpečnostní
patche") tam **nejsou** — číselná řada v repu skáče rovnou z `048` na
`056` (moje nová migrace). Je to stejný vzor, jaký zdokumentoval §93
(migrace `037` enrollment jádra chybí v repu) — potvrzuje se podruhé,
že "bez migrace" složka v repu **není spolehlivý zdroj pravdy** o tom,
co skutečně běží na produkci; produkční DB je vždy třeba ověřit přímo.

PRD k dnešní session správně počítal s tím, že další volné číslo je
"56+" (bod 3 v sekci 11), takže volba `056` byla bezpečná — ale stálo
by za to při příští příležitosti retroaktivně commitnout i 037 a
049–055 (existující TODO z předchozích addend), ať tahle mezera
nenarůstá donekonečna a `git grep` přes migrace zůstává použitelný.

---

## §100 — GDPR: `gdpr_consents` je mrtvý název, PRD na něj ještě odkazoval

PRD `PRD-TRD-druzina-prihlasky-2026-07-08.md`, sekce 3.5, navrhoval
`ALTER TABLE gdpr_consents ADD CONSTRAINT ... consent_type CHECK (...
'druzina_provoz')`. Tahle tabulka **neexistuje** — migrace `035` (`035_gdpr_consents.sql`)
ji `DROP`la a nahradila modelem `consent_definitions` (verzované,
aktivní/neaktivní účely) + `consent_records` (append-only vyjádření
rodičů), s RPC `get_consents_for_guardian` / `set_consent` /
`get_consent_overview` / `get_student_consent_state`.

**Poučení:** i dokument napsaný ve stejné konverzaci jako předchozí
práce (PRD cituje "TRD Addendum eSSL v2.6 (migrace 036/037)" jako
kontext) může zaostávat za skutečným stavem schématu, pokud vznikl bez
čerstvého pohledu do repa. Řešení v migraci `056`: nový řádek do
`consent_definitions` (`code = 'druzina_provoz'`), zápis přes stávající
`set_consent()` RPC — žádná nová tabulka ani RPC pro souhlas nebyly
potřeba, jen správné namapování na aktuální model.

Pokud se tenhle vzor (PRD navrhuje `ALTER` na tabulku, která
mezitím zanikla) objeví znovu, je to signál, že PRD dokumenty by měly
mít explicitní "ověřeno proti aktuálnímu schématu k datu X" hlavičku,
ne jen odkaz na číslo migrace.

---

## §101 — Sdílená RPC pro vytvoření pohledávky, volaná ze dvou míst

`druzina_vytvorit_pohledavku(p_student_id, p_school_year)` (migrace
`058`) je první případ v Nilssonu, kdy je vytvoření `payment_obligations`
řádku vytažené do samostatné `SECURITY DEFINER` RPC volané jak
z automatizovaného flow (schválení žádosti), tak z ručně vyvolané
akce (`enrollStudent()` — ruční dohlášení ředitelem), se sdílenou
ochranou proti duplicitě (`ON CONFLICT (student_id, school_year) WHERE
type = 'druzina' DO NOTHING`, partial unique index `uq_po_druzina_student_year`).

Dosud `createObligations()` v `payments.ts` generovala SS kód i
insert vždy jen z jednoho místa (ruční akce ředitele v UI). Vzor "jedna
DB-level RPC, dvě TS volající místa" je vhodný kdykoli budoucí modul
potřebuje pohledávku vytvářet symetricky z automatizovaného i ručního
flow — např. budoucí obědy/akce s podobnou dualitou.

**SS kód prefix registry** (pro orientaci při přidávání dalších typů
pohledávek): `10` = lunch, `70` = tuition, `20` = event/donation,
`30` = druzina (nově). Prefix + `YYYYMM` + 2místné pořadové číslo,
inkrementované s `pg_advisory_xact_lock` per typ+měsíc.

---

## §102 — eSSL open_spis konečně v repu, ne jen v produkci

`enrollment_essl_open_spis` (volaná z `app/actions/enrollment.ts:527`)
**není nikde v repu** — ověřeno `grep` přes celý strom migrací, existuje
jen jako živá funkce v produkční Supabase (stejný vzor jako §93/§99).
Nová `druzina_prihlaska_odeslat` (migrace `056`) plní analogickou roli
pro modul družiny, ale **je committnutá** hned od začátku — vzor
k následování pro budoucí eSSL-integrující RPC, ať se mezera z §93/§99
dál nerozšiřuje o nové případy.

---

## §103 — GitHub fine-grained PAT: read-only token projde clone, ne push

Token použitý na začátku téhle session úspěšně naklonoval repo
(`git clone`, čte přes `git-upload-pack`), ale `git push`
(`git-receive-pack`) vracel `401 Invalid username or token` — potvrzeno
`GIT_CURL_VERBOSE=1`, ne problém s formátem URL (zkoušeny 3 varianty:
`TOKEN@`, `TOKEN:@`, `x-access-token:TOKEN@`, všechny stejný 401 na
receive-pack). Příčina: token měl u repa nastavené jen **Contents:
Read-only** oprávnění (fine-grained PAT), ne **Read and write**.

**Poučení pro příště:** pokud se má v session i pushovat (ne jen číst
repo pro kontext), stojí za to hned na začátku ověřit scope tokenu
(`Contents: Read and write` v nastavení fine-grained PAT), místo
diagnostiky až při selhání push na konci session.

---

## Shrnutí migrací této session

| Migrace | Obsah |
|---|---|
| 056 | `druzina_prihlasky`, `druzina_prihlaska_vyzvedavajici`, ALTER `druzina_enrollments` (+dny_dochazky, odchod_*), `druzina_vyzvedavajici`, nový consent `druzina_provoz`, RPC `druzina_prihlaska_odeslat` / `druzina_prihlaska_stornovat` |
| 057 | RLS politiky pro všechny tabulky z 056 |
| 058 | `payment_obligations` ALTER (+`druzina` typ, unique index), RPC `druzina_vytvorit_pohledavku`, RPC `druzina_prihlaska_rozhodnout` |

## TODO do budoucna

1. Retroaktivně commitnout migrace `037` (enrollment jádro, §93) a
   `049–055` (Security Advisor, §99) do repa — mezera se dál
   neprohlubuje, ale pořád existuje.
2. Sjednotit dvě verze `ARCH-NOTES-addendum-2026-07-08.md` do jednoho
   souboru s jedním číslováním (viz varování nahoře).
3. Notifikace rodičům o rozhodnutí (přijato/zamítnuto) — vědomě mimo
   scope této session (PRD bod 11.2), řešit až v dalším kole.
4. Zvážit `students.pohlavi` sloupec (propojeno s podobným dluhem už
   zapsaným u modulu Zápis) — u družiny se pohlaví nesbírá vůbec, takže
   se tenhle dluh dál netýká, jen připomínka příbuzného TODO.
