## 34. Rodičovský portál — redesign layoutu a token systém (2026-06-19)

### Motivace

Uživatelský feedback (2026-06-17) odhalil tři kategorie problémů:
- Příliš světlý font v omluvenkových formulářích (hardcoded `text-gray-300`)
- Nadpisy sekcí v tmavě modré (`text-blue-900`) zanikaly v dark mode
- Nekonzistentní pozadí: Omluvenky/Docházka/Platby/Zprávy = bílé,
  Třídnice/Tripartity/Souhlasy = tmavě šedé — nesjednoceno

Kořenová příčina: každá stránka portálu používala vlastní Tailwind třídy
napřímo bez sdíleného token systému.

### Architekturická rozhodnutí

**1. Portálový token systém v `globals.css`**

Všechny barvy portálu jsou scoped pod `.portal-layout` jako CSS custom
properties (`--portal-text`, `--portal-surface`, `--portal-accent` atd.).
Dark mode varianty jsou v `.dark .portal-layout`. Výhody:
- Změna barvy na jednom místě se propaguje do všech sekcí
- Tailwind dark: varianty se z portálového kódu odstraní
- Personální dashboard není ovlivněn (jiný scope)

**2. Layout: topbar → sidebar**

Desktop layout změněn z horizontálního topbaru s přeplněnou navigací
(7 položek v řadě) na sidebar (220 px). Důvod: 7 textových odkazů
se nevejde na středně velké obrazovky bez overflow.

`PortalSidebar` je `'use client'` komponenta — potřebuje `usePathname()`
pro aktivní stav. Přijímá `fullName` a `initials` jako props ze
server komponenty `layout.tsx` (server ↔ client boundary zachována).

Mobile layout zachován: úzký topbar (48 px) + `PortalBottomNav`.

**3. `PortalThemeSwitcher` — sdílený localStorage klíč**

Klíč: `localStorage('theme')`, hodnoty: `'light' | 'system' | 'dark'`.
Třída `dark` se přidává/odebírá na `<html>` elementu.

Pokud personální dashboard používá `next-themes`: upravit
`PortalThemeSwitcher` aby volal `setTheme()` z `useTheme()` hooku
místo přímé DOM manipulace — klíč `'theme'` je kompatibilní.

**4. Nástěnka = Zprávy**

`bulletin_posts` (Nástěnka) a zprávy průvodce jsou sloučeny do
`/portal/zpravy`. Případná `/portal/nastenka` route → redirect.

**5. Dashboard `/portal`**

Nová stránka. Volá dvě nové RPC funkce:
- `get_guardian_unpaid_receivables()` — nezaplacené pohledávky
- `get_guardian_bulletin_posts(p_limit int)` — příspěvky z nástěnky

Obě funkce filtrují přes `guardian_id` odvozený z `auth.uid()`.
RPC shell (bez těla) je v `MIGRATION.md` — implementovat jako
migraci `026_portal_rpc.sql`.

### Nové soubory

| Soubor | Popis |
|--------|-------|
| `app/portal/layout.tsx` | Shell (sidebar + mobile topbar) |
| `app/portal/page.tsx` | Dashboard |
| `app/portal/_components/PortalSidebar.tsx` | Desktop sidebar |
| `app/portal/_components/PortalThemeSwitcher.tsx` | Přepínač motivu |
| `app/portal/_components/PortalBottomNav.tsx` | Bottom nav (6 položek) |
| `app/globals.css` | +portálový token systém |

### Migrace existujících stránek

Viz `MIGRATION.md` (dodáno s commitem). Klíčový find-and-replace:
`text-gray-300` → `text-[--portal-text]` (příčina světlého fontu).