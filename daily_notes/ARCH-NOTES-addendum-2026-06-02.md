# ARCH-NOTES — Addendum 2026-06-02

Navazuje na ARCH-NOTES addendum 2026-05-31.
Autoři: Ing. Jakub Mráček + Claude Sonnet 4.6

---

## 48. [[Rodičovský portál]] — bottom nav, dark mode, nové moduly (2026-06-02)

### 48.1 Motivace

`app/portal/layout.tsx` měl pouze desktop topbar bez mobilní navigace.
Dark mode nebyl aplikován na portálové komponenty (vznikl po [[Rodičovský portál]]).
Přidány moduly [[Třídní kniha]] a [[Zprávy a bulletin]].

### 48.2 Nové soubory

```
app/portal/
├── layout.tsx                       ← aktualizován: dark: varianty, import PortalBottomNav
├── _components/
│   └── PortalBottomNav.tsx          ← NOVÝ: Client Component, fixed bottom nav (mobile only)
├── tridnice/
│   └── page.tsx                     ← NOVÝ: Server Component, náhled [[Třídní kniha]]
└── zpravy/
    └── page.tsx                     ← NOVÝ: Server Component, [[Zprávy a bulletin]]/[[Zprávy a bulletin]]
```

### 48.3 Bottom nav architektura

`PortalBottomNav` je Client Component (potřebuje `usePathname` pro aktivní stav).
Zobrazuje se pouze na `sm:hidden` (mobile breakpoint = < 640px).
Topbar desktop navigace: `hidden sm:flex`.

5 položek:
| Položka | Href |
|---------|------|
| [[Omluvenky]] | `/portal/[[Omluvenky]]` |
| [[Docházka]] | `/portal/dochazka` |
| [[Platby]] | `/portal/[[Platby]]` |
| [[Třídní kniha]] | `/portal/tridnice` |
| [[Zprávy a bulletin]] | `/portal/zpravy` |

Aktivní položka: `text-orange-500 dark:text-orange-400` (brand color).
Výška bottom nav: `h-16` + safe area spacer pro iPhone home indikátor.
`main` element má `pb-24 sm:pb-6` — prostor pro bottom nav na mobile.

### 48.4 Dark mode v portálovém layoutu

[[Rodičovský portál]] byl vytvořen před dark mode implementací (2026-05-13 vs 2026-06-01).
Pravidlo z ARCH-NOTES sekce 33 aplikováno zpětně:

| Element | Light | Dark |
|---------|-------|------|
| Wrapper | `bg-gray-50` | `dark:bg-stone-950` |
| Topbar | `bg-white` | `dark:bg-stone-900` |
| Topbar border | `border-gray-200` | `dark:border-stone-700` |
| Název školy | `text-gray-900` | `dark:text-stone-100` |
| Nav linky | `text-gray-600` | `dark:text-stone-400` |
| Jméno uživatele | `text-gray-500` | `dark:text-stone-400` |
| Odhlásit | `text-gray-400` | `dark:text-stone-500` |
| Footer | `text-gray-300` | `dark:text-stone-700` |
| Bottom nav bg | `bg-white` | `dark:bg-stone-900` |
| Bottom nav border | `border-gray-200` | `dark:border-stone-700` |
| Aktivní ikona | `text-orange-500` | `dark:text-orange-400` |

### 48.5 Modul [[Třídní kniha]] (`/portal/tridnice`)

**Zobrazuje:** záznamy [[Třídní kniha]] skupiny dítěte přihlášeného guardiana.
**Kalendářní navigace:** URL parametr `?mesic=YYYY-MM`. Výchozí = aktuální měsíc.
Blokováno: navigace do budoucnosti, zpět do minulosti max. do září 2025.

**Datový zdroj:** `tridni_kniha_zaznamy` + JOIN `svp_vazby` + `svp_vystupy`.
RLS migrace 027 filtruje automaticky — aplikační vrstva nepotřebuje explicitní
filtr na guardian_id.

**ŠVP výstupy:** zobrazeny za `<details>` elementem (collapsed by default).
Uživatel rozklikne pokud má zájem — neznepřehledňuje hlavní obsah.

**`(supabase as any).from()`:** `tridni_kniha_zaznamy` a `svp_vazby` jsou
v typovém stubu — nutný cast dokud se typy neregenerují (viz sekce 33.4).

### 48.6 Modul [[Zprávy a bulletin]] (`/portal/zpravy`)

**Zobrazuje:** posty z `bulletin_posts` kde je guardian příjemcem
(`bulletin_post_recipients.guardian_id = current_guardian_id()`).
RLS migrace 027 filtruje automaticky.

**Segmentace:**
- Aktivní posty: `valid_until IS NULL OR valid_until >= dnes`
- Archivní posty (posledních 3 měsíce): `valid_until < dnes` — za `<details>` elementem

**Podmínka zobrazení:** `email_sent_at IS NOT NULL` — drafty se rodičům nezobrazí.

**Tělo [[Zprávy a bulletin]]:** `whitespace-pre-line` — zachovává odřádkování z Markdownu
bez nutnosti parsovat Markdown na straně klienta ([[Rodičovský portál]] je lightweight).
Pro plný Markdown rendering by bylo třeba `marked` (viz `emails/BulletinEmail.tsx`).

---

## 49. Migrace 027 — RLS rozšíření pro portálové moduly (2026-06-02)

### 49.1 Přidané politiky

| Tabulka | Politika | Podmínka |
|---------|----------|---------|
| `tridni_kniha_zaznamy` | `tkz_guardian_select` | `is_guardian()` + `group_id IS NULL` OR `group_memberships` JOIN |
| `svp_vystupy` | `svp_vystupy_guardian_select` | `is_guardian()` |
| `svp_vazby` | `svp_vazby_guardian_select` | `is_guardian()` + JOIN na `tridni_kniha_zaznamy` |
| `bulletin_posts` | `bp_guardian_select` | `is_guardian()` + EXISTS v `bulletin_post_recipients` |
| `bulletin_post_recipients` | `bpr_guardian_select` | `is_guardian()` + `guardian_id = current_guardian_id()` |

### 49.2 Návrhová rozhodnutí

**`tkz_guardian_select` — `group_id IS NULL` větev:**
Záznamy bez `group_id` jsou školní záznamy (prázdniny, ředitelské volno,
celoškolní akce) — relevantní pro všechny rodiče bez ohledu na skupinu.
Guardian je vidí vždy.

**`svp_vystupy` — bez row-level filtru:**
Číselník výstupů ŠVP je pedagogická referenční data bez citlivého obsahu.
Politika `is_guardian()` stačí — není potřeba filtrovat per žák/skupina.
Konzistentní s přístupem pro staff (`current_staff_role() IS NOT NULL`).

**Pouze SELECT politiky:**
Guardian nikdy nezapisuje do [[Třídní kniha]], ŠVP vazeb ani [[Zprávy a bulletin]].
Žádné INSERT/UPDATE/DELETE politiky pro guardiana na těchto tabulkách.

### 49.3 Sanity check po nasazení

```sql
SELECT policyname, tablename, cmd
  FROM pg_policies
 WHERE policyname IN (
   'tkz_guardian_select', 'svp_vystupy_guardian_select',
   'svp_vazby_guardian_select', 'bp_guardian_select', 'bpr_guardian_select'
 )
 ORDER BY tablename;
-- Očekáváno: 5 řádků, všechny cmd='SELECT'
```

Test jako guardian (v Supabase SQL Editoru s impersonací):
```sql
SET LOCAL role = authenticated;
SET LOCAL "request.jwt.claims" = '{"sub": "<guardian-auth-uid>"}';

-- Záznamy [[Třídní kniha]] skupiny dítěte:
SELECT COUNT(*) FROM tridni_kniha_zaznamy;
-- Očekáváno: záznamy skupiny dítěte guardiana (ne 0, ne všechny záznamy)

-- [[Zprávy a bulletin]] kde je guardian příjemcem:
SELECT COUNT(*) FROM bulletin_posts;
-- Očekáváno: pouze posty kde guardian figuruje v bulletin_post_recipients
```

---

## Aktualizace sekce 1.3 — schéma souborů projektu

Do `supabase/migrations/` přidat:

```
└── 027_rls_portal_guardian.sql     ← RLS SELECT politiky pro guardian ([[Třídní kniha]], ŠVP, [[Zprávy a bulletin]])
```

Do `app/portal/` přidat/upravit:

```
├── layout.tsx                       ← aktualizován: dark: varianty, PortalBottomNav
├── _components/
│   └── PortalBottomNav.tsx          ← NOVÝ: mobile bottom nav (Client Component)
├── tridnice/
│   └── page.tsx                     ← NOVÝ: náhled [[Třídní kniha]] (Server Component)
└── zpravy/
    └── page.tsx                     ← NOVÝ: [[Zprávy a bulletin]]/[[Zprávy a bulletin]] (Server Component)
```
