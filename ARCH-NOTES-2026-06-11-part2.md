# ARCH-NOTES — session 2026-06-11 (část 2)

## §57 — Auth: přechod z magic linku na OTP kód

**Příčina problému:** Supabase používá PKCE flow. Custom email hook dostával `token_hash` s prefixem `pkce_`. `verifyOtp({ token_hash })` na PKCE tokeny nefunguje — `code_verifier` nebyl dostupný v prohlížeči příjemce. Výsledek: `ERROR 3248045331` / "invalid flow state, no valid flow state found".

**Řešení:** Přechod na OTP kód (8 číslic) místo magic linku. OTP flow je nezávislý na PKCE a funguje napříč prohlížeči/zařízeními.

**Nový flow (staff i rodiče):**
1. Uživatel zadá email → `supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: false } })`
2. Hook zachytí email, pošle 8-místný kód z `email_data.token` přes Resend
3. Uživatel zadá kód → `supabase.auth.verifyOtp({ email, token, type: 'email' })`
4. Po úspěchu → `window.location.href = '/dashboard'` nebo `'/portal/omluvenky'`

**Důležité:** Po `verifyOtp` použít `window.location.href` (tvrdý redirect), **ne** `router.replace()`. Next.js router nezpropaguje novou session do Server Components — layout se nenačte, zobrazí se jen `children` bez navigace.

**Upravené soubory:**
- `app/api/auth/send-email/route.ts` — posílá `email_data.token` (OTP kód) místo `token_hash` (magic link)
- `app/login/page.tsx` — dvoustupňový formulář (email → kód), staff verifikace po `verifyOtp`
- `app/portal/login/page.tsx` — dvoustupňový formulář (email → kód), redirect na `/portal/omluvenky`

**Nepoužívané soubory (lze ponechat, ale nejsou v aktivním flow):**
- `app/auth/confirm/page.tsx` — byl opraven pro PKCE (`exchangeCodeForSession`), ale OTP flow ho obchází
- `app/auth/link/page.tsx` — mezistránka proti prefetch, také obejita OTP flow

---

## §58 — Supabase Email OTP nastavení

- **Email OTP length:** 8 číslic (nastaveno v Supabase → Authentication → Sign In / Providers → Email)
- **Email OTP expiration:** 1 hodina (výchozí)
- **Auth Hook:** `https://nilsson-two.vercel.app/api/auth/send-email` (Send Email hook, BETA)
- Hook musí být **enabled** — Supabase bez vlastního SMTP jinak emaily vůbec neposílá

---

## §59 — NEXT_PUBLIC_APP_URL a URL konzistence

Správná hodnota: `https://nilsson-two.vercel.app` (opraveno v Vercel env + `.env.local`).

Používá se na těchto místech:
- `app/actions/payments.ts` — odkaz v platebním notifikačním emailu (`/portal/platby`)
- Redirect po odhlášení z portálu
- `app/api/auth/send-email/route.ts` — `NEXT_PUBLIC_SITE_URL` (stejná hodnota, jiná env proměnná)

Pozor: jsou dvě různé env proměnné se stejnou hodnotou:
- `NEXT_PUBLIC_APP_URL` — používá payments
- `NEXT_PUBLIC_SITE_URL` — používá auth send-email hook

---

## §60 — Encoding UTF-8 při kopírování souborů přes PowerShell

Při kopírování `.tsx` souborů s českými znaky **vždy** použít:

```powershell
[IO.File]::WriteAllText(
  (Resolve-Path "cesta\k\souboru.tsx"),
  (Get-Content -LiteralPath "zdrojovy_soubor.tsx" -Raw -Encoding UTF8),
  (New-Object Text.UTF8Encoding $false)
)
```

`-Encoding UTF8` při čtení + `New-Object Text.UTF8Encoding $false` (BOM-free) při zápisu. Bez toho dochází k poškození českých znaků (`PĹ™ihlĂˇĹˇenĂ­` místo `Přihlášení`).
