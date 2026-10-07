# ARCH-NOTE: Rychlé odkazy ředitele na dashboardu

**Datum:** 2026-10-07
**Modul:** [[Správa školy]] — dashboard ředitele (`/dashboard`)
**Soubory:** `app/dashboard/page.tsx`
**Commity:** `a34cf07` (feat: rychlé odkazy ředitele na často užívané agendy)

---

## Přehled

V mřížce widgetů na dashboardu ředitele zůstávalo jedno prázdné pole (5 widgetů v 3sloupcové mřížce). Přibyl do něj widget „Rychlé odkazy" — sekundární menu často užívaných agend ze Správy školy, aby ředitel nemusel přes rozcestník.

---

## 1. Widget „Rychlé odkazy"

**Soubor:** `app/dashboard/page.tsx` — `QuickLinksWidget`, `DIRECTOR_QUICK_LINKS`

### Řešení
- Zobrazuje se jen pro `role === 'director'`, za widgetem Platby.
- Položky (pořadí dle zadání uživatele): Rozvrh, Mapa pokroku, Školní družina, Veřejné finance, Obědy – nastavení (`/dashboard/sprava-skoly/obedy`), Výchovné poradenství (`/dashboard/vp`). V hlavičce odkaz „Správa školy →".
- Ikony, barevné nádechy a `href` se berou z `NAV_ITEMS` v `components/nav/nav-items.tsx` (jeden zdroj pravdy). `DIRECTOR_QUICK_LINKS` nese jen `href` + volitelný přepis labelu pro dashboard („Obědy – nastavení", „Výchovné poradenství"); v menu/rozcestníku zůstávají původní labely.
- Položka, jejíž `href` v `NAV_ITEMS` neexistuje, se tiše vynechá (žádný mrtvý odkaz).

### Poučení
Zkratky na dashboardu nedefinovat znovu (ikony/URL) — odkazovat do `NAV_ITEMS` podle `href`, ať se při přejmenování/přesunu agendy nerozjedou.

---

## Ověření

- `tsc --noEmit` čisté; ESLint hlásí jen dříve existující `any` v souboru, nový kód čistý.
- Vizuální kontrola po nasazení — na uživateli.

## Související

- [[Mapa pokroku]], [[Rozvrh]], [[Školní družina]], [[Obědy]], [[Výchovný poradce (VP)]] — cíle odkazů
