# RosettaStone native integration

This guide describes the implemented bridge and configured Windows build. Product/model requirements live in [README](../README.md); card-support workflow and admission live in [the package process](CAPABILITY_PACKAGE_PROCESS.md) and [Standard registry](STANDARD_REGISTRY.md). Historical card-by-card queues and pilot permissions are inactive.

## Source and metadata

The gitlink pins a published commit in `MaksimOrekhov/RosettaStone`. Upstream is `utilForever/RosettaStone`; read the actual revision from Git/current registry rather than a hardcoded upstream SHA. Recursive clone includes the engine changes; do not apply the old integration patch on top.

ManaMind uses a separate pybind11 module, `mana_rosetta_bridge`, because upstream `pyRosetta` does not expose the gameplay API needed here. The Python adapter is `src/manamind/integrations/rosettastone/rosettastone.py`.

The native loader merges the profile-generated `Resources/cards.standard_current.json` into the historical database, preserving required non-collectible entries. Current set support and retired-Core reclassification are implemented. Metadata alone does not implement effects. Rebuild shared profile outputs through `scripts/build_standard_profile.py`; see the registry guide for approved updates.

## Configured native build

The current bridge CMake configuration is Windows-specific. A clean source clone does not contain build trees, vcpkg dependencies or Python development headers; the source CI does not provide a turnkey native bootstrap.

Required configured inputs:

- Visual Studio C++ Build Tools, x64 developer environment, CMake (minimum declared in CMakeLists), Ninja, Python 3.12 development files and pybind11.
- vcpkg packages `effolkronium_random`, `nlohmann_json` and the pybind11 CMake package.
- Core tree `vendor/RosettaStone/build-mana-py312`, producing `lib/RosettaStone.lib` and `bin/UnitTests.exe`.
- Python development headers at `vendor/RosettaStone/build-mana-ninja/python312-dev/include/Python.h`, required by the bridge CMake file.
- Bridge tree `integrations/rosettastone/build`, configured with `ROSETTA_SOURCE_DIR`, the dependency toolchain and the intended Python interpreter/development library.

For the existing configured workspace, build affected consumers and record identity:

```powershell
.\.venv\Scripts\python.exe scripts/build_native_identity.py
```

This builds RosettaStone and UnitTests before linking the bridge, checks that source/profile inputs stayed unchanged, and writes ignored `integrations/rosettastone/build/execution_identity.json` with binary hashes. It does not configure missing build trees.

Do not assume bridge-only relinking updates the imported core library. New cpp files require CMake source discovery/configuration; headers, enums and ABI changes require rebuilding affected consumers. Internal tag numeric identities must be preserved. Investigate dependency tracking before using a clean build.

The canonical module is `integrations/rosettastone/build/python/mana_rosetta_bridge*.pyd`. The adapter selects one compatible module there, or an explicitly selected path via `MANAMIND_ROSETTA_BRIDGE`; it does not choose the newest alternate build. Evidence producers reject a loaded bridge differing from the recorded build.

```powershell
.\.venv\Scripts\python.exe -m manamind.integrations.rosettastone.rosettastone
.\.venv\Scripts\python.exe scripts/verify_instance_observations.py
```

The second command checks actual modified hand/weapon observations against the Power.log import path. Focused family verifiers have their own scenarios and scoped evidence. A successful build/import is not complete rules coverage.

## Bridge API

- `inspect_decks(...)`: inspect a deterministic opening and legal actions for two 30-card lists; it does not maintain a persistent match.
- `validate_deck(...)` / `validate_decks(...)`: check deck size, known/collectible IDs, class, pinned set membership, DBF copy limits and conservative text-bearing CardDef presence. Empty messages mean passing those engine checks, not full-profile admission. The external dated ban snapshot is not enforced by this runtime validator.
- `make_simple_test_deck(...)`: controlled low-cost minion fixtures, not competitive lists.
- `SimulatorSession(...)`: persistent engine game. `shuffle`, `random_start` and `random_seed` support reproducible variations. Use `observation(perspective="ACTIVE"|"PLAYER1"|"PLAYER2")`, `legal_actions()` and `apply_action(action)`. Only submit a currently returned action; stale/illegal actions are rejected.
- `is_complete`, `needs_choice`, `result`: terminal/choice state and `PLAYER1_WIN`, `PLAYER2_WIN`, `DRAW` or no result.

| Action | Main fields |
|---|---|
| PLAY_CARD | hand_index, card_id, field_position, target_entity_id |
| ATTACK | attacker_entity_id, target_entity_id |
| HERO_POWER | target_entity_id when required |
| CHOOSE_CARD | choice_entity_id and offered visible card features |
| ACTIVATE_LOCATION | source_entity_id, card_id, target_entity_id when required |
| TRADE_CARD | hand_index, card_id |
| END_TURN | no selection |

Generic hand-choice windows and reviewed special choices are exposed; other choice types remain subject to explicit support. Attack/target and full shared-board legality must agree with final engine validators. Selection/activation API existence does not certify every card using it.

Observations contain SELF hand and public board/resources/Locations/weapons/hero powers, with current instance stats separate from base metadata. Opponent hidden hand and deck identities remain absent. Engine entity IDs are action handles only.

## Current limitations

Read the profile-selected report for card/closure/evidence/admission counts. Full Standard remains unadmitted; historical Mother Drake and five-list results do not establish readiness.

Death Knight deck legality has scoped checks, but default hero/hero-power session initialization remains missing. Dynamic outcomes, special choices, interactions and complete action coverage still need reviewed package/closure gates. The runtime conservative registration gate is weaker than canonical training admission.

The seeded weak baseline and policy tools can produce experimental trajectories, but they are biased data sources. Incomplete/unsupported outcomes must not become labels. Match-level splits keep both perspectives together. Do not restart training/evaluation from commands in old pilot records.

## Licensing and history

RosettaStone is third-party AGPL-3.0 source. Preserve its notices and review distribution obligations before distributing a combined application. [Upstream repository](https://github.com/utilForever/RosettaStone).

Dated native/scenario/build results are retained in [history](history/README.md); they are evidence with scope and limitations, not an active integration queue.
