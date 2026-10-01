# Work session checkpoint — 2026-09-30

## Current direction after strategy review

Follow [STANDARD_REGISTRY_PLAN_20260930.md](STANDARD_REGISTRY_PLAN_20260930.md), milestones 1–6, before another wave of card implementations. The full Standard snapshot and reachable dependencies define scope; the five lists are control/regression inputs. The older Chillmaw resume list below is parked, not the next action.

Later in this session, bridge CMake was updated to include the existing Python 3.12 development headers from `build-mana-ninja/python312-dev/include`. A rebuild outside the VS 2022 Developer environment selected VS 2015 for vcpkg and failed; rerunning inside VS 2022 restored the dependencies and successfully linked the primary `mana_rosetta_bridge.cp312-win_amd64.pyd`. Python adapter `make_sample_game_state()` returned `GameState` at turn 1. The earlier duplicate `Choice::~Choice()` linker error did not reproduce; archive inspection showed one definition and multiple undefined references. This smoke does not certify all five decks or the new Chillmaw implementation.

The subsequent incremental `UnitTests` build failed because Chillmaw's new test used a const CardDef with non-const Power accessors. That test declaration was changed to non-const; compilation and behavior scenarios were not rerun before the user paused card implementation. Chillmaw remains unverified. These later observations supersede the tooling/no-new-results statements retained below.

## Completed before this checkpoint

- Fixed the MSVC/Ninja `/showIncludes` prefix in `vendor/RosettaStone/CMakeLists.txt`. With the correct localized prefix, Ninja dependency scanning reports valid dependencies instead of retaining stale object files.
- Rebuilt the Python 3.12 RosettaStone library from refreshed C++ source timestamps, linked `mana_rosetta_bridge`, and completed a bridge smoke. The smoke loaded the rebuilt extension, validated two simple decks, and started a simulator session.
- The five selected deck validations still have seven missing registrations across Dragon Warrior (1), Attack Druid (3), and Quest Priest (3); the two Warlock lists validate. This is registration status only, not a rules-correctness or training gate.

## Current in-progress card

- Added a ManaMind-owned `CORE_AT_123` Chillmaw definition in `ManaMindDragonPoolCardsGen.cpp`. It uses the existing `IsHoldingRace(Race::DRAGON)` condition and `DamageTask(ALL_MINIONS, 3)` in a Deathrattle task list.
- Added a focused metadata/registration/task-shape assertion to `ManaMindDragonPoolCardsTests.cpp`.
- This card is **not yet verified**. The current bridge binary predates this new definition. Compilation, focused UnitTests, independent behavior scenarios (with and without a Dragon in hand), bridge deck validation, and audit regeneration remain outstanding.

## Resume steps

1. Build `UnitTests` and `mana_rosetta_bridge` incrementally from the `vendor/RosettaStone/build-mana-py312` and `integrations/rosettastone/build` trees; fix any compile or link failures.
2. Add/run independent Chillmaw scenarios proving no damage without a Dragon in hand and 3 damage to all minions when holding a Dragon. Confirm that the damage is non-spell damage.
3. Run the focused Dragon pool test and bridge smoke, then regenerate the card-support and Dark Gift audits so the new registration is counted.
4. Update the card-support plan, architecture-review follow-up, and `AGENTS.md` with the linker fix, Chillmaw evidence, and remaining selected-deck gates.
5. Do not train or evaluate a model until the complete selected pool passes its documented gates.

## Tooling limitation observed

During this continuation, `exec_command` repeatedly failed before launching a process with `helper_unknown_error: setup refresh had errors`. A few read-only commands succeeded intermittently, but build, Git status, and verification commands could not be run after the Chillmaw edit. Treat its source change as unverified and resume with the build steps above when command execution is available.

Continuation attempts on 2026-09-30 reproduced the same launcher failure, including for `git status` and a trivial `echo`; only `Get-Location` and occasional direct file reads ran. No compilation or runtime result has been added since this checkpoint.
