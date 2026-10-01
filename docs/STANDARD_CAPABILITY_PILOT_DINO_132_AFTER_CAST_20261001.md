# Triggered effect composition follow-up — 2026-10-01

## Scope

The bounded effect-composition generator now covers these additional roots:

- `DINO_132` Asphyxiodon: its own-turn-end trigger selects one random enemy minion and deals 5 non-spell damage. Taunt remains sourced from card metadata.
- `CORE_RLK_083` Deathchiller: after a friendly spell is cast, deal 1 non-spell damage to two independently selected random enemies. Repeated targets are allowed.
- `END_026` Fragment of Nothing: after a friendly spell targets a minion, draw one card. This uses RosettaStone's existing `SelfCondition::IsSpellTargetingMinion()` condition; a spell targeting a hero does not draw.
- `TLC_256` Marshland Thresher: after its controller casts a spell, it gains Divine Shield. An enemy spell does not activate it.
- `TIME_015` Hardlight Protector: Battlecry restores 3 Health to its controller's hero and grants that hero Divine Shield.
- `TLC_401` Bonechill Stegodon: Deathrattle deals 6 non-spell damage in three independent random hits to enemy characters.
- `RLK_223` Thassarian: Battlecry and Deathrattle each deal 2 non-spell damage to a random enemy. The card's Reborn keyword remains metadata-driven; the native scenario confirms the Deathrattle occurs before its Reborn copy returns at 1 Health.

The `AFTER_CAST` activation is constrained to reviewed rules-text patterns and uses the engine's existing event implementation. No new event interpreter or card-specific engine rule was added.

## Verification

- Independent native scenarios cover trigger ownership, target conditions, exact damage counts, Divine Shield, and hero healing.
- Native effect-composition suite: 43 cases / 276 assertions passed.
- Additional native filtered suite including the keyword-only checks: 87 cases / 1,388 assertions passed. `CORE_EX1_250` preserved TAUNT and caused exactly 2 Overload mana to be owed after play.
- Bridge smoke: all non-Death-Knight entries passed Standard deck validation, session creation, opening-hand and legal-action checks. Death Knight entries passed deck validation; session setup remains unavailable, so those cases did not enter a game.
- Registry tests: 14 passed. Latest snapshot: 1,185 roots; 167 direct + 127 generated; 891 roots without detected registration; 171 known non-root dependency nodes; 317 heuristic dynamic-pool signals; zero complete closures and zero training-eligible roots.

## Limits

All added roots remain `IMPLEMENTED_UNVERIFIED`; scenarios cover only the documented effects and scopes, not complete dependency closures. None is admitted to Standard training. Death Knight bridge setup remains an independent blocker.
