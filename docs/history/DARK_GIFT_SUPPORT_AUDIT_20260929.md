# Dark Gift support audit — 2026-09-29

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

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

The focused Dark Gift package is implemented, but its dynamic candidate closure is not training-ready. The refreshed 2026-09-30 inventory finds 80 Dragon candidates and 42 Warrior candidates (114 unique). It detects 22 registered roots and 92 unregistered candidates; registered roots have zero unresolved literal CardDef references. Five registered roots had dynamic hints; source review resolved these into one random-target case and four card pools. The unregistered 92 are triaged as 46 triggered, 30 choice/random/generated, 10 single-effect, and 6 composed cards. These routes are planning hints, not verification labels. Exact top-level runtime-pool membership is now checked against pinned metadata, but recursive closure and rule correctness remain open; all 114 outcomes remain unverified. Do not restrict the offered pool to registered cards.

The dated format artifact `data/cards/format_bans_20260929.json` records zero Standard bans and two Wild bans (`EDR_271`, `JAIL_509`), based on Blizzard's [active bans thread](https://us.forums.blizzard.com/en/hearthstone/t/bans-what-and-where/151289), checked 2026-09-29. The selected-deck audit reports the Standard ban gate PASS with zero violations. This external snapshot does not change RosettaStone's runtime validator and must be refreshed after relevant format updates. The official patch-note pages also reviewed were [36.4.2](https://hearthstone.blizzard.com/en-us/news/24296231/3642-patch-notes), [36.0.3](https://hearthstone.blizzard.com/en-us/news/24290431/note-della-patch-3603), and [36.6](https://hearthstone.blizzard.com/en-us/news/24294373/patchnotes-zu-36-6); the explicit 36.0.3 ban is identified as Wild. The full UnitTests executable hung without output on both full and filtered invocation and was interrupted; record native suite status as incomplete. The fresh py312 bridge relink also remains incomplete: MSVC reports duplicate `Choice::~Choice()` symbols between `Choice.cpp.obj` and another archive object. The focused card test itself passes, but do not claim bridge/action readiness until the linker problem is resolved. Do not infer five-deck readiness or schedule model training/evaluation from these focused scenarios.

## Manual review of heuristic dynamic-pool hints (2026-09-30)

The five source-scan hints are not five equivalent card pools. `CAP_107t` says “random enemy” and selects a current enemy character target; it has no dynamic card-ID pool. `CATA_140` samples collectible Standard Dragon minions and repeats until hand full. `CATA_556` samples collectible Standard Dragon minions with printed Cost at most 3. `EDR_456` uses the collectible Standard Dragon candidate pool with additional Dark Gift compatibility and distinct-option constraints. `FIR_959` casts random eligible Fire spells under a 15-Mana budget, excluding Quests and requiring an enemy target for spells that need one; individual spell effects can open further choices or pools.

The source review is recorded in [dark_gift_dynamic_pool_review_20260930.json](../../reports/dark_gift_dynamic_pool_review_20260930.json). The audit generator emits source-reviewed profiles and metadata-derived candidate IDs: CATA_140/EDR_456 share a raw base pool of 80 Dragons, CATA_556 has 20 Dragons with printed Cost at most 3, and FIR_959 has 33 top-level Fire spells before current-state target checks. Focused native tests compare the full raw candidate ID sets against predicates from the pinned Standard catalog and pass. They do not cover EDR_456 gift-compatibility filtering or distinct offer construction. The audit found and fixed a loader bug where 271 retired collectible cards labeled CORE in the historical database leaked into current Standard pools; stale members of configured Standard sets are now reclassified as Legacy unless present in the current collectible overlay. For `FIR_959`, state-dependent target legality and recursive spell effects remain unresolved. The older `dynamic_pool_review_card_ids` field remains a heuristic signal, not a closure result. The report was regenerated with the repaired Python command path.

The outcome-card package adds explicit CardDefs for `TIME_045` Whelp of the Infinite and `TIME_056` Whelp of the Bronze, whose printed behavior is covered by existing Poisonous, Reborn, Lifesteal, and Divine Shield engine tags, plus `TIME_856` Algeth'ar Instructor, whose Spell Damage value is loaded from metadata. Focused native tests confirm their current Standard metadata, stats, keywords, and registration, and compare exact IDs in the four top-level runtime pools against the pinned catalog (41 assertions). This does not verify their behavior under every Dark Gift interaction or recursive candidate outcomes. `CORE_DRG_079` Evasive Wyrm was excluded after source review found no Elusive GameTag or targeting implementation in this checkout; it must not be treated as supported or aliased to legacy `DRG_079`.

Next work resumes with the selected-card dependency closure and remaining deck gates from `docs/CARD_SUPPORT_AUTOMATION_PLAN_20260929.md`. The ban-list gate has a dated PASS; the result-pool gate is still open.

Next package selection should use the existing ranked queue and compare dependency closure and effort. No model matches, training, or evaluation are permitted before the five-deck gate in `docs/CARD_SUPPORT_AUTOMATION_PLAN_20260929.md` passes.
