# Phase 4F capability proposals

Branch `codex/manaengine-first-deck`; proposal baseline `a31fe5612b72c7e190dcbd3c950cd15aac6405bf`.

## `choice_mode_continuation_v1`

**Semantic contract.** A played Choose One spell opens one typed pending mode choice. Only the selected mode resolves. A selected mode may open a second typed target continuation; legality is calculated from current state, and a target is rejected if it has become illegal. Branch effects use the existing bounded `EffectStep` operations. No arbitrary effect script or card-ID dispatch is introduced.

**Reviewed candidates.** `CORE_AT_037` Living Roots and `EDR_570` Ominous Nightmares; both occur in the raw 77-card Whelp candidate pool and its 65/63 working envelopes. The pinned 2026-10-01 snapshot identifies EDR_570 as Warrior, cost 1. The frozen pool remains `CANDIDATE` with `OPEN` dependency closure.

**Rules basis.** The pinned official 2026-10-01 card snapshot records the two exact mode texts. Blizzard's Emerald Dream announcement independently confirms Ominous Nightmares belongs to the expanded Choose One mechanic. Blizzard's card pages are script-rendered and their text was not extractable in this review, so the pinned snapshot is the exact text source; Rosetta is implementation evidence only. Living Roots: choose deal 2 damage to a character or summon two 1/1 Saplings. Ominous Nightmares: choose deal 1 damage to all minions or give a damaged minion +2/+2. The targeted modes expose only their respective legal target sets. Each card resolves only the selected branch, then the engine follows its existing prototype stabilization boundary.

**Existing primitives.** `EFFECT_COMPOSITION`, typed `EffectStep`, target generation, damage attribution/Spell Damage, fixed summon, damaged-minion selection, action-level `choose_one_a/b` Policy features, pending-choice owner/options, clone-by-state-copy.

**Required shared changes.** Add two validated mode declarations to `CardDefinition`; represent mode selection and selected-effect target as distinct internal pending-choice variants; export mode and target actions through current `CHOOSE_CARD` semantic actions with existing `choose_one_a/b` features; preserve pending state in clone. Add a narrowly typed `BUFF_MINION` effect and `EXPLICIT_DAMAGED_MINION` target for Ominous Nightmares. No new observation feature is planned: the public pending-choice boundary already exists, and legal action rows carry mode/target semantics through the adapter and Policy. Confirm parity before retaining this no-schema-change decision.

**Dependencies.** Living Roots requires pinned Sapling token `AT_037t`; the token must be present as a supported fixed dependency. No dynamic pool. Ominous Nightmares has no generated outcomes. Static closure remains separate from candidate pool membership.

**Expected unlocks.** Two ManaEngine declarations, both in the class-only Whelp envelope; 2/63 class, 2/65 non-Quest-any-class, 2/77 raw-candidate memberships. This does not review Whelp pool membership or make either manifest dependency-closed.

**Test strategy.** Independent branch expectations for both roots; target legality and branch-specific no-target behavior; Spell Damage on each damage branch; all-minions damage with Divine Shield; damaged/minimally damaged target validity; board-full summon capacity; no unselected-branch effect; clone between mode and target; stale target rejection; adapter action roundtrip and Policy parity with existing Choose One feature columns. Exercise an additional parameterized test-only declaration to prove the shared renderer has no ID-specific behavior.

**Custom/deferred outliers.** `EDR_813` Morbid Swarm stays deferred: it requires Corpse resource/session state and conditionally exposes a target branch. `Core_LOE_115` Raven Idol stays deferred because each mode enters a different dynamic Discover universe. Neither expands this contract.

**Risk/cost.** Medium correctness risk because the adapter must distinguish the mode stage from the target stage while keeping current action semantics. Estimated one shared native+binding+adapter implementation cycle; no event/death scheduler changes. Stop if correct observation/action handling requires a broad policy schema or event-order redesign.

## `weapon_required_attack_modifier_v1`

**Semantic contract.** A declared spell requiring a currently equipped friendly weapon is not a legal PLAY action without one. When cast with a weapon, add a declared Attack delta to that live weapon instance; do not change catalog metadata or durability. Weapon replacement/destruction keeps existing lifecycle behavior.

**Reviewed candidate.** `CORE_CS2_074` Deadly Poison, a 1-cost Rogue spell in the raw 77 Whelp pool and both 65/63 working envelopes.

**Rules basis.** The pinned official card snapshot text is “Give your weapon +2 Attack.” The exact +2 is a property of the card's declaration, not a special rule branch. The official Card Library exposes the identity; its script-rendered text could not be extracted in this review. The pinned card text is the exact rules string. This contract does not infer additional behavior for no-weapon play: the card requires a friendly weapon and is uncastable without one.

**Existing primitives.** Live `WeaponState`, current durability, effective spell cost/Prepare discount, generic EffectComposition and clone-by-value state.

**Required shared changes.** Add `ModifyWeaponAttack` as a typed effect targeting `FRIENDLY_WEAPON`; add a strict `requires_friendly_weapon` play-legality predicate usable by any card declaration; apply the amount to current weapon state. Expose the same legality/effect action through ManaEngine adapter. No Policy or observation schema change is needed because the weapon is already public state and play legality is represented in current legal actions.

**Dependencies.** The enchantment identity `CS2_074e` is retained in the audit ledger but the bounded ManaEngine effect is an additive live-instance stat change; no runtime token is created. No dynamic pool.

**Expected unlocks.** One Whelp class candidate root; memberships 1/63, 1/65 and 1/77. Pool membership and training remain unchanged.

**Test strategy.** No weapon: no PLAY action, including at zero cost. Equipped weapon: +2 current Attack, durability unchanged. Test a second parameterized +1 effect declaration as a renderer control. Test clone isolation; weapon attack/use and normal durability destruction; Prepare followed by Deadly Poison where legally representable; ensure the prepared zero-cost spell still requires a weapon. Adapter legal action parity and Policy roundtrip. No synthetic impossible combination is counted as real consumer evidence.

**Custom/deferred outliers.** No CUSTOM card branch. Weapon keywords, hand/deck weapon modification, weapon equip/replace, conditional weapon-dependent cards, and Battlecry-specific weapon mechanics are outside this version unless they can consume the same exact live-weapon contract without new semantics.

**Risk/cost.** Low-to-medium. One shared effect and one shared legality predicate; no class/session changes. Estimated one native/adapter implementation cycle.

## Ranking at proposal time

| Rank | Package | In-scope roots | New shared surface | Reuse | Key risk |
|---:|---|---:|---|---|---|
| 1 | `choice_mode_continuation_v1` | 2 | Typed pending mode/target flow + one effect/target | Two frontier consumers; more future Choose One cards | Public choice/action parity |
| 2 | `weapon_required_attack_modifier_v1` | 1 | Live weapon Attack delta + shared play predicate | Reusable weapon spell contract; test-only parameter variation | Instance mutation / no-weapon legality |

The second package remains a real shared capability despite one frontier root: the effect contract is amount-parameterized, the independent control declaration exercises a second amount, and no card-specific dispatch is permitted. If the control needs implementation code, reclassify the package rather than adding it.

## Completion results

Both proposals were implemented. `choice_mode_continuation_v1` added declarations for `CORE_AT_037` and `EDR_570`; `weapon_required_attack_modifier_v1` added `CORE_CS2_074` plus a non-frontier parameter-control declaration used by native tests. The two packages added 3 real frontier consumers: 2/2 declared Choose One cards and 1/1 weapon-dependent spell. No card-ID behavioral branch was added.

The Prepare interaction was not claimed as verified. ManaEngine's `PrepareCard` action is a prototype instance preparation mechanic, not the Hearthstone Prepare spell, so using it as Deadly Poison evidence would assert a different contract. The no-weapon-at-zero-cost case was tested using a negative per-instance cost delta, and the current weapon clone, Attack, durability, attack-use and destruction paths were exercised.

The next conditional second-target candidate, `CATA_554` Earthen Roar, was audited and deferred as `RULES_EVIDENCE_REQUIRED`. Its pinned text establishes a second distinct enemy-minion selection when a Dragon is held, but available primary evidence did not settle set-Health/max-Health behavior and exact resolution/death timing. No implementation was started. `CATA_528` remains deferred for start-of-turn ordering; other reviewed random/repeated/conditional damage candidates remain deferred where target snapshot, reselection, or packet-boundary rules are unresolved.
