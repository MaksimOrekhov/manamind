# First full deck closure audit — Mother Drake Warlock

Date: 2026-10-03
Pinned inputs: `meta_training_20261002_v1`, `standard_full_20261001_v1`, `standard_registry_20261001_v1`, RosettaStone gitlink in `E:\\ManaMind`.

## Executive result

The frozen list resolves cleanly to **30 slots and 19 distinct Standard collectible roots**. The exact 30-card list passes the runtime deck validator, initializes a Warlock `SimulatorSession`, exposes five opening legal actions, and has no initial choice/terminal state. Life Tap also worked in a short class/session smoke (hero health 30→28; hand size 5→6).

That establishes class/deck/session startup only. The Meta Profile currently has **3 current scoped-verified roots** in this deck (`CORE_ICC_055`, `CORE_CS2_062`, `CATA_999`) and **16 roots with no current profile evidence**. All 19 roots have source registration, so there are 0 unregistered roots. The canonical registry still labels all 19 `IMPLEMENTED_UNVERIFIED` for its separate full Standard scope. Current full closure is **0/19 roots admitted**, **0/30 deck semantics certified**, and no deck session/match evidence exists.

The current registry summary lists 3 candidate static dependency nodes and two unresolved pool IDs. Source review found that this graph is a lower bound: it misses fixed enchantment/token/choice references and does not encode several runtime state-derived pools. The exact dependency closure is therefore larger than the report suggests and cannot be treated as complete.

## All 19 roots

“Current” below means current Meta Profile scoped evidence only. “Unverified” means registered/implemented source exists but this deck lacks current scoped evidence; it does not mean the card has no code.

| Root | Copies | Meta evidence | Source route | Independent semantic review and remaining issue |
|---|---:|---|---|---|
| `TLC_451` Cursed Catacombs | 2 | Unverified | Direct source / `DiscoverTask` | Discovers another card from the player’s live deck and makes the selected card Temporary. The deck-derived choice set and temporary-card lifecycle are not verified; this is the report’s `POOL:TLC_451:discover`. |
| `CORE_UNG_205` Glacial Shard | 2 | Unverified | Direct source / `FreezeTask` | Battlecry freezes an enemy. Requirements explicitly limit target to enemy; no root-specific scenario was found. Small deterministic verification candidate. |
| `CATA_496` Cursed Chains | 2 | Unverified | Direct source / enchant + control | Takes an enemy minion until the end of its owner’s next turn and prevents attack this turn. Source defines `CATA_496e_attack` and `CATA_496e_control`, but the registry graph omits both fixed children. Turn ownership, return timing, death/transform, and silence interactions need scenarios. |
| `CORE_ICC_055` Drain Soul | 2 | **Current scoped** | Direct source / damage + Lifesteal | Current evidence verifies 3 damage to a minion and Lifesteal in the scoped family. It is not full-profile admission. |
| `JAIL_515` Shadow Rounds | 1 | Unverified | Direct source / `CUSTOM` | Deals 2 to the selected enemy minion; if it dies, resolves deaths then chooses a random living enemy minion and repeats. The registry labels a generic random pool, but the real candidate set is the live enemy board rebuilt after each death; Deathrattle, Reborn and target protection matter. This is a state-dependent outcome family, not a fixed Standard-card pool. |
| `CATA_725` Shadowsworn Disciple | 2 | Unverified | Direct source / `CUSTOM` + token | Each Herald increments a player-level counter, summons `CATA_725t`, upgrades all Soldiers every second Herald (capped), and has a 3-health hero Deathrattle. `CATA_725t` is a fixed child omitted from registry closure. The counter lifetime/reset and token progression have no scoped scenario. |
| `JAIL_513` Caged Cranium | 2 | Unverified | Direct source / existing tasks | Taunt; Battlecry gains Health for each remaining card in hand. The source counts the hand after the played minion has left it; needs a scenario for exact timing and empty/small hand cases. |
| `CAP_405` Godfather Kazakus | 1 | Unverified | Direct source / custom multi-step choice | Constructs a three-stage choice: two potion effects from nine options, then potion length from three options. Resolving effects includes a live Standard 3-cost-minion candidate set, random board targeting, opponent-hand acquisition, summons, healing, draw and attack resolution. The 12 option definitions, choice continuation, duplicate-effect rules, and all outcome semantics are absent from the current registry graph. This is the largest known deck-specific choice/pool blocker. |
| `CORE_CS2_062` Hellfire | 1 | **Current scoped** | Direct source / `DamageTask(ALL, 3)` | Current evidence covers damage to all characters, including the caster. It remains scoped, not full-profile admission. |
| `JAIL_399` Imp Gang Stooge | 2 | Unverified | Direct source / Deathrattle | Deathrattle puts two `JAIL_399t1` Grandmother Imps (8/8 Demon, Taunt, Lifesteal) at the bottom of the deck. The fixed token dependency is not in the profile closure; root-specific tests cover token insertion but not all later draw/session behavior. |
| `JAIL_509` Godfrey the Betrayer | 1 | Unverified | Direct source / global player hook | Start of Game enables Godfrey for the player. Full-hand draws enter set-aside, then return when space opens at one less cost. This crosses Game Start, draw/overdraw, set-aside, hand-capacity and post-action processing (`Draw.cpp`, `Player.cpp`, `Game.cpp`). No profile scenario verifies edge timing or returned-card observations. |
| `TIME_031` RAFAAM LADDER!! | 2 | Unverified | Direct source / `CUSTOM` | Draws up to three cards from the current deck with distinct costs; each choice is random among remaining cards at a previously unused cost. This deck-dependent random selection is absent from the registry’s two pool IDs. Exact cost predicate, empty candidate behavior and all draws are unverified. |
| `CATA_999` Earthen Drake | 1 | **Current scoped** | Direct source / turn-end `DamageTask` | Newly verified: no immediate damage; 4 to enemy hero at controller turn end. Does not certify Deios doubling or whole-deck closure. |
| `JAIL_511` Spire of Solitude | 2 | Unverified | Direct source / Location activation + `CUSTOM` | Activates to summon fixed token `JAIL_511t` (Demon), set its stats to hand size and attack a random enemy minion. Token edge omitted; random live-enemy target family and Location action/observation interaction need review. |
| `TIME_064` Chrono-Lord Deios | 1 | Unverified | Direct source / player Aura + core trigger handling | Doubles Battlecries, Deathrattles, Hero Power and end-of-turn effects. The end-turn handling crosses global trigger processing; interactions with other root triggers (especially `CATA_999`, `CATA_725t`, and current-turn timing) require native and bridge scenarios. This is a high-risk shared engine semantic, not just a root test. |
| `JAIL_510` Annihilation | 2 | Unverified | Direct source / destroy + `CUSTOM` | Destroys all minions, then inspects the bottom three actual deck entities and summons the ones that are Demons. Its outcome depends on hidden deck order and death processing; no exact bottom-three predicate exists in the registry report and no scoped scenario was found. |
| `DINO_402` Bat Mask | 1 | Unverified | Direct source / `CUSTOM` | Sets one friendly minion’s stats to 1/1 and fills available board slots with copies. Needs independent checks for current damage/enchantments, copied tags, full/near-full board and summon ordering. |
| `BE_036` M.O.T.H.E.R. | 1 | Unverified | Direct source / `FuncNumberTask` + choice | Offers each card in hand; the selected card loses 5 cost, then neighboring cards lose 4, 3, 2 and 1 outward. The special `MOTHER` choice path is exposed by the bridge implementation but exact offered order, chosen instance and cost application are unverified. |
| `JAIL_514` The Unseen Atlas | 2 | Unverified | Direct source / adaptive cost + draw | Costs 1 less per card in hand and draws three. The current aura reads live hand size; verify whether the active card is counted before play, recalculation while in hand, floor at zero, and draw/fatigue/hand-cap cases. |

## Dependency and dynamic-outcome closure

### Fixed dependencies visible in the source

The current registry lower bound records three token candidates: `CATA_725t`, `JAIL_399t1`, and `JAIL_511t`. Source review additionally found:

- `CATA_496e_attack` and `CATA_496e_control`, both referenced by Cursed Chains and defined in the same source file;
- Kazakus option entities `MANA_KAZAKUS_EFFECT_1..9`, `MANA_KAZAKUS_LENGTH_7`, `_4`, `_0`, and its generated `MANA_KAZAKUS_TRIAL`;
- Kazakus effect 1 references `CORE_LOOT_368`; effect 5 queries Standard 3-cost minions at runtime.

Those references need explicit graph nodes/edge kinds even when their source definitions already exist. They are currently not all represented by the report’s three candidate edges.

### Pool report and additional runtime-derived sets

The two currently reported pool IDs are:

1. `POOL:TLC_451:discover` — candidates are drawn from the player’s remaining deck at resolution, not from a pre-truncated supported-card list. Selected outcome becomes Temporary.
2. `POOL:JAIL_515:random_card_or_pool` — source semantics are a live set of enemy minions remaining after each resolved hit and death chain, not a collectible-card pool.

Source review also identified dynamic memberships absent from those two report IDs:

- `TIME_031`: current deck cards grouped by cost, excluding costs already drawn in this effect;
- `JAIL_511`: current enemy minions eligible for the random attack target;
- `JAIL_510`: Demon minions among the exact bottom three entities of the current deck;
- `CAP_405`: all nine choice outcomes and the three length choices, plus the dynamic Standard 3-cost-minion pool used by one potion and state-dependent targets/hand outcomes in other effects.

These do not all require a new universal “random pool” abstraction, but each needs a versioned semantic predicate and either exact snapshot membership or an explicit runtime-state membership contract. Until that is recorded, the deck has **at least six** dynamic/state-derived outcome sets to review; the current two-pool summary is incomplete. Do not narrow any of them to implemented outcomes.

## Class, session, action and observation audit

- **Class/session startup:** no Warlock class blocker found. The exact 30-card list passes `validate_decks`; a configured bridge session initializes. A Life Tap smoke succeeds (30→28 hero health, hand 5→6). This is setup evidence only.
- **Legal actions:** startup exposes legal actions. The bridge documents `PLAY_CARD`, `ATTACK`, `HERO_POWER`, `CHOOSE_CARD`, `ACTIVATE_LOCATION`, `TRADE_CARD`, and `END_TURN`; Kazakus, MOTHER and deck Discover choice actions are explicitly enumerated in the choice exporter. This establishes API paths, not complete legality/parity for these roots. Exact card-target, multi-step continuation, Location activation, and random-outcome action tests are still missing.
- **Observations:** the normal contract exposes SELF hand plus public board/hero/resources and does not expose opponent hidden hand or deck order. Choice actions can reveal offered options when they become available. Verify the option payload for Kazakus’s simulator-only cards, MOTHER’s hand entities, and TLC_451 deck options; keep hidden deck order and unrevealed opponent hand IDs out of policy inputs. Returned overdrawn cards must appear only when they actually return to SELF hand.
- **Match-to-terminal:** bridge APIs expose `is_complete`, `result`, and `needs_choice`, but `configs/standard_profile.json` has no current `session_match_evidence`. There are no repeated Mother Drake matches ending in a recorded win/loss/draw under the exact pinned profile. Unsupported or incorrectly resolved choice/random outcomes would invalidate these labels.

## Why Mother Drake is not the cheapest first closure target

The audit exposed several mechanics that interact in one list: multi-stage Kazakus choice with large/random outcomes, live-deck random selection (TIME_031, Annihilation), repeated death processing (Shadow Rounds), overdraw/set-aside lifecycle (Godfrey), and Deios global trigger doubling. These are significant hidden blockers even though every collectible root has a source definition.

| Candidate | Roots | Current scoped | Unregistered | Registry pools | Other observed complexity |
|---|---:|---:|---:|---:|---|
| Mother Drake Warlock | 19 | 3 | 0 | 2 reported; at least 4 additional dynamic/state-derived families found | Multi-step custom choice, global turn/overdraw hooks, death-resolution loop, hidden deck-zone predicates |
| Cannoneer Dragon Warrior | 16 | 0 | 1 | 5 | 8 `CUSTOM` route roots; several Discover/random families |
| Fire Pirate Warrior | 17 | 0 | 5 | 3 | 6 `CUSTOM` routes plus five roots with no detected registration |

**Select `cannoneer_dragon_warrior` as the next first-closure candidate, with medium confidence.** It is not “ready”: it has five reported dynamic pools and eight custom routes. It is the best-supported cheaper candidate from these three because it has only one unregistered root (versus five for Fire Pirate), and its known profile does not combine Mother Drake’s Kazakus choice chain, Godfrey overdraw lifecycle and Deios global event interaction. Before committing to that choice, first resolve its five pool predicates and unknown `TIME_034` root from its own registry/source audit. Do not claim a time-to-close from this lower-bound comparison.

## Minimal ordered queue for the first complete deck

This queue is deck-specific and aims at `DECK_READY`; it is not a return to global Standard coverage.

1. **Repair the closure inventory first.** Add CATA_496’s two enchantments, CATA_725t, JAIL_399t1, JAIL_511t and Kazakus option/trial nodes. Record source-reviewed fixed edges. Replace the ambiguous Shadow Rounds pool label and add versioned predicates for Catacombs, Rafaam Ladder, Spire, Annihilation and Kazakus outcomes. Preserve the full eligible outcome sets.
2. **Harvest deterministic roots on existing primitives.** Independently verify Glacial Shard, Cursed Chains, Caged Cranium, Imp Gang Stooge, and The Unseen Atlas. Include target/action parity and the fixed-child effects. Do not treat source registration as completion.
3. **Verify repeatable/token/state families.** Cover Shadowsworn Disciple’s counter and Soldier token sequence; Bat Mask’s board fill; Spire’s Location activation/token stats/random attack; and Annihilation’s bottom-three Demon selection after full destroy/death processing.
4. **Verify live-deck and choice flows with full outcomes.** Cover Catacombs temporary Discover, Rafaam Ladder distinct-cost draws, Shadow Rounds reselected random minions after death, and Kazakus’s three sequential choices and every potion effect. Confirm MOTHER choices reference the selected entity and preserve hand order. These are full-pool/session checks, not restricted pilots.
5. **Verify shared player/event lifecycle mechanics.** Test Godfrey across full hand, repeated overdraw, a freed slot, reduced cost and observation update. Test Deios doubling each applicable event, including end-turn roots in this deck, without changing global event order opportunistically.
6. **Run full-deck bridge/parity and match evidence.** Revalidate exact deck/opp lists, verify every profile root can be legally reached and resolved in representative states, then run repeated seeded matches all the way to terminal. Record both perspectives, legal action/choice identity, result, execution identity, pool predicates and unsupported-outcome checks.
7. **Apply `DECK_READY` only after every gate passes.** Require 19/19 current root semantics, complete reviewed dependency closure, correct unshrunk pools, no action/observation mismatch, current session/match evidence, and repeated terminal results. Keep full-profile training blocked until the authoritative gates say otherwise.

## Audit limits

This audit reviewed pinned manifests, current registry/report rows, source definitions, listed dependencies/pools and the current bridge interface. It did not execute all 19 root behaviors, enumerate every runtime pool membership, run full matches, or certify a rules bug solely from unverified source. “Implemented” remains separate from “correct.”
