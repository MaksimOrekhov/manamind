# Meta Training Profile v1 capability queue (updated after package 2)

Ranking uses target-deck reuse, existing RosettaStone support, dependency cost,
dynamic-pool complexity, correctness risk, declaration-only likelihood, and
Training Profile v1 usefulness. Candidates remain proposals until card text,
native definitions, dependencies and scenario expectations are reviewed.

| Rank | Candidate package | Reviewed profile candidates | Decks advanced | Existing primitives / likely shared work | Dependency and risk notes | Expected reuse / current view |
|---:|---|---|---:|---|---|---|
| Done | `targeted_spell_damage_hero_attack_v1` | `TIME_218` Static Shock; `END_007` Press the Advantage | 3 | Existing effect-composition declaration schema and `BTA_02pe` were independently checked. No shared renderer change. | Native family tests, bridge target/action parity, and explicit profile-scoped evidence pass. The roots do not complete their deck closures. | 2/2 declarations, 2 current profile-scoped roots; 0 training-eligible roots. See proposal completion record. |
| Done | `profile_deck_minion_cost_threshold_v1` | `JAIL_327` Reinforcement Aura; `JAIL_516` Scarlet Recruiter | 1 | Added a strict shared live-deck minion/current-cost selector declaration renderer over existing RosettaStone tasks. | Native and bridge profile-scoped family scenarios pass; `TLC_438` remains unsupported, so Beatrix closure is not complete. | 2/2 declarations; +2 current profile-scoped roots; 0 closures/eligibility. See proposal completion record. |
| 1 — review next | `shaman_spell_threshold_hand_transform_v1` | `JAIL_801` Molten Gold; `JAIL_803` Frostshatter; `JAIL_805` Stormfury | 1 | Shared rule: after three spells are cast while each card is held, that instance transforms into its fixed minion form. Existing `TransformTask`, spell counters and Infuse's held-card processing are adjacent primitives. | The engine only applies Infuse counters during minion-death handling. A spell-cast counter attached to held card instances needs exact trigger timing and same-event ordering review; transformed token records also need pinned identity. Do not begin until this is shown to fit without a core session/event-order change. | 3 similar roots in one Shaman list, strong declarative reuse if the in-hand event contract fits existing lifecycle safely. Current leading candidate, not yet approved as implementation. |
| 2 | `cannoneer_fire_network_v1` | `CAP_102`, `CAP_103`, `CAP_106`; `CAP_104` only in a separate continuous-damage contract | 2 | Existing token, attack-trigger, damage and summon tasks may cover pieces. | The shared Fire behavior crosses hero-attack triggers, random target choice and additional shots. `CAP_102` token summon alone is not enough to claim full support for `CAP_106`. High event-order risk. | Multiple Warrior roots across two lists, but no clean low-risk package boundary yet. |
| 3 | `fabled_deck_seed_setup_v1` | `TIME_009`, `TIME_020`, `TIME_875` and six external noncollectible seed candidates; later `JAIL_397`/Scarlet Bruiser only after a separate review | 3–4 | Fabled deck composition/start-of-game seed handling may be shared across classes. | Token identities, initial deck contents, setup timing, DH session and Rogue opponent-deck handling need review. This may require session lifecycle changes. | High cross-class leverage, but stop-condition risk is material. |
| 4 | `discover_and_random_pool_families` | The current audit has 41 distinct unresolved pool definitions reachable from profile roots | 9+ | Existing Discover, random selection and deck/class/type filters can be reused only after exact predicate review. | Broad correctness risk: pinned memberships, state-dependent filters and unsupported outcomes. Never narrow pools. Choice-related changes are a stop condition. | High potential episode gain, poor first-package ROI until exact pools are grouped and measured. |

## Ranking notes

- The first two packages produced four current profile-scoped roots across
  four decks, but no complete deck closures. Canonical Standard admission is
  still blocked.
- The next highest-yield semantic cluster is the Shaman three-spell in-hand
  transform family. Its proposal must establish trigger ordering and token
  identity before any implementation. If that needs broad session/event
  changes, stop and report rather than widening the package.
- Global Standard coverage is secondary. Unrelated candidates remain out of
  scope unless they are a reviewed dependency or a necessary independent
  control declaration for a universal contract.
