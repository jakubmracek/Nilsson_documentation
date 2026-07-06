## Omluvenky — Discord notifikace (2026-06-24)

Notifikace `embedNovaOmluvenka` se odesílá v `portal-omluvenky.ts →
createGuardianOmluvenka`, ihned po úspěšném INSERTu omluvenky rodičem.
Jméno žáka se donačte extra dotazem na `students`.

`approveOmluvenka` Discord notifikaci neposílá — byla odstraněna.
`rejectOmluvenka` posílá `embedOmluvenkaRejected` beze změny.