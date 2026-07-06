# TRD — Addendum v2.5
# Aplikovat na TRD-v2.0.md (po aplikaci addend v2.1–v2.4)
# Datum: 2026-05-15

---

## CHANGELOG — přidat za v2.4

```
**Changelog v2.5 (2026-05-15):** Implementován MŠMT XML generátor.
lib/msmt-xml.ts — čistá generační logika (ZS.025, základní + „a").
app/api/msmt/xml/route.ts — Node.js API route, windows-1250 (iconv-lite),
autorizace director. app/dashboard/msmt/page.tsx — prerekvizity +
download UI. Prerekvizita: npm install iconv-lite + env MSMT_IZO.
Viz ARCH-NOTES v2.3 sekce 31.
```

---

## SEKCE 5.11 — Matriční výkazy (aktualizovat status)

```
**Status: _01.xml a _01a.xml nasazeny v produkci (2026-05-15)**

Soubor „b" (_01b.xml, zaměstnanci, ZSb.22) — TODO, pouze podzimní sběr.
```

---

## SEKCE 1.3 — aktualizovat soubory

```
lib/
└── msmt-xml.ts                        ← čistá generační logika (nový)

app/api/msmt/
└── xml/
    └── route.ts                       ← GET endpoint, Node.js runtime,
                                          windows-1250, auth director (nový)

app/dashboard/msmt/
└── page.tsx                           ← přehled + prerekvizity + download (nový)
```

---

## SEKCE 8.3 — MŠMT (aktualizovat status blokerů)

```
| Bloker                              | Stav              | Poznámka                   |
|-------------------------------------|-------------------|----------------------------|
| kod_zaka_msmt pro 32 žáků           | UI hotovo         | /dashboard/msmt/kody-zaku  |
| _01.xml generátor                   | Nasazeno          | /api/msmt/xml?type=01      |
| _01a.xml generátor                  | Nasazeno          | /api/msmt/xml?type=01a     |
| _01b.xml generátor (zaměstnanci)    | TODO              | Pouze podzimní sběr        |
| Polák Michael — student_matrika_a   | Čeká PPP          | pspo z doporučení ŠPZ      |
| iconv-lite                          | npm install nutný | viz ARCH-NOTES 31.5        |
| Env MSMT_IZO + MSMT_RED_IZO         | Nastavit Vercel   | viz ARCH-NOTES 31.4        |
```
