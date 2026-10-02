# CAPABILITY PACKAGE PROPOSAL

**State: COMPLETED; scoped evidence CURRENT.** Revision 3, 2026-10-02. User explicitly approved the three roots and two fixed dependencies. No deferred outliers, next package or training are authorized. See the [Completion Record](../../reports/minion_set_enchant_v1_20261002/completion.md) for measured results and limits.

## package_id

`minion_set_enchant_v1`.

Profile: `standard_full_20261001_v1`; registry: `standard_registry_20261001_v1`; pinned pool as of 2026-10-01. Candidate metadata fingerprints and the registry content hash are captured in [the source review JSON](../../reports/capability_package_candidates_20261002.json). Compare the current files before implementation; this proposal is not a replacement for current evidence.

Selection rationale and alternatives: [candidate comparison](../../reports/capability_package_candidates_20261002.md). The first PoC minimizes unresolved outcomes and action changes while serving Druid/Priest and a later DK profile. Current complete deck unlock count is UNKNOWN.

## semantic capability

Contract: `minion_set_enchant`, version 1. Proposed implementation kind: **REUSABLE_CAPABILITY** for finite minion selection + fixed enchantment/keyword application; underlying tasks remain ordinary RosettaStone primitives. This classification and contract metadata are proposed fields to implement/validate for this package, not existing registry APIs.

At SPELL/BATTLECRY effect resolution:

1. Select own board minions, own board minions excluding source, own hand minions, or a legal target minion. Selection is deterministic and ignores heroes, spells, weapons and Locations unless a separate explicitly typed effect targets a character.
2. Optionally filter board minions by a declared maximum **current** Attack. Recipient selection is fixed once before either the stats or keyword grant. See the [independent frozen expectations](minion_set_enchant_v1_expected_semantics.md), including the distinction between the rules interpretation and observed client evidence.
3. Apply an already reviewed, fixed numeric enchantment and explicit allowlisted permanent keywords to the selected set. Same selector/filter/flags/ref means identical generated task structure for every consumer.
4. Preserve controller, effect order, current/base stat separation, hand→board transfer and the engine's silence/copy/bounce semantics. Unsupported interactions block the affected evidence; no approximate substitute.

TIME_447 composes a preceding generic target-character Divine Shield effect with the hand-minion enchantment. Its character-target legality is unconditional; the minion-set operation does not become a character-set operation. This is a typed sequence of existing primitives, not a special code path for TIME_447.

Suggested finite parameters (design, not executable declaration format yet):

- `activation`: SPELL or BATTLECRY.
- `selector`: OWN_BOARD_MINIONS, OWN_BOARD_MINIONS_EXCLUDING_SOURCE, OWN_HAND_MINIONS, TARGET_MINION. Exclude arbitrary zones/expressions/callbacks.
- `max_current_attack`: optional nonnegative bounded integer, only on allowed board selectors. No tribal/history/dynamic amount predicate in v1.
- `enchantment_ref`: exact supported ENCHANTMENT dependency, fixed reviewed stats, explicit owner and fingerprint. No unknown ID may silently resolve to an empty card.
- `keywords`: finite subset reviewed for this contract (initial consumers need TAUNT and ELUSIVE); expose only values with tested lifetime/reset behavior. Independent generic character Divine Shield remains separately typed.
- Contract/package identity/version and ownership manifest fields validated together with the new schema. Do not migrate every legacy manifest as a prerequisite.

A new card with an already supported matching enchantment, selector and keywords changes declarations only. An unsupported new dependency remains a dependency blocker; adding a card-ID branch to manufacture it is not allowed. The contract is intentionally about applying reviewed fixed enchantments, not generating every possible new enchantment or interpreting card text.

## existing RosettaStone primitives

Source review, not runtime verification:

| Primitive | Reviewed behavior / limitation | Source |
|---|---|---|
| IncludeTask | MINIONS/MINIONS_NOSOURCE select own board minions; MINIONS_HAND selects only minion cards in own hand; FRIENDS includes hero and is wrong for a mass-minion buff | `Sources/Rosetta/PlayMode/Tasks/SimpleTasks/IncludeTask.cpp` |
| FilterStackTask | Filters the selected task stack through SelfCondition predicates; stack ownership/lifetime must be explicit | `Tasks/SimpleTasks/FilterStackTask.cpp` |
| SelfCondition::IsAttack | Reads current Character Attack and compares LEQ/GEQ/EQ | `Conditions/SelfCondition.cpp` |
| AddEnchantmentTask | Applies an exact named enchantment to selected entities; optional per-entity condition must not change agreed selection timing | `Tasks/SimpleTasks/AddEnchantmentTask.cpp` |
| Enchant / Effects | Fixed Attack/Health changes and removable effects; explicit Expectations required for each dependency | `Includes/Rosetta/PlayMode/Enchants/Enchant.hpp`, `Effects.hpp` |
| SetGameTagTask | Writes a specified tag to selected entities; inspect silence/reset/copy, not just successful assignment | `Tasks/SimpleTasks/SetGameTagTask.cpp` |
| Minion::Silence | Resets Taunt, Divine Shield and both spell/hero-power targeting protection tags and removes effects | `Models/Minion.cpp` |
| CardDef::Power | Existing power-task composition and engine event processing; retain them | `Includes/Rosetta/PlayMode/Cards/CardDef.hpp`, `Enchants/Power.hpp` |

Source paths in this table are relative to `vendor/RosettaStone/` and its `Sources/Rosetta/PlayMode/` subtree as indicated. Pin native source identity from the current registry before producing evidence.

`ICC_210e` has one generated owner with explicit `Effects::AttackHealthN(1)` and metadata. `ULD_191e` has registered +2 Health metadata and an Uldum definition. The latter uses `GetEnchantFromText`: its source presence/text is insufficient verification, so independently assert exact Health behavior. Preserve those owners, do not emit duplicate definitions or infer implementation kind solely from the containing filename.

## candidate cards using the same semantics

| New root ID | Parameterization / complete effect | Current registration | Review status |
|---|---|---|---|
| RLK_048 | SPELL, OWN_BOARD_MINIONS, ICC_210e, ELUSIVE | NO_DETECTED_RULE_REGISTRATION | Pinned-text/source candidate review; native verification pending |
| TLC_233 | BATTLECRY, OWN_BOARD_MINIONS_EXCLUDING_SOURCE, max_current_attack=2, ICC_210e, TAUNT | NO_DETECTED_RULE_REGISTRATION | Same; selection/interaction timing pending |
| TIME_447 | SPELL, generic target-character Divine Shield; OWN_HAND_MINIONS, ULD_191e | NO_DETECTED_RULE_REGISTRATION | Same; character target/parity pending |

Metadata hashes: see `groups.minion_set_enchant_v1.new` in the linked JSON. All three belong to the pinned collectible roots; all three are currently unsupported by the registration scan. Legality/version, rules, dependency and action gates remain independent.

Controls only: CAP_801, CORE_CS2_009, CORE_ULD_191, CORE_CFM_753. They demonstrate adjacent target/keyword/hand cases; retain current ownership and add no duplicate root definitions. Existing registration is not independent correctness evidence. The five old decklists are not the queue or a meta-frequency source.

## dependencies

- `RLK_048 → ICC_210e`.
- `TLC_233 → ICC_210e`.
- `TIME_447 → ULD_191e`.

Two unique fixed enchantment dependencies, with existing metadata/definitions. These are **proposed reviewed effect edges**, not installed canonical graph edges. Both need current independently checked dependency contracts and fingerprints. Review their loading/ownership despite their existing source registration.

No generated card identities, random/Discover outcomes, option cards or state/history-dependent card pools are required by the three complete texts. Max Attack is a deterministic recipient filter, not an outcome pool. This is an effect-scope conclusion from those texts; validate event/interaction completeness independently. The registry's empty heuristic edges do not establish closure.

Remaining blockers: selection timing, exact dependency runtime behavior, silence/copy/bounce and hand-transfer parity, Elusive action targeting, source/action evidence freshness. DK initialization/session gate separately blocks RLK_048 in a training profile. Other roots in any eventual deck still need their own complete closures.

## required engine/generator changes

1. Add a small versioned package declaration/schema and strict validator for the finite contract above. Reject unknown fields/operations, unresolved refs, unsupported selector/filter/flag combinations and duplicate root/dependency ownership. Metadata allowlists are explicit declarations, not behavioral dispatch.
2. Add one shared renderer mapping these parameters to existing Include/Filter/Enchant/SetTag tasks. Keep runtime executable rules in C++. Ensure selected recipients are used consistently by the stat and keyword effects; do not evaluate Attack again after buffing a recipient. Enforce the reviewed selection timing, including aura interactions.
3. Produce deterministic, traceable manifest/evidence ownership and register its outputs in the current regeneration/registry tooling. Consume matching contract/package/kind fields explicitly; don't claim the proposed fields are already recognized. Ensure the new generator is covered by AST guardrail and source CI.

No new engine primitive, enum, header/ABI change, hidden-information input or action type is expected. New generated C++/registration can still require CMake source discovery and a core build before bridge relinking. Keep existing CardSets and two enchantment owners intact. If a real native primitive error is found, stop expansion, record a blocker, amend this proposal and define affected consumers before fixing it.

Implementation review found an existing shared blocker: Character::TakeDamage
only consumed Divine Shield on minions. TIME_447's character contract requires
hero protection too. Correct this existing character primitive without card-ID
dispatch; cover own/enemy heroes, armor and shield consumption. No new task or
enum is needed. No other cards are being implemented. Existing minion damage
handling remains unchanged in this narrowly scoped correction.

The observation review also found missing hero Shield and minion spell/hero-power
protection flags. Add those visible instance fields in bridge/import/domain/
encoder, preserving unknown booleans with explicit known masks/ternary values.
Bump encoder schema 6 → 7; preserve and reject incompatible historical value
checkpoints. These are necessary boundaries of the two keyword contracts, not
a new card capability or an authorization to train.

First native family run found three additional shared blockers. Card targeting
omitted both Elusive protections; Entity reset retained the granted protections;
fixed Attack/Health additions could bake an external aura into stored stats.
Correct those existing primitives for the package contracts: spell/hero-power
target gating (Battlecries/attacks unchanged), reset of the two instance tags,
and additive/subtractive stat adjustments excluding external aura contributions.
Do not change SET/MUL semantics or add a new rule operation. The two attribute
headers affect many consumers: rebuild the entire configured core/test/bridge
targets and run adjacent native regressions in addition to the package family.

An intrinsic Elusive control exposed an incorrect existing CardLoader mapping
to CANT_BE_TARGETED_BY_OPPONENTS. The character-target legality contract must
also respect intrinsic protections: map the semantic ELUSIVE mechanic to both
spell/hero-power tags. No card-ID branch or new CardDef is introduced. The
existing Faerie Dragon owner is a negative targeting/observation control only;
its root evidence/admission is not promoted by this check.

**Card-ID behavioral branches required: none.** If any candidate unexpectedly needs one, classify it CUSTOM-first, record the reason and reassess the package rather than hiding the branch in validation or Python.

Evidence invalidation: new renderer/declarations/registration affect rules/engine identity and downstream package evidence under current conservative fingerprints. Produce actual family evidence after generation/build; do not copy old PASS. Scoped evidence for other consumers remains subject to its matching policy. No training profile is admitted by this change.

## expected unlock count

- Newly registerable collectible roots: **3** — RLK_048, TLC_233, TIME_447, conditional on the reviewed contract working as intended.
- Existing root controls: **4**, not new unlocks.
- Unique fixed dependencies reviewed/reused: **2**, not new root cards.
- New root consumers requiring only declaration changes after the shared renderer is fixed: **3 expected**. Record whether this is true, not just whether three C++ definitions appear.
- Potential effect closure benefit: up to three small root closures if independent dependency/rules/action checks succeed. Current complete closure/admission benefit is **UNKNOWN**. No complete deck claim; training-eligible delta is not assumed.

Estimated effort: S–M relative to the alternatives. Three shared work areas, three declarations, two independent dependency reviews, twelve scenario groups and four parity groups. Actual authoring/review/debug time, correction cycles and builds are UNKNOWN until measured. No fixed card-batch quota, deck target or deadline.

## test strategy

Before coding, write independent expected states from the reviewed rules. Expectations must not be computed by reading the generated declaration/task sequence.

Twelve native scenario groups (each can need multiple cases):

1. Board minion recipients vs source, enemy minions, heroes and Locations; empty board and shared-board positions.
2. Attack 0/2/3 boundary, plus minions with modified current Attack differing from base Attack.
3. Recipient selection timing and relevant aura interactions; require an explicit reviewed expectation before changing the engine or admitting evidence.
4. Exact +1/+1 and +2 Health deltas for both dependency contracts, including damaged recipients and enchant application/removal.
5. Taunt and Elusive lifetime, silence and multiple grants; enemy spells/hero powers vs attacks/Battlecries follow actual targeting rules.
6. TIME_447 friendly/enemy minion and hero targets, invalid/unavailable targets, and hand buff to the controller's hand only.
7. Hand minions vs hand spells/weapons; hand→board transfer retains current stats and preserves base metadata.
8. Silence removes applicable stats/flags and preserves unrelated current/base state according to engine rules.
9. Copy, bounce and subsequent replay with independently expected enchant lifetime; no stale task-stack recipients.
10. Repeated/duplicated buffs and source exclusion; threshold selection must not be accidentally reapplied after stats change.
11. The four registered controls with independent expected target/hand/keyword behavior, without transferring their source ownership or auto-upgrading evidence.
12. A second independent declaration/control variation using the same renderer without code changes; clone/task execution isolation and a nonmatching parameter negative case.

Source checks: schema rejects unknown op/fields/flags, noninteger/out-of-range threshold, illegal target combinations, missing enchantment metadata/rules/owner, unsupported nested behavior and duplicate IDs. AST guard must reject a new behavioral ID branch or require honest CUSTOM routing. Deterministic regeneration/ownership is necessary but not sufficient rules evidence.

Four bridge/import parity groups:

1. Actual legal target enumeration/application for TIME_447 (including heroes/enemy characters) and Elusive protection; reject stale/illegal handles.
2. Current hand→board Attack/Health and keyword observations agree with native state/import encoding, without replacing base metadata.
3. Ordered hand, minion/Location board positions, missing-value masks and visibility boundaries remain unchanged.
4. Class setup/loading identity: Druid/Priest scenarios in intended bridge; DK effect native evidence kept separate from missing DK session setup. No claim of a full session/match gate from an opening smoke.

Use one coherent generation/build/family-check cycle, not a rebuild per root. Build the core before bridge relinking, check loaded module identity, record scoped native/action/observation/dependency evidence and regenerate registry. Use new smoke output paths and preserve prior evidence. Broad deck matches/training require separate scope/authorization and are not part of this PoC.

## custom outliers

No expected CUSTOM behavior among the three selected consumers. Deferred: RLK_958 (tribal/dual-type matching), CORE_BOT_576 (Combo), CORE_UNG_952/TLC_477 (attached Deathrattle/outcomes), CATA_138 (dynamic buff amount). They remain unimplemented in this task. Prefer separate reusable contracts when coherent; any proposed ID-based behavior is CUSTOM-first and requires explicit ownership. No generic op will be introduced just to relocate one unique implementation.

## Completion record

| Measurement | Forecast / baseline | Actual |
|---|---|---|
| New root registrations | 3 expected | 3 |
| New declarations without per-card generator/native changes | 3 expected | 3; shared renderer has no identity input or findings |
| New CUSTOM consumers | 0 expected | 0; deferred outliers untouched |
| Fixed dependency contracts | 2 to verify; existing owners | 2 CURRENT scoped contracts; no duplicate owners |
| Complete closures / eligible roots / closed decks | UNKNOWN; canonical profile currently has none | +3 reviewed effect closures; eligible roots/decks remain 0 |
| Shared changes | 3 work areas; no expected new primitive/ABI | 84-line renderer + 142-line driver/schema; existing shared primitive and visible observation fixes; no new task/enum |
| Authoring / review / debugging / build time | UNKNOWN; log separately | 52m09s wall clock through final checks; separate active effort was not instrumented; see record |
| Correction cycles / builds | UNKNOWN | 4 failing-execution correction rounds; 7 configured build invocations (1 failed, 6 passed, including 1 no-op) |

All three approved consumers and two dependency contracts are delivered with
independent expectations, family/boundary tests and explicit evidence. Root
registration, reviewed effect closure and profile admission remain distinct.
No next package or training is started by completion.
