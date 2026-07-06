# ARCH-NOTES — Addendum v2.3
# Připojit na konec ARCH-NOTES-v2.2.md
# Datum: 2026-05-15

---

## 31. MŠMT XML generátor (2026-05-15)

### 31.1 Přehled

Implementován generátor matričních výkazů M3 formátu ZS.025.
Generuje soubory `_01.xml` (základní) a `_01a.xml` (SVP).

### 31.2 Soubory

```
lib/msmt-xml.ts
    ← čistá generační logika (bez Supabase)
    ← generateZakladni(students, cfg) → UTF-8 string
    ← generateSouborA(students, cfg)  → UTF-8 string

app/api/msmt/xml/route.ts
    ← GET /api/msmt/xml?type=01&year=2025%2F2026[&rdat=DD.MM.YYYY]
    ← runtime = 'nodejs' (iconv-lite nekompatibilní s Edge)
    ← auth: pouze director
    ← windows-1250 konverze přes iconv-lite

app/dashboard/msmt/page.tsx
    ← prerekvizity (kódy žáků, uzavření pololetí, SVP)
    ← download linky (disabled pokud prerekvizity nesplněny)
    ← termíny sběru
```

### 31.3 Architekturická rozhodnutí

**Node.js runtime místo Edge:**
Edge Function nedostupná v Deno pro windows-1250 konverzi (TextEncoder
nepodporuje win1250). API route s `runtime = 'nodejs'` + `iconv-lite`
je správné řešení.

**`iconv-lite` jako soft dependency:**
`require('iconv-lite')` v try/catch — pokud není nainstalováno,
vrátí UTF-8 s varováním v konzoli. Tím build neselže, ale výstup
nebude validní pro MŠMT. Instalace: `npm install iconv-lite`.

**`lib/msmt-xml.ts` jako pure funkce:**
Žádná Supabase závislost — snadné testování, mockování dat.

**NULL vs 0 pro OML_H/NEOML_H:**
Speciální funkce `aN()` (nullable attribute) — NULL → atribut se
neuvede vůbec (prázdno), 0 → atribut="0". Nesmí se zaměnit s `a()`
která NULL rovněž vynechává, ale číslo 0 by konvertovala na "0" správně.
Konvence pro jistotu oddělena.

**Věty: vždy 2 per žák (pro standardní případ):**
Věta 1: PLAT_ZAC=1.9. (nebo enrollment) → PLAT_KON=31.1.
Věta 2: PLAT_ZAC=1.2. → PLAT_KON=(withdrawal nebo prázdno) + OML_H/NEOML_H

Edge cases:
- žák nastoupil po 31.1. → věta 1 přeskočena
- žák odešel před 1.2. → věta 2 přeskočena
- zpusob ≠ '11' → OML_H/NEOML_H vynechány (prázdno)
- žák nastoupil po 31.1. → OML_H/NEOML_H vynechány

### 31.4 Env proměnné

| Proměnná | Popis | Příklad |
|----------|-------|---------|
| `MSMT_IZO` | IZO školy (povinné) | `250002639` |
| `MSMT_RED_IZO` | IZO právního subjektu | `691012868` (nebo = IZO) |
| `MSMT_DRUH_SKOLY` | Druh školy | `B00` |
| `MSMT_TYP_SKOLY` | Typ vlastnictví | `2` (soukromá) |

Nastavit na Vercelu + `.env.local`.

### 31.5 Instalace

```bash
npm install iconv-lite
```

Pokud není nainstalováno, build projde, ale XML výstup bude v UTF-8
(MŠMT systém odmítne). Zkontrolovat `package.json` po instalaci.

### 31.6 Navigace

`/dashboard/msmt/page.tsx` je přehledová stránka celého modulu.
NAV_ITEMS: existující položka 'MŠMT kódy' (`/dashboard/msmt/kody-zaku`)
zůstává. Přidat nadřazenou položku nebo přejmenovat:

```typescript
// Možnost A: přejmenovat stávající položku
{ href: '/dashboard/msmt', label: 'MŠMT výkazy', ... }
// → /dashboard/msmt/kody-zaku dostupné přes link na stránce

// Možnost B: dvě oddělené položky v draweru
{ href: '/dashboard/msmt', label: 'MŠMT výkazy', ... }
{ href: '/dashboard/msmt/kody-zaku', label: 'MŠMT kódy', ... }
```

### 31.7 Otevřené TODO

- Soubor „b" (`_01b.xml`, ZSb.22) — zaměstnanci, pouze podzimní sběr
- RDAT picker v UI (místo aktuálního data)
- Školní rok selector (pro budoucí roky)
- Logování generování do `system_alerts` nebo audit logu
- Mid-year zpusob changes (víc než 1 education_mode záznam) —
  aktuálně bere pouze nejnovější; správné řešení = věty per každou
  platnost education_mode záznamu (nízká priorita pro Vilekulu)
