# Keyword-only minion package — 2026-10-01

## Selection and contract

Added CardDefs for `CORE_GIL_558` Swamp Leech (Lifesteal), `CORE_ULD_723` Murmy (Reborn), `EDR_486` Scorching Observer (Rush + Lifesteal), `END_031` Shade of the End Time (Stealth + Spell Damage +1), and `RLK_067` Corrupted Ashbringer (Lifesteal weapon). In the pinned Standard catalog, each card's full rules text consists only of these supported intrinsic keyword labels and each metadata mechanic set matches the declaration exactly.

The allowlisted declaration is `integrations/rosettastone/card_rules/keyword_only.v1.json`; `scripts/generate_keyword_only_cards.py` validates its schema, catalog SHA-256, card type, exact mechanics, full text shape, and duplicate ownership against the existing generated manifests. It rejects unknown mechanics and any additional rules text. It emits a normal C++ CardDef registration with no card-specific Power task; RosettaStone applies the listed intrinsic mechanics through card metadata and the existing engine rules.

## Verification

- Generator emitted all five declarations; the pinned Standard registry recognized 5 `GENERATED_KEYWORD_ONLY` entries.
- Native focused registration test passed: 1 case, 6 assertions.
- Bridge smoke passed for the four non-DK cards: Standard deck validation, session creation, visible opening hand, and legal-action enumeration. `RLK_067` passes Standard Death Knight deck validation; the known missing Death Knight session setup prevents a match smoke for this card.
- Registry suite passed: 8 tests.
- Registry after the batch: 1,185 roots; 167 direct + 62 generated registrations; 953 text-bearing roots without detected registration; 127 known non-root dependency nodes; 306 heuristic dynamic-pool signals; zero complete root closures and zero training-eligible roots.

## Limits

The native test and bridge smoke establish registration and basic use in a loaded Standard session for four cards, and deck legality for the DK weapon. They do not independently test Lifesteal healing, Reborn token generation, Rush attack restrictions, Stealth targeting, or Spell Damage interaction for these exact cards. All five remain `IMPLEMENTED_UNVERIFIED` and blocked from full-profile training pending independent effect scenarios, dependency closure, action audit, and full-pool gates.

Cards with Elusive were excluded because the current checkout lacks the required targeting contract; special keyword text such as `Prepare` and Colossal was also excluded. No claim is made that all keyword-only cards have been found or that every keyword is supported.
