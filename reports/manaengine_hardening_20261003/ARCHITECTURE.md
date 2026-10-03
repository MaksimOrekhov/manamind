# ManaEngine Phase 2 architecture record

Base checkpoint: `339b51ebf9d9bede781bcf448eba34a23d83a36e` (`codex/manaengine-prototype`).
Hardening branch: `codex/manaengine-hardening`.

## Design constraints

- Keep `EngineState` authoritative and export only the current player's visible `GameState` projection.
- Keep RosettaStone and the original prototype checkpoint intact. All Phase 2 changes live on this branch.
- Never let a missing/unknown implementation map to a vanilla no-op. Support status is explicit and unsupported outcomes invalidate that branch.
- Legal action descriptions contain semantic source/target/choice data; entity IDs remain only execution handles.
- A card instance is one value moved between zones. `CardDefinition` stays immutable printed metadata; mutable cost/stats/flags/counters belong to `CardInstance`.
- Keep engine primitives small and typed. Composite cards declare short ordered lists of those primitives; unique mechanics keep explicit custom handlers.
- Stable random results use a documented integer generator mapping and shuffle, not standard-library distribution/shuffle algorithms.

## Implemented instance model

```cpp
struct CardInstance {
  int entity_id, owner, controller, zone_position, cost_delta;
  Zone zone;
  string card_id, provenance;
  int attack, health, max_health, durability, current_durability;
  bool can_attack, rush, rush_only, frozen, taunt, divine_shield;
  bool stealth, silenced, immune, has_attacked_this_turn;
  vector<string> enchantments;
  unordered_map<string, int> counters;
};
```

Deck, hand, board, graveyard and equipped weapon store `CardInstance` values; moves preserve entity ID and update zone/position. `HandCard`, `MinionState` and `WeaponState` are aliases of this value type. Hero-only fields stay on `PlayerState`; immutable printed facts stay in `CardDefinition` shared through `CardCatalog`.

This is not complete behavior support: transformation/copy operations, deck buffs, generic enchantment application/removal and ownership changes remain unimplemented. A narrow prototype hook updates held instances when the active player directly plays a spell from hand: after removing that spell from hand and before resolving its effects, each remaining hand instance increments `spells_played_from_hand` and receives its configured cost reduction. Cards drawn by the spell effect therefore start at zero. Two copies, a later-drawn copy, current cost/legal-action agreement and deep-clone branch independence are tested with the `TEST_HELD_TRACKER` fixture. This does not define replayed, generated, nested or auto-cast semantics and is not evidence for a profile card such as Shadow of Demise.

The public observation retains its existing player-visible types. Add only the backend-independent `hero_frozen: bool | None` field because `PlayerObservation` cannot currently represent that visible state. Increment state encoder schema version; old checkpoints must follow the repository's declared schema-compatibility behavior rather than silently reinterpreting weights. For policy action schema, append semantic features by name and use the existing name-based checkpoint migration that zero-initializes newly added input columns.

## Typed effect composition

`EffectStep` currently allowlists `Damage`, `Draw`, `GainArmor`, `ModifyHeroAttack` and `Freeze`, plus explicit target selectors. The JSON loader rejects unknown tags, unknown selectors, malformed fields and invalid combinations. Resolution runs the declared sequence in order through engine state operations. Frostbolt is composed as `Damage → Freeze`; Hellfire, Fan of Knives, Press the Advantage and Static Shock use the same renderer route. Triggers and unique mechanics remain named native handlers. `Heal`, `ModifyStats`, `ModifyCost`, `Summon`, `Destroy`, `AddCardToHand` and `EquipWeapon` remain future candidates; this pass does not claim them as generic effects.

## Action contract

Keep execution identity (`attacker_entity_id`, `target_entity_id`) in the boundary object used by `apply_action`. Add a separate semantic descriptor payload for card/source/target/choice identity and visible features. The policy encoder reads only semantic fields, including `choice_index`; it never reads execution IDs. Descriptor identity is stable while entity handles may change after clone or divergence.

## Explicit unresolved prototype limits

Prototype trigger/death processing is explicitly FIFO: drain pending triggers, remove all currently dead minions in player/board order, resolve queued deathrattles FIFO, then repeat to stability. It is not full Hearthstone event ordering. RNG uses `std::mt19937_64` raw output, uint64 rejection mapping `threshold = (0 - n) % n`, and Fisher-Yates from `i=n` down to 2 with `j=bounded_random(i)`. Golden vectors pin raw output, range picks and shuffle order.

This pass does not establish full class/hero-power coverage, all Standard dynamic pools, or training readiness. Unsupported random/generated/deck-pool results invalidate the branch without pruning the pool. Passing bounded property/fuzz tests guards state integrity; it is not a rules-correctness proof. Windows tests ran locally. Ubuntu/macOS green status awaits the newly added experimental CI workflow.
