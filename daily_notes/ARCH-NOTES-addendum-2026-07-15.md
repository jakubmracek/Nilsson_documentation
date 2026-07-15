# ARCH-NOTES Addendum — 2026-07-15
# [[Spisovka]] / eSSL: napojení na ISDS (datová schránka) — audit stavu & override rozhodnutí

> Číslování §: navazuji na eSSL addendum z 2026-07-03 (§71–§78). Pokud vedeš
> jednu globální řadu, zkontroluj max proti družinovým addendům (tam se řada
> šplhala k §99+) a případně přečísluj — v poznámkách je známý konflikt §92–§98.

Tato session byla **auditní**: cílem bylo zorientovat se ve skutečném stavu
napojení [[Spisovka]] na datovou schránku (ne psát kód). Zjištění níže
**explicitně přebíjejí** starší rozhodnutí a To-do — viz §84.

---

## §79 — Skutečný stav pipeline: NAPSÁNA, ale NIKDY neproběhla

Ověřeno proti repu (`jakubmracek/nilsson`, `master`) i proti DB (Supabase
`zrzknpamosnniuljjivg`).

**V repu existuje kompletní příchozí pipeline:**
- `scripts/isds-poll.ts` (344 řádků) — SOAP `GetListOfReceivedMessages` →
  `ds_zpravy` → `dokumenty` → `essl_log` → Discord.
- `.github/workflows/essl-isds-poll.yml` — denní cron `30 4 * * *`
  (≈06:30 CEST) + `workflow_dispatch`.
- `supabase/migrations/bez migrace/037_essl_isds.sql` — vytváří `ds_zpravy`
  a rozšiřuje `essl_log`.

**Ale ostrý provoz = nula:**
- `ds_zpravy`: **0 řádků** (celkem/zpracováno/s dokumentem/s chybou = 0/0/0/0).
- `essl_transakce` s `uzivatel_popis = 'ISDS cron'`: **0 záznamů**.
- GitHub Actions: **9 běhů (7.–15. 7. 2026), všechny neúspěšné**, každý ~30 s.

Závěr: pipeline nikdy nenatáhla ani jednu zprávu z datovky.

---

## §80 — Příčina denního pádu: chybějící ISDS secrets (NE síť, NE ISDS)

Log z běhu #9 (dnešního):

```
Run npx tsx scripts/isds-poll.ts
Error: Chybí povinná env proměnná: ISDS_USERNAME
    at requireEnv (scripts/isds-poll.ts:52:11)
Process completed with exit code 1.
```

Skript umře na `requireEnv('ISDS_USERNAME')` (řádek 62) **dřív**, než se
dotkne ISDS. Ověřeno proti nastaveným GitHub secrets:

| Secret vyžadovaný workflow | Stav |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ je |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ je |
| `ISDS_USERNAME` | ❌ **chybí** |
| `ISDS_PASSWORD` | ❌ **chybí** |
| `DISCORD_ADMINISTRATIVA_WEBHOOK_URL` | ❌ chybí (existuje jen `DISCORD_LUNCH_WEBHOOK_URL`) |

Discord secret je kosmetika — skript ho ošetřuje `console.log`em, neshodí ho.

**Interpretace:** autentizace k ISDS se od března **reálně nikdy nedořešila**.
Někdo nascaffoldoval skript i workflow s variantou jméno/heslo, ale
přihlašovací údaje nikdy nevznikly. Fakticky tedy **nevíme, zda by jméno/heslo
vůbec fungovalo** — nikdy se to tak daleko nedostalo.

---

## §81 — §77 UZAVŘEN: essl_log má p_spis_id i override

Otevřený bod §77 (signatura `essl_log` pro spisy) je **vyřešen**. DB funkce už
má:

```
essl_log(p_operace, p_dokument_id, p_spis_id, p_skartacni_navrh_id,
         p_detail, p_uzivatel_popis_override)
```

`p_uzivatel_popis_override` používá cron pro odlišení automatických zápisů
(`'ISDS cron'`) od ručních akcí. → **Škrtnout §77 z TODO v TRD i ARCH-NOTES.**

---

## §82 — ds_zpravy je NASAZENÁ, ale migrace visí mimo řadu

`to_regclass('public.ds_zpravy')` = existuje. Tabulka i úprava `essl_log`
jsou v DB. **Ale** soubor leží v `supabase/migrations/bez migrace/037_essl_isds.sql`,
tzn. mimo číselnou řadu migrací — opakující se pattern „v produkci, ne v řadě".

TODO: dorovnat `037_essl_isds.sql` do číselné řady, ať se historie nerozjede.

---

## §83 — Cron INSERT do dokumenty je životaschopný (žádný NOT NULL blocker)

Ověřeno v `036_essl.sql`: sloupce, které `isds-poll.ts` do `dokumenty`
nevkládá, jsou pokryté:
- `cislo_jednaci` / `rok` / `poradove_cislo` → plní trigger `trg_essl_cj`
  (BEFORE INSERT), `essl_generuj_cj()`.
- `datum_vzniku` → `DEFAULT CURRENT_DATE`.
- `prilohy` → `DEFAULT '[]'`.
- `stav` → `DEFAULT 'prijat'`.

Tzn. kdyby autentizace fungovala, INSERT by na NOT NULL nespadl.

Poznámka k datům: `dokumenty` má **90 přijatých / 24 odeslaných** (dokumentace
uváděla import 80/24). Těch +10 přijatých **nevzniklo z datovky** (cron neběžel)
— muselo přijít ručně přes UI nebo dalším během `import_ds_log.ts`.

---

## §84 — OVERRIDE: přebíjí starší rozhodnutí a To-do

### 84.1 — Railway JIŽ NENÍ potřeba (přebíjí březen 2026)
**Staré (březen 2026):** „ISDS přes systémový certifikát vyžaduje mTLS; Apps
Script `UrlFetchApp` mTLS neumí → **Railway jako middleware**."
**Nové:** poll běží na **Node v GitHub Actions**, a Node umí mTLS nativně
(`https.Agent` s klientským certifikátem). Důvod pro Railway (Apps Script) tím
**odpadá**. Runner zůstává GitHub Actions. **Railway z architektury vypuštěno.**

### 84.2 — Autentizace = certifikát, NE jméno/heslo (přebíjí scaffolding v repu)
**Staré (v kódu):** HTTP Basic přes `ISDS_USERNAME` / `ISDS_PASSWORD`.
**Nové:** **systémový certifikát spisové služby (mTLS)**. Důvody:
1. Heslo do DS v základním nastavení **expiruje po 90 dnech** → neobsluhovaný
   cron by se každé 3 měsíce tiše rozbil.
2. Pro certifikát spisové služby ISDS akceptuje **výhradně komerční certifikát
   akreditované CA** (self-signed ani podpisový/kvalifikovaný nelze). Detaily §85.
3. Jméno/heslo je z metod nejsnáze zneužitelné; u schránky v režimu ESS bývá
   web-service přístup stejně vázán na certifikát.

### 84.3 — Klarifikace „hesla" (pro budoucí session)
Nikdy jsem (Claude) nežádal heslo do datovky. Březnová otázka zněla „kde jsi
s **certifikátem**?" a nikdy nedostala odpověď. Heslo v pipeline pochází z
neatribuovaného pivotu na jméno/heslo. **Přihlašovací tajemství nepatří do
chatu — certifikát/klíč jdou jako GitHub secret, ne sem.**

---

## §85 — Certifikát spisové služby: kanonické parametry (ověřeno z info.mojedatovaschranka.cz)

- **Typ:** komerční **serverový** certifikát od akreditované CA
  (PostSignum / I.CA / eIdentity). **Self-signed a podpisový/kvalifikovaný
  certifikát NELZE.**
- **Formát pro registraci:** **PEM** (`-----BEGIN CERTIFICATE-----`).
- **Registrace:** jako administrátor schránky **rm35wuu** v portálu ISDS:
  *Nastavení → Externí aplikace → Certifikát spisové služby → Zaregistrovat
  certifikát*. Po registraci indikátor „Aktivní" (zelené zatržítko).
- **Platnost:** typicky **1 rok** → roční obnova (portál varuje 30 dní předem).
  NE 90denní cyklus jako heslo.
- **Cena:** řádově stokoruny–nižší tisíce Kč/rok.
- **Přihlašovací jméno se u certifikátu spisové služby nepoužívá** — ISDS
  identifikuje ESS podle registrovaného certifikátu při SSL handshake.

---

## §86 — Aktualizovaný TODO (nahrazuje předchozí „go-live" seznam pro ISADS část)

1. **Pořídit + zaregistrovat** komerční serverový certifikát (viz samostatný
   návod k této session).
2. **Přepsat `isds-poll.ts`**: HTTP Basic → **mTLS** (`https.Agent` s
   `ISDS_CERT_PEM` + `ISDS_KEY_PEM` z base64 secrets). Odstranit
   `ISDS_USERNAME` / `ISDS_PASSWORD` z workflow.
3. **Dorovnat migraci `037`** do číselné řady (§82).
4. **Přílohy (gap):** skript volá jen `GetListOfReceivedMessages` (envelope
   metadata). `MessageDownload` **nevolá** → i ostrý cron by zakládal dokumenty
   s prázdnými `prilohy`. Doplnit stažení příloh + rozhodnout úložiště
   (Supabase Storage vs. Drive URL).
5. **Odeslané:** `GetListOfSentMessages` není implementováno (skript řeší jen
   příchozí).
6. **Doplnit secret** `DISCORD_ADMINISTRATIVA_WEBHOOK_URL` (nebo přesměrovat na
   existující webhook).

**Bez datumového tlaku:** ostrý provoz [[Spisovka]] je až od **1. 1. 2027**;
cron teď jen neškodně padá (0 zpráv, 0 auditu). Žádný „most" přes jméno/heslo
není potřeba — jde se rovnou certifikátovou cestou.

---

## §87 — Právní upozornění k zapamatování (beze změny z března)

`GetListOfReceivedMessages` může iniciovat proces doručení (posun „dodáno" →
„doručeno"), od čehož běží lhůty. Skript vědomě **nevolá**
`MarkMessageAsDownloaded`. Před ostrým spuštěním (2027) tuto sémantiku znovu
ověřit proti aktuálnímu provoznímu řádu ISDS.
