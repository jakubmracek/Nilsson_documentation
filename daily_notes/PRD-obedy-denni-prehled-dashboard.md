# PRD — Modul Obědy: denní přehled strávníků v dashboardu

**Produkt:** IS Nilsson (ZŠ Vilekula)
**Verze dokumentu:** v1.0 (rozhodnutí O1–O6 uzavřena → implementováno)
**Stav:** ✅ implementováno (kód hotový, build zelený) — čeká na ruční spuštění migrace 083 + `npm run db:types` + ověření v prohlížeči
**Návaznost:** modul [[Obědy]] objednávkové jádro (migrace 074 — `lunch_orders`, `lunch_effective_orders`, `lunch_month`), ranní SMS report (`/api/cron/lunch-report`), `school_holidays` (026), `absence_requests` (omluvenky)

---

## 1. Cíl a kontext

Modul Obědy dnes žije **jen na rodičovském portálu** (rodič objednává/ruší) a jeho jediný výstup do provozu je **ranní SMS jídelně s počtem obědů**. Zaměstnanci školy nemají v dashboardu žádný náhled — nevidí, kdo konkrétně na oběd jde.

Tento doplněk přidává **personálský denní přehled**: pro vybraný den seznam žáků, kteří jdou na oběd (jméno + třída), se součty. Slouží pedagogům a vedení jako provozní podklad (kdo zůstává na oběd / dozor u výdeje / kontrola proti počtu poslanému jídelně).

### Cíle
- Zaměstnanec v dashboardu vidí pro daný den, **kdo jde na oběd**, přehledně po třídách.
- Počet odpovídá číslu, které dostává jídelna SMS (stejná „effective" množina).
- **Všechny zaměstnanecké role** vidí přehled; **vybrané role** (ředitel + zástupce) mohou navíc oběd za žáka objednat/zrušit — ale jen v otevřeném okně (uzávěrka 22:00 D-1 platí i pro ně).

### Nepatří do rozsahu (v1)
- Výběr konkrétního jídla (volba 1/2/3) — neukládá se (viz PRD objednávek).
- Evidence skutečného výdeje / odpich na čipy.
- Obědy zaměstnanců.
- Ceny / import do [[Platby]] (samostatný track).
- Alergeny / dietní režim žáků (neevidují se v modulu).
- Zápis **po uzávěrce / na dnešek** personálem (vědomě zamítnuto — počet poslaný jídelně tak zůstává vždy finální a odpadá dorovnávání SMS).

---

## 2. Uživatelské role a přístup

| Role | Čte přehled | Zapisuje (objedná/zruší) |
|---|---|---|
| **Ředitel (director)** | ✅ | ✅ |
| **Zástupce (vp)** | ✅ | ✅ |
| **Průvodce / učitel (guide)** | ✅ | ❌ |
| **Asistent (assistant)** | ✅ | ❌ |
| **Vychovatel družiny (vychovatel)** | ✅ | ❌ |
| **Zákonný zástupce** | ❌ (má vlastní pohled na portálu) | přes portál |
| **readonly (demo inspektor)** | ✅ read-only náhled | ❌ (v demo i tak REVOKE) |

> **Zápis = ředitel + zástupce.** „Zvolení" z rozhodnutí O1 = default `vp`; okruh lze později rozšířit změnou guardu v RPC (ne migrací UI). Čte **veškerý personál**.

**Technická poznámka (RLS):** dnes `lunch_orders` čte přes RLS jen `guardian_can_access_student` nebo `is_director()`. Personál (guide/assistant/vp/vychovatel) na data **nevidí**. Přehled proto poběží přes **nová SECURITY DEFINER RPC**, která sama ověří roli — konzistentní s house patternem (viz migrace 074/078). Přímá RLS policy pro personál se nepřidává.

- **`lunch_day_roster(p_date)`** — čtení, guard: `is_director() OR has_role('vp'/'guide'/'assistant'/'vychovatel'/'readonly')`.
- **`lunch_staff_set_order(p_student_id, p_menu_date, p_ordered)`** — zápis, guard: `is_director() OR has_role('vp')`; vynucuje `lunch_ordering_open(p_menu_date)` (stejná uzávěrka 22:00 jako rodič); zapíše `created_by = auth.uid()` pro audit. Nesdílí se s rodičovským `lunch_set_order` (jiný guard).

---

## 3. Datový model

**Žádná nová tabulka.** Přehled je jen čtení nad `lunch_orders` + `students` (třída/jméno) + `absence_requests` (autorušení) + `school_holidays`.

Vstupní množina = stejná logika jako `lunch_effective_orders(date)`:
> objednáno (`status='objednano'`) ∧ školní den ∧ NENÍ celodenní omluvenka podaná do uzávěrky 22:00 D-1.

### `lunch_day_roster(p_date date)` — vrací **jen strávníky** (effective) pro den:

| Sloupec | Popis |
|---|---|
| `student_id` | UUID žáka |
| `full_name` | jméno žáka |
| `class_name` | třída (pro grupování) |

> **Jen strávníci** (rozhodnutí O4) — kdo NEjde na oběd se nezobrazuje. Množina = shodná s `lunch_effective_orders(p_date)`, jen obohacená o jméno + třídu. Součet řádků = číslo v ranní SMS jídelně.
>
> Pro zápisové okno (ředitel/zástupce) vrací RPC navíc `ordering_open` (bool, z `lunch_ordering_open`) — jen aby UI vědělo, zda vůbec zobrazit tlačítka. Editace jednotlivce ale pracuje nad celým rosterem třídy (viz §4), pro který se použije existující náhled — detail v TRD.

---

## 4. UI / obrazovka

**Umístění:** samostatná dlaždice **`/dashboard/obedy`** (viditelná všem zaměstnaneckým rolím); ředitelské nastavení SMS zůstává odděleně v `/dashboard/sprava-skoly/obedy`.

**Rozvržení (výchozí = náhledový režim, všichni):**
- Přepínač dne (datum), default **dnes**, listovatelný dozadu i dopředu.
- Souhrn nahoře: **celkový počet obědů** + počet po třídách; pro dnešek badge „shoduje se s SMS jídelně".
- Seznam **grupovaný po třídách**, v každé třídě jen jména žáků, kteří jdou na oběd.
- Prázdný stav pro neškolní den („dnes se nevaří").

**Editace (jen ředitel + zástupce):**
- Zobrazí se jen když je pro zvolený den `ordering_open = true` (před uzávěrkou 22:00 D-1 a školní den). Po uzávěrce / u minulých dnů je i pro ně přehled read-only (zamčeno stejně jako pro rodiče).
- **Zrušit** strávníka = akce přímo u jména v seznamu.
- **Přidat** žáka, který dnes nejde: přepínač/mód „upravit třídu" rozbalí **celý roster třídy** (strávník ✓ / nestrávník) → zaškrtnutím se objedná. Tím se řeší tenze mezi „zobrazovat jen strávníky" (náhled) a „umět přidat" (editace) — plný roster se ukáže jen v edit módu.
- Každý zápis jde přes `lunch_staff_set_order` (uzávěrka + `created_by` audit); po úspěchu revalidace stránky.

**Mimo v1:** tisk / export seznamu (O6 — až podle potřeby dozoru).

---

## 5. Rozhodnutí (uzavřeno)

- **O1 — Editace:** ✅ personál **může** objednat/zrušit za žáka, ale **jen ředitel + zástupce** a **jen v otevřeném okně** (uzávěrka 22:00 D-1 platí i pro ně → počet pro jídelnu zůstává finální).
- **O2 — Čtení:** **všechny zaměstnanecké role** (director, vp, guide, assistant, vychovatel) + readonly náhled.
- **O3 — Rozsah dnů:** listovatelné datum, default dnes.
- **O4 — Obsah:** **jen strávníci** (kdo jde na oběd); plný roster se ukáže jen v edit módu kvůli přidávání.
- **O5 — Umístění:** vlastní dlaždice `/dashboard/obedy`.
- **O6 — Tisk/export:** ⏸ ne v1, dle potřeby později.

---

## 6. Odhad rozsahu

- **1 migrace (další v řadě, „bez migrace/NNN")** — dvě RPC: `lunch_day_roster` (čtení, guard = veškerý personál + readonly) a `lunch_staff_set_order` (zápis, guard = director + vp, vynucuje uzávěrku, `created_by` audit) + GRANTy. **Bez nové tabulky.**
- **1 stránka** `/dashboard/obedy` (server component, async searchParams pro datum) + komponenta seznamu po třídách + edit mód (jen director/vp).
- **1 server action** — čtení rosteru + zápis přes `lunch_staff_set_order`.
- **Nav** — nová dlaždice `/dashboard/obedy` v `nav-items.tsx` pro všechny zaměstnanecké role (viz house pattern; readonly → `DEMO_READONLY_HREFS`).
- **Bez dotčení** stávajícího cronu / SMS / rodičovského portálu.
- **db:types** po migraci (nové RPC do `types/database.ts`).

## 7. Rizika / na co dát pozor

- **RLS bypass v RPC:** obě RPC jsou SECURITY DEFINER → guard rolí musí být uvnitř těla (jinak by data viděl kdokoli přihlášený). Konzistentní s nálezem [[SECDEF execute hardening]] — neexponovat anon, nespoléhat na fail-open `is_director()`.
- **Uzávěrka jako jediný zdroj pravdy** je v `lunch_ordering_open` (server); UI ji jen zrcadlí. Nikdy nedovolit zápis z klienta mimo RPC.
- **Zdroj třídy/jména žáka** — ověřit sloupce v `students` (třída je řízená DB / school_year_config), viz [[Build konvence]] a [[Zdroj školního roku]].
- **Demo režim** — readonly musí mít i tady jen čtení (REVOKE zápisu), zkontrolovat `readonly-coverage.sql`.
