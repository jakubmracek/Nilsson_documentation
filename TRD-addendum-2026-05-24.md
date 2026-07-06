# TRD — Addendum 2026-05-24

Navazuje na TRD v2.1 + addenda 2026-05-19, 2026-05-20, 2026-05-21, druzina changelog 2026-05-16
Autori: Ing. Jakub Mracek + Claude Sonnet 4.6

---

## Changelog 2026-05-24

- **Rodicky portal — magic link auth: plne funkční.** Prelozeno ze Supabase SMTP
  na Resend Auth Hook. Vytvorena `app/auth/confirm/page.tsx` (klientska `verifyOtp`).
  Viz ARCH-NOTES sekce 40–44.
- **`proxy.ts` opraveno:** matcher rozsiren o `/auth/:path*`; bug v `setAll`
  (ztrata cookies) opraven. Viz ARCH-NOTES sekce 42.
- **RLS `can_read_guardian()` a `can_read_student()` rozsireny** o guardian vetev.
  Guardian nyni vidi vlastni zaznam a zaznamy vlastnich deti. Viz ARCH-NOTES sekce 43.
- **Guardian auto-link presunut do `portal/layout.tsx`.**
  Viz ARCH-NOTES sekce 44.

---

## Aktualizace sekce 1.2 — Autentizace

Nahradit odstavec o guardian magic link:

**Guardian (rodicky portal):** `shouldCreateUser: false`. Magic link email
odchazi pres **Resend Auth Hook** (`/api/auth/send-email`), ne pres Supabase SMTP.
Token je ve formatu `token_hash` — `verifyOtp()` probehne klientsky v
`app/auth/confirm/page.tsx` (Client Component, `createBrowserClient`).

Auto-link (`guardians.user_id = auth.uid()`) probehne pri prvnim prihlaseni
v `portal/layout.tsx` — ne v auth callbacku. Dusledek: guardian nepotrrebuje
admin zasah k aktivaci uctu.

**Kritická konfigurace (aktualizace):**
Supabase free tier v novem UI (2026) nema dostupnou SMTP sekci v dashboardu.
Reseni: **Resend Auth Hook** (`Authentication → Auth Hooks → Send Email`).
Toto je **prerekvizita nasazeni** — bez nej magic link emaily nedojdou.

---

## Aktualizace sekce 1.3 — schema souboru projektu

Do `app/auth/` pridat:

```
app/auth/
├── callback/route.ts    ← existujici; PKCE flow pro staff
├── confirm/
│   └── page.tsx         ← NOVY (2026-05-24); klientska verifyOtp pro guardian
├── error/
│   └── page.tsx         ← NOVY (2026-05-24); neplatny/expirovany token
└── signout/route.ts     ← existujici
```

Do `app/api/auth/` pridat:

```
app/api/auth/
└── send-email/
    └── route.ts         ← NOVY (2026-05-24); Resend Auth Hook endpoint
```

---

## Aktualizace sekce 4.4 — Omluvenky (auth flow uprava)

Sekci 26.1 (Auth — magic link + auto-link) v ARCH-NOTES aktualizovat:

Puvodni flow pres `auth/callback`:
```
magic link → /auth/callback?code=... → exchangeCodeForSession → auto-link → /portal
```

Aktualni flow pres `auth/confirm`:
```
magic link → /auth/confirm?token_hash=...&type=magiclink&next=/portal/omluvenky
  → verifyOtp() (klientsky, createBrowserClient)
  → session cookie zapsana browsere
  → router.replace('/portal/omluvenky')
  → portal/layout.tsx: auto-link pokud user_id IS NULL
  → portal se zobrazi
```

`auth/callback` zustava pro staff PKCE flow (magic link pres `/login`).
Pro guardian portal je kanonickym flow `auth/confirm`.

---

## Nova sekce — Env promenne: Resend Auth Hook

Pridat do prehledu env promennych:

| Promenna | Kde nastavit | Popis |
|----------|-------------|-------|
| `RESEND_API_KEY` | Vercel + `.env.local` | Resend API klic (citlivy); pouziva se i pro aplikacni emaily |
| `SEND_EMAIL_HOOK_SECRET` | Vercel + `.env.local` | Bearer token pro autorizaci Auth Hook requestu ze Supabase; generovat jako hex |

**Poznamka:** `RESEND_API_KEY` byl pravdepodobne jiz nastaven pro jine emaily
(Discord notifikace, VP alerty). Overit ze klic ma opravneni `Sending access`
pro domenu `zsvilekula.cz`.

---

## Aktualizace sekce 10.2 — Stav importu dat

Pridat radek:

| Akce | Obsah | Stav |
|------|-------|------|
| SQL UPDATE | `guardians.user_id` napárovano pro testovaci ucet `jakub.mracek@gmail.com` | ✅ 2026-05-24 |
| SQL UPDATE `can_read_guardian` | Guardian vetev pridana do RLS helper funkce | ✅ 2026-05-24 |
| SQL UPDATE `can_read_student` | Guardian vetev pridana do RLS helper funkce | ✅ 2026-05-24 |

---

## Aktualizace sekce 11 — Rozhodnute otazky

Pridat radek:

| # | Otazka | Rozhodnuti | Dopad na TRD |
|---|--------|------------|--------------|
| O13 | Supabase SMTP vs. Auth Hook pro magic link | Auth Hook (`send_email`) pres Resend API; SMTP sekce neni v novem Supabase UI dostupna | Sekce 1.2 aktualizovana; nova env sekce; soubory `app/api/auth/send-email/`, `app/auth/confirm/` |
| O14 | `verifyOtp` server-side vs. klientsky | Klientsky (`createBrowserClient` v Client Component) — jedina spolehlivá metoda pro zapsani session cookies v Next.js App Router bez PKCE flow | ARCH-NOTES sekce 41; `app/auth/confirm/page.tsx` |
| O15 | Guardian auto-link: kde provest? | V `portal/layout.tsx` — session je zarucene dostupna; ne v Route Handler kde cookies jeste nemusi byt precteny | ARCH-NOTES sekce 44; `app/portal/layout.tsx` |

---

## Aktualizace sekce 15.7 — Aktualni stav

Pridat radky:

- Rodicky portal: magic link end-to-end funkční (hook → email → confirm → session → portal) ✅
- `proxy.ts`: matcher opraven (`/auth/:path*`), `setAll` bug opraven ✅
- RLS `can_read_guardian()` + `can_read_student()`: guardian vetev pridana ✅
- Guardian auto-link: presunut do `portal/layout.tsx` ✅
- `app/auth/confirm/page.tsx`: klientska verifyOtp nasazena ✅
- `app/auth/error/page.tsx`: stranka pro neplatny token nasazena ✅

---

## Poznamky pro dalsi session

### Overit RLS pro dalsi portalove moduly

Po dnesnich opravach `can_read_student()` by mel guardian videt data docházky
(`attendance_records`) a omluvenek (`absence_requests`) — ale je treba overit
ze RLS politiky `guardian_absence_requests_select` a ekvivalent pro
`attendance_records` spravne funguje s novou guardian vetvou v `can_read_student`.

Testovaci dotaz:
```sql
-- Jako guardian: vidi vlastni omluvenky?
SELECT COUNT(*) FROM absence_requests
WHERE requested_by_guardian_id = '<guardian-id>';
-- Ocekavany vysledek: > 0 pokud nejake omluvenky existuji
```

### `student_guardian_links.platnost_do` konvence

Stejne jako `group_memberships.valid_to` — overit zda `platnost_do` aktivnich
vazeb je NULL nebo datum. RLS podminka `platnost_do IS NULL OR platnost_do >= CURRENT_DATE`
pokryva oba pripady.

### Portalova stranka Platby

`/portal/platby/page.tsx` je v TRD planovana (sekce 4.7.8).
Pred implementaci overit ze `can_read_student()` s guardian vetvou korektne
prochazi pres `payment_obligations → students → student_guardian_links`.
