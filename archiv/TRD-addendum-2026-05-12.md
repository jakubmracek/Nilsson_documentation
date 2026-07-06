# TRD addendum — session 2026-05-12
# Integrovat do TRD-v1.9

---

## Modul: Karta žáka (zaci/[id])

### Stav: ✓ Nasazeno v produkci

### UI komponenty
| Soubor | Popis |
|--------|-------|
| `app/dashboard/zaci/page.tsx` | Seznam žáků — RPC, abecední řazení, avatar iniciály |
| `app/dashboard/zaci/[id]/page.tsx` | Karta žáka — 6 sekcí |

### Sekce karty žáka
1. **Základní údaje** — birth_date, skupina/školní rok, nástup, ukončení, vzdělávání, SVP badge
2. **Zákonní zástupci** — role, ZZ/primární badge, email+tel s href
3. **BOZP** — datum posledního proškolení nebo výzva k přidání
4. **Docházka** — grid pololetí, omluvené/neomluvené hodiny
5. **VP alerty** — pouze role director/vp, module='vp', resolved_at IS NULL
6. **Třídní kniha** — odkaz s `?group_id=<uuid>`

### Přístupová práva
- Karta žáka: všichni přihlášení staff (RLS zajišťuje can_read_student)
- VP sekce: pouze director, vp

---

## Opravy existujících modulů

### tridni-kniha/page.tsx
- Přidán `searchParams.group_id` — filtrování dle skupiny žáka
- Přidán banner "Filtrováno dle skupiny" s odkazem "zrušit filtr"

### tridni-kniha/[id]/page.tsx
- Opraveno: `await params` (Next.js 15+)
- Opraveno: UTF-8 encoding

### bozp/[id]/page.tsx
- Opraveno: `await params` (Next.js 15+)

### tridni-kniha/[id]/svp/page.tsx
- Odstraněn `import type { Database }` (stub nestačí pro createBrowserClient)
- Lokální typy přepsány na `any`

---

## Komunikační modul — Fáze 2 (plánováno)

### Rozsah (navrhovaný)
- Omluvenky od rodičů (zadání přes portál nebo manuálně průvodcem)
- Průpis omluvenky do `attendance_records` (status → 'omluven')
- Notifikace průvodci při nové omluvenece

### Datový model (návrh, neschváleno)
```sql
-- Nová tabulka
CREATE TABLE parent_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID REFERENCES students(id),
  guardian_id UUID REFERENCES guardians(id),
  message_type TEXT CHECK (message_type IN ('omluvenka', 'zprava', 'dotaz')),
  content TEXT NOT NULL,
  date_from DATE,       -- pro omluvenky: od kdy
  date_to DATE,         -- pro omluvenky: do kdy
  status TEXT CHECK (status IN ('nova', 'zpracovana', 'zamitnuta')) DEFAULT 'nova',
  processed_by UUID REFERENCES staff(id),
  processed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### Integrace s docházkou
- Po schválení omluvenky: upsert do `attendance_records` pro každý pracovní den v rozsahu
- Status: 'omluven', hodiny dle skupinového nastavení nebo manuálně
- Vazba: `attendance_records.note` = odkaz na `parent_messages.id`
