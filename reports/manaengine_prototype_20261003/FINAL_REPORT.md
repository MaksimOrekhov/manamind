# ManaEngine controlled prototype — final report

Date: 2026-10-03
Branch: `codex/manaengine-prototype`
Base: ManaMind `0b27fec85b288996535c543b2e633c85ce73d68c`; RosettaStone gitlink `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.

## Decision

**Recommendation: `HYBRID_MIGRATION`.** Keep RosettaStone as the production rules engine and source of correctness. Keep this ManaEngine implementation isolated as a measured prototype and consider it for narrowly scoped search/branching experiments only after parity and performance are measured on those workloads. Do not switch production or training to it.

The experiment demonstrates that a separate engine can project the existing visible `GameState`, expose compatible legal-action dictionaries, branch through deep clones, and play a bounded full match. Its measured turn-advance throughput is higher and clone is available, but session construction is much slower, legal-action generation is slightly slower, the semantics cover only 18 scoped roots, and much of Hearthstone's rules surface is absent. That evidence favors preserving both assets while keeping Rosetta authoritative.

## Architecture and implemented scope

`EngineState` is private and authoritative in the C++ session. Python converts each observation into ManaMind's existing immutable `GameState`; hidden deck order, RNG state, pending trigger queues and typed choice continuation stay internal. Action dictionaries cross the same adapter boundary. Deep clone copies mutable state and RNG; immutable card definitions are shared through a read-only `CardCatalog`.

The documented prototype event pass is: resolve triggers FIFO, remove deaths, resolve resulting deathrattles FIFO, and repeat until stable. A typed `BuffSelectedMinion` choice derives options from the current board and resumes through a typed continuation. RNG is seeded (`7` in comparative runs). These are prototype rules, not a complete Hearthstone specification.

The behavior map contains the 18 reviewed Tier A/B roots: 3 Tier A canonical current verified roots and 15 Tier B roots with current scoped Meta Profile evidence. No Tier C root contributes to parity. Generated entities and test fixtures are declared as data; C++ behavior dispatch is by typed ability, not by card ID. Prototype-only choice fixture contributes no card root. Dynamic deck selectors evaluate the current complete deck by the declared minion/cost predicate and do not filter by implementation status.

### Root scenario matrix

Each expected effect below was asserted independently in a ManaEngine native scenario and reviewed against the focused Rosetta unit test(s) listed. The native run is a controlled fixture; it is not a claim that all surrounding card interactions match.

| Tier | Root | Independent expectation | Rosetta focused test coverage | ManaEngine scenario |
|---|---|---|---|---|
| A | `CORE_DRG_107` Violet Spellwing | Deathrattle adds Arcane Missiles | Core alias card tests | `test_tier_a_generated_effects` |
| A | `CORE_SW_072` Rustrot Viper | Battlecry destroys enemy weapon | Core alias card tests | `test_tier_a_generated_effects` |
| A | `CORE_SW_108` First Flame | Deal 2 to a minion and add Second Flame | Core alias card tests | `test_tier_a_generated_effects` |
| B | `CORE_CS2_024` Frostbolt | Deal 3 to target and freeze it | Effect composition tests | `test_targeted_spells_and_backstab` |
| B | `CORE_CS2_029` Fireball | Deal 6 to selected character | Core card tests; opening/post-play bridge parity | `test_targeted_spells_and_backstab` |
| B | `CORE_CS2_062` Hellfire | Deal 3 to all characters | Core card tests | `test_area_damage_draw_and_lifesteal` |
| B | `CORE_CS2_072` Backstab | Deal 2 only to an undamaged minion | Core card tests | `test_targeted_spells_and_backstab` |
| B | `CORE_EX1_129` Fan of Knives | Deal 1 to enemy minions, then draw | Effect composition tests | `test_area_damage_draw_and_lifesteal` |
| B | `CORE_EX1_145` Preparation | Next spell this turn costs 2 less | Core card tests | `test_cost_modifiers_and_composition` |
| B | `CORE_ICC_055` Drain Soul | Deal 3 to an enemy minion and heal controller for damage | Core card tests; focused enemy-target legality assertion | `test_area_damage_draw_and_lifesteal` |
| B | `CORE_BT_416` Raging Felscreamer | Next Demon in hand costs 2 less | Core card tests | `test_cost_modifiers_and_composition` |
| B | `CATA_475` Scalebreaker Bulwark | At controller turn end, deal 2 to enemy characters | Effect composition tests | `test_endturn_and_dynamic_deck_pools` |
| B | `CATA_999` Earthen Drake | At controller turn end, deal 4 to enemy hero | Effect composition tests | `test_endturn_and_dynamic_deck_pools` |
| B | `END_007` Press the Advantage | Deal 1, gain temporary hero Attack, draw, gain Armor | Effect composition tests | `test_attack_and_trigger_package` |
| B | `TIME_218` Static Shock | Deal 1 to minion, gain temporary hero Attack | Effect composition tests | `test_attack_and_trigger_package` |
| B | `JAIL_327` Reinforcement Aura | At each of next 3 turn ends, summon one current deck minion costing at most 2 | Profile deck minion composition tests | `test_endturn_and_dynamic_deck_pools` |
| B | `JAIL_516` Scarlet Recruiter | Battlecry summons up to two live deck minions costing at most 2 with Rush | Profile deck minion composition tests | `test_endturn_and_dynamic_deck_pools` |
| B | `JAIL_872` Spider Rider | After hero attacks, draw a card | Effect composition tests | `test_attack_and_trigger_package` |

Focused Rosetta run on the pinned source: **19 cases, 150 assertions passed**. ManaEngine CTest: **1/1 passed**; binary reports **10 scenario groups, 53 assertions**. Scenarios include damage/target legality, draw and generation, cost changes, attack/end-turn triggers, minion combat and death, live deck selectors, pending choice, clone independence, RNG reproducibility, Mage hero power, initial hand/Coin, and terminal completion.

### Parity boundary

The side-by-side bridge check compared the complete adapted `GameState` plus sorted legal-action signature at two reproducible points:

1. Opening state (same validated 30-card Mage fixture, seed `7`, deterministic order).
2. After playing Violet Spellwing in the opening state.

Both states and action sets matched. The comparison removes only the static catalog `mechanics` field, which the current Rosetta bridge does not export. Each of the other 16 roots has focused Rosetta case coverage and a separate ManaEngine expected-effect assertion; they were not all replayed at matching Rosetta/ManaEngine positions. Therefore this is a scoped semantic prototype matrix, not 18-card full-state cross-engine parity.

Choice continuation and runtime-derived candidates are validated in an isolated prototype fixture. This choice case is not a Tier A/B root. Deck selector tests verify filtering against all entries in the supplied current deck; they do not claim full behavior for every card that could later be summoned. Arcane Missiles uses seeded live character selection; no random/Discover pool was reduced to supported outcomes.

## Build, checks and environment

- Compiler/build: MSVC 19.44.35213, C++20, CMake 3.31.6, Ninja Release, Python 3.12.10, pybind11 3.1.0, Windows 11 build 26200.
- ManaEngine native build succeeded; CTest `manaengine_native` passed 1/1.
- Python adapter test passed 1/1; Ruff passed.
- Existing main checkout Python suite: **80 passed**.
- A second full-suite attempt through the isolated worktree passed **77/80**. Its three failures were two owner-path and one equivalent declaration-owner validation assertion: a temporary directory junction resolves `vendor/RosettaStone` to the main checkout, so `Path.is_relative_to()` sees the external physical path. No product source was changed to mask this. The junction was removed after verification. The 80/80 result comes from the ordinary checkout with its real submodule path.
- Focused Rosetta suite: **19/19, 150 assertions** at the pinned gitlink above. The full Rosetta UnitTests suite was not rerun for this prototype.
- Full bridged state/action equality was directly checked at the two points listed above.
- Main remained at base commit; no registry, evidence, data, checkpoint or training output was changed.

## Performance

Release benchmark on the same Windows host, seed `7`, 30-card Rosetta-validated Mage fixture, no shuffle; 15 timing iterations (150 legal-action calls), 10 complete pass-only fatigue games per backend. Times are median / p95 in ms.

| Operation | RosettaStone | ManaEngine | Observation |
|---|---:|---:|---|
| Session creation | 1.129 / 1.323 | 9.806 / 10.770 | ManaEngine remains about 8.7× slower here. |
| `legal_actions()` | 0.0257 / 0.0270 | 0.0325 / 0.0605 | ManaEngine is slower on this small fixture. |
| Apply end turn | 0.2151 / 0.2861 | 0.0382 / 0.0516 | ManaEngine is about 5.6× faster for this operation. |
| Clone | unavailable in bridge | 0.0010 / 0.0011 | ManaEngine supports a fast deep branch; Rosetta interface did not expose it. |
| Estimated working-set delta/session | 236,475 B | 546 B | Process working-set estimate while sessions are retained; not an object-level allocation measurement. |
| Pass-only complete games | 20.66/s; 1,384 transitions/s | 55.79/s; 3,738 transitions/s | Both completed 10/10 games, averaging 67 end-turn transitions, with P1 win. |

The estimated ManaEngine per-session memory fell from about **424,072 B** in the first run to **546 B** after sharing immutable card definitions. This estimate is sensitive to allocator and process working-set noise. Session construction did not improve because this Python adapter still materializes/validates the deck/session state. The benchmark measures the Python API boundary, not a raw C++ microbenchmark. Pass-only games measure fatigue/end-turn throughput; they are not representative full card-play match throughput.

## Reuse and migration inventory

| Area | Classification | Finding |
|---|---|---|
| Existing `GameState`, entity model, encoders, Policy/Value interfaces | `REUSE_UNCHANGED` behind projection | Existing visible schema and model pipelines remain untouched. |
| Catalog metadata and vocabulary | `REUSE_UNCHANGED` | Card IDs/stat metadata feed internal definitions and adapted observations. Immutable native catalog is shared. |
| Legal-action dictionaries | `REUSABLE_AFTER_ADAPTER` | Common actions cross as ManaMind dictionaries; engine entity handles remain execution-only. New choice action and hero power need explicit mapping. |
| Training data, Power.log, split logic, checkpoints | `REUSE_UNCHANGED` | Not read as simulator state, rewritten, or retrained. Compatibility here is structural only. |
| Rosetta CardDef/Power/Tasks/Triggers and native implementation | `ROSETTA_ONLY_WORK` | These executable rules are not portable as-is. Card behavior was separately authored as typed native C++ capability handlers plus JSON declarations. |
| ManaMind backend/session boundary | `REUSABLE_AFTER_ADAPTER` | The experiment proves the projection boundary, but there is no production-selectable backend protocol or lifecycle integration yet. |
| Full game rules and session processing | `WOULD_NEED_MIGRATION` | Every unsupported shared mechanic, hero class, event order, generated effect and lifecycle behavior would need explicit implementation and parity evidence. |

No model/schema migration was necessary for adapter smoke. Full simulator replacement is not a small migration: 18 roots do not represent current Standard or any complete deck closure.

## Limits and risks

- Implemented only the selected Mage-oriented parity set and one Mage hero power (Fireblast). There is no complete hero/class session support, mulligan, deck legality enforcement in ManaEngine core, or exhaustive action/observation surface.
- Prototype FIFO trigger/death/deathrattle order is bounded and documented. It is not verified against all simultaneous deaths, nested triggers, replacement effects, aura recalculation, secrets, choice ordering, or priority rules.
- Choice continuation is one typed prototype path; this is not a general complete choice system.
- Current-deck candidate predicates are applied without implementation filtering, but summoned definitions whose later effects are absent remain unsupported. No full collectible/random/Discover pool was verified.
- No 8–10 complete modern deck closures, training episode validation, policy-strength evaluation, or ML training was attempted.
- The worktree's Rosetta path mount must be a real initialized submodule for owner-path validators; a junction is not equivalent for `Path.is_relative_to()` checks.

These limits block `MANAENGINE_PRIMARY` and block claims of training eligibility. They do not undermine the narrower finding that the internal-state/projection boundary and a small reusable C++ core can coexist with current ManaMind types.

## Work and recommendation rationale

Observed elapsed active work was approximately **1 h 30 min**. Correction cycles were: (1) make the Windows toolchain/worktree import usable; (2) refine scenario setup/expectations and correct Drain Soul's enemy-only targeting; (3) match opening hand/Coin/deck order and terminal behavior; (4) share the immutable card catalog after measuring high session allocation. The final focused and CTest runs passed. A separate full-suite run surfaced only the three physical-path failures described above; the normal checkout suite passed 80/80.

`KEEP_ROSETTA` alone would discard the useful experiment on clone/branch behavior and fast turn-advance. `MANAENGINE_PRIMARY` is not supported by the narrow semantics, construction cost and missing class/rules surface. **`HYBRID_MIGRATION` is the single recommendation:** retain Rosetta as production authority; preserve this branch as a prototype and only consider a measured, opt-in backend slice if a concrete workload benefits from cloning or turn throughput and can be gated by parity. This recommendation does not authorize a production migration or training.
