# CAPABILITY PACKAGE PROPOSAL — `held_card_gate_fixed_battlecry_v1`

Proposal revision: 2026-10-02, based on RosettaStone commit `15d854c22995f0723e065558ae8248696c911ca2` and pre-package source-tree SHA-256 `4e0beda221b92dc9967704fab797e1b331580753d396b1aeae56cf10c21435b1`. Completed package source-tree SHA-256: `093e2e94aa8ddcbb0f12ca15b1c2a026832c7d9806378e3d28153e90be90a6cd`.

Pinned inputs: profile `standard_full_20261001_v1`; registry `standard_registry_20261001_v1`, regenerated at the above source identity. All five reviewed roots are currently `NO_DETECTED_RULE_REGISTRATION` / `UNKNOWN`.

## package_id

`held_card_gate_fixed_battlecry_v1`.

## semantic capability

Classification: `REUSABLE_CAPABILITY`, version 1. A minion Battlecry evaluates one declarative predicate over the controller's **current hand** when the Battlecry resolves, after the played source has left hand. When true, it executes a fixed, ordered effect list. A separately declared optional-target mode exposes legal character targets at play time only while the same hand predicate is true. A false predicate suppresses both target offers and the gated effect; the minion remains playable without a target.

Supported hand predicates are deliberately finite: `MINION_HAS_RACE`, `SPELL_HAS_SCHOOL`, and `SPELL_CURRENT_COST_AT_LEAST`. The cost predicate uses effective current `GetCost()`, including cost modifiers. `MINION_HAS_RACE` matches any race in the card's `races` metadata, including a secondary race and `Race::ALL`.

Supported fixed effects are `REFRESH_MANA(amount)`, `ADD_SELF_ENCHANT(ref)`, `SET_SELF_TAG(tag,value)`, and `DAMAGE_TARGET(amount)`. No random selection, history, conditional nesting, generated outcomes, or opponent-hidden information is part of this package.

## existing RosettaStone primitives

- `ConditionTask` / `FlagTask` provide condition-gated task sequencing (`Sources/Rosetta/PlayMode/Tasks/SimpleTasks/ConditionTask.cpp`, `FlagTask.cpp`).
- `SelfCondition::IsHoldingRace` and `SelfCondition::IsShadowSpell` exist, but neither currently expresses the full reviewed contract. `IsHoldingRace` compares one primary `GetRace()`; `CardLoader` currently drops `races[1]`.
- `SelfCondition::Has5MoreCostSpellInHand` uses current `Playable::GetCost()` but hard-codes 5. Replace this with a parameterized minimum-cost predicate while preserving current-cost semantics.
- `RefreshManaTask`, `AddEnchantmentTask`, `SetGameTagTask` and `DamageTask` implement the in-scope effects.
- Existing `PlayReq::REQ_TARGET_IF_AVAILABLE_AND_DRAGON_IN_HAND` and `TargetingPredicates::DragonInHand()` establish optional target availability. `BRM_034` is the existing native control for a target-gated Dragon Battlecry; its predicate is specific and must not be copied as the new cost-gate implementation.
- `BRM_033` is an existing non-Standard control for held-Dragon +1/+1. Its `BRM_033e` dependency is an exact reusable +1/+1 enchantment contract.

## candidate cards using the same semantics

Pinned fingerprints and base fields come from `vendor/RosettaStone/Resources/cards.standard_current.json` and the canonical registry.

| Root ID | Reviewed predicate | Fixed outcome | Target mode | Decision |
|---|---|---|---|---|
| `CATA_111` — Darkscale Broodmother | held minion has Dragon race | refresh 2 mana | none | in scope; source itself leaves hand before check |
| `TIME_062` — Chronicle Keeper | held minion has Dragon race | self Taunt + Divine Shield | none | in scope |
| `CORE_RLK_814` — Crystalsmith Cultist | held spell has Shadow school | add `BRM_033e` (+1/+1) | none | in scope; exact existing enchantment dependency |
| `FIR_961` — Ashleaf Pixie | held spell current cost >= 5 | self Divine Shield + Lifesteal | none | in scope |
| `EDR_472` — Weaver of the Cycle | held spell current cost >= 5 | deal 3 damage | optional character target, available only while predicate is true | in scope; target-arrow metadata plus the `BRM_034` control establish targeted optional-target semantics |

These five share the same event timing, controller/hand scope, pure predicate semantics and gate-to-fixed-effects ordering. Differences are declarative condition and effect parameters. No card ID is required by the proposed renderer.

## dual-race semantics review

The pinned Standard source contains 56 dual-race roots; seven have Dragon as their secondary race: `DINO_401`, `EDR_818`, `FIR_956`, `TIME_713`, `TLC_243`, `TLC_482`, `TLC_888`. `CardLoader.cpp` reads only `race`, and current `SelfCondition::IsHoldingRace` performs exact equality on `GetRace()`, so these cards do not satisfy a Dragon-in-hand gate today. This is a real shared-engine gap, not a reason to special-case a consumer.

The package will preserve primary `CARDRACE`, load the optional second entry from `races` into an appended internal tag, expose a shared `Card::HasRace` predicate, and use it for held-race and character race checks. `Race::ALL` remains a match for any requested tribe. Source data currently has at most two entries per card. The change will have native tests for primary Dragon, secondary Dragon, non-Dragon, `Race::ALL`, and a non-minion with incidental race metadata.

## conditional target legality review

`EDR_472` includes `targetingArrowText: "Deal 3 damage."`; it is target damage despite the shortened rules sentence. Legacy `BRM_034` uses `REQ_TARGET_IF_AVAILABLE_AND_DRAGON_IN_HAND`, which makes target selection optional and hides target choices when its hand condition is false. The new contract will add a parameterized optional-target availability requirement for a spell-in-hand current-cost threshold, backed by the same predicate helper used by Battlecry resolution.

Expected action semantics:

- predicate false: no target handles are enumerated; playing `EDR_472` without a target is legal; its Battlecry deals no damage;
- predicate true and legal characters exist: those characters are offered and a selected target takes exactly 3 damage;
- the broad character target set always includes the SELF hero in this engine, so an “all characters illegal” state is not reachable for this contract without adding another target restriction. The shared requirement remains optional and uses the engine's existing no-target fallback if a future target filter produces an empty set;
- cost-reduced spells below threshold do not enable the target or effect; cost-increased spells at/above threshold do.

## dependencies

- `BRM_033e`, reviewed fixed +1/+1 enchantment used by `CORE_RLK_814`; already present and implemented in RosettaStone.
- Root base metadata and race-list metadata from the pinned Standard catalog for the five consumers and dual-race regression controls. These are not generated outcome pools.
- No random/Discover pools. Full Standard training remains blocked by unrelated root/dependency/action/session gates; this package does not imply training eligibility.

## required engine/generator changes

- Strict declaration schema and Python validation for the finite predicate/effect set, allowlisted tags and race/school symbols, nonnegative bounded values, exact consumer metadata fingerprints, and optional target contract.
- One renderer emits CardDefs using `ConditionTask` / `FlagTask` and existing Tasks. It must reject unknown combinations and duplicate ownership.
- Add shared minimum-current-cost spell predicate; use the same helper for Battlecry evaluation and target availability.
- Correct dual-race metadata loading and shared race membership as described above.
- Add one appended internal `GameTag` for the secondary race to preserve existing tag numeric identities.
- No card-ID behavioral branches. Card IDs may appear only in reviewed declaration/metadata ownership checks.

## expected unlock count

- Five unique Standard roots become registerable: `CATA_111`, `TIME_062`, `CORE_RLK_814`, `FIR_961`, `EDR_472`.
- One existing known dependency: `BRM_033e`; no new generated pool/outcome IDs.
- Forecast: five declarations, all declaration-only after shared implementation; zero training-eligible roots claimed. Exact reviewed closure count is to be recorded after family tests and registry regeneration.

## test strategy

- Independent native family scenarios for each consumer, with true and false predicate controls, correct Battlecry/source movement timing, effect order, self/target ownership and negative cases.
- Dual-race race-membership scenarios covering a Standard minion whose primary race is not Dragon but whose secondary race is Dragon, plus `Race::ALL` and false controls.
- Current-cost boundary scenarios below/equal/above threshold after cost modification.
- `EDR_472` legal-action/target enumeration: false gate, true gate with friendly minion/hero and enemy minion/hero; no legal target; untouchable, Stealth and Immune exclusions; action handle application/parity through the bridge.
- Existing controls `BRM_033` / `BRM_034` stay regression cases. Full RosettaStone UnitTests and the known Fandral baseline test name are recorded before and after; any additional native failure blocks completion.
- Run declaration validator, AST identity guard, generated ownership/regeneration, scoped bridge/import parity, evidence producer and canonical registry/report regeneration. Training is not run.

## custom outliers

- `FIR_901`, `FIR_922`, `FIR_956`: hold a minion with Dark Gift; distinct predicate. `FIR_956` also has secondary Dragon race, but remains deferred from implementation. It may be used only as a held-card race test if its metadata is loaded without claiming its rules support.
- `TIME_213`: history-sensitive “while holding” condition plus draw; different timing and effect contract.
- `CORE_KAR_062`: Dragon-gated Discover with dynamic Dragon pool; pool closure and random outcome semantics are outside scope.

No candidate among the five reviewed roots is classified CUSTOM. The listed outliers remain in the registry/queue and are not implemented by this package.

## Completion record

- **Result:** implemented `held_card_gate_fixed_battlecry_v1` as `REUSABLE_CAPABILITY`; no consumer ID dispatch in renderer/generator; AST guard passes with only metadata/dependency validation allowlists reviewed.
- **Reviewed consumers:** 5/5 declaration-only (`CATA_111`, `TIME_062`, `CORE_RLK_814`, `FIR_961`, `EDR_472`). CUSTOM outliers: 0 in this package. Deferred queue remains `FIR_901`, `FIR_922`, `FIR_956`, `TIME_213`, `CORE_KAR_062`.
- **Shared work (separate from declarations):** one 131-line Python semantic renderer plus 43-line generator entry point; one 61-line C++ `HandPredicates` helper; shared engine changes for secondary-race loading/membership, parameterized current-cost-in-hand condition, and optional cost-gated target availability (82 inserted / 25 replaced lines across existing Rosetta files); 74-line generated shared CardDef renderer output. Bridge diagnostics add 51 lines and test fixtures add 81 lines. The five declarations contain only semantic predicates/effects and pinned metadata fingerprints.
- **Family verification:** 4 native family cases, 37/37 assertions passed. Coverage includes source leaving hand, false/true Dragon gate, secondary Dragon race, Shadow school, current cost 4/5, self effects, targetable heroes/minions, Stealth filtering, optional play without a target when the predicate is false, and target damage.
- **Bridge/parity:** `EDR_472` at held spell current cost 4 exposes 0 native targets and 0 target actions; at cost 5 exposes 4 target handles, with `Card::GetValidPlayTargets` exactly matching bridge legal-action targets.
- **Full native regression:** 267 cases; 266 pass / 1 fail; 8,072/8,074 assertions pass. The only failure is the pre-existing baseline case exactly named `[Druid : Minion] - CORE_OG_044 : Fandral Staghelmh`; no new native failures.
- **Registry delta:** generated roots 179 → 184 (+5); text-bearing roots without detected registration 839 → 834 (-5); current scoped evidence +5. The dependency graph adds one known non-root node (191 → 192) and one reviewed edge, `CORE_RLK_814 → BRM_033e`; the other four roots add no dependency. All five roots remain training-blocked by full-profile gates.
- **Revisions and execution:** engine base commit `15d854c22995f0723e065558ae8248696c911ca2`; completed source-tree SHA-256 `093e2e94aa8ddcbb0f12ca15b1c2a026832c7d9806378e3d28153e90be90a6cd`; evidence execution identity is stored in `held_card_gate_fixed_battlecry.evidence.json`.
- **Correction/build accounting:** 4 corrective loops (VS developer environment for compiler, native fixture include/setup, independent stat expectations, bridge fixture mana setup/target-state expectation); 5 successful complete native build-identity runs, 2 full native-suite runs, and final scoped family/bridge evidence pass. Elapsed implementation and verification time was approximately 30 minutes, rounded from the proposal file creation to final native regression.
- **Other checks:** 33 pinned generated outputs reproduced and generated ownership is unique; generator identity guard passes; targeted Ruff passes. A broad pytest attempt reported 63 passed and 5 setup errors because the environment denied access to its default Windows pytest temporary directory (`WinError 5`). The training-named test errored during fixture setup before its test body ran; no model training was run.
- **Training:** not run. No training eligibility is claimed.
