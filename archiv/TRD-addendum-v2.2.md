## TRD — Addendum v2.2
## Datum: 2026-05-13

### Changelog — přidat za v2.1

```
**Changelog v2.2 (2026-05-13):** Mobilní navigace rozšířena o hamburger drawer.
Bottom nav: Přehled / Třídní kniha / Omluvenky / Docházka / Více.
Drawer: zbývající položky dle role + Odhlásit se. Viz ARCH-NOTES sekce 27.
```

### Sekce 1.3 — aktualizovat soubory

```
components/nav/AppNav.tsx   ← hamburger drawer, drawerOpen state,
                               Icons.hamburger, bottomNav redistribuce
```

### Redistribuce bottomNav v NAV_ITEMS

| Položka | bottomNav před | bottomNav po |
|---------|---------------|--------------|
| Přehled | true | true |
| Žáci | true | **false** → drawer |
| Třídní kniha | false | **true** → bottom nav |
| Omluvenky | true | true |
| Docházka | true | true |
| Zprávy | true | **false** → drawer |
| ostatní | false | false |
