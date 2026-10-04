# Phase 4 correctness hardening completion

Package: `prototype_correctness_hardening_v1`.
Baseline: ManaMind `a62ff5fb2f7d48498aea7e913a46ab24ad723286`.
Branch: `codex/manaengine-first-deck`.
RosettaStone pinned and unchanged: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
Active work start: 2026-10-04 09:04:32 UTC. Implementation/report commit `ba5616541deed434882f7d6afbb0fb84b9d4cb10` at 10:05:00 UTC: 60 minutes 28 seconds observed elapsed, including authoring/review/debug/build/tests. Hosted results and logs confirmed at 10:08:03 UTC: 63 minutes 31 seconds through first acceptance, including about three minutes of hosted acceptance wait. No user-response waiting or card expansion occurred. These are observed elapsed intervals, not sampled CPU time or separate authoring-hour estimates.

## Repairs

One shared typed damage path now handles combat, spells/composed effects, Secret damage, hero power, end-turn effects and fatigue. It centralizes minion shield/Immune, hero armor, full-overkill Lifesteal, spell-damage event publication and damage state. Hero-to-minion retaliation is restored; weapon consumption and after-attack triggers remain tested.

Attack Secret eligibility is target-based, activation ordered and cancellation-aware. Secret damage uses shared prevention/accounting. No living target leaves Flames armed. Water Elemental cannot silently execute as vanilla; Oasis becomes explicitly invalid when that unsupported outcome is required. Metadata coverage rejects unrepresented mechanics, including Viper Tradeable. Fabricated dependency IDs and production diagnostic tracker were removed.

Death processing removes simultaneous dead minions from both boards before any ordered deathrattle and evaluates terminal state after mandatory processing. Simultaneous lethal heroes and double fatigue yield DRAW. This follows the previously approved prototype semantics; exact full-game ordering is not certified.

Prepare follows reviewed useful-spend/one-use rules. Prepared zero-cost cards are playable after their turn lock without poisoning `legal_actions()`. Shatter inherited modifiers and modified merges fail closed until independently established. Shared transform replaces instance content through a defined prototype contract.

Public observation schema is 14, with progress, trigger availability, discounts, timed effects and SELF Choice candidates. Existing checkpoints cannot silently reuse schema 13. Unsupported hero-power sessions fail; backend training admission remains blocked. Catalog/data/report changes trigger experimental CI. Adapter declaration fields are allowlisted, and random Mage Secret membership is checked against an explicit reviewed six-ID manifest, not a magic cardinality.

## Actual local results

| Check | Observed result |
|---|---|
| Windows local Debug native suite | PASS, 30 scenario groups / 537 assertions; CTest 1/1, 44.57 seconds |
| Python adapter + pipeline | PASS, 36 tests, 30.94 seconds |
| Full repository Python suite | PASS, 84 tests, 11.68 seconds |
| Ruff src/tests/scripts/adapter tests | PASS |
| Generic card-ID AST guard | PASS, 201 existing reviewed exceptions |
| Pinned regeneration | PASS, 36 outputs reproduced on repeated run |
| git diff whitespace check | PASS |
| Source CI Win/Ubuntu | PASS on ba56165; real pytest 84/84, Windows 7.37s / Ubuntu 11.19s |
| ManaEngine CI Win/Ubuntu | PASS on ba56165; Release CTest 1/1 and adapter/schema 36/36 on both |

Native build: fresh `%TEMP%/ManaEngineCorrectnessBuild`, MSVC/Ninja Debug core and Python bridge built together; the adapter loaded its `python` module directory. The cache/build.ninja was inspected directly: `ctest -C Release` does not change a single-config Ninja Debug build. Hosted builds independently use Release on both OSes. Nine local incremental build invocations including initial configure/build; one compile failure and five assertion-fixture correction cycles. Old assertions for Drain Soul targeting, Lifesteal overkill, no-target Secrets and Shatter propagation were reviewed independently rather than preserved as rules truth.

Hosted [Source run 37194189875](https://github.com/MaksimOrekhov/manamind/actions/runs/37194189875) passed regeneration, empty Git diff and actual full pytest on both operating systems. Hosted [ManaEngine run 37194189890](https://github.com/MaksimOrekhov/manamind/actions/runs/37194189890) passed Release CTest (Windows 1.30s / Ubuntu 1.08s) and adapter/schema tests (Windows 12.66s / Ubuntu 17.94s). Actual fetched job statuses and selected log lines are archived in `CORRECTNESS_CI_EVIDENCE.json`. They certify the implementation commit, not full card rules or training admission.

## Honest registry delta

Initial committed generated outputs were stale. Final regeneration preserves Rosetta source tree `c54f86221467d0a682c6331e83eb023e8eef7136da48763e711d26029165797a` and rules identity, while observation identity changes to `e195e293e38b45f224d88c680909288f6d8ef9ed7cb1ba5de9b43c0c28873edb`.

Current scoped canonical roots: 3 -> 0. Affected formerly current roots: `CORE_DRG_107`, `CORE_SW_072`, `CORE_SW_108`. Historical stale evidence count: 23 -> 27, also including previously unverified `CORE_ULD_133`. No fingerprints copied and no PASS evidence installed. Rosetta native evidence was not rerun or promoted as a side effect of experimental work.

Root membership remains 1185; registered routes, dependency graph and closure unchanged. Newly supported profile roots: 0; CUSTOM additions: 0; complete dependency closures: 0 -> 0; training-eligible roots: 0 -> 0. ManaEngine scoped scenarios are not interchangeable with canonical Rosetta rules evidence.

## Remaining limits and stop

[CORRECTNESS_RULES_AUDIT.md](CORRECTNESS_RULES_AUDIT.md) records the independent sources, exact prototype contracts and every unresolved rules question. CATA_489, JAIL_321, CATA_487 and several Secret interactions are not fully verified. Water Elemental and Viper are unsupported. No actual Tricky Burn Mage deck reaches DECK_READY; broad dynamic pool/session requirements remain open.

Verdict: `SAFE_AFTER_FIXES` for the narrow experimental prototype, with hosted checks passed. This does not certify full Hearthstone rules, training, search or production migration. STOP after report/push; the next deck-closure step requires a separate review checkpoint. The final report-only commit is checked by both workflows again; it does not change the verified engine/schema tree.
