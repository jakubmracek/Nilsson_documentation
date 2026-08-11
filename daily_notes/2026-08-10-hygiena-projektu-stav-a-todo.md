---
title: Hygiena projektu — stav a to-do
date: 2026-08-10
tags: [hygiena, udrzba, tech-debt, migrace]
---

# Hygiena projektu Nilsson — stav & to-do

> Institucionalizace čistoty systému: sirotci, drift databáze proti typům a
> splácení typového dluhu `(supabase as any)`.
> Aktualizováno **10. 8. 2026** · větev `master` · poslední commit `9250dad` · 16 commitů.
> Vizuální přehled (artefakt): https://claude.ai/code/artifact/ed67ac78-c094-4ab2-a402-850c69422e3c

## Přehled v číslech

| Metrika | Hodnota |
|---|---|
| Typový dluh `(supabase as any)` | **233 → 53** (−180, ~77 % splaceno) |
| Moduly vyčištěné | 9 — rozvrh · družina · platby · zápis · třídnice · essl · tripartita · výkaz PPČ · souhlasy |
| Migrace ověřené v DB | 061–070 (drift splacen) |
| Reálná vada opravená | 1 — detail transakce |
| Automatické guardy | 2 — CI ratchet · čtvrtletní audit |

---

## Hotovo

- **Institucionalizace hygieny** — 9 read-only SQL diagnostik (duchové, mrtvý RLS
  zámek, osiřelá data, drift) + runbook s čtvrtletní kadencí a pravidlem karantény
  „nikdy DROP napřímo". → `scripts/db-audit.sql`, `scripts/hygiena-runbook.md` (`12f0033`)
- **Bezpečnost — ISDS klíč** — soukromý klíč a CSR odtrackovány z gitu,
  `.gitignore` chrání `*.key/*.csr/*.lnk`. (`7e82c78`)
- **Úklid mrtvého kódu** — smazané root prototypy bez referencí a mrtvý duplikát
  `payments.ts`; `proxy.ts` správně ponechán (aktivní Next proxy); přejmenovaná
  kopie migrace `025_bulletin`. (`482ae91`, `34ec77f`)
- **Čtvrtletní Discord připomínka** — endpoint + GitHub Actions cron do `#nilsson`.
  Nasazeno a ověřeno (zpráva reálně dorazila; bylo potřeba re-deploy kvůli env).
- **CI guard + db:types** — první push/PR CI (typecheck + ratchet na typový dluh);
  bezpečný wrapper `db:types` regeneruje typy z živé DB a nemůže přepsat soubor
  při selhání. → `.github/workflows/ci.yml`, `scripts/gen-types.mjs` (`bbb72dd`, `84ceb4a`)
- **Splacení driftu typů** — regenerace `database.ts` z živé DB (+620 řádků),
  potvrzeno, že migrace 061–070 doběhly; osiřelé `pruvodci_*` tabulky v DB
  DROPnuté a kód je nereferencuje. (`03d6ef8`)

## Burndown typového dluhu (po modulech)

| Modul | Před | Po | Commit | Stav |
|---|---:|---:|---|---|
| rozvrh — `app/actions/rozvrh.ts` | 17 | 0 | `82d41f9` | ✅ hotovo |
| družina — 9 souborů | 49 | 1 | `9965657` | ✅ hotovo (1 drift cast) |
| platby — 10 souborů | 35 | 0 | `ee3756d` | ✅ hotovo |
| zápis (enrollment) — 3 soubory | 9 | 0 | `7f2c5ca` | ✅ hotovo |
| třídnice — 4 soubory | 19 | 0 | `4d164d5` | ✅ hotovo |
| essl (spisovka) — 3 soubory | 8 | 0 | `49c6a02` | ✅ hotovo |
| tripartita — 5 souborů | 15 | 0 | `b2c04cf` | ✅ hotovo |
| výkaz PPČ (rozvrh cluster) — 6 souborů | 22 | 0 | `fbd5735` | ✅ hotovo |
| souhlasy (GDPR) — 2 soubory | 7 | 0 | `9250dad` | ✅ hotovo |
| zbytek systému | — | 53 | — | ⬜ to-do |

**Metoda:** cast → `supabase`, `npm run typecheck`, opravit co `as any` schovával,
snížit `BASELINE` v ratchetu, commit. Ratchet drží číslo, aby jen klesalo — nové
casty spadnou v CI.

---

## To-do (dle priority)

### Priorita 1
- [ ] **Pokračovat v as-any burndownu** — zbývá 53 castů. Rychlé ověřitelné dávky.
  Zbývající clustery: `vp` (6) · `staff` (6) · `school-calendar` (6) ·
  `monitoring/výkaz KÚ` (~8) + roztroušené. Hnízda dle
  `git grep -c "supabase as any" -- app lib components | sort -t: -k2 -rn`.

### Priorita 2
- [ ] **Baseline reconciliation migrací** — narovnat migrační stav: jeden baseline
  z živé DB (`supabase db pull`), archiv `bez migrace/`, dál přes CLI. Půldenní
  práce se zálohou, na branchi. `db:types` a drift-check už fungují jako podpora.
- [ ] **Ověřit drift `druzina_vytvorit_pohledavku`** *(běží na pozadí jako task)* —
  signatura v živé DB (3 param) ≠ migrace 058 (2 param); funkce změněna ručně mimo
  migrace. Ověřit, zda ruční dohlášení do družiny reálně zakládá pohledávku.

### Priorita 3
- [ ] **ISDS klíč v historii — squash při přechodu do public** — mitigace místo
  rotace certifikátu: při zveřejnění IS repa přemigrovat obsah jako jeden squashnutý
  commit, aby se historie (a klíč) nepřenesly. Do té doby držet repo privátní.

---

## Klíčová rozhodnutí & nálezy

- 🐞 **Vada · opraveno — detail transakce zobrazoval žáka prázdný.** Kód přiřazoval
  data v `snake_case` do typu v `camelCase`, který JSX čte → jméno a kód žáka se
  renderovaly prázdné. `as any` to úplně skryl. Odhaleno a opraveno při burndownu
  modulu platby (`ee3756d`).
- ⚠️ **Drift · řeší se — RPC `druzina_vytvorit_pohledavku`: DB ≠ migrace.** Živá DB
  vyžaduje parametr navíc oproti migraci 058 — funkce změněna ručně mimo migrace.
  Cast ponechán s komentářem, chování se nemění naslepo; k dořešení při reconciliation.
- ✅ **Rozhodnutí — ISDS certifikát se nerotuje.** Rotace stojí peníze → vynechána.
  Mitigace klíče v git historii je squash při přechodu repa do veřejného.

---

## Jak drží čistota

- **Ratchet** `scripts/check-as-any.mjs` (baseline 53) v CI zablokuje nové casty.
- **`npm run db:types`** po každé migraci brání driftu typů.
- **Čtvrtletní audit** přes `scripts/db-audit.sql` hlídá sirotky a mrtvý RLS.

Souvisí: `scripts/hygiena-runbook.md` (operační postup sprintu).
