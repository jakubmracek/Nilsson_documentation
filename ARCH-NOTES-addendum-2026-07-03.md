# ARCH-NOTES Addendum — 2026-07-03
# eSSL Frontend: /dashboard/spisovka (session pokračování po 2026-06-29)

## §71 — Backfill skartačních údajů po DS importu

Import skriptu `scripts/import_ds_log.ts` zapsal `vecna_skupina_id` a
`datum_zahajeni_lhuty`, ale nepřenesl `skartacni_lhuta_let` a `skartacni_znak`
z věcné skupiny. Trigger `trg_essl_datum_isteni_dok` proto nenalezl data
pro výpočet `datum_isteni`.

Opraveno jednorázovým UPDATE:

```sql
UPDATE dokumenty d
SET
  skartacni_lhuta_let = vs.skartacni_lhuta_let,
  skartacni_znak      = vs.skartacni_znak
FROM vecne_skupiny vs
WHERE d.vecna_skupina_id = vs.id
  AND d.skartacni_lhuta_let IS NULL;
```

Výsledek: 104/104 dokumentů má `datum_isteni`, rozsah 2032-01-01 až 2037-01-01.
TODO: opravit import skript aby zapisoval tato pole přímo při INSERT.

---

## §72 — get_dokumenty_ke_skartaci — správný typ parametru

Funkce očekává `date`, nikoli `timestamp`. Volání:

```sql
-- Špatně (vrací chybu 42883):
SELECT * FROM get_dokumenty_ke_skartaci(CURRENT_DATE + interval '20 years');

-- Správně:
SELECT * FROM get_dokumenty_ke_skartaci((CURRENT_DATE + interval '20 years')::date);
```

Totéž platí pro `get_spisy_ke_skartaci`.

---

## §73 — Architektura frontendu /dashboard/spisovka

### Struktura souborů

```
app/dashboard/spisovka/
├── page.tsx                          # Seznam dokumentů (Server Component)
├── loading.tsx                       # Skeleton
├── novy/page.tsx                     # Nový dokument (Server Component)
├── [id]/page.tsx                     # Detail dokumentu (Server Component)
└── spisy/
    ├── page.tsx                      # Seznam spisů (Server Component)
    ├── novy/page.tsx                 # Nový spis (Server Component)
    └── [id]/page.tsx                 # Detail spisu (Server Component)

components/essl/
├── DokumentyTable.tsx                # Tabulka + filtry (Client Component)
├── DokumentDetail.tsx                # Detail + editace (Client Component)
├── NovyDokumentForm.tsx              # Formulář nového dokumentu (Client Component)
├── NovySpisForm.tsx                  # Formulář nového spisu (Client Component)
└── SpisDetail.tsx                    # Detail spisu + přiřazení (Client Component)

lib/essl/
├── types.ts                          # Lokální typy (DokumentRow, Spis, …)
└── queries.ts                        # Server-side Supabase dotazy
```

### Datové toky

- **Čtení:** Server Components volají `lib/essl/queries.ts` přes `.from()` s RLS.
  Nepotřebují RPC pro čtení — staff má SELECT na všechny eSSL tabulky.
- **Zápis dokumentů:** Client Components volají `.from('dokumenty').update()`
  přes browser client + `essl_log()` RPC pro audit.
- **Zápis spisů:** Client Components volají `.from('spisy').update/insert()`
  + `essl_log()` RPC.
- **Filtry:** URL search params (`?rok=2026&smer=prijaty`) — Server Component
  se re-renderuje, žádný client-side state pro data.

---

## §74 — DokumentDetail: typ DokumentDetail rozšiřuje Dokument o spisy

`getDokumentById` vrací `DokumentDetail` (definováno v `queries.ts`):

```typescript
export type DokumentDetail = Dokument & {
  spisy: Array<{
    spis_id: string
    poradi: number | null
    datum_zarazeni: string
    spis: {
      id: string
      spisova_znacka: string
      nazev: string
      stav: 'otevreny' | 'uzavreny'
    }
  }>
}
```

PostgREST join: `spisy:dokument_spis ( spis_id, poradi, datum_zarazeni, spis:spisy(...) )`.
Sekce „Zařazen ve spisu" je read-only v detailu dokumentu — odkaz na detail spisu.
Vyžadováno vyhláškou 259/2012 § 17 (viditelnost příslušnosti dokumentu ke spisu).

---

## §75 — NovyDokumentForm: datum_zahajeni_lhuty počítán na klientu

`datum_zahajeni_lhuty` = `1. 1. (rok vzniku + 1)` — počítáme v JS před INSERT:

```typescript
const rokVzniku = new Date(datumVzniku).getFullYear()
const datumZahajeniLhuty = `${rokVzniku + 1}-01-01`
```

DB trigger `trg_essl_datum_isteni_dok` pak automaticky vypočítá `datum_isteni`
z `datum_zahajeni_lhuty + skartacni_lhuta_let`.

---

## §76 — Encoding: UTF-8 bez BOM pro soubory s diakritikou

PowerShell `Set-Content` / přímé kopírování souborů z výstupu Claude
může zapsat soubory v špatném encodingu (UTF-8 s BOM nebo latin1).
Symptom: `â€"` místo `—`, `Ĺ™` místo `ř` atd.

Kanonický způsob zápisu v PowerShell:

```powershell
[IO.File]::WriteAllText("$PWD\cesta\k\souboru.tsx", $obsah, [Text.UTF8Encoding]::new($false))
```

Komentáře se speciálními UTF-8 znaky (`─`, `──`) vynechat nebo nahradit ASCII.

---

## §77 — essl_log RPC — signatura pro spisy (TODO ověřit)

Funkce `essl_log()` byla navržena primárně pro dokumenty (`p_dokument_id`).
Frontend volá `essl_log` i pro operace na spisech s parametrem `p_spis_id`.
Je potřeba ověřit aktuální signaturu v DB a případně přidat overload nebo
volitelný parametr `p_spis_id`.

```sql
-- Ověření aktuální signatury:
SELECT pg_get_functiondef(oid)
FROM pg_proc
WHERE proname = 'essl_log';
```

---

## §78 — Soulad s vyhláškou 259/2012 Sb.

Datový model pokrývá všechny povinné evidenční údaje dle § 17:
číslo jednací, datum doručení/vzniku, odesílatel/adresát, způsob doručení,
věcná skupina, skartační znak + lhůta, stav vyřízení, způsob vyřízení,
datum vyřízení, datum právní moci, zpracovatel.

Audit log (`essl_transakce`, append-only) splňuje § 17 odst. 2.

Otevřené body pro go-live:
- `essl_log` signatura pro spisy (§77)
- Regenerace TypeScript typů
- Ověření RLS politik pro zápis (director only pro spisy, zpracovatel pro dokument UPDATE)
