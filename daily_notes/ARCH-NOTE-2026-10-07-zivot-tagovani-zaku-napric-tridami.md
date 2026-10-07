# ARCH-NOTE: Průvodce nemohl na fotkách v galerii označit děti z jiných tříd

**Datum:** 2026-10-07
**Modul:** [[Ze života školy]] — dashboard, editor galerie (`/dashboard/zivot/galerie/[id]`)
**Soubory:** `app/dashboard/zivot/galerie/[id]/page.tsx`
**Commity:** `140ebdd` (fix: tagování fotek žáky ze všech tříd, ne jen z třídy průvodce)

---

## Přehled

Průvodkyně plnící fotogalerii „Ze života školy" nemohla na fotkách označit (otagovat) děti z jiné třídy, než ve které je třídní. Příčina byla v načítání seznamu žáků pod RLS personálu. Opraveno v aplikační vrstvě, bez migrace.

---

## 1. Picker žáků omezený RLS na vlastní třídu

**Soubor:** `app/dashboard/zivot/galerie/[id]/page.tsx` — načtení `activeStudents` a `studentById`

### Symptom
V editoru galerie nabízel `PhotoTagger` průvodci jen děti z jeho třídy. Navíc: když dítě z jiné třídy otagoval někdo jiný (např. ředitel), průvodce ten tag vůbec neviděl — nemohl ho odebrat a indikátor „publikovatelná / nepublikovatelná" počítal bez něj.

### Příčina
Picker i jména otagovaných žáků se četly přímým `select` z `public.students`. RLS na `students` průvodci vrací jen žáky jeho třídy. Omezení bylo známé už při stavbě fáze 3 zdi („guide vidí jen své žáky — možné omezení"), projevilo se až v provozu.

Souhlasy (`get_consent_overview`) problém neměly — RPC je SECURITY DEFINER pro všechny zaměstnance napříč třídami.

### Řešení
- Picker čte přes existující `get_students_in_school_year(gallery.school_year)` — SECURITY DEFINER, od migrace 089 jen pro zaměstnance (`current_staff_id()`), vrací jen `id` + jméno. Stejné RPC už používají jiné staff stránky (nová omluvenka, nová pohledávka, dashboard).
- Rozsah pickeru = aktivní žáci zapsaní v **roce galerie** (dřív všichni bez `withdrawal_date` bez ohledu na rok).
- `studentById` (jména tagů) se plní ze stejného seznamu; přímý RLS dotaz zůstává jen jako dohledání otagovaných mimo picker (např. žák mezitím odešel).

### Poučení
Agenda, kterou plní kdokoli z personálu za celou školu (galerie, akce), nesmí brát seznam žáků přímým selectem pod RLS — ten je řezaný podle třídy. Pro „všichni žáci školy, jen jména" použít `get_students_in_school_year`.

---

## Ověření

- `tsc --noEmit` čisté, ESLint na souboru čistý, `check:as-any` baseline 0.
- Vizuální ověření pod účtem průvodkyně (otagovat dítě z jiné třídy) — na uživateli.

## Související

- [[Souhlasy]] — barva chipu = souhlas `media_website` přes `get_consent_overview`
- [[Žáci]] — RLS čtení žáků po třídách
