# Completion record — scoped Conjured Bookkeeper

package_id: previous_own_turn_minion_types_kindred_copy_v1
baseline: ManaMind 361fbd0013288de5d4106c65496ea4e2b6e2e6cf; RosettaStone f34da0d3fcb5ad312f7e2acf634d0536b044d29a (unchanged)
implementation_kind: REUSABLE_CAPABILITY
rules_review_status: RULES_REVIEWED_FROM_PHASE_MODEL
support_scope: PARTIAL / experimental ManaEngine; no training admission
hosted_ci_status: PASS on implementation commit a6efe65a93b5df9d6d28308cbbff09574d588ece; actual jobs/logs in BOOKKEEPER_CI_EVIDENCE.json

## Reviewed contract and consumers

TLC_226 is the pinned 3-mana 2/2 Mage Elemental with Deathrattle draw a spell and Kindred summon a copy. The user's explicit phase-model decision resolves the previously blocked Runes edge: original enters play -> on-play Kindred -> copy summon -> modeled consequences -> After Play Secret targeting the ORIGINAL entity -> existing stabilization/deaths/Deathrattles. No Bookkeeper-specific Power.log/replay was captured; this is not DIRECT_REPLAY_VERIFIED.

One delivered Standard root is declaration-only. TEST_KINDRED_COPY independently varies type (BEAST), stats (3/4) and source identity inside the native fixture catalog; it executes the same shared contract with no code change. No production card-ID behavior branch, CLEAN_BASE_COPY, blanket CardInstance copy or CUSTOM consumer was added. Vulcanos, Whelp and Barrage remain unimplemented.

History uses canonical sorted unique semantic type sets per player: current_turn_minion_types_played and previous_turn_minion_types_played. Hand plays record every canonical type, including dual types; ALL expands to the finite reviewed set. Other zone movements do not record plays. Only the ending player's history rotates after its end-turn reactions/stabilization. Deep clone owns independent state. Both sides export public presence without card/event logs, entity IDs, deck order or RNG.

Copy fields follow INSTANCE_COPY_V1_CONTRACT_REVIEW.md. Pre-hand guard runs before normalization; live-source guard runs again at snapshot. New handles/activation, explicitly transferred identity/stats, recomputed owner/controller/zone/position/provenance, reset attack bookkeeping, guarded defaults for all unreviewed members. The source must be rightmost and unchanged, fully healthy, same owner/controller, without unsupported modifiers/counters/enchantments/Freeze/keywords/links/Prepare/aura ownership. Failed guards invalidate the branch. Full capacity does not allocate a phantom copy. The copied minion is not played and does not recursively activate Kindred; its own Deathrattle uses actual runtime deck spell filtering.

## Actual verification

All commands run from the managed manaengine-first-deck worktree. Native Debug core and Python extension rebuilt together in %TEMP%/ManaEngineCorrectnessBuild using MSVC/VsDevCmd + CMake/Ninja. Adapter loads that build using MANAMIND_MANAENGINE_BUILD.

- Final native run: **33 scenario groups / 653 assertions PASS**, up from 32 / 601: one group and 52 assertions gained. Existing native regressions are included; no new failure remains.
- Final adapter/policy/pipeline command: **45 passed**, up from 43. Real declarations/actions, original-versus-copy execution identities, Runes, clone parity, public history/known masks, encoder schema and action encoding verified.
- Full Python suite: **90 passed**, up from 88. New source-suite history tests cover immutable canonical sets, serialization roundtrip, unknown versus known-empty masks, rejected identities/types and both player projections.
- Pinned regeneration: first run explicitly detected the two changed canonical outputs; second run **36 pinned outputs reproduced**. No bypass, manual fingerprint or native evidence promotion.
- Generic identity guard: **PASS / 201 existing reviewed exceptions**. Ruff and git diff --check pass.

Family cases include previous/current/two-turn-old/no matching type; dual types; clone divergence; summon/transform negatives; 0/6/7 board occupancy and no phantom entity; independent declaration reuse; original Runes death/draw, copy's eventual death/draw; guarded modifier/keyword/link state families; damaged live snapshot; empty filtered deck without fatigue, full-hand burn and unsupported spell staying eligible; simultaneous deaths drawing for the correct controllers. Exact trace assertion places copy creation before Runes. All expected results are reviewed scenario expectations, not generated from declaration text.

## Schema, canonical freshness and deltas

State schema **14 -> 15**. Global feature count **54 -> 106**: two periods x twelve types plus two known masks, for both players. Old/Rosetta/imported states lacking the fields remain UNKNOWN, not empty. Existing checkpoint schema rejection remains active; no old-feature reinterpretation.

Actual observation fingerprint changes from a54cee582bc4da06e8b50d531f5edf4af775f0f542b4a02ac60c5b40c992e5e9 to 988407de57de0fa2d89edb1e5fc18afa8f99da15a866f174b9ef82a3fe5e0645. Regenerated canonical registry and summary record it. Baseline already has **0 current verified / 27 historical scoped roots STALE**; those counts remain **0 / 27**. Thus no newly current root can be claimed as preserved or recertified; no manual statuses changed. Canonical Rosetta registration/rules/closure deltas are zero. ManaEngine evidence is separate.

Experimental implementation delta: one PARTIAL root / two frozen Mage slots, one shared history capability and one bounded copy capability, existing draw reused. No fully closed root/deck/training eligibility is claimed. Frozen Mage remains 17 roots / 30 slots, not DECK_READY. Wholly missing roots now TIME_855, CATA_488, CATA_484 (five slots); TLC_226 still has reachable Whelp-generated modifier bounds, and existing Sleet/Shatter/Secrets/Raincaller/pool limitations remain.

## Effort and correction cycles

Shared changes: engine.hpp, engine.cpp, python_bindings.cpp, adapter metadata mapping and strict copy-contract declaration field; GameState/serialization/encoder plus affected tests and documentation. Three local incremental build attempts: first failed on a missing played_entity declaration, corrected before passing native; second passed 650 assertions; third passed 653 after consumer edge checks. No clean build.

Three correction cycles: compile handle declaration; adapter fixture used a nonexistent domain entity_id and was corrected to inspect native execution handles; an existing source test expected schema 14 and was updated to the explicit schema 15. Final runs pass. No change to independently reviewed expected rules was made to make a test pass.

Reliable timer window starts **2026-10-04 12:30:25 UTC**, after initial implementation edits, and ends at the hosted-evidence capture **12:47:51 UTC**: **17m26s observed elapsed**, a lower bound, not total active package authoring time. It includes hosted waiting after the 12:44 push; separate exact active duration was not instrumented. Do not infer full active duration from this partial window. Builds/test outputs/logs remain in fresh temporary paths; historical datasets/checkpoints were untouched.

Source run 37203098169: Windows job 111438621258 / Ubuntu 111438621366 both success, each actually ran 90 Python tests and reproduced 36 outputs. ManaEngine run 37203098157: Ubuntu 111438621133 / Windows 111438621276 both success, each actually ran CTest and 45 adapter/policy tests. Captured log excerpts, source hashes and local loaded-module hash are in BOOKKEEPER_CI_EVIDENCE.json. No job conclusion was inferred from local runs.

## Stop boundary

After actual Windows/Ubuntu Source and ManaEngine CI success, record logs/identities, push the evidence checkpoint and STOP. Whelp-generated hand buffs remain fail-closed, not supported; no training/search or next card follows this package.
