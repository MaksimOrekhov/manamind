# Verification proposal — `priest_minion_enchant_verification_v1`

## Semantic scope

Verification-only family for two existing Priest targeted minion spells. Each root has its own expected effect contract; the shared audit family is target selection of a minion plus declarative enchant composition. No engine or declaration changes are proposed.

| Root | Pinned text/expected result | Existing route | Static dependencies |
|---|---|---|---|
| `CORE_CS2_004` Power Word: Shield | Give any minion +2 Health, then draw a card | `SPELL_PLAY` → `ENCHANT CS2_004e` → `DRAW 1`; only minion-target requirements | `CS2_004e` |
| `CAP_801` Haunt | Give any minion +2/+3, Reborn and Taunt | `SPELL_PLAY` → `ENCHANT CS2_009e` → set Reborn tag | `CS2_009e` |

The word “a minion” and the pinned CardDef requirements do not restrict either spell to friendly minions. Verification therefore covers a legal friendly target and a legal enemy target for both roots. Power Word: Shield's pinned text agrees with Blizzard's official Core card library: [Power Word: Shield](https://hearthstone.blizzard.com/en-us/cards/120786-power-word-shield).

## Existing primitives and blockers

- Existing CardDefs and effect-composition declarations; RosettaStone target legality, fixed enchantments, Reborn tag handling and DrawTask.
- Both enchantment dependencies exist as fixed native CardDefs; no dynamic pool, generated outcome, session/class blocker or new event-order behavior was found.
- Expected scoped unlock: 2 profile roots, across 1 deck.
- CUSTOM/deferred outliers: none forecast. Stop if enemy-minion targeting does not match the current source requirements or if effects differ from the independent expectations.

## Verification plan

- Run the existing root-specific native scenarios for each root.
- In the configured bridge, verify both sides appear as legal targets, resolve each effect, check changed minion state, and check Power Word: Shield's draw without treating action import as rules proof.
- Bind explicit profile-scoped evidence to the pinned execution identity and this Meta manifest; regenerate the Meta Profile audit. This package does not claim canonical Standard evidence, dependency closure, or training admission.

## Completion record

Elapsed time will be recorded from a `time.perf_counter_ns()` start marker placed before this proposal's review and stopped after evidence and profile regeneration. The shared preflight needed to rebind prior evidence after adding the new harvest evidence slot is timed separately.
