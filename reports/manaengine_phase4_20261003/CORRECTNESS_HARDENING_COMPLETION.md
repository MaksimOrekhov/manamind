# Phase 4 correctness hardening completion

Package: `prototype_correctness_hardening_v1`.
Baseline: ManaMind `a62ff5fb2f7d48498aea7e913a46ab24ad723286`.
Branch: `codex/manaengine-first-deck`.
RosettaStone pinned and unchanged: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
Active work start: 2026-10-04 09:04:32 UTC. Local verification completed approximately 10:01 UTC; hosted acceptance still pending at this commit. Final observed elapsed/CI links will be appended after hosted checks.

## Repairs

One shared typed damage path now handles combat, spells/composed effects, Secret damage, hero power, end-turn effects and fatigue. It centralizes minion shield/Immune, hero armor, full-overkill Lifesteal, spell-damage event publication and damage state. Hero-to-minion retaliation is restored; weapon consumption and after-attack triggers remain tested.

Attack Secret eligibility is target-based, activation ordered and cancellation-aware. Secret damage uses shared prevention/accounting. No living target leaves Flames armed. Water Elemental cannot silently execute as vanilla; Oasis becomes explicitly invalid when that unsupported outcome is required. Metadata coverage rejects unrepresented mechanics, including Viper Tradeable. Fabricated dependency IDs and production diagnostic tracker were removed.

Death processing removes simultaneous dead minions from both boards before any ordered deathrattle and evaluates terminal state after mandatory processing. Simultaneous lethal heroes and double fatigue yield DRAW. This follows the previously approved prototype semantics; exact full-game ordering is not certified.

Prepare follows reviewed useful-spend/one-use rules. Prepared zero-cost cards are playable after their turn lock without poisoning `legal_actions()`. Shatter inherited modifiers and modified merges fail closed until independently established. Shared transform replaces instance content through a defined prototype contract.

Public observation schema is 14, with progress, trigger availability, discounts, timed effects and SELF Choice candidates. Existing checkpoints cannot silently reuse schema 13. Unsupported hero-power sessions fail; backend training admission remains blocked. Catalog/data/report changes trigger experimental CI. Adapter declaration fields are allowlisted, and random Mage Secret membership is checked against an explicit reviewed six-ID manifest, not a magic cardinality.

## Actual local results

| Check | Observed result |
|---|---|
| Windows Release native suite | PASS, 30 scenario groups / 537 assertions |
| Python adapter + pipeline | PASS, 36 tests, 30.94 seconds |
| Full repository Python suite | PASS, 84 tests, 11.68 seconds |
| Ruff src/tests/scripts/adapter tests | PASS |
| Generic card-ID AST guard | PASS, 201 existing reviewed exceptions |
| Pinned regeneration | PASS, 36 outputs reproduced on repeated run |
| git diff whitespace check | PASS |
| Source CI Win/Ubuntu | Await hosted results |
| ManaEngine CI Win/Ubuntu | Await hosted results |

Native build: fresh `%TEMP%/ManaEngineCorrectnessBuild`, MSVC/Ninja Release core and Python bridge built together; the adapter loaded its `python` module directory. Nine local incremental build invocations including initial configure/build; one compile failure and five assertion-fixture correction cycles. Old assertions for Drain Soul targeting, Lifesteal overkill, no-target Secrets and Shatter propagation were reviewed independently rather than preserved as rules truth.

## Honest registry delta

Initial committed generated outputs were stale. Final regeneration preserves Rosetta source tree `c54f86221467d0a682c6331e83eb023e8eef7136da48763e711d26029165797a` and rules identity, while observation identity changes to `e195e293e38b45f224d88c680909288f6d8ef9ed7cb1ba5de9b43c0c28873edb`.

Current scoped canonical roots: 3 -> 0. Affected formerly current roots: `CORE_DRG_107`, `CORE_SW_072`, `CORE_SW_108`. Historical stale evidence count: 23 -> 27, also including previously unverified `CORE_ULD_133`. No fingerprints copied and no PASS evidence installed. Rosetta native evidence was not rerun or promoted as a side effect of experimental work.

Root membership remains 1185; registered routes, dependency graph and closure unchanged. Newly supported profile roots: 0; CUSTOM additions: 0; complete dependency closures: 0 -> 0; training-eligible roots: 0 -> 0. ManaEngine scoped scenarios are not interchangeable with canonical Rosetta rules evidence.

## Remaining limits and stop

[CORRECTNESS_RULES_AUDIT.md](CORRECTNESS_RULES_AUDIT.md) records the independent sources, exact prototype contracts and every unresolved rules question. CATA_489, JAIL_321, CATA_487 and several Secret interactions are not fully verified. Water Elemental and Viper are unsupported. No actual Tricky Burn Mage deck reaches DECK_READY; broad dynamic pool/session requirements remain open.

Verdict after local repairs: `SAFE_AFTER_FIXES` for the narrow experimental prototype, pending hosted checks. This does not certify full Hearthstone rules, training, search or production migration. STOP after hosted acceptance and report/push; the next deck-closure step requires a separate review checkpoint.
