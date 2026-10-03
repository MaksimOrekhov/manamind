# Remaining risks after Phase 2 hardening

## Blocks acceptance beyond `KEEP_EXPERIMENTAL`

1. **CI is green for code commit `6223302`.** Source CI run `37141955265` passed on Windows and Ubuntu, including `check_generated_artifacts.py` and pytest on both. ManaEngine CI run `37141955267` passed on Windows, Ubuntu and macOS. A documentation-only follow-up commit records these run IDs and will receive normal CI checks.
2. **Held-card progress is fixture-scoped.** A local hook increments independent per-instance counters on direct player spell plays and adjusts current cost; no current Meta Profile card uses it. Nested, replayed, generated and auto-cast spell semantics remain undefined. A profile-root implementation needs a reviewed contract; changing global ordering requires architecture review.
3. **Event processing is deliberately approximate.** Prototype semantics are FIFO triggers, batch removal of all dead minions, FIFO deathrattles, repeat until stable. Replacements, death order nuances, aura recalculation, reborn, nested triggers and complete modern ordering are outside this pass.
4. **Effect composition is intentionally small.** `Damage`, `Draw`, `GainArmor`, `ModifyHeroAttack` and `Freeze` are reusable. `Heal`, general stat/cost modification, summon, destroy, hand generation and weapon effects remain named handlers, unsupported or future contracts; the schema is not a card-text DSL.
5. **Current legal/action semantics are narrow.** Only Mage hero power is implemented. Minion placement is automatic (adapter reports `field_position=-1`); Locations, Choose One, trade, hero classes, mulligan and broader action windows remain out of scope.
6. **Dynamic pools invalidate on selected unsupported outcomes.** Candidate sets are not filtered, as required, but complete current Standard pool semantics and all outcomes are not verified. Such a result must stop/invalidate an episode.
7. **Per-instance behavior remains incomplete.** The value model can hold counters, enchantment labels, modifiers and provenance, but transformations, copies, deck buffs, theft, silence application and aura/effect application are not general operations.
8. **Parity scope is small.** Rosetta parity passes two reference snapshots only. The comparator deliberately skips fields Rosetta does not expose; those fields rely on independently asserted ManaEngine scenarios. Lifecycle parity for all selected roots, combat/death order, dynamic outcomes and choice continuations remains open.
9. **Full repository Python suite is checkout-limited locally.** The current local run passed 81 tests with the Rosetta resource available from the configured workspace environment. Hosted Source CI also passed the complete suite on the prior source-reverification commit. The final commit must rerun Source CI.
10. **Benchmark uncertainty.** Clone is still fast in absolute terms, but clone/action/session performance shifted and the before/after fixtures differ. Repeat with matched supported deck fixtures and add an action-heavy workload before setting a numeric gate.

## Safe next work

- Keep the branch experimental until a real profile root has a reviewed held-card contract and parity coverage expands beyond the two current snapshots.
- Keep the branch experimental until a real profile root has a reviewed held-card contract and parity coverage expands beyond the two current snapshots.
- Before the first new card family, write a capability proposal that targets a real profile gap and can be expressed honestly by the current four effect primitives or a small shared native capability.
- Treat event-history, nested choice, global trigger-order or death-system work as an architecture checkpoint before changing it.
- Do not train, switch production backend, or start mass Meta Profile migration from the current evidence.
