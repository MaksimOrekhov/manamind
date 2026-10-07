# ENGINE-QUICK-3: existing-primitive ManaEngine batch (completion record)

Date: 2026-10-07, branched from main `1eb4ce6`. Declaration-only; no engine, generator, ABI or Python-loader change. ENGINE-QUICK-2 (Mother Duck, Flash of Light, Arcane Intellect, Elven Archer, Flame Imp) is a separate parallel batch and is untouched.

Pinned metadata was checked and none of the five cards had a declaration before this batch.

| Card | Pinned text | Existing contract |
|---|---|---|
| `CORE_CS2_042` Fire Elemental | Battlecry: Deal 4 damage. | minion battlecry via `EFFECT_COMPOSITION`: `DAMAGE EXPLICIT_CHARACTER 4` (no Spell Damage for minions) |
| `CORE_UNG_205` Glacial Shard | Battlecry: Freeze an enemy. | `FREEZE EXPLICIT_ENEMY_CHARACTER` (enemy hero or minion) |
| `CORE_EX1_096` Loot Hoarder | Deathrattle: Draw a card. | `DEATHRATTLE_DRAW`, count 1, no filter (as Bloodmage Thalnos) |
| `CORE_EX1_011` Voodoo Doctor | Battlecry: Restore #2 Health. | `HEAL EXPLICIT_CHARACTER 2` (hero cap 30, minion cap max Health) |
| `CORE_BT_035` Chaos Strike | Give your hero +2 Attack this turn. Draw a card. | `MODIFY_HERO_ATTACK SELF 2`, `DRAW SELF 1` (as Press the Advantage) |

All five were representable completely; none was rejected. Each declaration pins its reviewed text, so a text change fails closed. Nearby cards (`RLK_511` Frost-spell draw, `CATA_612` Freeze this, `EDR_468`, `CORE_OG_047`, `TIME_431`, `RLK_708`) stay UNSUPPORTED and are asserted so.

Tests: `experiments/manaengine/tests/test_quick3_existing_primitives.py` (6), including exact legal-target sets, exact amounts, cap behavior, deathrattle timing, hero-attack expiry at end of turn, and opponent-side execution.

Debt: SUPPORTED by reviewed-text guard only; not rules-verified, not verified-scoped, not training eligible. Heal assumes the engine's fixed 30 hero maximum. Targeting of Stealth/Elusive minions and an empty-target battlecry are not modeled beyond existing engine behavior. Hero attack uses the existing fixed lifecycle; no Windfury/weapon interactions were tested.
