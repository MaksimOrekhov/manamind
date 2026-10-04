# CAPABILITY PACKAGE PROPOSAL — Bookkeeper rules review

Follow-up review: [INSTANCE_COPY_V1_CONTRACT_REVIEW.md](INSTANCE_COPY_V1_CONTRACT_REVIEW.md) supplies the complete per-field policy and reachable-state audit. Its MORE_RULES_EVIDENCE_REQUIRED verdict supersedes the architectural alternatives below. No broad CardInstance redesign is currently required; exact Kindred/Explosive Runes timing remains unestablished.

package_id: previous_own_turn_minion_types_kindred_copy_v1
implementation_kind: REUSABLE_CAPABILITY (proposed)
status: BLOCKED_RULES_REVIEW
date: 2026-10-04
baseline: ManaMind 361fbd0013288de5d4106c65496ea4e2b6e2e6cf; RosettaStone f34da0d3fcb5ad312f7e2acf634d0536b044d29a
branch: codex/manaengine-first-deck
profile: standard_full_20261001_v1; frozen tricky_burn_mage

## Exact metadata and independent rules sources

The pinned collectible archive, data/cards/source_snapshots/cards_collectible_20261001_enUS.json, SHA-256 d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930, contains TLC_226 / dbfId 117535: Mage, cost 3, attack 2, health 2, Elemental, races [ELEMENTAL], Epic, collectible minion. Text: Deathrattle: Draw a spell. Kindred: Summon a copy of this. The mechanics array lists DEATHRATTLE only; this does not remove the Kindred text contract.

The [official card page](https://hearthstone.blizzard.com/en-gb/cards/117535-conjured-bookkeeper/) agrees with the pinned effect wording. Blizzard's [expansion announcement](https://hearthstone.blizzard.com/en-us/news/24217084) describes Kindred as a bonus for playing a card sharing a minion type or spell school with a card played on the preceding own turn.

Blizzard's [Developer Insights on copying](https://news.blizzard.com/en-gb/article/21965466/developer-insights-12-0-game-mechanics-update) explicitly establishes enchantment retention for play-to-play copies. Therefore a clean base summon cannot serve as the general contract for this effect. This is a general copy rule, not a Bookkeeper-specific timing specification. It does not enumerate the transfer policy of every internal counter, attack availability flag, aura contribution or pending event.

A [first-person Crater Experiment report](https://us.forums.blizzard.com/en/hearthstone/t/thornmantle-musician-and-crater-experiment-ordering/153453) describes a Kindred self-copy interacting with Thornmantle Musician. Its ordering explanation is a player's hypothesis, not an official rules specification or a captured reproducible Bookkeeper trace. It motivates a timing probe; it does not settle our scheduler contract.

## Semantic capability and dependencies

One declared consumer is in scope: TLC_226. No additional Standard roots will be implemented. Proposed generic parameters are previous-own-turn type intersection, a Kindred self-copy operation and Deathrattle draw_count=1 / filter=SPELL. An independent nonproduction control declaration must vary minion types and copy parameters without an ID behavior branch.

History records the canonical types of minions successfully played from hand. Record every applicable canonical type, not only the legacy single race field. Summon, deck recruit, generation and transform do not constitute a hand play. The handling of an ALL-type marker must be explicit before accepting such declarations; do not silently discard it or infer a single race.

Proposed rotation: after the ending player's end-turn reactions and stabilization, rotate that player's current types into previous types exactly once and clear current types, before activating the opponent. The other player's history does not rotate. New own-turn Kindred checks previous, not current types. This boundary must be tested against the reviewed supported play lifecycle before implementation is admitted.

The draw pool is the source controller's actual runtime deck filtered to spells. No external membership pool or filtering by support status. Existing draw_from_deck handles the eligible selection, empty filter without fabricated fatigue, full-hand burn and unsupported outcome invalidation. Existing activation-sorted simultaneous-death batches must remain the scheduler.

Self-copy is a dependency on the source's rules, including its Deathrattle; it creates no new card metadata ID. A copy must not recursively execute Kindred merely by being summoned. Capacity is checked after the original enters the board: starting with six minions allows the original but no copy; starting with seven makes the minion play illegal. Failed summons must not create a synthetic dead/burned entity.

## Existing primitives and concrete gaps

ManaEngine engine.cpp draw_from_deck and resolve_trigger already implement filtered Deathrattle draw. summon_fixed creates a fresh base instance with new activation and normal sickness; it cannot preserve the source's changed state. resolve_play resets minion attack/health/max_health to base metadata, queues recognized Battlecries, then queues OpponentPlaysMinion SecretWindow. There is no distinct Kindred hook or pre-summon event family.

CardInstance has flat attack/health/max_health, modifier fields, string enchantments and an untyped counters map. It does not declare which counters/modifiers are copyable versus execution bookkeeping. Blindly copying the whole struct would also duplicate entity identity, activation, links and attack/turn bookkeeping. Clearing every field would lose persistent effects. Neither is an honest universal copy contract.

Pinned RosettaStone SummonCopyTask.cpp uses game tags, internal attributes, applied enchantments and ongoing effects for board-source copies; Generic::Copy in Actions/Copy.cpp similarly distinguishes zone transitions and retains enchantments. These are reusable reference implementations, not independent evidence of Bookkeeper's Kindred timing. No equivalent typed effect lifetime/ownership contract currently exists in ManaEngine. A broad state refactor is not yet proven necessary; a narrowly bounded, fail-closed copy primitive may suffice, subject to the review below.

## Review boundary: copy state and exact timing

| Property | Established or proposed boundary | Outstanding verification |
|---|---|---|
| Card identity | Copy source identity, not a hardcoded TLC_226 ID | Source transformation before Kindred resolution |
| Enchantments | Retained for play-to-play copying under Blizzard's rule | Supported representation, expiry and source references |
| Stats and damage | Must not assume clean 2/2 when source is modified | Snapshot current attack/max health/damage at the reviewed instant |
| Counters | No blanket copy or reset contract | Per-counter lifetime and copy policy |
| Aura effects | Must not freeze/double a temporary contribution | Separate persisted modification from derived contribution, or reject unsupported state |
| Entity/activation | New entity and fresh summon activation | Exact relative board position and trigger order |
| Attack availability | A summon is not another hand play | Reset execution bookkeeping independently of retained abilities |
| Kindred timing | Distinct from merely reusing Battlecry dispatch | Before/after summon reactions and OpponentPlaysMinion SecretWindow |

Concrete probes needed to distinguish possible contracts:

1. A buffed source played with Kindred active: inspect original and copy stats/enchantments.
2. A before/after-summon modifier such as the Crater Experiment interaction: determine the snapshot boundary from a replay/Power.log or an independently reviewed rule.
3. An opposing play-minion Secret that damages/transforms the original: determine whether the copy already exists, which identity/state it has, and when deaths resolve.
4. A damaged/temporarily modified source in a generic copy control: establish damage and expiry retention separately from fresh attack/activation bookkeeping.

Do not implement a speculative ordering or clean-base substitution and then derive expected results from it. Section 1 of the task requires this audit before implementation; sections 8, 11 and 12 prohibit guessed transfer semantics and require a review stop at unresolved interactions/broad copy architecture.

## Architecture options for review

A. Bounded INSTANCE_COPY_V1 after the exact rules boundary is fixed. Explicitly enumerate retained supported fields and reset execution fields. Fail closed on unreviewed counters, enchantment lifetimes, aura/provenance or unavailable source states. This is the preferred small prototype route if independent rules probes support it. Report PARTIAL support for excluded reachable states; it is not full deck closure.

B. Design a typed persistent-modifier/counter ownership and lifetime layer first, then implement general copy. This provides a wider contract but changes core instance representation and expands the current package. Requires explicit architecture approval and measured scope; it has not been started.

CLEAN_BASE_COPY is not a fallback for general Bookkeeper semantics. A caller-authorized restricted prototype would still need explicit fail-closed bounds and could not claim full rules/admission.

## Observation/schema impact if implementation resumes

Previous and current own-turn type presence are publicly reconstructible and affect future transitions. Export compact semantic presence for BOTH players, with UNKNOWN distinct from known empty, never hidden card IDs or full event logs. Authoritative history remains inside EngineState and its deep clone. The adapter projects it into GameState.

Append reviewed finite type features and known masks; explicitly bump state encoder schema 14 to the next version and retain checkpoint incompatibility checks. Old/Rosetta observations without history must remain UNKNOWN. Regenerate canonical outputs and invalidate dependent evidence through the real observation fingerprint. No automatic status promotion or copied fingerprints. None of these changes has been made in this audit.

## Test strategy after review

Native independent expectations: previous/current/two-turn-old histories; own/opponent rotation; no types; multiple plays; dual type; summon/recruit/generate/transform negatives; clone divergence; filtered draw/no eligible/full hand/unsupported spell outcome; 0/6/7 initial board slots; fresh identities/activation/sickness and correct copy-state transfer; copy's later Deathrattle; simultaneous deaths across owners and activation order. Add a second declared control variation for reuse.

Adapter/policy tests must verify public known/unknown history, effective values and hidden-information exclusion; run full native and Python suites, pinned regeneration, source guard and both hosted Windows/Ubuntu workflows with actual test logs. Existing scoped CI is not evidence for the unimplemented package.

## Expected unlocks, custom outliers and audit outcome

Potential experimental unlock: one root TLC_226 / two frozen Mage slots, conditional on the reviewed copy contract. No promised canonical verification, dependency closure or training eligibility delta. No CUSTOM implementation or other root has been added.

Audit outcome: BLOCKED_RULES_REVIEW. Production engine, declarations, schema, evidence and registry remain unchanged. No build/test/CI result is claimed for this package; it has not been implemented. A new core architecture is not asserted to be inevitable.

Remaining wholly missing frozen Mage roots: TIME_855, TLC_226, CATA_488, CATA_484. Existing Sleet/mortality, Shatter/Secrets/Raincaller and other recorded partial boundaries still block DECK_READY. Training/search and follow-on card work remain unauthorized in this checkpoint.
