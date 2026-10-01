# Capability pilot 2: repeated Battlecry/Deathrattle draw

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Registry snapshot: `standard_registry_20261001_v1`  
Status: **completed as scoped rules pilot; not training-ready**

## Hypothesis

Some current Standard cards use the same draw effect on both Battlecry and Deathrattle. A small declaration can express those two activation slots and the recipient of each draw, while emitting normal CardDef tasks.

| Card ID | Battlecry | Deathrattle | Independent native expectation |
|---|---|---|---|
| `CORE_DMF_067` Prize Vendor | Controller and opponent draw one | Controller and opponent draw one | Both hand sizes increase by one on each event. |
| `RLK_708` Chillfallen Baron | Controller draws one | Controller draws one | Controller hand increases by one on each event; opponent hand is unchanged. |

## Implementation

- Declaration: `integrations/rosettastone/card_rules/repeated_trigger_draw.v1.json`.
- Generator: `scripts/generate_repeated_trigger_draw.py`.
- Generated source: `ManaMindRepeatedTriggerDrawGen.hpp/.cpp`.
- Independent scenarios: `vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindRepeatedTriggerDrawTests.cpp`.
- Bridge smoke and fingerprints: `scripts/verify_repeated_trigger_draw.py`, `integrations/rosettastone/card_rules/repeated_trigger_draw.evidence.json`.
- Consolidated statuses: `scripts/build_standard_registry.py`.

The generator allowlists exactly these two IDs, checks current pinned English rules text and catalog fingerprint, rejects extra schema fields/effects, and refuses a duplicate CardDef owner. It emits only `DrawTask(1)` and `DrawOpTask(1)` into Battlecry and Deathrattle task lists. This is a narrow pattern compiler, not a general repeated-trigger language.

## Results and effort

- Focused native suite: 3 cases, 24 assertions passed; 2,520 unrelated tests were skipped. The full UnitTests suite was not run.
- Standard bridge check: Prize Vendor passed deck validation, session creation, visible opening hand and legal-action enumeration.
- Chillfallen Baron passed deck legality. Death Knight session creation remains blocked by the known missing Death Knight hero/setup support, so this card has no bridge session/action smoke.
- The final evidence fingerprints match the current catalog, declaration, generated source, capability file, engine library, bridge module and test sources. Both cards are `VERIFIED_SCOPED` / `CURRENT` for their tested trigger and draw-recipient behavior. `bridge_action_support` remains unaudited.
- Net result for the entire registry: 1,185 roots; 167 direct definitions; 29 generated manifest entries; 986 text-bearing roots without detected registration; 5 current scoped rules verifications; 0 complete dependency closures; 0 training-eligible roots. Full Standard admission remains **BLOCKED**.
- Measured elapsed time from beginning the package work through the test/evidence run: approximately **5 min 37 sec**. Focused C++ incremental compile/link after the test correction took about **3.9 sec**; bridge relink completed, but was not timed separately. These figures include no clean build.
- Generator/native ratio: 2 generated card definitions, 0 card-specific native handlers. Manual authoring/review time before this measured window is unknown.
- Corrections: one compile fix for `Power::GetPowerTask()` constness; one class-fixture correction after the expected Death Knight setup limitation appeared; one bridge-smoke scope adjustment to keep DK legality evidence without claiming an unsupported session.

## Limits

Tests establish the recipient and count for the two trigger types under the checked cases. They do not exhaust empty-deck fatigue, overdraw, full-hand behavior, all death timings, deck-dependent outcome closure or complete Standard profile behavior. Bridge status is partial for Chillfallen Baron because DK session setup is missing. No pooled training or game-strength claim follows from this pilot.
