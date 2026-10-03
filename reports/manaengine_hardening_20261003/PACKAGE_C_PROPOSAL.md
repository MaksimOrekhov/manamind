# Capability Package Proposal — `profile_endturn_simultaneous_death_lifecycle_v1`

Status: verification-first stress package; no production engine change is proposed before the combined scenario passes.

## Semantic contract

On the active player's end turn, resolve the declared end-turn triggers for `CATA_475` and `CATA_999` in board order. `CATA_475` deals 2 damage to the enemy minion board and enemy hero. Damage that makes multiple enemy minions lethal is collected as a simultaneous death set after queued turn-end triggers complete. Then resolve deathrattles in player/board order until stable. The dying `CORE_DRG_107` generates one `EX1_277` in its owner's hand. `CATA_999` independently deals 4 damage to the enemy hero. The next active player's visible state must show its generated card in its own hand, while the opposing view must not reveal that hidden hand identity. The generated spell must expose an ordinary legal play action and resolve its deterministic, cloned RNG branch consistently.

The test establishes ManaEngine's declared FIFO prototype semantics only. It does not generalize this order to Death Knight/runeforge effects, nested choices, or all simultaneous trigger combinations. If the focused sequence disagrees with the pinned Rosetta tests or exposes an order that cannot be expressed with the current queue/death pass, stop for architecture review.

## Existing primitives

- FIFO end-turn trigger and per-minion end-turn behaviors (`CATA_475`, `CATA_999`).
- Board damage, simultaneous death collection and FIFO deathrattle queue.
- `CORE_DRG_107` deathrattle creates `EX1_277` in the owner's hand.
- Deterministic RNG, deep session cloning, visible self-hand projection and semantic legal actions.

## Reviewed profile candidates

| Card | Disposition | Current route |
|---|---|---|
| `CATA_475` Scalebreaker Bulwark | In scope | End-turn damage to all enemy characters, implemented. |
| `CATA_999` Earthen Drake | In scope | End-turn enemy-hero damage, implemented. |
| `CORE_DRG_107` Violet Spellwing | In-scope dependency/control | Deathrattle generates `EX1_277` Arcane Missiles, implemented and already used in trusted roots. |

This package is a composition/stress verification package, not a request to add three new card declarations. Expected new shared code is zero if tests confirm the existing contracts. Any production code change requires a revised proposal.

## Dependencies and outcomes

- Fixed dependency: generated `EX1_277` Arcane Missiles.
- Dynamic target pool: enemy hero and currently living enemy minions, sampled with cloned deterministic RNG; it is separate from the death test and remains complete.
- Unsupported dynamic outcomes: none in the focused deathrattle; the generated result is fixed and supported.
- No class/session requirement beyond current supported Mage observation/hero-power baseline.

## Test strategy

- Independent native scenario: end turn with both end-turn roots active and multiple one-health enemy minions, one carrying the real `CORE_DRG_107` deathrattle. Assert all minion deaths, both damage effects, exactly one generated spell, ownership/visibility, valid entity/zone invariants, normal legal actions, and clone-equivalent outcomes for generated Arcane Missiles.
- Review the pinned Rosetta native tests for `CATA_475`, `CATA_999`, and the generated-card dependency. Add a behavior-sequence parity case only when the current bridge can construct the sequence without weakening either side or modifying the source engine.
- Run full native and Python suites, RNG golden/invariant checks, and Windows/Ubuntu CI.

## Expected reuse and risk

- New declaration-only consumers: 0. Existing implementations exercised: 3 roots/dependency routes.
- `CUSTOM`/deferred outliers: 0. No ID-specific behavior or new effect primitive proposed.
- Estimated work is test/evidence focused (under an hour). Correctness risk is high enough to require event-order assertions; adding an arbitrary event-order repair would trigger an architecture checkpoint.
- Current Rosetta generated definitions and scoped tests are the cross-engine controls. Rosetta remains evidence for its implemented routes, not the sole semantic oracle.
