# CAPABILITY PACKAGE PROPOSAL — ENGINE-GATE-0 Multi-class Hero Power support v1

## package_id

`engine_gate0_hero_powers_v1`, revision 1, 2026-10-08. Base: `origin/main` `55d06d065b7e95dc3e70be61aedf45d2cd431f1f`. Pinned inputs: `data/cards/standard_current_enUS.json` (profile `standard_full_20261001_v1`, collectible Standard membership untouched) and the dependency capture `https://api.hearthstonejson.com/v1/latest/enUS/cards.json` (sha256 `e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65`, captured 2026-10-04) that `dependency_metadata_audit.json` already pins. This is an engine gate, not a card-support package: it removes the Mage-mirror restriction of the prototype session constructor.

## semantic capability

Contract `hero_power`, v1, **REUSABLE_CAPABILITY** (one shared definition/dispatch path for per-seat state, availability, targeting, cost, effect execution and observation; no card-ID behaviour branch).

**Identity is state, class is not evidence.** Each seat stores `PlayerState::hero_power_id`. A newly created *prototype* session fills it from the reviewed starting table (`hero_power.hpp`: MAGE `HERO_08bp`, PRIEST `HERO_09bp`, HUNTER `HERO_05bp`, WARRIOR `HERO_01bp`). Every consumer (legality, execution, observation, invariants) reads the stored identity through `hero_power_definition(owner)`, which throws the typed `UNSUPPORTED_HERO_POWER` for an empty, unknown, non-`HERO_POWER` or `UNSUPPORTED` identity. A replaced/imbued/unreviewed power is therefore never replaced by the class's base power, and a Mage seat holding a reviewed non-Mage power behaves as that power (native test HP90). Real-state import is not implemented and must set the identity explicitly or stay unsupported.

**Definition.** A supported Hero Power is a non-collectible catalog card of type `HERO_POWER`, ability `EFFECT_COMPOSITION`, with a non-empty effect list drawn from the reviewed set and at most one explicit target step:

| step | allowed selectors |
|---|---|
| `DAMAGE` | `EXPLICIT_CHARACTER`, new `ENEMY_HERO` (Hero Power only) |
| `HEAL` | `EXPLICIT_CHARACTER`, `EXPLICIT_FRIENDLY_CHARACTER` |
| `GAIN_ARMOR` | `SELF` |

Cost is the printed cost (0..10). Everything else (other kinds/selectors, lifesteal, random fields, Choose One, outcome follow-ups, collectible, `ENEMY_HERO` on any other card type) is rejected at catalog load. The pre-gate Fireblast encoding (`TARGET_DAMAGE` + `damage`) is normalised to the same effect list by the catalog.

**Availability and readiness.** Usable = not used this turn and Mana >= cost; one use per turn (a hero freeze does not block it); the flag is cleared at the owner's turn start, so an exhausted power stays exhausted through the opponent's turn. Observation `hero_power_ready` keeps its previous meaning (not exhausted; Mana is exported separately), so Policy/Value features are unchanged. There is no cost-modifier or extra-use state in the engine; any future one must go through `hero_power_cost()` / `hero_power_usable()` and fail closed.

**Targeting and encoding.** Explicit-target powers (Fireblast, Lesser Heal) advertise one action per legal character through the existing `legal_targets`; untargeted powers (Steady Shot, Armor Up!) advertise exactly one action with no target handle (`target_entity_id` absent in the Python dict, `-1` natively). Execution rejects a mismatched shape (`LEGALITY_EXECUTION_MISMATCH`); illegal caller input remains a non-poisoning `invalid_argument`.

**Execution** reuses `resolve_effects` with the hero as source: damage goes through the existing damage group with `DamageKind::HeroPower` (no Spell Damage, no spell attribution, Armor/Divine Shield/prevention as for any packet); healing goes through `apply_healing` (controller bonus per packet, Health caps, pending-death and cross-side-bonus fail-closed rules); Armor uses the existing `GAIN_ARMOR` step and never changes Health.

**Why another Hero Power is declaration-only.** A new power is one catalog row plus one `card_abilities.json` declaration; native tests exercise two synthetic powers (`TEST_POWER_FRIENDLY_HEAL`, cost 1; `TEST_POWER_ARMOR_THREE`, cost 3) with no session code change. Only a new class's *starting* power needs one row in the reviewed table.

### Rules basis and bounded uncertainty

Rules basis: `REVIEWED` for identity, cost, once-per-turn and the four effects (printed text of the pinned capture; cost 2 and targeting agree with the older RosettaStone `cards.json`). `OPEN` (unverified, applied as specified by the task): whether the persistent controller healing bonus (Cleansing Cleric) applies to Hero Power healing; the engine routes Lesser Heal through `apply_healing` and therefore applies it, and the cross-side case stays fail-closed. No evidence sample exists in the Power.log corpus for this interaction. Invalidation: any change of the four texts/costs, of the healing-pipeline contract, or a sample showing hero-power healing is not modified by the bonus. No `EvidenceConstraint` was added (the debt is recorded here and in the completion record); canonical training admission is unchanged.

## existing RosettaStone primitives

Not used; ManaEngine is the development backend. Reused ManaEngine primitives: `EFFECT_COMPOSITION` effect lists, damage groups (`HeroPower` kind), Healing pipeline v1, `GAIN_ARMOR`, `legal_targets`, the failure funnel.

## candidate cards using the same semantics

| Root ID | Rules/source fingerprint | Contract parameters | Existing/new support | Review status |
|---|---|---|---|---|
| `HERO_08bp` Fireblast | "Deal $1 damage." cost 2 | `DAMAGE/EXPLICIT_CHARACTER/1` | existing, re-declared | reviewed |
| `HERO_09bp` Lesser Heal | "Restore #2 Health." cost 2 | `HEAL/EXPLICIT_CHARACTER/2` | new | reviewed, bonus interaction OPEN |
| `HERO_05bp` Steady Shot | "Deal $2 damage to the enemy hero." cost 2 | `DAMAGE/ENEMY_HERO/2` | new | reviewed |
| `HERO_01bp` Armor Up! | "Gain $d2 Armor." cost 2 | `GAIN_ARMOR/SELF/2` | new | reviewed |

Not in scope and still `UNSUPPORTED` (rejected, never aliased): all skin/alternate variants (`HERO_01dbp`, `HERO_05dbp`, `HERO_08aabp`, ...), the other classes' base powers, upgraded/replaced/imbued powers, Quest/Location/Imbue effects.

## dependencies

Non-collectible Hero Power rows `HERO_01bp`, `HERO_05bp`, `HERO_09bp` (metadata only, in `experiments/manaengine/data/hero_power_dependency_metadata.json`, rows copied verbatim from the pinned capture; `HERO_08bp` stays in `dependency_metadata_audit.json`). No tokens, pools or enchantments. Not part of the Standard collectible pool or registry.

## required engine/generator changes

* Native: `hero_power.hpp` (reviewed starting table, reviewed step set), `PlayerState::hero_power_id`, `GameSession::{hero_power_definition, hero_power_cost, hero_power_targeted, hero_power_usable, use_hero_power}`, `DamageKind::HeroPower` selection in `resolve_effects`, appended `TargetSelector::EnemyHero`, catalog validation, observation/semantic/legal/invariant call sites, appended `FailureCode::UNSUPPORTED_HERO_POWER = 59` (Unsupported). The Mage-only constructor gate is replaced by the table.
* Python: `ENEMY_HERO` allowlist entry, failure-kind row, session constructor defers to the native gate, `action_from_dict` accepts an untargeted `HERO_POWER`.
* Declarations: four rows in `card_abilities.json`. New card-ID behaviour branch: **none**.
* Public schemas: see the completion record (the only observable action change is the missing `target_entity_id` for untargeted powers).

## expected unlock count

Unique registerable Standard roots: 0 (not a card package). Newly simulatable seats: Priest, Hunter, Warrior. Training eligibility 0; verified closures unchanged. The per-seat unsupported-card-in-hand gate is unchanged, so most real Priest/Hunter/Warrior decks still fail closed on their cards.

## test strategy

Native `manaengine_tests --hero-power` (independent expectations from printed text): all 16 pairings with identity from both perspectives; rejected classes and missing/unsupported starting power; Fireblast regression (targets, damage, Spell Damage immunity, Divine Shield, Armor, lethal); Lesser Heal (all characters, friendly/enemy, caps, full Health, bonus per packet, opponent bonus ignored, cross-side bonus fail-closed); Steady Shot (untargeted, Taunt, Armor, Spell Damage, lethal, frozen hero); Armor Up! (no Health change, accumulation); a 16-pair rules-model matrix; Mana boundary and once-per-turn across turns for both perspectives; clone independence; raw/semantic parity, illegal shapes without poisoning; identity-not-from-class and fail-closed for unknown/unsupported/non-power identities; extensibility with two synthetic powers; 10 invalid declarations; random mixed-class trajectories. Python `test_hero_powers.py`: catalog/provenance, pairings, typed class rejection, untargeted round trip, healing-bonus end to end, encoder/vocabulary compatibility, admission unchanged. Differential Mage-mirror transcript against the unmodified baseline build. Source checks: failure inventory, generator guard, generated artifacts, ruff, full pytest.

## custom outliers

None. Deferred: Imbue, Quest, Location, replacement/upgrade mechanics, the remaining six classes, cost modifiers, extra uses, real-state import, any hero-power-aware search.

## Completion record

See `reports/manaengine_gate0_hero_powers_20261008/COMPLETION.md`.
