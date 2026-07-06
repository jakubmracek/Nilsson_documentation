## 27. Mobilní navigace — hamburger drawer (2026-05-13)

### 27.1 Rozhodnutí

Bottom nav zobrazuje **4 hlavní položky + hamburger**. Průvodce potřebuje
rychlý přístup k: Přehled / Třídní kniha / Omluvenky / Docházka.
Ostatní položky jsou v draweru.

### 27.2 Implementace

`bottomNav: true` → bottom nav lišta
`bottomNav: false` → drawer ("Více")

```
Bottom nav:  Přehled | Třídní kniha | Omluvenky | Docházka | Více ☰
Drawer:      Žáci, Uzavření pololetí, BOZP, Platby, VP, Zprávy, Nastavení
             + Odhlásit se
```

Hamburger se zobrazí pouze pokud `drawerItems.length > 0` —
pokud role nemá žádné skryté položky, hamburger zmizí.

### 27.3 State

`drawerOpen` state přímo v `AppNav` (Client Component).
Overlay (`bg-black/40`) zavře drawer kliknutím mimo.
`Link onClick={() => setDrawerOpen(false)}` zavře drawer při navigaci.

### 27.4 Opravené problémy při implementaci

PS skripty s multiline regex na JSX jsou **nespolehlivé** — preferovat
ruční úpravu nebo dodání kompletního souboru. Při PS úpravě vznikly:
- Duplicitní `'use client'` + `import { useState }` (PS přidal znovu)
- Hamburger `<li>` omylem vložen do sidebar sekce místo bottom nav
