# Capability proposal: safe existing primitive composition

## package_id

`existing_targeted_damage_and_fixed_summon_v1`, profile `standard_full_20261001_v1`, baseline ManaMind `1686256493293459b6fa6f863832f887416025f7` (audit checkpoint `eb1018a`). Harvest has no random pool admission effect.

## semantic capability

Use existing `TARGET_DAMAGE`, `EFFECT_COMPOSITION`, selectors and `SUMMON_FIXED` for four pinned contracts: unrestricted character damage; minion-only damage; enemy-minion area damage; and damage followed by a fixed Rush token summon. Spell damage remains resolved by the existing damage pipeline. The final consumer does not imply support for conditional summon, area-target or hidden pool semantics beyond its declaration.

Implementation kind: `GENERIC` existing operations plus declarations. There is no new implementation operation or ID dispatch. Independent variations are current `CORE_CS2_029` six-damage character spell and `CORE_CS2_062` all-character damage, alongside the four new declarations below.

## existing primitives

`Ability::TargetDamage`, `Ability::EffectComposition`, `legal_targets`, `resolve_effects`, `EffectKind::SummonFixed`, `summon_fixed`, existing Rush and spell damage handling. No change to their semantics.

## candidates and declaration contract

| ID | Pinned text | Declaration |
|---|---|---|
| `CORE_DS1_185` Arcane Shot | Deal 2 damage. | `TARGET_DAMAGE`, 2 |
| `CORE_CS1_130` Holy Smite | Deal 3 damage to a minion. | one `DAMAGE / EXPLICIT_MINION / 3` |
| `CORE_CS2_032` Flamestrike | Deal 5 damage to all enemy minions. | one `DAMAGE / ENEMY_MINIONS / 5` |
| `CORE_BAR_801` Wound Prey | Deal 1 damage. Summon a 1/1 Hyena with Rush. | `DAMAGE / EXPLICIT_CHARACTER / 1`, then `SUMMON_FIXED / SELF / 1 / BAR_035t` |

Independent metadata identities are in the pinned profile. `BAR_035t` is a fixed dependency, not a collectible root: 1/1 Beast, Rush, with no additional rules text. Its full metadata object and provenance are recorded in `dependency_metadata_audit.json`. Tests must exercise that Rush survives summon and gates hero attacks for the turn.

## dependencies

No dynamic pools. Only fixed `BAR_035t` for Wound Prey; exact dbfId 63459, 1/1 Beast, Rush. A successful summon is conditional on an available board slot under the existing summon operation. No class resource or additional class/session mechanic is introduced by these effect contracts.

## changes / expected unlocks

Four unique roots can use existing declarations. One exact fixed dependency is added to the experimental metadata audit. No engine, bridge schema or policy features change; no card-ID branch is allowed. At most these declarations gain scoped ManaEngine behavior; neither Fire nor Whelp pool membership/admission, canonical registry correctness, full dependency closure or training eligibility changes.

## test strategy

One native family scenario with independent assertions for character targets, minion-only target legality, enemy-only area recipients, exact damage, fixed token identity/stats/Rush, full board behavior and Rush attack legality. Adapter checks load the real four declarations, preserve the domain/action schema, and cover target encodings. Run the native suite, focused adapter/policy checks, full pytest, generated artifact ownership checks and both hosted workflows. No bridge evidence is claimed unless a Rosetta comparison is separately executed.

## deferred outliers

`CORE_BOT_222` damages a target minion and its own hero in one card; current effects cannot declare SELF damage. `CORE_BAR_801`-adjacent conditional summon (`TIME_006`) is deferred because holding a Dragon changes the summon count. Board snapshots, conditionals and target-selector extensions stay out of this package.
