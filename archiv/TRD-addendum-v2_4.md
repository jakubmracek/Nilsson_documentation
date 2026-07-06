# TRD — Addendum v2.4
# Aplikovat na TRD-v2.0.md (po aplikaci addend v2.1–v2.3)
# Datum: 2026-05-15

---

## CHANGELOG — přidat za v2.3

```
**Changelog v2.4 (2026-05-15):** Implementována stránka pro hromadné zadání
kod_zaka_msmt (/dashboard/msmt/kody-zaku). Server Action updateKodZakaMsmt
v app/actions/students.ts. Progress bar, inline edit, auto-strip lomítka,
UNIQUE guard. Bloker MŠMT XML odblokován po vyplnění 32 žáků.
Viz ARCH-NOTES v2.2 sekce 30.
```

---

## SEKCE 1.3 — aktualizovat soubory

```
app/actions/
└── students.ts                        ← updateKodZakaMsmt Server Action (nový)

app/dashboard/msmt/
└── kody-zaku/
    ├── page.tsx                       ← hromadný přehled + progress bar
    └── _components/
        └── KodZakaMsmtRow.tsx         ← inline edit per žák (Client)
```

---

## SEKCE 10.4 — Bloker MŠMT XML (aktualizovat stav)

```
| Bloker                              | Stav       | Poznámka                        |
|-------------------------------------|------------|---------------------------------|
| kod_zaka_msmt pro 32 žáků           | UI hotovo  | /dashboard/msmt/kody-zaku       |
| Polák Michael — student_matrika_a   | Čeká PPP   | pspo/id_znev z doporučení ŠPZ   |
| MŠMT XML generátor (Edge Function)  | TODO       | Fáze 3, windows-1250            |
```
