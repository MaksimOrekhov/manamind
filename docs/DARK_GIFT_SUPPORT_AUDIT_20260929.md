# Dark Gift support audit — 2026-09-29

## Scope

This review covers the three selected-deck cards blocked on Dark Gift: `EDR_456` Darkrider, `FIR_939` Shadowflame Suffusion, and `EDR_856` Nightmare Lord Xavius. Current Standard metadata is from `data/cards/standard_current_enUS.json` (valid as of 2026-09-27). The implementation below is a scoped simulator pilot; it does not establish training eligibility for the three cards or their candidate pools.

Reproduce the candidate-pool inventory with `scripts/audit_dark_gift_support.py`; machine-readable result and source fingerprints are in `reports/dark_gift_support_audit_20260929.json`.

## Confirmed rules

Blizzard describes each Dark Gift Discover option as a minion paired with its own gift. A Discover presents three different gifts, each constrained when the effect does not work for that minion. The ten gifts are:

1. +3 Attack and Lifesteal.
2. +2/+2 and Elusive.
3. Cost −2 and Attack −2, only when Attack remains at least 1.
4. Charge.
5. Playing the minion summons a 2/2 copy.
6. Battlecries trigger twice; only for a minion with Battlecry.
7. +4 Health and Taunt.
8. Reborn, returning with full Health and enchantments.
9. +4/+5, then put the card on top of its owner's deck.
10. Divine Shield and Windfury.

Primary rules sources: [Blizzard's Into the Emerald Dream announcement](https://hearthstone.blizzard.com/en-us/news/24179067) and [expansion FAQ](https://hearthstone.blizzard.com/en-us/expansions-adventures/into-the-emerald-dream).

## Selected cards and exact candidate sets

| Card | Candidate source | Candidate predicate | Resolution after selection |
|---|---|---|---|
| `EDR_456` Darkrider | Standard collection | Dragon minions | If the Battlecry condition (holding a Dragon) is false, no choice occurs. Otherwise offer up to three candidates, each paired with a different valid gift; selected minion enters hand with its gift. |
| `FIR_939` Shadowflame Suffusion | Standard collection | Warrior minions | Deal 2 damage, then offer up to three eligible minions paired with distinct valid gifts; selected minion enters hand with its gift. |
| `EDR_856` Nightmare Lord Xavius | This player's actual deck entities | Minions in deck | Offer up to three distinct eligible deck minions paired with distinct valid gifts; the selected original entity moves from deck to hand and receives its gift. |

The catalog snapshot contains 80 collectible Standard Dragon minions and 42 collectible Standard Warrior-class minions. These are the two format-wide candidate pools; they must not be restricted to the three selected-deck cards. In the saved Quest Priest list, Xavius can select from three other unique minion IDs in that deck: `CAP_804`, `CAP_806`, and `JAIL_912` (the deck contains one Xavius). Xavius must preserve the identity and current state of the selected deck entity. Choice candidates with the same card ID but different gifts must remain distinguishable to the policy and legal-action bridge.

These counts make the strict dependency question material: Darkrider and Shadowflame can add a gifted minion from a 114-ID combined pool (80 Dragon candidates plus 42 Warrior candidates, with 8 IDs in both pools) to hand, so episode admission must account for the selected result's future behavior. The minion only needs to be behaviorally supported if it is selected; the other offered choices are metadata/action inputs. Strict training cannot silently hide unsupported candidates or pretend that these card effects are implemented by the gift resolver.

## Implemented scoped capability (2026-09-29)

The engine now has a scoped Dark Gift option model, a per-choice gift payload, and a `MANAMIND_DARK_GIFT_ID` entity marker. The task samples candidate/gift pairs with three distinct gifts and filters each gift against the candidate's keywords, attack, and Battlecry status. Darkrider checks for any Dragon-race card in hand. Shadowflame Suffusion deals 2 damage before its Warrior Discover. Xavius chooses actual minion entities from the player's deck, preserving the selected entity.

The implemented resolver covers these behaviors:

- immediate stats, keywords, cost change, and top-deck placement;
- Battlecry twice, summon-a-copy-on-play, and Reborn with full health and enchantments;
- visible gift identity in legal choice actions, SELF hand cards, and both players' public minion boards;
- selected generated options and original deck entities without applying gifts to unselected options.

Core registration and bridge metadata are implemented for the three selected cards. Native focused scenarios cover option eligibility/pairing, all ten immediate gifts, choice resolution, Battlecry x2, the 2/2 copy, full-health Reborn with enchantments, Dragon-in-hand gating, Shadowflame damage/order, and Xavius entity selection. The scoped test run reported 19 scenarios and 124 assertions passed before this turn. Python bridge/pipeline tests pass 16/16 after the final bridge update.

## Package decision

The focused Dark Gift package is implemented, but its dynamic candidate closure is not training-ready. Darkrider and Shadowflame can add a selected card from the 114-ID union of Dragon and Warrior pools; each selected card's own rules and generated dependencies still need verification. Current ban-list validation is also absent. The full UnitTests executable hung without output on both full and filtered invocation and was interrupted; record native suite status as incomplete. Do not infer five-deck readiness or schedule model training/evaluation from these focused scenarios.

Next work resumes with the selected-card dependency closure and remaining deck gates from `docs/CARD_SUPPORT_AUTOMATION_PLAN_20260929.md`. No next package was started in this work session.

Next package selection should use the existing ranked queue and compare dependency closure and effort. No model matches, training, or evaluation are permitted before the five-deck gate in `docs/CARD_SUPPORT_AUTOMATION_PLAN_20260929.md` passes.
