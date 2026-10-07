# ENGINE-QUICK-4: existing-primitive ManaEngine batch (completion record)

Date: 2026-10-07, branched from main `7431ac2`. Declaration-only: no engine, native, generator, loader or dependency-metadata change.

Pinned metadata was checked; none of the five cards had a declaration.

| Card | Pinned text | Existing contract |
|---|---|---|
| `CS3_038` Redgill Razorjaw | Rush (3/1 Murloc) | `NONE` + `VERIFIED_VANILLA`; text and mechanics are exactly the modeled keyword Rush. Real evidence: 1 game / 3 observations |
| `CORE_EX1_278` Shiv | Deal $1 damage. Draw a card. | `DAMAGE EXPLICIT_CHARACTER 1`, `DRAW 1` |
| `CORE_AT_064` Bash | Deal $3 damage. Gain 3 Armor. | `DAMAGE EXPLICIT_CHARACTER 3`, `GAIN_ARMOR 3` |
| `CORE_EX1_606` Shield Block | Gain 5 Armor. Draw a card. | `GAIN_ARMOR 5`, `DRAW 1` |
| `RLK_709` Remorseless Winter | Deal $2 damage to all enemies. Draw a card. | `DAMAGE ENEMY_CHARACTERS 2`, `DRAW 1` |

All five fit completely; none was rejected. Tests: `experiments/manaengine/tests/test_quick4_existing_primitives.py` (8). Neighbours with untrustworthy or unmodeled behavior (`TLC_248`/`TIME_053` textless metadata, Divine Shield, area Freeze, friendly healing) stay UNSUPPORTED.

Debt: SUPPORTED/VERIFIED_VANILLA by reviewed-text guard only; not rules-verified, not verified-scoped, not training eligible. Armor absorption of later damage uses existing engine behavior and was not re-reviewed here.
