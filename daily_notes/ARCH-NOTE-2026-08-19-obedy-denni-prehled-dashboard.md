# ARCH-NOTE: Denní přehled strávníků obědů v dashboardu pro personál

**Datum:** 2026-08-19
**Modul:** [[Obědy]] — dashboard personálu
**Soubory:** `supabase/migrations/bez migrace/083_lunch_dashboard_roster.sql`, `app/dashboard/obedy/page.tsx`, `app/dashboard/obedy/_components/LunchEditBoard.tsx`, `app/actions/lunch-dashboard.ts`, `components/nav/nav-items.tsx`, `app/dashboard/sprava-skoly/page.tsx`, `types/database.ts`, `app/api/bulletin/posts/route.ts`, `app/dashboard/bulletin/[id]/page.tsx`
**Commity:** `549cd96` (feat obědy), `e45ad0e` (Merge PR #14) → veřejný release `v3.1.0`

---

## Přehled

Modul Obědy měl dosud jediný personální výstup — ranní SMS jídelně s *počtem* obědů; sbor a vedení neměli žádný *procházecí* přehled, kdo konkrétně jde na oběd (data `lunch_orders` viděl přes RPC jen rodič na svém kalendáři). Tento run tu mezeru zavřel: nová stránka **`/dashboard/obedy`** ukazuje pro každý den seznam strávníků po třídách + součty, s možností objednat/zrušit za žáka (ředitel/zástupce). Řeší se návrhem `PRD-obedy-denni-prehled-dashboard.md` v1.0.

Vedle toho (téma 2) doklizeny 3 pre-existing `(supabase as any)` casty v modulu Bulletin, které šly odstranit poté, co `db:types` doplnil chybějící objekty.

---

## 1. Denní přehled obědů pro personál

**Soubory:** migrace `083_lunch_dashboard_roster.sql`, `app/dashboard/obedy/*`, `app/actions/lunch-dashboard.ts`

### Kontext / rozhodnutí (PRD)
Uzavřená rozhodnutí, která tvarují celý modul:
- **Čtou všechny zaměstnanecké role** + readonly (demo inspektor) náhled; **zapisují jen ředitel + zástupce** (`is_director_or_vp()`).
- **Uzávěrka 22:00 D-1 platí i pro personál.** To je klíčové: personál nemůže zapisovat po uzávěrce ani na dnešek → počet už poslaný jídelně ranní SMS zůstává **finální** a odpadá jakékoli dorovnávání SMS. Vědomě jsme zamítli „zápis po uzávěrce s upozorněním".
- **Seznam = jen strávníci** (= `lunch_effective_orders`, tj. přesně to, co jde v SMS). Edit mód ale musí umět i *přidat* žáka, který nejde → rozbalí **celý roster třídy** s přepínači. Tenze „zobrazovat jen strávníky" × „umět přidat" je vyřešená tím, že plný roster se ukáže jen v edit módu.
- Listovatelné datum (default dnes), vlastní dlaždice v nav.

### Řešení
Migrace 083 přidává **3 SECURITY DEFINER RPC, bez nové tabulky** (jen čtení/zápis nad `lunch_orders` + `students`/`groups`):
- `lunch_day_roster(date)` — strávníci dne (jméno + třída), guard = jakýkoli `staff`. Množina = `lunch_effective_orders` (join na `students`, třída = agregát `groups.name` přes `group_memberships(valid_to IS NULL)` pro `lunch_school_year(date)` — shodně s `get_students_roster`/073).
- `lunch_day_editable(date)` — celý aktivní roster dne + `ordered`/`auto_cancelled`, guard = `is_director_or_vp()`. `auto_cancelled` (objednáno, ale nejí kvůli omluvence/neškolnímu dni) se počítá stejnou logikou jako `lunch_month`.
- `lunch_staff_set_order(student,date,ordered)` — zápis, guard = `is_director_or_vp()`, vynucuje `lunch_ordering_open(date)` (stejná uzávěrka jako rodičovský `lunch_set_order`), zapíše `created_by = auth.uid()`.

UI: server komponenta [`page.tsx`](../../app/dashboard/obedy/page.tsx) (`force-dynamic`, async `searchParams` datum+edit; read view po třídách + součty; edit mód přes `?edit=1` jen pro ředitele/zástupce a jen když `orderingOpen`), klientská [`LunchEditBoard.tsx`](../../app/dashboard/obedy/_components/LunchEditBoard.tsx) (checkboxy, `useTransition`, `router.refresh()`), akce [`lunch-dashboard.ts`](../../app/actions/lunch-dashboard.ts). Nav dlaždice „Obědy — kdo jde na oběd" pro všechny staff (overflow), stará settings dlaždice přejmenována na „Obědy — nastavení SMS", obě ve skupině „Výkazy a provoz"; `/dashboard/obedy` přidán do `DEMO_READONLY_HREFS`.

### Poučení
- **Uzávěrka jako invariant zjednodušuje architekturu.** Tím, že zápis personálu podléhá stejné uzávěrce jako rodič, zůstal počet pro jídelnu finální — nebylo potřeba řešit žádnou synchronizaci/dorovnání SMS ani druhý cron. Když nová role zapisuje do existujícího toku, první otázka má být „drží náš dosavadní invariant, nebo ho tato role poruší?".
- **RPC guard patří do těla funkce, ne do RLS.** Personál (guide/asistent/vp/…) na `lunch_orders` přes RLS nevidí (policy jen guardian/director). Místo přidávání RLS policy je čistší nový SECURITY DEFINER RPC s explicitním role-guardem uvnitř + `REVOKE PUBLIC` / `GRANT authenticated` — konzistentní s `druzina_den_ocekavani`/081 a s [[secdef-execute-hardening]].
- **Generátor typů nezná nullabilitu `string_agg`.** `db:types` otypoval `trida: string` (ne `string | null`), i když u žáka bez třídy vrací RPC NULL. Kód to ošetřuje `?? 'Bez třídy'` — na RPC vracející agregát se nedá spoléhat na non-null z generovaných typů.

---

## 2. Doklizení `(supabase as any)` v Bulletinu (vedlejší)

**Soubory:** `app/api/bulletin/posts/route.ts`, `app/dashboard/bulletin/[id]/page.tsx`

Po `npm run db:types` (spuštěném kvůli obědům) se do `types/database.ts` doplnily i objekty modulu Bulletin (`bulletin_post_students`, RPC `bulletin_resolve_target_students`, `get_bulletin_read_by_class`), které předtím chyběly a nutily 3 `(supabase as any)` casty. Casty i jejich `eslint-disable` komentáře odstraněny → `check:as-any` zpět na **0/0** (baseline držena).

### Poučení
Ratchet `check:as-any` je citlivý na to, že se migrace pouští ručně a `types/database.ts` zastarává. Pokud přidávám vlastní RPC, otypuju je rovnou v `database.ts` (ať cast nevznikne); a když už jednou `db:types` běží, vyplatí se posbírat i cizí zastaralé casty, které tím spadnou „zadarmo".

---

## Ověření

- `npx tsc --noEmit` — **0 chyb**. `npm run check:as-any` — **0/0**. ESLint nových souborů čistý (v bulletin page zůstává 1 pre-existing warning `_id` unused, nesouvisí).
- `npm run build` — zelený, route `/dashboard/obedy` registrovaná jako dynamická (`ƒ`).
- Migrace 083 spuštěna ručně v Supabase, `db:types` přegenerováno — RPC `lunch_day_roster/editable/staff_set_order` v typech, tvar sedí.
- CI na PR #14 zelené (guard/check:as-any + build, Vercel prod i demo). PR #14 mergnut do master (`e45ad0e`) → Vercel nasadil na produkci.
- Vizuální ověření v prohlížeči (přihlášený personál) zůstává na uživateli — Claude se nepřihlašuje.

## Návazně

Produkční commit `e45ad0e` publikován jako veřejný release **`v3.1.0`** (snapshot přes [[publish-release]] recept; public commit `d7e3203` na `github.com/nilsson-cz/nilsson`, gitleaks bez nálezu). GitHub Release / release notes na v3.1.0 zatím nezaložené (ruční krok).

## Související

- [[Obědy]] — modul, do kterého to patří
- [[secdef-execute-hardening]] — proč guard v těle RPC + REVOKE/GRANT
- [[Zveřejnění IS]] — release v3.1.0, který tento modul vzal ven
