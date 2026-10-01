# Standard filtered-draw source audit

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Registry: `standard_registry_20261001_v1`  
Purpose: identify a safe next Standard capability package after the `DrawTask` source review.

## Findings

`DrawTask` is only the unfiltered draw primitive. It repeatedly calls `Generic::Draw(player, nullptr)`, so the engine takes the top card and runs the normal draw-trigger path. Empty-deck fatigue, hand overflow, card-draw triggers, after-draw triggers and topdeck tasks are handled by `Generic::Draw` and its callers.

The engine already has separate filtered-draw tasks:

| Primitive | Implemented selectors | Current Standard examples without detected registration |
|---|---|---|
| `DrawMinionTask` | minion; lowest/highest current cost; Deathrattle | `EDR_485` adds a minimum-cost threshold and is not an exact match |
| `DrawSpellTask` | spell; spell school; highest current cost | `FIR_929` Fire spell, `RLK_511` Frost spell, `TLC_223` Fire spell plus Kindred outcome |
| `DrawRaceMinionTask` | minion race, including `Race::ALL` | `EDR_226` Beast; `EDR_572` two Dragons plus cost reduction |
| `DrawWeaponTask` | weapon | no immediate simple candidate selected in this review |

The inventory scanner found no focused UnitTests for these four filtered-draw tasks; the only pre-existing task-specific draw test file covered ordinary `DrawTask`. Source inspection found unsafe amount handling in the filtered tasks: several loops indexed the selected-card vector up to the requested amount without first limiting by the number of matching cards. `DrawMinionTask` could additionally empty its candidate vector after the Deathrattle filter without rechecking it. These paths have now been bounded by the eligible candidate count; the Deathrattle-filtered empty case returns `STOP` before indexing.

Filtered tasks pass a concrete `cardToDraw` to `Generic::Draw`. Previously, `Generic::Draw` gated both `DRAW_CARD` and `AFTER_DRAW_CARD` callbacks on `cardToDraw == nullptr`, so selected draws skipped listeners. The gate is removed: a card drawn from the deck triggers draw listeners whether it was the top card or selected by a filter. An independent Chromaggus scenario now confirms the `DRAW_CARD` listener fires on `DrawSpellTask`; the separate `AFTER_DRAW_CARD` listener path still needs its own focused scenario.

## Candidate decision

The first proposed eight-card `DrawTask` group was not a coherent implementation package: its cards add unrelated history, condition, temporary-card, and Imbue behavior. `CAP_003` has since been completed in its own after-attack/draw pilot.

The selected card package is the exact school-filtered Deathrattle draw subset: `FIR_929` (one Fire spell) and `RLK_511` (one Frost spell). The generated declarations use the existing `DrawSpellTask(SpellSchool, amount)` contract. `TLC_223` remains excluded because Kindred adds another outcome; `EDR_226` and `EDR_572` remain excluded because they use different race filters and additional behavior. This package verifies only the spell-school selector and one-card Deathrattle activation, not exact deck-pool membership or dependency closure.

## Work and verification

- Added `FilteredDrawTaskTests.cpp`: 6 focused cases and 21 assertions pass, including minion/spell/race/weapon requests larger than their matching subset, an empty Deathrattle subset, and the Chromaggus filtered-draw trigger interaction.
- Rebuilt `UnitTests.exe` and `RosettaStone.lib` in the existing VS2022 x64 Debug configuration. The three fingerprinted package verifiers passed after the library change: after-attack/draw (3 cases, 25 assertions plus three bridge smokes), repeated-trigger draw (4 cases, 34 assertions; Death Knight setup remains blocked), and Core alias (7 cases, 288 assertions plus bridge smoke).
- Added the allowlisted declaration and deterministic generator in `integrations/rosettastone/card_rules/filtered_school_draw.v1.json` and `scripts/generate_filtered_school_draw.py`; generated registrations are tracked in the package manifest and ordinary C++ CardDefs.
- Added `ManaMindFilteredSchoolDrawTests.cpp`: 3 independent native scenarios and 27 assertions pass (Fire match, Frost match, and empty eligible school pool). The fingerprinted verifier confirms FIR_929 deck/session/visible-hand/legal-action smoke. RLK_511 passes Standard deck legality and native scenario; bridge session creation remains blocked by the known Death Knight setup gap.
- Both roots now have current `VERIFIED_SCOPED` evidence. At completion of this draw package, before the later five-alias batch, the registry reported 167 direct registrations, 33 generated registrations, 982 text-bearing roots without detected registrations, 9 current scoped verifications, 105 known non-root nodes, 300 heuristic pool signals, zero complete closures, and zero training-eligible roots. The live registry is regenerated after each later package.
- Re-running the generator is the determinism check for the generated manifest and C++ output. The source primitive fixes themselves add no rules for the broader pool and do not establish either root's dependency closure.

This is a scoped implementation result, not a claim that all reachable deck members are verified. Both roots remain blocked in the full Standard profile because their pool membership/closure and full-profile bridge/action/match gates are not satisfied.
