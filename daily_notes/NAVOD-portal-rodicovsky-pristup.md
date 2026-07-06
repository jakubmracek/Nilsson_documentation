# Zprovoznění přístupu rodičů do [[Rodičovský portál]] — návod

**Kdy použít:** Při prvním hromadném otevření [[Rodičovský portál]] pro zákonné zástupce
(plánováno před zahájením ostrého provozu, září 2026).

**Předpoklad:** Magic link flow je funkční (Auth Hook, Resend, `zsvilekula.cz`).
Ověřeno 2026-05-24.

---

## Krok 1 — Zkontroluj emaily v `guardians`

```sql
SELECT first_name, last_name, email
FROM guardians
WHERE email IS NULL OR email = ''
ORDER BY last_name;
```

Chybějící emaily doplnit ručně před rozesláním — bez emailu magic link
nelze odeslat.

---

## Krok 2 — Zkontroluj vazby na děti

Rodič bez vazby by po přihlášení viděl prázdný [[Rodičovský portál]].

```sql
SELECT g.first_name, g.last_name, g.email,
       COUNT(sgl.student_id) AS pocet_deti
FROM guardians g
LEFT JOIN student_guardian_links sgl ON sgl.guardian_id = g.id
GROUP BY g.id, g.first_name, g.last_name, g.email
ORDER BY pocet_deti, g.last_name;
```

Řádky s `pocet_deti = 0` — doplnit vazby do `student_guardian_links`
před rozesláním.

---

## Krok 3 — Rozeslat magic linky

### Varianta A: Supabase [[Přehled]] (doporučeno pro první spuštění)

```
Authentication → Users → Invite user → zadej email rodiče
```

Supabase pošle magic link přes Auth Hook = Resend.
Opakovat pro každého rodiče. Pro 30–40 rodičů zvládnutelné ručně.

> **Poznámka:** Invite vytvoří nový `auth.users` záznam pokud neexistuje.
> Auto-link v `portal/layout.tsx` ho správně napáruje na existující
> `guardians` záznam podle emailu — žádný ruční zásah není potřeba.

### Varianta B: hromadný skript (pro budoucí použití)

Jednorázový Server Action nebo API endpoint projde všechny guardians
bez `user_id` a vygeneruje magic link přes Supabase Admin API:

```typescript
const { data } = await supabase.auth.admin.generateLink({
  type: 'magiclink',
  email: guardian.email,
  options: {
    redirectTo: 'https://nilsson-two.vercel.app/auth/confirm?next=/portal/[[Omluvenky]]'
  }
})
// odeslat přes Resend s vlastní šablonou emailu
```

Tato varianta dává plnou kontrolu nad textem a časováním emailu.
Implementovat jako `/api/admin/invite-guardians` chráněný `CRON_SECRET`
nebo director session.

---

## Krok 4 — Co se stane při prvním přihlášení rodiče

Automatický flow bez admin zásahu:

```
Rodič dostane email s odkazem
  → klikne → /auth/confirm?token_hash=...
  → verifyOtp() (klientsky)
  → session cookie zapsána
  → portal/layout.tsx: najde guardians WHERE email = user.email AND user_id IS NULL
  → UPDATE guardians SET user_id = auth.uid()  (auto-link)
  → [[Rodičovský portál]] se otevře
```

Při každém dalším přihlášení rodič zadá email na `/portal/login`
a dostane nový magic link — stejný flow bez auto-link kroku.

---

## Krok 5 — Ověření po spuštění

```sql
-- Kolik rodičů se již přihlásilo (má user_id)?
SELECT
  COUNT(*) FILTER (WHERE user_id IS NOT NULL) AS prihlaseni,
  COUNT(*) FILTER (WHERE user_id IS NULL)     AS jeste_neprihlaseni,
  COUNT(*)                                     AS celkem
FROM guardians
WHERE email IS NOT NULL;
```

```sql
-- Kteří rodiče se ještě nepřihlásili?
SELECT first_name, last_name, email
FROM guardians
WHERE user_id IS NULL AND email IS NOT NULL
ORDER BY last_name;
```

Nepřihlášeným rodičům lze zaslat připomínku — opakovat Krok 3.

---

## Před spuštěním také ověřit

- [ ] `/portal/dochazka` — RLS pro `attendance_records` s guardian větví
      (neověřeno po změnách 2026-05-24)
- [ ] `/portal/[[Platby]]` — až bude modul implementován (TRD sekce 4.7.8)
- [ ] Zobrazení správného jména rodiče v topbaru [[Rodičovský portál]]
- [ ] Odhlášení funguje (`/auth/signout`)
- [ ] Magic link expiruje po 1 hodině — zkontrolovat [[Nastavení]] v
      `Supabase → Authentication → Email → Magic Link expiry`

---

## Časový odhad

| Aktivita | Čas |
|----------|-----|
| Kontrola a doplnění emailů + vazeb | 30–60 min |
| Ruční rozesílání přes [[Přehled]] (30–40 rodičů) | 1–2 hod |
| Ověření přihlášení a troubleshooting | 30 min |

**Celkem:** cca půl dne. Doporučeno provést týden před ostrým provozem,
aby byl čas na troubleshooting individuálních případů.

---

## Troubleshooting

| Příznak | Pravděpodobná příčina | Řešení |
|---------|-----------------------|--------|
| Email nedorazil | Auth Hook selhal, Resend chyba | Zkontrolovat Vercel Logs → `/api/auth/send-email` |
| „Odkaz není platný" (`/auth/error`) | Token expiroval nebo byl použit | Poslat nový magic link |
| [[Rodičovský portál]] zobrazí prázdný seznam dětí | Chybí vazba v `student_guardian_links` | Doplnit vazby, viz Krok 2 |
| [[Rodičovský portál]] přesměruje na `/[[Přehled]]` | `guardians.user_id` napárován na staff email | Ověřit že rodič používá správný email (ne staff email) |
| Rodič vidí cizí děti | Chyba v `student_guardian_links` | Zkontrolovat vazby pro daného guardiana |
