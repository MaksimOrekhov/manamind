# Standard capability package: Hammer of Twilight Deathrattle

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01. Pool snapshot: `standard_registry_20261001_v1`.

## Change

Added `CORE_OG_031` Hammer of Twilight to the allowlisted effect-composition declaration. Breaking the weapon summons one `OG_031a` Twilight Elemental. The token is present in the pinned RosettaStone card resources as a textless 4/2 Elemental. The generator checks the dependency metadata and exact effect/dependency match. Its Deathrattle activation accepts only MINION and WEAPON card types with Deathrattle rules text.

## Evidence

- Generator completed with 18 allowlisted card declarations.
- Native effect-composition suite: **18 cases / 118 assertions passed**. The added scenario plays Hammer, brings its durability to one, breaks it with a hero attack, and checks the resulting 4/2 body.
- Bridge smoke: Standard deck validation, session creation, opening hand and legal actions passed for the Shaman card.
- Registry builder and focused registry suite: **14/14 passed**. Inventory: 1,185 roots, 167 direct + 92 generated registrations, 926 text-bearing roots without detected registration, 159 known non-root nodes, 310 heuristic dynamic-pool signals, 5 current scoped rules verifications, 0 complete root closures and 0 training-eligible roots.

## Scope and limits

The scenario verifies the weapon breaking and the named summon in an open-board state. It does not verify summon behavior on a full board, replacement of an existing weapon, silence or other deathrattle interactions. This entry has no independent fingerprinted rules evidence and remains `IMPLEMENTED_UNVERIFIED`; the whole Standard pool remains blocked from training.
