# ARCH-NOTES — Addendum 2026-05-24

Navazuje na ARCH-NOTES v2.0 + addenda 2026-05-19, 2026-05-20, 2026-05-21, TRD_ARCHNOTES_druzina_changelog_20260516
Autori: Ing. Jakub Mracek + Claude Sonnet 4.6

---

## 40. Rodicky portal — auth flow: Resend Auth Hook (2026-05-24)

### 40.1 Problem: Supabase SMTP selhal

Puvodni konfigurace predpokladala vlastni SMTP pres Resend
(`smtp.resend.com:465`, API key jako heslo) nastaveny v
`Supabase → Project Settings → Auth → SMTP Settings`.

Po kontrole Auth Logs se ukazalo:

```json
{
  "action": "user_recovery_requested",
  "error": "535 Authentication credentials invalid",
  "msg": "500: Error sending magic link email"
}
```

**Pricina:** V novem Supabase UI (2026) neexistuje SMTP sekce v
`Settings` ani v `Authentication`. Custom SMTP byl bud presunut,
nebo neni dostupny na Free tieru v teto verzi dashboardu.

### 40.2 Reseni: Supabase Auth Hook `send_email`

Misto SMTP Supabase vola vlastni HTTP endpoint pri kazdem pozadavku
na odeslani emailu. Endpoint postara o doruceni pres Resend API.

**Tok:**
```
Uzivatel pozada magic link
  → Supabase vygeneruje token_hash
  → POST na /api/auth/send-email (Auth Hook)
  → endpoint postara o email pres Resend
  → rodic klikne na odkaz → /auth/confirm?token_hash=...
  → verifyOtp() → session → /portal/omluvenky
```

### 40.3 Implementace: `/api/auth/send-email/route.ts`

```typescript
import { Resend } from 'resend'
import { NextResponse } from 'next/server'

const resend = new Resend(process.env.RESEND_API_KEY)

export async function POST(request: Request) {
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.SEND_EMAIL_HOOK_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  const payload = await request.json()
  const { user, email_data } = payload
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://nilsson-two.vercel.app'

  const magicLink = email_data.token_hash
    ? `${siteUrl}/auth/confirm?token_hash=${email_data.token_hash}&type=magiclink&next=/portal/omluvenky`
    : null

  if (!magicLink) {
    return NextResponse.json({ error: 'Missing token_hash' }, { status: 400 })
  }

  await resend.emails.send({
    from: 'ZS Vilekula <noreply@zsvilekula.cz>',
    to: user.email,
    subject: 'Prihlaseni do rodicovského portalu',
    html: `... <a href="${magicLink}">Prihlasit se</a> ...`,
  })

  return NextResponse.json({ message: 'ok' })
}
```

**Klicove body:**
- Supabase posila `token_hash` (ne hotovy link) — link sestavujeme sami
- `from` musi byt z **overene domeny v Resend** (`zsvilekula.cz`, ne `vilekula.cz`)
- Autorizace pres `Bearer` header — secret sdili Supabase dashboard a `.env.local`

### 40.4 Konfigurace v Supabase

```
Authentication → Auth Hooks → + New hook
  Hook type:    Send Email
  HTTP endpoint: https://nilsson-two.vercel.app/api/auth/send-email
  Header name:  authorization
  Header value: Bearer <SEND_EMAIL_HOOK_SECRET>
```

### 40.5 Env promenne

| Promenna | Kde nastavit |
|----------|-------------|
| `RESEND_API_KEY` | Vercel + `.env.local` |
| `SEND_EMAIL_HOOK_SECRET` | Vercel + `.env.local` |

**Pravidlo:** `SEND_EMAIL_HOOK_SECRET` generovat jako hex (bez `/+= znaku`) —
stejny princip jako `CRON_SECRET` (viz ARCH-NOTES sekce 32.3).

---

## 41. `/auth/confirm` route — klientska verifyOtp (2026-05-24)

### 41.1 Problem: server-side cookie propagace

Puvodni implementace jako Route Handler (`app/auth/confirm/route.ts`) se
potykala s trvalym problemem: `verifyOtp()` probehlo, ale session cookie
neprezila redirect. Ladilo se pres pet iteraci:

| Pokus | Pristup | Vysledek |
|-------|---------|----------|
| 1 | `NextResponse.redirect()` + rucni kopirovani cookies | cookies nezapsany |
| 2 | `cookies()` z `next/headers` + `NextResponse.redirect()` | cookies nezapsany do redirectu |
| 3 | `response = NextResponse.redirect()` vytvoreny pred verifyOtp | `supabaseResponse` neexistuje v scope |
| 4 | HTML `<body><script>window.location.replace()</script>` (200 OK) | cookies zapsany, JS redirect |
| 5 | `page.tsx` Server Component + `cookies()` | `Cookies can only be modified in a Server Action or Route Handler` |
| **6** | **`page.tsx` Client Component + `createBrowserClient`** | **funguje** |

### 41.2 Reseni: klientska verifyOtp

`app/auth/confirm/page.tsx` (Client Component):

```typescript
"use client"
import { useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { createBrowserClient } from "@supabase/ssr"

function ConfirmInner() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const token_hash = searchParams.get("token_hash")
    const type = searchParams.get("type") ?? "magiclink"
    const next = searchParams.get("next") ?? "/portal/omluvenky"

    if (!token_hash) {
      router.replace("/auth/error?reason=missing_token")
      return
    }

    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    )

    supabase.auth.verifyOtp({ token_hash, type: type as "magiclink" | "email" })
      .then(({ error }) => {
        if (error) router.replace("/auth/error?reason=invalid_token")
        else router.replace(next)
      })
  }, [])

  return <p>Prihlasuji...</p>
}
```

**Proc to funguje:** `createBrowserClient` zavola `verifyOtp` primo v prohlizeci.
`supabase-js` zapise session cookies do browser cookie jar primo — bez server-side
response propagace. Teprve po zapisu cookie `router.replace()` naviguje dal.

**Dusledek:** `/auth/confirm` je jedina stranka portaloveho flow bez SSR.
Uzivatel vidi kratkodoby "Prihlasuji..." text (typicky < 1 sekunda).

### 41.3 Stranka `/auth/error`

Vytvorena `app/auth/error/page.tsx` pro neplatny nebo expirovany token.
Zobrazuje srozumitelnou hlasku a odkaz zpet na `/portal/login`.

**Pozor pri vytvareni souboru pres PowerShell:**
Stranka `auth/error/page.tsx` opakovane selhavala s Turbopack chybou
`Unexpected token. Did you mean {'>'} or &gt;?` pri viceriadkovych JSX elementech.
**Pricina:** Windows-1250 encoding nebo neocekavane znaky z copy-paste.
**Reseni:** Psat jednoduche jednoradkove JSX elementy bez diakritiky pri
prvnim deploymentu, hacky/carky dodat az po overeni buildu.

---

## 42. `proxy.ts` — opravy (2026-05-24)

### 42.1 Chybejici `/auth/:path*` v matcheru

Puvodni `config.matcher` neobsahoval `/auth/:path*`. Middleware nebezel
na `/auth/confirm` → session cookies se nerefreshovaly → `/portal` nevidel session.

**Oprava:**
```typescript
export const config = {
  matcher: [
    "/auth/:path*",      // pridano
    "/dashboard/:path*",
    "/portal/:path*",
    "/login",
  ],
}
```

### 42.2 Bug v `setAll`: ztrata cookies pri refreshi

Puvodni `setAll` implementace v proxy.ts vytvarela novy `supabaseResponse` uvnitr
callbacku a zahazovala driv nastavene headers (vcetne `x-pathname`):

```typescript
// SPATNE — zahazuje supabaseResponse pri kazdem setAll volani:
setAll(cookiesToSet) {
  cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
  supabaseResponse = NextResponse.next({ request })   // ← novy response = ztrata headers
  cookiesToSet.forEach(({ name, value, options }) =>
    supabaseResponse.cookies.set(name, value, options)
  )
}

// SPRAVNE — zapisovat cookies do existujiciho supabaseResponse:
setAll(cookiesToSet) {
  cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
  cookiesToSet.forEach(({ name, value, options }) =>
    supabaseResponse.cookies.set(name, value, options)
  )
}
```

Toto je znamou chybou v dokumentaci Supabase SSR — vzor s `supabaseResponse = NextResponse.next({ request })`
uvnitr `setAll` callbacku zpusobuje tichy state leak.

---

## 43. RLS rozsireni pro guardiana (2026-05-24)

### 43.1 Problem

Funkce `can_read_guardian()` a `can_read_student()` obsahovaly pouze vetvy pro
staff role. Guardian (ktery ma platnou session) nemohl cist vlastni zaznam ani
zaznamy vlastnich deti — RLS vracelo prazdny vysledek.

Dusledek: `portal/layout.tsx` nenasla guardian zaznam → redirect na `/dashboard`
→ crash (`TypeError: Cannot read properties of null`).

### 43.2 Oprava `can_read_guardian()`

Pridana vetev: guardian cte vlastni zaznam.

```sql
CREATE OR REPLACE FUNCTION public.can_read_guardian(p_guardian_id uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $fn$
  SELECT CASE
    WHEN EXISTS (
      SELECT 1 FROM guardians
      WHERE id = p_guardian_id AND user_id = auth.uid()
    ) THEN TRUE
    WHEN current_staff_role() IN ('director','vp','readonly') THEN TRUE
    WHEN current_staff_role() IN ('guide','assistant') THEN EXISTS (
      SELECT 1 FROM student_guardian_links sgl
      WHERE sgl.guardian_id = p_guardian_id
        AND staff_can_access_student(sgl.student_id)
        AND (sgl.platnost_do IS NULL OR sgl.platnost_do >= CURRENT_DATE)
    )
    ELSE FALSE
  END;
$fn$;
```

### 43.3 Oprava `can_read_student()`

Pridana vetev: guardian cte zaznamy vlastnich deti (pres `student_guardian_links`).

```sql
CREATE OR REPLACE FUNCTION public.can_read_student(p_student_id uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $fn$
  SELECT CASE
    WHEN EXISTS (
      SELECT 1 FROM student_guardian_links sgl
      JOIN guardians g ON g.id = sgl.guardian_id
      WHERE sgl.student_id = p_student_id
        AND g.user_id = auth.uid()
        AND (sgl.platnost_do IS NULL OR sgl.platnost_do >= CURRENT_DATE)
    ) THEN TRUE
    WHEN current_staff_role() IN ('director','vp','readonly') THEN TRUE
    WHEN current_staff_role() IN ('guide','assistant') THEN staff_can_access_student(p_student_id)
    ELSE FALSE
  END;
$fn$;
```

### 43.4 Obecne pravidlo

**Kazda RLS helper funkce ktera kontroluje pristup k entite musela byt
rozsirena o vetev pro guardian.** Vzor:

```sql
WHEN EXISTS (
  SELECT 1 FROM [entita_tabulka]
  JOIN guardians g ON g.id = [vazba_na_guardiana]
  WHERE [podminka_entity]
    AND g.user_id = auth.uid()
) THEN TRUE
```

Toto se tyka vsech funkcii pracujicich s:
- `guardians` → `can_read_guardian()` ✅ opraveno
- `students` / `student_guardian_links` → `can_read_student()` ✅ opraveno
- `absence_requests` → overit (RLS politika `guardian_absence_requests_select`
  existuje od migrace 019 — pravdepodobne OK)
- `attendance_records` (docházka v portálu) → overit az bude aktivni

### 43.5 Poznamka k Supabase SQL editoru a `$$`

Supabase SQL editor prida na konec dotazu automaticky komentar:
```sql
-- source: dashboard
-- user: session:xxx
-- date: 2026-05-24...
```
Tento komentar rozbija `$$` dollar-quoting — funkce skonci predcasne a SQL
selze s `unterminated dollar-quoted string`.

**Reseni:** Pouzit jiny oddelovac nez `$$`:
```sql
AS $fn$   -- nebo $body$, $func$ — cokoliv krome prazdneho $$
```

---

## 44. Guardian auto-link: presun do `portal/layout.tsx` (2026-05-24)

### Problem

Auto-link (`guardians.user_id = auth.uid()` pri prvnim prihlaseni) byl implementovan
v `auth/confirm/route.ts` a `auth/callback/route.ts`. Po prechodu na klientskou
`verifyOtp()` (`page.tsx`) server-side auto-link v confirm route vypadl.

### Reseni

Auto-link presunut do `app/portal/layout.tsx` — zde je session spolehlivou dostupna
(request uz ma cookies nastavene browsere):

```typescript
// Nejprve pokus pres user_id
const { data: guardianRaw } = await supabase
  .from('guardians')
  .select('id, first_name, last_name, user_id')
  .eq('user_id', user.id)
  .maybeSingle()

let guardian = guardianRaw as any

// Auto-link: prvni prihlaseni — user_id jeste neni naparovano
if (!guardian && user.email) {
  const { data: byEmail } = await supabase
    .from('guardians')
    .select('id, first_name, last_name')
    .eq('email', user.email)
    .is('user_id', null)
    .maybeSingle()

  if (byEmail) {
    await supabase
      .from('guardians')
      .update({ user_id: user.id })
      .eq('id', byEmail.id)
    guardian = byEmail
  }
}

if (!guardian) redirect('/dashboard')
```

**Vyhody umisteni v layout.tsx:**
- Session je zarucene dostupna (cookies jiz nastaveny browsere)
- Auto-link probehne spolehlivou pri kazdém prvnim prihlaseni
- Netyka se staffu (layout je jen pro `/portal/*`)
- Zadny dalsi async roundtrip — dotaz probehne ve stejnem SSR requestu

### Dusledek pro `auth/callback/route.ts`

Auto-link logika v `auth/callback` zustava jako pojistka pro PKCE flow
(staff magic link). Pro guardian portal je kanonickym mistem `portal/layout.tsx`.

---

## Aktualizace sekce 1 (RLS hierarchy) — stav po 2026-05-24

Hierarchie RLS helper funkci rozsirena o guardian vetev:

```
current_staff_id()              current_guardian_id() / auth.uid()
current_staff_role()                    ↓
    ↓                          guardian_can_access_student()
is_director()                  can_read_guardian()   ← rozsireno 2026-05-24
is_director_or_vp()            can_read_student()    ← rozsireno 2026-05-24
staff_can_access_student()
    ↓
can_read_student()   ← rozsireno 2026-05-24
can_read_guardian()  ← rozsireno 2026-05-24
```

Sanity check pro guardian RLS (spustit po kazde zmene):
```sql
-- Guardian vidi vlastni zaznam:
SET LOCAL role = authenticated;
SET LOCAL "request.jwt.claims" = '{"sub": "<guardian-auth-uid>"}';
SELECT id, email FROM guardians WHERE user_id = '<guardian-auth-uid>';
-- Ocekavany vysledek: 1 radek

-- Guardian vidi vlastni deti:
SELECT s.first_name, s.last_name
FROM students s
WHERE can_read_student(s.id);
-- Ocekavany vysledek: N radku (pocet deti guardiana)
```
