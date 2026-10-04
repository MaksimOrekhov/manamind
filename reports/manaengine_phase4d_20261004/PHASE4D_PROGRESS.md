# ManaEngine Phase 4D progress

- Branch: `codex/manaengine-first-deck`
- Baseline: `09e61e686f9a1a086d086e1bc24f475defd5c63b`
- Active-work timer started: 2026-10-04 14:28 UTC; hard stop at 17:13 UTC (2h45m)
- Initial primary queue: 31 `DEFERRED_RULES_EVIDENCE`
- Queue review completed: 13 of 31; 18 candidates still need individual dispositions. The initial candidate set is preserved in `SAFE_EXISTING_PRIMITIVE_HARVEST.json`.
- Baseline tests: native 34 scenario groups / 665 assertions; adapter-policy 46 passed; full Python 90 passed.

## Initial family map (provisional)

1. Healing / healing-draw: `CATA_302`, `CORE_AT_055`.
2. Damage outcome continuation: `CATA_303`, `CORE_EX1_302`, `CORE_EX1_391`, `FIR_954`.
3. Board-wide and state-scaled damage: `CATA_581`, `CATA_582`, `JAIL_307`, `EDR_570`.
4. Existing composition / fixed choices: `CORE_AT_037`, `CORE_BOT_222`, `CORE_CS2_074`, `CORE_EX1_238`, `CORE_BOT_451`, `TIME_006`.
5. Narrow target operation: `CORE_CS2_108`; weapon modification: `CORE_CS2_074`.
6. Conditional/delayed/random/state interactions to assess and defer if they cross event/session bounds: `CATA_528`, `CATA_554`, `DINO_406`, `DINO_417`, `EDR_531`, `EDR_813`, `FIR_906`, `FIR_909`, `FIR_910`, `FIR_923`, `TIME_212`, `TLC_221`, `TLC_227`.

This map does not claim verified semantics or authorize expanding any card beyond its exact contract.

## Current verified work (updated 16:02 UTC)

- Active elapsed time: about 94 minutes (timer started 14:28 UTC; hard stop 17:13 UTC).
- `manaengine_effect_target_boundaries_v1`: 2 declaration-only consumers (`CATA_582`, `CORE_BOT_222`), no custom outliers. Native PASS: 35 groups / 673 assertions; focused adapter PASS.
- `manaengine_constrained_minion_destroy_v1`: 2 declaration-only consumers (`CORE_CS2_108`, `EDR_531`), no custom outliers. Native PASS: 36 groups / 680 assertions. Adapter suite PASS: 22 passed.
- `manaengine_bounded_healing_v1`: 2 declaration-only consumers (`CORE_AT_055`, `CATA_302`), no custom outliers. Native PASS: 37 groups / 687 assertions. Adapter suite PASS: 22 passed. Mend's Blizzard page was not accessible; its pinned text has a secondary cross-check, so rules confidence remains medium.
- `manaengine_enemy_area_secret_damage_v1`: 1 declaration-only Secret consumer (`CORE_EX1_610`), no custom outliers. Native PASS: 38 groups / 692 assertions. Adapter suite PASS: 22 passed. The card's official text is direct; Spell Damage at Secret trigger has secondary/community evidence and remains scoped rather than canonical.
- `manaengine_damage_outcome_followup_v1`: 3 declaration-only consumers (`CORE_EX1_302`, `CORE_EX1_391`, `CATA_303`), no card-specific branches. Native PASS: 39 groups / 702 assertions; adapter suite PASS: 22 passed. A focused trace verifies Mortal Coil follow-up before the target Deathrattle. Elapsed implementation/check time observed: about 19 minutes; two correction cycles and four builds. No canonical evidence was promoted.
- `manaengine_damage_target_owner_draw_v1`: 1 declaration-only consumer (`FIR_954`), extending the same typed contract with `ALWAYS → DRAW_TARGET_OWNER`. Native PASS: 40 groups / 706 assertions; adapter suite PASS: 22 passed. Tests cover each target side, lethal target Deathrattle, Divine Shield and owner fatigue. Observed elapsed time: 5m46s; one build, zero correction cycles. No canonical evidence was promoted.
- `manaengine_holding_dragon_fixed_summon_v1`: 1 declaration-only root (`TIME_006`) and fixed vanilla dependency `TIME_006t1`; no CUSTOM outliers or ID branches. Shared typed `SUMMON_FIXED` condition checks the owner's hand for a Dragon as the effect resolves and adds a bounded count. Native PASS: 41 groups / 710 assertions. Adapter PASS: full adapter file, 23 passed. Guard, Ruff, and diff check PASS. Observed package span: 12m02s; four correction cycles; three builds. No canonical evidence was promoted.
- New reusable semantics so far: `ALL_MINIONS`, `SELF_HERO`, side/damage-constrained minion action selectors, typed minion destruction using existing death stabilization, fixed character healing and minion-to-full healing.
- First package needed an adapter enum allowlist update; one bridge correction cycle. No schema change.
- Found and fixed an existing attack-flow bug exposed by the Explosive Trap scenario: a minion/hero killed by a Secret could still complete combat. This is one generic engine fix, not card-ID behavior.
- Thirteen of 31 roots now have declarations and individual semantic review; the remaining 18 need individual dispositions. No canonical evidence status has been promoted.
- Latest recheck after package 4: native 38 groups / 692 assertions PASS; full adapter test file 22 passed. Generic card-ID guard passed in the preceding check. These checks were rerun after confirming the typed Secret pair allowlist.
- Native build outputs live in `E:\ManaMind\_build_phase4d` to keep worktree artifacts untouched.
- Checkpoint `5d16439` is pushed to `origin/codex/manaengine-first-deck`; it contains the separately committed Explosive Trap package.
- Checkpoint `e002fc3` is pushed to `origin/codex/manaengine-first-deck`; it contains the outcome-conditioned damage package.
- Proposal and completion record: `PROPOSAL_MIRROR_DIMENSION_V1.md`. The exact token metadata is recorded separately in `experiments/manaengine/data/summon_condition_dependencies.json` and is sourced from the pinned Phase 4B Full Definition Slice; it does not enter the collectible pool.
- `manaengine_school_discard_minion_buff_v1`: 1 declaration-only consumer (`FIR_906` Overheat), no CUSTOM outlier; `FIR_910` deferred for unresolved target/death ordering. Native PASS: 42 groups / 716 assertions; adapter PASS: 24 passed. Actual-hand Nature-school discard, empty-pool behavior, conditional second buff, deterministic clone and independent Fire-school control are covered. Two correction cycles, three builds; observed package span 13m36s. No canonical evidence was promoted. See `PROPOSAL_OVERHEAT_SCHOOL_DISCARD_V1.md` and `COMPLETION_OVERHEAT_SCHOOL_DISCARD_V1.md`.
