# ARCH-NOTE: Fotogalerie „Ze života školy" — zvětšení fotek, stažení jedné fotky a celé galerie jako ZIP

**Datum:** 2026-10-27
**Modul:** [[Rodičovský portál]] — galerie Ze života školy (`/portal/ze-zivota-skoly/[slug]`) + tokenová zeď `/zivot/[slug]`
**Soubory:** `app/zivot/_components/PhotoGallery.tsx` (nový), `app/portal/ze-zivota-skoly/[slug]/page.tsx`, `app/zivot/[slug]/page.tsx`, `package.json` (+ `fflate`)
**Commity:** `9ef40a7` (feat), `84b3804` (merge PR #68)
**TRD:** [[TRD-fotogalerie-lightbox-stazeni-2026-10-27]]

---

## Přehled

Galerie v detailu příspěvku byla jen čtvercová mřížka s oříznutými fotkami — nešlo je otevřít ve větším ani stáhnout. Nejdřív vznikl TRD s variantami, uživatel schválil všechna doporučení (lightbox i stahování, portál i tokenová zeď, GDPR poznámka). Postavena jedna sdílená klientská komponenta `PhotoGallery`, která nahradila mřížku na obou stránkách. Bez migrace, bez změny serverové logiky.

---

## 1. Lightbox nad nativním `<dialog>`

### Řešení
Vlastní komponenta, žádná knihovna. `dialog.showModal()` dává zdarma focus trap, Esc a inertní pozadí. Doplněno: šipky (klávesnice + tlačítka, na mobilu skryté), swipe přes `touchstart/touchend` (práh 50 px, ignoruje víc prstů a přiblíženou stránku → nativní pinch-zoom funguje), počítadlo, popisek, přednačtení sousedních fotek, zámek scrollu stránky.

Tlačítko **Zpět** (Android) zavírá lightbox: při otevření `history.pushState(null, '')`, při zavření `history.back()`, `popstate` nastaví index na null. Next 16 nativní `pushState` podporuje (docs „Native History API"). Esc se zachytí v `onCancel` s `preventDefault`, aby šel stejnou cestou a historie zůstala srovnaná.

### Poučení
- Touch eventy místo pointer events: v overlayi bez `touch-action` prohlížeč horizontální gesto „ukradne" a pošle `pointercancel`.
- `bg-black/95` nechávalo prosvítat mřížku pod dialogem → plně černé pozadí.

---

## 2. Stažení jedné fotky

### Řešení
Supabase Storage u podepsané URL respektuje query parametr `download=<jméno>` → `Content-Disposition: attachment`. Klient ho jen připojí k URL, kterou už má (`new URL(url).searchParams.set('download', …)`) — nic se nepodepisuje znovu. Název `<slug>-NN.jpg`.

### Poučení
Atribut `<a download>` prohlížeč u cizí domény (Storage) ignoruje — stažení musí vynutit hlavička ze serveru. storage-js `createSignedUrl({download})` dělá přesně totéž připojení parametru, proto to jde i čistě na klientu.

---

## 3. Stažení celé galerie jako ZIP

### Řešení
V prohlížeči: `fetch` podepsaných URL (max 4 souběžně, průběh „Stahuji N / M"), `zipSync(files, { level: 0 })` z `fflate` (dynamický import, JPEG se nekomprimuje), blob → `<a download>` (same-origin blob funguje). Serverová route zamítnuta — musela by řešit dvojí autentizaci (portálová session vs. cookie `zivot_sess`) a limity Vercel funkce.

Storage vrací `Access-Control-Allow-Origin: *` (ověřeno curl), neplatný/vypršelý token → HTTP 400 → komponenta hlásí „Odkazy na fotky vypršely. Obnovte prosím stránku." (podepsané URL mají TTL 1 h).

---

## GDPR

Gating se nemění: URL dostane klient jen pro fotky, které prošly anon RLS (`web.photo_is_publishable`) ve `wall.ts`. Stažení tedy nezpřístupňuje nic nového, jen to usnadňuje → pod galerií poznámka „Fotografie jsou určeny pro osobní potřebu rodin. Prosíme, nesdílejte je dál (např. na sociálních sítích)." (schváleno uživatelem).

---

## Ověření

- `tsc --noEmit`, eslint, `check:as-any` (0), `next build`; CI (Vercel nilsson + nilsson-demo, guard) zelené.
- Dočasná testovací stránka v prohlížeči (dev server z worktree, po testu smazána): otevření, šipky + přetočení, Esc, Zpět, swipe v mobilním viewportu, ZIP (6 souborů, správné názvy — blob zachycen v JS), hláška při 400.
- Stažení reálné fotky přes `download` parametr ověřil uživatel na produkci po nasazení („všechno OK").

## Vedlejší nález (nezasahováno)

- **Mřížka tahá plné 1600px fotky** (žádné náhledy). Řešení do budoucna: Supabase Image Transformations na signed URL (Pro: 100 zdrojových obrázků/měsíc v ceně) nebo 400px náhled při uploadu + backfill. Samostatný úkol.
- Lokální `.env.local` nemá `SUPABASE_SERVICE_ROLE_KEY` (je jen ve Vercelu) → podepsané URL nejde lokálně vyrobit.
- Preview server z `.claude/launch.json` startuje v hlavním checkoutu, ne ve worktree — pro worktree nutná dočasná konfigurace s `npm --prefix`.

## Související

- [[TRD-fotogalerie-lightbox-stazeni-2026-10-27]] — návrh a varianty
- [[Rodičovský portál]] — galerie v portálu
