# ManaEngine Phase 4D.1 — Completion

Branch: `codex/manaengine-first-deck`  
Base: `31a9df16a6ffa1ff571e79e9bcfcfd82d3248d17`

## M1 — Overload overflow

The end-turn transition now checks the next player's pending Overload against the crystal capacity after the normal maximum-Mana increase, before it clears pending debt, changes the active player, refills Mana, or draws. Existing already-applied debt above current capacity is also rejected. The branch is marked unsupported and raises `UnsupportedSimulationError`; excess debt is never clamped or silently dropped.

The regression sets next maximum Mana to 2 after turn start and pending Overload to 3. The transition fails closed before the player can take an action such as The Coin. Existing tests still cover one Overload, stacked debt within capacity, Counterspell suppression, clone equivalence, and normal turn lock/refill.

## M2 — Shared hand removal

`remove_card_from_hand(owner, position)` is now the ordinary hand-exit operation. It captures and returns the exact `CardInstance`, erases that instance, updates remaining hand positions, and repairs/recomputes Shatter relationships. A state that cannot be reconciled under the existing Shatter contract still invalidates through `UnsupportedSimulationError`.

| Path | Classification | Notes |
|---|---|---|
| Minion, spell, Secret, or weapon play | `USES_SHARED_REMOVE` | Effective cost is captured before removal; returned identity continues into the destination zone. |
| `DiscardRandomSpell` | `USES_SHARED_REMOVE` | Eligibility and unsupported discard-trigger checks happen before removal; the exact selected instance moves to graveyard. |
| Prepare action | `NOT_ACTUALLY_HAND_REMOVAL` | Mutates the held instance in place. |
| Draw or generated card when hand is full | `NOT_ACTUALLY_HAND_REMOVAL` | The incoming instance is burned before it enters hand. |
| Choice-generated hand card / draw into hand | `NOT_ACTUALLY_HAND_REMOVAL` | These are hand-entry paths. |
| Shatter split on hand entry | `NOT_ACTUALLY_HAND_REMOVAL` | Replaces one incoming instance with its reviewed fragments. |
| Shatter pair recombine | `SPECIALIZED_WITH_REASON` | Atomically replaces two linked fragments with one original card, preserving the chosen entity identity; sequencing individual removals would incorrectly expose a temporary SOLO state. |
| Transform | `NOT_ACTUALLY_HAND_REMOVAL` | Current transform path changes board minions, not hand instances. |

The regression matrix covers discarding LEFT and RIGHT, removing an unrelated card between a linked pair (which recombines), removing before a separated pair, multiple unrelated cards around a pair, position updates, and two cloned branches removing different instances. Randomly discarding RIGHT from `LEFT, X, RIGHT` leaves LEFT as `SOLO`, with no partner entity link. Native invariant validation succeeds and the observation exports no dangling position.

The Python adapter test passes the corresponding valid SOLO observation through `_export_state` and `GameState` construction. A deliberately dangling LEFT observation still raises the expected `ValueError`, so adapter validation was not weakened. The random-discard state transition itself is covered natively with a deterministic synthetic Shatter/Fire fixture; the Python test isolates the bridge/domain serialization contract.

## Cross-feature regressions

One native adversarial group combines hand removal with Shatter, per-instance Spell Damage, prepared-card state, and Kindred `INSTANCE_COPY_V1`; it also covers Overload with clone, Counterspell and turn transition, plus Sleet's ordered damage/random follow-up across clone. Shatter and Prepare-only card definitions are synthetic test fixtures; no production cards were added.

## Low findings and queue dispositions

- Simplified the enemy/friendly target filter to its equivalent side checks; existing target scenarios cover the result.
- Documented the prototype's fixed 30 hero max-Health assumption at the healing and Lifesteal clamps. No max-Health model was added.
- Kept `DrawTargetOwner` keyed to owner. Its implementation comment records that control changes are unsupported and owner/controller coincide for admitted targets.
- Reclassified `CORE_AT_037` Living Roots to `DEFERRED_ARCHITECTURE`: the remaining issue is the typed Choose One continuation and branch-specific action generation.
- Reclassified `CORE_CS2_074` Deadly Poison to `DEFERRED_ARCHITECTURE`: the remaining issue is generic weapon Attack/castability modeling, with the no-weapon case kept explicit in that contract.
- No new card implementation, canonical evidence promotion, training admission change, or training run.

## Verification

- Native full suite: **PASS**, 44 scenario groups / 741 assertions.
- Focused ManaEngine adapter file: **PASS**, 26 tests.
- Full Python test suite: **PASS**, 90 tests.
- Ruff: **PASS**.
- Generic card-ID identity guard: **PASS**, 201 reviewed AST exceptions; CUSTOM ownership checked.
- Generated artifacts: **PASS**, 36 pinned outputs reproduced.
- `git diff --check`: **PASS** after removing one trailing-space line.

The first pytest invocation used the worktree's default cache/temp location and completed all test cases but hung during pytest shutdown. Both Python runs were repeated with plugin autoload disabled, cacheprovider disabled, and a writable basetemp under `E:\ManaMind\_build_phase4d`; those runs returned exit code 0. Build artifacts remain outside the worktree.

## Hosted CI

Implementation commit: `0a7d3c763679f9adef92127fa4397eb907ac9c75`.

- Source and generated artifact checks, run `37221379382`: **PASS** on Ubuntu and Windows. The full `python -m pytest -q` step completed successfully on both runners, alongside correctness diagnostics, identity guard, generated artifact check, and clean-diff check.
- ManaEngine experimental, run `37221379325`: **PASS** on Ubuntu and Windows. Both release builds, CTest, and Python adapter/policy schema tests completed successfully.

The hosted checks ran against the implementation commit above. This completion-record-only follow-up does not change simulator code or test inputs.
