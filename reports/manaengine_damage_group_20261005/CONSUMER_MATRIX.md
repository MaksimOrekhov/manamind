# Phase 4H — consumer and historical-claim matrix

Analysis baseline: `af0a599399b0694f5f7ad92af5834f0be63b38bc`.
Rules identifiers refer to [the rules review](DAMAGE_GROUP_RULES_REVIEW.md); proposed checkpoints refer to [the architecture](DAMAGE_GROUP_ARCHITECTURE.md).
Line references below belong to this frozen baseline, not a later implementation.

## Concrete consumers

| Consumer | Current route / observed source behavior | Proposed damage boundary | Admission / work left |
|---|---|---|---|
| `CATA_488` Vulcanos | `resolve_end_turn_reactions`, engine.cpp:506–512. Source/targets filter health > 0; side/board order; immediate packet reactions | One fixed Effect area, exclude source, all mutations then event reactions. EOT phase ends later | Correct ordering in future shared helper. Fire unresolved; lethal self consumers and changed lifetimes blocked |
| `CATA_488t`, `CATA_488t2` Plumes | `deal_damage`:213 and `resolve_damage_occurrence`:203. Generation at each packet, unchanged positive-health self source required | Generate only after area's mutation barrier; self descriptor captured/revalidated | Pool unchanged/unloaded. No lethal admission or fabricated Fire result |
| `CATA_485` Sleet Storm | `resolve_effects`:391–414. Targeted 2 then random enemy minion 1. Amount evaluated per instruction; any pending board death blocks random selection | Single packet + reactions, then current modifier/candidate evaluation and second single packet | Accepted undamaged Seer example retained. Ordinary mortality filtering can be reviewed separately; mortal Spell Damage and lifecycle gaps stay blocked |
| `TIME_855` Arcane Barrage | No production declaration/handler; prior proposal blocked | Group infrastructure can represent alternatives, cannot choose topology | Dedicated [Barrage review](ARCANE_BARRAGE_REVIEW.md); no implementation |
| `CATA_582`, `EDR_570` damage mode — ALL_MINIONS | `resolve_effects`:406–414; skips nonpositive-health minions, then immediate reactions | Reviewed ordinary minion-area frame, targets include admitted mortal still-in-Play entities | Own conditional Spell Damage changes require preflight guard; choose-one continuation remains outside active damage execution |
| `CORE_CS2_032` Flamestrike — ENEMY_MINIONS | `resolve_effects`:394–414; snapshots enemy board, immediate reactions | Ordinary minion-area barrier, event order by entry sequence | Same helper; verify interleaved board/activation order and lethal non-consumer targets |
| `CATA_489` Shatter composition — ENEMY_CHARACTERS | Explicit first hit 4, then area 2; hero-first vector in area | First instruction reactions before next evaluated area. Hero event-order profile separate | Pure/no-reactive admitted path preserved. Mixed hero/minion reactions deferred until explicit profile reviewed; no arbitrary order promotion |
| `CORE_CS2_062` — ALL_CHARACTERS | Heroes 0/1 then side boards | Needs hero-containing area profile | No implication that vector order matches event order. Retain scalar-only prototype control; reject unreviewed reactive combination |
| `EX1_277` Arcane Missiles | `resolve_spell`:377; count evaluated once, 1 per packet; live living enemy pool each iteration | Complete one packet's reactions before next target draw; outer spell phase stays open | Preserve `MISSILE_TOTAL`, deterministic candidate ordering. Do not conflate with fixed-count/per-hit Spell Damage missiles |
| `CORE_EX1_610` Explosive Trap | `resolve_secret_instance`:473; area amount includes current Spell Damage; hero-first vector, positive-health enemies | Area barrier within existing attack Secret window; caller owns phase | Preserve Secret activation ordering. Reactive hero order and conditional modifier changes need separate guard/review |
| `CORE_LOOT_101` Explosive Runes | engine.cpp:484; precomputed excess from target health, minion packet then hero packet | Compound excess contract, not ordinary uniform AoE | Existing reviewed unmodified Bookkeeper original-identity case remains control. Reactions between minion/excess and shield/modifier interactions are not settled by this review |
| `CATA_475` EOT enemy area | engine.cpp:512; per-enemy calls then hero, source pointer reused | Local area + explicit hero ordering, completed before next EOT source | Replace pointer across reactions with captured value source. Mortal queued-source rule and supported combinations need family tests |
| `CATA_487` Raincaller | `record_spell_damage_event`:433 currently changes attack during packet handling | Typed successful-spell-damage reaction at P3; scalar turn accounting remains P1 | Preserve once-per-turn condition. Relative order with another responding consumer requires explicit profile; do not postpone all reactions until whole spell finishes |
| Combat | `apply_action`: near 603; defender packet then retaliation, immediate reactions before retaliation | Distinct paired mutation barrier and received-damage event order | At minimum fail closed for unreviewed reactive combat during first migration; pair helper before admitting those interactions. Normal scalar combat must not regress |
| Hero Power / fatigue | `deal_damage` callers in action handling / draw:201 | One packet group under existing attribution | Fatigue remains Fatigue, HeroPower remains HeroPower. No new DirectSpell attribution |
| Damage condition/follow-up | `resolve_effects`:415 | P3 completes before outcome condition at P4 | Preserve Mortal Coil/survives/target-owner follow-up family; do not process deaths merely to answer mortality |
| Reborn | `resolve_reborns`:525, `stabilize`:550 | Existing outer death processing after active frames finish | Keep intrinsic-only, fresh identity, 1 health, no second Reborn, board-mutation guards and multi-slot evidence constraint |
| Deathrattle batch | `stabilize`:550–583; collect/remove in entry order, FIFO Deathrattles then guarded Reborn | No group/packet-triggered extra drain | Existing pipeline is bounded prototype evidence. Do not claim complete death-trigger scheduler correctness |

Definitions are in `experiments/manaengine/data/card_abilities.json`; fixture-only variations remain tests, not new registered roots. Similar target selectors do not imply identical timing contracts.

## Phase 4G claims — precise disposition

Original record: `reports/manaengine_vulcanos_20261005/COMPLETION.md`.
Its numeric test/CI results describe what executed then and remain historical facts; no re-run was performed for this analysis.

| Historical claim / fixture | Disposition after review |
|---|---|
| Ordered Colossal appendages; independent entities; shared play/fixed summon entry | Remains valid within reviewed board-capacity/entry scope; unaffected by damage grouping |
| Capacity 0/1/4 admitted; 5/6 reject before mutation; transform/copy guards | Unchanged bounded results; no partial-capacity rules established |
| Fixed 3 Effect damage, source exclusion, no Spell Damage boost | Remains valid in isolated no-reaction/silenced-Plume scenarios |
| Shield/Immune scalar prevention | Remains valid in tested isolated targets; no claim of correct combined AoE reaction ordering |
| Intrinsic Reborn target returns after EOT | Remains bounded integration result with existing Reborn debt, not proof of full multi-death semantics |
| Silenced source does not run its effect | Valid static/pre-window case; silence after capture needs independent lifetime review |
| Two healthy Vulcanos bodies each damage the other to 5 health | Valid no-generation fixture result; does not certify simultaneous reaction semantics |
| Later queued Vulcanos at 1 health is killed by first and skips effect; older body stays at 8 | **Prototype-only expectation challenged by phase research.** New reference expectation is later source still executes while in Play; older body becomes 5 before death removal. Do not call old assertion rules verification |
| Target snapshot is sufficient to prove AoE behavior | Invalid inference: reactions still interleave; target-set freeze alone is insufficient |
| First Plume becomes 2, second stays 5 on pool failure | Actual diagnostic state of current prototype; **not a correct area barrier**. Future barrier test expects both 2 before failing generation |
| Candidate/missing pool and full hand fail before generation RNG | Valid fail-closed safety property; group placement of rejection must change without admitting candidate pool |
| Lethal Plume rejects | Remains intentional v1 restriction, not game-rule proof that lethal damage does not trigger |
| Dark Gift retained on surviving damaged minion | Valid scalar modifier-lifecycle control; not evidence for unreviewed nested modifier/trigger interactions |
| Three declarations/no behavioral ID branches | Remains source architecture fact; no extra support/admission implied |
| Runtime roots/closure/training gain = 0, verdict partial Fire blocked | Unchanged; correct conservative result |

## Evidence action in a future implementation

Do not edit old PASS traces or fingerprints. New semantic implementation must create new evidence with its actual source/build identity, qualify/reverify affected families and consume current pool status honestly. Scenarios expected to change must be changed with independent rationale, not merely to recover a green suite. This report promotes nothing and changes no canonical outputs.

## Phase 4H.3 update (implemented behavior; the rows above remain the original proposal-time analysis)

Authoritative current mortality and consumer behavior: [MORTALITY_POLICY.md](MORTALITY_POLICY.md). Additions and
corrections to this matrix:

| Consumer | Implemented route | Note |
|---|---|---|
| `JAIL_805` | Lifesteal `ENEMY_MINIONS` area, minion-entry order | Shield/Immune give no heal; omitted from the original matrix |
| `JAIL_805t` | same effect list through a minion Battlecry (Effect kind) | no Spell Damage, no Raincaller |
| `CORE_EX1_129` | enemy-minion area, then Draw after the group completes | one consumer may react normally |
| `CATA_999` | single EOT hero packet | mortal queued source resolves with `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED` |
| `CATA_475` | EOT enemy area plus hero, scalar-only group | mortal queued source carries the same debt; a reactive consumer among targets is rejected before mutation |
| `CORE_EX1_610` Explosive Trap | scalar-only attack-window area | keeps its `health>0` target filter, inconsistent with the AoE-includes-mortal rule but unreachable at present |
| Raincaller (`CATA_487`) | first-spell-damage attack gain | single reaction family: supported with hero-containing areas, compound Secrets and beside one generation consumer in minion areas; still rejected when the same entity is both watcher and consumer |
