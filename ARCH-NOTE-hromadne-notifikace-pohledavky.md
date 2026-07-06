# ARCH-NOTE: Hromadné notifikace při vytvoření pohledávek

**Datum:** 2026-06-24  
**Modul:** Platby — `payment_obligations` + `NovaPohledavkaForm`  
**Soubory:** `app/actions/payments.ts`, `app/dashboard/platby/pohledavky/nova/_components/NovaPohledavkaForm.tsx`

---

## Kontext

Původní flow vyžadovalo po vytvoření pohledávek ruční rozkliknutí každé
z nich a samostatné odeslání notifikace. Při 30 žácích = 30 kliků.

## Řešení

Formulář `NovaPohledavkaForm` obsahuje checkbox „Odeslat e-mailové notifikace
zákonným zástupcům" (defaultně zapnutý). Po odeslání formuláře `createObligations`
zavolá `sendNotifications()` hromadně pro všechny nově vytvořené pohledávky.

## Tok dat

```
NovaPohledavkaForm
  └── createObligations({ ..., notifyGuardians: true })
        ├── INSERT payment_obligations → .select('id, amount')
        └── pro každou pohledávku s amount > 0:
              sendNotifications(obligation.id)
                ├── načte studenta + zákonné zástupce
                ├── odešle e-mail přes Resend (QR kód, VS, SS)
                └── zapíše notified_at na pohledávce
```

## Klíčová rozhodnutí

**Sekvenční odesílání, ne `Promise.all`**  
Resend může throttlovat při souběžných požadavcích. Při 30 žácích
(1–2 zákonní zástupci každý) = 30–60 e-mailů sekvenčně; v praxi řádově
jednotky sekund. Pokud by se škola výrazně zvětšila, zvážit dávkování
nebo Resend Batch API.

**Chyby notifikací jsou nekritické**  
Insert pohledávek proběhl — chyba notifikace se zaloguje
(`console.warn`), ale `createObligations` vrátí úspěch. Notifikaci
lze doslat ručně přes detail pohledávky (stávající flow).

**Pohledávky s `amount = 0` notifikaci nedostanou**  
Filtr `amount > 0` je záměrný — nulová pohledávka nevyžaduje platbu,
e-mail by byl matoucí.

**Insert změněn z `count` na `.select('id, amount')`**  
Potřebujeme `id` vložených řádků pro volání `sendNotifications`.
`count: 'exact'` nahrazen délkou vráceného pole.

## Rozhraní (diff typů)

```ts
// CreateObligationsInput
+ notifyGuardians?: boolean

// CreateObligationsResult
+ notificationsSent?: number  // undefined pokud notifyGuardians = false
```

## UX

- Checkbox defaultně zapnutý — nejčastější případ je okamžité oznámení.
- Tlačítko v pending stavu: „Ukládám a odesílám…" / „Ukládám…"
- Po úspěchu zelený banner se souhrnem (`Vytvořeno N pohledávek. Odesláno M notifikací.`),
  po 1,8 s přesměrování na `/pohledavky`.

## Související

- `sendNotifications` (payments.ts §2) — stávající action pro odeslání
  notifikace jedné pohledávky; zde volaná hromadně
- `notified_at` na `payment_obligations` — timestamp posledního odeslání;
  zapisuje `sendNotifications`, slouží jako ochrana před duplicitním odesláním
  při ručním odeslání z detailu pohledávky
