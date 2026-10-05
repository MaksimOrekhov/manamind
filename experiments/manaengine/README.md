# ManaEngine simulator backend

ManaEngine is the primary forward simulator development backend, with strict
bounded behavior and explicit evidence debt. It is not a complete Hearthstone
rules implementation and is not currently admitted for canonical training.
RosettaStone remains a reference/regression backend and historical source of
implementation evidence. See the [partial-simulator architecture](../../docs/PARTIAL_SIMULATOR_ARCHITECTURE.md)
for the implemented behavior, accepted target and future work boundaries.

Runtime execution, evidence status, dependency closure and training admission
are separate. For example, the Vulcanos Fire pool can run using a bounded
`REVIEWED_INFERRED` manifest while each sample carries explicit evidence debt;
that does not make membership exact, promote canonical evidence or permit
training. Unsupported outcomes are not removed from pools and are not rerolled.
The simulator fails closed when a selected transition is unsupported.

The implementation described below is scoped to its current card catalog and
session lifecycle. Terms such as a typed `SimulationAttempt`, live-root import,
or `Q_fallback` refer to future architecture unless a later section identifies
an implemented API. These docs do not authorize a Phase 4K implementation or
training run.

## State and event contract

`EngineState` is authoritative inside the C++ session. Its exported `Observation` is converted at the Python boundary to the existing immutable player-visible `GameState`. Hidden deck identity/order, RNG, pending triggers and choice continuation are never exported. Legal actions are projected as ordinary ManaMind dictionaries and contain entity handles only for applying actions.

Prototype event pass:

1. Resolve queued triggers FIFO.
2. Remove all currently dead minions in activation/entry order.
3. Queue and resolve their deathrattles FIFO.
4. Repeat until both queues and death set are empty.

`damage_group_local_v1` separates synchronous damage mutation from reactions.
Ordinary admitted minion areas apply every packet before dispatching successful
damage events in entry order. Sequential instructions and missiles complete each
packet's reactions before continuing. The existing outer phase owns deaths;
group completion never calls the global death drain. Value-owned internal frames
are hidden from observations, and public action/observation/clone access requires
quiescence. Unsupported branches preserve diagnostic mutations and RNG, reject
continuation, and never become successful terminal episodes.

Generation (TakesDamage) reactions inside hero-containing areas, combat and compound
Secrets remain guarded where ordering is unreviewed. A first-spell-damage (Raincaller)
reaction is a separate, order-insensitive family and is supported alongside them; one
entity being both consumer and watcher stays unsupported.
Vulcanos's Fire pool can now be sampled from an explicitly `REVIEWED_INFERRED`
33-card manifest. This permits bounded simulation while attaching
`FIRE_POOL_MEMBERSHIP_INFERRED` evidence debt on each sample; it does not
establish exact Hearthstone membership, rules verification, or training
eligibility. The unresolved membership audit remains authoritative. Scope,
tests and remaining limits are recorded in
`reports/manaengine_damage_group_20261005/COMPLETION.md`,
`REMEDIATION_SONNET.md` and the mortality table in `MORTALITY_POLICY.md`.

Random-distinct Damage (Phase 4I.1, bounded): the declarative selectors
`RANDOM_DISTINCT_ENEMY_CHARACTERS` / `RANDOM_DISTINCT_ENEMY_MINIONS` with `random_count` (1..3) and
`exclude_previous_target` sample `min(random_count, n)` enemies without replacement by a simulator-owned
partial Fisher-Yates (`bounded_random(n-i)`, no reroll, `n = 0` draws nothing) over a stable candidate
snapshot (enemy hero, then enemy board left to right; mortally wounded minions and the excluded explicit
target removed; Stealth, Immune and Divine Shield stay eligible). Extras are one ApplyAll damage group
with a single `CURRENT_AT_STEP` Spell Damage evaluation; the outer spell boundary owns deaths. The selector
is valid only for a spell Damage step and malformed combinations fail closed at catalog load.
Arcane Barrage (`TIME_855`) is declared with it (explicit enemy damage 3, then two other random enemies for 2)
and records `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` whenever its extras instruction executes, including
with zero candidates. The constraint is a typed declaration on the step, not a card-ID branch, covers only
hero membership, distinctness and insufficient-candidate behavior (not topology), never poisons the branch and
blocks canonical training admission. A generation consumer beside a hero extra stays guarded. The rules contract
and its evidence debt are in `reports/manaengine_arcane_barrage_20261005/ARCANE_BARRAGE_RULES_EVIDENCE.md` and
`IMPLEMENTATION_COMPLETION.md`. Focused native run: `manaengine_tests --arcane-barrage`.

Failure funnel: `apply_action()` rejects illegal input before any mutation and leaves the
session valid. Any failure after execution starts poisons the session (first reason kept),
clears hidden frames and rethrows. A poisoned session refuses `legal_actions`, `clone`,
`observation`, `result`, `is_complete`, `needs_choice`, `choice_options` and further actions;
`is_valid`, `unsupported_outcome`, `evidence_constraints` and `diagnostic_trace` stay available
as diagnostics only. A queued EOT source that is mortally wounded but still in Play resolves
under the phase model and records `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED` until replay evidence exists.

`clone()` is a deep value-copy of all session state, including the `std::mt19937_64` state and pending choice. Choice is a typed continuation: the native board-choice fixture selects a current friendly minion, while the Phase 3 `CORE_GIL_836` Discover samples the complete pinned Standard class/neutral Battlecry-minion pool and generates the selected card into hand. Unsupported pool outcomes remain visible and invalidate the branch when selected. The precise bounded contract is in `reports/manaengine_hardening_20261003/PACKAGE_B_COMPLETION.md`. This is deliberately not the full Hearthstone event/death/choice specification.

Native sessions also expose an optional diagnostic event trace through `ManaEngineSession.set_diagnostic_trace(True)` and the read-only `diagnostic_trace` tuple. It is disabled by default, is not part of the observation/policy input, and is copied by value with session clones.

## Scope

Tier A/B roots are selected at run time by `scripts/select_roots.py` from the pinned Meta Profile card matrix, package evidence, and canonical Standard registry. The baseline selection is 18 (3 Tier A, 15 Tier B); the additional Phase 3 Discover root is documented separately and does not change the canonical registry. Tier C is not included in parity. The board-choice fixture is a test scenario only; it is not a collectible Standard card and contributes no root/parity count.

Deck summons filter the complete live deck by the card's declared current cost/type predicate, then use seeded RNG. The pool is never reduced to only roots with implemented ManaEngine effects. Unsupported card definitions encountered in a generated pool remain an explicit limitation.

## Build

Windows (run in a Visual Studio 2022 x64 Native Tools terminal):

```powershell
$pybindDir = & E:\ManaMind\.venv\Scripts\python.exe -m pybind11 --cmakedir
cmake -S experiments/manaengine -B experiments/manaengine/build-release -G Ninja -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR=$pybindDir -DPython_EXECUTABLE=E:/ManaMind/.venv/Scripts/python.exe
cmake --build experiments/manaengine/build-release
ctest --test-dir experiments/manaengine/build-release --output-on-failure
```

On Ubuntu/Linux, use an ordinary CMake C++20 toolchain plus an installed `pybind11` CMake package and Python development headers. The core library and native tests have no Rosetta/vcpkg dependency.

Python import uses `src/manamind/integrations/manaengine/engine.py`; set `PYTHONPATH=src` when running outside an editable install.

## Adapter smoke

After building the extension, use `ManaEngineSession` with the same deck IDs and player-class arguments as the Rosetta `SimulatorSession`. The returned `observation()` is the existing immutable visible `GameState`; `legal_actions()` returns ManaMind action dictionaries, and `clone()` creates an independent branch. Set `MANAMIND_ROSETTA_BRIDGE` only when running side-by-side parity from a worktree that does not have the Rosetta submodule initialized.

The current session adapter admits only Mage hero-power games. Its bounded behavior catalog covers the selected Tier A/B roots plus the Phase 3 `CORE_GIL_836` Discover root and generated cards declared in `data/card_abilities.json`. It does not verify every possible generated or randomly selected card outcome, enforce deck construction rules in the C++ core, implement mulligan, or provide full Hearthstone event semantics. Dynamic pools keep their complete declared predicates; selecting an unsupported result fails closed.
