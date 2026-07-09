# ARCH-NOTES Addendum — 2026-07-07
# Enrollment (Zápis/Přestup) modul: dokončení frontendu, RLS opravy, produkční nasazení

Navazuje na §1–78 (poslední: ARCH-NOTES-addendum-2026-07-03.md, eSSL frontend).
Tahle session dokončila zbývající dvě stránky enrollment frontendu
(`stav`, `pripojit`), nasadila migrace 043–048 a prošla kompletní
end-to-end smoke test na produkci — s šesti reálnými produkčními bugy
objevenými a opravenými cestou. Zapsáno v jednom addendu, protože nálezy
na sebe navazují (jeden test odkryl další).

**Poznámka k umístění tohohle souboru:** `documentation/` (starý
konvenční adresář pro ARCH-NOTES) byl v commitu `aafdac6` nahrazen
gitlink odkazem na `Nilsson_documentation` jako submodule — ale
`.gitmodules` neexistuje, takže submodule nemá registrovanou URL a
zůstává trvale prázdný (i ve Vercel buildu: "Failed to fetch one or
more git submodules"). Tenhle soubor proto není součástí žádného
commitu — je potřeba ho ručně vložit tam, kam dokumentace teď fakticky
patří (opravit `.gitmodules` je samostatný úkol, mimo scope týhle session).

---

## §79 — Frontend: dokončené stránky

Dvě chybějící stránky z předchozí session dokončeny:

```
app/zapis/[id]/stav/
├── page.tsx        # Server Component — read-only přehled žádosti
└── StavView.tsx     # Prezentační komponenta (status banner, rekapitulace,
                      # sekce druhého zástupce)

app/zapis/pripojit/[guardianId]/
├── page.tsx                    # Server Component — cíl e-mailové pozvánky
└── ConfirmSecondGuardian.tsx   # Klientská komponenta — tlačítko potvrzení
```

`stav/page.tsx` — vlastník s ještě editovatelnou žádostí (`jeEditovatelne()`)
se odsud přesměruje zpátky do wizardu; spoluzástupce i vlastník
s needitovatelnou žádostí (`odeslána`/rozhodnutá) vidí read-only přehled.

`pripojit/page.tsx` — volá bootstrap RPC (§81) přímo v render těle server
komponenty, stejný vzor jako `get_or_link_guardian_self` v
`app/portal/layout.tsx`. Po napojení normální RLS dovolí načíst
žádost + guardian řádek běžným SELECTem.

---

## §80 — Migrace 043: enrollment_create_application (bootstrap RPC)

**Problém:** RLS politika `enrollment_app_owner_all` (FOR ALL, jen USING,
bez WITH CHECK) a `enrollment_guardians_owner_write` (WITH CHECK vyžaduje
už existující řádek vlastníka) vytváří chicken-and-egg: nový rodič nemůže
založit VŮBEC PRVNÍ řádek žádosti, protože INSERT politiky vyžadují
řádek, který se teprve zakládá.

**Řešení:** `enrollment_create_application(p_typ enrollment_typ) RETURNS uuid`,
SECURITY DEFINER, atomicky INSERT do `enrollment_applications` +
`enrollment_guardians` (poradi=1, role='vlastnik', stav='zaregistrovan').
Kontroluje otevírací okno (jen pro typ='zapis', 'prestup' okno nekontroluje).
Sourozenecká kontrola: e-mail proti `guardians`, předvyplní jméno +
`existujici_guardian_id`.

```sql
GRANT EXECUTE ... TO authenticated;
REVOKE EXECUTE ... FROM anon;
```

Viz §82 — tohle samo o sobě NESTAČÍ (PUBLIC grant).

---

## §81 — Migrace 044: enrollment_link_second_guardian (bootstrap RPC)

Stejný chicken-and-egg, jen na druhé straně: pozvaný spoluzástupce má
řádek s `auth_user_id = NULL`, politika `enrollment_guardians_self_update`
vyžaduje `auth_user_id = auth.uid()` — první napojení účtu přes normální
RLS neprojde.

**Řešení:** `enrollment_link_second_guardian(p_guardian_id uuid)
RETURNS TABLE(application_id uuid, stav enrollment_guardian_stav)`,
SECURITY DEFINER. Navíc (na rozdíl od 043, kde je vlastník důvěryhodný
zakladatel) ověřuje shodu e-mailu přihlášeného účtu s e-mailem pozvánky —
obrana proti napojení cizí pozvánky podle uhodnutého/odposlechnutého
`guardianId` v URL (ten není tajný, chodí e-mailem). Idempotentní při
opakovaném volání týmž účtem.

Potvrzení žádosti (`stav → 'potvrzeno'`) jde běžnou cestou přes
`enrollment_guardians_self_update` RLS — po téhle RPC už
`auth_user_id = auth.uid()` platí, není potřeba další bootstrap.

---

## §82 — Migrace 045: PostgreSQL uděluje EXECUTE roli PUBLIC automaticky

**Nalezeno smoke testem (vrstva 1):** `REVOKE EXECUTE ... FROM anon`
v 043 a 044 NESTAČÍ. PostgreSQL uděluje EXECUTE na nově vytvořenou funkci
automaticky roli `PUBLIC`, jejímž členem je i `anon`. `REVOKE FROM anon`
odebere jen přímý grant té konkrétní roli, ne grant zděděný přes `PUBLIC`
členství — `anon` tak měl EXECUTE dál.

Funkčně nebylo zneužitelné (obě funkce mají i vlastní
`IF auth.uid() IS NULL THEN RAISE EXCEPTION`), ale neodpovídalo to
deklarovanému záměru.

```sql
REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC;   -- tohle chybělo
GRANT  EXECUTE ON FUNCTION ... TO authenticated;
```

**Poučení pro příští SECURITY DEFINER funkce:** vždy `REVOKE ... FROM PUBLIC`
explicitně, `REVOKE FROM anon` samo o sobě je falešný pocit bezpečí.

---

## §83 — Migrace 046: infinite recursion v RLS politice (POTVRZENÝ produkční bug)

**Nalezeno v produkčním logu:** `sql_state 42P17
"infinite recursion detected in policy for relation enrollment_guardians"`,
při běžném SELECTu na `enrollment_applications` z `/zapis` landing stránky.

**Příčina:** `enrollment_guardians_self_read` (SELECT politika) obsahovala
self-join na STEJNOU tabulku:

```sql
-- ŠPATNĚ (rekurzivní):
(auth_user_id = auth.uid()) OR (EXISTS (
  SELECT 1 FROM enrollment_guardians eg2
  WHERE eg2.application_id = enrollment_guardians.application_id
    AND eg2.auth_user_id = auth.uid()
))
```

Aby Postgres zjistil, které řádky `eg2` smí volající vidět, musí znovu
vyhodnotit TUTÉŽ politiku na těch řádcích → nekonečná rekurze. Stejný
vzor byl i v `enrollment_guardians_owner_write` (WITH CHECK) — tedy
pravděpodobně ovlivňoval i INSERT z migrace 043 (viz §84).

**Řešení:** kontrola vytažena do `SECURITY DEFINER` funkcí s
`row_security = off` (viz §84 pro vysvětlení proč je tenhle setting
nutný, ne jen SECURITY DEFINER samotné):

```sql
CREATE FUNCTION enrollment_is_guardian_on_application(p_application_id uuid)
  RETURNS boolean LANGUAGE sql SECURITY DEFINER STABLE
  SET search_path = public SET row_security = off
AS $$ SELECT EXISTS (SELECT 1 FROM enrollment_guardians eg2
  WHERE eg2.application_id = p_application_id AND eg2.auth_user_id = auth.uid()) $$;

CREATE FUNCTION enrollment_is_owner_on_application(p_application_id uuid)
  -- stejné, navíc AND eg2.role_v_zadosti = 'vlastnik'
```

Politiky na `enrollment_guardians` i `enrollment_applications` přepsány
na tyhle helpery (u `enrollment_applications` funkčně beze změny, jen
sjednocení logiky — cross-table EXISTS tam sám o sobě nerekurzoval).

**Obecné poučení:** self-join uvnitř RLS politiky NA STEJNOU tabulku je
vždycky riziko nekonečné rekurze. Kdykoli politika na tabulce X potřebuje
"existuje jiný řádek v X splňující podmínku" — vytáhnout do SECURITY
DEFINER + `row_security = off` helperu, nikdy ne přímý self-join v USING/
WITH CHECK klauzuli.

---

## §84 — Migrace 047: row_security = off v bootstrap RPC (preventivní, NE potvrzený bug)

Při opravě §83 vyšlo najevo, že 043 i 044 (SECURITY DEFINER) nikdy
nenastavovaly `row_security = off`. Enrollment tabulky mají `FORCE ROW
LEVEL SECURITY` (ověřeno: `relforcerowsecurity = true`) — což znamená,
že politiky platí i pro vlastníka tabulky, POKUD explicitně nenastaví
`row_security = off` (samotné SECURITY DEFINER nestačí, pokud vlastník
nemá BYPASSRLS).

**Důležité:** tohle NEBYLO přímo pozorováno v logu jako aktivní bug
(narozdíl od §83) — bylo přidáno preventivně, protože jsme se v tu chvíli
ještě nedostali k reálnému otestování INSERT cesty (blokovaly to OTP/
CAPTCHA/e-mail problémy, viz §86, §90). Nasazeno jako obranné opatření;
po §85 se ukázalo, že SKUTEČNÁ příčina "zápis není otevřený" byla jinde
(chybějící politika na `enrollment_settings`, ne row_security na 043/044
samotných) — ale 047 zůstává správná praxe i tak, nic nerozbíjí.

**Obecné poučení:** každá nová SECURITY DEFINER bootstrap funkce na
tabulce s FORCE RLS by měla mít `SET row_security = off` jako standardní
součást hlavičky, ne až po nalezení problému.

---

## §85 — Migrace 048: chybějící veřejná SELECT politika na enrollment_settings

**POTVRZENÝ bug** (diagnostický dotaz na `pg_policies`): na
`enrollment_settings` existovaly jen:
- `enrollment_settings_director_write` (UPDATE, jen ředitel)
- `enrollment_settings_staff_read` (SELECT, jen personál: director/guide/
  assistant/vp)

Žádná politika nedovolovala běžnému rodiči (natož nepřihlášenému
zájemci) tabulku číst. Pod FORCE RLS to znamenalo: `SELECT` z `/zapis`
(landing), `/zapis/nova` (kontrola okna před založením žádosti) a
`odvodRokZapisu()` v `app/actions/enrollment.ts` vždy vrátil nic —
bez ohledu na skutečnou hodnotu `zapis_otevren`.

**Projev:** "zápis není otevřený" i při `zapis_otevren = true` v DB
+ `/zapis/nova` přesměrovávala zpátky na `/zapis` dřív, než se vůbec
zavolala `enrollment_create_application` → žádná žádost nikdy nevznikla
("no rows" v `enrollment_applications").

**Řešení:**
```sql
CREATE POLICY enrollment_settings_public_read ON enrollment_settings
  FOR SELECT USING (true);
GRANT SELECT ON enrollment_settings TO anon, authenticated;
```
Bezpečné — tabulka obsahuje jen provozní metadata (`zapis_otevren`,
`okno_od`, `okno_do`), žádná citlivá data.

**Obecné poučení:** tabulky, které "personál konfiguruje", ale
"veřejnost/rodič potřebuje přečíst kvůli UX rozhodnutí" (zobrazit/
neskrýt tlačítko), potřebují DVĚ různé politiky — write pro personál,
read pro kohokoli. Snadno se zapomene na tu druhou, protože testování
migrace samotné (jako personál/ředitel) tenhle problém neodhalí — je
vidět jen z pohledu skutečného rodiče.

---

## §86 — Send Email Hook: neošetřená výjimka na module-level

**Kontext:** `app/api/auth/send-email/route.ts` (existuje od dřívějška,
NENÍ z týhle session — poslední dotčen v `aafdac6`). Supabase Auth vrátil
`500 {"code":"unexpected_failure","message":"Unexpected status code
returned from hook: 500"}` na `/auth/v1/otp`.

**Příčina:**
```ts
// ŠPATNĚ — na module-level, mimo POST handler:
const hookSecret = (process.env.SEND_EMAIL_HOOK_SECRET as string).replace(
  'v1,whsec_', ''
)
```
Pokud `SEND_EMAIL_HOOK_SECRET` na produkčním Vercel deploymentu chybí
(nebo je prázdná), `(undefined).replace(...)` spadne s neošetřenou
výjimkou HNED při startu funkce — před jakýmkoli `try/catch` uvnitř
`POST` handleru. Supabase pak dostane jen obecné "Unexpected status
code: 500", bez JSON těla, bez jakékoli stopy PROČ.

**Skutečná náprava:** rotace `SEND_EMAIL_HOOK_SECRET` v Supabase
dashboardu (Generate secret) + doplnění stejné hodnoty do Vercel
Production env (Vercel needuje matchovat hodnotu, ale hodnotu nejde
"reveal" zpětně — proto rotace obou stran najednou, ne pokus o
porovnání).

**Diagnostické vylepšení (dodáno spolu s nálezem):**
```ts
function getHookSecret(): string {
  const raw = process.env.SEND_EMAIL_HOOK_SECRET
  if (!raw) throw new Error('SEND_EMAIL_HOOK_SECRET není nastavená')
  return raw.replace('v1,whsec_', '')
}
// volá se UVNITŘ POST handleru, v try/catch, s čitelnou JSON odpovědí.
```
Taky zabaleno `resend.emails.send()` do try/catch (SDK může vyhodit
výjimku místo vrácení `{error}` za určitých okolností — síť, neplatný
klíč).

**Obecné poučení:** cokoli počítané na module-level v Route Handleru
(mimo `POST`/`GET` tělo) a závislé na env proměnné je jednobodové
selhání bez šance na `try/catch` záchranu. Vždy počítat uvnitř
handleru, i za cenu drobné neefektivity (běží to na každý request
znovu místo jednou při cold startu).

---

## §87 — Tailwind v4: `bg-[--var]` už NEfunguje jako zkratka za `var()`

**Nejzávažnější a nejrozšířenější nález — postihuje CELOU appku, ne jen
enrollment.**

Projekt používá Tailwind v4 (`"tailwindcss": "^4"`, žádný
`tailwind.config.js`, jen `postcss.config.mjs` s `@tailwindcss/postcss`).

V Tailwindu v3 se holý název CSS proměnné v hranatých závorkách
(`bg-[--foo]`) automaticky zabalil do `var(...)`. **V4 tohle chování
změnilo** — hranaté závorky teď berou hodnotu doslovně. Ověřeno přímým
vygenerováním CSS přes `@tailwindcss/cli` (ne jen čtením dokumentace):

```css
/* bg-[--portal-accent] vygeneruje (ŠPATNĚ): */
.bg-\[--portal-accent\] { background-color: --portal-accent; }
/* neplatná CSS hodnota — prohlížeč deklaraci potichu zahodí */

/* bg-(--portal-accent) vygeneruje (SPRÁVNĚ): */
.bg-\(--portal-accent\) { background-color: var(--portal-accent); }
```

**Projev:** tlačítka s `bg-[--portal-accent] text-white` byla vizuálně
neviditelná (bílý text na průhledném pozadí), ale ZŮSTÁVALA klikatelná
(element existuje v DOM, jen bez pozadí) — matoucí kombinace při
debuggování ("Enter fungovalo, tlačítko nikde").

**Rozsah:** 15 souborů napříč celou appkou (5 starších `/portal/*`
souborů + 10 z týhle session), prefixy `bg-`, `text-`, `border-`,
`divide-`. Opraveno regexem
`s/(bg|text|border|ring|fill|stroke|divide)-\[(--portal-[a-z-]+)\]/\1-(\2)/g`,
ověřeno `tsc --noEmit` + reálným vygenerováním CSS přes
`@tailwindcss/cli --content "./app/**/*.tsx"` (kontrola, že nikde
nezůstává `background-color/color/border-color: --portal-*` bez `var()`).

**Obecné poučení:** JAKÝKOLI budoucí kód v týhle codebase používající
vzor `[--nazev-promenne]` (bez `var()`) je od Tailwindu v4 potichu
rozbitý — nekompiluje chybu, jen negeneruje funkční CSS. Design token
konvence (`--portal-*`) v `app/globals.css` by měla mít u sebe
poznámku/lint pravidlo připomínající syntaxi `bg-(--var)`, ne
`bg-[--var]`. Stálo by za zvážení `stylelint`/ESLint pravidlo
zachytávající tenhle vzor automaticky, ať se to nemusí znovu ladit
ručně přes DevTools.

---

## §88 — eSSL append-only audit trail blokuje mazání auth.users (GDPR poznámka)

Při úklidu testovacích dat po smoke testu: `essl_transakce` (migrace
036) má Postgres RULE vynucující append-only:
```sql
CREATE RULE essl_transakce_no_delete AS ON DELETE TO essl_transakce DO INSTEAD NOTHING;
```
FK `uzivatel_id`/`zpracovatel_id`/`sestavil_id` → `auth.users(id)` NEMAJÍ
`ON DELETE SET NULL` (default `NO ACTION`) — přestože komentář u sloupce
`uzivatel_popis` explicitně říká *"Snapshot jména pro případ smazání
auth účtu"*, což naznačuje ZAMÝŠLENÝ (ale neimplementovaný) `ON DELETE
SET NULL`.

**Důsledek:** jakýkoli `auth.users` účet, který kdy vyvolal eSSL
transakci (např. rodič, jehož žádost o zápis dosáhla `k_rozhodnuti` a
otevřela spis), **nejde nikdy smazat** — FK to zablokuje, protože
referenční řádek v `essl_transakce` nejde odstranit ani obejít.

**Otevřená otázka k rozhodnutí (NErozhodnuto v týhle session):** tohle
je potenciálně relevantní k GDPR právu na výmaz (čl. 17 GDPR) u reálných
rodičovských účtů, ne jen testovacích. Oprava by byla:
```sql
ALTER TABLE essl_transakce
  DROP CONSTRAINT <constraint_name>,
  ADD CONSTRAINT <constraint_name> FOREIGN KEY (uzivatel_id)
    REFERENCES auth.users(id) ON DELETE SET NULL;
-- totéž pro zpracovatel_id, sestavil_id
```
Tohle by uvedlo implementaci do souladu s deklarovaným záměrem
(`uzivatel_popis` snapshot). Nejde o bug z týhle session (migrace 036,
starší) — zapsáno jako nález k budoucímu rozhodnutí, ne opraveno.

**Praktický dopad pro testování:** jakýkoli smoke test, co se dotkne
eSSL (otevření spisu), zanechává TRVALÝ artefakt — testovací spis i
testovací auth účet nejdou smazat, jen anotovat/uzavřít. Počítat s tím
při plánování budoucích testů (použít jasně označené testovací e-maily
od začátku, ne re-použít reálné pracovní adresy jako `mracek@gymtce.cz`).

---

## §89 — APP_BASE_URL (dřív PORTAL_BASE_URL) — oprava chybné domény

`lib/enrollment/send-guardian-invite.tsx`: proměnná `PORTAL_BASE_URL`
byla odhad (`https://portal.zsvilekula.cz`), navíc matoucí název — pokud
by se doslovně použila hodnota portálové sekce
(`https://nilsson.zsvilekula.cz/portal`), pozvánkový odkaz pro druhého
zástupce by omylem obsahoval `/portal` segment navíc
(`.../portal/zapis/pripojit/{id}` místo `.../zapis/pripojit/{id}`) —
`/zapis/*` žije architektonicky MIMO `/portal/*` (portál vyžaduje
existujícího guardiana, zápis je veřejný vstupní bod).

Přejmenováno na `APP_BASE_URL`, nastaveno na ověřenou skutečnou doménu
`https://nilsson.zsvilekula.cz` (bez `/portal`). Vercel env proměnná
`PORTAL_BASE_URL` (pokud existovala) se novým názvem nenačte — nutno
přejmenovat i ve Vercel dashboardu, ať fallback hodnota v kódu není
jediná záchrana.

---

## §90 — Cloudflare Turnstile CAPTCHA (nová závislost)

`/zapis/prihlaseni` je jediné místo v appce, které umí založit NOVÝ Auth
účet (`shouldCreateUser: true` — `/portal/login` používá `false`).
Před zapnutím "Allow new users to sign up" v Supabase (nutné pro
fungování enrollment flow) přidána CAPTCHA ochrana:

- Cloudflare Turnstile widget (`data-sitekey` přes
  `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `data-callback` → globální
  `window.onTurnstileVerify`).
- Token posílán jako `options.captchaToken` do `signInWithOtp()`;
  ověření probíhá server-side v Supabase Auth (Authentication → Attack
  Protection → Turnstile Secret Key), ne v našem kódu.
- Token jednorázový — reset po každém pokusu (`window.turnstile.reset()`).
- Tlačítko needitovatelné, dokud widget neposkytne token (chrání i
  proti chybějící/nesprávné env proměnné — bez sitekey widget nikdy
  neověří, tlačítko zůstane blokované, ne že by se CAPTCHA dala obejít).

**Nová externí závislost:** Cloudflare Turnstile účet, se **dvěma**
klíči (Site Key → veřejný, `NEXT_PUBLIC_*`; Secret Key → jen do Supabase
dashboardu, nikdy do `NEXT_PUBLIC_*`). Doména musí být v Turnstile
"Domains" seznamu — při testování na Vercel preview URL nutno přidat i
`vercel.app` wildcard, jinak chyba `110200 Invalid domain`.

---

## §91 — Stav smoke testu (vrstva 2) po týhle session

Kompletní end-to-end průchod ÚSPĚŠNĚ ověřen na produkci:
1. Registrace nového rodiče (OTP + CAPTCHA) ✓
2. Založení žádosti o zápis (migrace 043) ✓
3. Vyplnění dotazníku (dítě "Ida Mráčková", nar. 2022-02-22) ✓
4. Pozvání druhého zástupce (migrace 042 + e-mail) ✓
5. Napojení druhého zástupce přes pozvánkový odkaz (migrace 044) ✓
6. Potvrzení druhého zástupce (`stav → 'potvrzeno'`) ✓
7. Odeslání žádosti → `enrollment_essl_open_spis` → stav `k_rozhodnuti`,
   reálný eSSL spis vznikl (`e68c09aa-...`) ✓

**Zatím NEotestováno** (checklist vrstva 2, body zbývající):
- Bezpečnostní scénář: cizí e-mail se nesmí napojit na cizí pozvánku
  (kód existuje — ověření shody e-mailu v migraci 044 — ale nebylo
  cíleně vyzkoušeno záměrným pokusem)
- Spoluzástupce nesmí editovat žádost / vidět wizard (redirect na
  `/stav` — kód existuje, netestováno cíleně)
- Rozhodnutí ředitele (`enrollment_record_decision`) a navazující
  stavy (`přijat`/`nepřijat`/`odklad`) — mimo scope týhle session,
  rodičovský pohled na tyhle stavy existuje (`STAV_LABELS`/`STAV_VARIANT`
  ve `StavView.tsx`), ale nebyl reálně vyzkoušen s reálným rozhodnutím.

**Testovací data:** žádosti smazány po ověření (viz §88 pro eSSL
výjimku — spis zůstává, anotován jako testovací a uzavřen). Auth účty
(`mracek@gymtce.cz`, `jakub.mracek+1@gmail.com`) NEJDOU smazat (§88),
zůstávají jako trvalý testovací artefakt.

---

## Shrnutí commitů (branch `feat/enrollment-frontend` → merged do `master`)

| Commit | Obsah |
|---|---|
| `199a21d` | Frontend (18 souborů) + migrace 043–045 |
| `47ede2f` | Fix: distributivní conditional type (`EnrollmentResult<T>`) |
| `b456e4a` | Cloudflare Turnstile CAPTCHA |
| `7352950` | (Slepá větev — `overflow:visible` fix, neřešilo skutečnou příčinu §87) |
| `f820819` | Send Email Hook — diagnostika chybějící env proměnné (§86) |
| `a0c007e` | Migrace 048 — `enrollment_settings` public read (§85) |
| `08cabf3` | Migrace 046 + 047 (§83, §84) |
| `d56c24f` | Tailwind v4 syntax fix — `/zapis` soubory (§87) |
| `b86a9f8` | Tailwind v4 syntax fix — `/portal` soubory + `divide-` prefix (§87) |

---

## TODO do budoucna (nerozhodnuto/neopraveno v týhle session)

1. **§88** — GDPR: zvážit `ALTER ... ON DELETE SET NULL` na
   `essl_transakce.{uzivatel_id,zpracovatel_id,sestavil_id}` → `auth.users`.
2. Opravit `.gitmodules` (chybí, `Nilsson_documentation` submodule je
   trvale prázdný).
3. Přejmenovat `PORTAL_BASE_URL` → `APP_BASE_URL` i ve Vercel env (pokud
   tam starý název ještě existuje jako mrtvá proměnná).
4. Zvážit stylelint/ESLint pravidlo proti `[--var]` vzoru (§87) —
   prevence stejné třídy chyb v budoucích souborech.
5. Bezpečnostní scénáře checklistu vrstvy 2 (§91) — cíleně vyzkoušet,
   ne jen spoléhat na to, že kód vypadá správně.
6. Nastavit stabilní Vercel branch alias pro budoucí testovací branche
   (ať se nemusí Turnstile domény přidávat pro každý nový hash-URL).
