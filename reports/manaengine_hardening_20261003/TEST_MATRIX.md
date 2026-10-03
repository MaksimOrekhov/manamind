# Phase 2 test matrix

## Local environment

- Windows 11, AMD64 Family 25 Model 97; Visual Studio Build Tools 2022 x64 / MSVC 19.44; CMake Ninja Release; CPython 3.12.
- Rosetta parity bridge: `0b27fec85b288996535c543b2e633c85ce73d68c` from the existing `E:\ManaMind` checkout. No Rosetta source was changed.
- Build command: configure the already pinned `experiments/manaengine/build-release` with the repo venv's `pybind11 --cmakedir`, then `cmake --build ...` inside `VsDevCmd.bat -arch=x64`.

## Results

| Layer | Result | Scope |
|---|---:|---|
| ManaEngine Release native build | PASS | core, pybind module and native test executable |
| CTest | PASS, 1/1 | 19 scenario groups, 343 assertions |
| Bounded invariant/action smoke | PASS | 250 seeds × up to 40 transitions; every currently advertised action is applied on a clone and checked before the selected action is advanced |
| Adapter + policy + schema tests | PASS, 20 | `experiments/manaengine/tests/test_adapter.py`, `tests/test_pipeline.py`, and schema version regression |
| Python tests without Rosetta submodule-dependent modules | PASS, 39 | Remaining repository Python tests after excluding the four modules that require the missing checkout resource |
| Ruff | PASS | all changed Python modules/scripts listed in the command output |
| Rosetta shared-contract parity | PASS, 2 checkpoints | opening state/actions; after Violet Spellwing state/actions |
| Ubuntu / macOS native CI | PENDING | workflow is added but has not run on GitHub yet |

The unfiltered Python suite was attempted with a writable ignored temp root: **52 passed, 3 failed, 26 errored**. All 29 failures/errors are in registry/profile/card-family modules that read the unpopulated `vendor/RosettaStone/Resources/cards.json` in this isolated worktree; no ManaEngine test failed. The available subset and changed schema were rerun separately. The schema assertion still expecting encoder version 7 was corrected to 8; its targeted test passes.

## Focused semantic expectations

Independent assertions (expected values are encoded in the native scenarios; Rosetta is not used to generate expectations):

- Frostbolt: 30 → 27 hero health, hero becomes frozen, cannot attack on the next own turn, thaws after that missed opportunity. A minion also cannot attack while frozen and thaws after its opportunity.
- Raging Felscreamer: next Demon cost 5 → 3; discount survives two turn transitions and an unrelated minion play, then is consumed by the Demon.
- Weapon: initial current durability exports as 2; attack makes it 1 while total attack remains weapon 3 + temporary 2; at zero durability weapon leaves play and temporary attack 2 remains.
- Runtime state: granted Taunt appears in observation and clone; silencing removes active Taunt and unlocks hero target; clone remains unchanged.
- Dynamic pool: eligible candidates are selected from the current complete deck predicate. No supported-only filtering is introduced.
- Simultaneous deaths: Hellfire kills two Violet Spellwings; each owner receives its Arcane Missiles Deathrattle result.
- Generated lifecycle: First Flame creates Second Flame; playing Second Flame deals its own declared 2 damage.
- Unsupported branch: unknown ability is rejected at catalog load; unsupported card in the active hand is rejected; generated unsupported outcome marks the branch invalid and raises typed failure.
- RNG seed 7 raw vector: `13915952638675311015, 17511516338625233250, 2165911192842364878, 16452894106784333046`.
- RNG bounded picks for bounds `[2,3,10,7]`: `[1,0,8,2]`. Five-card Fisher-Yates order: `POOL_LOW_B, TEST_DEMON, TEST_FILLER, POOL_HIGH, POOL_LOW_A`.

## Parity boundary

The direct comparison checks only fields both backends actually export. Rosetta's current bridge lacks `hero_frozen`; it reports some unsupported/unknown flags as `False`; ManaEngine preserves unknown as `None`. Those fields are excluded from the shared-contract comparator. Current durability remains compared where it applies to a Weapon. A parity pass is scoped evidence for these two snapshots, not proof for all 18 roots or every lifecycle path.

## CI added

`.github/workflows/manaengine-experimental.yml` runs the same Release CMake build, native CTest, Python adapter, policy and golden RNG tests on `windows-latest`, `ubuntu-latest`, and `macos-latest`. Its hosted result is a required follow-up before Phase 2 acceptance can change from `KEEP_EXPERIMENTAL`.
