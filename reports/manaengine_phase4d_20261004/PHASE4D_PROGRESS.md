# ManaEngine Phase 4D progress

- Branch: `codex/manaengine-first-deck`
- Baseline: `09e61e686f9a1a086d086e1bc24f475defd5c63b`
- Active-work timer started: 2026-10-04 14:28 UTC; hard stop at 17:13 UTC (2h45m)
- Initial primary queue: 31 `DEFERRED_RULES_EVIDENCE`
- Queue review completed: 0; exact candidates are preserved in `SAFE_EXISTING_PRIMITIVE_HARVEST.json`.
- Baseline tests: native 34 scenario groups / 665 assertions; adapter-policy 46 passed; full Python 90 passed.

## Initial family map (provisional)

1. Healing / healing-draw: `CATA_302`, `CORE_AT_055`.
2. Damage outcome continuation: `CATA_303`, `CORE_EX1_302`, `CORE_EX1_391`, `FIR_954`.
3. Board-wide and state-scaled damage: `CATA_581`, `CATA_582`, `JAIL_307`, `EDR_570`.
4. Existing composition / fixed choices: `CORE_AT_037`, `CORE_BOT_222`, `CORE_CS2_074`, `CORE_EX1_238`, `CORE_BOT_451`, `TIME_006`.
5. Narrow target operation: `CORE_CS2_108`; weapon modification: `CORE_CS2_074`.
6. Conditional/delayed/random/state interactions to assess and defer if they cross event/session bounds: `CATA_528`, `CATA_554`, `DINO_406`, `DINO_417`, `EDR_531`, `EDR_813`, `FIR_906`, `FIR_909`, `FIR_910`, `FIR_923`, `TIME_212`, `TLC_221`, `TLC_227`.

This map does not claim verified semantics or authorize expanding any card beyond its exact contract.

## Current verified work (updated 14:59 UTC)

- Active elapsed time: about 31 minutes.
- `manaengine_effect_target_boundaries_v1`: 2 declaration-only consumers (`CATA_582`, `CORE_BOT_222`), no custom outliers. Native PASS: 35 groups / 673 assertions; focused adapter PASS.
- `manaengine_constrained_minion_destroy_v1`: 2 declaration-only consumers (`CORE_CS2_108`, `EDR_531`), no custom outliers. Native PASS: 36 groups / 680 assertions. Adapter suite PASS: 22 passed.
- `manaengine_bounded_healing_v1`: 2 declaration-only consumers (`CORE_AT_055`, `CATA_302`), no custom outliers. Native PASS: 37 groups / 687 assertions. Adapter suite PASS: 22 passed. Mend's Blizzard page was not accessible; its pinned text has a secondary cross-check, so rules confidence remains medium.
- New reusable semantics so far: `ALL_MINIONS`, `SELF_HERO`, side/damage-constrained minion action selectors, typed minion destruction using existing death stabilization, fixed character healing and minion-to-full healing.
- First package needed an adapter enum allowlist update; one bridge correction cycle. No schema change.
- Six of 31 roots now have declarations and individual semantic review; the remaining 25 need individual dispositions. Five roots have direct Blizzard text evidence; Mend's direct card route could not be retrieved, so its confidence is medium and no canonical evidence is promoted.
- Native build outputs live in `E:\ManaMind\_build_phase4d` to keep worktree artifacts untouched.
