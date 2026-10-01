# Capability pilot 1: after-attack draw

Date: 2026-10-01  
Registry snapshot: `standard_registry_20261001_v1`  
Status: **completed as a scoped implementation pilot; not training-ready**

## Hypothesis

Cards whose exact text says “After this attacks” or “After your hero attacks” can share RosettaStone's existing `AFTER_ATTACK` trigger and `DrawTask`; the trigger actor is the only shared-mechanic branch. A constrained declaration can emit standard CardDef C++ while rejecting text, actor, operation, ID, or catalog drift.

The package contains three currently unregistered Standard roots:

| Card ID | Trigger actor | Ordered effects | Scenario evidence |
|---|---|---|---|
| `CAP_003` SI:7 Supplier | `SELF` | Draw 1 | An unrelated friendly minion attack does not draw; Supplier's own attack draws once. |
| `EDR_253` Ursine Maul | `HERO` | Draw 1 | Hero attack plus Hookfist scenario observes its separate draw. |
| `CORE_NX2_028` Hookfist-3000 | `HERO` | Gain 4 Armor, draw 1 | Hero attack raises armor by 4 and the combined Maul/Hookfist scenario draws twice. |

## Implementation

- Declaration: `integrations/rosettastone/card_rules/after_attack_draw.v1.json`.
- Generator: `scripts/generate_after_attack_draw.py`; exact allowlist and text-shape validation, closed fields/operations, duplicate-owner scan, deterministic output.
- Generated CardDefs: `ManaMindAfterAttackDrawGen.hpp/.cpp`, separately owned from manually maintained set sources.
- Independent native expectations: `vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindAfterAttackDrawTests.cpp`.
- Bridge smoke and fingerprinted evidence: `scripts/verify_after_attack_draw.py`, `integrations/rosettastone/card_rules/after_attack_draw.evidence.json`.
- Registry integration: `scripts/build_standard_registry.py` recognizes the generated owner and promotes only current, fingerprint-matched scenario scope.

The exact source text in the pinned catalog is checked on each generator run. The generator is deliberately limited to `AFTER_ATTACK`, `SELF|HERO`, and fixed `DRAW 1` / `ARMOR 4`; it is not a general trigger or effect language.

## Verification results

- Generator validation: 3 declarations accepted against catalog SHA-256 `03ea4df3b30f…`.
- Native build and focused tests: 3 test cases, 25 assertions passed. The test executable skipped 2,517 unrelated cases; the full UnitTests suite was not run.
- Bridge relink: successful against the rebuilt `build-mana-py312/lib/RosettaStone.lib`.
- Bridge smoke: all 3 cards passed Standard deck validation, session creation, opening-hand observation and legal-action enumeration.
- Evidence fingerprints cover rules text, declaration, generated source, capability file, engine library, bridge module and scenario sources. The registry now reports exactly these 3 roots as `VERIFIED_SCOPED` with `CURRENT` evidence.
- Registry totals after integration: 1,185 roots; 167 direct registrations; 27 generated registrations; 988 text-bearing roots without detected registration; 3 current scoped rules verifications; 0 complete dependency closures; 0 training-eligible roots. Full Standard admission remains **BLOCKED**.

## Scope limits and corrections

The verified scope is trigger actor plus declared effects for the tested cases. It does not certify every interaction of these cards, fatigue/overdraw/hand-full behavior, Standard deck closure, deck composition outcomes, or the full binary's support for the Standard pool. The bridge smoke did not play these cards through bridge actions; it checks deck/session/observation/action plumbing. Therefore bridge/action support remains `NOT_AUDITED` in the registry.

The broad eight-card DrawTask screen was correctly rejected as a code-generation package: those cards each required additional unique mechanics. This smaller family was selected after source review, not because text-frequency counts imply high impact. No reliable meta-frequency or old manual-authoring-time data is available.

Implementation corrections recorded:

1. The initial generated filename matched the registry's direct CardSet source glob; it was renamed so the manifest, not a source regex, owns the three definitions. Registry totals returned to the correct 167 direct / 27 generated split.
2. The first bridge fixture deck duplicated cards already selected by the deterministic deck builder; the fixture now swaps the intended card into the first deck slot without changing copy counts.
3. CMake's first reconfigure attempted an unnecessary vcpkg manifest refresh and selected the stale VS 2015 toolset. Configuration was recovered by using the existing installed dependency tree and running CMake/Ninja inside VS 2022 `VsDevCmd`; the py312 engine library and UnitTests were then built successfully.

Build time was not instrumented end-to-end across the failed setup recovery, so no total elapsed-time claim is made. The next package should wrap configure/build/relink/test in a timer from the start. Authoring/review effort before measurement is unknown.

## Outcome and next decision

The pilot supports reusing existing trigger/task composition for tightly matched cards, with a narrow allowlisted generator and independent tests. It does not establish a broad automation percentage. Keep this schema bounded; choose the next package from the refreshed generated capability report, review source contracts first, and record elapsed authoring/build/correction time from the beginning.
