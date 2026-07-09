# ARCH-NOTES — RÚIAN adresní infrastruktura + dokončení enrollment modulu
# (migrace 038–042) + oprava Send Email Hooku

Navazuje na `ARCH_NOTES_enrollment.md` (migrace 037, návrhová fáze). Tenhle
dokument zachycuje architekturní rozhodnutí a poučení z **implementační**
fáze — od pivotu na lokální RÚIAN data až po první produkční nasazení.

---

## 1. Pivot: lokální RÚIAN data místo cizího API

Původní plán (viz `ARCH_NOTES_enrollment.md` bod 4) počítal s validací
adresy přes ARES/ČÚZK API volané ze server-side proxy. Při návrhu Edge
Function se ukázalo, že **ARES "Standardizace adres" je určená pro
ekonomické subjekty**, ne fyzické osoby/děti — nevhodné.

Zkusili jsme ČÚZK `GeocodeSOE` (`ags.cuzk.gov.cz/.../findAddressCandidates`)
jako alternativu. **Ověřeno živým voláním**: globální `findAddressCandidates`
vrací jen generické Esri-kompatibilní atributy (`Addr_type`, `City`,
`Country`...) — **žádné RÚIAN kódy** (ani `ruian_kod`, natož obec/okres).
Nepoužitelné pro naše účely.

**Finální rozhodnutí:** naimportovat oficiální RÚIAN data přímo do vlastních
tabulek a validovat adresu jako lokální SQL lookup, bez volání cizí služby
za běhu. Důsledky:
- Žádná závislost provozu na dostupnosti cizí služby.
- Žádný rate-limiting/timeout handling pro cizí API.
- Cena: potřeba importních skriptů a měsíčního refreshe adresních míst.

## 2. Datový model — tři tabulky, dva refresh režimy

- **`ruian_okresy` + `ruian_obce`** (migrace 038) — malý, stabilní
  číselník (77 okresů, 6258 obcí). Data **zapečená přímo v migraci** jako
  `INSERT` příkazy (ne import skript) — mění se jen při reorganizaci
  územního členění, řádově jednou za pár let. Zdroj: `UI_OKRES.csv` +
  `UI_OBEC.csv` (RÚIAN číselníky VFR), `Windows-1250`, `;`-delimited,
  datum `DD.MM.YYYY`. **Filtrovat na `PLATI_DO IS NULL`** (aktivní
  záznamy) — jinak konflikt (např. Praha má historický okresní záznam
  `3100` zaniklý 2022-07-01, nahrazený `9999` "území Hlavního města
  Prahy").
- **`ruian_adresni_mista`** (migrace 039+040) — 3 019 049 řádků,
  **měsíční refresh** (`import-ruian-adresni-mista.mjs`), TRUNCATE+COPY,
  NE zapečené INSERTy (objem). Zdroj: celostátní ZIP
  (`nahlizenidokn.cuzk.gov.cz/StahniAdresniMistaRUIAN.aspx`), 6258 souborů
  po obcích uvnitř, stejné kódování/formát jako číselníky, ale datum
  **ISO** (`2014-02-12T00:00:00`), ne `DD.MM.YYYY`.
- Migrace 040 odstranila `nazev_obce` z `ruian_adresni_mista` (byla
  redundantní kopie `ruian_obce.nazev_obce`) — ušetřilo to ~52 MB
  (700→648 MB), méně než čekáno, ale bezplatné. Název obce se dohledává
  přes JOIN, ne denormalizovaně.

**Poučení:** `ruian_adresni_mista` NEOBSAHUJE kód okresu (jen kód obce) —
okres se dopočítává přes JOIN na `ruian_obce.kod_okresu`. Praha nemá
klasický okres (`kod_okresu='9999'`).

## 3. `immutable_unaccent` — Supabase specifika

`unaccent()` je `STABLE`, ne `IMMUTABLE` — nejde použít v indexovém
výrazu. Wrapper funkce potřebuje:
```sql
SET search_path = extensions, public, pg_temp
```
protože **Supabase instaluje rozšíření do schématu `extensions`**, ne
`public` jako čistý Postgres — bez explicitního `search_path` selže
`unaccent('unaccent'::regdictionary, $1)` s "text search dictionary
does not exist", i když lokálně (bez Supabase konvence) může procházet.
Ověřeno na produkci (dva kola oprav, než se přišlo na přesnou příčinu).

## 4. Validace adresy — jeden dotaz, ne dvoukroková resoluce

`enrollment_validate_address` (migrace 041) řeší obec+ulice+číslo+PSČ
**jedním JOIN dotazem**, ne nejdřív obec → pak adresa. Důvod ověřený na
reálných datech: minimálně 3 různé obce se jmenují "Adamov" (různé
okresy) — izolovaná resoluce obce by musela řešit ambiguitu zvlášť.
Místo toho počet výsledných řádků z kombinovaného dotazu rozhoduje
matched/ambiguous/not_found — přirozeně to pokryje i multi-vchodové
budovy (číslo "12" když existují "12/1" i "12/2" → ambiguous).

Pole "ulice" se zkouší i proti `nazev_casti_obce` (fallback) — malé obce
běžně nemají ulice, lidé si jako "ulici" logicky představí místní část.

## 5. Import velkých objemů dat — poučení z produkčního nasazení

Import `ruian_adresni_mista` (3M řádků) narazil postupně na několik
reálných produkčních limitů, v tomhle pořadí:

1. **WAL bloat** — jedna obří transakce (TRUNCATE+COPY+reindex) donutila
   Postgres držet celý WAL nezapsaný do commitu → "No space left on
   device" na 93 % průběhu, i když finální velikost tabulky byla jen
   ~650 MB. **Řešení:** dávkové commity (`BATCH_SIZE = 20_000`,
   samostatný `COPY` per dávka, žádný obalující `BEGIN` přes celý import).
   Cena: ztráta atomicity celého importu — při chybě uprostřed se tabulka
   aspoň vyprázdní (`TRUNCATE`), nikdy nezůstane napůl naplněná.
2. **Compute tier** — i po upgradu Supabase **plánu** (Free→Pro, kvůli
   8 GB kvótě) zůstal **Compute Add-on** na nejmenším tieru (Nano/Micro,
   sdílené CPU) — tohle jsou u Supabase dvě nezávislé věci. Menší dávky
   pomáhají nezávisle na compute upgradu (nižší špička zátěže), řešili
   jsme to bez placení za vyšší tier.
3. **Tiché zahazování spojení** — síťová infrastruktura (NAT/firewall)
   tiše zahazuje spojení bez datového provozu (typicky během dlouhého
   `CREATE INDEX`, kdy klient jen čeká na odpověď). `keepAlive` snižuje
   riziko, ale nezaručuje — proto navíc `query_timeout` (klientský,
   Node-side časovač, nezávislý na síti) + retry-s-reconnectem na úrovni
   jednotlivého kroku (indexu).
4. **Supabase SQL editor má vlastní tvrdý `statement_timeout` (20s)**,
   který nejde přepsat `SET statement_timeout` z předchozího dotazu (každé
   spuštění resetuje nastavení) — dlouhotrvající `CREATE INDEX` (desítky
   sekund až minuty na Nano/Micro) proto musí jít přes vlastní skript
   (`pg` klient s persistentním spojením), ne přes dashboard.
5. **Školní síť blokuje Postgres protokol** (TCP handshake projde,
   samotná komunikace ne — pravděpodobně DPI firewall) — ověřeno
   `Test-NetConnection` (TCP OK) + test přes mobilní hotspot (funguje).
   Řešení pro budoucí refresh: buď hotspot, nebo výjimka na
   `*.pooler.supabase.com` portech `5432`/`6543` od správce školní sítě.

**Obecné poučení:** import velkého objemu dat proti managed cloud
Postgresu (obzvlášť na menším compute tieru) potřebuje počítat s WAL
limity, síťovou nespolehlivostí (tichá i hlučná selhání) a dashboardovými
limity nezávisle na tom, jak "jednoduchá" je cílová operace (`COPY`,
`CREATE INDEX`).

## 6. Pozvánka 2. zástupce — Resend architektura

Migrace 042 (`enrollment_invite_second_guardian` + `enrollment_mark_invite_sent`)
je čistý SQL, **neposílá e-mail sama** — SECURITY DEFINER jen kvůli
sourozenecké kontrole (čtení `guardians`), ne kvůli právu INSERTu (to už
dává RLS `enrollment_guardians_owner_write`).

Samotné odeslání prošlo jednou architektonickou opravou: první verze
počítala s Deno Supabase Edge Function + syrový `fetch` na Resend API.
Po nalezení `emails/BulletinEmail.tsx` se ukázalo, že systém posílá
e-maily přes **`resend` npm balíček + React Email komponenty v
Node.js/Next.js** (Server Action/API route), ne přes Edge Function.
Přepsáno na `emails/GuardianInviteEmail.tsx` (stylově sjednoceno s
`BulletinEmail.tsx` — stejná paleta, `Georgia/Times New Roman`) +
`lib/enrollment/send-guardian-invite.tsx` (styl `recipients.ts`).

**Poučení:** u frameworkových rozhodnutí (kde/jak se posílá e-mail) se
nevyplácí předpokládat konvenci bez ověření proti reálnému kódu — první
verze byla funkčně v pořádku, ale architektonicky na jiném místě, než
kam projekt reálně patří.

`email_events.source_type` je čistý `text`, bez enumu/CHECK constraintu
— rozšíření `EmailSourceType` (TypeScript) o `'enrollment'` nevyžadovalo
žádnou DB migraci navíc (ověřeno dotazem před úpravou, ne předpokladem).

## 7. Send Email Hook — nalezená bezpečnostní díra

`app/api/auth/send-email/route.ts` (Supabase Auth Hook pro OTP e-maily)
**neověřoval podpis webhooku** — přijímal jakýkoli POST payload bez
kontroly, že skutečně pochází ze Supabase Auth. Důsledek: veřejně
dostupný open-relay, kdokoli mohl přes tenhle endpoint rozeslat e-mail
(vydávající se za školu) na libovolnou adresu s libovolným obsahem
místo OTP kódu.

**Oprava:** `standardwebhooks` balíček, ověření `wh.verify(rawBody,
headers)` proti `SEND_EMAIL_HOOK_SECRET` (formát `v1,whsec_...`, prefix
se odřízne) — přesně podle oficiální Supabase dokumentace k Send Email
Hooku. Tělo požadavku se musí číst jako `request.text()` (syrový
string), ne `.json()` — podpis se počítá nad přesným bytovým obsahem.

Nasazeno a ověřeno na produkci (přihlášení funguje, e-mail dochází).

**Nevyřešeno/otevřené:** `/api/webhooks/resend` (delivery/bounce/complained
tracking) může mít stejný vzorec (chybějící ověření Resend webhook
signatury) — zmíněno, ale zatím neprověřeno.

## 8. Stav k 6. 7. 2026 večer

**Nasazeno na produkci:** migrace 037 (opravená věková klasifikace),
038, 039+import (3 019 049 řádků), 040, 041, 042, oprava Send Email
Hooku, rozšíření `EmailSourceType`.

**Otevřené TODO:**
1. Napojit `sendGuardianInvite()` na frontend enrollment formuláře —
   frontend na pozvání 2. zástupce zatím neexistuje vůbec.
2. `RESEND_FROM_ENROLLMENT` a `PORTAL_BASE_URL` v
   `send-guardian-invite.tsx` jsou zatím jen odhady (`zapis@zsvilekula.cz`,
   `https://portal.zsvilekula.cz`) — ověřit skutečné hodnoty.
3. `types/supabase.ts` — duplicitní/zastaralá kopie `types/database.ts`,
   nikde reálně importovaná. Zvážit smazání nebo re-export
   (`export * from './database'`), ať se příště neaktualizuje jen jeden
   ze dvou souborů.
4. `/api/webhooks/resend` — provést stejné bezpečnostní review jako u
   Send Email Hooku (ověření Resend webhook signatury).
5. Bezpečnostní review OTP endpointu obecně (rate-limiting/CAPTCHA) —
   PRD §11 to doporučovalo před nasazením do produkce, ještě neřešeno
   (mimo scope dnešní Send Email Hook opravy, která byla o webhooku
   *příchozím* od Supabase, ne o *odchozím* OTP-request flow od uživatele).
