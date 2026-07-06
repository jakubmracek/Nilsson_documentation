# ARCH-NOTES — Addendum v2.3 — dodatek
# Připojit za sekci 31.7 v ARCH-NOTES-addendum-v2_3.md
# Datum: 2026-05-15

---

### 31.8 Produkční oprava: Buffer → Uint8Array (Next.js 16)

**Problém:**
`new NextResponse(encoded, ...)` kde `encoded: Buffer` způsobilo TypeScript chybu při buildu:

```
Type 'Buffer<ArrayBufferLike>' is not assignable to parameter of type 'BodyInit | null | undefined'.
Type 'Buffer<ArrayBufferLike>' is missing the following properties from type 'URLSearchParams'
```

**Příčina:**
Next.js 16 zpřísnil typování `NextResponse` — `Buffer` není přímý `BodyInit`.
`Buffer` je Node.js třída, `BodyInit` očekává `ArrayBuffer`, `Uint8Array` nebo `string`.

**Oprava:**

```typescript
// toWin1250 — návratový typ Buffer → Uint8Array
async function toWin1250(utf8string: string): Promise<Uint8Array> {
  const buf = iconv.encode(utf8string, 'win1250')   // vrací Buffer
  return new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength)
  // fallback: return new TextEncoder().encode(utf8string)
}

// NextResponse — předat ArrayBuffer, ne Buffer přímo
return new NextResponse(encoded.buffer as ArrayBuffer, { headers: { ... } })
```

**Obecné pravidlo pro Next.js 16 route handlery:**
Pokud vracíte binární data, používejte `Uint8Array` / `ArrayBuffer`, ne `Buffer`.
`Buffer` funguje za runtime, ale TypeScript v Next.js 16 ho jako `BodyInit` neakceptuje.
