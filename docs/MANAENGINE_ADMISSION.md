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

## Local damage boundary, version 1

Ordinary spell Damage instructions use CURRENT_AT_STEP: base amount + current board Spell Damage + persistent played-instance bonus. One area instruction evaluates once for all its packets. Arcane Missiles uses the separate MISSILE_TOTAL contract: bonus affects the once-evaluated count, each missile deals one. Secret packets retain their fixed reviewed amounts; minion Battlecry damage receives no Spell Damage. These modes do not add stabilization between instructions or change the global trigger/death scheduler.

Sleet Storm (CATA_485) is a declarative two-instruction consumer. Damaging an undamaged friendly 1/3 Time-Twisted Seer first deals two; its now-active +2 aura makes the random enemy-minion instruction deal three. Selection uses the actual enemy board, without filtering unsupported cards or excluding a surviving initial target. Empty board consumes no RNG.

This is scoped support, not full root/deck closure. A mortally wounded unsilenced friendly Spell Damage source before another ordinary Damage instruction fails closed. Random minion selection after a pending board death also fails closed: its timing versus deathrattles/removal needs independent review. Such a branch invalidates the session. Arcane Barrage (TIME_855) remains unimplemented pending target selection/distinctness/mortality/per-hit boundary review. See the [proposal](../reports/manaengine_phase4b_20261004/DAMAGE_BOUNDARY_PROPOSAL.md) and completion evidence for the bounded verification scope.

## Direct spell damage turn accounting and fixed summon, version 1

DamageKind and damage attribution are independent. Only explicitly reviewed DirectSpell packets update the controller's internal spell_damage_dealt_this_turn: full unprevented damage including overkill and Armor absorption; zero for Divine Shield/Immune. ExternalSpellEffect and unreviewed Spell-kind packets do not update it. Ordinary spell instructions, unit missiles and actual Explosive Runes damage use DirectSpell. Flames of Infinity's legacy destroy-through-damage placeholder does not establish direct damage; its separate existing rules limitations remain open. Skeleton Key is not implemented by adding this source distinction.

Both controllers' counters reset at global turn rotation, after end-turn reactions and before the next draw. Off-turn Secret damage belongs to the ending global turn and cannot reduce a spell's cost next turn. A declarative coefficient applies through effective_cost; existing base metadata, current_cost, legal-action card_cost and Policy encoding remain separate. This package adds no public field, encoder feature or checkpoint schema: the effective hand/action cost carries its observable result. It does not claim complete future Markov coverage.

Spellweaver's Brilliance (CATA_452) uses coefficient one and the generic SUMMON_FIXED step for CATA_452t (Azure Warden, vanilla 6/6 Dragon). A new finite dependency archive records canonical identity/provenance separately from the unchanged Standard snapshot. The spell can resolve on a full seven-minion board; no extra token is instantiated, burned or killed. Supported exact minion dependencies and parameter combinations are validated; unknown/unrepresented outcomes fail closed. Scoped package verification does not admit the frozen Mage deck or training; read SPELLWEAVER_PROPOSAL.md and SPELLWEAVER_COMPLETION.md under reports/manaengine_phase4b_20261004 for evidence and remaining blockers.
