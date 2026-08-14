# ARCH-NOTE: Ročník jako matriční údaj — flow povýšení + přechod na nový školní rok

**Datum:** 2026-08-14
**Modul:** [[Žáci]] · [[Nastavení]] · [[Mapa pokroku]] · [[Školní družina]] (Správa školy)
**Soubory:** `app/dashboard/zaci/page.tsx`, `app/dashboard/rocniky/page.tsx` + `_components/RocnikEditor.tsx`, `app/dashboard/nastaveni/page.tsx` + `_components/YearTransition.tsx`, `app/actions/rocnik.ts`, `app/actions/school-year-transition.ts`, `lib/matrika.ts`, `lib/school-year.ts`, `app/dashboard/mapa-pokroku/page.tsx`, `app/dashboard/page.tsx`, `components/nav/nav-items.tsx`, družina (7 souborů), `supabase/migrations/bez migrace/075_matrika_set_rocnik.sql`, `076_matrika_set_rocnik_no_regres.sql`
**Commity:** `67982cc` (dělení po ročnících), `4d5e084` (moduly → aktivní rok z DB), `77ed29d` (flow ročníků 075), `0858512` (fix čtení ročníku), `3414738` (přechod roku + 076)
**Migrace:** `075_matrika_set_rocnik.sql` + `076_matrika_set_rocnik_no_regres.sql` — **obě spuštěny ručně v Supabase, ověřeno OK** (uživatel projel povýšení celé školy).

---

## Přehled

Ročník žáka se stal plnohodnotným **matričním údajem** s korektním zápisem
(soubor „a" MŠMT) a dostal:

1. **Sekundární dělení po ročnících** na `/dashboard/zaci` (uvnitř tříd).
2. **Matrika-správný zápis** ročníku přes RPC `matrika_set_rocnik` (verzovaně +
   audit), NE prostý UPDATE.
3. **Ředitelský editor** `/dashboard/rocniky` (ruční nastavení/oprava).
4. **Přechod na nový školní rok** v Nastavení — jedním krokem povýší všechny +1
   a nastaví aktivní rok.

Souvisí s [[ARCH-NOTE-2026-08-12-skolni-rok-nastaveni-zaci-csv]] (řízení roku z
`school_year_config`). Ročník žije v `student_education_mode.rocnik` (verzované
přes `valid_from/valid_to`; sloupec byl kdysi přidán ad-hoc mimo migrace).

---

## 1. Dělení po ročnících na /zaci + oprava referenčního data

- `zaci/page.tsx` uvnitř každé třídy dělí žáky do podskupin **N. ročník**
  (vzestupně, „Bez ročníku" na konec). Fallback: třída bez dat o ročníku = plochý
  seznam. Řádek žáka vytažen do `StudentRow`.
- **Zdroj ročníku = `student_education_mode`**, doplňován zvlášť (roster RPC ho
  nevrací). RLS `sem_select` (`can_read_student`): ředitel/vp/readonly vidí vše,
  průvodce/asistent jen svou skupinu → cizí žáci „Bez ročníku".
- **KLÍČOVÁ OPRAVA (`0858512`):** čtení ročníku nesmí být „k dnešku", ale
  **pro zobrazovaný školní rok** = referenční datum `1. 9. daného roku`. Jinak se
  do 1. 9. povýšený/nastavený ročník na `/zaci` vůbec neprojeví (nový záznam má
  `valid_from = 2026-09-01`, což je v srpnu „budoucnost"). Toto byl přesně symptom,
  který uživatel nahlásil („změny se neprojevily").

> Stejnou logikou „k dnešku" trpí i **Mapa pokroku** — zatím neopraveno (na TODO).

---

## 2. Matrika-správný zápis ročníku — RPC `matrika_set_rocnik` (075, 076)

Ročník je matriční údaj → **verzovaně**, ne UPDATE. RPC (SECURITY DEFINER,
director-only) pro jednoho žáka:

1. uzavře aktuální otevřený `student_education_mode` (`valid_to = p_valid_from - 1`),
2. založí nový (`valid_from`, `rocnik`, `zpusob` zkopírován / `'11'` u nováčka,
   `created_by`),
3. zapíše řádek do **`student_matrika_changes`** (immutabilní právní/auditní
   vrstva pro ČŠI) — `pole='rocnik'`, hodnota_před/po, `zdroj_zmeny`, `zaznamenal`.

> **`student_matrika_changes` je tímto poprvé reálně plněná** — dosud ji
> nepsal žádný kód (ani zápis žáka).

Pojistky:
- **Idempotence:** shodná hodnota = no-op (opakování ročníku).
- **`chk_sem_dates`:** guard, aby uzávěrka starého záznamu (`valid_from-1`) byla
  po jeho počátku.
- **Zákaz regresu (migrace 076):** `p_new_rocnik < aktuální` → EXCEPTION. Oprava
  dolů se touto cestou nedělá. Vynuceno i v UI editoru (dropdown nenabízí nižší).

`lib/matrika.ts` = tenký wrapper `callMatrikaSetRocnik` — RPC není v (stale)
`types/database.ts`, takže `as any` cast **na jednom místě** (ratchet drží
baseline 3). Viz [[nilsson-build-konvence]].

---

## 3. Editor ročníků `/dashboard/rocniky`

Ředitelská dlaždice (Správa školy → Žáci a rodiče). Živý přehled (žák · třída ·
ročník teď · od kdy platí), editovatelný „nový ročník" per žák, dvoukrokové
potvrzení se soupisem `3. → 4. ročník`. Server akce `bulkSetRocnik` (datum
platnosti `1.9.` + důvod počítá **server**, ne klient).

**Bezpečnostní default:** na načtení **nic nemění** (default „beze změny").
Povýšení `+1` je explicitní tlačítko „Předvyplnit povýšení". Jinak by opětovné
otevření + Uložit povýšilo všechny podruhé. 9. ročník se nepovyšuje.

---

## 4. Přechod na nový školní rok — Nastavení (`3414738`)

`YearTransition` + `school-year-transition.ts`. Jedním vědomým krokem:

- **Náhled** (`getPromotionPreview`): rozřadí aktivní žáky na `promote` (+1),
  `ends` (9. ročník = konec PŠD), `norocnik` (bez ročníku, beze změny), `done`
  (už povýšený pro cílový rok).
- **Podržení žáka** (odškrtnutí) = **opakování ročníku** → v matrice se nic
  nezapíše (záznam pokračuje), ale UI ukáže **explicitní amber alert**.
- **Potvrzení** (`startNewSchoolYear`): povýší nepodržené `promote` přes
  `matrika_set_rocnik(+1, valid_from = 1.9. cíle)` a pak nastaví
  `school_year_config.active_year = cílový rok` (+ přidá do `visible_years`).

Rozhodnutí / pojistky (zadání uživatele):
- **Cíl = `nextSchoolYear(active)`** — přechod jde vždy o rok dopředu; odvozuje se
  na serveru, klient ho nediktuje.
- **Idempotence:** `done` (aktuální záznam `valid_from >= 1.9. cíle`) se přeskočí
  → opětovné spuštění nezdvojí. Kdo klikne znovu vědomě, přejde o další rok (náhled
  to jasně ukáže).
- **Regres nelze** (RPC 076). **Opakování ano, ale s alertem.**
- Přechod jede **na žácích, ne na třídách** — nepředpokládá zařazení do tříd
  nového roku (membership je samostatný krok).

---

## 5. Kontext: moduly → aktivní rok z DB (`4d5e084`)

Ve stejném oblouku sjednoceno čtení roku (rotace bila tři místa):
- **Mapa pokroku:** default rok z data (v srpnu starý) → aktivní rok z DB +
  přepínač roku.
- **Dashboard dlaždice žáků:** natvrdo „2025/2026" → aktivní rok z DB (label i
  počet).
- **Družina:** celý modul na `NEXT_SCHOOL_YEAR` (po rotaci mířil na 2027/2028, pro
  který nebylo `druzina_oddeleni`) → `getActiveSchoolYear()`. + **UI pro zakládání
  oddělení družiny** per rok (dřív jen migračním seedem). Viz [[zdroj-skolniho-roku]].

---

## Ověření

- `tsc --noEmit` čistý u všech commitů; `check:as-any` = baseline 3.
- Migrace 075 + 076 spuštěny ručně, ověřeno. Uživatel projel povýšení celé školy
  — diagnostika potvrdila: každý žák má nový záznam `valid_from=2026-09-01,
  valid_to=null` se správným ročníkem, starý korektně uzavřen k `2026-08-31`.
- Živě je vše za ředitelským loginem (typecheck + revize logiky RPC).

## Poznámky do budoucna / TODO

- **Mapa pokroku** — sjednotit čtení ročníku na referenční datum jako `/zaci`.
- **Opakování ročníku** se do matriky/auditu nezapisuje (nic se nemění). Pokud
  ČŠI vyžaduje evidenci retence, doplnit záznam do `student_matrika_changes` /
  poznámky.
- **Oprava ročníku dolů** (regres) je zakázaná — pokud vznikne legitimní potřeba
  (překlep nahoru), přidat explicitní override cestu.
- **Membership do tříd nového roku** — zařazení žáků do tříd pro nový rok je
  pořád samostatný, zatím neautomatizovaný krok.
- **Pelc Antonín** — při prvním povýšení nebyl povýšen (5. ročník, otevřený
  záznam od 2026-02-01, žádný 2026-09-01). Prověřit, zda je v rosteru 2026/2027.

## Související

- [[ARCH-NOTE-2026-08-12-skolni-rok-nastaveni-zaci-csv]] — `school_year_config`, resolver
- [[migracni-workflow]] — migrace `bez migrace/NNN`, ručně v Supabase
- [[nilsson-build-konvence]] — ratchet as-any, RLS helpery, async searchParams
- [[umisteni-director-agend]] — director agendy jako dlaždice ve Správě školy
