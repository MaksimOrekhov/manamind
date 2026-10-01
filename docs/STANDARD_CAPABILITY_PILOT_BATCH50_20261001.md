# Standard registration batch — 50 roots (2026-10-01)

## Scope

This batch added engine support records for the following 50 roots from the pinned `standard_registry_20261001_v1` pool:

`CORE_EX1_250`, `CORE_ICC_210`, `CORE_AT_062`, `EDR_942`, `TIME_100`, `EDR_889`, `CORE_GVG_059`, `CORE_EX1_002`, `CORE_ICC_214`, `TLC_EVENT_402`, `CORE_KAR_061`, `CORE_GVG_103`, `EDR_816`, `TIME_428`, `CORE_OG_211`, `CORE_GIL_534`, `JAIL_329`, `TIME_212`, `DINO_406`, `CATA_201`, `JAIL_441`, `CATA_203`, `EDR_485`, `EDR_571`, `FIR_954`, `CATA_467`, `CORE_DRG_403`, `CATA_305`, `CORE_CFM_753`, `CORE_WW_329`, `TIME_037`, `JAIL_387`, `TLC_828`, `END_021`, `MEND_305`, `DINO_419`, `EDR_861`, `TLC_621`, `TLC_623`, `CATA_458`, `JAIL_377`, `JAIL_456`, `CATA_303`, `END_014`, `TLC_606`, `EDR_468`, `JAIL_376`, `JAIL_462`, `EDR_572`, `TLC_633`.

Forty-eight IDs are in the allowlisted effect-composition declarations. `CORE_EX1_250` uses the existing keyword-only route, and `CORE_EX1_002` reuses an existing audited Core/legacy route. The generator now emits 92 effect-composition CardDefs in total.

## Validation

- Rebuilt RosettaStone `UnitTests` and the `mana_rosetta_bridge` module in the configured VS 2022 environment.
- Focused native effect-composition suite: **57 test cases, 361 assertions passed**.
- `scripts/verify_effect_composition_batch.py`: all 50 roots passed deck validation; all non-DK roots also passed simulator session creation, opening-hand presence, and legal-action availability. Death Knight roots passed only deck validation because DK session initialization still lacks its hero/default hero-power mapping.
- The eight newest effect-composition cases (`CATA_303`, `END_014`, `TLC_606`, `EDR_468`, `JAIL_376`, `JAIL_462`, `EDR_572`, `TLC_633`) have independent focused behavior scenarios in the native suite. The smoke gate for the other batch roots proves registration/session loading only, not complete rule correctness.
- Registry builder completed after the batch: 1,185 roots; 167 direct registrations; 176 generated registration entries; 842 text-bearing roots without detected registration; 191 known non-root nodes; 318 heuristic dynamic-pool signals. Complete root closures and training-eligible roots remain **0**.

All newly routed rules remain `IMPLEMENTED_UNVERIFIED` unless a current, card-specific evidence record says otherwise. Successful registration, focused scenarios, and bridge smoke do not establish full dependency closure or Standard training readiness. Do not start pooled training from this batch.

## Follow-up

Continue from the generated registry queues and source review. Keep the user's requested 50-card test/build cadence. Record whether each route is reused or newly authored and keep behavior evidence separate from registration smoke. Refresh the registry and admission report after each coherent batch.
