# ARCH-NOTES Sekce 33 — Dark Mode
**Datum:** 2026-06-01  
**Autor:** session Jakub Mráček + Claude  
**Verze:** 1.0

---

## Strategie

`next-themes` s konfigurací:
```tsx
<ThemeProvider attribute="class" defaultTheme="system" enableSystem>
```

Téma se zapisuje jako třída `dark` na `<html>` elementu. Tři stavy: `light` / `system` / `dark`. Výběr uživatele perzistuje v `localStorage` přes `next-themes` automaticky.

---

## Klíčové soubory

### `app/globals.css`
- `@variant dark (&:where(.dark, .dark *))` — registrace dark varianty pro Tailwind v4 (místo `tailwind.config`)
- `.dark { --background: #0a0a0a; --foreground: #ededed; }` — CSS proměnné pro dark mode
- **Odstraněno:** `@media (prefers-color-scheme: dark)` — nahrazeno class strategií

### `app/providers.tsx`
```tsx
'use client'
import { ThemeProvider } from 'next-themes'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </ThemeProvider>
  )
}
```

### `app/layout.tsx`
- `<html suppressHydrationWarning>` — nutné, next-themes mění `class` při hydrataci
- `<Providers>` obaluje `{children}`

### `components/nav/AppNav.tsx` (v2)
- Přidána komponenta `ThemeToggle` — tři tlačítka ☀️ / 🖥️ / 🌙
- Umístění: sidebar — mezi uživatelským panelem a Odhlásit se; mobile drawer — nad Odhlásit se
- Všechny hardcoded barvy doplněny o `dark:` varianty

### `app/[[Přehled]]/layout.tsx` (v2)
- Shell elementy doplněny o `dark:` varianty:

| Element | Light | Dark |
|---|---|---|
| Hlavní wrapper | `bg-stone-50` | `dark:bg-stone-950` |
| Topbar (mobile) | `bg-white` | `dark:bg-stone-900` |
| Topbar border | `border-stone-200` | `dark:border-stone-700` |
| Logo pozadí | `bg-orange-50` | `dark:bg-orange-950` |
| Název "Nilsson" | `text-stone-900` | `dark:text-stone-100` |
| Jméno uživatele | `text-stone-500` | `dark:text-stone-400` |

---

## Pravidlo pro nové komponenty

Hardcoded Tailwind barvy **vždy** doplnit `dark:` variantou:

```
bg-white          → bg-white dark:bg-stone-900
bg-stone-50       → bg-stone-50 dark:bg-stone-950
text-stone-900    → text-stone-900 dark:text-stone-100
text-stone-600    → text-stone-600 dark:text-stone-400
border-stone-200  → border-stone-200 dark:border-stone-700
```

Barvy přes CSS proměnné (`bg-background`, `text-foreground`, `text-muted-foreground`) fungují automaticky — jsou navázány na `--background` / `--foreground` z `globals.css`.

---

## Závislosti

```
next-themes  (npm install next-themes)
```
