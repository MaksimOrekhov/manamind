# Remaining ManaEngine risks after Phase 3

## Blocks controlled migration

1. **Dynamic Discover outcomes:** the complete pinned `CORE_GIL_836` pool contains 139 eligible cards. Only one is currently supported in ManaEngine; 138 selected outcomes invalidate the branch. Pool membership must stay complete.
2. **Dynamic deck summon:** the current Paladin profile roots can select low-cost minions whose definitions are not supported. A successful complete-pool outcome is not yet evidenced; unsupported selections invalidate episodes.
3. **Weapon semantics and parity:** ManaEngine has weapon destruction and attack/durability primitives, but the current Meta fixture lacks a shared supported weapon-equip card path. A real supported scenario is needed before claiming weapon sequence parity.
4. **Event/death ordering:** the tested FIFO trigger → lethal-set removal → FIFO Deathrattle → repeat contract is only a prototype approximation. Replacement effects, nuanced death order, aura recalculation/expiry, reborn, and nested trigger/choice order remain unproved.
5. **Choice and action breadth:** the real Discover continuation works for the bounded reviewed contract. Other classes, Choose One, trade, locations, mulligan, and broader action windows are unsupported. Semantic parity is not established for all offered actions.
6. **Held-card cast paths:** the three Shaman consumers count an explicit successful player `PlayCard` action for a spell from hand. Internal replay, auto-cast, nested, countered, and generated effects that bypass that action are explicitly outside this contract and fail closed if they reach a tracker-held state.
7. **Training gates:** no canonical registry/dependency/session/match evidence was promoted by the prototype. No deck is training eligible; no training, production switch, or mass Meta migration is authorized by this result.
8. **Hosted CI:** final Source CI and ManaEngine CI must execute on Windows and Ubuntu for the pushed Phase 3 commit. Local Windows checks do not replace those jobs.

## Measured limits

- Local Windows Release native suite: 23 scenario groups / 398 assertions; CTest passes.
- Full Python suite: 81 passed. Focused adapter/action pipeline after trace coverage: 23 passed.
- Rosetta native UnitTests on the pinned source build: 266/267 pass, with the previously established `[Druid : Minion] - CORE_OG_044 : Fandral Staghelmh` failure. No new Rosetta source change was made.
- Sequence parity: 26 checkpoints over targeted Fireball, Violet Spellwing minion trade/deathrattle and generated Arcane Missiles play, and Earthen Drake end-turn damage. Weapon and dynamic-deck-summon outcomes are not parity claims.
- Matched ManaEngine performance comparison is in `BENCHMARKS.md`; no observed operation approached an order-of-magnitude regression. Short-run RSS and timing figures remain noisy.

Keep the branch experimental until the gaps above are addressed by reviewed contracts and real, non-filtered scenarios. This report does not authorize training or production migration.
