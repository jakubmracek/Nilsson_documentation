# TRD — Fotogalerie „Ze života školy": zvětšení a stažení fotek

Datum: 2026-10-27 · Stav: návrh ke schválení · Modul: [[Rodičovský portál]] / zeď Ze života školy

## Problém

Detail příspěvku v portálu (`/portal/ze-zivota-skoly/[slug]`) i na tokenové zdi (`/zivot/[slug]`) zobrazuje fotky jen jako čtvercovou mřížku (`object-cover`, ořez). Fotku nejde otevřít ve větším, listovat, ani stáhnout. Rodiče galerii prohlížejí hlavně na mobilu.

## Výchozí stav (zjištěno v kódu)

- Obě stránky jsou server komponenty, data ze sdíleného `app/zivot/_lib/wall.ts` → `getPostBySlug()` vrací `gallery.photos[] = { id, url, caption, sort_order }`.
- `url` = **podepsaná URL** privátního bucketu `zivot-photos` (Supabase Storage), TTL 3600 s. Podepisuje se až PO anon RLS dotazu (`photo_is_publishable`) → klient dostane URL jen k fotkám, které smí vidět. Tenhle GDPR gating zůstává beze změny.
- Fotky se ukládají už zmenšené klientem při uploadu: delší strana 1600 px, JPEG q 0.85 (`PhotoUploader.tsx`), tj. typicky 200–500 kB. Originály neexistují.
- Mřížka dnes načítá rovnou tyto 1600px soubory (žádné náhledy).

## Technické možnosti

### 1. Zvětšení (lightbox)

| Varianta | Pro | Proti |
|---|---|---|
| **A — vlastní komponenta nad nativním `<dialog>`** | 0 závislostí; `showModal()` dává zdarma focus trap, Esc, inert pozadí; přesně na míru portálu | swipe a ovládání si napíšeme sami (~200 řádků) |
| B — `yet-another-react-lightbox` | hotový swipe, pinch-zoom plugin, a11y | nová závislost + CSS, styl mimo portál; zoom u 1600px fotek moc nepřinese |
| C — PhotoSwipe | nejlepší zoom/gesta | těžší integrace s React 19/SSR, potřebuje rozměry fotek předem (máme jen u části fotek) |

**Doporučení: A.** Rozsah: klik na fotku → celoobrazovkový tmavý overlay, fotka `object-contain`, popisek, počítadlo „3 / 24", šipky ←/→ (klávesnice i tlačítka), swipe na mobilu (pointer events, práh ~50 px), Esc / tlačítko Zavřít, přednačtení sousedních fotek. Tlačítko Zpět v prohlížeči (Android) zavře lightbox místo odchodu ze stránky (`history.pushState` + `popstate`). Pinch-zoom: nativní zoom prohlížeče v overlayi nebráníme; vlastní zoom není v rozsahu.

### 2. Stažení jedné fotky

Supabase Storage podporuje u podepsané URL parametr `download` → server pošle `Content-Disposition: attachment; filename=…`. Funguje i cross-origin (atribut `<a download>` by u cizí domény prohlížeč ignoroval). Klient jen připojí `&download=<nazev>.jpg` k URL, kterou už má — **žádná změna na serveru ani nové podepisování**. Název souboru: `<slug-prispevku>-<poradi>.jpg`.

iOS Safari: stáhne do aplikace Soubory; „Uložit do Fotek" jde nativně dlouhým podržením fotky v lightboxu.

### 3. Stažení celé galerie (ZIP)

| Varianta | Pro | Proti |
|---|---|---|
| **A — ZIP v prohlížeči (`fflate`)** | žádná nová route ani re-autentizace (stačí URL, které klient už má); server nic nepočítá | paměť klienta (40 fotek ≈ 15 MB — v pohodě i na mobilu) |
| B — serverová route streamuje ZIP | funguje i se slabým klientem | nová API route s dvojí autentizací (portálová session vs. cookie tokenu `zivot_sess`), znovu RLS dotaz, limity Vercel funkce (čas/paměť) |

**Doporučení: A.** `fflate` je v `node_modules` už tranzitivně (přes `@react-pdf/renderer`), přidá se jako přímá závislost (~8 kB, jen do klientského bundlu detailu). JPEG se nekomprimuje (level 0 = jen zabalit). Průběh „Stahuji 12 / 40", jméno `<slug>.zip`. Fotky se stahují postupně (max 4 souběžně).

Předpoklad k ověření: Storage vrací CORS hlavičky pro `fetch()` z domény IS (Supabase Storage standardně `Access-Control-Allow-Origin: *`).

### 4. Vypršení podepsaných URL

URL platí 1 h od renderu. Kdo nechá stránku otevřenou déle, stahování/zobrazení selže → komponenta při chybě ukáže „Odkazy vypršely, obnovte prosím stránku." (Prodloužení TTL je zbytečné snížení ochrany.)

## Architektura

- Nová klientská komponenta `app/zivot/_components/PhotoGallery.tsx` (`'use client'`) = mřížka + lightbox + stahování. Props: `photos`, `slug`, `variant: 'portal' | 'zivot'` (barvy mřížky; lightbox je tmavý, nezávislý na tématu).
- Použije se v **obou** detailech (`app/portal/ze-zivota-skoly/[slug]/page.tsx`, `app/zivot/[slug]/page.tsx`) místo dnešního `<ul>`. Server stránky zůstávají server komponentami.
- `wall.ts`, `zivot-storage.ts`, RLS, schéma `web`: **beze změny**. Žádná migrace. Nesahá se na sdílený staff kód ani `proxy.ts` (mantinely zdi dodrženy).

## GDPR

Stažení nezpřístupňuje nic nového — jde o tytéž publikovatelné fotky, které rodič už vidí (a mohl by je uložit i dnes). Explicitní tlačítko ale usnadňuje šíření fotek cizích dětí. Návrh: pod galerií krátká poznámka „Fotografie jsou určeny pro osobní potřebu rodin. Prosíme, nesdílejte je dál (např. na sociálních sítích)."

## Mimo rozsah (pozdější možnosti)

- **Náhledy do mřížky** — dnes mřížka tahá 1600px soubory. Řešení: Supabase Image Transformations na signed URL (Pro: 100 zdrojových obrázků/měsíc v ceně, pak placené) nebo generovat 400px náhled už při uploadu (+ dávkový backfill). Samostatný úkol.
- Vlastní zoom v lightboxu, sdílení odkazu na konkrétní fotku, statistiky stažení.

## Ověření

- `npm run build` + lint + `check:as-any`.
- V prohlížeči: lightbox (klávesnice, swipe v mobilním viewportu, Esc, Zpět), stažení jedné fotky (hlavička `Content-Disposition`), ZIP (obsah + počet souborů), chování po vypršení URL.
