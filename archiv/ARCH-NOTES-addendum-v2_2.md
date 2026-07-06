# ARCH-NOTES — Addendum v2.2
# Připojit na konec ARCH-NOTES-v2.1.md
# Datum: 2026-05-15

---

## 30. Kódy žáků MŠMT — hromadná editace (2026-05-15)

### 30.1 Přehled

Implementována stránka pro hromadné zadání `kod_zaka_msmt` pro všechny žáky.
Prerekvizita před generováním MŠMT XML (viz TRD sekce 5.11).

### 30.2 Soubory

```
app/actions/students.ts
    ← updateKodZakaMsmt(studentId, rawKod): Server Action

app/dashboard/msmt/kody-zaku/
├── page.tsx
│   ← Server Component; SELECT students (active, ORDER BY kod_zaka)
│   ← progress bar: filled/total
└── _components/
    └── KodZakaMsmtRow.tsx
        ← Client Component; inline edit per řádek
        ← save on blur / Enter; Esc = revert
        ← auto-strip lomítko (RČ 170501/1341 → 1705011341)
        ← validace: právě 10 číslic, pouze [0-9]
```

### 30.3 UX vzory

- **Auto-strip:** `replace(/\//g, '').replace(/\D/g, '')` — dovoluje vložit
  RČ z jakéhokoli zdroje (s lomítkem, s mezerou, čistě číselné)
- **Optimistic:** hodnota se okamžitě zobrazí; stav (saving / saved / error)
  je vizuálně odlišen barvou inputu a ikonou
- **Keyboard:** Enter = save+blur, Esc = revert; tabulátor přechází na další řádek
- **UNIQUE guard:** error kód `23505` → srozumitelná hláška

### 30.4 Navigace

Přidat do `NAV_ITEMS` v `components/nav/AppNav.tsx`:

```typescript
{
  href: '/dashboard/msmt/kody-zaku',
  label: 'MŠMT kódy',
  // icon: Icons.document nebo podobné
  roles: ['director'],   // pouze ředitel
  bottomNav: false,      // → drawer
}
```

Nebo zařadit pod budoucí sekci "Výkazy" (seskupení v draweru — viz TRD sekce 5.11).

### 30.5 Server Action — poznámky

`updateKodZakaMsmt` je v `app/actions/students.ts` (nový soubor — žádný existující
students Server Action dosud neexistoval). Při budoucím přidávání dalších
student-related akcí (editace matrikových polí) přidávat do tohoto souboru.

`revalidatePath('/dashboard/msmt/kody-zaku')` — stránka se po uložení
server-side invaliduje; client vidí nový stav po dalším přechodu na stránku.
Při inline editaci stačí lokální React state (optimistic).
