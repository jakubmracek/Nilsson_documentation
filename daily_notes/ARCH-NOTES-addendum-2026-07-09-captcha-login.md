# ARCH-NOTES Addendum — 2026-07-09

## §92 — Turnstile CAPTCHA chybělo na `/portal/login` a `/login`, jen na `/zapis/prihlaseni`

### Symptom

Rodič se nemohl přihlásit na `/portal/login`: `signInWithOtp()` vracel error, frontend
zobrazil obecnou hlášku „Nepodařilo se odeslat kód. Zkontrolujte email a zkuste to
znovu." Stejný problém by nastal i na zaměstnaneckém `/login`.

### Příčina

Cloudflare Turnstile CAPTCHA byla zapnutá jako **projektové** nastavení Supabase Auth
(„Enable Captcha protection"), ne jen pro jeden formulář. To znamená, že **každé**
volání `signInWithOtp()` v celém projektu vyžaduje platný `captchaToken` — bez ohledu
na to, jestli daná stránka widget vůbec vykresluje.

Widget byl implementován jen na `/zapis/prihlaseni` (jediné místo, kde `shouldCreateUser:
true` zakládá nové účty a hrozí bot abuse). `/portal/login` a `/login` používají
`shouldCreateUser: false` a widget neměly — proto `signInWithOtp` tiše selhával na
chybějícím tokenu.

### Fix

Stejný Turnstile pattern zkopírován na obě zbývající přihlašovací stránky:

- `app/portal/login/page.tsx` (commit `a626521`)
- `app/login/page.tsx` (commit `fab2068`)

Pattern (identický na všech třech stránkách, jen jiný callback name kvůli globálnímu
`window` scope — `onTurnstileVerify` / `onPortalTurnstileVerify` / `onStaffTurnstileVerify`):

1. `<Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" />` v obalové komponentě.
2. `<div class="cf-turnstile" data-sitekey={NEXT_PUBLIC_TURNSTILE_SITE_KEY} data-callback="on...Verify" />` ve formuláři kroku 1.
3. `captchaToken` state naplněný přes `window.on...Verify`, posílá se jako `options.captchaToken` do `signInWithOtp()`.
4. Submit tlačítko disabled dokud `!captchaToken`.
5. `window.turnstile?.reset()` hned po odeslání — token je jednorázový.

### Poučení pro příště

Pokud je CAPTCHA protection zapnutá projektově v Supabase Auth (ne per-flow), **musí
mít widget úplně každá stránka, která volá `signInWithOtp` nebo `signUp`** — nejen ta,
kde dává smysl z hlediska bot-abuse. Při zavádění nového login/OTP flow zkontrolovat
Supabase Dashboard → Authentication → Attack Protection, jestli je captcha vyžadovaná
globálně.

`NEXT_PUBLIC_TURNSTILE_SITE_KEY` je sdílená env proměnná pro všechny tři stránky —
není potřeba per-flow site key.
