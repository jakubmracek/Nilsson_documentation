# ARCH-NOTE: MŠMT export — rodné číslo jen do základního souboru, KOD_ZAKA je pořadové číslo

**Datum:** 2026-09-28
**Modul:** [[MŠMT výkazy]] — export matriky, `/dashboard/msmt`, `/dashboard/msmt/rodna-cisla`
**Soubory:** `supabase/migrations/bez migrace/128_msmt_kod_zaka_poradove_cislo.sql`, `lib/rodne-cislo.ts`, `lib/msmt-xml.ts`, `app/api/msmt/xml/route.ts`, `app/dashboard/msmt/page.tsx`, `app/dashboard/msmt/rodna-cisla/page.tsx`, `app/dashboard/msmt/rodna-cisla/_components/RodneCisloRow.tsx`, `app/actions/students.ts`, `types/database.ts`
**Commity:** `7e5031c` (fix(msmt): RODC z rodného čísla, KOD_ZAKA = pořadové číslo (migrace 128))

---

## Přehled

Při návrhu podzimního sběru matriky (uživatel upozornil, že prerekvizita „uzavřené
1. pololetí" nedává na podzim smysl) jsem prošel metodiku MŠMT a zjistil, že
identifikace žáka v exportu je postavená obráceně. Migrace 127 ze stejného dne
plnila `kod_zaka_msmt` rodným číslem — anonymizovaný soubor „a" by tak rodná čísla
vyzradil. Tento run je **krok 1** přestavby exportu: správné identifikátory. Kroky 2
(přepínač jarní/podzimní sběr) a 3 (skladba vět podle oficiálního datového rozhraní)
čekají — viz níže.

---

## 1. RODC vs. KOD_ZAKA

### Symptom
Export `_01.xml` i `_01a.xml` identifikoval žáka atributem `KOD_ZAKA` s hodnotou
`students.kod_zaka_msmt`; ta byla po migraci 127 = rodné číslo.

### Příčina
Metodika MŠMT ([Informace a metodické poznámky](https://matrika.msmt.cz/matrikas/HELPY/POKYNY.PDF)):
- **Základní soubor** — žák se identifikuje položkou **RODC** (rodné číslo, 10 číslic
  dělitelných 11; cizinec bez RČ dočasně `RRNNDD` + `X` + pořadové číslo školy).
  Anonymizuje se až u MŠMT po zpracování.
- **Anonymizovaný soubor „a"** — **KOD_ZAKA** je „uveden v anonymizovaném souboru
  místo rodného čísla", přiděluje ho škola, 1–10 znaků, jednoznačný v rámci IZO,
  neměnný po dobu vzdělávání.

Původní TRD (`TRD_20260515_v2_1`, sekce 5.10/8.3) a starší ARCH-NOTES 16.4 zavedly
jediné pole `kod_zaka_msmt` = RČ pro oba soubory; komentář ve schématu přitom správně
říkal „anonymizovaný soubor ‚a', generuje se samostatně". Migrace 127 šla podle TRD.

### Řešení
- **Migrace 128:** zrušen trigger + funkce z 127; `msmt_kod_zaka_z_kod_zaka(text)` =
  pořadové číslo z `kod_zaka` (`VIL-2017-0012` → `0012`; globální sekvence →
  jednoznačné, neměnné, bez osobních údajů, stejné číslo už slouží jako VS).
  Trigger `trg_students_zz_kod_zaka_msmt` (BEFORE INSERT OR UPDATE) hodnotu vždy
  dopočítá — prefix `zz_` zajistí běh po `trg_students_kod_zaka` (BEFORE triggery
  běží abecedně). Přepsáni všichni žáci vč. odešlých (kontrola: `bez_kodu = 0`,
  `kod_je_rc = 0`, `max_delka = 4`).
- **Export:** základní soubor posílá `RODC` přímo z `students.birth_number`
  (normalizace `lib/rodne-cislo.ts`); když někdo nemá platné RČ, route vrátí 422
  s počtem — neúplný soubor se nevydá. Soubor „a" dál `KOD_ZAKA`.
- **`lib/rodne-cislo.ts`:** kontrola RČ (10 číslic + MODULO11 vč. výjimky zbytek 10
  → kontrolní 0, měsíc +20/+50/+70, platné datum), cizinecký kód s `X`, datum
  narození z RČ pro porovnání s kartou. Uložení `RRMMDD/XXXX`, do XML bez lomítka.
- **Stránka `/dashboard/msmt/kody-zaku` → `/dashboard/msmt/rodna-cisla`:** kontrola
  a oprava RČ (server action `updateRodneCislo`, director-only), upozornění na nesoulad
  s datem narození, kód „a" jen ke čtení. Stránka je nově director-only (dřív
  zobrazovala RČ komukoli s přístupem). RČ se v IS dosud po zápisu nedalo opravit
  vůbec.
- **Přehled `/dashboard/msmt`:** prerekvizita „Platná rodná čísla"; popisek souboru
  „b" opraven na podpůrná opatření 2.–5. stupně (ne zaměstnanci).

### Poučení
- U statistických/úředních exportů číst **metodiku zdroje**, ne jen vlastní TRD —
  TRD tu z jedné věty („kód = RČ") odvodilo schéma, UI i migraci.
- Když se komentář ve schématu a praxe rozcházejí, je to signál k ověření, ne k tomu
  přizpůsobit kód praxi (migrace 127 to udělala a musela se vracet).
- Identifikátor pro anonymizovaná data odvozovat z interní sekvence, nikdy z osobního
  údaje.

---

## Vedlejší nálezy (nezasahováno — kroky 2 a 3)

Export je stavěný jen na **jarní sběr** a v řadě bodů neodpovídá metodice:

1. **Jarní vs. podzimní sběr:** `OML_H/NEOML_H` se na jaře (RDAT 31. 3.) vykazují za
   1. pololetí aktuálního roku, na podzim (RDAT 30. 9.) za **2. pololetí předchozího**
   roku. Kód má natvrdo semestr 1 + `CURRENT_SCHOOL_YEAR` (dnes 2026/27 → prerekvizita
   nesplnitelná), jarní termíny 2026, věty dělené k 1. 2., RDAT default = dnes.
2. **Rozsah vět na podzim:** všechny věty s platností v intervalu 1. 10. minulého –
   30. 9. aktuálního roku, tj. i žáci, kteří mezitím odešli/vyšli — export bere jen
   `status = 'active'`.
3. **Položky:** metodika uvádí `POHLAVI`, `DAT_NAROZ`, `ROCNIK`, `TRIDA`,
   `ZAHDAT/KOD_ZAH`, `ST_SKOLY`, `PRIZN_ST`, `FIN`, `STPR`, `OBECB/OKRESB`, `KOD_VETY`…;
   export používá `RAZD/RAFZ/RAST/RAUJ/RAOR` (spíš názvy číselníků). Přesné názvy
   atributů určuje dokument MŠMT **„Datová rozhraní pro předávání dat"** — podklady
   zajišťuje uživatel.
4. **Soubor „b"** = podpůrná opatření 2.–5. stupně k 30. 9. (jen podzim), ne
   zaměstnanci — generátor chybí.

Rozhodnutí uživatele: „Systém rozhodně dotáhneme do produkční podoby; datově je to
připravené. Podklady seženu."

---

## Ověření

- Kontrolní dotaz po migraci 128: `bez_kodu = 0`, `kod_je_rc = 0`, `max_delka = 4`,
  `trigger_existuje = 1`, `stary_trigger = 0`.
- `npm run db:types`, `tsc --noEmit` bez chyb; validátor RČ ověřen na syntetických
  hodnotách (platné, s lomítkem, překlep, cizinec, špatný měsíc, 9 číslic, prázdné).
- Stránka `/dashboard/msmt/rodna-cisla` a export v prohlížeči neověřeny (produkční
  data za přihlášením). Soulad RČ s MODULO11 a datem narození u 32 žáků ukáže až
  stránka.

## Související

- [[ARCH-NOTE-2026-09-28-msmt-kod-zaka-z-rodneho-cisla]] — migrace 127, kterou tato opravuje
- [[Žáci]] — `kod_zaka` a jeho sekvence
