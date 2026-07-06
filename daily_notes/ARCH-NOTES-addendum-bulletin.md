# ARCH-NOTES – Addendum k v1.5 (modul [[Zprávy a bulletin]], migrace 025)

---

## § Supabase klient – dvě funkce

V projektu existují dvě odlišné funkce pro přístup k DB:

| Funkce | Typ | RLS | Použití |
|---|---|---|---|
| `createSupabaseServerClient()` | async | ✅ respektuje | Route Handlers, Server Components, Server Actions |
| `createSupabaseAdmin()` | sync | ❌ obchází | Cron joby, migrace, seed skripty |

Import vždy z `@/lib/supabase-server`. **Nikdy** `@/lib/supabase/server` (neexistuje).

---

## § Next.js 15+ – async params

Route Handlers s dynamickými segmenty `[id]` musí deklarovat `params` jako `Promise`:

```ts
type RouteParams = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: RouteParams) {
  const { id } = await params
  // ...
}
```

Totéž platí pro Server Components (`app/[[Přehled]]/[[Zprávy a bulletin]]/[id]/page.tsx`).

---

## § lib/discord.ts – sdílený soubor

`lib/discord.ts` je **jediný** Discord helper v projektu. Exportuje:

- `notifyDiscord(embed)` – generický odesílač → `DISCORD_WEBHOOK_URL`
- `embedNovaOmluvenka(opts)` – [[Omluvenky]]
- `embedOmluvenkaApproved(opts)` – [[Omluvenky]]
- `embedOmluvenkaRejected(opts)` – [[Omluvenky]]
- `sendBulletinNotification(post, recipientCount, missingEmailCount, authorName)` – [[Zprávy a bulletin]] → `DISCORD_BULLETIN_WEBHOOK_URL`

Při přidávání notifikací pro nové moduly rozšiřovat **tento soubor**. Nevytvářet nové discord helpery jinde.

Env proměnné:
- `DISCORD_WEBHOOK_URL` – [[Omluvenky]] (existující)
- `DISCORD_BULLETIN_WEBHOOK_URL` – [[Zprávy a bulletin]] (přidat při nasazení)

---

## § PowerShell – zápis souborů a nahrazování

**Zápis souborů** – vždy bez BOM, UTF-8:
```powershell
[IO.File]::WriteAllText($path, $content, (New-Object Text.UTF8Encoding $false))
```
Nikdy `Set-Content` (způsobuje Windows-1250 nebo BOM → Turbopack crash).

**Nahrazování v souborech** – pro soubory obsahující JSX s backtick template literals používat `.Replace()` metodu, **nikoli** PowerShell `-replace` regex:
```powershell
$content = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
$content = $content.Replace('starý řetězec', 'nový řetězec')
[IO.File]::WriteAllText($path, $content, (New-Object Text.UTF8Encoding $false))
```
`-replace` poškozuje backtick expressions (`${...}`) v JSX className a template literals.

**Cesty s hranatými závorkami** – vždy `-LiteralPath`, nikdy `-Path`:
```powershell
Copy-Item -LiteralPath "app\[[Zprávy a bulletin]]\[id]\page.tsx" -Destination "..."
Get-Content -LiteralPath "app\[[Zprávy a bulletin]]\[id]\page.tsx" -Raw
```

