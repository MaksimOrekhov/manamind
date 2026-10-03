# Remaining risks after Phase 2 hardening

## Blocks acceptance beyond `KEEP_EXPERIMENTAL`

1. **Source CI is still pending.** ManaEngine's hosted Windows/Ubuntu/macOS workflow is green at `0c2f4a20f9c28e3589d17885cc0fb07a62918d2b` (Actions run `37137664188`). The distinct Source CI must pass on Windows and Ubuntu after canonical regeneration is pushed, and its pytest step must be observed running.
2. **Held-card progress is storage-only.** `CardInstance.counters` proves independent per-copy state and clone fidelity, but no event updates a counter for a real Meta Profile card. A subsequent package that needs spell history must first establish the exact semantic event boundary and may require architecture review if that changes global event ordering.
3. **Event processing is deliberately approximate.** Prototype semantics are FIFO triggers, batch removal of all dead minions, FIFO deathrattles, repeat until stable. Replacements, death order nuances, aura recalculation, reborn, nested triggers and complete modern ordering are outside this pass.
4. **Effect composition is intentionally small.** `Damage`, `Draw`, `GainArmor` and `ModifyHeroAttack` are reusable. Other listed primitives remain named handlers or unsupported; the schema is not a card-text DSL.
5. **Current legal/action semantics are narrow.** Only Mage hero power is implemented. Minion placement is automatic (adapter reports `field_position=-1`); Locations, Choose One, trade, hero classes, mulligan and broader action windows remain out of scope.
6. **Dynamic pools invalidate on selected unsupported outcomes.** Candidate sets are not filtered, as required, but complete current Standard pool semantics and all outcomes are not verified. Such a result must stop/invalidate an episode.
7. **Per-instance behavior remains incomplete.** The value model can hold counters, enchantment labels, modifiers and provenance, but transformations, copies, deck buffs, theft, silence application and aura/effect application are not general operations.
8. **Parity scope is small.** Rosetta parity passes the two existing reference snapshots only. The direct comparator deliberately skips fields Rosetta does not expose; those fields rely on independently asserted ManaEngine scenarios.
9. **Full repository Python suite is checkout-limited locally.** 39 unrelated/in-scope tests and 20 adapter/policy/schema tests passed. Registry and family modules needing `vendor/RosettaStone/Resources/cards.json` could not run because this isolated worktree has no populated Rosetta submodule. Source CI should run those on a full checkout.
10. **Benchmark uncertainty.** Clone is still fast in absolute terms, but clone/action/session performance shifted and the before/after fixtures differ. Repeat with matched supported deck fixtures and add an action-heavy workload before setting a numeric gate.

## Safe next work

- Push the pinned-source re-verification and canonical outputs, then inspect both Source CI jobs through the pytest step before changing the verdict.
- Keep the branch experimental if CI is red or held-counter semantics remain untested.
- Before the first new card family, write a capability proposal that targets a real profile gap and can be expressed honestly by the current four effect primitives or a small shared native capability.
- Treat event-history, nested choice, global trigger-order or death-system work as an architecture checkpoint before changing it.
- Do not train, switch production backend, or start mass Meta Profile migration from the current evidence.
