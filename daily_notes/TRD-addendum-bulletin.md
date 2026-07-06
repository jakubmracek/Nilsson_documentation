# TRD – Addendum k v1.6 (modul [[Zprávy a bulletin]])

---

## Modul [[Zprávy a bulletin]] ([[Zprávy a bulletin]])

### Umístění v projektu

| Typ | Cesta |
|---|---|
| UI stránky | `app/[[Přehled]]/[[Zprávy a bulletin]]/` (součást [[Přehled]] layoutu) |
| API routes | `app/api/[[Zprávy a bulletin]]/` |
| Logika příjemců | `lib/[[Zprávy a bulletin]]/recipients.ts` |
| Email šablona | `emails/BulletinEmail.tsx` |
| Discord helper | `lib/discord.ts` (sdílený) |
| Typy | `types/[[Zprávy a bulletin]].ts` |

### Databáze – migrace 025 + 025b

**`bulletin_posts`** – příspěvky [[Zprávy a bulletin]]
- `type`: `'message'` nebo `'event'`
- `body`: Markdown
- `valid_from` / `valid_until`: okno viditelnosti (DATE)
- `event_date`: TIMESTAMPTZ, povinné pro `type='event'`
- `email_sent_at`: NULL dokud nebyl odeslán email; po odeslání uzamkne post
- `school_year`: TEXT `'2025/2026'`

**`bulletin_post_recipients`** – materializovaní příjemci
- Snapshot `email_at_send` v okamžiku vytvoření postu
- Záznamy se nevymažou ani po soft delete postu (CASCADE pouze při DELETE z DB)

**`email_events`** – generická tabulka emailových událostí
- Použitelná i pro platební modul (`source_type = 'payment'`)
- `event_type`: `'sent' | 'delivered' | 'bounced' | 'complained'`
- INSERT povoleno pro všechny autentizované (hlídá service role v API route)

### Životní cyklus příspěvku

```
Vytvoření → materializace příjemců → [odeslání emailu] → uzamčení
     ↓
Soft delete: valid_until = yesterday (příspěvek mizí z [[Přehled]])
```

### Uzamčení po odeslání emailu

Hlídáno dvojitě:
1. **DB trigger** `bulletin_posts_lock_after_send` – blokuje UPDATE klíčových polí pokud `email_sent_at IS NOT NULL`, vyhodí `ERRCODE P0001`
2. **PATCH route** – vrátí HTTP 409 pokud `email_sent_at IS NOT NULL` (kontrola před DB)

Povolená úprava i po uzamčení: `valid_until` (soft delete).

### Příjemci – rozlišení

RPC funkce `bulletin_resolve_recipients(p_group_ids, p_excluded_guardian_ids, p_school_year)`:
- SECURITY DEFINER + STABLE
- Vrátí DISTINCT zákonné zástupce (`je_zakonny_zastupce = true`) aktivních [[Žáci]] ve vybraných skupinách
- Filtruje vypršelé `student_guardian_links` a `group_memberships`
- Voláno z `lib/[[Zprávy a bulletin]]/recipients.ts` → `resolveRecipients()`

### Email

- Provider: Resend (sdílený `RESEND_API_KEY`)
- Šablona: `emails/BulletinEmail.tsx` (React Email + `marked` pro Markdown → HTML)
- Odesílá se pouze příjemcům s neprázdným `email` na záznamu `guardians`
- Každý odeslaný email → záznam v `email_events` s `resend_id`

### Discord

- Webhook: `DISCORD_BULLETIN_WEBHOOK_URL` (odlišný od `DISCORD_WEBHOOK_URL` pro [[Omluvenky]])
- Funkce: `sendBulletinNotification()` v `lib/discord.ts`
- Best-effort: chyba webhooku neblokuje vytvoření postu
- Pokud URL není nastavena → graceful skip (pouze log)

### RLS

| Tabulka | Role |
|---|---|
| `bulletin_posts` SELECT | `pruvodkyne`, `reditel`, `asistent` |
| `bulletin_posts` INSERT/UPDATE/DELETE | `pruvodkyne`, `reditel` |
| `bulletin_post_recipients` SELECT/INSERT | `pruvodkyne`, `reditel` |
| `email_events` SELECT | `reditel` |
| `email_events` INSERT | všichni (hlídá API route) |

`has_role()` v projektu má signaturu `has_role(p_role text)` – kontroluje `auth.uid()` interně.

