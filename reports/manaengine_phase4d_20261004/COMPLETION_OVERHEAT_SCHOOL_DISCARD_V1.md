# Completion: `manaengine_school_discard_minion_buff_v1`

- Root: `FIR_906` (Overheat).
- Contract: buff living friendly board minions +1/+1; choose uniformly from the actual hand's Nature spells and discard the selected instance; apply another +1/+1 only when a discard occurred. The cast source has already left hand before this effect resolves. Empty eligible pool preserves only the first buff.
- Shared implementation: two typed effect kinds (`BUFF_FRIENDLY_MINIONS`, `DISCARD_RANDOM_SPELL`), a typed spell-school selector, and a typed immediate prior-discard condition in ManaEngine C++, pybind, strict Python declaration parsing, and generic resolver. No `FIR_906` behavioral branch.
- Declaration-only consumers: 1 (`FIR_906`). Independent control: Fire-school discard plus conditional buff with no production-code changes.
- CUSTOM/deferred outliers: none in the package. `FIR_910` remains deferred because its damage-and-discard follow-up has unresolved target/death ordering.
- Native: PASS, 42 scenario groups / 716 assertions. The new family scenario covers an actual hand, school filtering, exactly one eligible discard, ineligible Fire-spell retention, conditional second buff, preserving existing minion damage, empty pool, deterministic clone, and a Fire-school control.
- Adapter/action parity: PASS, full adapter file 24 passed. Adapter scenario casts Overheat through a legal action, verifies the root and sole Nature-spell candidate leave visible hand, and encodes actions before/after.
- Correction cycles: 2 (first assertion counted the cast source in graveyard; Fire control had the same mistaken assumption).
- Build attempts: 3 (two test assertion corrections, final native PASS).
- Observed elapsed package time: 13m36s (proposal/implementation start estimated 16:09 UTC; verified 16:22:36 UTC).
- Canonical registry/evidence: not changed or promoted. ManaEngine prototype support is not `VERIFIED_SCOPED` or training eligibility.
- Rules confidence: official card text reviewed at [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/115630-overheat/); no Overheat-specific client replay captured. The resolver follows the written sequential text and only commits the conditional buff after successful discard.
- Risks/bounds: a selected spell carrying a recognized unsupported discard-trigger mechanic throws `UnsupportedSimulationError`, invalidating that branch rather than shrinking the random pool. This is prototype behavior, not full Standard closure. No Python suite or CI-wide run is implied by the focused adapter check.
