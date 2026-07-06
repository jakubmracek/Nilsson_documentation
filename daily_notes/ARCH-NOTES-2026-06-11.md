# ARCH-NOTES — session 2026-06-11

## §53 — [[Zprávy a bulletin]] / email_events: RLS v SSR kontextu

`createSupabaseServerClient()` v Server Components běží jako `authenticated` user, ale `has_role()` v RLS policy vrací `false` — `auth.uid()` není dostupné v tomto kontextu. Přímý dotaz `.from('email_events')` proto vrátil prázdné pole místo chyby, takže statistiky ukazovaly 0 i když data v DB byla správně.

**Canonical fix:** SECURITY DEFINER RPC (stejný pattern jako §50–52).

```sql
CREATE OR REPLACE FUNCTION get_bulletin_email_stats(p_post_id UUID)
RETURNS TABLE (event_type TEXT, cnt BIGINT)
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $fn$
  SELECT event_type, COUNT(*)::BIGINT AS cnt
  FROM email_events
  WHERE source_type = '[[Zprávy a bulletin]]'
    AND source_id = p_post_id
  GROUP BY event_type;
$fn$;

GRANT EXECUTE ON FUNCTION get_bulletin_email_stats(UUID) TO authenticated;
```

V `page.tsx`:
```typescript
const { data: emailStats } = await (supabase as any)
  .rpc('get_bulletin_email_stats', { p_post_id: p.id });

const stats = ((emailStats as { event_type: string; cnt: number }[]) ?? [])
  .reduce<Record<string, number>>((acc, ev) => {
    acc[ev.event_type] = (acc[ev.event_type] ?? 0) + Number(ev.cnt);
    return acc;
  }, {});
```

Migration: `032_bulletin_email_stats.sql`

---

## §54 — Resend webhook tracking

Handler: `app/api/webhooks/resend/route.ts`

- Ověření podpisu přes knihovnu `svix` (`Webhook.verify()`) — hlavičky `svix-id`, `svix-timestamp`, `svix-signature`
- Lookup podle `resend_id` + `event_type = 'sent'` v `email_events` → insert nového řádku s event typem `delivered` / `bounced` / `complained`
- Používá `createSupabaseAdmin()` (service role, bez JWT) — webhook přichází bez uživatelského JWT
- Env proměnná: `RESEND_WEBHOOK_SECRET` (hodnota `whsec_...` z Resend dashboardu)
- Registrováno na: `https://nilsson-two.vercel.app/api/webhooks/resend`
- Odběr eventů: `email.delivered`, `email.bounced`, `email.complained`
- Neznámé `resend_id` (např. platební emaily) → vrací `200 { ok: true, skipped: true }`, nezapisuje

Mapování Resend → `event_type`:
| Resend event | event_type v DB |
|---|---|
| `email.delivered` | `delivered` |
| `email.delivery_delayed` | `delayed` |
| `email.bounced` | `bounced` |
| `email.complained` | `complained` |

---

## §55 — Email deduplikace (sdílený email rodičů)

Oba rodiče mohou sdílet stejnou emailovou adresu. Bez deduplikace by [[Zprávy a bulletin]] dorazila dvakrát.

**Řešení:** `Set<string>` deduplikace podle `email.toLowerCase()` před odesílací smyčkou. Oba guardiani zůstávají v `bulletin_post_recipients` pro [[Přehled]] příjemců — deduplikace se týká pouze odesílání a zápisů do `email_events`.

```typescript
const seenEmails = new Set<string>();
const uniqueEmailRecipients = emailableRecipients.filter(r => {
  const email = r.email!.toLowerCase();
  if (seenEmails.has(email)) return false;
  seenEmails.add(email);
  return true;
});
```

Aplikováno v obou souborech:
- `app/api/[[Zprávy a bulletin]]/posts/route.ts`
- `app/api/[[Zprávy a bulletin]]/posts/[id]/send/route.ts`

---

## §56 — NEXT_PUBLIC_APP_URL

Správná hodnota: `https://nilsson-two.vercel.app`

Používá se na těchto místech:
- `app/actions/payments.ts` — odkaz v platebním notifikačním emailu (`/portal/[[Platby]]`)
- Redirect po odhlášení z [[Rodičovský portál]]

Nastaveno v Vercel → Settings → Environment Variables. Lokálně v `.env.local` (není commitováno).
