# ENGINE-GATE-0 — Multi-class Hero Power support v1: completion record

Date 2026-10-08. Branch `claude/engine-gate-0-hero-powers`, based on `origin/main` `55d06d065b7e95dc3e70be61aedf45d2cd431f1f`. Design record: [docs/proposals/20261008_engine_gate0_hero_powers_v1.md](../../docs/proposals/20261008_engine_gate0_hero_powers_v1.md).

## Result

| Axis | Status |
|---|---|
| Runtime simulation | Prototype sessions now admit Mage, Priest, Hunter and Warrior seats in any of the 16 pairings; each seat starts with its reviewed base Hero Power. Every other class is rejected (`UNSUPPORTED_HERO_CLASS`). |
| Rules basis | `REVIEWED` for identity, cost 2, once per turn and the four effects (pinned capture text). `OPEN`, applied as specified: the Cleansing-Cleric-style healing bonus also modifies Lesser Heal (shared `apply_healing`); no Power.log sample exists for it. |
| Dependency closure | Three non-collectible Hero Power metadata rows added; no tokens, pools or enchantments. Collectible Standard membership unchanged (verified by test). |
| Training eligibility | Unchanged: `training_eligible` is `False`, `require_training_admission()` still raises, `check_generated_artifacts.py` reports `Training admission: BLOCKED`. The unsupported-card-in-hand gate is not relaxed. |
| Real-game state | **Not enabled.** No importer exists; a real state cannot be represented (see limitations). |

## Hero Powers implemented and verified IDs

| Class | Card ID | Name | Pinned text | Cost | Encoding |
|---|---|---|---|---|---|
| MAGE | `HERO_08bp` | Fireblast | Deal $1 damage. | 2 | `DAMAGE / EXPLICIT_CHARACTER / 1` (targeted) |
| PRIEST | `HERO_09bp` | Lesser Heal | Restore #2 Health. | 2 | `HEAL / EXPLICIT_CHARACTER / 2` (targeted) |
| HUNTER | `HERO_05bp` | Steady Shot | Deal $2 damage to the enemy hero. | 2 | `DAMAGE / ENEMY_HERO / 2` (untargeted) |
| WARRIOR | `HERO_01bp` | Armor Up! | Gain $d2 Armor. | 2 | `GAIN_ARMOR / SELF / 2` (untargeted) |

Provenance: `https://api.hearthstonejson.com/v1/latest/enUS/cards.json`, sha256 `e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65`, captured 2026-10-04 (the same capture `dependency_metadata_audit.json` already pins; re-downloaded and the digest compared). Cost 2 and the targeting wording also agree with the older RosettaStone `cards.json`. Nothing was guessed: skin/variant IDs (`HERO_01dbp`, `HERO_05dbp`, `HERO_08aabp`, ...) are not aliased and stay unsupported.

## Shared architecture changes

* `hero_power.hpp`: the reviewed starting-power table and the reviewed step set. This table is the only per-class data.
* `PlayerState::hero_power_id`: the current power is state. `hero_power_definition(owner)` is the single accessor; unknown/empty/non-power/`UNSUPPORTED` identities throw the new `UNSUPPORTED_HERO_POWER` from construction, `legal_actions`, `semantic_legal_actions`, `observation` and `validate_invariants`. The class is never consulted after construction.
* `legal_actions`, `semantic_legal_actions`, `execute_action` and `observation` no longer contain Mage or `HERO_08bp` literals; execution goes through `use_hero_power` → `resolve_effects` (damage-group `HeroPower` kind, `apply_healing`, `GAIN_ARMOR`).
* Catalog validation for supported Hero Powers (non-collectible `EFFECT_COMPOSITION`, reviewed kind/selector pairs, one explicit target at most, no extra step fields); `ENEMY_HERO` is rejected on every other card type. The pre-gate `TARGET_DAMAGE` Fireblast encoding is normalised in the catalog to the same effect list.
* Python session: the duplicated Mage gate is gone; the native constructor owns it and its typed failure is wrapped.

## Added metadata / dependencies

`experiments/manaengine/data/hero_power_dependency_metadata.json` (3 rows copied verbatim from the capture above, registered in `engine.py` `dependency_files`), three declarations plus the Fireblast migration in `card_abilities.json`. The catalog now has 1218 definitions (102 `SUPPORTED`, 15 `VERIFIED_VANILLA`, 1101 `UNSUPPORTED`; the four Hero Powers are `SUPPORTED`).

## Public action / observation schema changes

* **Action:** the `HERO_POWER` action of an untargeted power (Hunter, Warrior) has no `target_entity_id` (native `-1`) and empty target fields; targeted powers (Mage, Priest) are unchanged. `action_from_dict` accepts a `HERO_POWER` without a target. Semantic fields (`card_id`, `card_type=HERO_POWER`, `card_cost`) now name the seat's current power.
* **Observation:** no field added or removed. `hero_power` and `hero_power_ready` are now exported for all four classes (and for both perspectives); `hero_power_ready` keeps its previous meaning (not exhausted). `player_class` takes the four values.
* **Declarations / failures:** appended `TargetSelector::EnemyHero` (Python `ENEMY_HERO`), appended `FailureCode::UNSUPPORTED_HERO_POWER = 59` (Unsupported); no existing numeric identity changed.
* **Checkpoints:** `STATE_ENCODING_SCHEMA_VERSION` stays 16; feature names and the vocabulary are untouched. The new power IDs are outside the Standard-catalog vocabulary and encode as the existing unknown-card index (test). Policy/Value checkpoints stay usable.

## Tests executed

| Check | Result |
|---|---|
| Native `manaengine_tests` (all groups, incl. new `--hero-power` family and codes 58/59 in the failure-funnel loop) | 79 groups, 18484 assertions passed |
| `--hero-power`, `--healing`, `--damage-group`, `--arcane-barrage`, `--fire-pool` | 15776 / 87 / 173 / 142 / 228 passed (the large hero-power count is dominated by the 128 random mixed-class trajectories checking invariants and raw/semantic parity at every step) |
| `experiments/manaengine/tests` | 148 passed (31 new in `test_hero_powers.py`; one Prepare fixture and one class-rejection probe updated because Fireblast now needs its effect and Warrior is supported) |
| Full `pytest` | 510 passed, 1 skipped |
| `ruff check`, `check_generic_card_branches.py`, failure-site audit `check`, `check_generated_artifacts.py` (two runs, clean tree) | all pass |
| Differential Mage regression | The same seeded random Mage-mirror transcript (80 games, up to 120 steps, 31,832 legal actions of which 4,839 Hero Power, all actions and both perspectives' observations hashed) run under an unmodified `origin/main` build and this build produced the identical SHA-256 `08528e4cbbd90c2ae13c3f5391ecf5e9ffcc8c8297a3dcb2834070fcaf1f3f6f` |

Hosted CI (Windows and Ubuntu) passed on `2558352`. In the review-fix commit the ManaEngine experimental workflow replaced its explicit per-file selection from `experiments/manaengine/tests` with the whole directory (adapter, simulation-attempt, native-failure, healing, QUICK-1..5 and Hero Power tests); the root-level tests stay explicitly selected. CI-only change.

## Remaining unsupported / evidence debt

1. **Real-state simulation is not enabled.** There is no importer; only brand-new prototype sessions start at a base power. A real state with another class, a replaced, upgraded, Imbued or modified power, or an unknown power cannot be created and an unreviewed identity fails closed (`UNSUPPORTED_HERO_POWER`), never as the class's base power. The unsupported-card-in-hand gate is unchanged, so real Priest/Hunter/Warrior decks still fail closed on their cards.
2. **Healing bonus on Hero Power healing is applied by specification, not by evidence** (OPEN above); the cross-side case fails closed with `HEALING_BONUS_SCOPE_UNREVIEWED`. No `EvidenceConstraint` was introduced for it.
3. Not implemented: Imbue, Quests, Locations, Hero Power replacement/upgrade, cost modifiers, extra uses (the engine has no state for them, so nothing can silently apply), the remaining seven classes (Death Knight, Demon Hunter, Druid, Paladin, Rogue, Shaman, Warlock), determinization/search.
4. Hero Power damage uses the same targeting as the previous Fireblast (no stealth/untargetable filtering exists anywhere in `legal_targets`); `Elusive`/`Stealth` interactions stay as unmodelled as for spells.
5. Linux/GCC compilation was not available locally; the hosted Ubuntu job is the check.
6. Resolved in the review fix: the experimental CI now runs the whole `experiments/manaengine/tests` directory, so the healing and QUICK-1..5 tests also run in hosted CI.

## Measurements

Declaration-only consumers after the shared change: 3 new reviewed powers plus the migrated Fireblast; two synthetic native powers confirm no session code is needed for a new power. New card-ID behaviour branches: 0. Correction cycles: 4 (a mangled newline in a patch string, Spell Damage fixture ability, test fatigue from emptied decks, an Armor-blind oracle). Native builds: 6 incremental, about 1 minute each; one extra baseline build for the differential check.
