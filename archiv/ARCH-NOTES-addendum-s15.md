## 15. UI architektura — aplikační vrstva (Fáze aplikace)

> Přidat do ARCH-NOTES-v1_3.md jako sekce 15.
> Zachycuje rozhodnutí učiněná při implementaci aplikační vrstvy (magic link auth + dashboard).

---

### 15.1 Autentizace — dva Supabase klienti

Projekt používá **dva oddělené klienty** — neplést:

| Soubor | Funkce | Kde použít |
|--------|--------|-----------|
| `lib/supabase.ts` | `createBrowserClient` | Client Components (`'use client'`) |
| `lib/supabase-server.ts` | `createServerClient` + cookies | Server Components, Route Handlers, Server Actions |

**Proč dva?**
Server klient čte/zapisuje cookies přes `next/headers` — v browser kontextu nedostupné.
Browser klient používá cookie store prohlížeče přímo.
Záměna způsobí: session leak, RLS bypass, nebo runtime chybu.

**Kritické:** Nikdy nepoužívat `service_role` key v klientu dostupném z browseru.
FORCE RLS platí i pro Edge Functions s `service_role` — viz ARCH-NOTES sekce 10.

---

### 15.2 Middleware — `getUser()` vs `getSession()`

Middleware vždy volá `supabase.auth.getUser()`, nikdy `getSession()`.

`getSession()` čte JWT payload přímo z cookie bez server-side validace.
Manipulovaný cookie by prošel jako validní session.
`getUser()` vždy ověří token proti Supabase Auth serveru — latence ~50 ms,
bezpečnost nezpochybnitelná.

---

### 15.3 Staff-only login — explicitní check v callbacku

`app/auth/callback/route.ts` po výměně PKCE code za session **explicitně ověří**:
1. `staff.id = auth.uid()` — email je registrovaný zaměstnanec
2. `staff.is_active = true` — účet není deaktivován

Pokud selže → `supabase.auth.signOut()` + redirect na `/login?error=not_staff`.

**Proč nestačí RLS?**
RLS by cizímu uživateli vrátil prázdné výsledky, ale IS by mu zobrazil přihlášené UI.
Explicitní check to vyřeší dřív — uživatel se do systému vůbec nedostane.

`signInWithOtp` má `shouldCreateUser: false` — Supabase nevytvoří nový `auth.users`
záznam pro neznámý email. Cizí email → Supabase vrátí chybu → formulář zobrazí
vágní hlášku (bezpečnost: neprozrazovat, zda email existuje).

---

### 15.4 Dashboard layout — responsive strategie

**Desktop (lg+):** Sidebar 240px (fixní) + main area (flex-1, scrollovatelný)
**Mobile (<lg):** Topbar 56px (fixní nahoře) + main area (scrollovatelný) + bottom nav 64px (fixní dole)

Bottom nav zobrazuje pouze nejdůležitější položky (`bottomNav: true` v `NAV_ITEMS`).
Sidebar na mobilu není — hamburger menu se záměrně nepoužívá (horší UX pro palec).

`pb-20 lg:pb-0` na main area kompenzuje výšku bottom nav na mobilu.
`h-dvh` (dynamic viewport height) místo `h-screen` — správně funguje na iOS Safari
kde `100vh` nezohledňuje system UI (adresní řádek, home indicator).

---

### 15.5 Role-based navigace — statická v první verzi

`NAV_ITEMS` v `components/nav/AppNav.tsx` definuje viditelnost položek per role:

```typescript
type NavItem = {
  href: string
  roles: StaffRole[]   // kdo vidí položku
  bottomNav?: boolean  // zobrazit v bottom nav
}
```

**Budoucí rozšíření (admin panel):**
Konfigurace se přesune do tabulky `ui_role_config` (nebo JSONB sloupec
na `staff` tabulce) — ředitel ji bude editovat v `/dashboard/nastaveni`.
Schéma tabulky a API route přidat jako samostatný úkol před go-live.

Statická konfigurace je v pořádku pro v1 — tým je malý a role stabilní.

---

### 15.6 Widget architektura

Každý dashboard widget je samostatný Server Component s vlastním `fetch`.
Data se načítají paralelně přes `Promise.all` v `fetchDashboardData()`.

```
DashboardPage (Server Component)
  ├── fetchDashboardData() — Promise.all([alerts, students])
  ├── AlertsWidget          — Server Component, data z fetch
  ├── StudentsOverviewWidget — Server Component, data z fetch
  ├── StudentSearchWidget   — CLIENT Component (interaktivní hledání)
  └── …další widgety        — Server Components (zatím placeholdery)
```

`StudentSearchWidget` je Client Component — volá Supabase přímo z browseru,
debounce 250 ms, RLS zajistí filtraci podle skupiny průvodce.

Při přidávání nových widgetů: preferovat Server Components pro read-only data,
Client Components pouze pro interaktivní prvky.

---

### 15.7 Chybové kódy na `/login`

Route `/auth/callback` při odmítnutí přesměruje na `/login?error={kód}`.
`app/login/page.tsx` čte parametr z URL a zobrazí lokalizovanou zprávu.

Aktuální kódy:

| Kód | Příčina |
|-----|---------|
| `invalid_link` | Chybějící nebo expirovaný `code` parametr |
| `session_exchange` | `exchangeCodeForSession` selhalo |
| `auth_failed` | `getUser()` selhalo po výměně |
| `not_staff` | Email není v tabulce `staff` |
| `inactive` | `staff.is_active = false` |
| `server_error` | Neočekávaná DB chyba při staff lookup |

Hlášky jsou záměrně vágní pro veřejnost — přesná příčina je v server logu.

---

*Sekce 15 přidána 2026-05-06 — aplikační vrstva auth + dashboard.*
