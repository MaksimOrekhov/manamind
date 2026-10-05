# ManaEngine admission and information boundary

ManaEngine is ManaMind's primary forward simulator development backend, with bounded correctness and admission; it is not production-complete. Its internal state is authoritative during simulation; ManaMind `GameState` is a separate player-visible projection. Existing RosettaStone canonical evidence does not certify ManaEngine rules. See the [partial-simulator architecture](PARTIAL_SIMULATOR_ARCHITECTURE.md) for unknown-state handling, inferred behavior and future fallback boundaries.

## Development and training

A successful development branch, a registered declaration, or a scoped scenario is not training admission. `ManaEngineSession.training_eligible` remains false and `require_training_admission()` fails before episode collection. There is currently no ManaEngine training dataset producer. A future producer must require current backend-specific evidence for its selected environment: legal deck/class/hero-power initialization, the selected roots' required rules, transitive static dependencies, all reachable dynamic outcomes, action/observation support, session lifecycle and repeated complete matches. Pool membership must remain complete. Unsupported episodes must fail collection and invalidate the run; silently dropping them would bias the surviving labels.

### Runtime execution vs canonical training admission

These are independent status dimensions:

- **Mechanically executable:** this transition completes within the current ManaEngine contract.
- **Rules/evidence basis:** the behavior is reviewed, carries `REVIEWED_INFERRED` evidence debt, or remains unresolved/blocked.
- **Dependency closure:** required static and dynamic outcomes are independently closed or remain open.
- **Canonical training eligibility:** the complete applicable profile has passed its strict admission gates.

The current Fire pool is explicitly `REVIEWED_INFERRED`: it can be sampled for bounded runtime simulation, and sampling records `FIRE_POOL_MEMBERSHIP_INFERRED`. Its membership is not rules-verified, dependencies remain `OPEN`, and its manifest sets `training_eligible` to false. This is permitted runtime simulation with evidence debt, not a training exception. `ManaEngineSession.training_eligible` is false globally today. Do not add arbitrary numerical penalties to inferred transitions merely because they carry evidence debt.

An unsupported action can eventually remain rankable through a future higher-layer action-value evaluator, but that path is not implemented and cannot consume a fabricated or poisoned child state. A runtime transition's success does not itself close dependencies, verify rules, or permit canonical training.

Only Mage hero-power sessions are admitted to ordinary development simulation. Cross-class decks in focused adapter tests are semantic fixtures, not legal decks or deck-readiness evidence. Tests use real declarations and do not install diagnostic cards in production catalog configuration. Diagnostic traces may contain hidden identities and are a separate debugging channel; GameState serialization, encoders and datasets must never consume them.

## Search hard gate

Full-state `clone()` is allowed for authoritative simulation, environment branching and deterministic tests. BEFORE MCTS, real-game search or search-generated targets, implement an information-set/determinized search-state boundary. Never use the present full-information clone to select real-game actions. This checkpoint does not implement determinized clone or authorize search/training.

Phase 4K.1 `attempt_action` executes a canonical legal action on a clone and
exports a valid result from a fixed root seat. Its four outcomes are
`COMPLETED`, `UNSIMULATABLE`, `ILLEGAL` and `ENGINE_DEFECT`; only
`UNSIMULATABLE` reasons for unsupported/unresolved coverage are fallback eligible;
`NATIVE_BUDGET_LIMIT` is explicitly excluded. There is no fallback consumer yet.
A completed `REVIEWED_INFERRED` transition retains evidence debt and remains
blocked for canonical training. Failed attempts expose diagnostics only, with
no state/child or transition evidence.

The result and even its outcome can depend on hidden deck/RNG state in the
full-information clone. For example, `END_TURN` may become unsimulatable
because an opponent hidden draw is unsupported. The retained child is an
internal full-information handle, not a visible model feature or permission
for live-root decision-making. Phase 4K.1b classifies typed native payloads;
diagnostic text is not used. `ENGINE_DEFECT`, untyped failures and BudgetLimit
are never fallback eligible. Typed error records are internal diagnostic evidence,
not model features. `Q_fallback` remains absent, and training/live-root gates
remain unchanged.

## Observation scope

The current value-state encoder version is `STATE_ENCODING_SCHEMA_VERSION = 16` in `src/manamind/encoding/state_encoder.py`. Version 16 includes public cast counts/discounts and missing-value masks, timed effect identities/durations, SELF held progress, per-instance trigger availability, Prepare-used state, Freeze duration, SELF pending Choice candidates, and both players' current/previous own-turn minion-type presence. Type history is a canonical semantic set with UNKNOWN distinct from known empty; it contains no card/event log or entity identities. Version 15 was the preceding state contract; checkpoints with a different state-encoding schema are incompatible. The Rosetta policy action contract has a separate `POLICY_ACTION_SCHEMA_VERSION = 3` in `src/manamind/integrations/rosettastone/policy.py`. Hidden opponent choice identities, hand/deck identities, RNG state, deck order and internal activation sequence are excluded. Legal action descriptors carry effective selected-card cost. A public-state audit is not a declaration of complete Hearthstone Markov coverage: disputed ordering and future unsupported mechanics still block complete rules/admission evidence.

## Metadata versus rules

`dependency_metadata_audit.json` is a finite archived identity audit from HearthstoneJSON captured 2026-10-04; its complete-response SHA and URL are recorded. It does not replace the 2026-10-01 Standard scope or prove historical token rules. Future dependency snapshot reconciliation must explicitly review differences. `EX1_100t` and `CORE_SW_108t` were absent; use actual `CS2_tk1` and `SW_108t`. Water Elemental's Freeze-on-damage and Viper's Tradeable are unsupported and block their complete closures.

Exact reviewed declaration text plus explicit required mechanic representation is an authoring guard, not rules verification. Changes or unmodeled mechanics fail closed. Static keyword-only vanilla cards may have nonempty text. Shatter pre-split modifier inheritance and ambiguous modifier merges remain partial/fail-closed pending independent verification; old duplication tests do not establish rules truth.

## Local damage boundary, version 1

Ordinary spell Damage instructions use CURRENT_AT_STEP: base amount + current board Spell Damage + persistent played-instance bonus. One area instruction evaluates once for all its packets. Arcane Missiles uses the separate MISSILE_TOTAL contract: bonus affects the once-evaluated count, each missile deals one. Secret packets retain their fixed reviewed amounts; minion Battlecry damage receives no Spell Damage. These modes do not add stabilization between instructions or change the global trigger/death scheduler.

Sleet Storm (CATA_485) is a declarative two-instruction consumer. Damaging an undamaged friendly 1/3 Time-Twisted Seer first deals two; its now-active +2 aura makes the random enemy-minion instruction deal three. Selection uses the actual enemy board, without filtering unsupported cards or excluding a surviving initial target. Empty board consumes no RNG.

This is scoped support, not full root/deck closure. A mortally wounded unsilenced friendly Spell Damage source before another ordinary Damage instruction fails closed. Random minion selection after a pending board death also fails closed: its timing versus deathrattles/removal needs independent review. Such a branch invalidates the session. Arcane Barrage (TIME_855) has a bounded executable declaration (random-distinct extras, Phase 4I.1) that records the targeting evidence constraint `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` (hero membership, distinctness, insufficient-candidate behavior) whenever its extras instruction executes; the constraint blocks canonical training admission, and the card is neither rules-verified nor training eligible. See the [rules-evidence audit](../reports/manaengine_arcane_barrage_20261005/ARCANE_BARRAGE_RULES_EVIDENCE.md) and the [proposal](../reports/manaengine_phase4b_20261004/DAMAGE_BOUNDARY_PROPOSAL.md) and completion evidence for the bounded verification scope.

## Previous own-turn type history and bounded instance copy

TLC_226 is a declaration-only experimental consumer of filtered spell Deathrattle draw and INSTANCE_COPY_V1, gated by previous-own-turn matching minion type. History records hand-played minions, including all canonical types; ALL expands to the finite reviewed type set. Summon, generation, recruitment and transform do not record plays. After the ending player's reactions/stabilization, only that player's current set rotates into previous and current clears. Deep clone preserves independent histories.

The user-reviewed minion-play phase model places Kindred after original entry and before After Play/After Summon reactions. The exact reviewed Explosive Runes scenario creates the copy before Runes targets the original execution entity. Evidence status is RULES_REVIEWED_FROM_PHASE_MODEL, not DIRECT_REPLAY_VERIFIED; no Bookkeeper Power.log was captured. Current admitted copies introduce no summon reaction source; newly supported nested reactions require their own review rather than a speculative new scheduler.

INSTANCE_COPY_V1 explicitly transfers identity and admitted stats field by field, assigns new entity/activation identities, recomputes ownership/placement/provenance and resets ordinary summon attack bookkeeping. It rejects non-default unreviewed modifiers, counters, enchantments, Freeze/silence/keywords, links, Prepare, damage, control change, aura ownership and non-rightmost sources. Guards precede play normalization and run again at snapshot; failed branches invalidate the session. No clean-base substitution or blanket struct copy. Full-board minion legality and failed summon capacity remain ordinary engine rules.

This consumer is PARTIAL. Whelp-generated hand buffs and broader generated/reaction state remain blockers; no full root/deck closure or training admission is granted. The TLC_226 change recorded at that time changed the observation fingerprint under schema 15. Schema 16 is current; historical stale Rosetta evidence is not promoted or recertified by ManaEngine scenarios. See INSTANCE_COPY_V1_CONTRACT_REVIEW.md and BOOKKEEPER_COMPLETION.md under reports/manaengine_phase4b_20261004.

## Direct spell damage turn accounting and fixed summon, version 1

DamageKind and damage attribution are independent. Only explicitly reviewed DirectSpell packets update the controller's internal spell_damage_dealt_this_turn: full unprevented damage including overkill and Armor absorption; zero for Divine Shield/Immune. ExternalSpellEffect and unreviewed Spell-kind packets do not update it. Ordinary spell instructions, unit missiles and actual Explosive Runes damage use DirectSpell. Flames of Infinity's legacy destroy-through-damage placeholder does not establish direct damage; its separate existing rules limitations remain open. Skeleton Key is not implemented by adding this source distinction.

Both controllers' counters reset at global turn rotation, after end-turn reactions and before the next draw. Off-turn Secret damage belongs to the ending global turn and cannot reduce a spell's cost next turn. A declarative coefficient applies through effective_cost; existing base metadata, current_cost, legal-action card_cost and Policy encoding remain separate. This package adds no public field, encoder feature or checkpoint schema: the effective hand/action cost carries its observable result. It does not claim complete future Markov coverage.

Spellweaver's Brilliance (CATA_452) uses coefficient one and the generic SUMMON_FIXED step for CATA_452t (Azure Warden, vanilla 6/6 Dragon). A new finite dependency archive records canonical identity/provenance separately from the unchanged Standard snapshot. The spell can resolve on a full seven-minion board; no extra token is instantiated, burned or killed. Supported exact minion dependencies and parameter combinations are validated; unknown/unrepresented outcomes fail closed. Scoped package verification does not admit the frozen Mage deck or training; read SPELLWEAVER_PROPOSAL.md and SPELLWEAVER_COMPLETION.md under reports/manaengine_phase4b_20261004 for evidence and remaining blockers.
