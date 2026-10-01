# Standard capability package: turn-end damage

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01. Pool snapshot: `standard_registry_20261001_v1`.

## Change

Added `CATA_475` Scalebreaker Bulwark to effect-composition. Its `TURN_END` trigger deals 2 damage to `ENEMIES`—the opponent's hero and minions—at the controller's turn end. This is a narrowly allowlisted trigger activation; unknown activation types remain rejected.

## Evidence

- Generator completed with 21 allowlisted effect-composition definitions.
- Native composition suite: **21 cases / 141 assertions passed**. The independent scenario places a Yeti on the opponent's field, plays the Bulwark, ends its controller's turn, and checks 2 damage to the enemy minion and hero while the friendly hero remains undamaged.
- Bridge smoke: Standard deck validation, session creation, opening hand and legal actions passed for Paladin.
- Registry builder and focused suite: **14/14 passed**. Snapshot: 1,185 roots, 167 direct + 103 generated registrations, 915 text-bearing roots without detected registration, 171 known non-root nodes, 317 heuristic pool signals, 6 current scoped verifications, 5 historical stale-evidence entries, 0 complete closures and 0 training-eligible roots.

## Limits

The scenario checks timing and target set in one controlled position. It does not cover immunity, damage prevention, deathrattle interactions or full match behavior. `CATA_475` remains `IMPLEMENTED_UNVERIFIED`; full Standard training remains blocked.
