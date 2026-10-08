# ENGINE-PRIMITIVE-1 — Healing pipeline v1: completion record

Date 2026-10-08. Branch `claude/engine-primitive-1-healing`, based on `origin/main` `d69a093`. Design record: [docs/proposals/20261008_engine_primitive1_healing_v1.md](../../docs/proposals/20261008_engine_primitive1_healing_v1.md).

## Result

| Axis | Status |
|---|---|
| Runtime simulation | Four Standard roots newly declared `SUPPORTED`: `EDR_476` Moonwell, `CORE_CS1_112` Holy Nova, `CORE_CFM_604` Greater Healing Potion, `CATA_216` Cleansing Cleric. ManaEngine declarations are now 99 `SUPPORTED`, 15 `VERIFIED_VANILLA`, 8 `UNSUPPORTED`. |
| Rules basis | `REVIEWED` for the packet calculation, additive stacking, persistence, per-packet Lifesteal and Health caps (card text plus 32-game Power.log evidence below). `OPEN` for a bonus holder healing a character it does not control: failed closed, not inferred. No `REVIEWED_INFERRED` behaviour and no new `EvidenceConstraint` was introduced. |
| Dependency closure | No new dependencies (no tokens, pools or enchantment identities materialised). Closures of the four roots are not otherwise audited by this package. |
| Training eligibility | Unchanged: still blocked. Nothing in this package grants canonical admission. |

## Shared contracts implemented

* One native `GameSession::apply_healing(source_controller, targets, base_amount, source)`; it is the only code that raises Health. Per target packet: `restored = min(base + controller bonus, own maximum Health - current Health)`.
* Routed through it: the `HEAL` effect step, Lifesteal healing in `apply_damage_packet` (one healing packet per damage packet) and the `HEAL_ENEMY_HERO` damage follow-up.
* New allowlisted effect kind `GRANT_HEALING_BONUS` (target `SELF`, 1..100, persistent, additive, total bounded by 1000) and selectors `ALL_FRIENDLY_CHARACTERS` (own hero, then own minions left to right) and `EXPLICIT_FRIENDLY_CHARACTER` (enforced at legality and again at execution).
* Atomicity: all targets are resolved and checked before any mutation. A pending-death target fails closed (`HEAL_MORTALLY_WOUNDED_UNREVIEWED`); a bonus holder healing a character it does not control fails closed with the new append-only `HEALING_BONUS_SCOPE_UNREVIEWED` (58, RuleUnresolved).
* Hero maximum Health is a separate field (`hero_max_health`, fixed 30 and checked by `validate_invariants`); no other start Health was admitted.

## Native / Python / state / schema changes

* `engine.hpp`: appended `EffectKind::GrantHealingBonus`, `TargetSelector::{AllFriendlyCharacters, ExplicitFriendlyCharacter}` (numeric identities of existing values preserved), `PlayerState::{hero_max_health, healing_bonus}`, `HealingSource`, `healing_bonus_limit`.
* `engine.cpp`, `damage_group.cpp`: pipeline, catalog validation through the existing `reject` site (Choose One, Lifesteal/other step fields, explicit-target sharing, bounds, `HEAL_ENEMY_HERO` amount), friendly-only legality for the hero as well as minions, invariants.
* `failure.hpp/.cpp`, `python_bindings.cpp`, `engine.py`: new code, enums, allowlists. `card_abilities.json`: four declarations. No generator, no card-ID branch, no per-card native code.
* Observation (review fix): `PlayerObservation.healing_bonus: int | None` (public; None = unknown, never inferred as 0), exported by ManaEngine for both seats, parsed/serialised by `game_state_from_dict`, accepted by the visible-schema validator; not an encoder feature (schema version 16, feature names and Policy v1/v2 checkpoints unchanged). `compare_reference.py` excludes the key because the Rosetta bridge cannot export it. `HEAL_MINION_TO_FULL` now applies a pipeline packet of exactly the missing Health (cross-side exempt because no bonus can change it).
* Failure ledger: `PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json` source hashes refreshed, one allowlist message updated, reason code 58 appended; `tests/test_native_failure_contract.py` count 57 -> 58.

## Rules evidence (Cleansing Cleric)

Corpus `data/processed_evidence/collected` (32 processed games, `evidence-0b.1`, build 253216). Cleric creates `CATA_216e` attached to the controller's player entity (55 attach facts, 0 removals, 39 Cleric deaths). Devouring Plague Lifesteal packets of 1 restore 1 / 3 / 5 with zero / one / two Clerics (additive stacking, per packet, Lifesteal included); Moonwell restores 4 / 6 / 8; after all Clerics of a game died, packets of 3 and 5 were still observed (persistence is independent of the minion). `HEALING_PACKET.amount` equals the real damage-tag change, i.e. the post-cap restored Health. Not verifiable from the corpus: a bonus holder healing the opponent's character (the single sample is capped at 1).

## Tests

| Check | Result |
|---|---|
| Native `manaengine_tests` (all groups) | 79 groups, 2683 assertions passed (74 are the new `--healing` family: area/single/friendly-only, caps, stacking, ownership for both seats, per-packet Lifesteal incl. combat, order and pending-death atomicity, persistence/clone, bound, 17 invalid declarations, existing Mage hero power and consumers) |
| `--damage-group`, `--arcane-barrage`, `--fire-pool` | 173 / 142 / 228 assertions passed |
| Mutation checks of the new family | 4/4 detected (bonus ignored, bonus on first target only, Lifesteal bypasses bonus, executor friendly check removed) |
| `experiments/manaengine/tests` | 115 passed (7 new in `test_healing_pipeline.py`; two older "neighbours stay unsupported" assertions were updated because Moonwell and Holy Nova are now declared) |
| Full `pytest` | 503 passed, 1 skipped |
| `ruff check`, `check_generic_card_branches.py`, failure-site guard, `check_generated_artifacts.py` (twice, clean tree) | all pass |

Hosted CI status is recorded in the final report after the push.

## Remaining limitations / evidence debt

1. **Bonus is public in `GameState` but not a model feature, and real-log imports leave it unknown (`None`).** The importer does not derive it from the `CATA_216e` enchantment (no catalog identity, no reviewed derivation); policies cannot yet condition on it until an encoder schema bump and retraining.
2. **Cross-side healing with a bonus** (e.g. Flash Heal on an enemy, `CATA_303` Purifying Breath to the enemy hero) is `RULE_UNRESOLVED`, fallback-eligible, never guessed. Invalidated/removable by a rules sample showing whether the bonus follows the healing controller regardless of target.
3. Moonwell/Holy Nova/Greater Healing Potion rules come from pinned card text and general Health rules; the corpus contains only opponent plays with matching packets (damaged targets only receive a packet). No test compares to a recorded engine/log replay.
4. Hero maximum Health is fixed at 30. Observed games with a 40-Health opponent hero (8 of 36) are outside the engine; they are not admitted.
5. No healing triggers, overheal, heal-to-damage conversion, multipliers, hero power heals or dynamic amounts. Deferred and still `UNSUPPORTED`: Lightshower Elemental, Priest of An'she, Amber Priestess, Lingering Spirit, Ruby Sanctum, Siphon Soul and others.
6. The adapter remains a Mage-mirror session; the Priest cards run only as semantic fixtures.
7. Linux/GCC compilation was not available locally; the hosted Ubuntu job is the check.

## Measurements

Declaration-only consumers of an existing contract after the shared change: 0 beyond the four cards; independent second consumers of the new contracts exist only as synthetic native fixtures (`TEST_HEAL_BONUS_ONE`, `TEST_HEAL_BONUS_THREE`, `TEST_MEND_ALL`, `TEST_LIFESTEAL_AREA`). Correction cycles: 2 (a partially applied patch script; ledger markers/hashes), plus 4 intentional mutation builds. Build runs: 7 native builds, about 1 minute each.
