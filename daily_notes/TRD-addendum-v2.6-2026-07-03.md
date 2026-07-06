# TRD Addendum v2.6 — 2026-07-03
# eSSL Frontend: /[[Přehled]]/[[Spisovka]]

## Změny oproti v2.5

### Nové soubory

| Soubor | Typ | Popis |
|--------|-----|-------|
| `lib/essl/types.ts` | Utility | Lokální typy pro eSSL modul |
| `lib/essl/queries.ts` | Server utility | Supabase dotazy pro eSSL |
| `app/[[Přehled]]/[[Spisovka]]/page.tsx` | Server Component | Seznam dokumentů |
| `app/[[Přehled]]/[[Spisovka]]/loading.tsx` | Server Component | Skeleton |
| `app/[[Přehled]]/[[Spisovka]]/novy/page.tsx` | Server Component | Shell formuláře nového dokumentu |
| `app/[[Přehled]]/[[Spisovka]]/[id]/page.tsx` | Server Component | Shell detailu dokumentu |
| `app/[[Přehled]]/[[Spisovka]]/spisy/page.tsx` | Server Component | Seznam spisů |
| `app/[[Přehled]]/[[Spisovka]]/spisy/novy/page.tsx` | Server Component | Shell formuláře nového spisu |
| `app/[[Přehled]]/[[Spisovka]]/spisy/[id]/page.tsx` | Server Component | Shell detailu spisu |
| `components/essl/DokumentyTable.tsx` | Client Component | Tabulka dokumentů + filtry |
| `components/essl/DokumentDetail.tsx` | Client Component | Detail + editace dokumentu |
| `components/essl/NovyDokumentForm.tsx` | Client Component | Formulář nového dokumentu |
| `components/essl/NovySpisForm.tsx` | Client Component | Formulář nového spisu |
| `components/essl/SpisDetail.tsx` | Client Component | Detail spisu + přiřazení dokumentů |

### Změněné soubory

| Soubor | Změna |
|--------|-------|
| `components/nav/AppNav.tsx` | Přidána ikona `archive` + nav položka `[[Spisovka]]` (roles: director) |
| `lib/essl/queries.ts` | `getDokumentById` rozšířen o JOIN `dokument_spis → spisy` |

---

## Klíčové typy (lib/essl/types.ts)

```typescript
DokumentStav   = 'prijat' | 'prideleno' | 've_vyrizeni' | 'vyrizeno' | 'uzavreno'
DokumentSmer   = 'prijaty' | 'odchozi' | 'vlastni'
ZpusobDoruceni = 'datova_schranka' | 'email' | 'posta' | 'osobne'
ZpusobVyrizeni = 'odpoved_odeslana' | 'rozhodnuti_vydano' | 'postoupeno'
                 | 'ulozeno_bez_odpovedi' | 'vzato_na_vedomi'
SkartacniZnak  = 'A' | 'S' | 'V'
```

Exportované label mapy: `STAV_LABELS`, `SMER_LABELS`, `SKARTACNI_ZNAK_LABELS`,
`ZPUSOB_DORUCENI_LABELS`, `KOD_AGENDY_OPTIONS`.

---

## Datové operace

### Čtení (server-side, lib/essl/queries.ts)

| Funkce | Tabulky | Použití |
|--------|---------|---------|
| `getDokumenty(filters)` | `dokumenty` + `vecne_skupiny` | Seznam dokumentů |
| `getDokumentById(id)` | `dokumenty` + `vecne_skupiny` + `jmenny_rejstrik` + `dokument_spis` + `spisy` | Detail dokumentu |
| `getVecneSkupiny()` | `vecne_skupiny` | Select ve formulářích |
| `getJmennyRejstrik()` | `jmenny_rejstrik` | Combobox subjektů |
| `getSpisy()` | `spisy` | Seznam spisů |
| `getSpisById(id)` | `spisy` + `dokument_spis` + `dokumenty` | Detail spisu |
| `getDostupneRoky()` | `dokumenty` | Filtr roku |

### Zápis (client-side, browser Supabase client)

| Operace | Tabulka | Audit |
|---------|---------|-------|
| Nový dokument | `dokumenty` INSERT | `essl_log('dokument_zaevidovan')` |
| Editace dokumentu | `dokumenty` UPDATE | `essl_log('dokument_vyrizeno')` |
| Nový spis | `spisy` INSERT | `essl_log('spis_zalozen')` |
| Přiřazení dokumentu | `dokument_spis` INSERT | `essl_log('dokument_prirazen_spisu')` |
| Uzavření spisu | `spisy` UPDATE | `essl_log('spis_uzavren')` |

---

## Otevřené TODO před go-live

1. **`essl_log` signatura** — ověřit podporu `p_spis_id` parametru v DB funkci
2. **Supabase TypeScript typy** — `npx supabase gen types typescript --project-id <id>`
   → přepsat `(supabase as any)` casts v eSSL souborech
3. **Import skript** — opravit `scripts/import_ds_log.ts` aby zapisoval
   `skartacni_lhuta_let` + `skartacni_znak` přímo při INSERT
4. **RLS audit** — ověřit že spisy INSERT/UPDATE je omezen na `director`
5. **Encoding** — všechny tsx soubory zapisovat přes
   `[IO.File]::WriteAllText(..., [Text.UTF8Encoding]::new($false))`
