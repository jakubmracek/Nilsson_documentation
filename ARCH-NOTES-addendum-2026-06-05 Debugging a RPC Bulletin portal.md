# ARCH-NOTES addendum 2026-06-05
# Bulletin edit page, send route, recipients API

---

## Sekce 54 — Bulletin modul: edit stránka + odeslání emailu (2026-06-05)

### 54.1 Přidané soubory

```
app/dashboard/bulletin/[id]/edit/
└── page.tsx                          ← NOVÝ: Client Component, edit formulář

app/api/bulletin/posts/[id]/send/
└── route.ts                          ← NOVÝ: POST odeslání emailu přes Resend

app/api/bulletin/posts/[id]/recipients/
└── route.ts                          ← NOVÝ: GET seznam příjemců, PUT nahrazení
```

### 54.2 Edit stránka (`[id]/edit/page.tsx`)

Client Component (`'use client'`). Načítá data ze tří API:
- `GET /api/bulletin/posts/[id]` — post detail
- `GET /api/bulletin/posts/[id]/recipients` — uložení příjemci
- `GET /api/groups` + `GET /api/bulletin/groups/[id]/parents` — skupiny + rodiče

**Důležité: formát API odpovědí**

`/api/bulletin/groups/[id]/parents` vrací wrapper objekt, ne čisté pole:
```typescript
// SPRÁVNĚ:
const raw = Array.isArray(pData) ? pData : (pData.recipients ?? []);
// ŠPATNĚ:
const parents: Guardian[] = pRes.ok ? await pRes.json() : [];
// → TypeError: t.parents.some is not a function
```

**Typ Guardian odpovídá `RecipientPreview` z `lib/bulletin/recipients.ts`:**
```typescript
type Guardian = {
  guardian_id: string;  // ← NE id, ale guardian_id
  first_name:  string;
  last_name:   string;
  email:       string | null;
  hasEmail:    boolean;
};
```

**Logika zamykání:**
- `isLocked = post.email_sent_at != null`
- Po zamknutí: formulář read-only, příjemce nelze měnit (PATCH i PUT recipients vrátí 409)
- Odeslání emailu dostupné vždy (i opakovaně) — s viditelným varováním

### 54.3 API: `POST /api/bulletin/posts/[id]/send`

Odesílá emaily příjemcům z `bulletin_post_recipients.email_at_send`.
- Žádný zámek na opakované odeslání — UI zobrazí varování
- Po odeslání nastaví/aktualizuje `email_sent_at = now()`
- Zapisuje do `email_events` (event_type='sent')
- Vrací `{ sent, failed, missing_email, total }`

### 54.4 API: `GET+PUT /api/bulletin/posts/[id]/recipients`

GET: vrací `{ guardian_id, email_at_send }[]`

PUT: nahradí seznam příjemců (delete + insert)
- Blokováno pokud `email_sent_at IS NOT NULL` → 409
- Při insertu čte aktuální `guardians.email` pro `email_at_send`

### 54.5 Oprava detail stránky (`[id]/page.tsx`)

Chyba v původním kódu — špatný template literal:
```tsx
// CHYBA (původní):
href={`/dashboard/bulletin/\/edit`}
// OPRAVA:
href={`/dashboard/bulletin/${p.id}/edit`}
```

### 54.6 Oprava detail stránky: podmínka zobrazení tlačítka Upravit

Původní kód skrýval tlačítko "Upravit" pokud `isLocked`. Po implementaci
send route je edit stránka užitečná i po odeslání (zobrazení statistik,
opakované odeslání) — tlačítko se zobrazuje vždy, stránka sama řeší zamknutí.

### 54.7 E2E flow: nová zpráva → portál

1. `POST /api/bulletin/posts` → vytvoří post + materializuje příjemce
2. `/dashboard/bulletin/[id]/edit` → úprava obsahu + příjemců (před odesláním)
3. `POST /api/bulletin/posts/[id]/send` → odešle email, nastaví `email_sent_at`
4. `/portal/zpravy` → RPC `get_bulletin_for_guardian` vrátí post (filtr `email_sent_at IS NOT NULL`)

---

*Addendum 2026-06-05 — Jakub Mráček / Claude Sonnet 4.6*
