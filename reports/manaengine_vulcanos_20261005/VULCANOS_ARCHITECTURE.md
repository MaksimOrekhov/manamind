# CAPABILITY PACKAGE PROPOSAL — Vulcanos vertical slice

Date: 2026-10-05. Package: `colossal_appendages_end_turn_other_minions_v1`.

## Semantic contract

Implement a finite declared Colossal body-to-appendage relation shared by play and effect-summon entrypoints, plus a reusable end-turn damage instruction that damages every minion except its source. `CATA_488` declares `CATA_488t`, then `CATA_488t2`, as appendages; its damage amount is declarative. Both Plumes declare the existing TakesDamage v1 consumer with pool ID `fire_spell_standard_20261001_candidate_v1` and cost delta `-3`. The generic pool runtime rejects candidate manifests before RNG; no Fire result is sampled in production until membership is reviewed.

## Capability package proposal fields

- **Existing primitives:** ordinary summon, activation sequence, shared board positions/capacity, damage prevention and damage pipeline, TakesDamage v1, finite pool manifests, deterministic RNG, generated-instance additive cost deltas, clone.
- **Reviewed candidates:** `CATA_488` and fixed dependencies `CATA_488t`, `CATA_488t2` only.
- **Dependencies:** two non-collectible Plume definitions; Fire manifest remains candidate/open and cannot serve as a production result pool.
- **Required shared changes:** typed `colossal_appendages` field and parser/validator; one common board-entry helper; typed end-turn-other-minions damage ability; preflight/full-family capacity failure; explicitly fail-closed transform-into-Colossal and Plume candidate pool.
- **Expected unlock:** Vulcanos Colossal/end-turn branch under full-family capacity; 0 fully executable Plume damage reactions until exact Fire membership is evidenced. Training eligibility remains false.
- **Test strategy:** native capacity boundary, play/effect summon, insertion order and identity, source exclusion, both-side damage, shields/immune/silence, Reborn, Dark Gift preservation, candidate-pool fail-before-RNG, cost descriptor, clone determinism, transform/copy boundaries; then full adapter/Python/guardrail/CI matrix.
- **CUSTOM outliers:** none proposed; no card-ID behavior dispatch.

## Deferred semantics

Exact partial-capacity Colossal behavior, Transform into Colossal, copying/creating a copy of a live Colossal, and the complete random Fire generation membership are outside this package's admitted contracts. Unsupported branches invalidate before hidden RNG consumption or partial mutation.
