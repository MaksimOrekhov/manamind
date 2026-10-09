# RosettaStone legacy archive

Inert, historical data from the Simulator-first phase, when RosettaStone (a C++ Hearthstone simulator in a Git submodule) was the reference backend. **None of it is consumed by active code, CI or tests.** It is kept so that the origin of old results in `reports/` and the frozen registry stays understandable.

RosettaStone, its C++ bridge (`integrations/rosettastone/bridge.cpp`, `CMakeLists.txt`, the engine patch), the Python adapter (`manamind.integrations.rosettastone`), the card-rule generators (`scripts/generate_*.py`, `scripts/card_rules/`), scenario verifiers (`scripts/verify_*.py`), the registry builder (`scripts/build_standard_registry.py`) and the evidence tooling were removed in MODEL-FIRST-MIGRATION-1. All of it is recoverable from Git history at commit `5961822` (the last commit before the migration). See [the migration report](../../../reports/model_first_migration_1/README.md) for the full list.

## Contents

`card_rules/` — the reviewed declarations (`*.v1.json`), generated manifests (`*.generated.json`), capability inventory and scoped verification evidence (`*.evidence.json`) as they were under `integrations/rosettastone/card_rules/`. They were moved byte-for-byte. Historical configs and reports that cite `integrations/rosettastone/card_rules/<file>` mean the file of the same name here.

## Caveats

- Evidence here certified RosettaStone behaviour at a specific source/build identity. It does not certify ManaEngine and cannot be regenerated without the removed engine.
- `data/cards/standard_registry_20261001_enUS.json` and `reports/standard_registry_20261001` are frozen snapshots built from these inputs; see `configs/standard_profile.json` (`historical_registry`).
- Do not use anything here to choose cards or authorize training.
