# ManaEngine Phase 4F completion report

## Scope and result

- Branch baseline: `codex/manaengine-first-deck` at `a31fe5612b72c7e190dcbd3c950cd15aac6405bf`.
- Frozen profile: `standard_full_20261001_v1`.
- Active elapsed time: approximately 45 minutes, measured from creation of the Phase 4F ledger/proposal artifacts through final local verification; no user wait is included.
- Implemented packages: `choice_mode_continuation_v1` and `weapon_required_attack_modifier_v1`.
- New frontier roots declared: 3 total; 2/2 reviewed Choose One consumers and 1/1 weapon-required spell. All 3 remain canonically rules-blocked because canonical Rosetta evidence was not changed.
- Additional static dependency metadata: `AT_037t` Sapling, one token dependency. This does not make the Whelp dependency graph closed.

## Package records

### `choice_mode_continuation_v1`

- Contract: typed mode choice, then at most one existing bounded effect step; a mode may create one typed target continuation. Only the selected mode resolves. Target legality is recomputed at application and stale selections are rejected. Clone copies pending choice state.
- Consumers: `CORE_AT_037` Living Roots and `EDR_570` Ominous Nightmares, both declaration-only.
- Shared additions: `choose_one_a`/`choose_one_b` declarations; two typed continuation states; `BUFF_MINION` and `EXPLICIT_DAMAGED_MINION`; action transport through existing Choose One Policy feature columns.
- Tests: branch isolation, target legality changes, unavailable target mode, cloned continuation, Sapling summon, Spell Damage on both damage modes, per-minion Divine Shield handling, adapter action encoding and Policy feature columns.
- Unsupported boundary: two one-step branches only, no arbitrary script or multi-step branch language. No Discover, dynamic pool, event ordering, or observation schema change.
- Frontier leverage: 2 Whelp candidate roots (2/77 raw, 2/65 non-Quest any-class, 2/63 class-only); 0 Fire roots.

### `weapon_required_attack_modifier_v1`

- Contract: a declared spell with `requires_friendly_weapon` is not playable without a live friendly weapon; its typed effect adds positive Attack to that weapon instance. Durability and catalog metadata are unchanged.
- Consumer: `CORE_CS2_074` Deadly Poison, declaration-only. A separately parameterized +1 control declaration verifies reuse without generator changes.
- Shared additions: `MODIFY_WEAPON_ATTACK`, `FRIENDLY_WEAPON`, and the generic play-legality predicate.
- Tests: no weapon at zero effective cost; current weapon mutation; cloned branch; hero Attack; durability unchanged on cast and decremented on attack; normal weapon destruction; adapter action filtering. Prepare was not used as evidence because ManaEngine's existing `PrepareCard` is a different prototype mechanic from Hearthstone's Prepare spell.
- Unsupported boundary: current equipped weapon only; no hand/deck weapon edits, weapon creation/replacement semantics, or card-ID behavior.
- Frontier leverage: 1 Whelp candidate root (1/77 raw, 1/65 non-Quest any-class, 1/63 class-only); 0 Fire roots.

## Frontier counts

Classification order is independent of pool membership, dependency closure and training admission. “Implemented” here means a ManaEngine declaration exists; it does not mean canonical rules evidence is current.

| Scope | Point | Verified scoped | Implemented, rules blocked | Rules evidence required | Bounded capability missing | Major architecture missing | Dependency blocked |
|---|---|---:|---:|---:|---:|---:|---:|
| Unique roots (105) | Before | 0 | 28 | 8 | 60 | 5 | 4 |
| Unique roots (105) | After | 0 | 31 | 9 | 57 | 4 | 4 |
| Fire (33) | Before/after | 0 | 14 | 7 | 10 | 1 | 1 |
| Whelp raw (77) | Before | 0 | 17 | 1 | 52 | 4 | 3 |
| Whelp raw (77) | After | 0 | 20 | 2 | 49 | 3 | 3 |
| Whelp non-Quest any-class (65) | Before | 0 | 17 | 1 | 40 | 4 | 3 |
| Whelp non-Quest any-class (65) | After | 0 | 20 | 2 | 37 | 3 | 3 |
| Whelp class-only (63) | Before | 0 | 17 | 1 | 38 | 4 | 3 |
| Whelp class-only (63) | After | 0 | 20 | 2 | 35 | 3 | 3 |

The four frozen manifests retain counts 33/77/65/63, `CANDIDATE` membership and `OPEN` dependency closure. Their status and membership were not promoted. The ledger generator validates manifest count and ID uniqueness and emits reproducible pool membership digests.

## Deferred frontier

- **RULES_EVIDENCE_REQUIRED:** `CATA_554` (set-Health and exact resolution/death boundary), `CATA_581` (improved amount and area snapshot), `DINO_406` (Elemental eligibility/snapshot), `FIR_909` (distinct random targets and packet timing), `FIR_910` (target/discard/follow-up ordering), `FIR_923` (held-card cost semantics), `JAIL_307` (deck-size snapshot and repeated damage boundary), `TIME_212` (random target timing), `TLC_227` (lowest-Health ties/reselection).
- **MAJOR_ARCHITECTURE:** `CATA_528` (start-of-turn effect ordering), `DINO_417` (instance-specific expiring destruction), `EDR_813` (Corpse/session state), `TLC_221` (deathrattle random damage outcome driving generated result count).
- **DEPENDENCY:** `CORE_CS2_004`, `CORE_WON_337`, `Core_LOE_115`, `TIME_447` remain blocked by their current dependency audit. No pool was shortened to avoid unsupported outcomes.

## Verification and invariants

- Native ManaEngine suite: **51 scenario groups, 1,494 assertions passed**.
- Full Python suite: **92 passed**.
- Adapter/pipeline/Policy selection: **60 passed**.
- Ruff: passed for `src`, `tests`, `scripts`, and `experiments/manaengine`.
- Generated-artifact check: passed; 36 pinned outputs reproduced.
- Generic generator branch/identity guard: passed (201 reviewed AST exceptions; CUSTOM ownership checked); **0 new card-ID behavior branches**.
- Pool ledger check: passed for 105 unique roots and all four unchanged manifest sizes; generated ledger reproduces.
- `git diff --check`: passed.
- Hosted Source CI and ManaEngine Windows/Ubuntu jobs: pending push; final report will be updated with their run result.

## Evidence and admission boundaries

- Observation schema and Policy feature schema were not changed. The existing Choose One action columns are reused; `choose_one` is added to the native semantic action transport only.
- Evidence constraints and canonical Standard evidence were not changed. Registry outputs reproduced without a diff.
- All four Fire/Whelp pool manifests remain candidate/open. Training eligibility remains **false**.
- Current verdict before hosted CI: `FRONTIER_COVERAGE_EXPANDED`.
