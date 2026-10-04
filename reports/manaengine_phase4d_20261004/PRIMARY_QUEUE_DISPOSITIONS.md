# Phase 4D primary queue dispositions

Baseline is the 31-card `DEFERRED_RULES_EVIDENCE` queue in the Phase 4C harvest. Fifteen roots now have task-local native + adapter/action verification in the Phase 4D package records. This does not promote canonical RosettaStone evidence.

## Remaining 16

The root text below was checked against the pinned October 1 Standard metadata and the Blizzard Card Library where its entry was available. None of the prototype's behavior is used as evidence for the rule.

| Root | Rules contract reviewed | Current disposition and exact remaining question |
|---|---|---|
| `CATA_528` Sigil of the Seas | Start of your next turn, summon a 3/3 Naga with Taunt. | `DEFERRED_ARCHITECTURE`: the prototype has no start-of-turn delayed fixed summon phase. Adding a delayed session event is outside the small existing primitive boundary. Fixed token identity `CATA_528t` is metadata-resolved; no scheduler behavior inferred. |
| `CATA_554` Earthen Roar | Set an enemy minion's Health to 1; if holding a Dragon, pick another. | `DEFERRED_ARCHITECTURE`: conditional second target requires a pending target continuation and exclusion of the first target. Current Choice continuation does not represent this. |
| `CATA_581` Decimation | Blizzard's Library says “Deal damage to all minions (Improved for each minion on the battlefield).” | `DEFERRED_RULES_EVIDENCE`: available official page omits the numeric base/upgrade amount; pinned card text supplies `$1` but does not settle whether the count includes both boards, snapshot time, or one area packet versus repeated damage. |
| `CORE_AT_037` Living Roots | Choose One: deal 2 damage; or summon two 1/1 Saplings. | `DEFERRED_ARCHITECTURE`: reviewed rules/target semantics are sufficiently established. The remaining blocker is a typed Choose One continuation that selects between distinct effect branches; the damage branch's target action must be emitted after option selection. No card-specific path is needed. |
| `CORE_CS2_074` Deadly Poison | Give your weapon +2 Attack. | `DEFERRED_ARCHITECTURE`: the remaining gap is weapon-state/castability modeling, not card-text evidence: ManaEngine has no generic current-weapon Attack modification operation and no reviewed action/resolution contract for the no-weapon state. Keep the no-weapon case explicit when that shared capability is designed. |
| `DINO_406` Fire Breath | Deal 4 damage; give your Elementals +1/+1. | `DEFERRED_RULES_EVIDENCE`: official text does not state a damage target. The exact Elemental membership snapshot/zone and whether a minion that dies to the damage receives the buff remain unverified. |
| `DINO_417` Soulrest Ceremony | Give your minions +1 Attack and Rush; they die at end of turn. | `DEFERRED_ARCHITECTURE`: needs a reviewed expiring board-wide effect plus end-of-turn death processing for the affected instances. Current timed aura path does not model “they die” as an instance-specific expiry. |
| `EDR_570` Ominous Nightmares | Choose One: deal 1 damage to all minions; or give a damaged minion +2/+2. | `DEFERRED_ARCHITECTURE`: current typed Choice continuation cannot select between two effect branches, one of which creates a later target action. Avoid representing this as a card-ID path. |
| `EDR_813` Morbid Swarm | Choose One: summon two 1/1 Ants; or spend 2 Corpses to deal 4 damage to a minion. | `DEFERRED_ARCHITECTURE`: exact Ant dependency is resolved, but this requires Death Knight Corpse resource state plus option-dependent targeting/resource payment; the prototype supports only Mage hero sessions and has no Corpse resource. |
| `FIR_909` Bursting Shot | Deal 2 damage to three random enemies. | `DEFERRED_RULES_EVIDENCE`: distinctness/with-replacement rule, candidate snapshot and fewer-than-three behavior are not established. Each packet's death/trigger boundary also needs verification before using a random sampler. |
| `FIR_910` Scorching Winds | Deal 3 damage; discard a random Fire spell to deal 3 more. | `DEFERRED_RULES_EVIDENCE`: exact first damage target is absent from the pinned text and the Blizzard entry was not retrievable in this pass; discard timing relative to the first packet and eligible hand snapshot remain unverified. Do not inherit Overheat's buff contract. |
| `FIR_923` Flames of the Firelord | Deal 4 to a random enemy minion; deal 8 instead if holding a card that costs 8+. | `DEFERRED_RULES_EVIDENCE`: resolve whether “costs 8 or more” uses current or printed hand cost and when that condition is snapshotted; also confirm random target timing against other effect changes. |
| `JAIL_307` Crowd Control | Deal 2 to all minions twice; costs 2 less if your deck has at least 25 cards. | `DEFERRED_RULES_EVIDENCE`: exact deck-size check timing and whether death/trigger processing occurs between the two area packets are unverified. Existing sequential effects are not evidence for this boundary. |
| `TIME_212` Lightning Rod | Deal 2 to a friendly minion to deal 4 to a random enemy minion. | `DEFERRED_RULES_EVIDENCE`: whether the second packet's random candidate snapshot occurs before/after first-packet damage and its death/trigger interleave are unresolved. Don't copy Sleet Storm's contract by resemblance. |
| `TLC_221` Sizzling Swarm | Deal 3 damage; summon that many 2/1 Sizzling Cinders. | `DEFERRED_ARCHITECTURE`: exact `TLC_221` generated minion dependency has a random damage Deathrattle; effect count depends on a reviewed damage result. This exceeds fixed summon and existing Deathrattle primitives. |
| `TLC_227` Lava Flow | Deal 2 to the lowest-Health enemy three times; Overload 1. | `DEFERRED_RULES_EVIDENCE`: establish per-instruction reselection, hero/minion candidate set, tie-breaking RNG, and target/death ordering. The Overload transition is available, but it does not resolve this damage contract. |

## Evidence boundaries

- `IMPLEMENTED_SCOPED_VERIFIED` in Phase 4D means a focused prototype family passed native and adapter/action tests. It is not `CURRENT VERIFIED_SCOPED` canonical evidence.
- The remaining rules-evidence cases stay deferred until their listed question is answered from rules evidence, not guessed from ManaEngine or RosettaStone implementation.
- No training, pool admission, full dependency closure or `DECK_READY` status is established by these dispositions.
