# Experimental ManaEngine admission and information boundary

ManaEngine is an explicitly authorized isolated experimental backend. Its internal state is authoritative; ManaMind GameState is a separate player-visible projection. Existing RosettaStone canonical evidence does not certify ManaEngine rules.

## Development and training

A successful development branch, a registered declaration, or a scoped scenario is not training admission. `ManaEngineSession.training_eligible` remains false and `require_training_admission()` fails before episode collection. There is currently no ManaEngine training dataset producer. A future producer must require current backend-specific evidence for the selected environment: legal deck/class/hero-power initialization, every root's complete rules, transitive static dependencies, all reachable dynamic outcomes, action/observation support, session lifecycle and repeated complete matches. Pool membership must remain complete. Unsupported episodes must fail collection and invalidate the run; silently dropping them would bias the surviving labels.

Only Mage hero-power sessions are admitted to ordinary development simulation. Cross-class decks in focused adapter tests are semantic fixtures, not legal decks or deck-readiness evidence. Tests use real declarations and do not install diagnostic cards in production catalog configuration. Diagnostic traces may contain hidden identities and are a separate debugging channel; GameState serialization, encoders and datasets must never consume them.

## Search hard gate

Full-state `clone()` is allowed for authoritative simulation, environment branching and deterministic tests. BEFORE MCTS, real-game search or search-generated targets, implement an information-set/determinized search-state boundary. Never use the present full-information clone to select real-game actions. This checkpoint does not implement determinized clone or authorize search/training.

## Observation scope

Schema 14 adds public cast counts/discounts and missing-value masks, timed effect identities/durations, SELF held progress, per-instance trigger availability, Prepare-used state, Freeze duration, and SELF pending Choice candidates. Hidden opponent choice identities, hand/deck identities, RNG state, deck order and internal activation sequence are excluded. Legal action descriptors carry effective selected-card cost. A public-state audit is not a declaration of complete Hearthstone Markov coverage: disputed ordering and future unsupported mechanics still block complete rules/admission evidence.

## Metadata versus rules

`dependency_metadata_audit.json` is a finite archived identity audit from HearthstoneJSON captured 2026-10-04; its complete-response SHA and URL are recorded. It does not replace the 2026-10-01 Standard scope or prove historical token rules. Future dependency snapshot reconciliation must explicitly review differences. `EX1_100t` and `CORE_SW_108t` were absent; use actual `CS2_tk1` and `SW_108t`. Water Elemental's Freeze-on-damage and Viper's Tradeable are unsupported and block their complete closures.

Exact reviewed declaration text plus explicit required mechanic representation is an authoring guard, not rules verification. Changes or unmodeled mechanics fail closed. Static keyword-only vanilla cards may have nonempty text. Shatter pre-split modifier inheritance and ambiguous modifier merges remain partial/fail-closed pending independent verification; old duplication tests do not establish rules truth.
