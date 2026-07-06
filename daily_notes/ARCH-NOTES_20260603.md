## [[Zprávy a bulletin]] / [[Zprávy a bulletin]] — arch notes (2026-06-03)

### RLS policies — konvence názvů rolí

Reálné hodnoty rolí v DB (staff.role / staff_roles.role):
- `director` (ředitel)
- `guide` (průvodkyně)
- `assistant` (asistent pedagoga)
- `[[Výchovný poradce (VP)]]` ([[Výchovný poradce ([[Výchovný poradce (VP)]])]])
- `vychovatel`

**Pozor:** V migration 025_bulletin.sql byly policies napsány s českými názvy
(`reditel`, `pruvodkyne`) — ty v DB neexistují a způsobují 42501 RLS error.
Vždy používat anglické názvy výše.

Opravené policies: `bulletin_posts`, `bulletin_post_recipients`.

### Soft delete

DELETE handler provádí UPDATE (`valid_from = valid_until = yesterday`).
Nutno nastavit **obě** pole — samotný `valid_until` do minulosti porušuje
CHECK constraint `valid_until >= valid_from`.

### Resend — from adresa

Ověřená adresa pro doménu zsvilekula.cz: `nilsson@zsvilekula.cz`
Display name musí obsahovat pouze ASCII znaky.
`from: 'ZS Vilekula Teplice <nilsson@zsvilekula.cz>'`

### Závislosti

`@react-email/render` musí být přímá závislost projektu (ne jen tranzitivní
přes `@react-email/components`) — jinak Next.js bundler balíček nenajde.