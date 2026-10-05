# ManaEngine mortality decision table (Phase 4H.3)

Scope: behavior of `experiments/manaengine` at the Phase 4H.3 remediation commit. This is a record of what the code
does, not a rules-verification claim and not new support. A *mortally wounded* minion has `health <= 0`, is still in
Play, and is removed only by the outer `stabilize()` death boundary. Decisions: **include**, **exclude**,
**evidence constrained** (behavior kept, `EvidenceConstraint` recorded), **fail closed** (session poisoned).

Rules background (independent research, not official, not replay evidence): the Advanced rulebook at
<https://hearthstone.wiki.gg/wiki/Advanced_rulebook> describes AoE as counting mortally wounded characters, targeted or
random negative triggers as ignoring them, and Secrets as aborting when their specific target is mortal. The engine
follows that shape. It is a model, not a verified client behavior.

## Decision table

| Area | Case | Decision | Code / evidence |
|---|---|---|---|
| Ordinary AoE membership | Enemy-minion area (`CORE_CS2_032`, `JAIL_805`, `JAIL_805t`, `CORE_EX1_129`), all-minion area (`CATA_582`, `EDR_570` damage mode), `ALL_CHARACTERS` (`CORE_CS2_062`), `ENEMY_CHARACTERS` (`CATA_489` area step, fragments), Vulcanos `CATA_488`, `CATA_475` | **include** pending-death minions (no `health>0` filter); hero targets included where the selector names them | `resolve_effects` selectors, `resolve_end_turn_reactions`; DG tests, differential probe PD |
| Ordinary AoE membership | Explosive Trap `CORE_EX1_610` | **exclude** (`minion.health>0` filter kept). Accidental inconsistency with the row above; **unreachable today** because attack-declaration windows start from a quiescent board and no other attack-window Secret deals damage. Not changed in this pass | `resolve_secret_instance` EnemyAreaDamage |
| Random target candidates | `RANDOM_ENEMY_MINION` (Sleet Storm second step) | **fail closed** if *any* pending-death minion exists on either side; otherwise candidates are enemy minions with `health>0`; empty set consumes no RNG | `resolve_effects` |
| Random target candidates | Arcane Missiles | **exclude** mortal minions; pool = enemy hero + enemy minions with `health>0`, rebuilt before every missile | `resolve_spell` |
| Random target candidates | Flames of Infinity | **exclude** mortal minions (highest-health tie set); no living minion means not eligible | `resolve_secret_instance` |
| Explicit targets | Damage to a chosen target | target legality is fixed at action start; no extra mortality filter inside one action | `legal_targets` |
| Explicit targets | Heal / HealMinionToFull / BuffMinion on a mortal target; target left the board | **fail closed** | `resolve_effects` (bare throw, now funneled to poison) |
| Explicit targets | Damage-outcome conditions (`MortallyWounded`, `Survives`, draw-target-owner) | read health after the completed group; target missing is **fail closed** | `resolve_effects` |
| Explicit targets | `DestroyMinion` | sets health to 0 (pending destroy); minion stays until the outer boundary | `resolve_effects` |
| Reaction consumers | TakesDamage consumer lethal / already mortal / silenced / identity changed | **fail closed** (v1 bound) | `resolve_damage_occurrence` |
| Queued EOT sources | `CATA_488`, `CATA_475`, `CATA_999` queued before an earlier source made it mortal | **evidence constrained**: resolves while still in Play; records `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED`; branch stays valid, training admission is blocked by the debt | `resolve_end_turn_reactions` |
| Queued EOT sources | silenced after collection, removed, transformed, controller/identity changed | **fail closed**; silenced before collection is simply not queued | `resolve_end_turn_reactions` |
| Secrets | Explosive Runes, Mystic Misdirection | **exclude/abort**: Secret is not consumed when its subject is not `health>0` | `resolve_secret_instance` |
| Secrets | Flames of Infinity | eligible only while some enemy minion has `health>0` | `resolve_secret_instance` |
| Secrets | Explosive Runes excess | computed from pre-hit Health (including Shield/Immune), never from `PacketOutcome` | reviewed contract, native tests |
| Combat | attacker mortal after attack-window Secrets | attack **cancelled** (outer boundary only, no damage) | `execute_action` Attack |
| Combat | defender / attacker packets | one paired scalar group; reactive consumers **fail closed** before either packet | `guard_scalar_damage` |
| Spell Damage providers | non-silenced provider counted while mortal | **include** in `spell_damage_for` (state fact) | `spell_damage_for` |
| Spell Damage providers | mortal provider before an instruction, a spell area or an Explosive Trap trigger | **fail closed** | `evaluate_spell_damage`, `guard_area_spell_modifiers`, Trap guard |
| Spell Damage providers | static provider wounded or killed inside the one area | **include**: captured amount stays fixed, removal at the outer boundary | `guard_area_spell_modifiers` |
| Spell Damage providers | undamaged conditional provider (`END_022`) targeted by a *spell* area | **fail closed** (conservative; the amount is already fixed, so this is a coverage cost, not a correctness need) | `guard_area_spell_modifiers` |
| Spell Damage providers | Effect damage (Vulcanos, `CATA_475`, `CATA_999`, minion Battlecries) | ignores Spell Damage entirely, so providers among targets are not guarded | `resolve_effects`, EOT |

This table does not widen any support boundary. `fail closed` rows remain unsupported; the evidence-constrained row is
the only mortal-source behavior that executes.

## Consumer notes (current behavior)

| Card | Route | Notes |
|---|---|---|
| `JAIL_805` | held spell transform; Lifesteal `ENEMY_MINIONS 2` (Spell kind) | one minion-area group in entry order; Shield/Immune prevent damage and Lifesteal; fixed 30-health hero heal; `DirectSpell` accounting per successful packet |
| `JAIL_805t` | minion Battlecry trigger running the same effect list | Effect kind (no Spell Damage, no Raincaller); same area path; scalar Lifesteal |
| `CORE_EX1_129` | enemy-minion area, then Draw | Draw runs only after the group and its reactions complete; one TakesDamage consumer reacts normally; fatigue stays a single-packet group |
| `CATA_999` | EOT, single hero packet | no area; a mortal queued source resolves with `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED` (winner can differ from the pre-4H.1 skip) |
| `CATA_475` | EOT, enemy minions then hero, scalar-only group | a reactive consumer among targets is rejected before mutation; a mortal queued source carries the same debt |
| `CATA_488` | EOT, all other minions, minion-entry order | mortal queued source carries the debt; its Fire pool stays blocked |
| `CORE_EX1_610` | attack-window area | scalar-only group; mortal filter row above |

## Failure funnel (public boundary)

`apply_action()` rejects illegal input before any mutation (`std::invalid_argument`, session stays valid). After execution
starts, any escaping failure sets `state_.unsupported` (first reason kept, prefixed `action failed after mutation:` when
the failure itself had not poisoned), clears hidden damage frames and rethrows the original exception. Poisoned sessions
refuse `legal_actions`, `clone`, `observation`, `result`, `is_complete`, `needs_choice`, `choice_options`,
`begin_prototype_choice` and further actions; `is_valid`, `unsupported_outcome`, `evidence_constraints`,
`diagnostic_trace` and `seed` stay available as explicit diagnostics.
