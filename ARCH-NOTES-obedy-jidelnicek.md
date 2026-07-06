# ARCH-NOTES — Modul Obědy: scraper jídelníčku (SOSTP)

> Zařaď jako sekci č. **___** (navazuje na vzor SECURITY DEFINER RPC ze sekcí 50–52).
> Migrace: **033**. Stav: nasazeno, ověřeno v produkci.

## Účel

Týdenní jídelníček jídelny Dobrovolců (SOSTP) se denně scrapuje a ukládá do Supabase jako **informativní** podklad — pro zobrazení rodičům a pro budoucí objednávkový modul (plánovaná migrace 034).

## Tok dat

GitHub Actions cron (denně 04:00 UTC ≈ 06:00 CEST) → `fetch` HTML stránky → cheerio převede na text → textový stavový automat naparsuje → idempotentní upsert do `lunch_menu_days` + `lunch_menu_items` přes `service_role` klient.

## Datový model (migrace 033)

- **`lunch_menu_days`** — `menu_date` (UNIQUE), `weekday` (1–7), `soup`, `soup_allergens smallint[]`, `week_start`, `week_end`, `source_url`, `raw_text` (snapshot pro re-parse/debug), `scraped_at`.
- **`lunch_menu_items`** — `day_id` FK (ON DELETE CASCADE), `option_no` (1–9), `description`, `allergens smallint[]`, UNIQUE`(day_id, option_no)`.
- **`lunch_allergens`** — číselník EU alergenů 1–14 (`name_cs`) pro zobrazení názvů.

## RLS

- FORCE RLS na všech třech tabulkách (standard dle ARCH-NOTES).
- SELECT policy `USING (true) TO authenticated` — jídelníček je **veřejné info** publikované na webu školy, takže není důvod ho skrývat; navíc tím odpadá nutnost řešit guardian vs. staff na úrovni řádků.
- **Žádná** INSERT/UPDATE/DELETE policy → zápis dělá výhradně `service_role` (BYPASSRLS) z cronu. `authenticated`/`anon` zapisovat nemůže.
- Pro portál/objednávky čti přes RPC **`get_lunch_menu_week(p_week_start date default null)`** (SECURITY DEFINER, STABLE, `search_path=public`), default = pondělí aktuálního ISO týdne (`date_trunc('week', current_date)`). Vrací řádek na den s položkami jako `jsonb`. Konzistentní s kanonickým portálovým patternem (sekce 50–52).

## Proč textový parser, ne CSS selektory

Stránka je server-rendered (žádný JS rendering), takže stačí `fetch` + cheerio — **žádný headless browser**. Parsování je ale záměrně **textový stavový automat nad řádky**, ne selektory:

- Struktura je „měkká" (nadpisy dnů `<strong>` + očíslované řádky), selektory by byly křehké vůči změnám DOMu.
- Kotví se na **řádek s rozsahem dat** týdne (regex `dd.mm. - dd.mm.`). Tím se přeskočí navigace, kde jsou taky odkazy „Jídelní lístek", ale bez data.
- Parsuje do dalšího holého nadpisu „Jídelní lístek" (= prázdná šablona příštího týdne) nebo do sekce „Nepřehlédněte".
- **Pojistka:** do výsledku jdou jen dny s ≥1 položkou → i kdyby slicing selhal, prázdná šablona se neuloží a nepřepíše reálná data.

## Záludnosti zdroje (ošetřené v parseru)

- Alergeny jako koncový blok čísel; parser toleruje rozbité `1,,,7` (vícenásobné čárky). **Pojistka:** pokud blok obsahuje číslo mimo 1–14, nebere se jako alergeny (ochrana proti náhodnému číslu na konci názvu).
- Polévka i u slepeného `-polévka` bez mezery.
- **Rok není v hlavičce** → dopočítává se z aktuálního data (okno ±180 dní), ošetřen přelom roku.
- Stránka obsahuje překlepy přímo v datech (`híuskové knedlíky`, `list.špenátem`) — ukládají se tak, jak jsou; případné čištění je věc zobrazovací vrstvy, ne scraperu.

## Idempotence

Upsert na `menu_date`; položky se na úrovni dne **mažou a vkládají znovu** (počet voleb se mezi běhy může měnit). Denní běh je proto bezpečný a samoopravný — a scrapuje se **denně**, ne jen 1×/týden, protože nevíme přesně, kdy škola publikuje nový týden.

## Provozní gotchas (důležité)

- **Node 22+ je ve workflow povinný.** `@supabase/supabase-js` eagerně inicializuje RealtimeClient (WebSocket) už v konstruktoru `SupabaseClient`. Node 20 nemá nativní globální `WebSocket` → `createClient` hodí výjimku *„Node.js 20 detected without native WebSocket support"*. Řešení: `node-version: 22` v `lunch-menu.yml`. (Záloha: nainstalovat `ws` a předat přes `transport`, ale Node bump je čistší a realtime tahle úloha nevyužívá.)
- **GitHub Actions má vlastní secrets**, oddělené od Vercelu (na sebe nevidí): `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DISCORD_LUNCH_WEBHOOK_URL`.
- `npm ci` vyžaduje commitnutý `package-lock.json` s `cheerio` + `tsx`.
- cron je v **UTC** (`0 4 * * *`), workflow běží jen z výchozí větve.
- Monitoring: při pádu / 0 dnech / varování jde alert na Discord (prefix `🍲 [jídelníček]`). Při změně šablony SOSTP je v `raw_text` snapshot k ladění.

## Vazba na objednávkový modul

Jídelníček je **čistě informativní**. Objednávky (migrace 034) budou vázat na **datum**, ne na `lunch_menu_items.option_no` — dítě si konkrétní jídlo vybírá na místě a neukládá se. Viz PRD modulu Obědy.
