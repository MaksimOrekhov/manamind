# ManaEngine Phase 4E.1 — Dark Gift integration completion

## Result

Verdict: `DARK_GIFT_INTEGRATED_SCOPED`.

The mainline now has a bounded typed Dark Gift modifier and a reproducible experimental option fixture. Four of the ten launch-reviewed gifts have execution support. The other six remain in the choice universe and fail closed if selected. Runtime membership is `UNRESOLVED`, the sampler is `UNVERIFIED`, and training eligibility remains false. No canonical registry support or training status was promoted.

The independently typed option manifest contains 12 metadata candidates and 10 launch-reviewed options. It records its source and membership hashes and rejects altered identities or uncertainty statuses. The fixture is deliberately not asserted to be the exact live runtime pool.

## Scope and behavior

- `FIR_900` and `EDR_488` refer to the shared option manifest; no card-specific Dark Gift implementation branches were added.
- Implemented option effects: Waking Terror, Short Claws, Bundled Up and Sleepwalker.
- Unsupported launch gifts stay selectable candidates; selecting one invalidates the episode with the option identity.
- Modifiers are stored separately from generated `cost_delta`. Stat projection preserves accumulated damage. Charge grants an immediate attack against either minions or the enemy hero, subject to normal attack restrictions.
- Gifts remain attached through the reviewed hand, play, death, burn and transform paths. Copy, Silence, deck movement, Secret interaction and a second modifier fail closed. The existing `INSTANCE_COPY_V1` admission contract was not widened.
- Gifts are exposed on own-hand entities and public board entities. Pending option identities are shown only to the choosing player. The encoder schema is now 16; existing policy columns `dark_gift_1..10` are reused without a policy schema bump.
- Phase 4D.1 shared hand removal and Overload checks, and Phase 4E generated cost deltas, finite-pool manifests and TakesDamage processing remain covered.

## Verification

- Native build: MSVC 19.44, target `build/phase4e1-ninja` — PASS.
- Native CTest: 1/1 target PASS. Direct result: 46 scenario groups, 766 assertions PASS.
- Full Python suite: 90 passed.
- Ruff: PASS (`ruff check --no-cache src tests experiments/manaengine/tests scripts`).
- Generated artifact check: PASS; 36 pinned outputs reproduced.
- Generic card branch guard: PASS; 201 reviewed AST exceptions validated.
- `git diff --check`: PASS.
- Hosted Source CI: Ubuntu and Windows PASS on `e1a4d2d` (including the full `python -m pytest -q` step): [run 37228367420](https://github.com/MaksimOrekhov/manamind/actions/runs/37228367420).
- Hosted ManaEngine CI: Ubuntu and Windows PASS on `e1a4d2d`; both Release builds, CTest, and adapter/policy steps passed: [run 37228367387](https://github.com/MaksimOrekhov/manamind/actions/runs/37228367387).
- An earlier CI attempt on `c436683` caught the CRLF-sensitive metadata digest and an assertion that ignored numeric normalization. Both were fixed and verified in the rerun above.

## Registry and evidence

The observation-schema fingerprint changed from `6d78f757...` to `988407de...`. Canonical Standard registry outputs were regenerated using the normal registry builder, so dependent evidence freshness is evaluated from the new fingerprint. The Dark Gift source metadata SHA uses canonical UTF-8/LF bytes so Windows and Unix working-tree line endings produce the same identity. No evidence was manually copied or promoted. The registry still reports training admission `BLOCKED`.

## Implementation accounting

- Declaration consumers: 2 (`FIR_900`, `EDR_488`); 0 card-ID behavior branches.
- Shared behavior: typed persistent modifier, eligibility and deterministic assignment plumbing, preview/application/lifecycle guards, observation and policy mapping.
- Correction cycles: 2 Python verification corrections (schema expectation and typed manifest fixture setup); no production semantic correction cycle.
- Local native builds: 1; CTest runs: 1 successful.
- Active elapsed time: not reliably instrumented from the start of this task continuation; no fabricated duration is recorded.

## Deferred work

Do not claim exact runtime option membership, assignment distribution, full Dark Gift training readiness, Reborn restoration, double Battlecry, or broader copy compatibility. Those remain outside this bounded integration.
