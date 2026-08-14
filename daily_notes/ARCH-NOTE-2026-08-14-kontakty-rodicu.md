# ARCH-NOTE: Kontakty rodičů — export telefonů zákonných zástupců (CSV + vCard)

**Datum:** 2026-08-14
**Modul:** [[Žáci]] · Správa školy
**Soubory:** `app/dashboard/kontakty-rodicu/page.tsx` + `_components/ClassPicker.tsx` + `csv/route.ts` + `vcf/route.ts`, `lib/guardian-contacts.ts`, `components/nav/nav-items.tsx`, `app/dashboard/sprava-skoly/page.tsx`
**Commity:** `89cf241` (feat)
**Migrace:** žádná (viz RLS níže).

---

## Přehled

Ředitelská dlaždice **Správa školy → Kontakty rodičů** (`/dashboard/kontakty-rodicu`):
ředitel vybere třídy (checkboxy) a stáhne telefony zákonných zástupců k rychlému
nahrání do mobilu / hromadné komunikaci školy.

Dva formáty ze **stejného zdroje dat**:
- **CSV** (`;` + BOM, `\r\n`) — tabulka pro Excel.
- **vCard `.vcf`** (v3.0) — v mobilu se otevře a přidá kontakty **přímo do adresáře**
  (to CSV neumí).

---

## Datový řetězec — `lib/guardian-contacts.ts`

Sdílená funkce `getGuardianContacts(supabase, rok, tridy[])` (používá ji CSV i
vCard route, aby se nerozjely formáty ani logika):

```
groups(name ∈ tridy, school_year)
  → group_memberships(valid_to IS NULL)
  → students(status='active')
  → student_guardian_links(platnost_do IS NULL)
  → guardians(phone_primary, phone_secondary, email, jméno, role)
```

- Řádek/VCARD **jen pro zástupce s aspoň jedním telefonem** (email-only se vynechá).
- Primární kontakt první (`order je_primarni_kontakt desc`).
- Zahrnuje i **kontaktní osoby** (ne jen ZZ), pokud mají telefon — jsou to užitečné
  nouzové kontakty.
- Třída žáka = agregát názvů skupin z výběru (obvykle 1).

---

## Bez migrace — RLS ředitele

Klíčové rozhodnutí: **žádná migrace není potřeba.** Ředitel čte všechny potřebné
tabulky běžným klientem přes RLS:
- `can_read_student()` → director **TRUE** (vše),
- `can_read_guardian()` → director **TRUE** (vše).

(Vzor ověřen na kartě žáka, která stejné tabulky čte embed dotazem.) Guard v obou
routách je proto **explicitně jen `director`** — RLS by jinak pustila i vp/readonly
(ti čtou žáky/zástupce taky). Vzor guardu = `tridni-kniha/priznaky/csv`.

---

## Sloupce / vCard

**CSV:** `Třída ; Žák ; Zákonný zástupce ; Vztah ; Telefon ; Telefon 2 ; E-mail`.

**vCard (jeden VCARD = jeden zástupce per žák):**
- `FN` = `Jméno Příjmení – Příjmení Jméno_žáka (Třída)` → dohledatelné v telefonu
  podle rodiče i podle dítěte.
- `N`, `TEL;TYPE=CELL` (1–2), `EMAIL;TYPE=INTERNET`, `NOTE` = vztah + žák + třída.
- Textové hodnoty escapované dle **RFC 6350** (`\ , ; \n`).

---

## UI

- `ClassPicker` (klient): checkboxy tříd + „Vybrat vše" + počty žáků, přepínač
  školního roku (jako `/zaci`). Dvě tlačítka: **Stáhnout CSV** a **Stáhnout do
  kontaktů (vCard)** — aktivní až po výběru ≥1 třídy.
- Počty žáků/tříd v náhledu; třídy odvozené z `get_students_roster` (agregát
  `trida` rozdělený po jednotlivých názvech).
- Dole GDPR upozornění (osobní údaje ZZ, jen pro provozní komunikaci, nesdílet dál).

---

## Ověření

- `tsc --noEmit` čistý; `check:as-any` = baseline 3 (nepřidán žádný
  `(supabase as any)` — dotazy jsou nad zralými tabulkami, embed funguje).
- ESLint hlásí `no-explicit-any` stejně jako existující nasazené soubory
  (`zaci/page.tsx`, `priznaky/csv`) — projektový baseline, `next.config` lint
  during build nezapíná.
- Živě za ředitelským loginem (neověřeno klikem).

## Poznámky do budoucna

- vCard `FN` schválně nese i jméno žáka + třídu; kdyby vadilo v adresáři, lze
  zjednodušit na jméno zástupce + NOTE.
- Import `.vcf` do kontaktů se chová jinak na iOS vs Androidu — ověřit na reálném
  telefonu.

## Související

- [[nilsson-build-konvence]] — as-any ratchet, RLS helpery
- [[umisteni-director-agend]] — director agendy jako dlaždice ve Správě školy
- [[nav-menu-architektura]] — položka v `nav-items.tsx` → dlaždice přes `resolveNav`
- [[photo-consent-zdroj]] — GDPR souhlasy jsou jinde (consent_records), tady se neřeší
