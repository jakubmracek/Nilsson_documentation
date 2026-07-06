# ARCH-NOTES addendum — 2026-06-29

Navazuje na předchozí addendum. Tato session zavedla modul **eSSL (Elektronický systém spisové služby)** jako migrace 036.

---

## §63 — eSSL: datový model

Migrace `036_essl.sql` zavedla 8 tabulek:

| Tabulka | Účel |
|---|---|
| `vecne_skupiny` | Spisový a skartační plán (SSP) — 8 skupin, 97 záznamů (úrovně 1–3) |
| `jmenny_rejstrik` | Evidence odesílatelů a adresátů |
| `dokumenty` | Hlavní evidence — číslo jednací, metadata, DS vazba |
| `spisy` | Obálky pro dokumenty téže věci — spisová značka |
| `dokument_spis` | M:N vazba dokument ↔ spis |
| `essl_transakce` | Append-only audit log (vzor: `student_matrika_changes`) |
| `skartacni_navrhy` + `skartacni_navrh_polozky` | Skartační řízení |
| `essl_cj_sekvence` + `essl_sz_sekvence` | Sekvence čísel jednacích a spisových značek |

Právní základ: § 66 zákona č. 499/2004 Sb. Škola má výjimku z atestace dle § 63 odst. 3 (ve znění zákona č. 197/2024 Sb.).

---

## §64 — Číslo jednací a spisová značka

- **Číslo jednací:** `VIL/[seq]/[rok]` — generuje trigger `trg_essl_cj` s advisory lock (`pg_advisory_xact_lock`) proti race condition při souběžných inserts
- **Spisová značka:** `VIL-[kód]/[seq]/[rok]` — generuje trigger `trg_essl_sz`, stejný pattern
- Kódy agend: `PRI`, `ODKL`, `PREST`, `SR`, `DOT`, `SML`, `ZAM`, `INS`, `SD`
- Sekvence se resetují každý rok (per rok v `essl_cj_sekvence`, per kód×rok v `essl_sz_sekvence`)

---

## §65 — datum_isteni: GENERATED ALWAYS AS není možné

`GENERATED ALWAYS AS` s výrazem `(datum_zahajeni_lhuty + (skartacni_lhuta_let || ' years')::interval)::date` selže s `42P17: generation expression is not immutable` — interval cast přes string concatenation PostgreSQL nepovažuje za immutable.

**Řešení:** plain `date` sloupec + trigger `essl_set_datum_isteni()` na `BEFORE INSERT OR UPDATE OF skartacni_lhuta_let, datum_zahajeni_lhuty`. Výpočet: `NEW.datum_zahajeni_lhuty + (NEW.skartacni_lhuta_let * interval '1 year')` — immutable.

Platí pro `dokumenty.datum_isteni` i `spisy.datum_isteni`.

---

## §66 — Unikátnost v jmenny_rejstrik

`UNIQUE NULLS NOT DISTINCT (ico)` způsobuje chybu `23505` při více řádcích s `ico = NULL` — Supabase to interpretuje jako duplicitní NULL. Správné řešení: **partial unique index**:

```sql
CREATE UNIQUE INDEX idx_jmenny_rejstrik_ico ON jmenny_rejstrik(ico) WHERE ico IS NOT NULL;
```

Stejný pattern pro `id_ds`.

---

## §67 — FTS konfigurace

Supabase nepodporuje konfiguraci `'czech'` pro `to_tsvector`. Použít `'simple'` — bez stemmingu, ale funkční pro české názvy.

---

## §68 — DS integrace: loose reference

Historická datová schránka byla evidována v Google Sheets (sheet `datovka`). Tabulka `dokumenty` má sloupec `ds_zprava_id bigint` jako loose reference na ISDS message ID — **bez FK constraint**, protože zdrojová data nejsou v Supabase.

Formát ISDS message ID je celé číslo (`bigint`), např. `1658287578`.

Při budoucím zavedení tabulky `ds_zpravy` do Supabase přidat FK dodatečnou migrací.

---

## §69 — Historický DS import

Skript `scripts/import_ds_log.ts` — jednorázový import 104 dokumentů (80 přijatých, 24 odeslaných) z Google Sheets do `dokumenty`. Rozsah: 2025-09-02 až 2026-06-26.

Klíčová rozhodnutí:
- Přílohy: `prilohy = []` — soubory jsou na Google Drive, URL doplnit manuálně přes UI
- `datum_zahajeni_lhuty` nastaveno explicitně z data vzniku záznamu (ne z `CURRENT_DATE` jako v triggeru — historické záznamy by dostaly špatný rok)
- Klasifikace věcné skupiny: 15 pravidel dle adresáta a předmětu, fallback `1.8.1` (Běžná korespondence S/5)
- Stav: `uzavreno` — historické dokumenty jsou vyřízené
- Subjekty bez shody v rejstříku: `subjekt_id = NULL`, `subjekt_nazev_cache` zachován
- Autentizace: vyžaduje **service_role key** (ne anon key) — anon key způsobí „věcná skupina nenalezena" pro všechny záznamy kvůli RLS

---

## §70 — Otevřené TODO pro eSSL

- [ ] Frontend `/dashboard/spisovna` — seznam dokumentů, detail, nový dokument, přiřazení do spisu
- [ ] Doplnění GDrive URL příloh do `dokumenty.prilohy` (manuálně přes UI)
- [ ] Cron job (GitHub Actions, Q1 každého roku) — volá `get_dokumenty_ke_skartaci()` a `get_spisy_ke_skartaci()`, generuje skartační návrh
- [ ] XML export metadat pro SOA Litoměřice (NSESSS schéma, VMV čá. 85/2024)
- [ ] Automatický import nových DS zpráv od 1. 1. 2027 (eSSL modul)
- [ ] Tabulka `ds_zpravy` v Supabase + FK z `dokumenty.ds_zprava_id`
