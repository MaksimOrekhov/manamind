# ManaEngine simulator backend

ManaEngine is an **optional, independent simulator for bounded tactical
verification**, with strict bounded behavior and explicit evidence debt. Its
development is frozen under the Model-first strategy
([roadmap](../../docs/MODEL_FIRST_ROADMAP.md)): extend it only for a separate
task with a written Model-first benefit. It is not a complete Hearthstone rules
implementation, is not currently admitted for canonical training, and nothing in
Model-first training or live inference requires it. RosettaStone was removed
from the repository and is not a dependency or reference backend. See the [partial-simulator architecture](../../docs/PARTIAL_SIMULATOR_ARCHITECTURE.md)
for the implemented behavior, accepted target and future work boundaries.

Runtime execution, evidence status, dependency closure and training admission
are separate. For example, the Vulcanos Fire pool can run using a bounded
`REVIEWED_INFERRED` manifest while each sample carries explicit evidence debt;
that does not make membership exact, promote canonical evidence or permit
training. Unsupported outcomes are not removed from pools and are not rerolled.
The simulator fails closed when a selected transition is unsupported.

The implementation described below is scoped to its current card catalog and
session lifecycle. Phase 4K.1 implements the `SimulationAttempt` adapter API;
live-root import and `Q_fallback` remain future work. These docs do not
authorize additional Phase 4K implementation or training.

## Attempt API (Phase 4K.1)

`attempt_action(parent, action, perspective=None, retain_child=True)` checks
native legality by the six execution fields and applies the canonical native
action on a clone. It preserves parent state/RNG and exports from a fixed
root seat (`PLAYER1` or `PLAYER2`), resolved once from the acting parent when
omitted. `apply_action` keeps its existing post-action ACTIVE-seat behavior.

The frozen `SimulationAttempt` has four outcomes: `COMPLETED`,
`UNSIMULATABLE`, `ILLEGAL`, `ENGINE_DEFECT`. Only completion contains a
visible state and optional child. Only explicitly allowlisted unsupported/rule
reasons are eligible for future fallback; budgets are excluded. There is no fallback routing or scoring. Failure diagnostics contain
immutable scalar `NativeFailure` snapshots and strings/tuples, including failure
evidence and at most 32 trace rows.

Completed inferred Fire outcomes retain `FIRE_POOL_MEMBERSHIP_INFERRED` in
state/result evidence. Unsupported sampled outcomes fail without reroll and
carry failure evidence only in diagnostics. Neither changes training gates.
Phase 4K.1b implements four native failure kinds and 57 append-only codes.
Classification reads payloads only, with no message heuristic. Native exceptions
carry kind/code/detail/context and session `failure` exposes the stored record.
`EngineDefectError` subclasses `UnsupportedSimulationError`; legacy untyped
failures default to engine defects. A poisoned child is never exported.
`BudgetLimit` is not fallback eligible. No `Q_fallback` exists.

The failure inventory/source guard runs in Source CI. Test-only fault probes
are built under `BUILD_TESTING` as a separate extension; they add no production
cards or runtime invariant validator.

A retained child is full-information internal simulation infrastructure,
excluded from repr/equality; it is not a model feature or live observation.
An attempt outcome may itself depend on hidden state (for example an
unsupported opponent next draw). A chance transition is one sampled result,
not an expectation. No live-root use or live search is authorized.

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

Healing pipeline v1 (ENGINE-PRIMITIVE-1): all Health restoration (the `HEAL` step, Lifesteal damage packets and the
`HEAL_ENEMY_HERO` damage follow-up) goes through one native `apply_healing`. Each target receives its own packet:
`restored = min(base + controller healing bonus, own maximum Health - current Health)`; the bonus is an additive
player-owned integer (`GRANT_HEALING_BONUS`, persists for the game, stacks, independent of the creating minion) and applies
per packet, including each Lifesteal damage packet. New selectors are `ALL_FRIENDLY_CHARACTERS` (own hero, then own minions
left to right) and `EXPLICIT_FRIENDLY_CHARACTER` (legality and execution both enforce friendly-only). Hero maximum Health is
a separate field fixed at 30; no other start Health is admitted. An area or single heal that selects a character pending
death fails closed atomically (`HEAL_MORTALLY_WOUNDED_UNREVIEWED`); a caster with a bonus healing a character it does not
control fails closed (`HEALING_BONUS_SCOPE_UNREVIEWED`, evidence gap). There are no healing triggers. The bonus is deliberately
exported as an enchantment identity (none is fabricated; `active_effects` stays empty). It is the public nullable integer
`PlayerObservation.healing_bonus` (exact for both seats in ManaEngine, `None` = unknown in historical imports) and is not an
encoder feature, so Policy/Value checkpoints stay compatible. `HEAL_MINION_TO_FULL` is a packet of exactly the missing Health
through the same pipeline. Declared consumers: Moonwell
(`EDR_476`), Holy Nova (`CORE_CS1_112`), Greater Healing Potion (`CORE_CFM_604`), Cleansing Cleric (`CATA_216`). Focused
native run: `manaengine_tests --healing`; design record `docs/proposals/20261008_engine_primitive1_healing_v1.md`.

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

On Ubuntu/Linux, use an ordinary CMake C++20 toolchain plus an installed `pybind11` CMake package and Python development headers. The core library and native tests have no external engine or vcpkg dependency; no Git submodule is needed.

Python import uses `src/manamind/integrations/manaengine/engine.py`; set `PYTHONPATH=src` when running outside an editable install.

## Adapter smoke

After building the extension, use `ManaEngineSession` with deck IDs and player-class arguments. The returned `observation()` is the existing immutable visible `GameState`; `legal_actions()` returns ManaMind action dictionaries, and `clone()` creates an independent branch.

The current session adapter admits games whose two seats are Mage, Priest, Hunter or Warrior, each starting with its reviewed base Hero Power (Fireblast, Lesser Heal, Steady Shot, Armor Up!); every other class is rejected with `UNSUPPORTED_HERO_CLASS`, and a current power without a reviewed supported definition with `UNSUPPORTED_HERO_POWER`. This is a prototype-setup gate only: it does not import real-game state. Its bounded behavior catalog covers the selected Tier A/B roots plus the Phase 3 `CORE_GIL_836` Discover root and generated cards declared in `data/card_abilities.json`. It does not verify every possible generated or randomly selected card outcome, enforce deck construction rules in the C++ core, implement mulligan, or provide full Hearthstone event semantics. Dynamic pools keep their complete declared predicates; selecting an unsupported result fails closed.

## Engineering rules for the frozen engine

These rules moved here from the repository-wide working rules; they apply only when a separate task touches ManaEngine.

- Keep rules deterministic and strict. Fail closed when a transition is unsafe or unsupported; never fabricate a plausible Hearthstone transition. Resilience to incomplete coverage belongs above the engine, never in a second approximate rules engine.
- Keep runtime simulation, rules/evidence basis, dependency closure and canonical training admission separate. `REVIEWED_INFERRED` may authorize bounded runtime simulation with explicit evidence debt; it is not rules verification and does not grant canonical training eligibility.
- Dynamic generation membership comes from reviewed game rules and manifests, never implementation coverage. Do not prune pools, substitute supported outcomes or reroll an unsupported sampled result. A poisoned or partially mutated state is diagnostic only and cannot be a valid observation, search child or training sample. `ENGINE_DEFECT` must not silently become ordinary unsupported behaviour.
- Full-information simulator cloning is not authorization for real-game search; a reviewed information-set/determinization design is required first.
- Declarations are versioned and allowlisted: reject unknown operations, fields and symbols, invalid targets and unresolved dependencies. Never execute arbitrary code from declarations.
- Build the core before relinking the bridge; account for CMake source discovery when adding `.cpp` files; rebuild all affected consumers after header/enum/ABI changes; append internal tags to preserve numeric identities. Use clean builds only for diagnosed dependency/ABI problems.
- Native evidence requires the intended configured build and the actually loaded module identity. Invalidate dependent evidence when rules, capability contracts, source/build identity or pool predicates change.
- Family scenarios need independent expectations and negative/interaction tests; a smoke test derived from the same declaration is not rules evidence.

## Metadata provenance

Card metadata used by the engine comes from the pinned HearthstoneJSON snapshot `data/cards/source_snapshots/cards_collectible_20261001_enUS.json`, the Standard catalog, and the dependency files in `experiments/manaengine/data/`. The engine no longer reads any RosettaStone dump at runtime (the optional `vendor/RosettaStone/Resources/cards.json` gap filler was removed; for the current inputs it never contributed, because every engine record is already covered by the pinned files).

Three committed dependency identities were captured from RosettaStone's bundled `cards.json` rather than from HearthstoneJSON: `quick1_dependency_metadata.json` (`CS2_065`), `quick2_dependency_metadata.json` (`EDR_492t`) and `choice_mode_dependency_metadata.json` (one Living Roots token). **Their independent confirmation against HearthstoneJSON has not been performed** (it would need a new download, which the migration did not do). They are left byte-identical so that the capability fingerprint does not change; treat the three identities as unconfirmed-by-independent-source until someone re-captures them from a pinned HearthstoneJSON build.
