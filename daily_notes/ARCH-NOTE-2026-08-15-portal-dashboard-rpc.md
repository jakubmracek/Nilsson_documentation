# ARCH-NOTE: Rodičovský portál — dashboard RPC (nezaplacené pohledávky + nástěnka)

**Datum:** 2026-08-15
**Modul:** [[Rodičovský portál]] · [[Platby]] · [[Zprávy a bulletin]]
**Soubory:** `app/portal/page.tsx`, `lib/matrika.ts`, `scripts/check-as-any.mjs`, `types/database.ts`, `supabase/migrations/bez migrace/078_rpc_portal_dashboard.sql`
**Commity:** `b02fa7d` (fix), PR [#3](https://github.com/jakubmracek/nilsson/pull/3) → merge `a2ef051`
**Migrace:** `078_rpc_portal_dashboard.sql` — **nasazená** (ruční spuštění v Supabase).

---

## Přehled

Dashboard rodičovského portálu (`/portal`) volal dvě RPC funkce, které **nikdy
nebyly implementované** v DB ani v migracích — byly naplánované dle TRD
(Platební modul §4.2, Bulletin), ale nenasazené:

- `get_guardian_unpaid_receivables` — otevřené pohledávky rodiče
- `get_guardian_bulletin_posts` — poslední příspěvky nástěnky

**Dopad (tichá chyba):** `.rpc()` vracelo error, kód dělal `?? []`, takže widgety
**„Nezaplacené pohledávky" a „Zprávy a nástěnka" tiše ukazovaly prázdno**
(0 Kč / žádné zprávy) — pravděpodobně od začátku existence portálu. Odhaleno až
při burndownu typového dluhu `(supabase as any)` (oba casty tam byly ponechané
jako DRIFT markery).

Migrace 078 obě RPC doplňuje dle kanonického guardian vzoru.

---

## RPC 1 — `get_guardian_unpaid_receivables()`

Otevřené pohledávky napříč všemi **aktivními** dětmi přihlášeného rodiče.

**Návrat** `{ id, description, amount_czk, due_date, status, vs }[]`:

| pole | odvození |
|---|---|
| `description` | `COALESCE(NULLIF(btrim(popis), ''), 'Pohledávka')` |
| `amount_czk` | **zbytek k úhradě** = `amount − SUM(matched_amount)` |
| `status` | `overdue` (due_date < dnes) / `due` (≤ dnes+7) / `upcoming` |
| `vs` | poslední segment `kod_zaka` (`VIL-2016-0007` → `0007`) |

**Datový tok:**

```
current_guardian_id()
  → student_guardian_links(guardian_id, platnost_do IS NULL)   -- aktivní vazba
  → payment_obligations(student_id)
  ⨝ Σ payment_matches.matched_amount  (LEFT JOIN, COALESCE 0)
  WHERE (amount − Σ matched) > 0        -- jen nedoplacené; kredity (amount<0) vypadnou
  ORDER BY due_date ASC
```

**Rozhodnutí:**
- Vazba na dítě přes `platnost_do IS NULL` (aktivní link) — shodně s helperem
  `guardian_can_access_student` (migrace 019). **Nevyžaduje** `je_zakonny_zastupce`:
  vidět/platit dluh může kterýkoli aktivní zástupce (stejně jako stránka `/portal/platby`).
- `amount_czk` je **zbytek**, ne původní částka → korektní součet u částečných plateb.
- Kredity/dobropisy (záporné `amount`) padnou přes filtr `> 0`.

---

## RPC 2 — `get_guardian_bulletin_posts(p_limit int = 5)`

Posledních `p_limit` **odeslaných** příspěvků nástěnky, kde je rodič příjemcem.

**Návrat** `{ id, title, body_preview, published_at }[]`:
- `body_preview` = `left(body, 120)` (prvních 120 znaků)
- `published_at` = `email_sent_at`

**Datový tok:**

```
current_guardian_id()
  → bulletin_post_recipients(guardian_id)  ⨝  bulletin_posts
  WHERE email_sent_at IS NOT NULL          -- jen odeslané, ne drafty
  ORDER BY email_sent_at DESC
  LIMIT GREATEST(COALESCE(p_limit,5), 0)
```

### ⚠️ Stav přečtení se NESLEDUJE

Původní kód počítal s polem `is_read` a metrikou „Nové zprávy" (počet nepřečtených).
Jenže **v celém produktu neexistuje read-receipt** — `bulletin_post_recipients` má
jen `post_id / guardian_id / email_at_send`, ani stránka `/portal/zpravy` přečtení
nesleduje. Přidat ho = celá feature (nový sloupec + write RPC + UI označování).

**Rozhodnutí (uživatel, 2026-08-15): zjednodušit, bez unread.** RPC `is_read`
nevrací, dashboard metrika je přejmenovaná na **„Poslední zprávy"** = počet
posledních příspěvků (`bulletinPosts.length`), `BulletinRow` bez indikátoru tečky.
Read-tracking se může doplnit později jako samostatný modul.

---

## Bezpečnost

Obě funkce dle kanonického guardian RPC vzoru (migrace 028/035):

- `SECURITY DEFINER`, `STABLE`, `SET search_path = public`.
- Guard: `current_guardian_id()` → `RAISE EXCEPTION`, když volající není guardian.
  (Portál stejně gatuje `layout.tsx` přes `get_or_link_guardian_self`.)
- **Hardening dle SECDEF nálezu (077):** `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE
  TO authenticated` — **žádný anon EXECUTE**.

Důvod RPC místo `.from()`: `@supabase/ssr` server kontext nepředá JWT správně pro
guardian RLS politiky přes PostgREST → count=0, error=null. RPC (definer) to obchází.

---

## Typový dluh — burndown `(supabase as any)` DOKONČEN (→ 0)

Vedlejší, ale podstatné: tímto padl **poslední** `(supabase as any)` v projektu.

1. Odstraněny oba casty v `app/portal/page.tsx` (obě RPC nově otypované).
2. Po nasazení 078 dal `npm run db:types` do `types/database.ts` i
   `matrika_set_rocnik` (migrace 075/076, dosud v types chyběl) → odstraněn i cast
   v `lib/matrika.ts`.
3. `scripts/check-as-any.mjs`: **BASELINE 3 → 0**. Ratchet teď blokuje jakýkoli nový cast.

> Pozn.: db:types čte z **živé** DB, takže funkce jsem v PR nejdřív předtypoval
> ručně (aby branch buildil), a po nasazení migrace ověřil regenem — diff byl
> **prázdný** (ruční typy sedly 1:1 s generátorem).

---

## Ověření

- Sanity check na živé DB: obě funkce `prosecdef=true`, `provolatile=s`,
  `proconfig=["search_path=public"]`.
- `npm run db:types` → moje ruční typy = generátor (žádný drift).
- `node scripts/check-as-any.mjs` → **0 řádků (baseline 0)**.
- `npx tsc --noEmit` → čistý (exit 0).
- Vercel preview check na PR → SUCCESS.
- Reálná data ve widgetech za guardian loginem — neověřeno klikem (chybí testovací
  účet rodiče).

---

## Poznámky do budoucna

- **Read-receipty nástěnky** jsou vědomě odloženy. Až budou, `get_guardian_bulletin_posts`
  se rozšíří o `is_read` a dashboard vrátí metriku nepřečtených (viz sekce výše).
- `status='due'` má okno **7 dní** — kdyby bylo potřeba jinak (např. „do konce
  měsíce"), měnit `CURRENT_DATE + 7` v migraci 078.
- Konflikt při mergi: master mezitím taky odstranil matrika cast (`7bc90f9`,
  baseline 3→2) — vyřešeno ve prospěch finálního stavu (baseline 0).

## Související

- [[nilsson-build-konvence]] — as-any ratchet, RLS helpery, guardian RPC vzor
- [[druzina-rpc-drift-077]] — sesterský drift nález (`druzina_vytvorit_pohledavku`)
- [[secdef-execute-hardening]] — REVOKE PUBLIC + GRANT authenticated na SECDEF RPC
- [[Platby]] · [[Zprávy a bulletin]] — plné stránky, které dashboard sumarizuje
- `scripts/hygiena-runbook.md` — reconciliation driftu migrací
