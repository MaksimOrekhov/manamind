# Phase 4H — damage-group rules review

Date: 2026-10-05. Analysis only; no runtime changes or evidence promotion.

Reviewed ManaMind: `af0a599399b0694f5f7ad92af5834f0be63b38bc`, branch `codex/manaengine-first-deck`.
RosettaStone reference: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
Pinned Standard: `standard_full_20261001_v1`.
Metadata: `data/cards/standard_current_enUS.json`, SHA256
`c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34`.

## Verdict

**DAMAGE_GROUP_LOCAL_CONTRACT_BOUNDED** for ordinary minion AoE, single-packet instructions and their synchronous admitted reactions. Combine local grouping with instruction continuation. This is an architecture verdict, not full card correctness or permission to admit blocked states.

Arcane Barrage remains `BLOCKED_DESIGN_REVIEW`. Fire membership, lethal/lifetime TakesDamage v1 states, exceptional AoEs and ambiguous intra-group Spell Damage changes remain outside admission.

## Evidence discipline

Official materials below are primary publisher statements. The advanced-rulebook research project is independent reverse-engineering with its own experiments, not an official specification. Historical examples establish counterexamples, not patch-specific replay evidence for 2026. Individual card notes are corroborating leads. ManaEngine tests and RosettaStone establish implementation behavior, never rules truth.

No Vulcanos/Plume, Sleet Storm or Arcane Barrage client replay/Power.log was captured. General-phase conclusions are **RULES_REVIEWED_FROM_PHASE_MODEL**, not **DIRECT_REPLAY_VERIFIED**. Search-index excerpts were available for research pages whose direct fetch was restricted. Historical video links were identified but not watched; no video verification is claimed.

### Primary / independent research ledger

| ID | Source | Narrow finding used |
|---|---|---|
| S1 | [Blizzard: Hearthstone Game Mechanics Update, Josh Durica/Daxxarri, 2017](https://hearthstone.blizzard.com/en-us/news/21037565/hearthstone-game-mechanics-update) | Publisher confirms core timing changes; article does not specify the full damage algorithm. Old simulator behavior cannot certify current rules. |
| S2 | [Blizzard: Saviors of Uldum, Reborn](https://hearthstone.blizzard.com/en-us/news/23037181) | First destruction returns a Reborn minion with 1 health. Exact queue placement is not specified there. |
| S3 | [Advanced rulebook research](https://hearthstone.wiki.gg/wiki/Advanced_rulebook), Rules 1–5, DH1–4, combat | Ordinary AoE creates all damage events before their reactions. Events and responding triggers have separate ordering. Nested consequences finish before siblings. Normally deaths begin at the outer phase boundary. Multi-step effects finish damage reactions before condition checks/next steps. Combat has defender-first received-damage order. Mortal differs from removed. Historical exceptional AoEs exist. |
| S4 | [Original rulebook project, Draft1](https://hearthstone.wiki.gg/wiki/Hearthstone_Wiki%3AAdvanced_rulebook_project/Draft1), simultaneous-effect experiments | End-turn examples permit an already queued source at nonpositive health to act before removal. Counterexample to a universal positive-health execution filter; historical/current-client uncertainty retained. |
| S5 | [Researcher Patashu's experiment notes](https://hearthstone.wiki.gg/wiki/User_talk%3APatashu) | Original research index identifies an AoE/mortally-wounded-trigger experiment and [historical video](https://www.youtube.com/watch?v=QCk4CBuVnsM). Index inspected; video unavailable to this review. |

Supporting leads only: [AoE](https://hearthstone.wiki.gg/wiki/Area_of_effect), [damage](https://hearthstone.wiki.gg/wiki/Damage), [Grim Patron](https://hearthstone.wiki.gg/wiki/Grim_Patron), [Arcane Missiles](https://hearthstone.wiki.gg/wiki/Arcane_Missiles), [Greater Arcane Missiles](https://hearthstone.wiki.gg/wiki/Greater_Arcane_Missiles), [Spell Damage](https://hearthstone.wiki.gg/wiki/Spell_Damage). They corroborate the research model: missiles finish reactions before another selection, survival conditions are rechecked at activation, printed per-hit damage differs from a split total. No exact Barrage selection timeline was found in [its metadata page](https://hearthstone.wiki.gg/wiki/Arcane_Barrage).

## Fourteen requirements

The contract column is our proposed simulator design with explicit uncertainty guards. It does not assert universal Hearthstone equivalence.

| # | Question | Local contract / remaining boundary |
|---|---|---|
| 1 | One instruction, multiple targets | Ordinary minion AoE freezes membership, mutates every target, then dispatches damage events. Exceptional behavior cannot be inferred from a selector. Require a reviewed timing contract. |
| 2 | Multiple instructions | Finish instruction 1's reactions and nested consequences before evaluating instruction 2. No automatic death removal at this checkpoint. |
| 3 | Random multi-hit | Separate single-packet groups. Select each next target from the current admitted living set; no preselection. Empty set consumes no selection RNG. Repeated surviving targets are permitted only by the reviewed random contract. |
| 4 | TakesDamage in group | Entire area's mutations precede its first reaction. Queue eligibility and activation validity are separate. Keep existing v1 fail-closed bounds; 'takes damage' is not 'survives damage'. |
| 5 | Lethal packet | Mortal entity remains in Play until the phase boundary. Existing self-reaction v1 must reject lethal state, not claim the rules omit its event. |
| 6 | Reborn / Deathrattle | No group-local death drain inside open spell/EOT phase. Preserve batch-death implementation and intrinsic Reborn guards at existing reviewed outer boundaries. General death-trigger/slot ordering remains separate debt. |
| 7 | Source mortal mid-effect | Already-started group retains captured source/controller/attribution. Nonpositive source health does not erase remaining packets. Actual removal/transform/control change needs its own reviewed policy or rejection. |
| 8 | Later target mortal/removed | Mortal still-in-Play is not an automatic AoE exclusion; random selection excludes mortality. Unexpected actual removal/identity change during apply-all is unsupported, not silent retargeting. |
| 9 | Shield / Immune / zero | Resolve prevention during mutation. Prevented packets emit no successful-damage reaction/accounting. Shield loss remains a state change. Armor loss counts as successful damage separately from health loss. |
| 10 | Simultaneous vs ordered | Simultaneous means a reaction barrier, not unordered writes. Minion-area events use entry order; each event has its own trigger-order contract. Combat and compound Secrets need distinct profiles. |
| 11 | Spell Damage | Preserve `CURRENT_AT_STEP` per instruction and `MISSILE_TOTAL` once per split-total effect. If area's own mutations may change relevant modifiers, reject until intra-group evaluation is reviewed. Do not invent packet-wise re-evaluation. |
| 12 | Snapshot vs live | Snapshot ordinary area membership; live candidates per random hit. New entities do not join the current area's targets, but may join a later reviewed instruction. |
| 13 | Nested reactions | Finish admitted child group and its consequences before parent sibling. Appending children to one global FIFO is insufficient. Unsupported choice/phase/death operations reject. |
| 14 | RNG / clone | State-owned deterministic stream, stable candidate order and group/event IDs. Quiescent full-state clones must reproduce trace/RNG. No active-frame resumption claim. |

Requirements 1, 2, 4–8, 10, 12 and 13 use the researched phase model with exclusions. Requirement 11 includes the previously accepted project contract plus a conservative admission guard; unresolved aura behavior is not rules-established. RNG/clone are simulator requirements.

## Vulcanos determination

Pinned `CATA_488` has non-spell end-turn damage 3 to all other minions. No reviewed metadata establishes an exceptional packet/reaction mode. Ordinary AoE classification follows the research model.

**Both admitted unshielded Plumes receive 3 damage before either generation reaction begins.** Status: `RULES_REVIEWED_FROM_PHASE_MODEL`. There is no card-specific direct replay proof; current passing tests cannot establish sequential apply/react correctness.

At HEAD, `resolve_end_turn_reactions()` snapshots board-side-order handles, then calls `deal_damage()` for positive-health targets. That immediately calls `resolve_damage_occurrence()`. First Plume's unresolved pool throws before the second's packet. Native fixture records 2/8/5 health. A future apply-all group reaching that reaction failure must instead expose diagnostic 2/8/2. Both failed branches are unusable episodes; no production result changed today.

Other gaps: board order is not global entry order; positive-health filters conflate mortal and removed; later queued EOT sources are skipped at nonpositive health. The researched end-turn counterexample challenges that last universal filter. Source identity/phase eligibility and explicit unsupported-state guards must replace any unjustified health-only cancellation.

## Unresolved or excluded rules

- Barrage's selection timeline, replacement law and compound-event topology.
- Conditional Spell Damage changing during an area's own mutations.
- Removal, transform, silence or controller changes without a reviewed consumer-lifetime contract.
- Arbitrary predamage redirection, hero watchers and cross-zone trigger priorities.
- Lifesteal interactions requiring a healing-reaction order; current scalar healing remains a prototype bound.
- Forced intermediate death phases and full Reborn slot/death-trigger rules beyond current guards.
- Patch-specific direct replay confirmation for these consumers.

Use guards/deferred consumers. If a critical consumer needs forced phase transitions or Choice suspension, return to architecture review before enlarging scope.

## RosettaStone reference audit

Pinned `Tasks/SimpleTasks/DamageTask.cpp:34` gathers entities and loops through `Generic::TakeDamageToCharacter()`. `Actions/Generic.cpp:23` calls `ProcessTasks()`; queue context needs review before any port. `ConsecutiveDamageTask.cpp:32` explicitly invokes `ProcessDestroyAndUpdateAura()` between iterations. These are implementation references, not proof of desired boundaries. Do not copy their control flow as rules truth.

## Review impact

This review qualifies historical claims without rewriting Phase 4G, changing Fire membership, evidence fingerprints or registry statuses. Exact dispositions: [CONSUMER_MATRIX.md](CONSUMER_MATRIX.md). Future gate: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
