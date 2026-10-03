# Phase 4 — Secret event-ordering review

Date: 2026-10-04
Branch: `codex/manaengine-first-deck`
Base revision: `eecc9fe9f187da5162037a4c052aca36896870d9`

## Exact pinned Standard Mage Secret pool

The pinned `data/cards/standard_current_enUS.json` profile has six collectible Mage Secrets:

| Card | Required typed window | Contract |
|---|---|---|
| `CORE_BAR_812` Oasis Ally | `FRIENDLY_MINION_ATTACKED` | Summon a 3/6 Water Elemental. |
| `CORE_EX1_287` Counterspell | `OPPONENT_CASTS_SPELL` | Cancel the spell before its effect resolves. |
| `CORE_EX1_289` Ice Barrier | `FRIENDLY_HERO_ATTACKED` | Gain 8 Armor before attack damage. |
| `CORE_LOOT_101` Explosive Runes | `OPPONENT_PLAYS_MINION` | After Battlecry resolution, deal 6 to the played minion and excess to its hero. |
| `END_024` Flames of Infinity | `OPPONENT_TURN_ENDS` | Deal lethal damage to the opponent's highest-Health minion. |
| `JAIL_315` Mystic Misdirection | `ENEMY_MINION_ATTACKS` | Transform the attacker into a 1/1 Sheep and cancel combat. |

No other collectible Standard card with Mage class and Secret keyword matched the pinned profile. All six are potential outcomes of Tricksy Improviser's "two random Mage Secrets" effect. The selection pool must remain all six regardless of implementation status. Random selection is independent per cast; the prototype must not remove active Secrets from candidate membership unless exact game rules establish that filter. A selected Secret that cannot enter the active zone must be represented as a failed cast outcome, not silently filtered from the pool.

The opponent-facing observation must expose only active Secret count. The owner-facing observation may expose the identities of their own Secrets. Secret resolution order must preserve play order.

## Timing review

- Attack windows occur before combat damage. Ice Barrier grants Armor before a hero takes attack damage. Oasis Ally responds to a friendly minion being attacked. Mystic Misdirection transforms a declared enemy minion attacker and cancels that combat.
- Counterspell resolves after an opponent begins casting a spell and before that spell's effect. A countered spell still counts as cast for current-turn history.
- Explosive Runes is an **after-play** window. Its effect follows the played minion's Battlecry. The minion is the target if it remains available after Battlecry processing.
- Flames of Infinity occurs when the opponent ends their turn. The pinned rules text and 36.6 patch notes matter here: Blizzard fixed a bug where this Secret always triggered first at opponent turn end. It therefore needs ordering relative to other end-of-turn effects, rather than a fixed "Secret first" or "Secret last" phase.
- The normal one-copy-per-active-Secret rule applies to ordinary play. Tricksy's random casts must sample the full pinned pool; they must not pre-filter outcomes based on current active Secrets. The precise failed-cast presentation is not represented in current observations.

References: [Blizzard 36.6 patch notes](https://hearthstone.blizzard.com/en-gb/news/24294373/updated-9292026-366-patch-notes); [Secret timing reference](https://hearthstone.wiki.gg/wiki/Secret); [Tricksy Improviser](https://hearthstone.wiki.gg/wiki/Tricksy_Improviser).

## Why implementation is paused

ManaEngine's current event loop drains FIFO triggers, checks deaths, resolves FIFO deathrattles, and repeats. Its end-turn trigger currently processes all board end-turn effects together in board order. Secrets are not represented in the loop. The current event representation cannot preserve the required relative ordering between an end-turn Secret and other end-turn effects.

An attempted implementation would have added an ordered shared Secret dispatcher spanning attacks, spell casting, minion play, and turn end, and changed combat cancellation / spell resolution points. Automatic approval review rejected that patch because it changes core event ordering. This is also the one unresolved architectural detail in the approved Phase 4 scope. No Secret production code was retained.

## Review choices

1. **Minimal unified sequence** — add a monotonically increasing play-order stamp and typed Secret windows. Merge only Secret activations with currently modeled end-turn triggers in that order; keep the existing FIFO trigger/death loop. This preserves the required ordering with a narrow extension, but changes `CardInstance` / `EngineState` and end-turn processing.
2. **Defer Flames of Infinity** — implement the five other Secret windows and Tricksy while keeping the full six-card random pool. This is not sufficient for a valid Tricksy outcome pool, because the unimplemented Secret outcome would invalidate affected matches.
3. **Defer the Secret package** — continue non-Secret Mage capabilities; revisit Secrets after an explicit event-order design review.

Choice 1 is the smallest route to an honest complete Mage Secret pool, but it needs explicit architecture acceptance because it changes shared event ordering. Training and production backend are unaffected.
