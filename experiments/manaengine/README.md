# ManaEngine controlled prototype

This is an isolated C++20 backend experiment. RosettaStone stays the reference backend. This does not change profile evidence, declarations, registry, datasets, checkpoints, or training behavior.

## State and event contract

`EngineState` is authoritative inside the C++ session. Its exported `Observation` is converted at the Python boundary to the existing immutable player-visible `GameState`. Hidden deck identity/order, RNG, pending triggers and choice continuation are never exported. Legal actions are projected as ordinary ManaMind dictionaries and contain entity handles only for applying actions.

Prototype event pass:

1. Resolve queued triggers FIFO.
2. Remove all currently dead minions in player/board order.
3. Queue and resolve their deathrattles FIFO.
4. Repeat until both queues and death set are empty.

`clone()` is a deep value-copy of all session state, including the `std::mt19937_64` state and pending choice. Choice is a typed continuation (`BuffSelectedMinion`) with options computed from the current board. This is deliberately not the full Hearthstone event/death/choice specification.

## Scope

Tier A/B roots are selected at run time by `scripts/select_roots.py` from the pinned Meta Profile card matrix, package evidence, and canonical Standard registry. The current selection is 18 (3 Tier A, 15 Tier B). Tier C is not included in parity. The prototype choice fixture is a test scenario only; it is not a collectible Standard card and contributes no root/parity count.

Deck summons filter the complete live deck by the card's declared current cost/type predicate, then use seeded RNG. The pool is never reduced to only roots with implemented ManaEngine effects. Unsupported card definitions encountered in a generated pool remain an explicit limitation.

## Build

Windows (run in a Visual Studio 2022 x64 Native Tools terminal):

```powershell
$pybindDir = & E:\ManaMind\.venv\Scripts\python.exe -m pybind11 --cmakedir
cmake -S experiments/manaengine -B experiments/manaengine/build-release -G Ninja -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR=$pybindDir -DPython_EXECUTABLE=E:/ManaMind/.venv/Scripts/python.exe
cmake --build experiments/manaengine/build-release
ctest --test-dir experiments/manaengine/build-release --output-on-failure
```

On Linux/macOS, use an ordinary CMake C++20 toolchain plus an installed `pybind11` CMake package and Python development headers. The core library and native tests have no Rosetta/vcpkg dependency.

Python import uses `src/manamind/integrations/manaengine/engine.py`; set `PYTHONPATH=src` when running outside an editable install.

## Adapter smoke

After building the extension, use `ManaEngineSession` with the same deck IDs and player-class arguments as the Rosetta `SimulatorSession`. The returned `observation()` is the existing immutable visible `GameState`; `legal_actions()` returns ManaMind action dictionaries, and `clone()` creates an independent branch. Set `MANAMIND_ROSETTA_BRIDGE` only when running side-by-side parity from a worktree that does not have the Rosetta submodule initialized.

The current prototype only implements Mage hero power. Its card behavior catalog covers the 18 selected Tier A/B roots plus the generated cards and test fixtures named in `data/card_abilities.json`. It does not verify every possible generated or randomly selected card outcome, enforce deck construction rules in the C++ core, implement mulligan, or provide full Hearthstone event semantics. The dynamic deck selectors operate on the complete current deck and preserve their predicates; an unsupported selected card's subsequent behavior remains outside this prototype's parity claims.
