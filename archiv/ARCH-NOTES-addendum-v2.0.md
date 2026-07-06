# ARCH-NOTES — Addendum v2.0
# Připojit na konec ARCH-NOTES-v1.9.md
# Datum: 2026-05-13 | Navazuje na TRD v2.1

---

## Aktualizace sekce 1 — RLS helper hierarchie

Rozšířená hierarchie po implementaci rodičovského portálu (migrace 019):

```
current_staff_id()              current_guardian_id()
current_staff_role()            is_guardian()
    ↓                               ↓
is_director()                   guardian_can_access_student()
is_director_or_vp()
staff_can_access_student()
    ↓
can_read_student()
can_read_guardian()
staff_can_read_campaign()
```

Guardian funkce mají stejné atributy jako staff: `SECURITY DEFINER + STABLE + SET search_path = public`.
Kritické: stejný důvod jako u staff — bez SECURITY DEFINER by `guardians` tabulka
způsobila rekurzi přes RLS.

---

## 25. Omluvenky — implementační poznámky (migrace 018 + 019, 2026-05-13)

### 25.1 Přehled

| Migrace | Obsah |
|---------|-------|
| `018_omluvenky.sql` | `absence_requests`, FK `attendance_records.absence_request_id`, RLS pro staff |
| `019_guardian_auth.sql` | `guardians.user_id`, `entered_by_staff_id` → nullable, guardian helper funkce, rozšířené RLS |

### 25.2 Tabulka `absence_requests`

Dva klíčové sloupce pro právní doložitelnost:

| Sloupec | Význam |
|---------|--------|
| `requested_by_guardian_id` | Právní původ žádosti — kdo ji fakticky inicioval |
| `entered_by_staff_id` | Kdo zapsal do IS — NULL pokud rodič přes portál, UUID pokud průvodce za rodiče |

`entered_by_staff_id` je **nullable** (migrace 019) — původně NOT NULL v návrhu (TRD sekce 4.4),
uvolněno pro rodičovský portál. Constraint `check_reviewed_when_decided` zůstává:
`status != 'pending' → reviewed_by IS NOT NULL`.

### 25.3 Schválení → průpis do attendance_records

`approveOmluvenka()` Server Action:
1. UPDATE `absence_requests.status = 'approved'`, nastaví `reviewed_by` + `reviewed_at`
2. Vygeneruje `attendance_records` pro každý **pracovní den** (Po–Pá) v rozsahu
3. Čtvrtek = 6 hodin (terénní program), ostatní dny = 4 hodiny
4. `status = 'absent_excused'` (ne `'omluven'` — viz TRD sekce 5.9)
5. Propojí přes `absence_request_id` FK

**Pozor:** `attendance_records` nemá UNIQUE constraint na `(student_id, date)` —
duplicitní záznamy jsou technicky možné. V praxi průvodce vidí, zda záznamy
existují. Budoucí TODO: ON CONFLICT DO UPDATE.

### 25.4 RLS strategie — souběžné politiky

Tabulka `absence_requests` má **6 oddělených politiky** (staff + guardian varianty):

| Politika | Role | Operace |
|----------|------|---------|
| `staff_absence_requests_select` | staff (přes `can_read_student`) | SELECT |
| `guardian_absence_requests_select` | guardian (vlastní omluvenky) | SELECT |
| `staff_absence_requests_insert` | director/vp/guide | INSERT |
| `guardian_absence_requests_insert` | guardian (vlastní dítě) | INSERT |
| `staff_absence_requests_update` | director/vp/guide | UPDATE (schválení) |
| — | guardian | UPDATE **zakázán** |

Guardian INSERT má dodatečnou podmínku: `entered_by_staff_id IS NULL` — zabrání
guardianovi podvrhnout staff pole.

### 25.5 UI architektura

```
app/dashboard/omluvenky/
├── page.tsx                         ← seznam; čekající omluvenky mají žlutý tón
├── novy/
│   ├── page.tsx                     ← Server wrapper; přednačte žáky + mapu ZZ
│   └── _components/
│       └── NovaOmluvenkaForm.tsx    ← Client; dynamický select ZZ dle žáka
└── [id]/
    ├── page.tsx                     ← detail + seznam vygenerovaných záznamů
    └── _components/
        └── ApprovalPanel.tsx        ← Client; schválit / zamítnout se skrytou poznámkou

app/portal/
├── layout.tsx                       ← topbar pro rodiče; ověřuje is_guardian()
├── login/page.tsx                   ← magic link; shouldCreateUser: false
├── omluvenky/
│   ├── page.tsx                     ← seznam vlastních omluvenek
│   └── novy/
│       ├── page.tsx                 ← Server wrapper; jen vlastní dítka
│       └── _components/
│           └── GuardianOmluvenkaForm.tsx ← Client; pokud 1 dítě → skrytý select
└── dochazka/
    └── page.tsx                     ← přehled docházky za 60 dní, souhrn hodin
```

---

## 26. Rodičovský portál — architekturická rozhodnutí (2026-05-13)

### 26.1 Auth — magic link + auto-link

Guardian nepotřebuje admin zásah k aktivaci účtu. Flow:

1. Rodič zadá email na `/portal/login`
2. Supabase odešle magic link (`shouldCreateUser: false` — nevytváří se anonymní uživatelé)
3. `auth/callback/route.ts` zkontroluje v pořadí:
   - `staff` table → `/dashboard`
   - `guardians WHERE user_id = auth.uid()` → `/portal` (opakované přihlášení)
   - `guardians WHERE email = user.email AND user_id IS NULL` → auto-link + `/portal` (první přihlášení)
   - jinak → sign out + `/login?error=no_access`

**Auto-link:** první přihlášení zapíše `guardians.user_id = auth.uid()`. Bezpečnost:
magic link vyžaduje přístup k emailové schránce → úroveň zabezpečení odpovídá emailu.

### 26.2 Dual-role uživatel (jeden člověk = staff + guardian)

Rozhodnutí: **dva oddělené auth.users záznamy = dva emaily**.

```
staff email    → staff table → /dashboard (ředitel)
guardian email → guardians table → /portal (rodič)
```

Callback kontroluje nejdřív `staff`, pak `guardian`. Jeden email pro obě role
by způsobil, že staff role vždy vyhraje → guardian nikdy nedostupný.
Toto je záměrné omezení v1 — v budoucnosti lze řešit přes `user_roles` tabulku.

### 26.3 Middleware (proxy.ts) — Next.js 16

V Next.js 16+ se soubor jmenuje `proxy.ts` (ne `middleware.ts`) a export
musí být pojmenován `proxy` (ne `middleware`):

```typescript
// SPRÁVNĚ (Next.js 16):
export async function proxy(request: NextRequest) { ... }

// ŠPATNĚ (Next.js 15 / chybí přejmenování):
export async function middleware(request: NextRequest) { ... }
```

Chyba Turbopack: `Proxy is missing expected function export name`.

Middleware záměrně nekontroluje roli — pouze přítomnost session. Role check
probíhá v `layout.tsx` příslušné sekce (dashboard/portal). Důvod: middleware
nesmí číst z DB (výkon, edge runtime).

### 26.4 Zprávy — rozhodnutí

Komunikační modul (`comm_campaigns`, `comm_campaign_recipients`, `comm_log`)
zůstává v DB bez UI. Rodiče komunikují emailem (Resend), průvodci přes
stávající kanály. IS neposkytuje vlastní messaging.

### 26.5 Discord webhook — TODO (Fáze 2b)

Po zadání omluvenky rodičem chceme notifikovat průvodce na Discord.
Místo v kódu: `app/actions/portal-omluvenky.ts`, označeno komentářem
`// TODO: notifyStaff(...)`.

Implementace: `fetch(process.env.DISCORD_WEBHOOK_URL, { method: 'POST', body: JSON.stringify({ content: '...' }) })`.
Neblokující — obalit do `try/catch`, neovlivní výsledek akce při selhání.
