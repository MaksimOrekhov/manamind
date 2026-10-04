# CAPABILITY PACKAGE PROPOSAL — Vulcanos / Colossal

Date: 2026-10-04. Status: **BLOCKED_DESIGN_REVIEW — STOP BEFORE IMPLEMENTATION**.

## Identity and scope

- Proposed package_id: `colossal_appendages_end_turn_other_minions_v1`.
- Branch: `codex/manaengine-first-deck`.
- ManaMind HEAD at audit: `1686256493293459b6fa6f863832f887416025f7`; worktree was clean.
- Pinned RosettaStone: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
- Profile: `configs/standard_profile.json`, `standard_full_20261001_v1`.
- Candidate root: `CATA_488`. Fixed dependencies: `CATA_488t`, `CATA_488t2`.
- Latest explicit Phase 4B instruction overrides historical queues. No Whelp, Barrage, training or search work is authorized here.

## Exact metadata and provenance

| ID | Name | Cost | Stats | Type | Collectible | Rules |
|---|---|---:|---|---|---|---|
| CATA_488 | Vulcanos | 7 | 4/8 | Elemental | Yes | Colossal +2. At the end of your turn, deal 3 damage to all other minions. |
| CATA_488t | Plume of Vulcanos | 2 | 1/5 | Elemental | No | Whenever this takes damage, get a random Fire spell. It costs (3) less. |
| CATA_488t2 | Plume of Vulcanos | 2 | 1/5 | Elemental | No | Same complete effect as CATA_488t. |

Root dbfId 123665; appendage dbfIds 123666 and 128032. Root mechanics: COLOSSAL, TRIGGER_VISUAL. Both appendages: TRIGGER_VISUAL. The visual tag does not make their executable text vanilla. Full objects omit collectible on the appendages, whereas the root explicitly has collectible=true.

The complete objects and acquisition provenance are preserved in [VULCANOS_DEPENDENCY_METADATA_AUDIT.json](VULCANOS_DEPENDENCY_METADATA_AUDIT.json). Full-feed response SHA256: `e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65`. Pinned collectible archive SHA256: `d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930`. The fetched root object equals the entire pinned root object. The finite subset is audit material only, outside the adapter's loaded metadata sources. No pinned profile/feed was replaced.

The initial unqualified full-feed URL returned HTTP 403. A read with User-Agent and the recorded query URL succeeded; the SHA identifies that successful response. The subset is not a newly pinned all-card snapshot for dynamic-pool admission.

## Rules established and unknown

Primary evidence: [Blizzard 36.2.2 patch notes](https://hearthstone.blizzard.com/en-us/news/24293284/36-2-2-patch-notes), August 18, 2026, explicitly establish the current 3-damage effect and 1/5 appendages. Earlier 2-damage / 1/4 reveal discussions are obsolete for this snapshot.

[Blizzard's Sunken City launch explanation](https://news.blizzard.com/en-gb/article/23784370/voyage-to-the-sunken-city-is-now-live) establishes that appendages are summoned whenever the main body is summoned, including without a hand play. This supports both play and effect-summon entrypoints. It does not establish all position, capacity or event-order details.

Metadata establishes both exact appendage identities and their nontrivial text. Left/right naming in secondary sources is supporting evidence, not a finalized placement contract. Before implementation, root-relative insertion order, partial creation at capacity, sequencing against summon reactions and death processing still need reviewed evidence. No claim of a global scheduler requirement is made from these unknowns. Copy/transform interaction remains outside the reviewed path; do not attach appendages to every identity replacement or extend INSTANCE_COPY_V1 automatically.

The unqualified random Fire spell text does not justify a Mage-only outcome pool. All-class Standard Fire spells are an audit candidate universe, pending review of actual generation eligibility, bans, aliases and any special exclusions. No outcome distribution or complete runtime membership is certified here.

## Immediate stop-condition

**Section 17 applies: an appendage has an unsupported core mechanic required immediately.**

In the ordinary proposed root path, both healthy 1/5 appendages receive 3 damage from Vulcanos at the first own end-turn and survive at 1/2. Their text therefore requires two damage-triggered random Fire-spell generations, each with an instance cost reduction of 3. This is a direct semantic implication of the reviewed text, not an executed native scenario or captured client replay.

Current source inspection:

- `experiments/manaengine/src/engine.cpp::deal_damage` updates health, Shield/Immune prevention, Lifesteal, direct-spell totals and spell-specific reactions. It has no appendage/self-damage-triggered random spell generation hook.
- `TriggerKind` in `engine.hpp` contains Battlecry, AfterHeroAttack, EndTurn, Deathrattle and SecretWindow; no reviewed takes-damage reaction contract exists.
- `MinionDamageGenerate` is a targeted damage effect producing a declared fixed outcome. `DeathrattleGenerate` is also fixed. Neither models this reactive random generation.
- Discover and random Secret casting have bounded reviewed contracts. They are not a reviewed random Fire-spell-to-hand pool.
- `summon_fixed` and `summon_from_deck` are reusable entrypoints, but there is no Colossal definition/placement hook.
- Existing end-turn area damage targets enemy entities and the enemy hero. It cannot represent both boards excluding only the source without a new shared semantic declaration.

Diagnostic metadata scan: the pinned Standard roots include **33 collectible Fire spells**, of which **7 have entries in the experimental ability declaration map** and **26 lack entries**. This is declaration presence, not verification or full pool membership. Those 33 must not be narrowed to the 7. Includes other classes and a dual-class spell. Recursively reachable generated outcomes and session/resource requirements remain unaudited.

## Proposed reusable semantic capability

Proposed kind: REUSABLE_CAPABILITY, not implemented. A finite `colossal_appendages` declaration supplies reviewed token IDs and placement parameters; common play/summon entrypoints create independent ordinary board entities. A separate parameterized end-turn other-minion damage effect uses Effect damage with no DirectSpell attribution or Spell Damage bonus. No behavioral card-ID dispatch.

Existing primitives: deterministic RNG, fresh instance/activation assignment, board positions/capacity, typed damage and prevention, activation-sequence end-turn dispatch, batch deaths/Deathrattles, previous-own-turn type history, clone, adapter projections.

Required changes beyond those originally expected: a reviewed takes-damage event contract; random spell generation-to-hand with finite versioned pool, real eligibility, cost_delta and full-hand behavior; verification of every reachable outcome. Reaction timing must cover lethal damage, simultaneous packets, Shield/Immune, ownership, Silence, nested triggers and death phases. Existing direct-spell counters must remain independent. These are prerequisites for honest root support, not optional future extensions.

Expected unlock count: at most 1 Standard root and 2 fixed dependencies after all prerequisites. **Actual gains: 0.** Dependency closure and training eligibility gain: 0. No production consumers, shared code, CUSTOM branch or newly admitted rules evidence was added.

Custom outliers: none classified merely from unique card IDs. The uncovered behavior appears reusable but requires an independently reviewed package contract. Fire outcomes with unsupported mechanics are blockers; individual card implementation is not authorized opportunistically.

## Verification strategy if resumed

- Independent second nonproduction Colossal declaration with different root/token stats and token count.
- Reviewed exact placement, neighbors and board counts 0/4/5/6/7; no allocation/death artifacts on failed summons; all successful identities, activation order, owner/controller and sickness.
- Hand play records only root types; effect summons and appendages do not increment played history.
- Effect damage includes appendages and both sides, excludes only source, respects prevention, triggers appendage generation and preserves spell counters.
- Full exact Fire membership/selection/cost/full-hand cases; unsupported outcomes invalidate branches rather than disappearing from pools.
- Source removal, both-player Deathrattles, simultaneous deaths, timed summons and Secrets/end-turn activation ordering.
- Native, adapter/policy, complete Python, reproducible artifacts and actual hosted Windows/Ubuntu Source/ManaEngine jobs.

These are planned checks, **not PASS evidence**. No build/test/CI run was performed for this audit-only stop; historical Bookkeeper runs do not verify Vulcanos.

## Decision and bounded next step

**STOP_BEFORE_IMPLEMENTATION.** Do not deliver a vanilla appendage or a partially implemented root as completed support. Before resumption, architecture/scope review must choose whether to authorize the takes-damage/random-Fire-generation prerequisite plus its full closure, or defer Vulcanos. A standalone Colossal control prototype would not close Vulcanos and is not started under this task.

Separately: IMPLEMENTED = NO; RULES_VERIFIED = NO (metadata/partial rules audit only); DEPENDENCY_CLOSED = NO. Frozen Mage missing root declarations remain CATA_488, CATA_484 and TIME_855; other partial interaction gates remain unchanged. No DECK_READY or training claim.

Reliable observed audit timer: 2026-10-04 12:55:30 UTC to 13:03:17 UTC, **7m47s**. It measures the audit interval following the initial read, excludes previous Bookkeeper work, and is not a full native implementation throughput measurement.
