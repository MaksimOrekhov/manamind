# CAPABILITY PACKAGE PROPOSAL — ENGINE-PRIMITIVE-1 Healing pipeline v1

## package_id

`engine_primitive1_healing_v1`, revision 1, 2026-10-08. Base: `origin/main` `d69a093`. Pinned inputs: `data/cards/standard_current_enUS.json` (profile `standard_full_20261001_v1`), Power.log evidence corpus `data/processed_evidence/collected` (32 processed Ranked Standard games, extractor `evidence-0b.1`, client build 253216). Selection basis: the ENGINE-PRIMITIVE-1 audit (decision-weighted real-game coverage, Priest healing core).

## semantic capability

Contract `healing_pipeline` v1, classified **REUSABLE_CAPABILITY** (event ownership + persistent controller state + several shared primitives, no card-ID dispatch).

**Healing packet.** One restoration of Health to one character by one source controller. Calculation, in this order, per packet:

1. `base` is the printed `#N` amount (Heal step) or, for Lifesteal, the damage the damage packet reported.
2. `effective = base + bonus(source controller)`; the controller-owned additive healing bonus applies to **each** packet, not to an aggregate. Bonuses from several sources add (each Cleansing Cleric adds its own 2).
3. `restored = min(effective, max_health - current_health)` using the character's own maximum Health (heroes: `hero_max_health`, a separate field from current Health).
4. Current Health increases by `restored`. Armor, Divine Shield, Immune and Stealth are not involved; healing never changes maximum Health.

**Sources routed through the pipeline (single implementation).** `HEAL` effect steps; Lifesteal healing in `apply_damage_packet`; the existing `HEAL_ENEMY_HERO` damage followup. Each Lifesteal damage packet is its own healing packet (Devouring-Plague-style splits get +bonus per packet).

**Targets.** Existing `EXPLICIT_CHARACTER`; new `EXPLICIT_FRIENDLY_CHARACTER` (hero or minion controlled by the caster, enforced at legality and again at execution); new `ALL_FRIENDLY_CHARACTERS` (own hero first, then own minions left to right; with no healing triggers the order is not observable).

**Persistent bonus.** New effect kind `GRANT_HEALING_BONUS` (target `SELF`, amount 1..100): adds `amount` to the caster's bonus for the rest of the game. It is not tied to the creating minion (survives its death or silence), is not removed at end of turn, and is stored on the player, never on a card instance.

**Sequencing.** Effect steps run in declaration order inside the existing outer spell/battlecry boundary. Moonwell/Holy Nova therefore apply their damage group (including reactions) before the heal; deaths remain owned by the outer boundary. A healing packet or area never mutates when any selected target is mortally wounded (Health <= 0 awaiting the death phase): the whole instruction fails closed with `HEAL_MORTALLY_WOUNDED_UNREVIEWED` before any mutation. The Lifesteal source keeps the previously reviewed scalar behaviour (no pending-death check on the source hero).

**Fail closed.** (a) A source controller with a non-zero bonus healing a character it does not control raises the new RuleUnresolved code `HEALING_BONUS_SCOPE_UNREVIEWED` (evidence gap, see below). (b) Invalid selector/kind combinations, non-positive amounts, out-of-range bonus, and the new kinds/selectors inside Choose One fail catalog load. (c) A bonus total above 1000 fails `NUMERIC_RANGE_VIOLATION`.

**Explicitly excluded.** Overheal/"after a character is healed" triggers, heal-to-damage conversion (Ruby Sanctum), healing multipliers (Velen), dynamic amounts (Amber Priestess), random-split healing, hero power heals, Excess-heal damage, hero starting Health other than 30, non-numeric bonus sources (the numeric total is public, see below).

**Why another card is declaration-only.** `ALL_FRIENDLY_CHARACTERS`/`EXPLICIT_FRIENDLY_CHARACTER`/`HEAL` with any amount and `GRANT_HEALING_BONUS` with any amount are parameters; native tests use synthetic second consumers (a +1 minion, a +3 spell, a friendly-only area heal) without a code change.

## existing RosettaStone primitives

Not used; ManaEngine is the development backend (AGENTS.md). Existing ManaEngine primitives reused: `EFFECT_COMPOSITION` effect lists, `DAMAGE` on `ENEMY_CHARACTERS`/`ENEMY_MINIONS` with the damage-group boundary, `DRAW`, targeting legality (`legal_targets`), `HEAL_MORTALLY_WOUNDED_UNREVIEWED`, Lifesteal flag on damage steps and minions.

## candidate cards using the same semantics

| Root ID | Rules/source fingerprint | Contract parameters | Existing/new support | Review status |
|---|---|---|---|---|
| `EDR_476` Moonwell | pinned text "Deal $4 damage to all enemy characters. Restore #4 Health to all friendly characters." | `DAMAGE/ENEMY_CHARACTERS/4`, `HEAL/ALL_FRIENDLY_CHARACTERS/4` | new | in scope |
| `CORE_CS1_112` Holy Nova | "Deal $2 damage to all enemy minions. Restore #2 Health to all friendly characters." (current text: minions only) | `DAMAGE/ENEMY_MINIONS/2`, `HEAL/ALL_FRIENDLY_CHARACTERS/2` | new | in scope |
| `CORE_CFM_604` Greater Healing Potion | "Restore #12 Health to a friendly character. Draw a card." | `HEAL/EXPLICIT_FRIENDLY_CHARACTER/12`, `DRAW/SELF/1` | new | in scope |
| `CATA_216` Cleansing Cleric | "Battlecry: Your healing effects restore 2 more Health this game." 4-mana 4/5 Draenei | `GRANT_HEALING_BONUS/SELF/2` | new | in scope, rules evidence below |
| `CORE_AT_055`, `CORE_TRL_307`, `CORE_EX1_011`, `CATA_303` | existing healing consumers | unchanged declarations | existing | regression controls (they now see the bonus) |

Deferred (not implemented): Lightshower Elemental (Deathrattle effect list), Priest of An'she ("if you've restored Health this turn"), Amber Priestess (dynamic amount), Lingering Spirit, Ruby Sanctum (Location + conversion), Siphon Soul/Lifedrinker/Healing Rain (other selectors).

### Rules basis and bounded uncertainty

Rules basis: **REVIEWED** for packet calculation, additive stacking, persistence, per-packet Lifesteal application, Health caps; **OPEN** for cross-side healing (see below) which is failed closed rather than inferred. Cleansing Cleric evidence (32 games, `evidence-0b.1`, build 253216): the Cleric creates enchantment `CATA_216e` attached to the controller's player entity (55 attach facts, 0 `ENCHANTMENT_REMOVED`, 39 Cleric deaths); Devouring Plague Lifesteal packets of 1 heal 1 / 3 / 5 with zero / one / two Clerics; Moonwell heals 4 / 6 / 8; after every Cleric of a game died, packets of 3 (one Cleric) and 5 (two Clerics) are still observed; `HEALING_PACKET.amount` equals the real change of the damage tag, i.e. the post-cap restored Health. Unverified: a bonus holder healing the opponent's character (only one capped sample exists). Invalidation: any client build / rules text change of the four cards or `CATA_216e`. Training impact: none (no canonical admission change).

## dependencies

None new. The Cleric enchantment `CATA_216e` is an observation-only identity (type ENCHANTMENT, attached to a player) taken from evidence; it is not materialised in the engine and no token/outcome dependency exists. No dynamic pools.

## required engine/generator changes

* Native: append `EffectKind::GrantHealingBonus`, `TargetSelector::AllFriendlyCharacters` and `ExplicitFriendlyCharacter`; `PlayerState::{hero_max_health, healing_bonus}`; one `apply_healing_packet` used by Heal steps, Lifesteal and the damage followup; catalog validation; friendly-only legality; append-only `FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED`; invariant checks for the new fields.
* Python: allowlists in `_EFFECT_KINDS`/`_TARGET_SELECTORS`, failure-kind table, no card-ID branches.
* Declarations: four cards in `card_abilities.json` (no generator, no per-card native code).
* New card-ID behaviour branch: **none**.
* Observation (review revision): new nullable public field `PlayerObservation.healing_bonus` (`None` = unknown for historical imports and the Rosetta bridge, never inferred as 0; ManaEngine exports the exact value for both seats, 0 included). It is deliberately not an encoder feature, so `STATE_ENCODING_SCHEMA_VERSION` (16), feature names and Policy v1/v2 checkpoints are unchanged; consuming it later needs an encoder schema bump and retraining. No `CATA_216e` identity is fabricated and `active_effects` stays empty. Restore-to-full (`HEAL_MINION_TO_FULL`) is routed through the same pipeline as a packet of exactly the missing Health, which no bonus can change, so it is exempt from the cross-side fail-closed rule.

## expected unlock count

Unique registerable Standard roots: 4 (`EDR_476`, `CORE_CS1_112`, `CORE_CFM_604`, `CATA_216`). Dependency/outcome IDs: 0. Verified closures / eligible roots: unchanged, training eligibility 0. Observed real-game value: decision-weighted +6.3 pp chosen-action coverage (audit estimate).

## test strategy

Native (`manaengine_tests --healing`): independent expectations written from the rules text. Single-target and area healing, friendly-only restriction (legality and execution), damaged/undamaged/full, hero cap 30, minion cap by own maximum, overheal, multi-source stacking, per-packet Lifesteal (several packets, armor-absorbed and capped), source ownership (opponent bonus does not apply; own damage vs opponent heal), damage/heal order and lethal-to-enemy ordering, mortally wounded friendly target atomicity, cross-side fail-closed, invalid declarations, bonus persistence after the Cleric dies and across turns, clone independence, no change when the bonus is zero. Python: declaration reach, play of all four cards through the session, regression of existing healing cards, Mage hero power, legality actions encoding. Source checks: failure inventory, generator branch guard, generated artifacts, ruff, full pytest.

## custom outliers

None. Deferred cards above stay UNSUPPORTED.

## Completion record

See `reports/manaengine_healing_v1_20261008/COMPLETION.md`.
