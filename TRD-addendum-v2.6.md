# TRD Addendum v2.6 — Modul Docházka
**Datum:** 2026-06-01  
**Autor:** session Jakub Mráček + Claude  
**Soubor:** `app/actions/dochazka.ts` (v4)

---

## Bug fix: `saveDayAttendance` — PostgREST NOT NULL violation (23502)

### Symptom

`POST /rest/v1/attendance_records → 400`  
`proxy_status: PostgREST; error=23502`

Chyba nastávala **pouze při druhém uložení téhož dne** — první uložení (čisté inserty) proběhlo bez problémů. Při druhém uložení byly v dávce záznamy s `existingId` (update) i bez něj (insert), což způsobilo chybu.

### Příčina

PostgREST odvozuje query parametr `columns=` jako **union všech klíčů** v poli objektů předaném do `.upsert()`. Původní kód používal podmíněný spread:

```typescript
// ❌ v3 — problematický kód
const records = upserts.map(row => ({
  ...(row.existingId ? { id: row.existingId } : {}),
  student_id: row.studentId,
  // ...
}))
await supabase.from('attendance_records').upsert(records, ...)
```

Pokud bylo v poli alespoň jedno `{ id: ... }`, PostgREST přidal `id` do `columns` pro **celý batch**. Záznamy bez `id` pak dostaly `NULL` → `23502 not_null_violation` (sloupec `id` je `NOT NULL`, default `gen_random_uuid()`).

Vercel log potvrdil: `columns="student_id","date","status","hodiny","note","group_id","staff_id","id"`

### Řešení

Rozdělit upsert na dvě samostatná volání se striktně homogenními payload:

```typescript
// ✅ v4 — opravený kód
const updates = upserts.filter(row => row.existingId)
const inserts = upserts.filter(row => !row.existingId)

if (updates.length > 0) {
  await supabase.from('attendance_records').upsert(
    updates.map(row => ({ id: row.existingId!, student_id: row.studentId, ... })),
    { onConflict: 'student_id,date' }
  )
}

if (inserts.length > 0) {
  await supabase.from('attendance_records').upsert(
    inserts.map(row => ({ /* id záměrně vynecháno */ student_id: row.studentId, ... })),
    { onConflict: 'student_id,date' }
  )
}
```

### Obecné pravidlo

> **PostgREST anti-pattern:** nikdy nemixovat objekty s různými sadami klíčů v jednom `.upsert()` volání, pokud jsou některé klíče `NOT NULL` bez defaultu nebo jsou to primární klíče s DB defaultem (`gen_random_uuid()`). Vždy rozdělit na homogenní batche.
