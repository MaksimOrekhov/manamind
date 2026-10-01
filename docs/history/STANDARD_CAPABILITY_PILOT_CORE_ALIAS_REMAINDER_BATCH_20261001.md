# Core alias remainder batch — 2026-10-01

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

## Scope

Added fourteen exact metadata-linked Core-to-legacy aliases through the existing bounded alias generator:

| Core ID | Source ID |
|---|---|
| `CORE_BT_120` | `BT_120` |
| `CORE_BT_321` | `BT_321` |
| `CORE_BT_493` | `BT_493` |
| `CORE_DAL_575` | `DAL_575` |
| `CORE_DAL_720` | `DAL_720` |
| `CORE_DRG_024` | `DRG_024` |
| `CORE_EX1_100` | `EX1_100` |
| `CORE_KAR_057` | `KAR_057` |
| `CORE_ONY_022` | `ONY_022` |
| `CORE_REV_308` | `REV_308` |
| `CORE_SCH_717` | `SCH_717` |
| `CORE_ULD_152` | `ULD_152` |
| `CORE_ULD_165` | `ULD_165` |
| `CORE_ULD_280` | `ULD_280` |

Each declaration passed checks for the metadata copy DBF, normalized rules-text equality, an existing source CardDef, dependency evidence, and unique ownership. `CORE_CS2_004 -> CS2_004` was reviewed but excluded because the effect-composition generator already owns `CORE_CS2_004`. The alias generator now rejects card IDs owned by other generated manifests before emitting output.

## Verification

- Alias generator emitted 40 total registrations after this batch.
- Native CardDef parity covered all 40 IDs: 7 focused cases, 516 assertions.
- The 14 new IDs passed bridge deck validation, session creation, observation, and legal-action enumeration.
- Related prior package verifiers were rerun after the library/bridge rebuild: after-attack draw (3 cases / 25 assertions), repeated-trigger draw (4 / 34), and filtered-school draw (3 / 27). Known Death Knight setup limitations remain for selected session smoke cases.
- `scripts/build_standard_registry.py` regenerated the registry and `pytest -q tests/test_standard_registry.py` passed (7 tests).

## Coverage meaning and limits

These fourteen records are `IMPLEMENTED_UNVERIFIED`. Metadata parity confirms that the generated Core definition points at the matching legacy implementation; bridge smoke confirms loading and legal-action plumbing. Neither independently establishes that every effect matches current Hearthstone rules. The generated alias manifest flags seven dynamic pool dependencies across the alias cohort, including Discover and random-card outcomes. Those pools still need exact predicates, memberships, and runtime parity before closure.

The updated registry snapshot has 1,185 Standard roots; 167 direct and 52 generated registrations; 963 text-bearing roots without detected registration; 127 known non-root dependency nodes; 306 heuristic dynamic-pool signals; 9 current scoped verifications; 0 complete root closures; and 0 training-eligible roots. Full Standard training remains blocked.

## Changed artifacts

- `scripts/generate_core_card_aliases.py`
- `integrations/rosettastone/card_rules/core_aliases.v1.json`
- `integrations/rosettastone/card_rules/core_aliases.generated.json`
- `vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp`
- `scripts/verify_core_alias_uld133.py`
- Generated registry and reports under `data/standard_registry/` and `reports/standard_registry_20261001/`
