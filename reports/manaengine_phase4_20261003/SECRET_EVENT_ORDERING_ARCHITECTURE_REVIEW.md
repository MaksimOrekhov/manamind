# Phase 4 — Secret event ordering and implementation record

Date: 2026-10-04
Branch: `codex/manaengine-first-deck`
Architecture decision: `APPROVE_MINIMAL_SHARED_EVENT_SEQUENCE`

## Implemented boundary

ManaEngine adds typed Secret windows at existing lifecycle points and a monotonically increasing activation sequence for persistent reactive sources. The sequence is internal simulator state; it is not exported to GameState or Policy observations.

At opponent turn end, currently modeled board reactions and active Secrets are collected together and resolved in ascending activation sequence. Flames of Infinity uses this normal ordering. There are no FIRST/NORMAL/LAST classes and no card-ID ordering exception. Clone preserves the counter and stamps; leaving and re-entering the active zone assigns a fresh stamp. The existing FIFO trigger → death check → FIFO deathrattle → repeat loop remains the processing baseline.

## Typed windows and phases

| Window | Placement in the prototype lifecycle |
|---|---|
| `OPPONENT_CASTS_SPELL` | After card/mana commitment and cast-history increment; before the spell effect. Counterspell cancels resolution, while the cast remains counted. |
| `FRIENDLY_MINION_ATTACKED` | After target declaration and before combat damage; Oasis Ally summons Water Elemental. |
| `FRIENDLY_HERO_ATTACKED` | After attack declaration and before combat damage; Ice Barrier grants Armor. |
| `ENEMY_MINION_ATTACKS` | After attack declaration and before damage; Mystic Misdirection transforms the attacker and cancels that combat. |
| `OPPONENT_PLAYS_MINION` | After the minion's Battlecry processing; Explosive Runes damages the played minion if still available and sends excess to its hero. |
| `OPPONENT_TURN_ENDS` | Unified end-turn reaction collection, merged with currently modeled board sources by activation sequence. |

These are prototype lifecycle hooks, not a claim of complete Hearthstone event-order semantics. Reviewed scenarios cover the six current Standard Mage Secrets and the interactions listed above. Any newly encountered interaction that cannot fit these phases must be recorded as a limitation before extending the dispatcher.

## Pool, history, and information boundary

The pinned Standard Mage Secret pool has six collectible members: `CORE_BAR_812`, `CORE_EX1_287`, `CORE_EX1_289`, `CORE_LOOT_101`, `END_024`, and `JAIL_315`. Tricksy Improviser uses this full pool for each independent random cast; pool membership does not depend on implementation support or active copies. Duplicate-active selection follows ordinary activation failure behavior without resampling.

Generic `spells_cast_this_turn` state is incremented when a spell is committed, before Counterspell resolves. Tricksy checks this history without a card-ID condition. Observations expose Secret counts for both players and Secret identities only to their owner. The observation schema was bumped to 11; checkpoint loading uses the existing schema-version rejection for incompatible checkpoints. No activation sequence or opponent Secret identity enters Policy input.

## Prepare rule correction and unresolved legality

Prepare spends all remaining mana and applies a persistent discount of exactly `spent_mana + 1`. It does not stop spending when displayed cost reaches zero. Focused native scenarios cover cost 7 with 3 mana and cost 2 with 5 mana, plus clone divergence and end-turn persistence.

Whether an already zero-cost card is a legal Prepare target remains unresolved. Blizzard's published Prepare rule specifies spending all remaining mana and reducing cost by that amount plus one, but does not state the zero-cost target restriction. ManaEngine therefore fails closed if a zero-cost Prepare card with spendable mana reaches legal-action generation. The test verifies this unresolved boundary; it does not assert Hearthstone legality.

## Verification record

- Native Windows build completed; native suite passed: 25 scenario groups, 442 assertions.
- ManaEngine Python adapter tests passed: 8/8 via direct invocation.
- Tests cover activation order `A → Flames → B`, reversed ordering, normal Secret order, clone preservation, re-entry stamping, Counterspell/cast history, timing windows, full Tricksy pool behavior, and observation privacy.
- The six-Secret random pool is not reduced to supported outcomes. These ManaEngine results do not update canonical Rosetta evidence, Standard registry status, or training eligibility.
- No training, production backend switch, or macOS work occurred.

Official Prepare rule reference: [Escape from Violet Hold Is Now Live](https://hearthstone.blizzard.com/en-gb/news/24287640).
