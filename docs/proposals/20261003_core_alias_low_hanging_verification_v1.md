# Verification Harvest Completion — `profile_core_alias_low_hanging_verification_v1`

Completed 2026-10-03 against `meta_training_20261002_v1`, `standard_full_20261001_v1`, registry revision `945d89116e072b7a3be936b8c4e837896b875d86`.

## Scope

Verified only `CORE_DRG_107` Violet Spellwing, `CORE_SW_072` Rustrot Viper and `CORE_SW_108` First Flame. All reuse existing Core alias declarations and their existing base CardDefs. No new engine capability, CardDef generator branch, or card-ID behavior was added. `CORE_DRG_024` Sky Raider remains excluded because source inspection identifies random Pirate generation despite its incomplete pool classification.

## Completion record

| Metric | Result |
|---|---|
| Elapsed time | Not captured by a package timer; do not use the pre-run estimates as measured duration. |
| Candidate roots | 3, across 2 profile decks (Mage and Demon Hunter) |
| Current scoped-verified roots gained | +3 in Meta Profile and canonical Standard registry |
| Declaration-only consumers | 3 existing aliases; no new declarations or renderer changes |
| Shared engine/generator changes | 0 production changes; one native test source extension and one Python evidence runner |
| Native scenarios | 3 functional scenarios: existing base Violet Spellwing and Rustrot Viper tests plus the existing First Flame alias test. Existing 65-alias structural parity test also passed. |
| Native assertions | 789 total across the four selected runs: 780 alias structural parity assertions, 2 Violet Spellwing assertions, 2 Rustrot Viper assertions, and 5 First Flame assertions. |
| Bridge checks | 3 loaded-bridge Standard sessions: deck validation, SELF-hand identity and legal-action enumeration. |
| Build / correction cycles | Several native build/runner attempts; the final configured build and evidence producer passed on the pinned source. An exploratory test edit inside the RosettaStone submodule was reverted so its pinned revision stayed unchanged. |
| Registry delta | +0 generated registrations; +3 current scoped rules-evidence roots. |
| Dependency closure delta | +0 complete closures. Static alias/outcome edges are recorded but remain unreviewed as complete transitive closure. |
| Training eligibility delta | 0; all three roots remain blocked by incomplete closure/profile and session-match gates. |
| Python / source checks | Python suite 80 passed; generator output reproducibility 36/36; generic-branch guard passed; Ruff passed after removing an unused import. |

The exact completion evidence is in `integrations/rosettastone/card_rules/core_aliases.evidence.json`; regeneration outputs are in the pinned registry and Meta Profile report. Full native regression baseline evidence from before adding the focused scenarios is preserved at `reports/meta_training_20261002_v1/native_full_suite_945d891.txt` and described in the corrected Package 2 Completion Record.
