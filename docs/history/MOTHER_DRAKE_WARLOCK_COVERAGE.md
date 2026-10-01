# Mother Drake Warlock: simulator coverage audit

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

**Audited:** 2026-09-27  
**Deck source:** [Vicious Syndicate, published September 23, 2026](https://www.vicioussyndicate.com/decks/mother-drake-warlock/)  
**Format:** Standard

The audited 30-card variant is the page's 26 Core cards plus its 4 Flex cards. The page also lists four Tech cards as replacements for the Flex package; those are noted separately below. This is an audit of rules coverage, not a claim that this is the only current or highest-win-rate list.

## Findings

- The local Standard catalog now contains metadata for all **19 of the deck's 19 unique cards**. **M.O.T.H.E.R. (`BE_036`, dbfId `128132`)** is included as an exact one-card Standard exception because Blizzard made it available as a login reward from September 15, before its set's October 20 release. Its record comes from the current HearthstoneJSON collectible-card feed; card details are also listed by the [Hearthstone Wiki](https://hearthstone.wiki.gg/wiki/M.O.T.H.E.R.). The unreleased `BE` set remains excluded.
- The pinned engine has explicit CardDefs for **eighteen** of the 19 cards: Cursed Catacombs, Glacial Shard, Cursed Chains, Drain Soul, Shadow Rounds, Shadowsworn Disciple, Hellfire, Caged Cranium, Godfather Kazakus, Imp Gang Stooge, Godfrey the Betrayer, Annihilation, Bat Mask, Spire of Solitude, RAFAAM LADDER!!, Earthen Drake, Chrono-Lord Deios, and The Unseen Atlas. Focused scenarios cover Catacombs' deck choice and end-of-turn expiry, Chains' temporary control, Shadow Rounds' repeated damage, Shadowsworn Disciple's Herald summon and healing Deathrattle, Kazakus' three-stage choices and generated 7-cost spell, and the previously listed effects. Bat Mask sets a friendly minion to 1/1 and fills the remaining board slots with copies; `scripts/verify_bat_mask_scenario.py` checks a 1/3 Voidwalker becoming a full board of seven 1/1 copies. Annihilation destroys both boards, then removes and summons each Demon among the bottom three deck cards, stopping when the board fills; `scripts/verify_annihilation_scenario.py` checks both board clearing and two bottom Demons with a non-Demon between them. Deios now doubles friendly Battlecries, Deathrattles, Hero Power effects, and end-of-turn triggers; `scripts/verify_deios_scenario.py` checks the first three, while `scripts/verify_current_standard_scenarios.py` covers end-of-turn triggers and controller ownership. Kazakus implements all nine trial effects and turn-start resolution for Grueling and Unending trials.
- M.O.T.H.E.R. has a separate supported choice definition. All included cards now have a CardDef or supported choice definition. In addition to the focused card scenarios, `scripts/verify_mother_drake_interactions.py` checks the central Bat Mask + Imp Gang Stooge + Deios + Annihilation combo: six Stooge Deathrattles add 24 Imps, then Annihilation summons three from the bottom of the deck. It also ensures the bridge does not offer a Location play when minions plus Locations already fill the board. The first 48-game mirror pilot completed six policy updates. On held-out seeds, the final checkpoint went 18–2 against the fixed heuristic and 20–0 against its cycle-one checkpoint in a paired comparison. This is evidence of policy improvement only within this deck and simulator; the opponent is weak, the sample is small, and not every game-state edge is covered.
- The RosettaStone deck gate requires an explicit CardDef for each text-bearing card. This is a conservative gate; passing it alone does not prove that a card's full effect or edge cases are correct.

## Core + Flex 30-card list

| Card | Copies | ID | Current simulator status |
|---|---:|---|---|
| Cursed Catacombs | 2 | `TLC_451` | Implemented; discovers a card from the deck and moves that temporary copy to the graveyard at end of turn; `Game::MainCleanUp` routes it through the card owner's graveyard; checked by `scripts/verify_current_standard_scenarios.py` |
| Glacial Shard | 2 | `CORE_UNG_205` | Implemented; Battlecry freeze verified by `scripts/verify_current_standard_scenarios.py` |
| Cursed Chains | 2 | `CATA_496` | Implemented; control returns after the opponent's turn, and the minion cannot attack during the current turn; control timing and attack restriction checked by `scripts/verify_current_standard_scenarios.py` |
| Drain Soul | 2 | `CORE_ICC_055` | CardDef exists; damage and Lifesteal checked by `scripts/verify_current_standard_scenarios.py` |
| Shadow Rounds | 1 | `JAIL_515` | Implemented; repeats 2 spell damage on a random enemy minion after a kill; basic repeat behavior checked by `scripts/verify_current_standard_scenarios.py` |
| Shadowsworn Disciple | 2 | `CATA_725` | Implemented; Herald summons Soldier of Cho'gall, Heralds upgrade Soldiers every second time, and Deathrattle restores 3 Health; tested by `scripts/verify_current_standard_scenarios.py` |
| Caged Cranium | 2 | `JAIL_513` | Implemented; Taunt and hand-size-based Battlecry health gain checked by `scripts/verify_current_standard_scenarios.py` |
| Godfather Kazakus | 1 | `CAP_405` | Implemented: choose two distinct effects from nine, then create a 7-cost trial spell or schedule the chosen effects for the next own turn / four own turns; see `scripts/verify_kazakus_scenario.py` |
| Hellfire | 1 | `CORE_CS2_062` | CardDef exists; area damage checked by `scripts/verify_current_standard_scenarios.py` |
| Imp Gang Stooge | 2 | `JAIL_399` | Implemented; Deathrattle adds two 8/8 Taunt and Lifesteal Grandmother Imps at the deck bottom, verified by `scripts/verify_imp_gang_stooge.py`; a native Core card assertion also checks both tokens at deck bottom |
| Godfrey the Betrayer | 1 | `JAIL_509` | Implemented; overdrawn cards are kept aside, then return in random order when hand space opens at one less Cost; checked by `scripts/verify_godfrey_scenario.py` |
| RAFAAM LADDER!! | 2 | `TIME_031` | Implemented; draws up to three cards with different Costs, checked by `scripts/verify_current_standard_scenarios.py` |
| Earthen Drake | 1 | `CATA_999` | Implemented; standalone 4 damage and Deios interaction are scenario-checked |
| Spire of Solitude | 2 | `JAIL_511` | Implemented; activates as a Location, summons a Demon matching hand size, and forces it to attack a random enemy minion; verified by `scripts/verify_spire_scenario.py` |
| Chrono-Lord Deios | 1 | `TIME_064` | Implemented; doubles friendly Battlecries, minion Deathrattles, Hero Power effects, and end-of-turn triggers; see `scripts/verify_deios_scenario.py` and `scripts/verify_current_standard_scenarios.py` |
| Annihilation | 2 | `JAIL_510` | Implemented; destroys both boards and summons Demons found among the bottom three deck cards; verified by `scripts/verify_annihilation_scenario.py` |
| Bat Mask | 1 | `DINO_402` | Implemented; sets a friendly minion to 1/1 and fills remaining board slots with copies; verified by `scripts/verify_bat_mask_scenario.py` |
| M.O.T.H.E.R. | 1 | `BE_036` | Implemented: choose a card in hand, reduce its cost by 5 and neighboring cards by 4 through 1; scenario verification in `scripts/verify_mother_scenario.py` |
| The Unseen Atlas | 2 | `JAIL_514` | Implemented; hand-size-based cost reduction and 3-card draw checked by `scripts/verify_current_standard_scenarios.py` |

The page's Tech alternatives are Mortal Coil (`CORE_EX1_302`) ×2, Shadow Rounds (`JAIL_515`) ×1, and Hellfire (`CORE_CS2_062`) ×1; they replace the four Flex slots. Mortal Coil has a CardDef. Hellfire's presence in the source does not replace the need for behavior checks.

## Recommended implementation order

1. Add focused behavior scenarios for existing definitions used by this archetype (Drain Soul and Hellfire) and preserve the passing Earthen Drake/Deios and M.O.T.H.E.R. scenarios.
2. Implement reusable engine support for simple action groups (freeze, damage, healing/Lifesteal, constrained draws, and buffs), then attach current-card definitions and test them.
3. Continue treating remaining player choices, start-of-game rules, deck-bottom searches, and copy/fill-board effects as separate simulator features. These require action/state semantics and token support, not just a one-line card definition.
4. Admit this deck to current-format rollouts only after every included card and generated token/choice path is supported and tested. Keep self-play labels paused until then.
