# Standard capability batch: Voidlord Deathrattle

Date: 2026-10-01. Snapshot: `standard_registry_20261001_v1`.

## Change

Added `CORE_LOOT_368` Voidlord to the allowlisted effect-composition generator. On death, it summons three `CS2_065` Voidwalkers. The dependency is explicit and must resolve to the existing registered MINION CardDef. The generated definition attaches the task as a Deathrattle rather than a play task.

This also adds a narrowly validated `DEATHRATTLE` activation to the composition route. Other activations and operations remain independently allowlisted; no general rules interpreter was added.

## Evidence

- Native effect-composition suite: **17 test cases / 113 assertions passed**. The independent scenario plays Voidlord, kills it, then checks exactly three summoned 1/3 Taunt minions.
- Bridge smoke: Standard deck validation, session creation, opening hand and legal actions passed for `CORE_LOOT_368`.
- Registry builder and focused registry suite: **14/14 tests passed**. Inventory is 1,185 roots, 167 direct + 91 generated definitions, 927 text-bearing roots without detected registration, 158 known non-root nodes and 310 heuristic dynamic-pool signals. There are zero complete closures and zero training-eligible roots.

## Scope

The scenario verifies this Deathrattle and its named token dependency in an open-board state. It does not verify the entire death-resolution ordering system, full-board outcomes, or all interactions affecting summon availability. The card remains `IMPLEMENTED_UNVERIFIED` and Standard training remains blocked.
